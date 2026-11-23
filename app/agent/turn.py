"""Agent turn: bind_and_expose + optional auto tools (tools never re-bind)."""

from __future__ import annotations

from typing import Any

from app.agent.tools import invoke_tool
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
    """Run one agentic turn. Binder stays authority; tools enrich the shell UI.

    On CLARIFY (``interrupt=True``) the shell must pause — no generate from L1,
    and bound search tools are skipped.
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
    # Host contract overlays (interrupt clears answer/L1 for clarify).
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

    timeline = list(out.get("timeline") or bound.timeline)
    tool_runs: list[dict[str, Any]] = []
    if auto_tools and not bound.interrupt:
        health = invoke_tool(
            store, "session_health", {"conversation_id": conversation_id},
        )
        tool_runs.append(health.to_dict())
        timeline.append({
            "step": "tool",
            "detail": "session_health",
            "ok": health.ok,
        })
        if bound.task_id:
            searched = invoke_tool(store, "search_bound", {
                "conversation_id": conversation_id,
                "workstream_id": bound.task_id,
                "query": message,
                "limit": 3,
            })
            tool_runs.append(searched.to_dict())
            timeline.append({
                "step": "tool",
                "detail": "search_bound",
                "ok": searched.ok,
                "n_hits": len((searched.data or {}).get("hits") or []),
            })
    elif bound.interrupt:
        timeline.append({
            "step": "interrupt",
            "detail": "clarify — host must pause",
        })

    out["timeline"] = timeline
    out["tools"] = tool_runs
    return out
