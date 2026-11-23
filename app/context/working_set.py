"""Project asserted MemoryItems into ContextPackage fields. Not a second prompt type.

Does not extract memory. Does not choose the workstream (ContextFlow already did).
Superseded/retracted/uncertain items are excluded from the working set.
Sibling loops on the same workstream are excluded when a referent is selected
(referent_id must match, or the item must be workstream-scoped with no referent).

Condensation (selection inside the chosen workstream):
- Prefer higher source_turn (more recent).
- Prefer slotted items over unslotted when ranking.
- Cap per kind so answer packages stay lean under noisy extractors.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.memory.store import MemoryStore
from app.models.memory import MemoryItem
from app.models.task import Task


@dataclass(frozen=True)
class WorkingSetLimits:
    """Per-kind caps for answer-package condensation. 0 = unlimited."""

    max_decisions: int = 6
    max_constraints: int = 6
    max_facts: int = 8
    max_entities: int = 8
    max_procedures: int = 6
    max_recent_changes: int = 3


DEFAULT_LIMITS = WorkingSetLimits()


@dataclass
class WorkingSetProjection:
    decisions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    procedures: list[str] = field(default_factory=list)
    item_ids: list[str] = field(default_factory=list)
    recent_changes: list[str] = field(default_factory=list)
    excluded_workstreams: list[str] = field(default_factory=list)


def _rank_key(item: MemoryItem) -> tuple:
    """Higher is better: recent first, slotted before unslotted, stable id."""
    slotted = 1 if (item.slot or "").strip() else 0
    return (item.source_turn, slotted, item.id)


def _take_ranked(items: list[MemoryItem], limit: int) -> list[MemoryItem]:
    ordered = sorted(items, key=_rank_key, reverse=True)
    if limit <= 0 or len(ordered) <= limit:
        return ordered
    return ordered[:limit]


class WorkingContextBuilder:
    def __init__(self, limits: WorkingSetLimits | None = None):
        self.limits = limits or DEFAULT_LIMITS

    def project(
        self,
        task: Task,
        referent_id: str | None,
        store: MemoryStore,
        open_tasks: list[Task] | None = None,
    ) -> WorkingSetProjection:
        proj = WorkingSetProjection()
        if open_tasks:
            proj.excluded_workstreams = [
                t.title or t.id for t in open_tasks if t.id != task.id
            ]
        items = [
            i for i in store.asserted(task.id)
            if not i.uncertain
            and (i.referent_id is None or referent_id is None or i.referent_id == referent_id)
        ]

        buckets: dict[str, list[MemoryItem]] = {
            "decision": [],
            "constraint": [],
            "fact": [],
            "entity": [],
            "procedure": [],
        }
        kind_alias = {
            "decision": "decision",
            "correction": "decision",
            "constraint": "constraint",
            "fact": "fact",
            "preference": "fact",
            "event": "fact",
            "entity": "entity",
            "procedure": "procedure",
        }
        for i in items:
            bucket = kind_alias.get(i.kind)
            if bucket is not None:
                buckets[bucket].append(i)

        lim = self.limits
        selected: list[MemoryItem] = []
        selected.extend(_take_ranked(buckets["decision"], lim.max_decisions))
        selected.extend(_take_ranked(buckets["constraint"], lim.max_constraints))
        selected.extend(_take_ranked(buckets["fact"], lim.max_facts))
        selected.extend(_take_ranked(buckets["entity"], lim.max_entities))
        selected.extend(_take_ranked(buckets["procedure"], lim.max_procedures))
        # Stable package order: decisions → constraints → facts → entities → procedures
        for i in selected:
            if i.kind in ("decision", "correction"):
                proj.decisions.append(i.text)
            elif i.kind == "constraint":
                proj.constraints.append(i.text)
            elif i.kind == "entity":
                proj.entities.append(i.text)
            elif i.kind == "procedure":
                proj.procedures.append(i.text)
            else:
                proj.facts.append(i.text)
            proj.item_ids.append(i.id)
            proj.recent_changes.append(f"{i.kind}:{i.text}")

        # recent_changes: most recent across selected, then cap
        by_turn = sorted(selected, key=_rank_key, reverse=True)
        proj.recent_changes = [
            f"{i.kind}:{i.text}" for i in by_turn[: max(0, lim.max_recent_changes)]
        ]
        return proj

    def missing_required(self, proj: WorkingSetProjection, required: list[str]) -> list[str]:
        blob = " ".join(
            proj.decisions + proj.constraints + proj.facts
            + proj.entities + proj.procedures
        ).lower()
        return [r for r in required if r and r.lower() not in blob]

    def insufficient(self, proj: WorkingSetProjection, required: list[str]) -> bool:
        return bool(self.missing_required(proj, required))
