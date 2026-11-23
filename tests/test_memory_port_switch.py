from app.context.working_memory_switch import expose_bound_thread
from app.context.working_set import WorkingContextBuilder, WorkingSetLimits
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.cold_search import hits_from_items, lexical_score
from app.memory.port import DictMemoryPort, InProcessMemoryPort
from app.memory.registry import InMemoryRegistry
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryItem, MemoryPatch
from tests.conftest import make_task


def _item(iid, wid, kind, text, turn=1, status="asserted"):
    return MemoryItem(
        id=iid, kind=kind, text=text, source_turn=turn,
        workstream_id=wid, status=status, proposer="system",
    )


def test_cold_search_ranks_bound_thread_only():
    items = [
        _item("M1", "B", "decision", "navy peplum for hosting", 2),
        _item("M2", "C", "fact", "Lisbon hotel near station", 3),
        _item("M3", "B", "fact", "corporate evening silhouette", 4),
    ]
    hits = hits_from_items("navy hosting outfit", items, limit=5, workstream_id="B")
    assert hits
    assert all(h.workstream_id == "B" for h in hits)
    assert any("navy" in h.text.lower() for h in hits)
    assert not any("Lisbon" in h.text for h in hits)
    assert lexical_score("navy hosting", "navy peplum for hosting") > 0


def test_expose_enriches_capped_facts_via_cold_search():
    outfit = make_task("B", "outfit", "corporate outfit", ["color"], ["dress"])
    # Many facts; caps keep 3; query should promote the navy-related one into L1
    items = [_item(f"M{i}", "B", "fact", f"noise-detail-{i}", turn=i) for i in range(1, 10)]
    items.append(_item("M99", "B", "fact", "navy peplum top for corporate hosting", turn=20))
    port = DictMemoryPort({"B": outfit}, {"B": items})
    notation = expose_bound_thread(
        port,
        workstream_id="B",
        builder=WorkingContextBuilder(limits=WorkingSetLimits(max_facts=3)),
        query="what about the navy peplum for hosting?",
        enrich_cold=True,
    )
    assert notation is not None
    assert len(notation.facts) <= 3
    assert any("navy" in f.lower() for f in notation.facts)


def test_expose_bound_thread_isolates_avenues():
    outfit = make_task("B", "outfit", "corporate outfit", ["color"], ["dress"])
    travel = make_task("C", "travel", "plan trip", ["hotel"], ["lisbon"])
    port = DictMemoryPort(
        {"B": outfit, "C": travel},
        {
            "B": [_item("M1", "B", "decision", "navy", 2)],
            "C": [_item("M2", "C", "fact", "Lisbon hotel", 3)],
        },
    )
    notation_b = expose_bound_thread(
        port,
        workstream_id="B",
        referent_id="B.loop1",
        selected_loop="color",
        query="navy color",
    )
    assert notation_b is not None
    assert notation_b.tier == "L1"
    assert "navy" in notation_b.decisions or any("navy" in f for f in notation_b.facts)
    blob = notation_b.to_expose_text()
    assert "Lisbon" not in blob

    notation_c = expose_bound_thread(
        port, workstream_id="C", referent_id="C.loop1", query="Lisbon hotel",
    )
    assert notation_c is not None
    assert "Lisbon hotel" in notation_c.facts or "Lisbon" in notation_c.to_expose_text()
    assert "navy" not in " ".join(notation_c.decisions)


def test_engine_uses_port_path_for_package():
    reg = InMemoryRegistry()
    b = make_task("B", "outfit", "outfit", ["color"], ["dress"])
    c = make_task("C", "travel", "trip", ["hotel"], ["travel"])
    reg.add(b)
    reg.add(c)
    store = InMemoryMemoryStore(conversation_id="x")
    w = MemoryWriter(store, reg)
    w.commit([
        MemoryPatch(kind="decision", text="navy", source_turn=1, workstream_id="B", slot="color"),
        MemoryPatch(kind="fact", text="Lisbon hotel", source_turn=2, workstream_id="C"),
    ], turn=2)
    eng = Engine(MockLLM(), reg, memory_store=store)
    assert isinstance(eng.memory_port, InProcessMemoryPort)
    pkg, _expose = eng._make_package(b, "B.loop1", "color", "what color navy?", [b, c])
    body = " ".join(pkg.active_decisions + pkg.relevant_facts + pkg.active_constraints)
    assert "navy" in body
    assert "Lisbon" not in body
