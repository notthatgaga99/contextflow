"""Phase 14: NEW-focus fact extraction + extract_committed semantics."""

from app.domain import Transition
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.extractor import (
    ExtractRequest,
    LlmMemoryExtractor,
    apply_extraction,
    try_parse_new_focus_fact,
)
from app.memory.registry import InMemoryRegistry
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.task import Task, TaskAnchor
from app.turn_pipeline import run_turn


class _AbstainLLM:
    """Vertex-shaped abstain — must not be required for NEW espresso persistence."""

    def generate(self, prompt):
        return "[]"

    def propose(self, prompt, schema):
        return {"patches": [], "abstain": True}

    def embed(self, texts):
        return MockLLM().embed(texts)


def test_new_focus_fact_requires_focus_id():
    assert try_parse_new_focus_fact(
        "I need to figure out why my espresso machine keeps leaking.",
        focus_workstream_id=None,
        asserted=[],
    ) is None


def test_new_focus_fact_espresso():
    row = try_parse_new_focus_fact(
        "I need to figure out why my espresso machine keeps leaking water.",
        focus_workstream_id="T1",
        asserted=[],
    )
    assert row is not None
    assert row["kind"] == "fact"
    assert row["workstream_id"] == "T1"
    assert "leaking" in row["text"].lower()


def test_new_focus_fact_abstains_recall():
    assert try_parse_new_focus_fact(
        "What did we decide on color?",
        focus_workstream_id="T1",
        asserted=[],
    ) is None


def test_new_focus_fact_abstains_maybe():
    assert try_parse_new_focus_fact(
        "Maybe navy?",
        focus_workstream_id="T1",
        asserted=[],
    ) is None


def test_new_focus_fact_no_unrelated_color_mention():
    assert try_parse_new_focus_fact(
        "Blue is my favorite color.",
        focus_workstream_id="T1",
        asserted=[],
    ) is None


def test_pipeline_new_persists_without_vertex():
    reg = InMemoryRegistry()
    store = InMemoryMemoryStore(conversation_id="dyn14")
    writer = MemoryWriter(store, reg)
    llm = MockLLM({
        "espresso": {"task_id": None, "is_new_task": True, "confidence": 0.95},
        "leaking": {"task_id": None, "is_new_task": True, "confidence": 0.95},
    })
    eng = Engine(llm, reg, memory_store=store)
    ext = LlmMemoryExtractor(_AbstainLLM())
    pipe = run_turn(
        eng, writer, ext,
        conversation_id="dyn14",
        message="I need to figure out why my espresso machine keeps leaking.",
        turn=1,
    )
    assert pipe.turn.transition == Transition.NEW
    assert pipe.turn.task_id == "T1"
    assert pipe.extract.ok
    assert pipe.extract.items
    assert any("leaking" in i.text for i in store.asserted("T1"))
    notes = ext.extract(ExtractRequest(
        message="I need to figure out why my espresso machine keeps leaking.",
        source_turn=1,
        open_workstreams=eng.reg.open_tasks(),
        focus_workstream_id="T1",
    )).notes
    assert "deterministic_new_focus_fact" in notes


def test_apply_extraction_notes_new_focus():
    reg = InMemoryRegistry()
    reg.add(Task(
        id="T1", title="espresso", status="active",
        retrieval_cues=["espresso"],
        anchor=TaskAnchor(goal="fix leak", open_loops=["leaking"]),
    ))
    store = InMemoryMemoryStore(conversation_id="n")
    writer = MemoryWriter(store, reg)
    ext = LlmMemoryExtractor(_AbstainLLM())
    req = ExtractRequest(
        message="I need to figure out why my espresso machine keeps leaking.",
        source_turn=1,
        conversation_id="n",
        open_workstreams=reg.open_tasks(),
        focus_workstream_id="T1",
    )
    out = ext.extract(req)
    assert out.patches
    assert "deterministic_new_focus_fact" in out.notes
    r = apply_extraction(ext, writer, req)
    assert r.ok and r.items


def test_idempotent_retry_same_new_focus_fact():
    reg = InMemoryRegistry()
    reg.add(Task(
        id="T1", title="espresso", status="active",
        retrieval_cues=["espresso"],
        anchor=TaskAnchor(goal="fix leak", open_loops=["leaking"]),
    ))
    store = InMemoryMemoryStore(conversation_id="n")
    writer = MemoryWriter(store, reg)
    ext = LlmMemoryExtractor(_AbstainLLM())
    req = ExtractRequest(
        message="I need to figure out why my espresso machine keeps leaking.",
        source_turn=1,
        conversation_id="n",
        open_workstreams=reg.open_tasks(),
        asserted_items=[],
        focus_workstream_id="T1",
    )
    r1 = apply_extraction(ext, writer, req)
    req2 = ExtractRequest(
        message=req.message,
        source_turn=1,
        conversation_id="n",
        open_workstreams=reg.open_tasks(),
        asserted_items=store.asserted(),
        focus_workstream_id="T1",
    )
    r2 = apply_extraction(ext, writer, req2)
    assert r1.ok and r2.ok
    asserted = [i for i in store.asserted("T1") if i.status == "asserted"]
    # Second pass may drop as redundant or idempotent — never duplicate current.
    texts = [i.text for i in asserted]
    assert len(texts) == len(set(texts))
