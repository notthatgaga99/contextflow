"""Switch-mastery trust suite — primary adoption bar (Mock only).

Run: pytest -m trust -q
Laws: one hop, L1-only generate surface, bound RELEVANT, switch/revive, isolation.
"""

from __future__ import annotations

import pytest

from app.config import SETTINGS
from app.context.working_memory_switch import expose_bound_thread
from app.context.working_set import WorkingContextBuilder
from app.engine import Engine
from app.kernel.session import run_kernel_turn
from app.llm.mock import MockLLM
from app.memory.cold_search import filter_hits_for_l1, hits_from_items
from app.memory.extractor import MockMemoryExtractor
from app.memory.port import DictMemoryPort
from app.memory.registry import InMemoryRegistry
from app.memory.sessions import ConversationStore
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryItem, MemoryPatch
from eval.ten_workstream.load import extract_scripts, llm_scripts, load_fixture
from eval.ten_workstream.run import make_registry
from tests.conftest import make_task

pytestmark = pytest.mark.trust


def _item(iid, wid, kind, text, turn=1, status="asserted", slot=None):
    return MemoryItem(
        id=iid, kind=kind, text=text, source_turn=turn,
        workstream_id=wid, status=status, proposer="system", slot=slot,
    )


def test_kernel_e2e_single_hop_and_l1_surface():
    """Law: bind one hop; expose_text / package exclude sibling body."""
    store = ConversationStore(MockLLM())
    eng = store.engine("trust-e2e")
    outfit = make_task("B", "outfit", "corporate outfit", ["color"], ["dress", "navy"])
    travel = make_task("C", "travel", "plan trip", ["hotel"], ["lisbon", "parking"])
    eng.reg.add(outfit)
    eng.reg.add(travel)
    w = store.writer("trust-e2e")
    w.commit([
        MemoryPatch(kind="decision", text="navy peplum", source_turn=1,
                    workstream_id="B", slot="color", conversation_id="trust-e2e"),
        MemoryPatch(kind="fact", text="Lisbon hotel needs parking", source_turn=2,
                    workstream_id="C", conversation_id="trust-e2e"),
    ], turn=2)

    k = run_kernel_turn(
        eng, w, MockMemoryExtractor(),
        conversation_id="trust-e2e",
        message="Confirm the navy color for the outfit",
        turn=3,
    )
    assert k.result.task_id == "B"
    assert k.expose_text is not None
    blob = k.expose_text.lower()
    assert "navy" in blob
    assert "lisbon" not in blob
    assert "parking" not in blob
    if k.planes and k.planes.get("short_term"):
        assert k.planes["short_term"].get("plane") == "short_term"
        assert k.planes["short_term"].get("tier") == "L1"
    steps = [s["step"] for s in k.timeline]
    assert steps.count("bind") == 1
    assert "short_term" in steps or k.expose_text


def test_bound_relevant_never_imports_sibling():
    """Law: cold RELEVANT is bound-scoped — sibling facts stay out of L1."""
    outfit = make_task("B", "outfit", "corporate outfit", ["color"], ["dress"])
    travel = make_task("C", "travel", "plan trip", ["hotel"], ["lisbon"])
    port = DictMemoryPort(
        {"B": outfit, "C": travel},
        {
            "B": [_item("M1", "B", "decision", "navy", 2)],
            "C": [_item("M2", "C", "fact", "Lisbon hotel near station", 3)],
        },
    )
    notation = expose_bound_thread(
        port,
        workstream_id="B",
        referent_id="B.loop1",
        selected_loop="color",
        query="navy outfit Lisbon hotel",
        enrich_cold=True,
    )
    assert notation is not None
    text = notation.to_expose_text()
    assert "navy" in text.lower()
    assert "Lisbon" not in text
    hits = hits_from_items(
        "navy outfit Lisbon hotel",
        [_item("M1", "B", "decision", "navy", 2),
         _item("M2", "C", "fact", "Lisbon hotel near station", 3)],
        limit=5,
        workstream_id="B",
    )
    assert hits
    assert all(h.workstream_id == "B" for h in hits)


def test_superseded_cold_filtered_when_slot_asserted():
    """Law: superseded cold hits for an asserted slot do not enter L1."""
    hits = hits_from_items(
        "color navy",
        [
            _item("old", "B", "decision", "black", 1, status="superseded", slot="color"),
            _item("new", "B", "decision", "navy", 2, status="asserted", slot="color"),
        ],
        limit=5,
        workstream_id="B",
    )
    filtered = filter_hits_for_l1(
        hits,
        asserted_slots={"color"},
        prefer_asserted_over_superseded=True,
    )
    texts = " ".join(h.text.lower() for h in filtered)
    assert "navy" in texts or not any(h.status == "superseded" for h in filtered)
    assert not any(
        h.status == "superseded" and (h.slot or "") == "color" for h in filtered
    )


def test_switch_revive_keeps_correct_hop():
    """Law: after topic jump, binder returns to the earlier workstream."""
    fx = load_fixture()
    reg = make_registry(fx)
    mem = InMemoryMemoryStore(conversation_id="trust-switch")
    writer = MemoryWriter(mem, reg)
    ext = MockMemoryExtractor(extract_scripts(fx))
    eng = Engine(
        MockLLM(llm_scripts(fx)),
        reg,
        SETTINGS,
        memory_store=mem,
        working_context_builder=WorkingContextBuilder(),
    )
    # Seed outfit (E) then travel (F), then return to outfit (navy correction)
    for t in fx["turns"]:
        if t["turn"] in (3, 4, 11, 32):
            k = run_kernel_turn(
                eng, writer, ext,
                conversation_id="trust-switch",
                message=t["message"],
                turn=t["turn"],
            )
    assert k.result.task_id == "E"
    assert k.expose_text is not None
    blob = k.expose_text.lower()
    assert "navy" in blob or "navy" in (k.result.answer or "").lower()
    # Hard law: sibling travel must not appear in L1 after switch-back
    assert "parking" not in blob
    assert "lisbon" not in blob


def test_conversation_isolation():
    """Law: stores do not leak across conversation_id."""
    a = InMemoryMemoryStore(conversation_id="trust-a")
    b = InMemoryMemoryStore(conversation_id="trust-b")
    ra = InMemoryRegistry()
    ra.add(make_task("A", "jwt", "auth", ["401"], ["jwt"]))
    MemoryWriter(a, ra).commit([
        MemoryPatch(
            kind="fact", text="secret-a", source_turn=1,
            workstream_id="A", conversation_id="trust-a",
        ),
    ], turn=1)
    assert any(i.text == "secret-a" for i in a.all())
    assert b.all() == []


def test_package_l1_excludes_sibling_via_engine_port():
    """Law: generate package path (engine._make_package) is bound L1 only."""
    reg = InMemoryRegistry()
    b = make_task("B", "outfit", "outfit", ["color"], ["dress"])
    c = make_task("C", "travel", "trip", ["hotel"], ["travel"])
    reg.add(b)
    reg.add(c)
    store = InMemoryMemoryStore(conversation_id="trust-pkg")
    w = MemoryWriter(store, reg)
    w.commit([
        MemoryPatch(kind="decision", text="navy", source_turn=1, workstream_id="B", slot="color"),
        MemoryPatch(kind="fact", text="Lisbon hotel", source_turn=2, workstream_id="C"),
    ], turn=2)
    eng = Engine(MockLLM(), reg, memory_store=store)
    pkg, expose = eng._make_package(b, "B.loop1", "color", "what color navy?", [b, c])
    body = " ".join(
        (pkg.active_decisions or [])
        + (pkg.relevant_facts or [])
        + (pkg.active_constraints or [])
    ).lower()
    assert "navy" in body
    assert "lisbon" not in body
    assert expose and "navy" in expose.lower() and "lisbon" not in expose.lower()


def test_agent_turn_uses_kernel_timeline():
    """Agent shell consumes kernel; tools cannot invent a second bind step."""
    from app.agent.turn import run_agent_turn

    store = ConversationStore(MockLLM())
    out = run_agent_turn(
        store, MockMemoryExtractor(),
        conversation_id="trust-agent",
        message="I need a navy outfit for a formal evening",
        turn=1,
        auto_tools=True,
    )
    steps = [s["step"] for s in out["timeline"]]
    assert steps.count("bind") == 1
    assert "answer" in steps


def test_bound_write_procedure_reaches_l1():
    """Law: bound writes go through kernel Writer door and appear on L1."""
    from app.kernel.writes import assert_bound

    store = ConversationStore(MockLLM())
    eng = store.engine("trust-write")
    eng.reg.add(make_task("B", "outfit", "outfit", ["color"], ["dress"]))
    w = store.writer("trust-write")
    r = assert_bound(
        w, eng.reg,
        conversation_id="trust-write",
        workstream_id="B",
        kind="procedure",
        text="try jacket then shoes",
        turn=1,
    )
    assert r.ok, r.errors
    k = run_kernel_turn(
        eng, w, MockMemoryExtractor(),
        conversation_id="trust-write",
        message="how should I try the outfit?",
        turn=2,
    )
    assert k.result.task_id == "B"
    assert k.expose_text and "jacket" in k.expose_text.lower()
