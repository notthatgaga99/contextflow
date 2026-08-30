"""HTTP turn: extract then frozen ContextFlow. Extractor does not select working context."""

from __future__ import annotations

from dataclasses import dataclass

from app.engine import Engine, TurnResult
from app.memory.extractor import ExtractRequest, MemoryExtractor, apply_extraction
from app.memory.writer import MemoryWriter, WriterResult


@dataclass
class PipelineResult:
    extract: WriterResult
    turn: TurnResult


def run_turn(
    engine: Engine,
    writer: MemoryWriter,
    extractor: MemoryExtractor,
    *,
    conversation_id: str,
    message: str,
    turn: int,
    history: list[dict] | None = None,
) -> PipelineResult:
    """turn N → extract → validate → commit → ContextFlow. Safe to retry.

    The extractor only proposes MemoryPatches. Working-context selection is
    exclusively Engine.handle_turn (resolver + gate).
    """
    store = writer.store
    req = ExtractRequest(
        message=message,
        source_turn=turn,
        conversation_id=conversation_id,
        history=list(history or []),
        open_workstreams=engine.reg.open_tasks(),
        asserted_items=store.asserted() if hasattr(store, "asserted") else [],
    )
    extracted = apply_extraction(extractor, writer, req)
    routed = engine.handle_turn(message, turn)
    return PipelineResult(extract=extracted, turn=routed)
