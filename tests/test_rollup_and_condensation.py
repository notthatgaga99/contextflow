from app.context.working_set import WorkingContextBuilder, WorkingSetLimits
from app.memory.registry import InMemoryRegistry
from app.memory.rollup import build_conversation_rollup
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from tests.conftest import make_task


def test_working_set_caps_and_prefers_recent_slotted():
    reg = InMemoryRegistry()
    reg.add(make_task("B", "outfit", "outfit", ["color"], ["dress"]))
    store = InMemoryMemoryStore(conversation_id="c1")
    w = MemoryWriter(store, reg)
    patches = [
        MemoryPatch(kind="fact", text=f"old-{i}", source_turn=i, workstream_id="B")
        for i in range(1, 12)
    ]
    patches.append(
        MemoryPatch(
            kind="fact", text="slotted-late", source_turn=5, workstream_id="B", slot="key",
        )
    )
    w.commit(patches, turn=12)
    proj = WorkingContextBuilder(
        limits=WorkingSetLimits(max_facts=3, max_decisions=6, max_constraints=6, max_entities=8),
    ).project(reg.get("B"), None, store)
    assert len(proj.facts) == 3
    # Highest turns win; slotted at turn 5 beats unslotted at turn 5 if tied — here top are 11,10,9
    assert "old-11" in proj.facts
    assert "old-1" not in proj.facts


def test_rollup_from_asserted_not_sibling_bleed():
    reg = InMemoryRegistry()
    b = make_task("B", "outfit", "corporate outfit", ["choose color"], ["outfit"])
    c = make_task("C", "travel", "plan trip", ["book hotel"], ["travel"])
    reg.add(b)
    reg.add(c)
    reg.mark_active("B", 2)
    reg.mark_active("C", 3)
    store = InMemoryMemoryStore(conversation_id="demo")
    w = MemoryWriter(store, reg)
    w.commit([
        MemoryPatch(kind="decision", text="navy", source_turn=2, workstream_id="B", slot="color"),
        MemoryPatch(kind="fact", text="Lisbon hotel", source_turn=3, workstream_id="C"),
    ], turn=3)
    roll = build_conversation_rollup(reg, store, conversation_id="demo")
    assert roll.open_count == 2
    assert "outfit" in roll.blurb.lower() or "travel" in roll.blurb.lower()
    by_id = {w.workstream_id: w for w in roll.workstreams}
    assert by_id["B"].decisions == ["navy"]
    assert "Lisbon" not in " ".join(by_id["B"].facts)
    assert "Lisbon hotel" in by_id["C"].facts
    d = roll.to_dict()
    assert d["source"] == "asserted_memory"
    assert len(d["workstreams"]) == 2
