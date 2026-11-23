"""MemoryManager — ContextFlow plane assembly after bind (RB-WSR).

Own design (see docs/MEMORY_MANAGEMENT.md):
  SHORT_TERM  — only surface for generate()
  LONG_TERM   — durable semantic + episodic
  PROCEDURAL  — how-to items; not a dump of every open loop
  RELEVANT    — bound-scoped cold enrich only
  INDEX       — routing cards; never generate body
  ARCHIVE     — never auto-merge

Binder (frozen) selects the hop. This manager only reads MemoryPort and projects.
Learned from field practice; not a port of any vendor memory stack.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any

from app.context.compact_notation import CompactNotation, build_compact_notation
from app.context.working_set import WorkingContextBuilder, WorkingSetLimits
from app.memory.cold_search import (
    ColdHit,
    filter_hits_for_l1,
    hit_item_ids,
    merge_hits_into_facts,
)
from app.memory.planes import (
    DEFAULT_PLANE_POLICY,
    LongTermKind,
    MemoryPlane,
    PlanePolicy,
    design_notes,
    long_term_kind_for,
    plane_catalog,
    plane_for_kind,
)
from app.memory.port import MemoryPort, ThreadCard
from app.models.memory import MemoryItem
from app.models.task import Task


class _AssertedView:
    def __init__(self, items: list[MemoryItem]):
        self._items = list(items)

    def asserted(self, workstream_id: str | None = None) -> list[MemoryItem]:
        if workstream_id is None:
            return list(self._items)
        return [i for i in self._items if (i.workstream_id or "") == workstream_id]


@dataclass
class PlaneSlice:
    """Items (or texts) visible in one plane for the bound context."""

    plane: MemoryPlane
    texts: list[str] = field(default_factory=list)
    item_ids: list[str] = field(default_factory=list)
    count: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plane": self.plane.value,
            "texts": list(self.texts),
            "item_ids": list(self.item_ids),
            "count": self.count if self.count else len(self.texts),
            "meta": dict(self.meta),
        }


@dataclass
class ContextAwareMemory:
    """Full plane view after bind — SHORT_TERM is the only generate surface."""

    workstream_id: str
    referent_id: str | None = None
    query: str | None = None
    short_term: CompactNotation | None = None
    long_term: PlaneSlice = field(
        default_factory=lambda: PlaneSlice(plane=MemoryPlane.LONG_TERM)
    )
    procedural: PlaneSlice = field(
        default_factory=lambda: PlaneSlice(plane=MemoryPlane.PROCEDURAL)
    )
    relevant: PlaneSlice = field(
        default_factory=lambda: PlaneSlice(plane=MemoryPlane.RELEVANT)
    )
    index: PlaneSlice = field(
        default_factory=lambda: PlaneSlice(plane=MemoryPlane.INDEX)
    )
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workstream_id": self.workstream_id,
            "referent_id": self.referent_id,
            "query": self.query,
            "short_term": self.short_term.to_dict() if self.short_term else None,
            "long_term": self.long_term.to_dict(),
            "procedural": self.procedural.to_dict(),
            "relevant": self.relevant.to_dict(),
            "index": self.index.to_dict(),
            "diagnostics": dict(self.diagnostics),
            "planes": plane_catalog(),
            "design": design_notes(),
        }


def _cold_enrich_enabled() -> bool:
    return os.getenv("CF_COLD_ENRICH", "1").strip() != "0"


def _procedural_slice(
    task: Task,
    items: list[MemoryItem],
    *,
    max_procedures: int,
    skills_only_in_l1: bool,
) -> tuple[PlaneSlice, list[str]]:
    """Return (diagnostics slice, L1 procedure texts).

    Control-plane goal/loops stay on CompactNotation.goal / selected_loop.
    L1 PROCEDURAL lists how-to steps (`kind=procedure`) only when policy says so.
    """
    control: list[str] = []
    goal = (task.anchor.goal or "").strip()
    if goal:
        control.append(f"goal: {goal}")
    for loop in task.anchor.open_loops or []:
        loop = (loop or "").strip()
        if loop:
            control.append(f"loop: {loop}")

    procs = [
        i for i in items
        if plane_for_kind(i.kind) == MemoryPlane.PROCEDURAL and not i.uncertain
    ]
    procs.sort(key=lambda i: (i.source_turn, i.id), reverse=True)
    if max_procedures > 0:
        procs = procs[:max_procedures]
    skill_texts = [i.text for i in procs]
    skill_ids = [i.id for i in procs]

    diag_texts = control + skill_texts
    l1_texts = list(skill_texts) if skills_only_in_l1 else list(diag_texts)
    return (
        PlaneSlice(
            plane=MemoryPlane.PROCEDURAL,
            texts=diag_texts,
            item_ids=skill_ids,
            count=len(diag_texts),
            meta={
                "control_plane": control,
                "skills": skill_texts,
                "l1_skills_only": skills_only_in_l1,
            },
        ),
        l1_texts,
    )


def _long_term_slice(items: list[MemoryItem], *, max_texts: int = 24) -> PlaneSlice:
    durable = [
        i for i in items
        if plane_for_kind(i.kind) == MemoryPlane.LONG_TERM and not i.uncertain
    ]
    durable.sort(key=lambda i: (i.source_turn, i.id), reverse=True)
    if max_texts > 0:
        durable = durable[:max_texts]
    semantic = [i for i in durable if long_term_kind_for(i.kind) == LongTermKind.SEMANTIC]
    episodic = [i for i in durable if long_term_kind_for(i.kind) == LongTermKind.EPISODIC]
    return PlaneSlice(
        plane=MemoryPlane.LONG_TERM,
        texts=[i.text for i in durable],
        item_ids=[i.id for i in durable],
        count=len(durable),
        meta={
            "semantic": [i.text for i in semantic],
            "episodic": [i.text for i in episodic],
            "semantic_count": len(semantic),
            "episodic_count": len(episodic),
        },
    )


def _index_slice(cards: list[ThreadCard], bound_id: str) -> PlaneSlice:
    texts = [
        f"{c.workstream_id}:{c.title or c.goal}"
        + (" *" if c.workstream_id == bound_id else "")
        for c in cards
    ]
    return PlaneSlice(
        plane=MemoryPlane.INDEX,
        texts=texts,
        item_ids=[c.workstream_id for c in cards],
        count=len(cards),
    )


def _split_relevant_in_l1(
    projected_facts: list[str],
    merged_facts: list[str],
) -> tuple[list[str], list[str]]:
    """Asserted = projected ∩ L1; relevant = L1 − projected (order preserved)."""
    projected_set = {f.strip().lower() for f in projected_facts}
    asserted_in_l1 = [f for f in merged_facts if f.strip().lower() in projected_set]
    relevant_only = [f for f in merged_facts if f.strip().lower() not in projected_set]
    return asserted_in_l1, relevant_only


class MemoryManager:
    """Context-aware memory management over a MemoryPort."""

    def __init__(
        self,
        port: MemoryPort,
        *,
        builder: WorkingContextBuilder | None = None,
        limits: WorkingSetLimits | None = None,
        policy: PlanePolicy = DEFAULT_PLANE_POLICY,
        max_procedures: int = 6,
    ):
        self.port = port
        self.builder = builder or WorkingContextBuilder(limits=limits)
        self.limits = self.builder.limits
        self.policy = policy
        self.max_procedures = max_procedures

    def assemble(
        self,
        *,
        workstream_id: str,
        referent_id: str | None = None,
        selected_loop: str | None = None,
        query: str | None = None,
        enrich_cold: bool | None = None,
        cold_limit: int = 5,
        open_tasks: list[Task] | None = None,
    ) -> ContextAwareMemory | None:
        task = self.port.get_task(workstream_id)
        if task is None:
            return None

        items = self.port.read_asserted(workstream_id)
        cards = self.port.list_open_threads()
        if open_tasks is None:
            open_tasks = []
            for card in cards:
                t = self.port.get_task(card.workstream_id)
                if t is not None:
                    open_tasks.append(t)

        proj = self.builder.project(task, referent_id, _AssertedView(items), open_tasks)
        notation = build_compact_notation(
            task,
            referent_id=referent_id,
            selected_loop=selected_loop,
            projection=proj,
        )

        procedural, l1_procs = _procedural_slice(
            task,
            items,
            max_procedures=self.max_procedures,
            skills_only_in_l1=self.policy.procedural_skills_only_in_l1,
        )
        notation.procedures = list(l1_procs)
        notation.asserted_facts = list(notation.facts)
        notation.relevant_facts = []
        notation.memory_planes = {
            "short_term": "L1",
            "long_term_source": "L2 semantic+episodic",
            "procedural_source": "L2 procedures (+ L4 control on card)",
            "relevant_source": "bound cold L2/L3",
            "archive": "L6/L7 never auto",
        }

        hits: list[ColdHit] = []
        do_enrich = _cold_enrich_enabled() if enrich_cold is None else enrich_cold
        q = (query or "").strip()
        if do_enrich and q and self.policy.relevant_must_be_bound:
            raw_hits = self.port.search_cold(
                q, limit=max(1, cold_limit), workstream_id=workstream_id,
            )
            asserted_slots = {
                (i.slot or "").strip()
                for i in items
                if (i.slot or "").strip() and i.status == "asserted"
            }
            hits = filter_hits_for_l1(
                raw_hits,
                asserted_slots=asserted_slots,
                prefer_asserted_over_superseded=self.policy.prefer_asserted_over_superseded,
            )
            before = list(notation.facts)
            notation.facts = merge_hits_into_facts(
                notation.facts,
                hits,
                max_facts=self.limits.max_facts,
                bound_workstream_id=workstream_id,
            )
            asserted_in_l1, relevant_only = _split_relevant_in_l1(before, notation.facts)
            notation.asserted_facts = asserted_in_l1
            notation.relevant_facts = relevant_only
            # Provenance: projection ids + cold ids that landed in L1
            cold_ids = hit_item_ids(hits, notation.facts)
            seen = set(notation.memory_item_ids)
            for iid in cold_ids:
                if iid not in seen:
                    notation.memory_item_ids.append(iid)
                    seen.add(iid)

        relevant = PlaneSlice(
            plane=MemoryPlane.RELEVANT,
            texts=list(notation.relevant_facts),
            item_ids=hit_item_ids(hits, notation.relevant_facts) if hits else [],
            count=len(notation.relevant_facts),
            meta={
                "hit_count": len(hits),
                "sources": [h.source for h in hits[:8]],
            },
        )

        return ContextAwareMemory(
            workstream_id=workstream_id,
            referent_id=referent_id,
            query=query,
            short_term=notation,
            long_term=_long_term_slice(items),
            procedural=procedural,
            relevant=relevant,
            index=_index_slice(cards, workstream_id),
            diagnostics={
                "l1_item_count": len(notation.memory_item_ids),
                "l2_asserted_count": len(items),
                "l4_open_count": len(cards),
                "relevant_hit_count": len(hits),
                "l1_asserted_fact_count": len(notation.asserted_facts),
                "l1_relevant_fact_count": len(notation.relevant_facts),
                "l1_procedure_count": len(notation.procedures),
                "generate_plane": MemoryPlane.SHORT_TERM.value,
                "policy": asdict(self.policy),
                "design": design_notes(),
            },
        )

    def expose_short_term(self, **kwargs) -> CompactNotation | None:
        """Convenience: SHORT_TERM CompactNotation only (generate surface)."""
        bundle = self.assemble(**kwargs)
        return None if bundle is None else bundle.short_term
