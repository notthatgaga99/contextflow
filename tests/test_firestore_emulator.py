"""Optional Firestore emulator integration. Skips when emulator is not running."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("FIRESTORE_EMULATOR_HOST"),
    reason="Set FIRESTORE_EMULATOR_HOST to run emulator integration",
)


def test_emulator_roundtrip():
    from app.memory.firestore_store import FirestoreMemoryStore
    from app.models.memory import MemoryItem

    store = FirestoreMemoryStore(
        "emulator-conv",
        project=os.getenv("GCP_PROJECT") or "demo-project",
        database=os.getenv("CF_FIRESTORE_DATABASE") or "(default)",
    )
    item = MemoryItem(
        id="e1", kind="fact", text="hello", source_turn=1,
        conversation_id="emulator-conv", provenance="emulator", proposer="system",
    )
    ver = store.commit([item], expected_version=store.namespace_version(), turn=1)
    assert ver >= 1
    assert store.get("e1").text == "hello"
