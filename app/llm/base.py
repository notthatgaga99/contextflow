from app.models.proposal import TaskProposal


def validate_proposal(raw: dict) -> TaskProposal:
    """Coerce a provider dict into a validated TaskProposal. Never trusted as truth."""
    if raw is None:
        return TaskProposal()
    try:
        return TaskProposal(**raw)
    except Exception:
        return TaskProposal(
            task_id=raw.get("task_id") if isinstance(raw, dict) else None,
            is_new_task=bool(raw.get("is_new_task", True)) if isinstance(raw, dict) else True,
            confidence=float(raw.get("confidence", 0.0)) if isinstance(raw, dict) else 0.0,
            referent=raw.get("referent") if isinstance(raw, dict) else None,
            rationale=str(raw.get("rationale", "")) if isinstance(raw, dict) else "",
        )
