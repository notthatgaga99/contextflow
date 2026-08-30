from app.memory.registry import InMemoryRegistry
from app.memory.store import DuplicateTurnError, InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryItem, MemoryPatch
from tests.conftest import make_task


def test_create_item_and_provenance_required():
    reg = InMemoryRegistry()
    reg.add(make_task("B", "outfit", "pick a corporate outfit",
                    ["choose dress color"], ["outfit", "dress", "navy"]))
    store = InMemoryMemoryStore()
    w = MemoryWriter(store, reg)
    bad = w.commit([MemoryPatch(kind="decision", text="navy", source_turn=-1,
                                workstream_id="B", slot="color")])
    assert not bad.ok
    assert store.namespace_version() == 0
    ok = w.commit([MemoryPatch(kind="decision", text="navy", source_turn=3,
                               workstream_id="B", slot="color")])
    assert ok.ok
    assert store.get(ok.items[0].id).source_turn == 3
    assert store.namespace_version() == 1


def test_invalid_workstream_and_referent_rejected():
    reg, store = InMemoryRegistry(), InMemoryMemoryStore()
    reg.add(make_task("B", "outfit", "outfit", ["color"], ["dress"]))
    w = MemoryWriter(store, reg)
    r1 = w.commit([MemoryPatch(kind="fact", text="x", source_turn=1, workstream_id="Z")])
    assert not r1.ok and store.all() == []
    r2 = w.commit([MemoryPatch(kind="fact", text="x", source_turn=1,
                               workstream_id="B", referent_id="B.loop9")])
    assert not r2.ok and store.all() == []
    r3 = w.commit([MemoryPatch(kind="nope", text="x", source_turn=1, workstream_id="B")])
    assert not r3.ok


def test_append_only_supersession_and_retraction():
    reg = InMemoryRegistry()
    reg.add(make_task("B", "outfit", "outfit", ["color"], ["dress"]))
    store = InMemoryMemoryStore()
    w = MemoryWriter(store, reg)
    a = w.commit([MemoryPatch(kind="decision", text="black", source_turn=1,
                              workstream_id="B", slot="color")])
    old_id = a.items[0].id
    b = w.commit([MemoryPatch(kind="decision", text="navy", source_turn=2,
                              workstream_id="B", slot="color")])
    assert b.ok
    old = store.get(old_id)
    assert old.status == "superseded"
    assert old.superseded_by == b.items[-1].id
    assert old.text == "black"
    assert store.get(b.items[-1].id).status == "asserted"
    assert store.get(b.items[-1].id).text == "navy"
    c = w.commit([MemoryPatch(kind="decision", text="", source_turn=3,
                              action="retract", retract_id=b.items[-1].id,
                              workstream_id="B")])
    assert c.ok
    assert store.get(b.items[-1].id).status == "retracted"


def test_unkeyed_decision_conflict_not_silently_won():
    reg = InMemoryRegistry()
    reg.add(make_task("B", "outfit", "outfit", ["color"], ["dress"]))
    store = InMemoryMemoryStore()
    w = MemoryWriter(store, reg)
    w.commit([MemoryPatch(kind="decision", text="black", source_turn=1, workstream_id="B")])
    r = w.commit([MemoryPatch(kind="decision", text="navy", source_turn=2, workstream_id="B")])
    assert not r.ok
    asserted = store.asserted("B")
    assert len(asserted) == 1 and asserted[0].text == "black"


def test_stale_namespace_and_idempotent_turn():
    reg = InMemoryRegistry()
    reg.add(make_task("B", "outfit", "outfit", ["color"], ["dress"]))
    store = InMemoryMemoryStore()
    w = MemoryWriter(store, reg)
    first = w.commit(
        [MemoryPatch(kind="fact", text="a", source_turn=1, workstream_id="B")],
        expected_version=0, turn=1,
    )
    assert first.ok and store.namespace_version() == 1
    stale = w.commit(
        [MemoryPatch(kind="fact", text="b", source_turn=2, workstream_id="B")],
        expected_version=0, turn=2,
    )
    assert not stale.ok
    same = first.items
    assert store.commit(same, expected_version=1, turn=1) == 1
    w2 = MemoryWriter(store, reg)
    retry = w2.commit(
        [MemoryPatch(kind="fact", text="a", source_turn=1, workstream_id="B")],
        expected_version=1, turn=1,
    )
    assert retry.ok
    assert len([i for i in store.all() if i.kind == "fact" and i.text == "a"]) == 1
    try:
        store.commit(
            [MemoryItem(id="OTHER", kind="fact", text="z", source_turn=1, workstream_id="B")],
            expected_version=1, turn=1,
        )
        raise AssertionError("expected DuplicateTurnError")
    except DuplicateTurnError as exc:
        assert "already committed" in str(exc)


def test_propose_does_not_write():
    reg = InMemoryRegistry()
    reg.add(make_task("B", "o", "o", ["x"], ["x"]))
    store = InMemoryMemoryStore()
    w = MemoryWriter(store, reg)
    w.propose([{"kind": "fact", "text": "hello", "source_turn": 1, "workstream_id": "B"}])
    assert store.all() == []
    assert store.namespace_version() == 0
