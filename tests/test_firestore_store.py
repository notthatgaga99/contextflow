"""FirestoreMemoryStore tests via FakeFirestoreClient (no emulator required)."""

from __future__ import annotations

import pytest

from app.context.working_set import WorkingContextBuilder
from app.memory.fake_firestore import FakeFirestoreClient
from app.memory.firestore_store import FirestoreMemoryStore, StorageError
from app.memory.registry import InMemoryRegistry
from app.memory.store import DuplicateTurnError, InMemoryMemoryStore, StaleNamespaceError
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryItem, MemoryPatch
from tests.conftest import make_task


def _writer_store(cid: str, client: FakeFirestoreClient):
    reg = InMemoryRegistry()
    reg.add(make_task("B", "outfit", "outfit", ["color"], ["dress"]))
    store = FirestoreMemoryStore(cid, client=client)
    return reg, store, MemoryWriter(store, reg)


def test_write_read_roundtrip():
    client = FakeFirestoreClient()
    reg, store, w = _writer_store("c1", client)
    r = w.commit([
        MemoryPatch(kind="decision", text="navy", source_turn=1,
                    workstream_id="B", slot="color"),
    ], turn=1)
    assert r.ok
    got = store.get(r.items[0].id)
    assert got is not None
    assert got.text == "navy"
    assert got.status == "asserted"
    assert got.slot == "color"
    assert got.source_turn == 1
    assert got.conversation_id == "c1"
    assert got.provenance


def test_conversation_isolation():
    client = FakeFirestoreClient()
    _, a, wa = _writer_store("conv-A", client)
    _, b, wb = _writer_store("conv-B", client)
    wa.commit([MemoryPatch(kind="decision", text="navy", source_turn=1,
                           workstream_id="B", slot="color")], turn=1)
    wb.commit([MemoryPatch(kind="fact", text="paris", source_turn=1,
                           workstream_id="B")], turn=1)
    assert all("paris" not in i.text for i in a.all())
    assert all("navy" not in i.text for i in b.all())


def test_idempotent_retry():
    client = FakeFirestoreClient()
    _, store, w = _writer_store("c1", client)
    patch = MemoryPatch(kind="fact", text="x", source_turn=1, workstream_id="B")
    r1 = w.commit([patch], turn=1)
    assert r1.ok
    v = store.namespace_version()
    r2 = w.commit([patch], turn=1)
    assert r2.ok
    assert store.namespace_version() == v
    assert len(store.all()) == 1


def test_supersession_and_retraction():
    client = FakeFirestoreClient()
    _, store, w = _writer_store("c1", client)
    a = w.commit([MemoryPatch(kind="decision", text="black", source_turn=1,
                              workstream_id="B", slot="color")], turn=1)
    old_id = a.items[0].id
    b = w.commit([MemoryPatch(kind="decision", text="navy", source_turn=2,
                              workstream_id="B", slot="color")], turn=2)
    assert store.get(old_id).status == "superseded"
    assert store.get(old_id).superseded_by == b.items[-1].id
    assert store.asserted("B")[0].text == "navy"
    c = w.commit([MemoryPatch(kind="decision", text="", source_turn=3,
                              action="retract", retract_id=b.items[-1].id,
                              workstream_id="B")], turn=3)
    assert c.ok
    assert store.get(b.items[-1].id).status == "retracted"
    hist = store.historical("B")
    assert any(i.status == "superseded" for i in hist)
    assert any(i.status == "retracted" for i in hist)


def test_uncertain_exclusion():
    """Writer rejects uncertain patches; projection excludes uncertain items."""
    client = FakeFirestoreClient()
    reg, store, w = _writer_store("c1", client)
    rejected = w.commit([
        MemoryPatch(kind="fact", text="maybe", source_turn=1, workstream_id="B",
                    uncertain=True),
    ], turn=1)
    assert not rejected.ok
    assert store.all() == []
    # Persist an uncertain item at storage layer (bypass writer) — WC must exclude.
    store.commit([
        MemoryItem(
            id="u1", kind="fact", text="guess", source_turn=1, workstream_id="B",
            status="asserted", uncertain=True, conversation_id="c1",
            provenance="test", proposer="extractor",
        ),
        MemoryItem(
            id="ok1", kind="fact", text="known", source_turn=1, workstream_id="B",
            status="asserted", uncertain=False, conversation_id="c1",
            provenance="test", proposer="system",
        ),
    ], expected_version=0, turn=1)
    task = reg.get("B")
    proj = WorkingContextBuilder().project(task, "B.loop1", store, [task])
    assert "known" in proj.facts
    assert "guess" not in proj.facts


def test_invalid_workstream_and_referent_rejected():
    client = FakeFirestoreClient()
    reg, store, w = _writer_store("c1", client)
    assert not w.commit([
        MemoryPatch(kind="fact", text="x", source_turn=1, workstream_id="Z"),
    ], turn=1).ok
    assert store.all() == []
    assert not w.commit([
        MemoryPatch(kind="fact", text="x", source_turn=1,
                    workstream_id="B", referent_id="B.loop9"),
    ], turn=1).ok


def test_history_auditable_current_excludes_superseded():
    client = FakeFirestoreClient()
    reg, store, w = _writer_store("c1", client)
    a = w.commit([MemoryPatch(kind="decision", text="black", source_turn=1,
                              workstream_id="B", slot="color")], turn=1)
    w.commit([MemoryPatch(kind="decision", text="navy", source_turn=2,
                          workstream_id="B", slot="color")], turn=2)
    assert store.get(a.items[0].id).status == "superseded"
    assert [i.text for i in store.asserted("B")] == ["navy"]
    task = reg.get("B")
    proj = WorkingContextBuilder().project(task, "B.loop1", store, [task])
    assert any("navy" in d for d in proj.decisions)
    assert not any("black" in d for d in proj.decisions)


def test_restart_persistence_same_client():
    client = FakeFirestoreClient()
    _, store, w = _writer_store("c1", client)
    w.commit([MemoryPatch(kind="decision", text="navy", source_turn=1,
                          workstream_id="B", slot="color")], turn=1)
    # Simulate new process: new store object, same durable client.
    store2 = FirestoreMemoryStore("c1", client=client)
    assert store2.asserted("B")[0].text == "navy"
    assert store2.namespace_version() == 1


def test_storage_error_on_commit_failure():
    client = FakeFirestoreClient()
    client.fail_commits = True
    store = FirestoreMemoryStore("c1", client=client)
    item = MemoryItem(
        id="x", kind="fact", text="t", source_turn=1, workstream_id="B",
        conversation_id="c1", provenance="t", proposer="system",
    )
    with pytest.raises(StorageError):
        store.commit([item], expected_version=0, turn=1)


def test_malformed_document_fail_closed():
    client = FakeFirestoreClient()
    store = FirestoreMemoryStore("c1", client=client)
    client._docs["conversations/c1/memory/bad"] = {"id": "bad", "kind": "nope", "text": "x", "source_turn": 1}
    with pytest.raises(StorageError):
        store.get("bad")


def test_cross_conversation_commit_rejected():
    client = FakeFirestoreClient()
    store = FirestoreMemoryStore("c1", client=client)
    item = MemoryItem(
        id="x", kind="fact", text="t", source_turn=1,
        conversation_id="other", provenance="t", proposer="system",
    )
    with pytest.raises(ValueError, match="conversation_id_mismatch"):
        store.commit([item], expected_version=0, turn=1)


def test_stale_version():
    client = FakeFirestoreClient()
    store = FirestoreMemoryStore("c1", client=client)
    item = MemoryItem(
        id="x", kind="fact", text="t", source_turn=1, conversation_id="c1",
        provenance="t", proposer="system",
    )
    store.commit([item], expected_version=0, turn=1)
    with pytest.raises(StaleNamespaceError):
        store.commit([item], expected_version=0, turn=2)


def test_generate_cannot_mutate_memory_firestore():
    from app.config import SETTINGS
    from app.engine import Engine
    from app.llm.mock import MockLLM

    client = FakeFirestoreClient()
    reg, store, w = _writer_store("c1", client)
    w.commit([
        MemoryPatch(kind="decision", text="navy", source_turn=1,
                    workstream_id="B", slot="color"),
    ], turn=1)
    n = store.namespace_version()
    ids = {i.id for i in store.all()}
    llm = MockLLM({"back to the outfit": {
        "task_id": "B", "is_new_task": False, "confidence": 0.5,
    }})
    eng = Engine(llm, reg, SETTINGS, memory_store=store)
    eng.handle_turn("back to the outfit", 5)
    assert store.namespace_version() == n
    assert {i.id for i in store.all()} == ids


def test_inmemory_still_behaves():
    """Existing InMemoryMemoryStore semantics preserved."""
    store = InMemoryMemoryStore("local")
    item = MemoryItem(
        id="x", kind="fact", text="t", source_turn=1, conversation_id="local",
        provenance="t", proposer="system",
    )
    assert store.commit([item], 0, 1) == 1
    assert store.commit([item], 1, 1) == 1  # idempotent same turn
    with pytest.raises(DuplicateTurnError):
        other = MemoryItem(
            id="y", kind="fact", text="u", source_turn=1, conversation_id="local",
            provenance="t", proposer="system",
        )
        store.commit([other], 1, 1)
