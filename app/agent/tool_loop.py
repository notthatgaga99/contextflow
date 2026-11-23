"""Thin post-bind tool loop — fail-closed, never re-binds, never stuffs L1.

Law:
  bind_and_expose first → tools only on ACT-family with task_id → optional
  Writer patches on the bound hop → answer L1 stays the pre-tool expose.
"""

from __future__ import annotations

import os
from typing import Any

from app.agent.tools import ToolResult, invoke_tool
from app.kernel.writes import assert_bound

# Transitions that may run bound tools (CLARIFY / missing task → skip).
_ACT_FAMILY = frozenset({"CONTINUE", "SWITCH", "RETURN", "NEW"})


def tool_loop_commit_enabled() -> bool:
    return (os.getenv("CF_TOOL_LOOP_COMMIT", "1") or "1").strip() != "0"


def patches_from_search_hits(
    hits: list[dict[str, Any]],
    *,
    workstream_id: str,
    limit: int = 1,
) -> list[dict[str, Any]]:
    """Map cold-search hits to bound patch specs (fact). Empty if nothing useful."""
    out: list[dict[str, Any]] = []
    want = max(1, limit)
    for hit in hits:
        if len(out) >= want:
            break
        text = str(hit.get("text") or "").strip()
        if len(text) < 3:
            continue
        # Skip superseded / historical for auto-commit.
        if str(hit.get("status") or "").lower() == "superseded":
            continue
        out.append({
            "kind": "fact",
            "text": text[:240],
            "workstream_id": workstream_id,
            "slot": None,
            "provenance": "tool_loop:search_bound",
        })
    return out


def run_bound_tool_loop(
    store,
    *,
    conversation_id: str,
    message: str,
    turn: int,
    task_id: str | None,
    transition: str | None,
    l1_expose: str | None,
) -> dict[str, Any]:
    """Run one bound search (+ optional commit). Does not call the binder."""
    timeline: list[dict[str, Any]] = []
    tool_runs: list[dict[str, Any]] = []
    patches_committed: list[dict[str, Any]] = []
    l1_before = l1_expose

    tid = (task_id or "").strip() or None
    trans = (transition or "").strip().upper()
    if not tid or trans not in _ACT_FAMILY:
        return {
            "tools": tool_runs,
            "timeline": timeline,
            "patches_committed": patches_committed,
            "l1_expose": l1_before,
            "l1_unchanged": True,
            "skipped": True,
            "skip_reason": "clarify_or_unbound",
        }

    searched = invoke_tool(
        store,
        "search_bound",
        {
            "conversation_id": conversation_id,
            "workstream_id": tid,
            "query": message,
            "limit": 3,
        },
        bound_workstream_id=tid,
    )
    tool_runs.append(searched.to_dict())
    timeline.append({
        "step": "tool",
        "detail": "search_bound",
        "ok": searched.ok,
        "n_hits": len((searched.data or {}).get("hits") or []),
    })

    if (
        tool_loop_commit_enabled()
        and searched.ok
        and isinstance(searched.data, dict)
    ):
        specs = patches_from_search_hits(
            list(searched.data.get("hits") or []),
            workstream_id=tid,
        )
        if specs:
            eng = store.engine(conversation_id)
            writer = store.writer(conversation_id)
            for spec in specs:
                result = assert_bound(
                    writer,
                    eng.reg,
                    conversation_id=conversation_id,
                    workstream_id=tid,
                    kind=spec["kind"],
                    text=spec["text"],
                    turn=max(1, int(turn)),
                    slot=spec.get("slot"),
                    provenance=spec.get("provenance") or "tool_loop",
                )
                if result.ok:
                    patches_committed.extend(
                        [i.to_dict() for i in result.items]
                    )
                    timeline.append({
                        "step": "tool_commit",
                        "detail": "search_bound→fact",
                        "ok": True,
                        "n": len(result.items),
                    })
                else:
                    timeline.append({
                        "step": "tool_commit",
                        "detail": "search_bound→fact",
                        "ok": False,
                        "errors": list(result.errors or [])[:4],
                    })

    return {
        "tools": tool_runs,
        "timeline": timeline,
        "patches_committed": patches_committed,
        "l1_expose": l1_before,
        "l1_unchanged": True,
        "skipped": False,
        "skip_reason": None,
    }


def reject_unbound_workstream(
    args: dict[str, Any],
    *,
    bound_workstream_id: str | None,
) -> ToolResult | None:
    """If a bound stamp is set, forged workstream_id fails closed."""
    if not bound_workstream_id:
        return None
    wid = str(args.get("workstream_id") or "").strip()
    if wid and wid != bound_workstream_id:
        return ToolResult(
            ok=False,
            tool="(gate)",
            error=f"workstream_not_bound:{wid}",
        )
    return None
