"""Remedy-AI read-only MCP server (Phase 8).

Transport: **stdio** (the default, dev-friendly). The wiring is deliberately
transport-agnostic — `build_server()` returns a configured `MCPServer`, so
Streamable HTTP can be added later by calling `server.run("streamable-http")`
behind an authenticated proxy. No unauthenticated public HTTP server is
started here, by design.

Authentication/ownership model
------------------------------
An MCP server has no browser session, so identity comes from configuration:

* ``MCP_USER_ID`` — the Remedy-AI account UUID this server is bound to
  (required; startup fails without it).
* ``DATABASE_URL`` — used to open one short-lived read-only session per call.

Every tool therefore answers *as that single user*: the tools can only ever
return that account's own assessments and reports, and a foreign id produces
the same "not found" error as a missing one. There is no tool argument that
can widen this scope.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.tools import (  # noqa: E402
    TOOLS,
    ToolContext,
    ToolError,
    assert_read_only_tool_surface,
)
from mcp.types import ToolAnnotations  # noqa: E402

SERVER_NAME = "remedy-ai"
SERVER_VERSION = "2.0.0"

INSTRUCTIONS = """\
Read-only access to a Remedy-AI cardiovascular risk account.

What this server is for
- Inspecting the cardiovascular assessments (model inputs + model output) that
  the bound account has already created.
- Inspecting uploaded medical reports and what the extraction step proposed.
- Reading safe ML metadata (model version, feature list, target semantics).
- Searching the pre-ingested health-evidence knowledge base.

Hard rules
- READ-ONLY: nothing can be created, modified, deleted, approved or uploaded.
- SCOPED: every answer comes from one specific Remedy-AI account. Passing
  another account's id returns "not found", exactly as for a missing id.
- The probability returned is a MODEL ESTIMATE from an educational prototype.
  It is not a diagnosis, not a clinical measurement, and not a validated risk
  score. Say so whenever you report it.
"""


class McpConfigurationError(RuntimeError):
    """Raised when the server is started without a bound user."""


def _require_bound_user_id() -> str:
    """The single account this MCP server may ever read."""
    user_id = (os.environ.get("MCP_USER_ID") or "").strip()
    if not user_id:
        raise McpConfigurationError(
            "MCP_USER_ID is required: an MCP server must be bound to exactly "
            "one Remedy-AI account. Refusing to start unscoped."
        )
    return user_id


TOOL_DESCRIPTIONS = {
    "get_assessment": (
        "Get one cardiovascular assessment owned by the bound account, "
        "including the 13 model inputs and the model-estimated probability. "
        "Read-only."
    ),
    "get_assessment_history": (
        "List the bound account's assessments, newest first (limit/offset, "
        "limit capped at 100). Read-only."
    ),
    "get_report_metadata": (
        "Get metadata for an uploaded medical report owned by the bound "
        "account: filename, type, size, extraction status, and how many "
        "metrics the extraction proposed. Never returns the file itself, its "
        "storage path, or its hash. Read-only."
    ),
    "get_model_information": (
        "Safe ML metadata: model version, selected model, feature count and "
        "names, target definition, and evaluation metadata. Contains no "
        "filesystem paths and no serialized model objects. Read-only."
    ),
    "search_health_evidence": (
        "Search the pre-ingested health-evidence knowledge base and return "
        "title, publisher, section, URL and the relevant passage. Only "
        "already-ingested sources are returned; no arbitrary URL fetching. "
        "Read-only."
    ),
}


def _wrap(name: str, fn: Any) -> Any:
    """Bind the tool context and convert typed errors into safe payloads."""

    def _handler(*args: Any, **kwargs: Any) -> Any:
        with _ToolSession() as ctx:
            try:
                return fn(ctx, *args, **kwargs)
            except ToolError as exc:
                # Typed, non-sensitive errors; never a stack trace.
                return {"error": exc.kind, "message": exc.message}

    _handler.__name__ = name
    _handler.__doc__ = TOOL_DESCRIPTIONS[name]
    return _handler


def _register_tools(server: MCPServer) -> None:
    """Register every tool in `mcp.tools.TOOLS` with read-only annotations."""
    for name, fn in TOOLS.items():
        # readOnlyHint/destructiveHint are advisory to clients, but they are
        # the clearest machine-readable statement of this server's contract.
        server.tool(
            name=name,
            description=TOOL_DESCRIPTIONS[name],
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        )(_wrap(name, fn))


def build_server() -> MCPServer:
    """Create the MCP server with every read-only tool registered."""
    assert_read_only_tool_surface()
    server = MCPServer(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        instructions=INSTRUCTIONS,
    )
    _register_tools(server)
    return server


class _ToolSession:
    """Open one short-lived DB session for a single tool call.

    Read-only by construction: every handler reaches data through the
    existing services, and the session is closed immediately afterwards.
    """

    def __enter__(self) -> ToolContext:
        self._user_id = _require_bound_user_id()
        from backend.app.db.session import create_db_engine, create_session_factory
        from backend.app.services.model_service import ModelService

        self._engine = create_db_engine()
        self._session_factory = create_session_factory(self._engine)
        self._session = self._session_factory()
        model_service = ModelService()
        try:
            model_service.load()
        except Exception:  # noqa: BLE001 - metadata tool reports unavailability
            pass
        return ToolContext(
            user_id=self._user_id,
            db=self._session,
            model_service=model_service,
        )

    def __exit__(self, *exc: Any) -> None:
        try:
            self._session.close()
        finally:
            self._engine.dispose()


def main() -> None:
    """Entry point: run over stdio (default transport)."""
    build_server().run("stdio")


if __name__ == "__main__":
    main()

