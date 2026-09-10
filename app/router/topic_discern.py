"""Lite-LLM topic discern — same thread vs switch vs new.

Post-gate only. Does not change gate.py / scorer.py thresholds.
Fail-closed: invalid or missing LLM output → caller keeps gate / lexical fallback.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain import LLM, Transition
from app.models.task import Task

DISCERN_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["CONTINUE", "SWITCH", "NEW", "CLARIFY"],
        },
        "task_id": {"type": "string", "nullable": True},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["decision", "confidence"],
}

_MIN_CONF = 0.55


@dataclass
class DiscernResult:
    transition: Transition
    task_id: str | None
    confidence: float
    rationale: str
    reason: str = "llm_topic_discern"


def build_discern_prompt(
    message: str,
    open_tasks: list[Task],
    active_id: str | None,
    memory_texts_by_task: dict[str, list[str]] | None = None,
) -> str:
    mem = memory_texts_by_task or {}
    lines = []
    for t in open_tasks:
        active = "ACTIVE" if t.id == active_id else t.status
        cues = ", ".join((t.retrieval_cues or [])[:8])
        loops = "; ".join((t.anchor.open_loops or [])[:2])
        facts = "; ".join((mem.get(t.id) or [])[:3])
        lines.append(
            f"- id={t.id} [{active}] title={t.title!r} goal={(t.anchor.goal or '')[:120]!r} "
            f"cues=[{cues}] loops=[{loops[:160]}] memory=[{facts[:160]}]"
        )
    cards = "\n".join(lines) or "- (none)"
    return (
        "You classify whether the USER message continues the ACTIVE workstream, "
        "switches to another OPEN workstream, or starts a NEW topic.\n"
        "Rules:\n"
        "- Vague short follow-ups about the same domain (e.g. 'those yamls', 'yml', 'ok?', "
        "'and the config') → CONTINUE on ACTIVE.\n"
        "- Clear return to another open card (e.g. ivory dress while ACTIVE is IoT) → SWITCH "
        "with that task_id.\n"
        "- Clear new domain with no matching open card → NEW (task_id null).\n"
        "- Only CLARIFY if two open cards are equally plausible.\n"
        "- Prefer CONTINUE over NEW when uncertain but ACTIVE is related.\n"
        "- Do not invent task ids.\n\n"
        f"ACTIVE_ID: {active_id or 'none'}\n"
        f'USER: "{message}"\n\n'
        f"OPEN WORKSTREAMS:\n{cards}\n\n"
        'Return JSON: {decision: CONTINUE|SWITCH|NEW|CLARIFY, task_id|null, '
        "confidence 0..1, rationale}"
    )


def _parse(raw: dict, open_ids: set[str], active_id: str | None) -> DiscernResult | None:
    if not isinstance(raw, dict):
        return None
    decision = str(raw.get("decision") or "").strip().upper()
    try:
        conf = float(raw.get("confidence"))
    except (TypeError, ValueError):
        return None
    if conf < _MIN_CONF:
        return None
    tid = raw.get("task_id")
    if tid is not None:
        tid = str(tid).strip() or None
    rationale = str(raw.get("rationale") or "")[:240]

    if decision == "CONTINUE":
        target = tid if tid in open_ids else active_id
        if not target:
            return None
        return DiscernResult(Transition.CONTINUE, target, conf, rationale)

    if decision == "SWITCH":
        if not tid or tid not in open_ids:
            return None
        # RETURN if leaving active for another open card (same act path).
        tr = Transition.RETURN if active_id and tid != active_id else Transition.SWITCH
        if not active_id:
            tr = Transition.SWITCH
        return DiscernResult(tr, tid, conf, rationale)

    if decision == "NEW":
        return DiscernResult(Transition.NEW, None, conf, rationale)

    if decision == "CLARIFY":
        return DiscernResult(Transition.CLARIFY, None, conf, rationale)

    return None


def discern_topic(
    llm: LLM,
    message: str,
    open_tasks: list[Task],
    active_id: str | None,
    memory_texts_by_task: dict[str, list[str]] | None = None,
) -> DiscernResult | None:
    """Ask lite LLM; return None on any failure (caller fails closed)."""
    if not open_tasks and not message.strip():
        return None
    open_ids = {t.id for t in open_tasks}
    prompt = build_discern_prompt(message, open_tasks, active_id, memory_texts_by_task)
    try:
        raw = llm.propose(prompt, DISCERN_SCHEMA)
    except Exception:
        return None
    return _parse(raw if isinstance(raw, dict) else {}, open_ids, active_id)
