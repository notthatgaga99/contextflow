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


def test_vague_deictic_follows_mention_not_llm(registry):
    registry.mark_active("C", 10)
    registry.record_mention("C", 10, "C.loop1")
    llm = scripted(**{"fix that": {"task_id": "A", "is_new_task": False, "confidence": 0.85}})
    r = _engine(registry, llm).handle_turn("fix that", 12)
    assert r.task_id == "C" and r.predicted_referent_id == "C.loop1"


def test_deictic_without_mentions_clarifies(registry):
    registry.mark_active("C", 10)
    llm = scripted(**{"fix that": {"task_id": "A", "is_new_task": False, "confidence": 0.85}})
    r = _engine(registry, llm).handle_turn("fix that", 12)
    assert r.transition == Transition.CLARIFY


def test_new(registry):
    registry.mark_active("A", 5)
    llm = scripted(**{"poem": {"task_id": None, "is_new_task": True, "confidence": 0.95}})
    eng = _engine(registry, llm)
    r = eng.handle_turn("help me write a poem about rain", 6)
    assert r.transition == Transition.NEW
    assert r.task_id is not None
    created = registry.get(r.task_id)
    assert created is not None
    assert created.status == "active"
    assert r.predicted_referent_id == f"{r.task_id}.loop1"
    assert registry.active() is not None and registry.active().id == r.task_id


def test_new_is_resumable_on_later_turn():
    from app.memory.registry import InMemoryRegistry
    reg = InMemoryRegistry()
    llm = scripted(
        **{
            "poem about rain": {"task_id": None, "is_new_task": True, "confidence": 0.95},
            "rain stanza": {"task_id": "T1", "is_new_task": False, "confidence": 0.9},
        }
    )
    eng = Engine(llm, reg, SETTINGS)
    first = eng.handle_turn("help me write a poem about rain", 1)
    assert first.transition == Transition.NEW and first.task_id == "T1"
    second = eng.handle_turn("continue the rain stanza", 2)
    assert second.task_id == "T1"
    assert second.transition in (Transition.CONTINUE, Transition.SWITCH, Transition.RETURN)



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
