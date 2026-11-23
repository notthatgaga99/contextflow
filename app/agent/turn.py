"""Agent turn: bind_and_expose first; thin tool loop after ACT only.

Tools never re-bind, never replace L1 for this turn, never soften Select.
"""

from __future__ import annotations

from typing import Any

from app.agent.tool_loop import run_bound_tool_loop
from app.kernel.bind_api import bind_and_expose


def run_agent_turn(
    store,
    extractor,
    *,
    conversation_id: str,
    message: str,
    turn: int,
    auto_tools: bool = True,
) -> dict[str, Any]:
    """One agentic turn. Binder stays authority.

    Order (honest): bind → extract/L1/answer → optional bound tools →
    optional Writer patches for *next* turn. CLARIFY interrupts with no tools.
    """
    bound = bind_and_expose(
        store,
        extractor,
        conversation_id=conversation_id,
        message=message,
        turn=turn,
    )
    kernel = bound.kernel
    if kernel is not None:
        out = kernel.to_agent_dict()
    else:
        out = {
            "conversation_id": bound.conversation_id,
            "turn": bound.turn,
            "transition": bound.transition,
            "task_id": bound.task_id,
            "answer": bound.answer,
            "clarify_question": bound.clarify_question,
            "expose_text": bound.l1_expose,
            "timeline": list(bound.timeline),
        }
    out["interrupt"] = bound.interrupt
    out["l1_expose"] = bound.l1_expose
    out["discrimination"] = bound.discrimination
    out["latency_ms"] = bound.latency_ms
    out["llm_mode"] = bound.llm_mode
    if bound.interrupt:
        out["answer"] = None
        out["task_id"] = None
        out["clarify_question"] = bound.clarify_question
        out["expose_text"] = None
        out["l1_expose"] = None

    # Freeze L1 snapshot before any tool work (same-turn expose must not change).
    l1_snapshot = out.get("l1_expose")
    timeline = list(out.get("timeline") or bound.timeline)
    tool_runs: list[dict[str, Any]] = []
    patches_committed: list[dict[str, Any]] = []

    if bound.interrupt:
        timeline.append({
            "step": "interrupt",
            "detail": "clarify — host must pause; tools skipped",
        })
    elif auto_tools:
        loop = run_bound_tool_loop(
            store,
            conversation_id=conversation_id,
            message=message,
            turn=turn,
            task_id=bound.task_id,
            transition=bound.transition,
            l1_expose=l1_snapshot,
        )
        tool_runs = list(loop.get("tools") or [])
        patches_committed = list(loop.get("patches_committed") or [])
        timeline.extend(list(loop.get("timeline") or []))
        # Law: tools must not rewrite this turn's L1 expose.
        out["l1_expose"] = l1_snapshot
        out["expose_text"] = l1_snapshot
        out["tool_loop"] = {
            "skipped": bool(loop.get("skipped")),
            "skip_reason": loop.get("skip_reason"),
            "l1_unchanged": bool(loop.get("l1_unchanged")),
            "n_patches": len(patches_committed),
        }

    out["timeline"] = timeline
    out["tools"] = tool_runs
    out["patches_committed"] = patches_committed
    return out
