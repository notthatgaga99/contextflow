"""Working-memory switch: after bind, load one avenue's SHORT_TERM (L1).

  bind (frozen ContextFlow)
    → MemoryManager.assemble (LONG_TERM + PROCEDURAL + RELEVANT → SHORT_TERM)
    → CompactNotation

generate() may only be fed L1 / short_term (+ user message).
"""

from __future__ import annotations

from app.context.compact_notation import CompactNotation
from app.context.working_set import WorkingContextBuilder, WorkingSetLimits
from app.memory.manager import ContextAwareMemory, MemoryManager
from app.memory.port import MemoryPort
from app.models.task import Task


def assemble_bound_memory(
    port: MemoryPort,
    *,
    workstream_id: str,
    referent_id: str | None = None,
    selected_loop: str | None = None,
    builder: WorkingContextBuilder | None = None,
    open_tasks: list[Task] | None = None,
    limits: WorkingSetLimits | None = None,
    query: str | None = None,
    enrich_cold: bool | None = None,
    cold_limit: int = 5,
) -> ContextAwareMemory | None:
    """Full context-aware plane bundle for the bound hop."""
    mgr = MemoryManager(port, builder=builder, limits=limits)
    return mgr.assemble(
        workstream_id=workstream_id,
        referent_id=referent_id,
        selected_loop=selected_loop,
        query=query,
        enrich_cold=enrich_cold,
        cold_limit=cold_limit,
        open_tasks=open_tasks,
    )


def expose_bound_thread(
    port: MemoryPort,
    *,
    workstream_id: str,
    referent_id: str | None = None,
    selected_loop: str | None = None,
    builder: WorkingContextBuilder | None = None,
    open_tasks: list[Task] | None = None,
    limits: WorkingSetLimits | None = None,
    query: str | None = None,
    enrich_cold: bool | None = None,
    cold_limit: int = 5,
) -> CompactNotation | None:
    """Resolve-then-read (+ optional bound-scoped cold enrich) → SHORT_TERM L1."""
    bundle = assemble_bound_memory(
        port,
        workstream_id=workstream_id,
        referent_id=referent_id,
        selected_loop=selected_loop,
        builder=builder,
        open_tasks=open_tasks,
        limits=limits,
        query=query,
        enrich_cold=enrich_cold,
        cold_limit=cold_limit,
    )
    return None if bundle is None else bundle.short_term
