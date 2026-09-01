"""HTTP turn: extract then frozen ContextFlow. Extractor does not select working context."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain import Transition
from app.engine import Engine, TurnResult
from app.memory.extractor import ExtractRequest, MemoryExtractor, apply_extraction
from app.memory.writer import MemoryWriter, WriterResult


@dataclass
class PipelineResult:
    extract: WriterResult
    turn: TurnResult
    extract_passes: int = 1


def _extract_request(
    engine: Engine,
    writer: MemoryWriter,
    *,
    conversation_id: str,
    message: str,
    turn: int,
    history: list[dict] | None,
    focus_workstream_id: str | None = None,
) -> ExtractRequest:
    store = writer.store
    return ExtractRequest(
        message=message,
        source_turn=turn,
        conversation_id=conversation_id,
        history=list(history or []),
        open_workstreams=engine.reg.open_tasks(),
        asserted_items=store.asserted() if hasattr(store, "asserted") else [],
        focus_workstream_id=focus_workstream_id,
    )


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
    """turn N → route-aware extract → ContextFlow. Safe to retry.

    Non-NEW turns: extract → route → answer (unchanged semantics).
    NEW turns: plan → create card → bounded extract → answer already generated.
    """
    plan = engine.plan_turn(message, turn)
    passes = 0

    if plan.transition == Transition.NEW:
        routed = engine.execute_plan(plan, message, turn)
        req = _extract_request(
            engine, writer,
            conversation_id=conversation_id,
            message=message,
            turn=turn,
            history=history,
            focus_workstream_id=routed.task_id,
        )
        extracted = apply_extraction(extractor, writer, req)
        passes = 1
        return PipelineResult(extract=extracted, turn=routed, extract_passes=passes)

    req = _extract_request(
        engine, writer,
        conversation_id=conversation_id,
        message=message,
        turn=turn,
        history=history,
    )
    extracted = apply_extraction(extractor, writer, req)
    passes = 1
    routed = engine.execute_plan(plan, message, turn)
    return PipelineResult(extract=extracted, turn=routed, extract_passes=passes)
