"""Extractor invariant tests. No live Ollama/Vertex in pytest."""

from app.memory.extractor import (
    ExtractRequest,
    LlmMemoryExtractor,
    MockMemoryExtractor,
    apply_extraction,
    parse_patch_list,
)
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from app.models.task import Task, TaskAnchor
from eval.ten_workstream.load import load_fixture
from eval.ten_workstream.run import make_registry


class _StubLLM:
    def __init__(self, text: str):
        self.text = text
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        assert "ACT" in prompt or "CLARIFY" in prompt  # instructed not to choose
        return self.text


def test_invalid_workstream_id_cannot_commit():
    fx = load_fixture()
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="inv")
    writer = MemoryWriter(store, reg)
    r = writer.commit([
        MemoryPatch(kind="fact", text="x", source_turn=1, workstream_id="ZZZ",
                    conversation_id="inv"),
    ], turn=1)
    assert not r.ok
    assert store.all() == []


def test_unknown_referent_loop_cannot_commit():
    """Invented E.loop2 when only loop1 exists must not enter the store."""
    fx = load_fixture()
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="bad-ref")
    writer = MemoryWriter(store, reg)
    r = writer.commit([
        MemoryPatch(kind="decision", text="navy", source_turn=1, workstream_id="E",
                    referent_id="E.loop2", slot="color", conversation_id="bad-ref"),
    ], turn=1)
    assert not r.ok
    assert any("unknown referent" in e for e in r.errors)
    assert store.all() == []


def test_batch_with_one_bad_referent_does_not_partial_commit():
    fx = load_fixture()
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="batch-ref")
    writer = MemoryWriter(store, reg)
    r = writer.validate([
        MemoryPatch(kind="decision", text="navy", source_turn=1, workstream_id="E",
                    referent_id="E.loop1", slot="color", conversation_id="batch-ref"),
        MemoryPatch(kind="constraint", text="evening", source_turn=1, workstream_id="E",
                    referent_id="E.loop3", slot="event_time", conversation_id="batch-ref"),
    ])
    assert not r.ok
    assert any("E.loop3" in e for e in r.errors)


def test_uncertain_patch_rejected_by_writer():
    fx = load_fixture()
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="unc")
    writer = MemoryWriter(store, reg)
    r = writer.validate([
        MemoryPatch(kind="preference", text="maybe navy", source_turn=1,
                    workstream_id="E", uncertain=True, conversation_id="unc"),
    ])
    assert not r.ok
    assert any("uncertain" in e for e in r.errors)


def test_valid_anchored_patch_commits_with_provenance():
    fx = load_fixture()
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="ok")
    writer = MemoryWriter(store, reg)
    r = writer.commit([
        MemoryPatch(kind="fact", text="401 after refresh", source_turn=1,
                    workstream_id="A", referent_id="A.loop1", conversation_id="ok"),
    ], turn=1)
    assert r.ok
    item = store.asserted("A")[0]
    assert "conversation:ok:turn:1" in item.provenance
    assert item.source_turn == 1


def test_slot_supersession_preserves_history():
    fx = load_fixture()
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="sup")
    writer = MemoryWriter(store, reg)
    writer.commit([
        MemoryPatch(kind="decision", text="black", source_turn=1, workstream_id="E",
                    referent_id="E.loop1", slot="color", conversation_id="sup"),
    ], turn=1)
    writer.commit([
        MemoryPatch(kind="decision", text="navy", source_turn=2, workstream_id="E",
                    referent_id="E.loop1", slot="color", conversation_id="sup"),
    ], turn=2)
    assert store.asserted("E")[0].text == "navy"
    hist = [i for i in store.historical("E") if i.text == "black"]
    assert hist and hist[0].status == "superseded"


def test_duplicate_same_turn_idempotent():
    fx = load_fixture()
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="dup")
    writer = MemoryWriter(store, reg)
    patches = [
        MemoryPatch(kind="fact", text="401 after refresh", source_turn=1,
                    workstream_id="A", conversation_id="dup"),
    ]
    writer.commit(patches, turn=1)
    n = len(store.all())
    ver = store.namespace_version()
    writer.commit(patches, turn=1)
    assert len(store.all()) == n
    assert store.namespace_version() == ver


def test_extractor_never_mutates_store_directly():
    fx = load_fixture()
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="no-mut")
    ext = MockMemoryExtractor({
        "JWT": {"patches": [{"kind": "fact", "text": "401", "workstream_id": "A"}]},
    })
    before = len(store.all())
    ext.extract(ExtractRequest(
        message="JWT still returns 401", source_turn=1,
        open_workstreams=reg.open_tasks(),
    ))
    assert len(store.all()) == before


def test_llm_extractor_strips_routing_fields_and_unknown_ids():
    llm = _StubLLM(
        '[{"kind":"fact","text":"x","workstream_id":"A","task_id":"A",'
        '"transition":"ACT","is_new_task":false},'
        '{"kind":"fact","text":"y","workstream_id":"NOPE"}]'
    )
    fx = load_fixture()
    reg = make_registry(fx)
    ext = LlmMemoryExtractor(llm)
    out = ext.extract(ExtractRequest(
        message="JWT 401", source_turn=1, open_workstreams=reg.open_tasks(),
    ))
    assert len(out.patches) == 1
    assert out.patches[0].workstream_id == "A"
    assert not hasattr(out, "task_id")
    assert any("dropped_unknown_workstream" in n for n in out.notes)


def test_llm_extractor_normalizes_bracketed_ids():
    """Model often copies [A] from card formatting; strip brackets, do not invent."""
    llm = _StubLLM(
        '[{"kind":"fact","text":"401 after refresh","workstream_id":"[A]",'
        '"referent_id":"[A].loop1"}]'
    )
    fx = load_fixture()
    reg = make_registry(fx)
    ext = LlmMemoryExtractor(llm)
    out = ext.extract(ExtractRequest(
        message="JWT 401", source_turn=1, open_workstreams=reg.open_tasks(),
    ))
    assert len(out.patches) == 1
    assert out.patches[0].workstream_id == "A"
    assert out.patches[0].referent_id == "A.loop1"


def test_llm_extractor_unanchored_without_cards():
    llm = _StubLLM('[{"kind":"decision","text":"black dress","workstream_id":"E"}]')
    ext = LlmMemoryExtractor(llm)
    out = ext.extract(ExtractRequest(
        message="black dress", source_turn=1, open_workstreams=[],
    ))
    # E not in known set → dropped
    assert out.patches == [] or all(p.workstream_id is None for p in out.patches) or out.uncertain


def test_generate_path_not_used_for_memory_in_extractor_protocol():
    # LlmMemoryExtractor uses llm.generate for proposals only; apply_extraction
    # still goes through writer — store grows only via writer.commit.
    fx = load_fixture()
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="gen")
    writer = MemoryWriter(store, reg)
    llm = _StubLLM('[{"kind":"fact","text":"401 after refresh","workstream_id":"A","referent_id":"A.loop1"}]')
    ext = LlmMemoryExtractor(llm)
    r = apply_extraction(ext, writer, ExtractRequest(
        message="JWT 401", source_turn=1, conversation_id="gen",
        open_workstreams=reg.open_tasks(),
    ))
    assert r.ok
    assert store.asserted("A")
    assert llm.calls == 1


def test_llm_extractor_omits_invented_referent_keeps_patch():
    """E.loop3 omitted; patch still proposed with workstream E (writer can accept)."""
    llm = _StubLLM(
        '[{"kind":"decision","text":"navy","workstream_id":"E",'
        '"referent_id":"E.loop3","slot":"color"}]'
    )
    fx = load_fixture()
    reg = make_registry(fx)
    ext = LlmMemoryExtractor(llm)
    out = ext.extract(ExtractRequest(
        message="Actually navy, not black, for the formal evening event.",
        source_turn=32, open_workstreams=reg.open_tasks(),
    ))
    assert len(out.patches) == 1
    assert out.patches[0].workstream_id == "E"
    assert out.patches[0].referent_id is None
    assert any("omitted_unknown_referent" in n for n in out.notes)


def test_underspecified_message_no_assert():
    from app.memory.extractor import message_looks_underspecified
    assert message_looks_underspecified("maybe the navy one?")
    assert message_looks_underspecified("the other one")
    assert message_looks_underspecified("no, the other one")
    assert message_looks_underspecified("fix that")
    assert not message_looks_underspecified(
        "Actually navy, not black, for the formal evening event."
    )
    llm = _StubLLM('[{"kind":"preference","text":"navy","workstream_id":"E"}]')
    fx = load_fixture()
    reg = make_registry(fx)
    ext = LlmMemoryExtractor(llm)
    out = ext.extract(ExtractRequest(
        message="maybe the navy one?", source_turn=46,
        open_workstreams=reg.open_tasks(),
    ))
    assert out.uncertain and out.patches == []
    assert llm.calls == 0  # fail-closed before generate


def test_llm_extractor_fills_supersedes_for_slot():
    llm = _StubLLM(
        '[{"kind":"decision","text":"navy","workstream_id":"E",'
        '"referent_id":"E.loop1","slot":"color"}]'
    )
    fx = load_fixture()
    reg = make_registry(fx)
    from app.models.memory import MemoryItem
    prior = MemoryItem(
        id="M1", kind="decision", text="black", status="asserted",
        workstream_id="E", referent_id="E.loop1", slot="color",
        source_turn=3, provenance="t",
    )
    ext = LlmMemoryExtractor(llm)
    out = ext.extract(ExtractRequest(
        message="Actually navy, not black, for the formal evening event.",
        source_turn=32, open_workstreams=reg.open_tasks(),
        asserted_items=[prior],
    ))
    assert out.patches[0].supersedes_id == "M1"
