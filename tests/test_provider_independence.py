from app.config import SETTINGS
from app.router.gate import decide
from app.models.proposal import Candidate
from app.engine import Engine
from app.llm.mock import MockLLM
from tests.conftest import scripted


def test_gate_is_pure():
    cands = [Candidate("A", 0.6, 0.6, {}), Candidate("B", 0.2, 0.2, {}),
             Candidate("__NEW__", 0.2, 0.2, {})]
    d1 = decide(cands, None, "A", SETTINGS, statuses={"A": "active"}, turns_since={"A": 0})
    d2 = decide(cands, None, "A", SETTINGS, statuses={"A": "active"}, turns_since={"A": 0})
    assert d1.transition == d2.transition and d1.task_id == d2.task_id
    assert d1.margin == d2.margin


def test_two_llms_same_script_same_decision(registry):
    import copy
    script = {"fix that authentication thing": {"task_id": "A", "is_new_task": False, "confidence": 0.9}}
    r1 = copy.deepcopy(registry); r1.mark_active("C", 10)
    r2 = copy.deepcopy(registry); r2.mark_active("C", 10)
    d1 = Engine(MockLLM(scripted=script), r1, SETTINGS).handle_turn("fix that authentication thing", 12)
    d2 = Engine(MockLLM(scripted=script), r2, SETTINGS).handle_turn("fix that authentication thing", 12)
    assert d1.transition == d2.transition and d1.task_id == d2.task_id
