"""Durable E2E: same kernel path after process-local drop (FakeFirestore).

Simulates restart: new ConversationStore, same Firestore client data.
Switch laws must still hold. Marked trust + uses CF_MEMORY_BACKEND=firestore.
"""

from __future__ import annotations

import pytest

from app.kernel.session import run_kernel_turn
from app.llm.mock import MockLLM
from app.memory.extractor import MockMemoryExtractor
from app.memory.fake_firestore import FakeFirestoreClient
from app.memory.sessions import ConversationStore
from app.models.memory import MemoryPatch
from tests.conftest import make_task

pytestmark = pytest.mark.trust


def test_kernel_switch_survives_restart(monkeypatch):
    monkeypatch.setenv("CF_MEMORY_BACKEND", "firestore")
    client = FakeFirestoreClient()
    cid = "durable-switch-1"

    # --- live process: seed two threads + memory, bind outfit ---
    store1 = ConversationStore(MockLLM(), store_client=client)
    eng1 = store1.engine(cid)
    eng1.reg.add(make_task("B", "outfit", "corporate outfit", ["color"], ["dress", "navy"]))
    eng1.reg.add(make_task("C", "travel", "plan trip", ["hotel"], ["lisbon", "parking"]))
    w1 = store1.writer(cid)
    w1.commit([
        MemoryPatch(
            kind="decision", text="navy peplum", source_turn=1,
            workstream_id="B", slot="color", conversation_id=cid,
        ),
        MemoryPatch(
            kind="fact", text="Lisbon hotel needs parking", source_turn=2,
            workstream_id="C", conversation_id=cid,
        ),
    ], turn=2)
    eng1.reg.mark_active("C", 2)
    eng1.reg.mark_active("B", 3)

    k1 = run_kernel_turn(
        eng1, w1, MockMemoryExtractor(),
        conversation_id=cid,
        message="Confirm the navy color for the outfit",
        turn=3,
    )
    assert k1.result.task_id == "B"
    assert k1.expose_text and "navy" in k1.expose_text.lower()
    assert "lisbon" not in k1.expose_text.lower()

    # --- restart: drop in-process maps; keep FakeFirestore data ---
    store1.reset()
    del store1

    store2 = ConversationStore(MockLLM(), store_client=client)
    eng2 = store2.engine(cid)
    assert eng2.reg.get("B") is not None
    assert eng2.reg.get("C") is not None
    asserted_b = [i.text for i in store2.memory_store(cid).asserted("B")]
    assert any("navy" in t.lower() for t in asserted_b)

    k2 = run_kernel_turn(
        eng2, store2.writer(cid), MockMemoryExtractor(),
        conversation_id=cid,
        message="Back to the outfit — still navy?",
        turn=4,
    )
    assert k2.result.task_id == "B", (
        f"after restart expected B, got {k2.result.task_id} "
        f"transition={k2.result.transition}"
    )
    assert k2.expose_text is not None
    blob = k2.expose_text.lower()
    assert "navy" in blob
    assert "lisbon" not in blob
    assert "parking" not in blob
