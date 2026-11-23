"""Integration: kernel + durable FakeFirestore bind via stored slots."""

from __future__ import annotations

import pytest

from app.kernel.session import run_kernel_turn
from app.llm.mock import MockLLM
from app.memory.extractor import MockMemoryExtractor
from app.memory.fake_firestore import FakeFirestoreClient
from app.memory.sessions import ConversationStore
from app.models.memory import MemoryPatch
from eval.discrimination.kernel_probe import run_kernel_probe
from eval.discrimination.run_cases import _load_cases
from tests.conftest import make_task
from tests.test_identity_cues import CASES

pytestmark = [pytest.mark.trust, pytest.mark.integration]


def test_kernel_slot_ttl_excludes_sibling_and_exposes_value():
    rows = {c["id"]: c for c in _load_cases(CASES)}
    out = run_kernel_probe(rows["slot_ttl_vs_orders"])
    assert out["bind_ok"], out
    assert out["l1_ok"], out
    assert out["task_id"] == "A"
    blob = (out.get("l1_expose") or "").lower()
    assert "5 minutes" in blob
    assert "checkout" not in blob
    prompt = (out.get("generate_prompt") or "").lower()
    assert "checkout" not in prompt
    disc = out.get("discrimination") or {}
    hits = (disc.get("slot_hits") or {}).get("A") or []
    assert "ttl" in hits


def test_kernel_slot_sku_and_color_and_entity():
    rows = {c["id"]: c for c in _load_cases(CASES)}
    for cid, tid in (
        ("slot_sku_vs_auth", "C"),
        ("slot_color_vs_travel", "B"),
        ("entity_alfama_bare_title", "L"),
    ):
        out = run_kernel_probe(rows[cid])
        assert out["ok"], {"id": cid, **{k: out[k] for k in ("bind_ok", "l1_ok", "task_id", "transition", "forbid_hits")}}
        assert out["task_id"] == tid


def test_kernel_shared_window_clarifies():
    rows = {c["id"]: c for c in _load_cases(CASES)}
    out = run_kernel_probe(rows["slot_shared_window_clarify"])
    assert out["bind_ok"]
    assert out["transition"] == "CLARIFY"
    assert out.get("clarify_question")


def test_durable_slot_ttl_survives_firestore_restart(monkeypatch):
    """Process drop: slot=ttl still hops off orders after FakeFirestore revive."""
    monkeypatch.setenv("CF_MEMORY_BACKEND", "firestore")
    client = FakeFirestoreClient()
    cid = "durable-slot-ttl"

    store1 = ConversationStore(MockLLM({
        "TTL": {"task_id": "C", "is_new_task": False, "confidence": 0.9},
        "ttl": {"task_id": "C", "is_new_task": False, "confidence": 0.9},
    }), store_client=client)
    eng1 = store1.engine(cid)
    eng1.reg.add(make_task("A", "JWT auth", "debug jwt", ["refresh"], ["jwt", "auth", "refresh"]))
    eng1.reg.add(make_task("C", "orders", "checkout 401", ["checkout"], ["orders", "cart", "checkout"]))
    w1 = store1.writer(cid)
    w1.commit([
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

    k1 = run_kernel_turn(
        eng1, w1, MockMemoryExtractor(),
        conversation_id=cid,
        message="what's the TTL?",
        turn=2,
    )
    assert k1.result.task_id == "A"
    assert k1.expose_text and "5 minutes" in k1.expose_text.lower()
    assert "cart" not in k1.expose_text.lower()

    store1.reset()
    del store1

    store2 = ConversationStore(MockLLM({
        "TTL": {"task_id": "C", "is_new_task": False, "confidence": 0.9},
        "ttl": {"task_id": "C", "is_new_task": False, "confidence": 0.9},
    }), store_client=client)
    eng2 = store2.engine(cid)
    items_a = store2.memory_store(cid).asserted("A")
    assert any((i.slot or "") == "ttl" for i in items_a)

    k2 = run_kernel_turn(
        eng2, store2.writer(cid), MockMemoryExtractor(),
        conversation_id=cid,
        message="remind me of the TTL",
        turn=3,
    )
    assert k2.result.task_id == "A", (
        f"after restart expected A, got {k2.result.task_id} {k2.result.transition}"
    )
    blob = (k2.expose_text or "").lower()
    assert "5 minutes" in blob
    assert "checkout" not in blob
    disc = (k2.result.resolution_evidence or {}).get("discrimination") or {}
    assert "ttl" in ((disc.get("slot_hits") or {}).get("A") or [])
