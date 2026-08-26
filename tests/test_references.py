from app.config import SETTINGS
from app.domain import Transition
from app.engine import Engine
from app.router.references import parse_reference
from tests.conftest import scripted


def test_parse_ordinal():
    assert parse_reference("fix 1").kind == "ordinal"
    assert parse_reference("fix 1").value == 1


def test_parse_entity():
    ref = parse_reference("fix the oauth thing")
    assert ref.kind == "entity" and ref.value == "oauth"


def test_parse_pronoun():
    assert parse_reference("fix that").kind == "pronoun"


def test_http_401_is_not_ordinal():
    assert parse_reference("still getting HTTP 401").kind == "none"
    assert parse_reference("still getting 401").kind == "none"


def test_ordinal_conflict_clarifies(registry):
    # Task A has only 1 open loop; "fix 2" is out of range -> conflict -> CLARIFY
    registry.mark_active("A", 5)
    llm = scripted(**{"fix 2": {"task_id": "A", "is_new_task": False, "confidence": 0.9}})
    r = Engine(llm, registry, SETTINGS).handle_turn("fix 2", 6)
    assert r.transition == Transition.CLARIFY
