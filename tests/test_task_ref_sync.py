"""task_id / pred_ref must stay on one workstream after topic-LLM soft prior."""

from __future__ import annotations

import pytest

from app.domain import Transition
from app.engine import Engine, TurnPlan
from app.models.proposal import GateDecision
from app.memory.registry import InMemoryRegistry
from tests.conftest import make_task

pytestmark = pytest.mark.trust


class _WrongDiscernLLM:
    """Topic discern soft-prior that points at the wrong card."""

    def propose(self, prompt, schema=None):
        # Soft proposal used by gate + discern; always nudge toward C.
        if schema and "decision" in (schema.get("properties") or {}):
            return {
                "decision": "SWITCH",
                "task_id": "C",
                "confidence": 0.9,
                "rationale": "wrong",
            }
        return {
            "task_id": "C",
            "is_new_task": False,
            "confidence": 0.4,
            "updates": {},
            "suggested_answer": None,
        }

    def generate(self, prompt: str) -> str:
        return "ok"

    def embed(self, texts):
        return [[0.0] * 8 for _ in texts]


def test_reconcile_prefers_referent_owner_when_winner_matches():
    reg = InMemoryRegistry()
    for tid, title, cues in (
        ("A", "JWT auth", ["jwt", "401"]),
        ("B", "outfit", ["dress", "navy"]),
        ("C", "Lisbon", ["lisbon", "hotel"]),
    ):
        reg.add(make_task(tid, title, title, [f"{title} loop"], cues))
    eng = Engine(llm=_WrongDiscernLLM(), registry=reg)
    open_tasks = reg.open_tasks()
    plan = TurnPlan(
        Transition.SWITCH,
        "C",
        "A",
        "A.loop1",
        {},
        GateDecision(
            transition=Transition.SWITCH,
            task_id="C",
            top=0.5,
            margin=0.2,
            gating_quantity=0.2,
        ),
        open_tasks,
        [],
    )
    out = eng._reconcile_task_ref(plan, {"winner_id": "A", "delta_I": 1.0}, active_id="C")
    assert out.task_id == "A"
    assert out.pred_ref == "A.loop1"
    assert out.evidence.get("task_ref_sync") == "sync_task_to_referent_owner"


def test_topic_llm_cannot_skip_discrimination(monkeypatch):
    """With CF_TOPIC_LLM=1, wrong discern must still lose to I-channel on JWT return."""
    monkeypatch.setenv("CF_TOPIC_LLM", "1")
    monkeypatch.setenv("CF_USE_VERTEX", "0")
    reg = InMemoryRegistry()
    reg.add(make_task(
        "A", "JWT auth refresh 401", "fix JWT",
        ["401 after refresh"], ["jwt", "auth", "401", "token"],
    ))
    reg.add(make_task(
        "B", "corporate outfit", "outfit",
        ["pick color"], ["outfit", "dress", "formal"],
    ))
    reg.add(make_task(
        "C", "Lisbon trip", "trip",
        ["hotel parking"], ["lisbon", "hotel", "parking"],
    ))
    reg.mark_active("C", 1)
    reg.set_last_selected_referent("C.loop1")
    eng = Engine(llm=_WrongDiscernLLM(), registry=reg)
    plan = eng.plan_turn("go back to the JWT", turn=2)
    assert plan.task_id == "A"
    assert plan.pred_ref is None or str(plan.pred_ref).startswith("A")
