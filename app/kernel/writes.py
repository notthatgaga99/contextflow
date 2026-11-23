"""Bound-hop memory writes — one Writer door for tools and future kernel hooks.

Never writes from generate(). Caller supplies the bound workstream_id; this
module does not re-bind.
"""

from __future__ import annotations

from typing import Any

from app.memory.writer import MemoryWriter, WriterResult
from app.models.memory import MemoryPatch

# Kinds allowed on the bound write path (switch control, not memory CRM).
BOUND_WRITE_KINDS = frozenset({
    "procedure",
    "preference",
    "correction",
    "decision",
    "constraint",
    "fact",
})


def assert_bound(
    writer: MemoryWriter,
    registry,
    *,
    conversation_id: str,
    workstream_id: str,
    kind: str,
    text: str,
    turn: int,
    slot: str | None = None,
    referent_id: str | None = None,
    provenance: str = "kernel:assert_bound",
) -> WriterResult:
    """Commit one item on an existing workstream via MemoryWriter."""
    wid = (workstream_id or "").strip()
    if not wid:
        return WriterResult(ok=False, errors=["workstream_id_required"])
    if registry.get(wid) is None:
        return WriterResult(ok=False, errors=[f"unknown_workstream:{wid}"])
    k = (kind or "").strip().lower()
    if k not in BOUND_WRITE_KINDS:
        return WriterResult(ok=False, errors=[f"unsupported_bound_kind:{kind}"])
    body = (text or "").strip()
    if not body:
        return WriterResult(ok=False, errors=["empty_text"])
    src = max(1, int(turn))
    patch = MemoryPatch(
        kind=k,
        text=body,
        source_turn=src,
        workstream_id=wid,
        referent_id=referent_id,
        slot=slot,
        conversation_id=conversation_id,
        proposer="system",
        provenance=provenance,
    )
    return writer.commit([patch], turn=src)


def assert_bound_dict(result: WriterResult, *, workstream_id: str, plane: str) -> dict[str, Any]:
    if not result.ok:
        raise RuntimeError("; ".join(result.errors) or "commit_failed")
    return {
        "committed": [i.to_dict() for i in result.items],
        "workstream_id": workstream_id,
        "plane": plane,
    }
