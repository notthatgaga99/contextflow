from app.config import Settings, NEW_ID
from app.domain import Transition
from app.models.proposal import Candidate, GateDecision
from app.models.context import Conflict


def _delta(settings: Settings) -> float:
    return getattr(settings, "DELTA", settings.THETA)


def gating_quantity(cands: list[Candidate], settings: Settings,
                    platt: tuple[float, float] | None = None) -> float:
    """Discriminative evidence: top_raw - runner_raw. Not a probability.

    `platt` is ignored until a held-out calibration layer exists.
    """
    del settings, platt
    top_raw = cands[0].raw
    runner_raw = cands[1].raw if len(cands) > 1 else 0.0
    return top_raw - runner_raw


def _diagnostics(cands: list[Candidate], active_id: str | None,
                 settings: Settings) -> dict:
    top_c = cands[0]
    runner_c = cands[1] if len(cands) > 1 else None
    top_raw = top_c.raw
    runner_raw = runner_c.raw if runner_c is not None else 0.0
    top_norm = top_c.norm
    runner_norm = runner_c.norm if runner_c is not None else 0.0
    open_tasks = [c for c in cands if c.task_id != NEW_ID]
    active = next((c for c in cands if c.task_id == active_id), None) if active_id else None
    active_raw = active.raw if active is not None else 0.0
    return {
        "top_raw": top_raw,
        "runner_raw": runner_raw,
        "raw_margin": top_raw - runner_raw,
        "top_norm": top_norm,
        "runner_norm": runner_norm,
        "norm_margin": top_norm - runner_norm,
        "open_task_count": len(open_tasks),
        # Count of tasks with enough absolute evidence to be a real alternative.
        # Not a new score term; logging only. Open-task count != interference.
        "plausible_candidate_count": sum(1 for c in open_tasks if c.raw >= settings.TAU),
        "active_task": active_id,
        "active_raw": active_raw,
        "active_gap": (top_raw - active_raw) if active_id is not None else 0.0,
    }


def decide(cands: list[Candidate], conflict: Conflict | None, active_id: str | None,
           settings: Settings, platt: tuple[float, float] | None = None,
           statuses: dict[str, str] | None = None,
           turns_since: dict[str, int] | None = None) -> GateDecision:
    """ACT vs CLARIFY. LLM-free, retrieval-free, no memory mutation.

    Order:
      1. explicit conflict → CLARIFY
      2. TAU: top_raw >= TAU else CLARIFY
      3. HYST: if challenger beats active by less than HYST, stick CONTINUE
      4. DELTA: raw_margin >= DELTA else CLARIFY
      5. NEW / CONTINUE / SWITCH / RETURN
    """
    del platt  # calibration is a later layer; do not use as P(correct)
    statuses = statuses or {}
    turns_since = turns_since or {}
    diag = _diagnostics(cands, active_id, settings)
    top_c = cands[0]
    raw_margin = diag["raw_margin"]
    delta = _delta(settings)

    def gd(tr, tid):
        return GateDecision(
            transition=tr, task_id=tid,
            top=diag["top_norm"], margin=raw_margin,
            gating_quantity=raw_margin, conflict=conflict, candidates=cands,
            **diag,
        )

    if conflict is not None:
        return gd(Transition.CLARIFY, None)
    if diag["top_raw"] < settings.TAU:
        return gd(Transition.CLARIFY, None)

    # Stick to the active task when the challenger only barely wins on raw.
    if (active_id is not None and top_c.task_id != active_id
            and top_c.task_id != NEW_ID):
        if diag["active_gap"] < settings.HYST:
            return gd(Transition.CONTINUE, active_id)

    if raw_margin < delta:
        return gd(Transition.CLARIFY, None)
    if top_c.task_id == NEW_ID:
        return gd(Transition.NEW, None)

    tid = top_c.task_id
    if tid == active_id:
        return gd(Transition.CONTINUE, tid)
    if statuses.get(tid) == "paused" and turns_since.get(tid, 0) > settings.COLD:
        return gd(Transition.RETURN, tid)
    return gd(Transition.SWITCH, tid)


def bind_task(cands: list[Candidate], conflict: Conflict | None, active_id: str | None,
              settings: Settings, statuses: dict[str, str], turns_since: dict[str, int],
              task_id: str) -> GateDecision:
    """CONTINUE/SWITCH/RETURN for a task already chosen by the referent resolver.

    Does not re-apply TAU/DELTA/HYST; those remain scorer-ranking policy.
    """
    del conflict
    diag = _diagnostics(cands, active_id, settings)
    raw_margin = diag["raw_margin"]

    def gd(tr, tid):
        return GateDecision(
            transition=tr, task_id=tid,
            top=diag["top_norm"], margin=raw_margin,
            gating_quantity=raw_margin, conflict=None, candidates=cands,
            **diag,
        )

    if task_id == active_id:
        return gd(Transition.CONTINUE, task_id)
    if statuses.get(task_id) == "paused" and turns_since.get(task_id, 0) > settings.COLD:
        return gd(Transition.RETURN, task_id)
    return gd(Transition.SWITCH, task_id)


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
