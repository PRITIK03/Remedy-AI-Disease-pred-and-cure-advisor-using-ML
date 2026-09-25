"""Single controlled guidance workflow (LangGraph).

    START → load_assessment → retrieve_evidence → generate_guidance
          → safety_check → review_router ─┬─ finalize
                                           ├─ human_review → finalize
                                           └─ error → END

This is an orchestration workflow, not an autonomous agent: every edge is
hard-coded, every route is a pure function of state, and the LLM has no
write access to anything (no DB writes, no filesystem, no network of its
own — it only answers through the existing llm client).
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.app.agents.routing import (
    build_review_payload,
    route_after_load,
    route_after_safety,
)
from backend.app.agents.state import GuidanceGraphState
from backend.app.core.logging import get_logger

logger = get_logger("backend.agents.graph")


def build_guidance_graph(db, assessment_id: str, llm_client=None):
    """Compile the guidance workflow bound to one assessment run.

    Nodes are thin closures over the current DB session (request-scoped) so
    the existing services can be reused unchanged.
    """
    from backend.app.agents.nodes import (
        make_generate_guidance_node,
        make_load_assessment_node,
        make_retrieve_evidence_node,
        make_safety_check_node,
    )

    builder = StateGraph(GuidanceGraphState)

    builder.add_node("load_assessment", make_load_assessment_node(db, assessment_id))
    builder.add_node("retrieve_evidence", make_retrieve_evidence_node(db))
    builder.add_node("generate_guidance", make_generate_guidance_node(db, llm_client))
    builder.add_node("safety_check", make_safety_check_node(db))

    def review_router(state: GuidanceGraphState) -> dict[str, Any]:
        """Attach the review decision to state (single writer, deterministic)."""
        from backend.app.agents.routing import review_reason

        route = route_after_safety(state)
        if route == "human_review":
            return {
                "review_required": True,
                "review_reason": review_reason(state),
                "review_status": "pending",
                "workflow_status": "pending_review",
                "metadata": {"review_payload": build_review_payload(state)},
            }
        return {"review_required": False, "review_status": "not_required"}

    def human_review(state: GuidanceGraphState) -> dict[str, Any]:
        """Workflow boundary: pause for human review (demo-safe).

        With a checkpointer the graph interrupts here; approval happens
        through the resume operation in service.py. Nothing here pretends a
        clinician approved anything.
        """
        # When reached without interrupt (e.g. no checkpointer), the state
        # simply records the pending boundary; the API maps it to 202-style
        # metadata. No auto-approval of high-risk cases ever happens.
        return {
            "workflow_status": "pending_review",
            "metadata": {"review_boundary": "reached"},
        }

    def finalize(state: GuidanceGraphState) -> dict[str, Any]:
        if state.get("workflow_status") == "pending_review":
            return {}  # do not overwrite the pending marker
        return {"workflow_status": "finalized"}

    def error_node(state: GuidanceGraphState) -> dict[str, Any]:
        if state.get("workflow_status") != "pending_review":
            return {"workflow_status": "failed"}
        return {}

    builder.add_node("review_router", review_router)
    builder.add_node("human_review", human_review)
    builder.add_node("finalize", finalize)
    builder.add_node("error", error_node)

    builder.add_edge(START, "load_assessment")
    builder.add_conditional_edges(
        "load_assessment", route_after_load,
        {"retrieve_evidence": "retrieve_evidence", "error": "error"},
    )
    builder.add_edge("retrieve_evidence", "generate_guidance")
    builder.add_edge("generate_guidance", "safety_check")
    builder.add_conditional_edges(
        "safety_check", route_after_safety,
        {
            "finalize": "finalize",
            "human_review": "review_router",
            "error": "error",
        },
    )
    builder.add_edge("review_router", "human_review")
    builder.add_edge("human_review", "finalize")
    builder.add_edge("finalize", END)
    builder.add_edge("error", END)

    return builder.compile(checkpointer=_make_checkpointer())


_checkpointer_instance = None


def _make_checkpointer():
    """PostgreSQL-backed checkpointer for the real app path; in-memory only
    as a local/dev/test fallback when the DB package/connection is missing.

    The instance is cached process-wide: resume (get_state/update_state) must
    see the checkpoints written by earlier invocations, which requires the
    SAME checkpointer across calls.

    Using the assessment UUID as thread_id works for this unauthenticated
    demo; it MUST change when auth/multi-user isolation arrives (see
    docs/langgraph-architecture.md).
    """
    global _checkpointer_instance
    if _checkpointer_instance is not None:
        return _checkpointer_instance

    import os

    if os.environ.get("AGENTS_CHECKPOINTER", "").lower() == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        _checkpointer_instance = InMemorySaver()
        return _checkpointer_instance

    try:
        from langgraph.checkpoint.postgres import PostgresSaver

        from backend.app.core.config import get_settings

        dsn = get_settings().database_url.replace(
            "postgresql+psycopg://", "postgresql://", 1
        )
        checkpointer = PostgresSaver.from_conn_string(dsn)
        # PostgresSaver.from_conn_string returns a context-managed sync
        # connection wrapper; setup() creates its tables (idempotent).
        checkpointer.setup()
        _checkpointer_instance = checkpointer
        return _checkpointer_instance
    except Exception as exc:  # noqa: BLE001 - graceful dev fallback
        logger.warning(
            "PostgreSQL checkpointer unavailable (%s); falling back to "
            "in-memory checkpointer for local development only.", exc,
        )
        from langgraph.checkpoint.memory import InMemorySaver

        _checkpointer_instance = InMemorySaver()
        return _checkpointer_instance
