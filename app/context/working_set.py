"""Project asserted MemoryItems into ContextPackage fields. Not a second prompt type.

Does not extract memory. Does not choose the workstream (ContextFlow already did).
Superseded/retracted/uncertain items are excluded from the working set.
Sibling loops on the same workstream are excluded when a referent is selected
(referent_id must match, or the item must be workstream-scoped with no referent).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.memory.store import MemoryStore
from app.models.task import Task


@dataclass
class WorkingSetProjection:
    decisions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    item_ids: list[str] = field(default_factory=list)
    recent_changes: list[str] = field(default_factory=list)
    excluded_workstreams: list[str] = field(default_factory=list)


class WorkingContextBuilder:
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
        kind_map = {
            "decision": proj.decisions,
            "constraint": proj.constraints,
            "fact": proj.facts,
            "entity": proj.entities,
            "preference": proj.facts,
            "event": proj.facts,
            "correction": proj.decisions,
        }
        for i in items:
            bucket = kind_map.get(i.kind)
            if bucket is not None:
                bucket.append(i.text)
            proj.item_ids.append(i.id)
            proj.recent_changes.append(f"{i.kind}:{i.text}")
        proj.recent_changes = proj.recent_changes[-3:]
        return proj

    def missing_required(self, proj: WorkingSetProjection, required: list[str]) -> list[str]:
        blob = " ".join(
            proj.decisions + proj.constraints + proj.facts + proj.entities
        ).lower()
        return [r for r in required if r and r.lower() not in blob]

    def insufficient(self, proj: WorkingSetProjection, required: list[str]) -> bool:
        return bool(self.missing_required(proj, required))
