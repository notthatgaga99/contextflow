"""Engineering fixture only — not empirical evidence."""

from app.config import SETTINGS
from app.context.working_set import WorkingContextBuilder
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.registry import InMemoryRegistry
from app.memory.retriever import OpenWorkstreamRetriever
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from app.models.task import Task, TaskAnchor


def _task(tid, title, goal, loops, cues, status="paused"):
    return Task(
        id=tid, title=title, status=status,
        retrieval_cues=list(cues),
        anchor=TaskAnchor(goal=goal, open_loops=list(loops)),
    )


def abcd_world():
    reg = InMemoryRegistry()
    a = _task("A", "authentication", "fix JWT authentication",
              ["401 after refresh"], ["jwt", "401", "authentication"])
    b = _task("B", "corporate outfit", "choose a corporate event outfit",
              ["pick dress color"], ["outfit", "dress", "navy", "formal"])
    c = _task("C", "travel", "plan Lisbon trip",
              ["book hotel with parking"], ["lisbon", "hotel", "travel"])
    d = _task("D", "paper", "finish paper draft",
              ["write related-work section"], ["paper", "draft", "citation"])
    for t in (a, b, c, d):
        reg.add(t)
    reg.record_mention("A", 1, "A.loop1")
    reg.mark_active("A", 1)
    reg.record_mention("B", 2, "B.loop1")
    reg.mark_active("B", 2)
    reg.record_mention("C", 3, "C.loop1")
    reg.mark_active("C", 3)
    reg.record_mention("D", 4, "D.loop1")
    reg.mark_active("D", 4)
    store = InMemoryMemoryStore()
    w = MemoryWriter(store, reg)
    w.commit([
        MemoryPatch(kind="decision", text="navy", source_turn=2, workstream_id="B",
                    referent_id="B.loop1", slot="color"),
        MemoryPatch(kind="constraint", text="corporate/formal", source_turn=2,
                    workstream_id="B", referent_id="B.loop1", slot="dress_code"),
        MemoryPatch(kind="constraint", text="evening event", source_turn=2,
                    workstream_id="B", referent_id="B.loop1", slot="event"),
        MemoryPatch(kind="fact", text="Lisbon hotel needs parking", source_turn=3,
                    workstream_id="C", referent_id="C.loop1"),
        MemoryPatch(kind="fact", text="citation style APA", source_turn=4,
                    workstream_id="D", referent_id="D.loop1"),
    ], turn=4)
    return reg, store


def test_return_to_outfit_reconstructs_navy_formal_evening():
    reg, store = abcd_world()
    llm = MockLLM({"back to the outfit": {
        "task_id": "B", "is_new_task": False, "confidence": 0.4,
        "rationale": "soft guess",
    }})
    eng = Engine(
        llm, reg, SETTINGS,
        retriever=OpenWorkstreamRetriever(),
        memory_store=store,
    )
    before = [i.id for i in store.all()]
    res = eng.handle_turn("back to the outfit", 12)
    after = [i.id for i in store.all()]
    assert after == before
    assert res.package is not None
    assert res.task_id == "B"
    rendered = eng.compiler.render(res.package)
    assert "navy" in rendered.lower()
    assert "formal" in rendered.lower()
    assert "evening" in rendered.lower()
    assert "Lisbon" not in rendered
    assert "APA" not in rendered
    assert "parking" not in rendered
    proj = WorkingContextBuilder().project(reg.get("B"), res.predicted_referent_id, store)
    assert not proj or not WorkingContextBuilder().insufficient(
        proj, ["navy", "formal", "evening"]
    )


def test_correct_b_missing_navy_is_insufficient():
    reg, store = abcd_world()
    # drop color decision
    store._items = {
        k: v for k, v in store._items.items()
        if not (v.workstream_id == "B" and v.slot == "color")
    }
    proj = WorkingContextBuilder().project(reg.get("B"), "B.loop1", store)
    assert WorkingContextBuilder().insufficient(proj, ["navy", "formal", "evening"])
    llm = MockLLM({"back to the outfit": {
        "task_id": "B", "is_new_task": False, "confidence": 0.4,
    }})
    eng = Engine(llm, reg, SETTINGS, memory_store=store)
    res = eng.handle_turn("back to the outfit", 12)
    assert res.task_id == "B"
    rendered = eng.compiler.render(res.package)
    assert "navy" not in rendered.lower()
    assert WorkingContextBuilder().insufficient(
        WorkingContextBuilder().project(reg.get("B"), "B.loop1", store),
        ["navy"],
    )
