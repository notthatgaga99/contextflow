"""Structured conversation rollup — condensation for horizon H2 / UI / archive.

Built from registry cards + asserted memory only. Not a transcript summarizer.
Does not write memory, does not route, does not change the answer package path.
Frozen gate / scorer / referent / writer contracts are untouched.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.context.working_set import WorkingContextBuilder, WorkingSetLimits
from app.memory.store import MemoryStore
from app.models.task import Task


@dataclass
class WorkstreamRollup:
    workstream_id: str
    title: str
    goal: str
    status: str
    open_loops: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    last_active_turn: int = 0
    mention_turn: int = 0
    item_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConversationRollup:
    conversation_id: str
    workstreams: list[WorkstreamRollup] = field(default_factory=list)
    open_count: int = 0
    blurb: str = ""
    source: str = "asserted_memory"

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "open_count": self.open_count,
            "blurb": self.blurb,
            "source": self.source,
            "workstreams": [w.to_dict() for w in self.workstreams],
        }


def _blurb_from_titles(tasks: list[Task], *, max_titles: int = 5) -> str:
    titles: list[str] = []
    for t in tasks:
        label = (t.title or t.anchor.goal or t.id or "").strip()
        if label:
            titles.append(label[:64])
        if len(titles) >= max_titles:
            break
    return " · ".join(titles)


def build_conversation_rollup(
    registry,
    store: MemoryStore,
    *,
    conversation_id: str | None = None,
    include_abandoned: bool = False,
    limits: WorkingSetLimits | None = None,
    max_loops: int = 3,
) -> ConversationRollup:
    """Condense a conversation into structured per-workstream rollups.

    Selection rules mirror working-set philosophy: asserted only, capped,
    recent-first. Abandoned workstreams omitted unless include_abandoned.
    """
    cid = (conversation_id or getattr(store, "conversation_id", "") or "").strip()
    builder = WorkingContextBuilder(limits=limits)
    tasks = list(registry.open_tasks())
    if include_abandoned and hasattr(registry, "all"):
        seen = {t.id for t in tasks}
        for t in registry.all():
            if t.id not in seen and getattr(t, "status", "") == "abandoned":
                tasks.append(t)

    # Most recently active first for catalog UX.
    tasks.sort(key=lambda t: (t.last_active_turn, t.mention_turn), reverse=True)

    rolls: list[WorkstreamRollup] = []
    for t in tasks:
        proj = builder.project(t, None, store, open_tasks=None)
        loops = list(t.anchor.open_loops or [])[: max(0, max_loops)]
        rolls.append(
            WorkstreamRollup(
                workstream_id=t.id,
                title=(t.title or t.id),
                goal=(t.anchor.goal or t.title or ""),
                status=t.status,
                open_loops=loops,
                decisions=list(proj.decisions),
                constraints=list(proj.constraints),
                facts=list(proj.facts),
                entities=list(proj.entities),
                last_active_turn=t.last_active_turn,
                mention_turn=t.mention_turn,
                item_count=len(proj.item_ids),
            )
        )

    open_n = len(registry.open_tasks()) if hasattr(registry, "open_tasks") else len(rolls)
    return ConversationRollup(
        conversation_id=cid,
        workstreams=rolls,
        open_count=open_n,
        blurb=_blurb_from_titles(tasks),
    )
