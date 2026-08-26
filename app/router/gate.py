import math

from app.config import Settings, NEW_ID
from app.domain import Transition
from app.models.proposal import Candidate, GateDecision
from app.models.context import Conflict


def _platt(margin: float, platt: tuple[float, float] | None) -> float:
    if platt is None:
        return margin
    a, b = platt
    return 1.0 / (1.0 + math.exp(-(a * margin + b)))


def gating_quantity(cands: list[Candidate], settings: Settings,
                    platt: tuple[float, float] | None = None) -> float:
    top = cands[0].norm
    runner = cands[1].norm if len(cands) > 1 else 0.0
    return _platt(top - runner, platt)


def decide(cands: list[Candidate], conflict: Conflict | None, active_id: str | None,
           settings: Settings, platt: tuple[float, float] | None = None,
           statuses: dict[str, str] | None = None,
           turns_since: dict[str, int] | None = None) -> GateDecision:
    statuses = statuses or {}
    turns_since = turns_since or {}
    top_c = cands[0]
    top = top_c.norm
    top_raw = top_c.raw
    runner = cands[1].norm if len(cands) > 1 else 0.0
    margin = top - runner
    gq = _platt(margin, platt)

    def gd(tr, tid):
        return GateDecision(transition=tr, task_id=tid, top=top, margin=margin,
                            gating_quantity=gq, conflict=conflict, candidates=cands)

    if conflict is not None:
        return gd(Transition.CLARIFY, None)
    if top_raw < settings.TAU:
        return gd(Transition.CLARIFY, None)
    if gq < settings.THETA:
        return gd(Transition.CLARIFY, None)
    if top_c.task_id == NEW_ID:
        return gd(Transition.NEW, None)

    # hysteresis: challenger must beat incumbent by HYST
    if active_id is not None and top_c.task_id != active_id:
        inc = next((c.norm for c in cands if c.task_id == active_id), 0.0)
        if top - inc < settings.HYST:
            return gd(Transition.CONTINUE, active_id)

    tid = top_c.task_id
    if tid == active_id:
        return gd(Transition.CONTINUE, tid)
    if statuses.get(tid) == "paused" and turns_since.get(tid, 0) > settings.COLD:
        return gd(Transition.RETURN, tid)
    return gd(Transition.SWITCH, tid)


def clarify_question(cands: list[Candidate], reg) -> str:
    real = [c for c in cands if c.task_id != NEW_ID][:2]
    labels = []
    for c in real:
        t = reg.get(c.task_id)
        labels.append((t.anchor.goal or t.title) if t else c.task_id)
    if len(labels) >= 2:
        return f"Do you mean the {labels[0]}, or the {labels[1]}?"
    if labels:
        return f"Do you mean the {labels[0]}?"
    return "Which task did you mean?"
