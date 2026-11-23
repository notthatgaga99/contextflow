"""L1 compact notation — the only working-memory view exposed to the answer LLM.

Bind selects a thread; this schema is what may enter generate().
Not a transcript. Not multi-thread top-k. Tier label: L1 (SHORT_TERM plane).

Planes inside L1:
  - asserted_*  from LONG_TERM hop CURRENT (L2) — semantic/episodic kinds
  - relevant_*  from RELEVANT cold enrich (bound L2/L3 only)
  - procedures  from PROCEDURAL how-tos only (`kind=procedure`)
  - goal / selected_loop stay on card fields (control plane, not procedure dump)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.context.working_set import WorkingSetProjection
from app.models.task import Task


@dataclass
class CompactNotation:
    """Stable answer-model contract for one bound avenue (SHORT_TERM / L1)."""

    workstream_id: str
    title: str = ""
    goal: str = ""
    referent_id: str | None = None
    selected_loop: str | None = None
    decisions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)  # merged asserted + relevant
    entities: list[str] = field(default_factory=list)
    procedures: list[str] = field(default_factory=list)
    asserted_facts: list[str] = field(default_factory=list)
    relevant_facts: list[str] = field(default_factory=list)
    recent_changes: list[str] = field(default_factory=list)
    excluded_workstreams: list[str] = field(default_factory=list)
    memory_item_ids: list[str] = field(default_factory=list)
    memory_planes: dict[str, str] = field(default_factory=dict)
    tier: str = "L1"
    plane: str = "short_term"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def compiler_extras(self) -> dict[str, Any]:
        """Fields consumed by ContextCompiler.build(**extra)."""
        return {
            "active_decisions": list(self.decisions),
            "active_constraints": list(self.constraints),
            "relevant_facts": list(self.facts),
            "relevant_entities": list(self.entities),
            "procedures": list(self.procedures),
            "excluded_workstreams": list(self.excluded_workstreams),
            "memory_item_ids": list(self.memory_item_ids),
            "recent_changes": list(self.recent_changes),
        }

    def to_expose_text(self) -> str:
        """Human/LLM-facing compact notation (no sibling hop bodies)."""
        lines = [
            f"THREAD: {self.title or self.workstream_id}",
            f"GOAL: {self.goal or self.title or self.workstream_id}",
            "PLANE: short_term (L1)",
        ]
        if self.referent_id:
            lines.append(f"REFERENT: {self.referent_id}")
        if self.selected_loop:
            lines.append(f"SELECTED LOOP: {self.selected_loop}")
        if self.procedures:
            lines.append("PROCEDURAL: " + "; ".join(self.procedures))
        if self.decisions:
            lines.append("DECISIONS: " + "; ".join(self.decisions))
        if self.constraints:
            lines.append("CONSTRAINTS: " + "; ".join(self.constraints))
        # Prefer split labels when relevant enrich happened; else plain FACTS.
        if self.relevant_facts or self.asserted_facts:
            if self.asserted_facts:
                lines.append("LONG_TERM: " + "; ".join(self.asserted_facts))
            if self.relevant_facts:
                lines.append("RELEVANT: " + "; ".join(self.relevant_facts))
        elif self.facts:
            lines.append("FACTS: " + "; ".join(self.facts))
        if self.entities:
            lines.append("ENTITIES: " + "; ".join(self.entities))
        if self.recent_changes:
            lines.append("RECENT: " + "; ".join(self.recent_changes))
        return "\n".join(lines)


def build_compact_notation(
    task: Task,
    *,
    referent_id: str | None,
    selected_loop: str | None,
    projection: WorkingSetProjection,
) -> CompactNotation:
    facts = list(projection.facts)
    # How-tos only — goal/loops already exposed as GOAL / SELECTED LOOP.
    procedures = list(getattr(projection, "procedures", []) or [])
    return CompactNotation(
        workstream_id=task.id,
        title=task.title or task.id,
        goal=(task.anchor.goal or task.title or task.id),
        referent_id=referent_id,
        selected_loop=selected_loop,
        decisions=list(projection.decisions),
        constraints=list(projection.constraints),
        facts=facts,
        entities=list(projection.entities),
        procedures=procedures,
        asserted_facts=list(facts),
        relevant_facts=[],
        recent_changes=list(projection.recent_changes),
        excluded_workstreams=list(projection.excluded_workstreams),
        memory_item_ids=list(projection.item_ids),
        memory_planes={
            "short_term": "L1",
            "long_term_source": "L2",
            "procedural_source": "L2+L4",
        },
        tier="L1",
        plane="short_term",
    )
