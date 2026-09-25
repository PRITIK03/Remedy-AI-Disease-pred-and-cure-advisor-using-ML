"""Conservative safety layer applied BEFORE the LLM response reaches the
frontend.

Not a giant rule engine: a small, auditable set of checks that
(1) screens the user context for requests the system must not fulfill
    (diagnose with certainty, prescribe/dose medication, replace a
    clinician, fabricate evidence) and
(2) appends emergency-escalation language when clearly urgent symptom
    descriptions appear.

Fail-safe posture: when in doubt, the conservative path wins.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.app.core.logging import get_logger

logger = get_logger("backend.rag.safety")

# --- Request screening (context is system-built; this guards future free
# --- text and adversarial payloads) --------------------------------------- #
DIAGNOSIS_REQUEST_RE = re.compile(
    r"\b(do i have|confirm that i (have|don't have)|is this (definitely|certainly)|"
    r"am i (certain|sure) (that )?i)\b",
    re.IGNORECASE,
)
PRESCRIPTION_REQUEST_RE = re.compile(
    r"\b(prescribe|prescription|dosage|dose of|mg of|how much (of )?(insulin|"
    r"metformin|aspirin|statin|warfarin|ibuprofen)|stop taking|change my (dose|"
    r"medication|medicine))\b",
    re.IGNORECASE,
)
CLINICIAN_REPLACEMENT_RE = re.compile(
    r"\b(instead of (a |my )?(doctor|clinician|physician)|i don't need a doctor|"
    r"no need to (see|visit) (a )?doctor)\b",
    re.IGNORECASE,
)
FABRICATION_REQUEST_RE = re.compile(
    r"\b(make up|fabricate|invent) (medical )?(evidence|studies|citations)\b",
    re.IGNORECASE,
)

# --- Emergency escalation -------------------------------------------------- #
EMERGENCY_RE = re.compile(
    r"\b(chest pain|crushing chest|chest pressure|pressure in (my|the) chest|"
    r"pain (spreading|radiating) to (my )?(arm|jaw|neck|back)|shortness of breath "
    r"(at rest|severe)|can'?t breathe|fainting|about to faint|passed out|"
    r"cold (sweat|clammy)|nausea with chest (pain|discomfort)|heart attack)\b",
    re.IGNORECASE,
)

EMERGENCY_NOTICE = (
    "IMPORTANT: If you are experiencing symptoms such as severe chest pain or "
    "pressure, pain spreading to the arm/jaw/back, severe shortness of breath, "
    "fainting, or a cold sweat — call your local emergency number or emergency "
    "services IMMEDIATELY. Do not wait for model output or web guidance."
)

REFUSAL_NOTICE_TEMPLATE = (
    "I can't help with that request. This tool provides general, evidence-based "
    "health information only — it cannot {capability}. Please consult a "
    "qualified healthcare professional."
)


@dataclass
class SafetyVerdict:
    blocked: bool = False
    reason: str | None = None
    escalate_emergency: bool = False
    flagged_terms: list[str] = field(default_factory=list)


def screen_request(text: str) -> SafetyVerdict:
    """Screen a user request; conservative — any hit blocks guidance."""
    checks = [
        (DIAGNOSIS_REQUEST_RE, "diagnose your condition"),
        (PRESCRIPTION_REQUEST_RE, "prescribe medication or adjust dosages"),
        (CLINICIAN_REPLACEMENT_RE, "replace your doctor or clinician"),
        (FABRICATION_REQUEST_RE, "fabricate medical evidence"),
    ]
    for regex, capability in checks:
        m = regex.search(text)
        if m:
            logger.info("Safety screen blocked request (term=%s)", m.group(0))
            return SafetyVerdict(
                blocked=True,
                reason=REFUSAL_NOTICE_TEMPLATE.format(capability=capability),
                flagged_terms=[m.group(0)],
            )
    return SafetyVerdict()


def detect_emergency(text: str) -> SafetyVerdict:
    """Detect clearly urgent symptom descriptions → prepend escalation."""
    m = EMERGENCY_RE.search(text)
    if m:
        return SafetyVerdict(escalate_emergency=True, flagged_terms=[m.group(0)])
    return SafetyVerdict()


def apply_post_safety(guidance_summary: str, source_text: str) -> str:
    """Post-LLM hook: attach the emergency notice when warranted."""
    verdict = detect_emergency(source_text)
    if verdict.escalate_emergency:
        return f"{EMERGENCY_NOTICE}\n\n{guidance_summary}"
    return guidance_summary
