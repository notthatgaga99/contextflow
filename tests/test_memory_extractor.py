"""Extractor → MemoryWriter only. Engineering fixtures, not empirical evidence."""

import json

from app.config import SETTINGS
from app.context.working_set import WorkingContextBuilder
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.extractor import (
    ExtractRequest,
    LlmMemoryExtractor,
    MockMemoryExtractor,
    apply_extraction,
)
from app.memory.registry import InMemoryRegistry
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from app.models.task import Task, TaskAnchor

NAVY_MSG = (
    "Actually, back to the dress — navy, not black. "
    "And it needs to work for the formal evening event."
)

NAVY_KEY = "navy, not black"


def _task(tid, title, goal, loops, cues):
    return Task(
        id=tid, title=title, status="paused",
        retrieval_cues=list(cues),
        anchor=TaskAnchor(goal=goal, open_loops=list(loops)),
    )


def abcd_black():
    """B established black + formal + evening; later A → C → D."""
    reg = InMemoryRegistry()
    tasks = [
        _task("A", "authentication", "fix JWT authentication",
              ["401 after refresh", "refresh token still expired"],
              ["jwt", "401", "authentication"]),
        _task("B", "corporate outfit", "choose a corporate event outfit",
              ["pick dress color"], ["outfit", "dress", "navy", "formal"]),
        _task("C", "travel", "plan Lisbon trip",
              ["book hotel with parking"], ["lisbon", "hotel", "travel"]),
        _task("D", "paper", "finish paper draft",
              ["write related-work section"], ["paper", "draft", "citation"]),
    ]
    for t in tasks:
        reg.add(t)
    for i, tid in enumerate("ABCD", start=1):
        reg.record_mention(tid, i, f"{tid}.loop1")
        reg.mark_active(tid, i)
    store = InMemoryMemoryStore()
    w = MemoryWriter(store, reg)
    w.commit([
        MemoryPatch(kind="decision", text="black", source_turn=2, workstream_id="B",
                    referent_id="B.loop1", slot="color", proposer="extractor",
                    conversation_id="demo"),
        MemoryPatch(kind="constraint", text="corporate/formal", source_turn=2,
                    workstream_id="B", referent_id="B.loop1", slot="dress_code",
                    proposer="extractor", conversation_id="demo"),
        MemoryPatch(kind="constraint", text="evening event", source_turn=2,
                    workstream_id="B", referent_id="B.loop1", slot="event_time",
                    proposer="extractor", conversation_id="demo"),
        MemoryPatch(kind="fact", text="Lisbon hotel needs parking", source_turn=5,
                    workstream_id="C", referent_id="C.loop1", proposer="extractor",
                    conversation_id="demo"),
        MemoryPatch(kind="fact", text="citation style APA", source_turn=6,
                    workstream_id="D", referent_id="D.loop1", proposer="extractor",
                    conversation_id="demo"),
    ], turn=6)
    return reg, store, w


def _navy_script(**extra):
    spec = {
        "patches": [
            {"kind": "decision", "text": "navy", "workstream_id": "B",
             "referent_id": "B.loop1", "slot": "color"},
            {"kind": "constraint", "text": "corporate/formal", "workstream_id": "B",
             "referent_id": "B.loop1", "slot": "dress_code"},
            {"kind": "constraint", "text": "evening event", "workstream_id": "B",
             "referent_id": "B.loop1", "slot": "event_time"},
        ],
        "resolve_supersede_slot": True,
    }
    spec.update(extra)
    return {NAVY_KEY: spec}


def test_extractor_never_writes_store():
    class BoomStore(InMemoryMemoryStore):
        def commit(self, *a, **k):
            raise AssertionError("extractor must not commit")

    store = BoomStore()
    ext = MockMemoryExtractor(_navy_script())
    out = ext.extract(ExtractRequest(message=NAVY_MSG, source_turn=12, conversation_id="t"))
    assert out.patches
    assert [p.kind for p in out.patches] == ["decision", "constraint", "constraint"]
    assert store.namespace_version() == 0


def test_navy_extraction_commit_route_reconstruct():
    reg, store, writer = abcd_black()
    black = next(i for i in store.asserted("B") if i.slot == "color")
    ext = MockMemoryExtractor(_navy_script())
    req = ExtractRequest(
        message=NAVY_MSG, source_turn=12, conversation_id="demo",
        open_workstreams=reg.open_tasks(),
        asserted_items=store.asserted(),
    )
    result = apply_extraction(ext, writer, req)
    assert result.ok
    color = next(i for i in store.asserted("B") if i.slot == "color")
    assert color.text == "navy"
    assert color.conversation_id == "demo"
    assert color.source_turn == 12
    assert store.get(black.id).status == "superseded"
    assert store.get(black.id).superseded_by == color.id
    assert any(i.slot == "dress_code" and i.status == "asserted" for i in store.all())
    assert any(i.slot == "event_time" and i.status == "asserted" for i in store.all())
    v = store.namespace_version()
    llm = MockLLM({NAVY_KEY: {
        "task_id": "B", "is_new_task": False, "confidence": 0.35,
    }})
    eng = Engine(llm, reg, SETTINGS, memory_store=store)
    res = eng.handle_turn(NAVY_MSG, 13)
    assert store.namespace_version() == v
    assert res.task_id == "B"
    rendered = eng.compiler.render(res.package)
    assert "navy" in rendered.lower()
    assert "formal" in rendered.lower()
    assert "evening" in rendered.lower()
    assert "Lisbon" not in rendered and "APA" not in rendered
    assert "navy" in " ".join(res.package.active_decisions).lower()
    # MockLLM.generate only prefixes the first tokens of the prompt; it is not an answer model.
    assert "navy" in (res.package.answer_text or rendered).lower()
    proj = WorkingContextBuilder().project(reg.get("B"), "B.loop1", store)
    assert not WorkingContextBuilder().insufficient(proj, ["navy", "formal", "evening"])


def test_wrong_workstream_id_rejected():
    _reg, store, writer = abcd_black()
    n = store.namespace_version()
    ext = MockMemoryExtractor({
        "navy": {"patches": [
            {"kind": "decision", "text": "navy", "workstream_id": "Z", "slot": "color"},
        ]},
    })
    r = apply_extraction(ext, writer, ExtractRequest(message="navy", source_turn=9))
    assert not r.ok
    assert store.namespace_version() == n


def test_wrong_but_valid_workstream_commits_and_b_is_insufficient():
    reg, store, writer = abcd_black()
    ext = MockMemoryExtractor({
        "navy": {"patches": [
            {"kind": "decision", "text": "navy", "workstream_id": "A",
             "referent_id": "A.loop1", "slot": "color"},
        ]},
    })
    r = apply_extraction(ext, writer, ExtractRequest(
        message="navy", source_turn=9, open_workstreams=reg.open_tasks(),
    ))
    assert r.ok
    proj_b = WorkingContextBuilder().project(reg.get("B"), "B.loop1", store)
    assert WorkingContextBuilder().insufficient(proj_b, ["navy"])
    assert any(i.workstream_id == "A" and i.text == "navy" for i in store.asserted("A"))


def test_sibling_loops_omit_referent():
    _reg, store, writer = abcd_black()
    ext = MockMemoryExtractor({
        "token": {
            "omit_referent": True,
            "patches": [{"kind": "fact", "text": "token still expired",
                         "workstream_id": "A"}],
        },
    })
    r = apply_extraction(ext, writer, ExtractRequest(message="token", source_turn=9))
    assert r.ok
    item = next(i for i in store.asserted("A") if i.text == "token still expired")
    assert item.referent_id is None


def test_ambiguous_fact_no_invented_item():
    _reg, store, writer = abcd_black()
    n = len(store.all())
    ext = MockMemoryExtractor({
        "maybe": {"uncertain": True, "notes": ["ambiguous_fact"]},
    })
    r = apply_extraction(ext, writer, ExtractRequest(
        message="maybe the navy one?", source_turn=9,
    ))
    assert r.ok
    assert r.items == []
    assert "ambiguous_fact" in r.errors
    assert len(store.all()) == n


def test_old_fact_conflict_without_supersession():
    _reg, store, writer = abcd_black()
    writer.commit([
        MemoryPatch(kind="decision", text="black unkeyed", source_turn=7,
                    workstream_id="B", proposer="extractor"),
    ], turn=7)
    n = store.namespace_version()
    ext = MockMemoryExtractor({
        "navy": {"patches": [
            {"kind": "decision", "text": "navy", "workstream_id": "B"},
        ]},
    })
    r = apply_extraction(ext, writer, ExtractRequest(message="navy", source_turn=9))
    assert not r.ok
    assert "unresolved_decision_conflict" in r.errors[0]
    assert store.namespace_version() == n
    asserted_unkeyed = [
        i for i in store.asserted("B") if i.kind == "decision" and not i.slot
    ]
    assert len(asserted_unkeyed) == 1 and asserted_unkeyed[0].text == "black unkeyed"


def test_omitted_constraint_flags_insufficiency():
    reg = InMemoryRegistry()
    reg.add(_task("B", "corporate outfit", "choose a corporate event outfit",
                  ["pick dress color"], ["outfit", "dress", "navy", "formal"]))
    store = InMemoryMemoryStore()
    writer = MemoryWriter(store, reg)
    writer.commit([
        MemoryPatch(kind="decision", text="black", source_turn=2, workstream_id="B",
                    referent_id="B.loop1", slot="color", proposer="extractor"),
    ], turn=2)
    ext = MockMemoryExtractor({
        NAVY_KEY: {"patches": [
            {"kind": "decision", "text": "navy", "workstream_id": "B",
             "referent_id": "B.loop1", "slot": "color"},
        ], "resolve_supersede_slot": True, "notes": ["omitted_constraint"]},
    })
    apply_extraction(ext, writer, ExtractRequest(
        message=NAVY_MSG, source_turn=9, asserted_items=store.asserted(),
    ))
    proj = WorkingContextBuilder().project(reg.get("B"), "B.loop1", store)
    assert WorkingContextBuilder().insufficient(proj, ["formal", "evening"])
    assert not WorkingContextBuilder().insufficient(proj, ["navy"])


def test_supported_kinds_and_retract_go_through_writer():
    _reg, store, writer = abcd_black()
    apa = next(i for i in store.asserted("D") if "APA" in i.text)
    ext = MockMemoryExtractor({
        "kinds": {"patches": [
            {"kind": "fact", "text": "guest list is 40", "workstream_id": "B",
             "referent_id": "B.loop1"},
            {"kind": "entity", "text": "the navy dress", "workstream_id": "B",
             "referent_id": "B.loop1"},
            {"kind": "preference", "text": "prefer pockets", "workstream_id": "B",
             "referent_id": "B.loop1"},
            {"kind": "event", "text": "fitting on Thursday", "workstream_id": "B",
             "referent_id": "B.loop1"},
            {"kind": "correction", "text": "not black", "workstream_id": "B",
             "referent_id": "B.loop1"},
            {"kind": "fact", "text": "", "action": "retract", "retract_id": apa.id,
             "workstream_id": "D"},
        ]},
    })
    r = apply_extraction(ext, writer, ExtractRequest(message="kinds", source_turn=10))
    assert r.ok
    kinds = {i.kind for i in store.asserted("B")}
    assert {"fact", "entity", "preference", "event", "correction"} <= kinds
    assert store.get(apa.id).status == "retracted"


def test_llm_extractor_fail_closed():
    class Boom:
        def generate(self, prompt):
            return "not-json"

    ext = LlmMemoryExtractor(Boom())
    out = ext.extract(ExtractRequest(message="hi", source_turn=1))
    assert out.uncertain and out.patches == []


def test_llm_extractor_drops_unknown_workstream():
    class JsonLLM:
        def generate(self, prompt):
            return '[{"kind":"fact","text":"x","workstream_id":"Z"}]'

    ext = LlmMemoryExtractor(JsonLLM())
    out = ext.extract(ExtractRequest(
        message="hi", source_turn=1, open_workstreams=abcd_black()[0].open_tasks(),
    ))
    assert out.patches == []
    assert any("dropped_unknown_workstream" in n for n in out.notes)


def test_llm_extractor_parses_fence_and_ignores_routing_fields():
    from app.memory.extractor import parse_patch_list

    data, err = parse_patch_list('```json\n[{"kind":"fact","text":"x","workstream_id":"A"}]\n```')
    assert err is None and data[0]["kind"] == "fact"

    class Mix:
        def generate(self, prompt):
            return json.dumps([{
                "kind": "fact", "text": "401", "workstream_id": "A",
                "transition": "ACT", "task_id": "A", "is_new_task": False,
            }])

    ext = LlmMemoryExtractor(Mix())
    out = ext.extract(ExtractRequest(
        message="401", source_turn=1, open_workstreams=abcd_black()[0].open_tasks(),
    ))
    assert len(out.patches) == 1
    assert out.patches[0].kind == "fact"
    assert not hasattr(out, "transition")


def test_llm_extractor_clears_invalid_referent():
    class JsonLLM:
        def generate(self, prompt):
            return '[{"kind":"decision","text":"navy","workstream_id":"B","referent_id":"corporate outfit"}]'

    ext = LlmMemoryExtractor(JsonLLM())
    out = ext.extract(ExtractRequest(
        message="navy", source_turn=1, open_workstreams=abcd_black()[0].open_tasks(),
    ))
    assert out.patches and out.patches[0].referent_id is None
    assert any(
        "omitted_unknown_referent" in n or "dropped_invalid_referent" in n
        for n in out.notes
    )

