"""Critical memory invariants on the ABCD fixture. Routing frozen; memory authority tested."""

from app.context.compiler import ContextCompiler
from app.config import SETTINGS
from app.context.working_set import WorkingContextBuilder
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.extractor import MockMemoryExtractor
from app.memory.registry import InMemoryRegistry
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.turn_pipeline import run_turn
from eval.memory_lifecycle.fixture import EXTRACT_SCRIPTS, LLM_SCRIPTS, PRODUCT_USER_TURNS
from eval.memory_lifecycle.run import make_registry


def _replay():
    reg = make_registry()
    store = InMemoryMemoryStore(conversation_id="invariant")
    writer = MemoryWriter(store, reg)
    eng = Engine(MockLLM(LLM_SCRIPTS), reg, SETTINGS, memory_store=store)
    ext = MockMemoryExtractor(EXTRACT_SCRIPTS)
    snaps = {}
    for turn, msg, _ in PRODUCT_USER_TURNS:
        pipe = run_turn(
            eng, writer, ext,
            conversation_id="invariant", message=msg, turn=turn,
        )
        snaps[turn] = pipe
    return reg, store, writer, snaps


def _b_package(snap):
    pkg = snap.turn.package
    assert pkg is not None
    return pkg


def test_abcd_return_b_carries_navy_formal_evening_excludes_irrelevant():
    reg, store, _writer, snaps = _replay()
    compiler = ContextCompiler()
    builder = WorkingContextBuilder()

    # After navy correction (turn 9) and return B (turn 10)
    b10 = snaps[10]
    assert b10.turn.task_id == "B"
    pkg = _b_package(b10)
    rendered = compiler.render(pkg).lower()

    assert "navy" in rendered
    assert "formal" in rendered
    assert "evening" in rendered
    assert "black" not in rendered
    assert "lisbon" not in rendered
    assert "apa" not in rendered
    assert "401" not in rendered

    proj = builder.project(reg.get("B"), "B.loop1", store, reg.open_tasks())
    assert "navy" in proj.decisions
    assert any("formal" in c for c in proj.constraints)
    assert any("evening" in c for c in proj.constraints)
    assert "black" not in " ".join(proj.decisions).lower()
    assert not any("lisbon" in f.lower() for f in proj.facts)
    assert pkg.memory_item_ids
    for iid in pkg.memory_item_ids:
        item = store.get(iid)
        assert item is not None
        assert item.provenance
        assert item.status == "asserted"


def test_return_b_before_correction_still_has_black_not_navy():
    _, store, _, snaps = _replay()
    b7 = snaps[7]
    assert b7.turn.task_id == "B"
    rendered = ContextCompiler().render(_b_package(b7)).lower()
    assert "black" in rendered
    assert "navy" not in rendered
    assert "lisbon" not in rendered


def test_black_to_navy_supersession_auditable():
    _, store, _, snaps = _replay()
    assert snaps[9].extract.ok
    color_asserted = [i for i in store.asserted("B") if i.slot == "color"]
    assert len(color_asserted) == 1
    assert color_asserted[0].text == "navy"
    black = next(i for i in store.historical("B") if i.slot == "color" and i.text == "black")
    assert black.status == "superseded"
    assert black.superseded_by == color_asserted[0].id
    assert black.provenance


def test_unrelated_workstreams_remain_stored():
    _, store, _, _ = _replay()
    assert any(i.workstream_id == "C" and i.status == "asserted" for i in store.all())
    assert any(i.workstream_id == "D" and i.status == "asserted" for i in store.all())
    assert any(i.workstream_id == "A" and i.status == "asserted" for i in store.all())


def test_working_package_does_not_invent_missing_state():
    reg, store, _, snaps = _replay()
    b7 = snaps[7]
    pkg = _b_package(b7)
    # Before navy correction: no navy in package
    blob = " ".join(
        (pkg.active_decisions or [])
        + (pkg.active_constraints or [])
        + (pkg.relevant_facts or [])
    ).lower()
    assert "navy" not in blob
