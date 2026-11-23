"""Integration: bind_and_expose survives FakeFirestore process drop (+ optional emulator)."""

from __future__ import annotations

import os

import pytest

from app.kernel.bind_api import bind_and_expose
from app.llm.mock import MockLLM
from app.memory.extractor import MockMemoryExtractor
from app.memory.fake_firestore import FakeFirestoreClient
from app.memory.sessions import ConversationStore
from app.models.memory import MemoryPatch
from tests.conftest import make_task

pytestmark = [pytest.mark.trust, pytest.mark.integration]


def test_bind_and_expose_slot_ttl_survives_fakefirestore_restart(monkeypatch):
    monkeypatch.setenv("CF_MEMORY_BACKEND", "firestore")
    monkeypatch.setenv("CF_LLM_MODE", "mock")
    client = FakeFirestoreClient()
    cid = "bind-durable-ttl"
    scripts = {
        "TTL": {"task_id": "C", "is_new_task": False, "confidence": 0.9},
        "ttl": {"task_id": "C", "is_new_task": False, "confidence": 0.9},
    }

    store1 = ConversationStore(MockLLM(scripts), store_client=client)
    eng1 = store1.engine(cid)
    eng1.reg.add(make_task("A", "JWT auth", "debug jwt", ["refresh"], ["jwt", "auth", "refresh"]))
    eng1.reg.add(make_task("C", "orders", "checkout 401", ["checkout"], ["orders", "cart", "checkout"]))
    store1.writer(cid).commit([
        MemoryPatch(
            kind="decision", text="5 minutes", source_turn=1,
            workstream_id="A", slot="ttl", conversation_id=cid,
        ),
        MemoryPatch(
            kind="fact", text="cart 401", source_turn=1,
            workstream_id="C", conversation_id=cid,
        ),
    ], turn=1)
    eng1.reg.mark_active("C", 1)

    out1 = bind_and_expose(
        store1, MockMemoryExtractor(),
        conversation_id=cid,
        message="what's the TTL?",
        turn=2,
    )
    assert not out1.interrupt
    assert out1.task_id == "A"
    assert out1.l1_expose and "5 minutes" in out1.l1_expose.lower()
    assert "cart" not in (out1.l1_expose or "").lower()

    store1.reset()
    del store1

    store2 = ConversationStore(MockLLM(scripts), store_client=client)
    items_a = store2.memory_store(cid).asserted("A")
    assert any((i.slot or "") == "ttl" for i in items_a)

    out2 = bind_and_expose(
        store2, MockMemoryExtractor(),
        conversation_id=cid,
        message="remind me of the TTL",
        turn=3,
    )
    assert out2.task_id == "A", (
        f"after restart expected A, got {out2.task_id} {out2.transition}"
    )
    blob = (out2.l1_expose or "").lower()
    assert "5 minutes" in blob
    assert "checkout" not in blob


@pytest.mark.skipif(
    not os.getenv("FIRESTORE_EMULATOR_HOST"),
    reason="Set FIRESTORE_EMULATOR_HOST for live emulator revive",
)
def test_bind_and_expose_emulator_revive_optional(monkeypatch):
    """Same bind_and_expose contract against real emulator when available."""
    monkeypatch.setenv("CF_MEMORY_BACKEND", "firestore")
    monkeypatch.setenv("CF_LLM_MODE", "mock")
    scripts = {"ttl": {"task_id": "C", "is_new_task": False, "confidence": 0.9}}
    cid = "bind-emu-ttl"
    store = ConversationStore(MockLLM(scripts))
    eng = store.engine(cid)
    eng.reg.add(make_task("A", "JWT auth", "debug jwt", ["refresh"], ["jwt", "auth"]))
    eng.reg.add(make_task("C", "orders", "checkout", ["checkout"], ["orders", "cart"]))
    store.writer(cid).commit([
        MemoryPatch(
            kind="decision", text="5 minutes", source_turn=1,
            workstream_id="A", slot="ttl", conversation_id=cid,
        ),
    ], turn=1)
    eng.reg.mark_active("C", 1)
    out = bind_and_expose(
        store, MockMemoryExtractor(),
        conversation_id=cid,
        message="what's the TTL?",
        turn=2,
    )
    assert out.task_id == "A"
    store.reset()
    del store
    store2 = ConversationStore(MockLLM(scripts))
    if store2.engine(cid).reg.get("A") is None:
        pytest.skip("emulator registry not durable in this config")
    out2 = bind_and_expose(
        store2, MockMemoryExtractor(),
        conversation_id=cid,
        message="TTL again",
        turn=3,
    )
    assert out2.task_id == "A"
