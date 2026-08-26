from app.config import SETTINGS
from app.domain import Transition
from app.engine import Engine
from app.llm.mock import MockLLM
from tests.conftest import scripted


def _engine(registry, llm):
    return Engine(llm, registry, SETTINGS)


def test_continue(registry):
    registry.mark_active("A", 5)
    llm = scripted(**{"still 401": {"task_id": "A", "is_new_task": False, "confidence": 0.9}})
    r = _engine(registry, llm).handle_turn("still 401 error on the token", 6)
    assert r.transition == Transition.CONTINUE and r.task_id == "A"


def test_switch(registry):
    registry.mark_active("B", 4)
    registry.mark_active("A", 5)
    llm = scripted(**{"macbook": {"task_id": "B", "is_new_task": False, "confidence": 0.95}})
    r = _engine(registry, llm).handle_turn("about the macbook vs xps laptop", 6)
    assert r.transition == Transition.SWITCH and r.task_id == "B"


def test_return_explicit(registry):
    registry.mark_active("C", 10)
    llm = scripted(**{"authentication": {"task_id": "A", "is_new_task": False, "confidence": 0.9}})
    r = _engine(registry, llm).handle_turn("fix that authentication thing", 12)
    assert r.task_id == "A" and r.transition in (Transition.RETURN, Transition.SWITCH)


def test_vague_return_uses_proposal(registry):
    registry.mark_active("C", 10)
    llm = scripted(**{"fix that": {"task_id": "A", "is_new_task": False, "confidence": 0.85}})
    r = _engine(registry, llm).handle_turn("fix that", 12)
    assert r.task_id == "A"


def test_new(registry):
    registry.mark_active("A", 5)
    llm = scripted(**{"poem": {"task_id": None, "is_new_task": True, "confidence": 0.95}})
    r = _engine(registry, llm).handle_turn("help me write a poem about rain", 6)
    assert r.transition == Transition.NEW


def test_ambiguous_clarifies(registry):
    registry.mark_active("A", 5)
    llm = scripted(**{"hmm": {"task_id": None, "is_new_task": False, "confidence": 0.15}})
    r = _engine(registry, llm).handle_turn("hmm ok", 6)
    assert r.transition == Transition.CLARIFY and r.clarify_question


def test_threshold_low_top_clarifies(registry):
    # no active task, all cold, far-future turn -> raw scores tiny -> TAU triggers
    llm = scripted(**{"zzz": {"task_id": None, "is_new_task": False, "confidence": 0.05}})
    r = _engine(registry, llm).handle_turn("zzz", 50)
    assert r.transition == Transition.CLARIFY
