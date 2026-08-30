"""Product path on the existing ABCD fixture. Not a new synthetic world."""

from app.context.compiler import ContextCompiler
from app.config import SETTINGS
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.extractor import ExtractRequest, MockMemoryExtractor
from app.memory.registry import InMemoryRegistry
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from app.models.task import Task, TaskAnchor
from app.turn_pipeline import run_turn
from eval.memory_lifecycle.fixture import EXTRACT_SCRIPTS, LLM_SCRIPTS, PRODUCT_USER_TURNS
from eval.memory_lifecycle.run import make_registry


def _world(conversation_id="product"):
    reg = make_registry()
    store = InMemoryMemoryStore(conversation_id=conversation_id)
    writer = MemoryWriter(store, reg)
    llm = MockLLM(LLM_SCRIPTS)
    eng = Engine(llm, reg, SETTINGS, memory_store=store)
    ext = MockMemoryExtractor(EXTRACT_SCRIPTS)
    return reg, store, writer, eng, ext


def _replay():
    reg, store, writer, eng, ext = _world()
    snapshots = {}
    for turn, msg, _do in PRODUCT_USER_TURNS:
        pipe = run_turn(
            eng, writer, ext,
            conversation_id="product", message=msg, turn=turn,
        )
        snapshots[turn] = pipe
    return reg, store, snapshots


def test_extractor_does_not_select_working_context():
    ext = MockMemoryExtractor(EXTRACT_SCRIPTS)
    out = ext.extract(ExtractRequest(message="JWT still returns 401 after refresh.", source_turn=1))
    assert hasattr(out, "patches")
    assert not hasattr(out, "task_id")
    assert not hasattr(out, "selected_referent")


def test_product_path_returns_and_correction():
    reg, store, snaps = _replay()
    compiler = ContextCompiler()
    b7 = snaps[7].turn
    assert b7.task_id == "B"
    rendered7 = compiler.render(b7.package)
    assert "black" in rendered7.lower()
    assert "Lisbon" not in rendered7 and "APA" not in rendered7

    a8 = snaps[8].turn
    assert a8.task_id == "A"
    rendered8 = compiler.render(a8.package)
    assert "401" in rendered8
    assert "15 minutes" in rendered8.lower() or "15" in rendered8
    assert "Lisbon" not in rendered8 and "navy" not in rendered8.lower()

    b9 = snaps[9].turn
    assert b9.task_id == "B"
    rendered9 = compiler.render(b9.package)
    assert "navy" in rendered9.lower()
    assert "formal" in rendered9.lower()
    assert "evening" in rendered9.lower()
    assert "Lisbon" not in rendered9
    color = next(i for i in store.asserted("B") if i.slot == "color")
    assert color.text == "navy"
    black = next(i for i in store.historical("B") if i.slot == "color" and i.text == "black")
    assert black.status == "superseded"
    assert "black" not in " ".join(
        i.text for i in store.asserted("B") if i.slot == "color"
    )

    b10 = snaps[10].turn
    assert b10.task_id == "B"
    rendered10 = compiler.render(b10.package)
    assert "navy" in rendered10.lower()
    assert "Lisbon" not in rendered10

    assert any(i.workstream_id == "C" and i.status == "asserted" for i in store.all())
    assert any(i.workstream_id == "D" and i.status == "asserted" for i in store.all())


def test_retry_same_turn_does_not_duplicate():
    reg, store, writer, eng, ext = _world("retry")
    msg = "I need a black dress for a corporate event."
    run_turn(eng, writer, ext, conversation_id="retry", message=msg, turn=3)
    n = len(store.all())
    ver = store.namespace_version()
    w2 = MemoryWriter(store, reg)
    pipe = run_turn(eng, w2, ext, conversation_id="retry", message=msg, turn=3)
    assert pipe.extract.ok
    assert len(store.all()) == n
    assert store.namespace_version() == ver
    colors = [i for i in store.all() if i.slot == "color"]
    assert len(colors) == 1


def test_conversations_namespace_memory():
    a = InMemoryMemoryStore(conversation_id="c-a")
    b = InMemoryMemoryStore(conversation_id="c-b")
    ra, rb = InMemoryRegistry(), InMemoryRegistry()
    ra.add(Task(id="A", title="a", retrieval_cues=["jwt"],
                anchor=TaskAnchor(goal="auth", open_loops=["401"])))
    rb.add(Task(id="A", title="a", retrieval_cues=["jwt"],
                anchor=TaskAnchor(goal="auth", open_loops=["401"])))
    MemoryWriter(a, ra).commit([
        MemoryPatch(kind="fact", text="401", source_turn=1, workstream_id="A",
                    conversation_id="c-a"),
    ], turn=1)
    MemoryWriter(b, rb).commit([
        MemoryPatch(kind="fact", text="other", source_turn=1, workstream_id="A",
                    conversation_id="c-b"),
    ], turn=1)
    assert all(i.conversation_id == "c-a" for i in a.all())
    assert all(i.conversation_id == "c-b" for i in b.all())
    assert [i.text for i in a.asserted()] != [i.text for i in b.asserted()]
