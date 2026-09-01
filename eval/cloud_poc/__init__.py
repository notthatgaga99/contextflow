"""Cloud durability POC — plan and deterministic harness helpers.

Do not fake restart persistence with the in-memory backend.
Do not execute live Vertex or deploy from this module in Phase 8.
"""

from __future__ import annotations

from app.context.working_set import WorkingContextBuilder
from app.memory.fake_firestore import FakeFirestoreClient
from app.memory.firestore_store import FirestoreMemoryStore
from app.memory.registry import InMemoryRegistry
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from tests.conftest import make_task

DURABILITY_PLAN = """
Request 1 — conversation A:
  Commit decision memory (e.g. outfit color=navy) via MemoryWriter.

Request 2 — conversation B:
  Commit unrelated memory. Must not appear in A's store.

Restart / redeploy simulation:
  Drop in-process Engine/store objects. Keep the same Firestore (or FakeFirestore)
  client/data. Construct new FirestoreMemoryStore(conversation_id=A).

Request 3 — return to A:
  A's asserted memory survives.
  B's memory does not leak into A.
  Superseded history (if any) remains in historical().
  WorkingContextBuilder projection excludes superseded/stale state.
"""

# Explicit Vertex smoke ceiling — DO NOT RUN in Phase 8 without approval.
VERTEX_SMOKE_COST_CEILING_USD = 1.0
VERTEX_SMOKE_CMD = (
    "CF_USE_VERTEX=1 CF_LLM_EXTRACT=1 CF_MEMORY_BACKEND=firestore "
    "GCP_PROJECT=$GCP_PROJECT "
    "python -m eval.cloud_poc.vertex_smoke --max-usd 1.0"
)


def simulate_restart_roundtrip() -> dict:
    """Deterministic durability proof using FakeFirestore (no GCP)."""
    client = FakeFirestoreClient()
    reg_a = InMemoryRegistry()
    reg_a.add(make_task("B", "outfit", "outfit", ["color"], ["dress"]))
    store_a = FirestoreMemoryStore("conv-A", client=client)
    writer_a = MemoryWriter(store_a, reg_a)
    writer_a.commit([
        MemoryPatch(kind="decision", text="navy", source_turn=1,
                    workstream_id="B", slot="color"),
    ], turn=1)
    writer_a.commit([
        MemoryPatch(kind="decision", text="black", source_turn=2,
                    workstream_id="B", slot="color"),
    ], turn=2)

    reg_b = InMemoryRegistry()
    reg_b.add(make_task("X", "travel", "travel", ["city"], ["flight"]))
    store_b = FirestoreMemoryStore("conv-B", client=client)
    MemoryWriter(store_b, reg_b).commit([
        MemoryPatch(kind="fact", text="paris", source_turn=1,
                    workstream_id="X", slot="city"),
    ], turn=1)

    # Restart: new store instances, same client persistence.
    store_a2 = FirestoreMemoryStore("conv-A", client=client)
    store_b2 = FirestoreMemoryStore("conv-B", client=client)
    asserted_a = store_a2.asserted("B")
    hist_a = [i for i in store_a2.historical("B") if i.status == "superseded"]
    leak = [i for i in store_a2.all() if "paris" in (i.text or "").lower()]
    task = reg_a.get("B")
    proj = WorkingContextBuilder().project(task, "B.loop1", store_a2, [task])
    return {
        "a_current": [i.text for i in asserted_a],
        "a_superseded": [i.text for i in hist_a],
        "b_current": [i.text for i in store_b2.asserted("X")],
        "leak_into_a": leak,
        "projection_decisions": list(proj.decisions),
        "excluded": list(proj.excluded_workstreams),
    }
