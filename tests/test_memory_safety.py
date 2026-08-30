from app.config import SETTINGS
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.registry import InMemoryRegistry
from app.memory.sessions import ConversationStore
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from tests.conftest import make_task


def test_generate_does_not_mutate_memory():
    reg = InMemoryRegistry()
    reg.add(make_task("B", "outfit", "outfit", ["color"], ["outfit"]))
    store = InMemoryMemoryStore()
    MemoryWriter(store, reg).commit([
        MemoryPatch(kind="decision", text="navy", source_turn=1, workstream_id="B", slot="color"),
    ], turn=1)
    n = store.namespace_version()
    ids = {i.id for i in store.all()}
    llm = MockLLM({"back to the outfit": {
        "task_id": "B", "is_new_task": False, "confidence": 0.5,
    }})
    eng = Engine(llm, reg, SETTINGS, memory_store=store)
    eng.handle_turn("back to the outfit", 5)
    assert store.namespace_version() == n
    assert {i.id for i in store.all()} == ids


def test_conversation_memory_namespaces_isolated():
    cs = ConversationStore(MockLLM())
    ea, eb = cs.engine("ca"), cs.engine("cb")
    ea.reg.add(make_task("B", "outfit", "outfit", ["color"], ["dress"]))
    eb.reg.add(make_task("B", "outfit", "outfit", ["color"], ["dress"]))
    MemoryWriter(cs.memory_store("ca"), ea.reg).commit([
        MemoryPatch(kind="decision", text="navy", source_turn=1, workstream_id="B", slot="color"),
    ], turn=1)
    assert cs.memory_store("ca").asserted("B")
    assert cs.memory_store("cb").all() == []
    assert "navy" in cs.memory_store("ca").asserted("B")[0].text
