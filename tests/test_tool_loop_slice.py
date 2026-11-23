"""Thin tool-loop laws: bind first, ACT-only, bound wid, L1 unchanged this turn."""

from __future__ import annotations

import pytest

from app.agent.tool_loop import patches_from_search_hits, run_bound_tool_loop
from app.agent.tools import invoke_tool
from app.agent.turn import run_agent_turn
from app.domain import Transition
from app.llm.mock import MockLLM
from app.memory.extractor import MockMemoryExtractor
from app.memory.sessions import ConversationStore
from app.models.memory import MemoryPatch
from tests.conftest import make_task

pytestmark = pytest.mark.integration


def _seed_auth_outfit(store: ConversationStore, cid: str) -> None:
    eng = store.engine(cid)
    eng.reg.add(make_task(
        "A", "JWT auth", "fix JWT", ["401 after refresh"], ["jwt", "auth", "ttl"],
    ))
    eng.reg.add(make_task(
        "B", "orders", "checkout 401", ["checkout"], ["orders", "cart", "401"],
    ))
    store.writer(cid).commit([
        MemoryPatch(kind="fact", text="refresh fails TTL 15", source_turn=1, workstream_id="A", slot="ttl"),
        MemoryPatch(kind="fact", text="checkout 401", source_turn=1, workstream_id="B"),
    ], turn=1)
    eng.reg.mark_active("A", 1)


def test_clarify_skips_tools_and_patches():
    store = ConversationStore(MockLLM({
        "401": {"task_id": "A", "is_new_task": False, "confidence": 0.9},
        "still": {"task_id": "A", "is_new_task": False, "confidence": 0.9},
    }))
    cid = "tl-clar"
    _seed_auth_outfit(store, cid)
    out = run_agent_turn(
        store, MockMemoryExtractor(),
        conversation_id=cid,
        message="still getting 401",
        turn=2,
        auto_tools=True,
    )
    assert out["interrupt"] is True
    assert out["transition"] == Transition.CLARIFY.value or out["transition"] == "CLARIFY"
    assert out.get("tools") == []
    assert out.get("patches_committed") == []
    assert out.get("l1_expose") is None


def test_forged_workstream_rejected_when_bound_stamp_set():
    store = ConversationStore(MockLLM())
    cid = "tl-forge"
    _seed_auth_outfit(store, cid)
    bad = invoke_tool(
        store,
        "search_bound",
        {
            "conversation_id": cid,
            "workstream_id": "B",
            "query": "TTL",
            "limit": 3,
        },
        bound_workstream_id="A",
    )
    assert bad.ok is False
    assert "workstream_not_bound" in (bad.error or "")


def test_act_search_commits_bound_fact_l1_unchanged(monkeypatch):
    monkeypatch.setenv("CF_TOOL_LOOP_COMMIT", "1")
    store = ConversationStore(MockLLM({
        "TTL": {"task_id": "A", "is_new_task": False, "confidence": 0.95},
        "refresh": {"task_id": "A", "is_new_task": False, "confidence": 0.95},
    }))
    cid = "tl-act"
    _seed_auth_outfit(store, cid)
    before_n = len(store.memory_store(cid).asserted("A"))
    out = run_agent_turn(
        store, MockMemoryExtractor(),
        conversation_id=cid,
        message="JWT refresh TTL still wrong on auth",
        turn=2,
        auto_tools=True,
    )
    assert out.get("interrupt") is not True
    assert out.get("task_id") == "A"
    assert out.get("tools")
    assert out["tools"][0]["tool"] == "search_bound"
    assert out["tools"][0]["ok"] is True
    # L1 from bind must not be rewritten by tool cards.
    assert out.get("tool_loop", {}).get("l1_unchanged") is True
    l1 = out.get("l1_expose") or ""
    assert "tool_loop" not in l1.lower()
    # Patches land on A only (next-turn memory), not B.
    after = store.memory_store(cid).asserted("A")
    assert len(after) >= before_n
    assert not any(
        (i.provenance or "").startswith("tool_loop")
        for i in store.memory_store(cid).asserted("B")
    )


def test_patches_from_search_hits_skips_superseded():
    specs = patches_from_search_hits(
        [
            {"text": "old", "status": "superseded", "score": 0.9},
            {"text": "fresh TTL 5", "status": "asserted", "score": 0.8},
        ],
        workstream_id="A",
    )
    assert len(specs) == 1
    assert specs[0]["text"] == "fresh TTL 5"
    assert specs[0]["workstream_id"] == "A"


def test_unbound_loop_skips():
    store = ConversationStore(MockLLM())
    loop = run_bound_tool_loop(
        store,
        conversation_id="x",
        message="hi",
        turn=1,
        task_id=None,
        transition="CLARIFY",
        l1_expose=None,
    )
    assert loop["skipped"] is True
    assert loop["tools"] == []
