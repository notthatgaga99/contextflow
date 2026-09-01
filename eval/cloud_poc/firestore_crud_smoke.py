"""Real Firestore CRUD smoke via FirestoreMemoryStore (ADC). No FakeFirestore."""

from __future__ import annotations

import json
import os
import sys
import uuid

from app.memory.firestore_store import FirestoreMemoryStore
from app.memory.registry import InMemoryRegistry
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from tests.conftest import make_task


def _store(cid: str) -> FirestoreMemoryStore:
    return FirestoreMemoryStore(
        cid,
        project=os.getenv("GCP_PROJECT", "contextflow-506414"),
        database=os.getenv("CF_FIRESTORE_DATABASE", "contextflow-poc"),
    )


def run() -> dict:
    suffix = uuid.uuid4().hex[:8]
    a_id = f"poc-crud-a-{suffix}"
    b_id = f"poc-crud-b-{suffix}"
    results: dict = {"conversation_a": a_id, "conversation_b": b_id, "checks": []}

    def check(name: str, ok: bool, detail: str = ""):
        results["checks"].append({"name": name, "ok": ok, "detail": detail})

    # A writes
    reg_a = InMemoryRegistry()
    reg_a.add(make_task("B", "outfit", "outfit", ["color"], ["dress"]))
    store_a = _store(a_id)
    w_a = MemoryWriter(store_a, reg_a)
    r1 = w_a.commit([
        MemoryPatch(kind="decision", text="black", source_turn=1,
                    workstream_id="B", slot="color", conversation_id=a_id),
    ], turn=1)
    check("a_write", r1.ok, str(r1.errors))
    r2 = w_a.commit([
        MemoryPatch(kind="decision", text="navy", source_turn=2,
                    workstream_id="B", slot="color", conversation_id=a_id),
    ], turn=2)
    check("a_supersede", r2.ok)
    old = [i for i in store_a.historical("B") if i.status == "superseded"]
    check("a_superseded_history", len(old) == 1 and old[0].text == "black")
    check("a_current_navy", store_a.asserted("B")[0].text == "navy")

    # B writes
    reg_b = InMemoryRegistry()
    reg_b.add(make_task("C", "deploy", "deploy", ["docker"], ["ci"]))
    store_b = _store(b_id)
    w_b = MemoryWriter(store_b, reg_b)
    r3 = w_b.commit([
        MemoryPatch(kind="fact", text="docker ci fail", source_turn=1,
                    workstream_id="C", conversation_id=b_id),
    ], turn=1)
    check("b_write", r3.ok)

    # Isolation
    check("a_no_b_leak", all("docker" not in i.text for i in store_a.all()))
    check("b_no_a_leak", all("navy" not in i.text for i in store_b.all()))

    # Idempotent retry
    v = store_a.namespace_version()
    r4 = w_a.commit([
        MemoryPatch(kind="decision", text="navy", source_turn=2,
                    workstream_id="B", slot="color", conversation_id=a_id),
    ], turn=2)
    check("a_idempotent", r4.ok and store_a.namespace_version() == v)

    # Fresh read (simulate restart)
    store_a2 = _store(a_id)
    check("a_restart_read", store_a2.asserted("B")[0].text == "navy")
    check("a_restart_history", any(i.status == "superseded" for i in store_a2.historical("B")))

    results["ok"] = all(c["ok"] for c in results["checks"])
    return results


def main() -> int:
    os.environ.setdefault("GCP_PROJECT", "contextflow-506414")
    os.environ.setdefault("CF_FIRESTORE_DATABASE", "contextflow-poc")
    out = run()
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
