"""Tool harness for the ContextFlow agent shell.

Tools read/write through Engine + MemoryPort/Writer. They never replace the
frozen binder (gate/referent/scorer). Useful for an IDE-like agent workspace:
inspect planes, bind-aware recall, assert procedures, list open threads.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from app.context.working_memory_switch import assemble_bound_memory
from app.kernel.writes import assert_bound, assert_bound_dict
from app.memory.planes import design_notes, plane_catalog


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    category: str = "memory"  # memory | session | write


@dataclass
class ToolResult:
    ok: bool
    tool: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _eng(store, conversation_id: str):
    try:
        return store.engine(conversation_id)
    except ValueError as exc:
        raise KeyError(str(exc)) from exc


def tool_list_threads(store, *, conversation_id: str, **_kwargs) -> dict[str, Any]:
    eng = _eng(store, conversation_id)
    threads = []
    for t in eng.reg.open_tasks():
        threads.append({
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "goal": t.anchor.goal,
            "open_loops": list(t.anchor.open_loops or []),
            "last_active_turn": t.last_active_turn,
        })
    active = eng.reg.active()
    return {
        "threads": threads,
        "active_id": active.id if active else None,
        "n_open": len(threads),
    }


def tool_memory_planes(store, *, conversation_id: str, **_kwargs) -> dict[str, Any]:
    return {
        "planes": plane_catalog(),
        "design": design_notes(),
        "conversation_id": conversation_id,
    }


def tool_assemble_short_term(
    store,
    *,
    conversation_id: str,
    workstream_id: str,
    query: str | None = None,
    referent_id: str | None = None,
    **_kwargs,
) -> dict[str, Any]:
    eng = _eng(store, conversation_id)
    if eng.memory_port is None:
        raise RuntimeError("memory_port_unavailable")
    task = eng.reg.get(workstream_id)
    if task is None:
        raise KeyError(f"unknown workstream {workstream_id}")
    ref = referent_id or (f"{workstream_id}.loop1" if task.anchor.open_loops else workstream_id)
    loop = task.anchor.open_loops[0] if task.anchor.open_loops else None
    bundle = assemble_bound_memory(
        eng.memory_port,
        workstream_id=workstream_id,
        referent_id=ref,
        selected_loop=loop,
        builder=eng.working_context_builder,
        open_tasks=eng.reg.open_tasks(),
        query=query,
    )
    if bundle is None:
        raise RuntimeError("assemble_failed")
    return {
        "expose_text": bundle.short_term.to_expose_text() if bundle.short_term else "",
        "short_term": bundle.short_term.to_dict() if bundle.short_term else None,
        "planes": {
            "long_term": bundle.long_term.to_dict(),
            "procedural": bundle.procedural.to_dict(),
            "relevant": bundle.relevant.to_dict(),
            "index": bundle.index.to_dict(),
        },
        "diagnostics": bundle.diagnostics,
    }


def tool_search_bound(
    store,
    *,
    conversation_id: str,
    workstream_id: str,
    query: str,
    limit: int = 5,
    **_kwargs,
) -> dict[str, Any]:
    eng = _eng(store, conversation_id)
    if eng.memory_port is None:
        raise RuntimeError("memory_port_unavailable")
    hits = eng.memory_port.search_cold(
        query, limit=max(1, min(20, int(limit))), workstream_id=workstream_id,
    )
    return {
        "workstream_id": workstream_id,
        "query": query,
        "hits": [
            {
                "text": h.text,
                "score": h.score,
                "status": h.status,
                "kind": h.kind,
                "item_id": h.item_id,
                "source": h.source,
            }
            for h in hits
        ],
    }


def tool_assert_procedure(
    store,
    *,
    conversation_id: str,
    workstream_id: str,
    text: str,
    turn: int = 0,
    **_kwargs,
) -> dict[str, Any]:
    """Write a how-to into PROCEDURAL plane (kernel bound-write → Writer)."""
    eng = _eng(store, conversation_id)
    writer = store.writer(conversation_id)
    src = int(turn) if turn else max(1, getattr(eng, "turn", 1) or 1)
    result = assert_bound(
        writer,
        eng.reg,
        conversation_id=conversation_id,
        workstream_id=workstream_id,
        kind="procedure",
        text=text,
        turn=src,
        provenance="agent_tool:assert_procedure",
    )
    if not result.ok and any("unknown_workstream" in e for e in result.errors):
        raise KeyError(f"unknown workstream {workstream_id}")
    if not result.ok and any("empty_text" in e for e in result.errors):
        raise ValueError("empty procedure text")
    return assert_bound_dict(result, workstream_id=workstream_id, plane="procedural")


def tool_session_health(store, *, conversation_id: str, **_kwargs) -> dict[str, Any]:
    eng = _eng(store, conversation_id)
    mem = store.memory_store(conversation_id)
    n_items = len(list(mem.all())) if hasattr(mem, "all") else None
    return {
        "conversation_id": conversation_id,
        "n_open_threads": len(eng.reg.open_tasks()),
        "n_memory_items": n_items,
        "active_id": eng.reg.active().id if eng.reg.active() else None,
        "has_memory_port": eng.memory_port is not None,
    }


TOOL_REGISTRY: dict[str, tuple[ToolSpec, Callable[..., dict[str, Any]]]] = {}


def _reg(spec: ToolSpec, fn: Callable[..., dict[str, Any]]) -> None:
    TOOL_REGISTRY[spec.name] = (spec, fn)


_reg(
    ToolSpec(
        name="list_threads",
        description="List open workstream cards (INDEX plane) for this conversation.",
        category="session",
        parameters={
            "type": "object",
            "properties": {"conversation_id": {"type": "string"}},
            "required": ["conversation_id"],
        },
    ),
    tool_list_threads,
)
_reg(
    ToolSpec(
        name="memory_planes",
        description="Describe ContextFlow memory planes and design stance (RB-WSR).",
        category="memory",
        parameters={
            "type": "object",
            "properties": {"conversation_id": {"type": "string"}},
            "required": ["conversation_id"],
        },
    ),
    tool_memory_planes,
)
_reg(
    ToolSpec(
        name="assemble_short_term",
        description=(
            "Bind a workstream and assemble SHORT_TERM (L1) plus plane diagnostics. "
            "Optional query enables bound RELEVANT cold enrich."
        ),
        category="memory",
        parameters={
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string"},
                "workstream_id": {"type": "string"},
                "query": {"type": "string"},
                "referent_id": {"type": "string"},
            },
            "required": ["conversation_id", "workstream_id"],
        },
    ),
    tool_assemble_short_term,
)
_reg(
    ToolSpec(
        name="search_bound",
        description="Cold recall ranked over one bound workstream only (never multi-thread top-k).",
        category="memory",
        parameters={
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string"},
                "workstream_id": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["conversation_id", "workstream_id", "query"],
        },
    ),
    tool_search_bound,
)
_reg(
    ToolSpec(
        name="assert_procedure",
        description="Commit a how-to step into the PROCEDURAL plane via MemoryWriter.",
        category="write",
        parameters={
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string"},
                "workstream_id": {"type": "string"},
                "text": {"type": "string"},
                "turn": {"type": "integer"},
            },
            "required": ["conversation_id", "workstream_id", "text"],
        },
    ),
    tool_assert_procedure,
)
_reg(
    ToolSpec(
        name="session_health",
        description="Quick session diagnostics: open threads, item counts, active bind.",
        category="session",
        parameters={
            "type": "object",
            "properties": {"conversation_id": {"type": "string"}},
            "required": ["conversation_id"],
        },
    ),
    tool_session_health,
)


def list_tools() -> list[dict[str, Any]]:
    out = []
    for name, (spec, _) in sorted(TOOL_REGISTRY.items()):
        out.append({
            "name": spec.name,
            "description": spec.description,
            "category": spec.category,
            "parameters": spec.parameters,
        })
    return out


def invoke_tool(
    store,
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    bound_workstream_id: str | None = None,
) -> ToolResult:
    """Invoke a registered tool.

    When ``bound_workstream_id`` is set, a mismatched ``workstream_id`` argument
    fails closed (tools never retarget another hop).
    """
    entry = TOOL_REGISTRY.get(name)
    if entry is None:
        return ToolResult(ok=False, tool=name, error=f"unknown_tool:{name}")
    spec, fn = entry
    args = dict(arguments or {})
    if bound_workstream_id:
        from app.agent.tool_loop import reject_unbound_workstream

        gated = reject_unbound_workstream(
            args, bound_workstream_id=bound_workstream_id,
        )
        if gated is not None:
            gated.tool = spec.name
            return gated
        # Stamp bound id for write/search tools that require it.
        if "workstream_id" in (spec.parameters.get("properties") or {}):
            args["workstream_id"] = bound_workstream_id
    try:
        data = fn(store, **args)
        return ToolResult(ok=True, tool=spec.name, data=data)
    except TypeError as exc:
        return ToolResult(ok=False, tool=spec.name, error=f"bad_args:{exc}")
    except Exception as exc:
        return ToolResult(ok=False, tool=spec.name, error=str(exc))
