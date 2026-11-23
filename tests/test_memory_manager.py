"""ContextFlow memory planes: STM / LTM / procedural / relevant (our RB-WSR)."""

from app.context.working_memory_switch import assemble_bound_memory, expose_bound_thread
from app.context.working_set import WorkingContextBuilder, WorkingSetLimits
from app.memory.cold_search import ColdHit, filter_hits_for_l1, hits_from_items
from app.memory.manager import MemoryManager
from app.memory.planes import (
    LongTermKind,
    MemoryPlane,
    design_notes,
    long_term_kind_for,
    plane_catalog,
    plane_for_kind,
)
from app.memory.port import DictMemoryPort
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryItem, MemoryPatch
from app.memory.registry import InMemoryRegistry
from app.memory.store import InMemoryMemoryStore
from tests.conftest import make_task


def _item(iid, wid, kind, text, turn=1, status="asserted", slot=None):
    return MemoryItem(
        id=iid, kind=kind, text=text, source_turn=turn,
        workstream_id=wid, status=status, proposer="system", slot=slot,
    )


def test_plane_design_is_ours():
    assert plane_for_kind("procedure") == MemoryPlane.PROCEDURAL
    assert long_term_kind_for("fact") == LongTermKind.SEMANTIC
    assert long_term_kind_for("event") == LongTermKind.EPISODIC
    assert plane_catalog()
    notes = design_notes()
    assert "RB-WSR" in notes["product"]
    assert notes["not_a_clone_of"]
    assert "learned_from" in notes


def test_manager_separates_planes_howto_only_procedural_l1():
    outfit = make_task("B", "outfit", "corporate outfit", ["color"], ["dress"])
    travel = make_task("C", "travel", "plan trip", ["hotel"], ["lisbon"])
    items_b = [
        _item("M1", "B", "decision", "navy peplum", 2),
        _item("M2", "B", "fact", "hosting Thursday", 3),
        _item("M3", "B", "procedure", "try jacket then shoes then bag", 4),
        _item("M4", "B", "event", "fitting on Monday", 5),
        _item("M9", "B", "fact", "navy peplum top for corporate hosting", 20),
    ]
    items_b.extend(_item(f"N{i}", "B", "fact", f"noise-{i}", turn=i) for i in range(5, 14))
    port = DictMemoryPort(
        {"B": outfit, "C": travel},
        {
            "B": items_b,
            "C": [_item("T1", "C", "fact", "Lisbon hotel near station", 3)],
        },
    )
    mgr = MemoryManager(
        port,
        builder=WorkingContextBuilder(limits=WorkingSetLimits(max_facts=3, max_procedures=4)),
    )
    bundle = mgr.assemble(
        workstream_id="B",
        referent_id="B.loop1",
        selected_loop="color",
        query="navy peplum for hosting",
        enrich_cold=True,
    )
    assert bundle is not None and bundle.short_term is not None
    assert bundle.short_term.plane == "short_term"

    # L1 procedural = how-tos only (not goal:/loop: dumps)
    assert any("try jacket" in p for p in bundle.short_term.procedures)
    assert not any(p.startswith("goal:") for p in bundle.short_term.procedures)
    # Diagnostics still keep control plane
    assert any(t.startswith("goal:") for t in bundle.procedural.texts)
    assert bundle.long_term.meta.get("episodic_count", 0) >= 1
    assert bundle.long_term.meta.get("semantic_count", 0) >= 1

    blob = bundle.short_term.to_expose_text()
    assert "Lisbon" not in blob
    assert "GOAL:" in blob
    assert any("navy" in f.lower() for f in bundle.short_term.facts)
    # Provenance includes cold ids when enrich lands
    assert bundle.short_term.memory_item_ids
    assert bundle.diagnostics["generate_plane"] == "short_term"


def test_filter_superseded_when_slot_asserted():
    hits = [
        ColdHit(text="old navy", status="superseded", slot="color", item_id="old", score=0.9),
        ColdHit(text="black now", status="asserted", slot="color", item_id="new", score=0.8),
        ColdHit(text="loose note", status="superseded", slot=None, item_id="x", score=0.5),
    ]
    kept = filter_hits_for_l1(hits, asserted_slots={"color"}, prefer_asserted_over_superseded=True)
    texts = {h.text for h in kept}
    assert "old navy" not in texts
    assert "black now" in texts
    assert "loose note" in texts  # unslotted superseded still allowed


def test_cold_hit_carries_item_id():
    items = [_item("M99", "B", "fact", "navy peplum top", 20)]
    hits = hits_from_items("navy peplum", items, limit=3, workstream_id="B")
    assert hits and hits[0].item_id == "M99"


def test_writer_accepts_procedure_kind():
    reg = InMemoryRegistry()
    store = InMemoryMemoryStore()
    reg.add(make_task("B", "outfit", "corporate outfit", ["color"], ["dress"]))
    w = MemoryWriter(store, reg)
    cr = w.commit([
        MemoryPatch(
            kind="procedure",
            text="confirm size then order then tailor",
            source_turn=1,
            workstream_id="B",
            proposer="extractor",
        ),
    ], turn=1)
    assert cr.ok, cr.errors
    assert any(i.kind == "procedure" for i in store.asserted("B"))


def test_assemble_bound_memory_matches_expose():
    outfit = make_task("B", "outfit", "corporate outfit", ["color"], ["dress"])
    port = DictMemoryPort(
        {"B": outfit},
        {"B": [_item("M1", "B", "fact", "navy", 1)]},
    )
    bundle = assemble_bound_memory(port, workstream_id="B", query="navy")
    notation = expose_bound_thread(port, workstream_id="B", query="navy")
    assert bundle is not None and notation is not None
    assert notation.facts == bundle.short_term.facts
