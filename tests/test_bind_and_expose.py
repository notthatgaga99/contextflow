"""Trust: bind_and_expose host contract — ACT L1, CLARIFY interrupt, no re-bind."""

from __future__ import annotations

import pytest

from app.config import SETTINGS
from app.kernel.bind_api import bind_and_expose, resolve_llm_mode
from app.llm.mock import MockLLM
from app.memory.extractor import MockMemoryExtractor
from app.memory.sessions import ConversationStore
from app.models.memory import MemoryPatch
from tests.conftest import make_task

pytestmark = pytest.mark.trust


def test_resolve_llm_mode_mock_by_default(monkeypatch):
    monkeypatch.delenv("CF_LLM_MODE", raising=False)
    monkeypatch.setenv("CF_USE_VERTEX", "0")
    monkeypatch.setenv("CF_USE_GEMINI", "0")
    monkeypatch.setenv("CF_USE_OLLAMA", "0")
    assert resolve_llm_mode() == "mock"


def test_bind_and_expose_act_returns_l1_excludes_sibling(monkeypatch):
    monkeypatch.setenv("CF_LLM_MODE", "mock")
    monkeypatch.setenv("CF_USE_VERTEX", "0")
    monkeypatch.setenv("CF_USE_GEMINI", "0")
    store = ConversationStore(MockLLM({
        "navy": {"task_id": "B", "is_new_task": False, "confidence": 0.95},
        "outfit": {"task_id": "B", "is_new_task": False, "confidence": 0.95},
    }), SETTINGS)
    cid = "bind-act-1"
    eng = store.engine(cid)
    eng.reg.add(make_task("B", "outfit", "corporate outfit", ["color"], ["dress", "navy"]))
    eng.reg.add(make_task("C", "travel", "plan trip", ["hotel"], ["lisbon", "parking"]))
    w = store.writer(cid)
    w.commit([
        MemoryPatch(
            kind="decision", text="navy peplum", source_turn=1,
            workstream_id="B", slot="color", conversation_id=cid,
        ),
        MemoryPatch(
            kind="fact", text="Lisbon hotel needs parking", source_turn=2,
            workstream_id="C", conversation_id=cid,
        ),
    ], turn=2)
    eng.reg.mark_active("C", 2)

    out = bind_and_expose(
        store, MockMemoryExtractor(),
        conversation_id=cid,
        message="Confirm the navy color for the outfit",
        turn=3,
    )
    assert not out.interrupt
    assert out.task_id == "B"
    assert out.transition in ("CONTINUE", "SWITCH", "RETURN")
    assert out.l1_expose
    blob = out.l1_expose.lower()
    assert "navy" in blob
    assert "lisbon" not in blob
    assert out.answer is not None
    assert out.clarify_question is None
    assert out.latency_ms >= 0
    assert out.llm_mode == "mock"


def test_http_bind_endpoint_returns_interrupt_contract():
    from fastapi.testclient import TestClient
    from app.api import main as api_main

    client = TestClient(api_main.app)
    # Seed via ConversationStore on the live module store
    cid = "http-bind-clar"
    eng = api_main.store.engine(cid)
    eng.reg.add(make_task("A", "JWT auth", "debug jwt", ["refresh"], ["jwt", "auth", "401"]))
    eng.reg.add(make_task(
        "C", "orders", "checkout 401", ["checkout"], ["orders", "cart", "401", "checkout"],
    ))
    api_main.store.writer(cid).commit([
        MemoryPatch(kind="fact", text="refresh fails", source_turn=1, workstream_id="A"),
        MemoryPatch(kind="fact", text="checkout 401", source_turn=1, workstream_id="C"),
    ], turn=1)
    eng.reg.mark_active("A", 1)
    r = client.post("/bind", json={
        "conversation_id": cid, "message": "still getting 401", "turn": 2,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["interrupt"] is True
    assert body["transition"] == "CLARIFY"
    assert body["answer"] is None
    assert body["l1_expose"] is None
    assert body["clarify_question"]


def test_bind_and_expose_clarify_is_interrupt_no_answer():
    store = ConversationStore(MockLLM({
        "401": {"task_id": "A", "is_new_task": False, "confidence": 0.9},
        "still": {"task_id": "A", "is_new_task": False, "confidence": 0.9},
    }), SETTINGS)
    cid = "bind-clar-1"
    eng = store.engine(cid)
    eng.reg.add(make_task("A", "JWT auth", "debug jwt", ["refresh"], ["jwt", "auth", "401"]))
    eng.reg.add(make_task(
        "C", "orders", "checkout 401", ["checkout"], ["orders", "cart", "401", "checkout"],
    ))
    w = store.writer(cid)
    w.commit([
        MemoryPatch(kind="fact", text="refresh fails", source_turn=1, workstream_id="A"),
        MemoryPatch(kind="fact", text="checkout 401", source_turn=1, workstream_id="C"),
    ], turn=1)
    eng.reg.mark_active("A", 1)

    out = bind_and_expose(
        store, MockMemoryExtractor(),
        conversation_id=cid,
        message="still getting 401",
        turn=2,
    )
    assert out.interrupt is True
    assert out.transition == "CLARIFY"
    assert out.task_id is None
    assert out.answer is None
    assert out.l1_expose is None
    assert out.clarify_question
    q = out.clarify_question.lower()
    assert "jwt" in q or "auth" in q or "refresh" in q
    assert "order" in q or "checkout" in q or "cart" in q
    assert out.discrimination.get("high_confusion") is True
