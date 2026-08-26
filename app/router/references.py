import re

from app.config import Settings, NEW_ID
from app.models.task import Task
from app.models.context import Reference, Conflict
from app.models.proposal import Candidate

_PRONOUNS = {"that", "it", "this", "the other thing", "those"}


def parse_reference(message: str) -> Reference:
    m = message.strip().lower()
    # Only treat a number as an ordinal REFERENCE when it follows a referential cue
    # (fix/do/#/number/item/option/step/task) and is small. This avoids reading
    # content numbers like an HTTP 401 as a reference.
    ord_match = re.search(r"(?:#|\b(?:number|item|option|step|task|fix|do)\s+)(\d{1,2})\b", m)
    if ord_match:
        val = int(ord_match.group(1))
        if 1 <= val <= 20:
            return Reference(kind="ordinal", value=val, raw_span=ord_match.group(0).strip())
    ent = re.search(r"the ([a-z0-9]+) (?:thing|issue|bug|task|problem)", m)
    if ent:
        return Reference(kind="entity", value=ent.group(1), raw_span=ent.group(0))
    for p in _PRONOUNS:
        if re.search(rf"\b{re.escape(p)}\b", m):
            return Reference(kind="pronoun", value=p, raw_span=p)
    return Reference(kind="none", value=None, raw_span="")


def detect_conflict(ref: Reference, top: Candidate, task: Task | None,
                    settings: Settings) -> Conflict | None:
    if ref.kind == "ordinal" and task is not None:
        n = int(ref.value)
        loops = task.anchor.open_loops
        if n < 1 or n > len(loops):
            return Conflict(kind="ordinal_out_of_range", explicit_ref=ref,
                            evidence_task_id=task.id,
                            reason=f"ordinal {n} but task has {len(loops)} open loops")
    if ref.kind == "entity" and task is not None and top.task_id != NEW_ID:
        ev = ref.value
        hay = " ".join([task.anchor.goal, task.title] + task.retrieval_cues
                       + task.anchor.open_loops).lower()
        if ev not in hay:
            return Conflict(kind="entity_mismatch", explicit_ref=ref,
                            evidence_task_id=task.id,
                            reason=f"reference '{ev}' not found in routed task evidence")
    return None
