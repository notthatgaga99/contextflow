from app.memory.catalog import ConversationCatalog
from app.memory.import_rollup import import_rollup_workstreams
from app.memory.registry import InMemoryRegistry
from app.memory.rollup import build_conversation_rollup
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from tests.conftest import make_task


def _seed_two_ws():
    reg = InMemoryRegistry()
    b = make_task("B", "outfit", "corporate outfit", ["choose color"], ["outfit"])
    c = make_task("C", "travel", "plan trip", ["book hotel"], ["travel"])
    reg.add(b)
    reg.add(c)
    reg.mark_active("C", 3)
    store = InMemoryMemoryStore(conversation_id="chat-a")
    w = MemoryWriter(store, reg)
    w.commit([
        MemoryPatch(kind="decision", text="navy", source_turn=2, workstream_id="B", slot="color"),
        MemoryPatch(kind="fact", text="Lisbon hotel", source_turn=3, workstream_id="C"),
    ], turn=3)
    return reg, store, w


def test_catalog_keeps_last_n_only():
    cat = ConversationCatalog(max_entries=3, persist=False)
    for i in range(5):
        cat.upsert_rollup(
            {
                "conversation_id": f"c{i}",
                "blurb": f"chat {i}",
                "open_count": 1,
                "workstreams": [],
            },
            updated_at=float(i),
        )
    listed = cat.list()
    assert len(listed) == 3
    ids = [e.conversation_id for e in listed]
    assert ids == ["c4", "c3", "c2"]
    assert cat.get("c0") is None


def test_import_paused_no_sibling_bleed_and_remaps_ids():
    src_reg, src_store, _ = _seed_two_ws()
    roll = build_conversation_rollup(src_reg, src_store, conversation_id="chat-a")

    dst_reg = InMemoryRegistry()
    dst_store = InMemoryMemoryStore(conversation_id="chat-b")
    dst_writer = MemoryWriter(dst_store, dst_reg)

    result = import_rollup_workstreams(
        dst_reg,
        dst_writer,
        roll.to_dict(),
        workstream_ids=["B"],
        turn=0,
        as_paused=True,
    )
    assert result.ok
    assert len(result.imported) == 1
    new_id = result.imported[0]["new_workstream_id"]
    assert new_id != "B"
    task = dst_reg.get(new_id)
    assert task is not None
    assert task.status == "paused"
    assert "navy" in dst_store.asserted(new_id)[0].text or any(
        i.text == "navy" for i in dst_store.asserted(new_id)
    )
    # Travel facts must not appear on the imported outfit card.
    blob = " ".join(i.text for i in dst_store.asserted(new_id))
    assert "Lisbon" not in blob
    assert dst_reg.get("B") is None


def test_catalog_plus_import_roundtrip():
    src_reg, src_store, _ = _seed_two_ws()
    cat = ConversationCatalog(max_entries=5, persist=False)
    entry = cat.touch_from_live(src_reg, src_store, conversation_id="chat-a")
    assert entry.open_count == 2
    assert cat.list()[0].conversation_id == "chat-a"

    dst_reg = InMemoryRegistry()
    dst_store = InMemoryMemoryStore(conversation_id="fresh")
    dst_writer = MemoryWriter(dst_store, dst_reg)
    got = cat.get("chat-a")
    assert got is not None
    result = import_rollup_workstreams(dst_reg, dst_writer, got.rollup, turn=1)
    assert result.ok
    assert len(result.imported) == 2
    assert len(dst_reg.open_tasks()) == 2
    assert all(t.status == "paused" for t in dst_reg.open_tasks())


def test_catalog_file_persistence_roundtrip(tmp_path):
    path = tmp_path / "catalog.json"
    cat = ConversationCatalog(max_entries=5, path=path, persist=True)
    cat.upsert_rollup(
        {
            "conversation_id": "persist-me",
            "blurb": "outfit · travel",
            "open_count": 2,
            "workstreams": [{"workstream_id": "B", "title": "outfit", "goal": "g",
                             "status": "paused", "decisions": ["navy"]}],
        },
        updated_at=10.0,
    )
    assert path.is_file()
    cat2 = ConversationCatalog(max_entries=5, path=path, persist=True)
    got = cat2.get("persist-me")
    assert got is not None
    assert got.blurb == "outfit · travel"
    assert got.rollup["open_count"] == 2
