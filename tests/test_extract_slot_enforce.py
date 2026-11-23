"""Extract Write-quality: focus attach + known-slot enforce (stub LLM, no live Vertex)."""

from __future__ import annotations

import json

import pytest

from app.config import SETTINGS
from app.domain import Transition
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.extractor import (
    ExtractRequest,
    LlmMemoryExtractor,
    apply_extraction,
    infer_known_slots,
)
from app.memory.registry import InMemoryRegistry
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from app.turn_pipeline import run_turn
from tests.conftest import make_task

pytestmark = pytest.mark.integration


def _auth_outfit():
    reg = InMemoryRegistry()
    reg.add(make_task(
        "A", "JWT auth", "fix JWT", ["401 after refresh"], ["jwt", "auth", "ttl", "aud"],
    ))
    reg.add(make_task(
        "B", "corporate outfit", "choose outfit", ["pick dress color"], ["outfit", "dress", "color"],
    ))
    store = InMemoryMemoryStore(conversation_id="ex-slot")
    writer = MemoryWriter(store, reg)
    return reg, store, writer


def test_infer_known_slots_ttl_aud_builder_mem_color():
    row = {"kind": "decision", "text": "refresh TTL should be five minutes", "workstream_id": "A"}
    infer_known_slots(row, message="set refresh TTL to 5 minutes on auth")
    assert row["slot"] == "ttl"
    assert "5" in row["text"]

    row = {"kind": "constraint", "text": "audience claim", "workstream_id": "A"}
    infer_known_slots(row, message="aud claim must be api.internal for JWT")
    assert row["slot"] == "aud"
    assert row["text"] == "api.internal"

    row = {"kind": "decision", "text": "use debian slim builder image", "workstream_id": "C"}
    infer_known_slots(row, message="Use debian slim as the builder image")
    assert row["slot"] == "builder"
    assert row["text"] == "debian slim"

    row = {"kind": "decision", "text": "memory limit", "workstream_id": "C"}
    infer_known_slots(row, message="set mem to 4Gi for the job")
    assert row["slot"] == "mem"
    assert "4" in row["text"]

    row = {"kind": "decision", "text": "prefer navy for the dress", "workstream_id": "B"}
    infer_known_slots(row, message="navy dress for evening")
    assert row["slot"] == "color"
    assert row["text"] == "navy"


def test_llm_unslotted_row_gets_slot_and_supersedes():
    reg, store, writer = _auth_outfit()
    writer.commit([
        MemoryPatch(
            kind="decision", text="15 minutes", source_turn=1,
            workstream_id="A", slot="ttl",
        ),
    ], turn=1)

    class JsonLLM:
        def generate(self, prompt):
            return json.dumps([{
                "kind": "decision",
                "text": "refresh TTL should be five minutes now",
                "workstream_id": "A",
            }])

    ext = LlmMemoryExtractor(JsonLLM())
    out = apply_extraction(ext, writer, ExtractRequest(
        message="set refresh TTL to 5 minutes on the auth service",
        source_turn=2,
        open_workstreams=reg.open_tasks(),
        asserted_items=store.asserted(),
        focus_workstream_id="A",
    ))
    assert out.ok
    asserted = store.asserted("A")
    ttl = [i for i in asserted if i.slot == "ttl"]
    assert len(ttl) == 1
    assert "5" in ttl[0].text
    hist = [i for i in store.historical("A") if i.slot == "ttl"]
    assert hist and hist[0].status == "superseded"


def test_focus_attaches_unanchored_llm_row():
    reg, store, writer = _auth_outfit()

    class JsonLLM:
        def generate(self, prompt):
            return json.dumps([{
                "kind": "constraint",
                "text": "aud must be api.internal",
                # deliberately omit workstream_id
            }])

    ext = LlmMemoryExtractor(JsonLLM())
    out = apply_extraction(ext, writer, ExtractRequest(
        message="also check aud claim must be api.internal for JWT",
        source_turn=3,
        open_workstreams=reg.open_tasks(),
        asserted_items=store.asserted(),
        focus_workstream_id="A",
    ))
    assert out.ok
    items = store.asserted("A")
    assert items
    assert any(i.slot == "aud" for i in items)
    assert not store.asserted("B")


def test_recall_only_still_abstains():
    reg, store, writer = _auth_outfit()

    class Boom:
        def generate(self, prompt):
            raise AssertionError("recall must not call LLM")

    ext = LlmMemoryExtractor(Boom())
    out = apply_extraction(ext, writer, ExtractRequest(
        message="Final check: JWT 401 after refresh — TTL 5 minutes and aud api.internal",
        source_turn=4,
        open_workstreams=reg.open_tasks(),
        asserted_items=store.asserted(),
        focus_workstream_id="A",
    ))
    assert out.ok
    assert store.asserted("A") == []


def test_pipeline_passes_focus_on_continue():
    reg, store, writer = _auth_outfit()
    reg.mark_active("A", 1)
    eng = Engine(
        MockLLM({
            "TTL": {"task_id": "A", "is_new_task": False, "confidence": 0.9},
        }),
        reg,
        SETTINGS,
        memory_store=store,
    )

    class JsonLLM:
        def generate(self, prompt):
            return json.dumps([{
                "kind": "decision",
                "text": "TTL to 5 minutes",
                # no workstream_id — must attach via pipeline focus
            }])

    pipe = run_turn(
        eng, writer, LlmMemoryExtractor(JsonLLM()),
        conversation_id="ex-slot",
        message="TTL looks wrong — set refresh TTL to 5 minutes on the auth service",
        turn=2,
    )
    assert pipe.turn.transition != Transition.CLARIFY
    assert pipe.turn.task_id == "A"
    ttl = [i for i in store.asserted("A") if i.slot == "ttl"]
    assert ttl and "5" in ttl[0].text


def test_deterministic_ttl_slot_correction():
    reg, store, writer = _auth_outfit()
    writer.commit([
        MemoryPatch(
            kind="decision", text="15 minutes", source_turn=1,
            workstream_id="A", slot="ttl",
        ),
    ], turn=1)
    ext = LlmMemoryExtractor(object())  # should not be called — deterministic path
    # Avoid Boom: deterministic should short-circuit before LLM.
    class Boom:
        def generate(self, prompt):
            raise AssertionError("deterministic ttl should not call LLM")
        def propose(self, *a, **k):
            raise AssertionError("deterministic ttl should not call LLM")

    ext = LlmMemoryExtractor(Boom())
    out = apply_extraction(ext, writer, ExtractRequest(
        message="set refresh TTL to 5 minutes on the auth service",
        source_turn=2,
        open_workstreams=reg.open_tasks(),
        asserted_items=store.asserted(),
        focus_workstream_id="A",
    ))
    assert out.ok
    ttl = [i for i in store.asserted("A") if i.slot == "ttl"]
    assert len(ttl) == 1 and "5" in ttl[0].text
