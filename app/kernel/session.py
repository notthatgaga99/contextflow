"""Single E2E turn path: extract → bind → planes → L1 → answer.

HTTP /turn and /agent/turn must call run_kernel_turn. Agent tools may run
afterward but must not re-bind or replace L1 assembly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.context.working_memory_switch import assemble_bound_memory
from app.engine import Engine, TurnResult
from app.memory.extractor import MemoryExtractor
from app.memory.writer import MemoryWriter, WriterResult
from app.turn_pipeline import PipelineResult, run_turn


@dataclass
class KernelResult:
    """Full ContextFlow turn outcome — one hop, L1 diagnostics included."""

    conversation_id: str
    turn: int
    pipeline: PipelineResult
    expose_text: str | None = None
    planes: dict[str, Any] | None = None
    workstream_title: str | None = None
    selected_loop: str | None = None
    timeline: list[dict[str, Any]] = field(default_factory=list)

    @property
    def result(self) -> TurnResult:
        return self.pipeline.turn

    @property
    def extract(self) -> WriterResult:
        return self.pipeline.extract

    def to_agent_dict(self) -> dict[str, Any]:
        r = self.result
        return {
            "conversation_id": self.conversation_id,
            "turn": self.turn,
            "transition": r.transition.value,
            "task_id": r.task_id,
            "workstream_title": self.workstream_title,
            "selected_loop": self.selected_loop,
            "predicted_referent_id": r.predicted_referent_id,
            "answer": r.answer,
            "clarify_question": r.clarify_question,
            "discrimination": (r.resolution_evidence or {}).get("discrimination"),
            "extract_ok": self.extract.ok,
            "extract_committed": bool(self.extract.items) or bool(
                self.extract.idempotent_retry
            ),
            "expose_text": self.expose_text,
            "planes": self.planes,
            "timeline": list(self.timeline),
            "context_mode": r.package.context_mode if r.package else None,
            "total_context_tokens": (
                r.package.total_context_tokens if r.package else None
            ),
        }


def _bound_loop(engine: Engine, task_id: str | None) -> str | None:
    if not task_id:
        return None
    task = engine.reg.get(task_id)
    if task and task.anchor.open_loops:
        return task.anchor.open_loops[0]
    return None


def _title_for(engine: Engine, task_id: str | None) -> str | None:
    if not task_id:
        return None
    task = engine.reg.get(task_id)
    return task.title if task else None


def _assemble_planes(
    engine: Engine,
    *,
    task_id: str,
    referent_id: str | None,
    selected_loop: str | None,
    message: str,
) -> tuple[str | None, dict[str, Any] | None]:
    if engine.memory_port is None:
        return None, None
    bundle = assemble_bound_memory(
        engine.memory_port,
        workstream_id=task_id,
        referent_id=referent_id,
        selected_loop=selected_loop,
        builder=engine.working_context_builder,
        open_tasks=engine.reg.open_tasks(),
        query=message,
    )
    if not bundle or not bundle.short_term:
        return None, None
    expose = bundle.short_term.to_expose_text()
    planes = {
        "short_term": bundle.short_term.to_dict(),
        "long_term": bundle.long_term.to_dict(),
        "procedural": bundle.procedural.to_dict(),
        "relevant": bundle.relevant.to_dict(),
        "index": bundle.index.to_dict(),
        "diagnostics": bundle.diagnostics,
    }
    return expose, planes


def run_kernel_turn(
    engine: Engine,
    writer: MemoryWriter,
    extractor: MemoryExtractor,
    *,
    conversation_id: str,
    message: str,
    turn: int,
    history: list[dict] | None = None,
) -> KernelResult:
    """Canonical E2E turn. Binder stays authority; L1 assembled once after bind."""
    timeline: list[dict[str, Any]] = [
        {"step": "receive", "detail": f"turn {turn}"},
    ]
    pipe = run_turn(
        engine,
        writer,
        extractor,
        conversation_id=conversation_id,
        message=message,
        turn=turn,
        history=history,
    )
    r = pipe.turn
    timeline.append({
        "step": "bind",
        "detail": f"{r.transition.value} → {r.task_id or 'none'}",
        "transition": r.transition.value,
        "task_id": r.task_id,
        "referent_id": r.predicted_referent_id,
    })
    timeline.append({
        "step": "extract",
        "detail": "ok" if pipe.extract.ok else "rejected",
        "committed": bool(pipe.extract.items) or bool(pipe.extract.idempotent_retry),
    })

    loop = _bound_loop(engine, r.task_id)
    title = _title_for(engine, r.task_id)
    # Prefer the exact L1 snapshot generate consumed.
    expose_text = r.l1_expose
    planes = None
    if r.task_id:
        assembled_expose, planes = _assemble_planes(
            engine,
            task_id=r.task_id,
            referent_id=r.predicted_referent_id,
            selected_loop=loop,
            message=message,
        )
        if expose_text is None:
            expose_text = assembled_expose
        if planes and planes.get("short_term"):
            st = planes["short_term"]
            timeline.append({
                "step": "short_term",
                "detail": (
                    f"L1 items={len(st.get('memory_item_ids') or [])} "
                    f"relevant={len(st.get('relevant_facts') or [])}"
                    + (" snapshot=generate" if r.l1_expose else "")
                ),
            })

    timeline.append({
        "step": "answer",
        "detail": (
            "clarify" if r.clarify_question
            else ("ok" if r.answer else "none")
        ),
    })

    return KernelResult(
        conversation_id=conversation_id,
        turn=turn,
        pipeline=pipe,
        expose_text=expose_text,
        planes=planes,
        workstream_title=title,
        selected_loop=loop,
        timeline=timeline,
    )
