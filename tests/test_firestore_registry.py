"""FirestoreRegistry tests via FakeFirestoreClient."""

from __future__ import annotations

import pytest

from app.config import SETTINGS
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.fake_firestore import FakeFirestoreClient
from app.memory.firestore_registry import FirestoreRegistry
from app.memory.firestore_store import FirestoreMemoryStore
from app.memory.registry import InMemoryRegistry
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from app.models.task import Task, TaskAnchor
from tests.conftest import make_task


def _reg(cid: str, client: FakeFirestoreClient) -> FirestoreRegistry:
    return FirestoreRegistry(cid, client=client)


def test_create_and_load_workstream():
    client = FakeFirestoreClient()
    reg = _reg("c1", client)
    reg.add(Task(id="E", title="outfit", status="paused",
                 anchor=TaskAnchor(goal="pick outfit", open_loops=["color"]),
                 retrieval_cues=["dress"]))
    reg2 = _reg("c1", client)
    t = reg2.get("E")
    assert t is not None and t.title == "outfit"


def test_update_and_close_workstream():
    client = FakeFirestoreClient()
    reg = _reg("c1", client)
    reg.add(Task(id="A", title="auth", status="paused",
                 anchor=TaskAnchor(goal="fix auth", open_loops=["401"])))
    reg.mark_active("A", 5)
    reg2 = _reg("c1", client)
    assert reg2.get("A").status == "active"
    assert reg2.get("A").last_active_turn == 5
    reg2.mark_abandoned("A")
    reg3 = _reg("c1", client)
    assert reg3.get("A").status == "abandoned"


def test_conversation_isolation():
    client = FakeFirestoreClient()
    a = _reg("conv-a", client)
    b = _reg("conv-b", client)
    a.add(Task(id="E", title="outfit", anchor=TaskAnchor(goal="o", open_loops=["c"])))
    b.add(Task(id="B", title="docker", anchor=TaskAnchor(goal="d", open_loops=["x"])))
    assert _reg("conv-a", client).get("E") is not None
    assert _reg("conv-a", client).get("B") is None
    assert _reg("conv-b", client).get("B") is not None


def test_idempotent_add():
    client = FakeFirestoreClient()
    reg = _reg("c1", client)
    t = Task(id="E", title="outfit", anchor=TaskAnchor(goal="o", open_loops=["c"]))
    reg.add(t)
    reg.add(t)
    assert len(reg.all()) == 1


def test_memory_workstream_consistency():
    client = FakeFirestoreClient()
    cid = "consist"
    reg = _reg(cid, client)
    reg.add(make_task("E", "outfit", "outfit", ["color"], ["dress"]))
    store = FirestoreMemoryStore(cid, client=client)
    w = MemoryWriter(store, reg)
    r = w.commit([MemoryPatch(kind="decision", text="navy", source_turn=1,
                              workstream_id="E", slot="color")], turn=1)
    assert r.ok
    assert not w.commit([MemoryPatch(kind="fact", text="x", source_turn=1,
                                     workstream_id="Z")], turn=2).ok


def test_restart_reconstruction():
    client = FakeFirestoreClient()
    cid = "restart"
    reg = _reg(cid, client)
    reg.add(make_task("E", "outfit", "outfit", ["color"], ["dress"]))
    store = FirestoreMemoryStore(cid, client=client)
    w = MemoryWriter(store, reg)
    w.commit([MemoryPatch(kind="decision", text="black", source_turn=1,
                          workstream_id="E", slot="color")], turn=1)
    w.commit([MemoryPatch(kind="decision", text="navy", source_turn=2,
                          workstream_id="E", slot="color")], turn=2)
    reg.mark_active("E", 2)
    # Simulate new process
    reg2 = _reg(cid, client)
    store2 = FirestoreMemoryStore(cid, client=client)
    assert reg2.get("E").title == "outfit"
    assert store2.asserted("E")[0].text == "navy"
    assert any(i.status == "superseded" for i in store2.historical("E"))


def test_generate_does_not_mutate_registry():
    client = FakeFirestoreClient()
    cid = "gen"
    reg = _reg(cid, client)
    reg.add(make_task("E", "outfit", "outfit", ["color"], ["dress"]))
    store = FirestoreMemoryStore(cid, client=client)
    n = len(reg.all())
    llm = MockLLM({"outfit": {"task_id": "E", "is_new_task": False, "confidence": 0.9}})
    eng = Engine(llm, reg, SETTINGS, memory_store=store)
    eng.handle_turn("outfit question", 1)
    reg2 = _reg(cid, client)
    assert len(reg2.all()) == n


def test_inmemory_unchanged():
    reg = InMemoryRegistry()
    reg.add(Task(id="A", title="a", anchor=TaskAnchor(goal="g", open_loops=["l"])))
    assert reg.get("A") is not None
