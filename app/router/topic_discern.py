"""Lite-LLM topic discern — same thread vs switch vs new.

Post-gate only. Does not change gate.py / scorer.py thresholds.
Fail-closed: invalid or missing LLM output → caller keeps gate / lexical fallback.
Lexical veto corrects confident-but-wrong LLM labels (demo reliability).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain import LLM, Transition
from app.models.task import Task
from app.router.topic_align import is_underspecified, overlap_score, task_blob

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
_MATCH_KEEP = 0.15
_STEAL_MARGIN = 0.10
_NEW_BLOCK_MATCH = 0.16


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
        "- Short / vague follow-ups on the SAME domain must CONTINUE on ACTIVE "
        "(examples: 'those yamls', 'yml', 'hikes or cafes?', 'ok?', 'and the config', "
        "'bash exit 4' when ACTIVE is already CI/pipeline).\n"
        "- Same engineering saga (Azure Pipelines, YAML files, self-hosted agent, pytest) "
        "stays one workstream even if wording shifts — CONTINUE or SWITCH only among "
        "matching tech cards, never NEW mid-saga.\n"
        "- Clear life/travel/outfit break with no matching open card → NEW "
        "(peplum/hosting dress; Meghalaya trip).\n"
        "- Returning to an older open card (dress while on pipelines, or pipelines while "
        "on dress) → SWITCH with that task_id. Never SWITCH to a card that does not "
        "match the USER topic.\n"
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
        tr = Transition.RETURN if active_id and tid != active_id else Transition.SWITCH
        if not active_id:
            tr = Transition.SWITCH
        return DiscernResult(tr, tid, conf, rationale)

    if decision == "NEW":
        return DiscernResult(Transition.NEW, None, conf, rationale)

    if decision == "CLARIFY":
        return DiscernResult(Transition.CLARIFY, None, conf, rationale)

    return None


def _scores(
    message: str,
    open_tasks: list[Task],
    memory_texts_by_task: dict[str, list[str]] | None,
) -> dict[str, float]:
    mem = memory_texts_by_task or {}
    return {
        t.id: overlap_score(message, task_blob(t, mem.get(t.id)))
        for t in open_tasks
    }


def _bind(active_id: str | None, task_id: str, conf: float, rationale: str, reason: str) -> DiscernResult:
    if active_id == task_id:
        tr = Transition.CONTINUE
    elif active_id and active_id != task_id:
        tr = Transition.RETURN
    else:
        tr = Transition.SWITCH
    return DiscernResult(tr, task_id, conf, rationale, reason=reason)


def refine_discern(
    discerned: DiscernResult,
    message: str,
    open_tasks: list[Task],
    active_id: str | None,
    memory_texts_by_task: dict[str, list[str]] | None = None,
) -> DiscernResult:
    """Lexical veto — fix inverted SWITCH / spurious NEW for demo reliability."""
    if not open_tasks:
        return discerned
    scores = _scores(message, open_tasks, memory_texts_by_task)
    best_id, best_sc = max(scores.items(), key=lambda x: x[1])
    conf = discerned.confidence
    rationale = discerned.rationale

    # Short follow-ups stay on ACTIVE (hikes or cafes?, yml, ok?).
    if active_id and is_underspecified(message):
        if discerned.transition in (Transition.NEW, Transition.CLARIFY) or (
            discerned.task_id and discerned.task_id != active_id
        ):
            return DiscernResult(
                Transition.CONTINUE, active_id, conf, rationale,
                reason="veto_underspecified_stick",
            )

    chosen = discerned.task_id
    chosen_sc = scores.get(chosen or "", 0.0)

    # LLM pointed at a weak card while another card clearly matches.
    if (
        discerned.transition != Transition.NEW
        and chosen
        and best_id
        and best_sc >= _MATCH_KEEP
        and best_sc >= chosen_sc + _STEAL_MARGIN
        and best_id != chosen
    ):
        return _bind(active_id, best_id, conf, rationale, "veto_better_lexical")

    # Spurious NEW while an open card already matches the message.
    if discerned.transition == Transition.NEW and best_id and best_sc >= _NEW_BLOCK_MATCH:
        return _bind(active_id, best_id, conf, rationale, "veto_new_has_match")

    return discerned


def discern_topic(
    llm: LLM,
    message: str,
    open_tasks: list[Task],
    active_id: str | None,
    memory_texts_by_task: dict[str, list[str]] | None = None,
) -> DiscernResult | None:
    """Ask lite LLM; return None on any failure (caller fails closed)."""
    if not message.strip():
        return None
    open_ids = {t.id for t in open_tasks}
    prompt = build_discern_prompt(message, open_tasks, active_id, memory_texts_by_task)
    try:
        raw = llm.propose(prompt, DISCERN_SCHEMA)
    except Exception:
        return None
    parsed = _parse(raw if isinstance(raw, dict) else {}, open_ids, active_id)
    if parsed is None:
        return None
    return refine_discern(parsed, message, open_tasks, active_id, memory_texts_by_task)
