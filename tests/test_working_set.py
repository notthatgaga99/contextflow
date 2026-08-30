from app.context.working_set import WorkingContextBuilder
from app.domain import Transition
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.registry import InMemoryRegistry
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from tests.conftest import make_task


def test_working_set_filters_and_sufficiency():
    reg = InMemoryRegistry()
    b = make_task("B", "outfit", "corporate outfit", ["choose color"], ["outfit", "dress"])
    c = make_task("C", "travel", "plan trip", ["book Lisbon hotel"], ["lisbon", "hotel"])
    d = make_task("D", "paper", "draft paper", ["write intro"], ["paper", "draft"])
    reg.add(b)
    reg.add(c)
    reg.add(d)
    store = InMemoryMemoryStore()
    w = MemoryWriter(store, reg)
    w.commit([
        MemoryPatch(kind="decision", text="navy", source_turn=2, workstream_id="B", slot="color"),
        MemoryPatch(kind="constraint", text="corporate/formal", source_turn=2, workstream_id="B",
                    slot="dress_code"),
        MemoryPatch(kind="constraint", text="evening event", source_turn=2, workstream_id="B",
                    slot="event"),
        MemoryPatch(kind="fact", text="Lisbon hotel near station", source_turn=3, workstream_id="C"),
        MemoryPatch(kind="fact", text="paper due Friday", source_turn=4, workstream_id="D"),
    ], turn=4)
    builder = WorkingContextBuilder()
    proj = builder.project(b, "B.loop1", store, reg.open_tasks())
    assert "navy" in proj.decisions
    assert "corporate/formal" in proj.constraints
    assert "evening event" in proj.constraints
    blob = " ".join(proj.decisions + proj.constraints + proj.facts)
    assert "Lisbon" not in blob and "paper due" not in blob
    assert any("travel" in x.lower() or "paper" in x.lower() for x in proj.excluded_workstreams)
    assert not builder.insufficient(proj, ["navy", "formal", "evening"])
    thin = WorkingContextBuilder().project(b, "B.loop1", InMemoryMemoryStore(), [b])
    assert builder.insufficient(thin, ["navy", "formal", "evening"])


def test_superseded_excluded_from_working_set():
    reg = InMemoryRegistry()
    reg.add(make_task("B", "outfit", "outfit", ["color"], ["dress"]))
    store = InMemoryMemoryStore()
    w = MemoryWriter(store, reg)
    w.commit([MemoryPatch(kind="decision", text="black", source_turn=1,
                          workstream_id="B", slot="color")])
    w.commit([MemoryPatch(kind="decision", text="navy", source_turn=2,
                          workstream_id="B", slot="color")])
    proj = WorkingContextBuilder().project(reg.get("B"), "B.loop1", store)
    assert proj.decisions == ["navy"]


def test_clarify_produces_no_fake_working_set():
    eng = Engine(MockLLM(), InMemoryRegistry())
    from app.models.proposal import GateDecision
    d = GateDecision(
        transition=Transition.CLARIFY, task_id=None,
        top=0.0, margin=0.0, gating_quantity=0.0, candidates=[],
    )
    out = eng._clarify(d, [], None, None, {})
    assert out.package is None
    assert out.answer is None
    assert out.clarify_question
