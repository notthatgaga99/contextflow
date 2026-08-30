"""Negative memory paths — every failure must fail closed."""

from app.config import SETTINGS
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.extractor import ExtractRequest, MockMemoryExtractor, apply_extraction
from app.memory.registry import InMemoryRegistry
from app.memory.store import DuplicateTurnError, InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from tests.conftest import make_task


def _world():
    reg = InMemoryRegistry()
    reg.add(make_task("A", "auth", "fix JWT", ["401"], ["jwt"]))
    reg.add(make_task("B", "outfit", "pick outfit", ["color"], ["dress"]))
    store = InMemoryMemoryStore()
    return reg, store, MemoryWriter(store, reg)


def test_wrong_workstream_id_rejected():
    _, store, w = _world()
    r = w.commit([MemoryPatch(kind="fact", text="x", source_turn=1, workstream_id="Z")])
    assert not r.ok
    assert store.all() == []


def test_ambiguous_sibling_omit_referent_still_persists_unkeyed():
    reg, store, w = _world()
    r = w.commit([
        MemoryPatch(kind="fact", text="token still expired", source_turn=2,
                    workstream_id="A", proposer="extractor"),
    ])
    assert r.ok
    item = store.asserted("A")[0]
    assert item.referent_id is None


def test_unkeyed_decision_conflict_rejected():
    _, store, w = _world()
    w.commit([MemoryPatch(kind="decision", text="black", source_turn=1, workstream_id="B")])
    r = w.commit([MemoryPatch(kind="decision", text="navy", source_turn=2, workstream_id="B")])
    assert not r.ok
    assert store.asserted("B")[0].text == "black"


def test_uncertain_patch_rejected():
    _, store, w = _world()
    r = w.commit([
        MemoryPatch(kind="fact", text="maybe navy", source_turn=1,
                    workstream_id="B", uncertain=True),
    ])
    assert not r.ok
    assert store.all() == []


def test_uncertain_extraction_does_not_commit():
    reg, store, w = _world()
    ext = MockMemoryExtractor({"maybe": {"uncertain": True, "notes": ["ambiguous"]}})
    req = ExtractRequest(message="maybe navy", source_turn=1, open_workstreams=reg.open_tasks())
    out = apply_extraction(ext, w, req)
    assert out.ok
    assert store.all() == []


def test_duplicate_turn_different_content_rejected():
    _, store, w = _world()
    w.commit([MemoryPatch(kind="fact", text="401", source_turn=1, workstream_id="A")], turn=1)
    r = w.commit([MemoryPatch(kind="fact", text="other", source_turn=1, workstream_id="A")], turn=1)
    assert not r.ok


def test_duplicate_turn_identical_idempotent():
    _, store, w = _world()
    w.commit([MemoryPatch(kind="fact", text="401", source_turn=1, workstream_id="A")], turn=1)
    n = len(store.all())
    r = w.commit([MemoryPatch(kind="fact", text="401", source_turn=1, workstream_id="A")], turn=1)
    assert r.ok
    assert len(store.all()) == n


def test_correction_supersedes_decision_on_slot():
    reg, store, w = _world()
    w.commit([MemoryPatch(kind="decision", text="black", source_turn=1,
                          workstream_id="B", slot="color")])
    r = w.commit([MemoryPatch(kind="correction", text="navy", source_turn=2,
                              workstream_id="B", slot="color")])
    assert r.ok
    assert store.asserted("B")[0].text == "navy"
    old = next(i for i in store.historical("B") if i.text == "black")
    assert old.status == "superseded"


def test_abandon_closes_workstream_keeps_history():
    reg, store, w = _world()
    w.commit([MemoryPatch(kind="fact", text="401", source_turn=1, workstream_id="A")], turn=1)
    r = w.commit([MemoryPatch(kind="fact", text="", source_turn=2,
                              action="abandon", workstream_id="A")], turn=2)
    assert r.ok
    assert reg.get("A").status == "abandoned"
    assert len(store.all()) == 1
    assert "A" not in {t.id for t in reg.open_tasks()}


def test_retract_invalidates_without_delete():
    _, store, w = _world()
    first = w.commit([MemoryPatch(kind="fact", text="401", source_turn=1, workstream_id="A")])
    iid = first.items[0].id
    r = w.commit([MemoryPatch(kind="fact", text="", source_turn=2,
                              action="retract", retract_id=iid, workstream_id="A")])
    assert r.ok
    assert store.get(iid).status == "retracted"
    assert store.get(iid) is not None


def test_hallucinated_entity_unknown_referent_rejected():
    _, store, w = _world()
    r = w.commit([
        MemoryPatch(kind="entity", text="ghost", source_turn=1,
                    workstream_id="B", referent_id="B.loop9"),
    ])
    assert not r.ok
    assert store.all() == []


def test_generate_does_not_mutate_memory():
    reg, store, w = _world()
    w.commit([MemoryPatch(kind="decision", text="navy", source_turn=1,
                          workstream_id="B", slot="color")], turn=1)
    ver = store.namespace_version()
    eng = Engine(MockLLM({"back to dress": {"task_id": "B", "is_new_task": False, "confidence": 0.4}}),
                 reg, SETTINGS, memory_store=store)
    eng.handle_turn("back to dress", 3)
    assert store.namespace_version() == ver


def test_missing_constraint_not_invented_by_writer():
    _, store, w = _world()
    w.commit([MemoryPatch(kind="decision", text="navy", source_turn=1,
                          workstream_id="B", slot="color")], turn=1)
    constraints = [i for i in store.asserted("B") if i.kind == "constraint"]
    assert constraints == []
