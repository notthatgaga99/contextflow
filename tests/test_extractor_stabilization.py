"""Phase 12: extractor dedup + correction stabilization (deterministic, no live Vertex)."""

import json

from app.memory.extractor import (
    ExtractRequest,
    LlmMemoryExtractor,
    MockMemoryExtractor,
    apply_extraction,
    filter_redundant_patches,
    message_looks_recall_only,
)
from app.memory.registry import InMemoryRegistry
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from app.models.task import Task, TaskAnchor
from tests.test_memory_extractor import NAVY_KEY, NAVY_MSG, _navy_script, abcd_black


def _outfit_reg():
    reg = InMemoryRegistry()
    reg.add(Task(
        id="B", title="corporate outfit", status="paused",
        retrieval_cues=["outfit", "dress", "formal"],
        anchor=TaskAnchor(goal="choose outfit", open_loops=["pick dress color"]),
    ))
    return reg


def test_recall_only_messages_abstain():
    assert message_looks_recall_only("What did we decide on color?")
    assert message_looks_recall_only("What was the Lisbon hotel requirement again?")
    assert not message_looks_recall_only("Actually navy, not black.")


def test_llm_recall_turn_returns_empty_without_llm_call():
    class Boom:
        def generate(self, prompt):
            raise AssertionError("recall should not call LLM")

    ext = LlmMemoryExtractor(Boom())
    out = ext.extract(ExtractRequest(
        message="What did we decide on color?",
        source_turn=7,
        open_workstreams=_outfit_reg().open_tasks(),
    ))
    assert out.uncertain and out.patches == []
    assert "recall_only" in out.notes[0]


def test_llm_drops_redundant_reassertion():
    reg, store, writer = abcd_black()
    ext = MockMemoryExtractor(_navy_script())
    apply_extraction(ext, writer, ExtractRequest(
        message=NAVY_MSG, source_turn=12, conversation_id="demo",
        open_workstreams=reg.open_tasks(), asserted_items=store.asserted(),
    ))
    n_before = len(store.all())

    class JsonLLM:
        def generate(self, prompt):
            return json.dumps([{
                "kind": "decision",
                "text": "navy",
                "workstream_id": "B",
                "referent_id": "B.loop1",
                "slot": "color",
            }])

    ext2 = LlmMemoryExtractor(JsonLLM())
    r = apply_extraction(ext2, writer, ExtractRequest(
        message="still thinking navy for the dress",
        source_turn=13,
        conversation_id="demo",
        open_workstreams=reg.open_tasks(),
        asserted_items=store.asserted(),
    ))
    assert r.ok
    assert r.items == []
    assert len(store.all()) == n_before


def test_llm_black_to_navy_supersedes_with_full_sentence_patch():
    reg, store, writer = abcd_black()
    black = next(i for i in store.asserted("B") if i.slot == "color")

    class JsonLLM:
        def generate(self, prompt):
            return json.dumps([{
                "kind": "decision",
                "text": "Pick a navy dress.",
                "workstream_id": "B",
                "referent_id": "B.loop1",
            }])

    ext = LlmMemoryExtractor(JsonLLM())
    r = apply_extraction(ext, writer, ExtractRequest(
        message="Actually I changed my mind: navy, not black.",
        source_turn=12,
        conversation_id="demo",
        open_workstreams=reg.open_tasks(),
        asserted_items=store.asserted(),
    ))
    assert r.ok, r.errors
    navy = next(i for i in store.asserted("B") if i.slot == "color")
    assert navy.text == "navy"
    assert store.get(black.id).status == "superseded"
    assert store.get(black.id).superseded_by == navy.id


def test_llm_repeated_navy_not_duplicated():
    reg, store, writer = abcd_black()
    ext = MockMemoryExtractor(_navy_script())
    apply_extraction(ext, writer, ExtractRequest(
        message=NAVY_MSG, source_turn=12, conversation_id="demo",
        open_workstreams=reg.open_tasks(), asserted_items=store.asserted(),
    ))
    n_after_first = len(store.asserted("B"))

    class JsonLLM:
        def generate(self, prompt):
            return json.dumps([{
                "kind": "decision", "text": "navy", "workstream_id": "B",
                "referent_id": "B.loop1", "slot": "color",
            }])

    ext2 = LlmMemoryExtractor(JsonLLM())
    r = apply_extraction(ext2, writer, ExtractRequest(
        message="still navy",
        source_turn=13,
        conversation_id="demo",
        open_workstreams=reg.open_tasks(),
        asserted_items=store.asserted(),
    ))
    assert r.ok
    assert len(store.asserted("B")) == n_after_first


def test_llm_unrelated_color_mention_on_other_workstream():
    reg, store, writer = abcd_black()

    class JsonLLM:
        def generate(self, prompt):
            return json.dumps([{
                "kind": "fact", "text": "team prefers navy branding",
                "workstream_id": "A", "referent_id": "A.loop1",
            }])

    ext = LlmMemoryExtractor(JsonLLM())
    r = apply_extraction(ext, writer, ExtractRequest(
        message="the auth team uses navy in their logo",
        source_turn=9,
        conversation_id="demo",
        open_workstreams=reg.open_tasks(),
        asserted_items=store.asserted(),
    ))
    assert r.ok
    assert any(i.workstream_id == "A" for i in store.asserted("A"))
    assert all(i.text != "navy" or i.workstream_id != "B" for i in store.asserted("B"))


def test_llm_uncertain_maybe_navy_abstains():
    class JsonLLM:
        def generate(self, prompt):
            return json.dumps([{
                "kind": "decision", "text": "maybe navy",
                "workstream_id": "B", "uncertain": True,
            }])

    ext = LlmMemoryExtractor(JsonLLM())
    out = ext.extract(ExtractRequest(
        message="maybe navy?",
        source_turn=1,
        open_workstreams=_outfit_reg().open_tasks(),
    ))
    assert out.uncertain or not out.patches


def test_llm_unknown_referent_cleared():
    class JsonLLM:
        def generate(self, prompt):
            return json.dumps([{
                "kind": "decision", "text": "navy",
                "workstream_id": "B", "referent_id": "B.loop9",
            }])

    ext = LlmMemoryExtractor(JsonLLM())
    out = ext.extract(ExtractRequest(
        message="navy",
        source_turn=1,
        open_workstreams=abcd_black()[0].open_tasks(),
    ))
    assert out.patches and out.patches[0].referent_id is None


def test_llm_invented_loop_dropped_or_cleared():
    class JsonLLM:
        def generate(self, prompt):
            return json.dumps([{
                "kind": "fact", "text": "x",
                "workstream_id": "B", "referent_id": "B.loop2",
            }])

    ext = LlmMemoryExtractor(JsonLLM())
    out = ext.extract(ExtractRequest(
        message="x",
        source_turn=1,
        open_workstreams=abcd_black()[0].open_tasks(),
    ))
    assert out.patches
    assert out.patches[0].referent_id is None


def test_same_turn_retry_idempotent_with_llm_path():
    from eval.ten_workstream.load import load_fixture
    from eval.ten_workstream.run import make_registry

    fx = load_fixture()
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="retry")
    writer = MemoryWriter(store, reg)

    class JsonLLM:
        def generate(self, prompt):
            return json.dumps([{
                "kind": "decision", "text": "navy", "workstream_id": "E",
                "referent_id": "E.loop1", "slot": "color",
            }])

    ext = LlmMemoryExtractor(JsonLLM())
    req = ExtractRequest(
        message="navy", source_turn=3, conversation_id="retry",
        open_workstreams=reg.open_tasks(), asserted_items=store.asserted(),
    )
    r1 = apply_extraction(ext, writer, req)
    r2 = apply_extraction(ext, writer, req)
    assert r1.ok and r2.ok
    assert r2.idempotent_retry
    assert len([i for i in store.asserted("E") if i.slot == "color"]) == 1


def test_filter_redundant_helper_unit():
    reg = _outfit_reg()
    store = InMemoryMemoryStore()
    writer = MemoryWriter(store, reg)
    writer.commit([
        MemoryPatch(kind="decision", text="navy", source_turn=1,
                    workstream_id="B", slot="color", proposer="extractor"),
    ], turn=1)
    dup = MemoryPatch(kind="decision", text="Pick a navy dress.", source_turn=2,
                      workstream_id="B", slot="color", proposer="extractor")
    kept, notes = filter_redundant_patches([dup], store.asserted())
    assert kept == []
    assert notes
