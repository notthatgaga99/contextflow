"""Tests for dynamic NEW workstream pipeline (no seed, no live GCP)."""

from app.domain import Transition
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.extractor import ExtractRequest, LlmMemoryExtractor, apply_extraction
from app.memory.registry import InMemoryRegistry
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.turn_pipeline import run_turn


def _engine_and_writer():
    reg = InMemoryRegistry()
    store = InMemoryMemoryStore(conversation_id="dyn")
    writer = MemoryWriter(store, reg)
    llm = MockLLM({
        "espresso": {"task_id": None, "is_new_task": True, "confidence": 0.95},
        "leaking": {"task_id": None, "is_new_task": True, "confidence": 0.95},
        "espresso machine": {"task_id": "T1", "is_new_task": False, "confidence": 0.9},
        "tax": {"task_id": None, "is_new_task": True, "confidence": 0.9},
        "return": {"task_id": "T1", "is_new_task": False, "confidence": 0.85},
    })
    eng = Engine(llm, reg, memory_store=store)
    return eng, writer, store


class _ExtractLLM:
    def _patches_for(self, prompt: str) -> list[dict]:
        import json
        import re

        if "espresso" not in prompt.lower() and "leaking" not in prompt.lower():
            return []
        ws = "T1"
        if "FOCUS WORKSTREAM" in prompt:
            m = re.search(r"FOCUS WORKSTREAM.*?:\s*(\S+)", prompt)
            if m:
                ws = m.group(1)
        return [{
            "kind": "fact",
            "text": "espresso machine keeps leaking",
            "workstream_id": ws,
        }]

    def generate(self, prompt):
        import json

        patches = self._patches_for(prompt)
        if not patches:
            return json.dumps([])
        return json.dumps(patches)

    def embed(self, texts):
        return MockLLM().embed(texts)


def test_new_turn_creates_registry_before_extract():
    eng, writer, store = _engine_and_writer()
    ext = LlmMemoryExtractor(_ExtractLLM())
    pipe = run_turn(
        eng, writer, ext,
        conversation_id="dyn",
        message="I need to figure out why my espresso machine keeps leaking.",
        turn=1,
    )
    assert pipe.turn.transition == Transition.NEW
    assert pipe.turn.task_id == "T1"
    assert eng.reg.get("T1") is not None
    assert any("leaking" in i.text for i in store.asserted("T1"))
    assert pipe.extract_passes == 1


def test_non_new_turn_extract_before_route():
    eng, writer, store = _engine_and_writer()
    run_turn(
        eng, writer, LlmMemoryExtractor(_ExtractLLM()),
        conversation_id="dyn",
        message="I need to figure out why my espresso machine keeps leaking.",
        turn=1,
    )
    ext = LlmMemoryExtractor(_ExtractLLM())
    pipe = run_turn(
        eng, writer, ext,
        conversation_id="dyn",
        message="Back to the espresso machine — is it still leaking?",
        turn=2,
    )
    assert pipe.turn.transition in (Transition.CONTINUE, Transition.RETURN, Transition.SWITCH)
    assert pipe.turn.task_id == "T1"


def test_new_only_one_registry_card():
    eng, writer, _store = _engine_and_writer()
    ext = LlmMemoryExtractor(_ExtractLLM())
    run_turn(
        eng, writer, ext,
        conversation_id="dyn",
        message="I need to figure out why my espresso machine keeps leaking.",
        turn=1,
    )
    assert len([t for t in eng.reg.all() if t.id == "T1"]) == 1


def test_plan_turn_has_no_side_effects():
    eng, writer, store = _engine_and_writer()
    n0 = store.namespace_version()
    cards0 = len(eng.reg.all())
    plan = eng.plan_turn("brand new tax filing problem", 1)
    assert plan.transition == Transition.NEW
    assert store.namespace_version() == n0
    assert len(eng.reg.all()) == cards0
