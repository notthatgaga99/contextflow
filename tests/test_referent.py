"""Production referent resolution. Diagnostic metrics are not benchmark claims."""

from app.config import SETTINGS
from app.domain import Transition
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.registry import InMemoryRegistry
from app.models.task import Task, TaskAnchor
from app.router.referent import classify_utterance, resolution_metrics
from tests.conftest import scripted


def _task(tid: str, title: str, goal: str, loops: list[str], cues: list[str]) -> Task:
    return Task(
        id=tid, title=title, status="paused",
        retrieval_cues=list(cues),
        anchor=TaskAnchor(goal=goal, open_loops=list(loops)),
    )


def jwt_frontend() -> InMemoryRegistry:
    r = InMemoryRegistry()
    r.add(_task("A", "jwt auth", "JWT authentication",
                ["HTTP 401 after token refresh"],
                ["jwt", "401", "authentication", "token"]))
    r.add(_task("B", "frontend", "Frontend rendering",
                ["component renders twice"],
                ["react", "render", "component"]))
    return r


def two_loops_a() -> InMemoryRegistry:
    r = InMemoryRegistry()
    r.add(_task("A", "auth", "fix authentication",
                ["HTTP 401 after refresh", "expired access token"],
                ["jwt", "401", "authentication", "token"]))
    r.add(_task("B", "frontend", "Frontend rendering",
                ["component renders twice"],
                ["react", "render"]))
    return r


def jwt_oauth() -> InMemoryRegistry:
    r = InMemoryRegistry()
    r.add(_task("JWT", "jwt", "fix JWT authentication",
                ["JWT token not verified"], ["jwt", "token", "authentication"]))
    r.add(_task("OAuth", "oauth", "fix OAuth authentication",
                ["OAuth redirect fails"], ["oauth", "redirect", "authentication"]))
    return r


def seed_mentions(reg: InMemoryRegistry, mentions: list[tuple[str, str, int]]) -> None:
    for task_id, loop_id, turn in mentions:
        reg.record_mention(task_id, turn, loop_id)
        reg.mark_active(task_id, turn)


def _wrong() -> MockLLM:
    return MockLLM({
        "authentication thing": {
            "task_id": "B", "is_new_task": False, "confidence": 0.92,
            "referent": None, "rationale": "wrong-C1",
        },
        "renders twice": {
            "task_id": "A", "is_new_task": False, "confidence": 0.92,
            "referent": None, "rationale": "wrong-C2",
        },
        "other one": {
            "task_id": "A", "is_new_task": False, "confidence": 0.92,
            "referent": None, "rationale": "wrong-D1",
        },
        "the 401": {
            "task_id": "B", "is_new_task": False, "confidence": 0.92,
            "referent": None, "rationale": "wrong-F1",
        },
        "fix that": {
            "task_id": "A", "is_new_task": False, "confidence": 0.95,
            "referent": None, "rationale": "always-A",
        },
    })


def _run(reg: InMemoryRegistry, msg: str, turn: int, llm=None):
    return Engine(llm or _wrong(), reg, SETTINGS).handle_turn(msg, turn)


def _diag(r, gold_task: str, gold_ref: str, llm_task: str | None) -> dict:
    decision = "CLARIFY" if r.transition == Transition.CLARIFY else r.transition.value
    return resolution_metrics(
        gold_task, gold_ref, r.predicted_task_id, r.predicted_referent_id,
        decision, llm_task,
    )


def test_classify_production():
    assert classify_utterance("fix that") == "deictic"
    assert classify_utterance("change it") == "deictic"
    assert classify_utterance("try this") == "deictic"
    assert classify_utterance("fix that authentication thing") == "explicit"
    assert classify_utterance("the 401") == "explicit"
    assert classify_utterance("no, the other one") == "correction"


def test_a1_a2_must_differ():
    r1 = jwt_frontend()
    seed_mentions(r1, [("A", "A.loop1", 1), ("A", "A.loop1", 2), ("B", "B.loop1", 3)])
    a1 = _run(r1, "fix that", 4)
    r2 = jwt_frontend()
    seed_mentions(r2, [("A", "A.loop1", 1), ("B", "B.loop1", 2), ("A", "A.loop1", 3)])
    a2 = _run(r2, "fix that", 4)
    assert (a1.predicted_task_id, a1.predicted_referent_id) == ("B", "B.loop1")
    assert (a2.predicted_task_id, a2.predicted_referent_id) == ("A", "A.loop1")
    assert a1.predicted_referent_id != a2.predicted_referent_id
    d1 = _diag(a1, "B", "B.loop1", "A")
    d2 = _diag(a2, "A", "A.loop1", "A")
    assert d1["joint_resolution_correct"] and d2["joint_resolution_correct"]
    assert d1["llm_error"] and d1["llm_error_recovered"]


def test_b1_b2_must_differ():
    r1 = two_loops_a()
    seed_mentions(r1, [("A", "A.loop1", 1), ("B", "B.loop1", 2), ("A", "A.loop1", 3)])
    b1 = _run(r1, "fix that", 4)
    r2 = two_loops_a()
    seed_mentions(r2, [("A", "A.loop1", 1), ("B", "B.loop1", 2), ("A", "A.loop2", 3)])
    b2 = _run(r2, "fix that", 4)
    assert b1.predicted_referent_id == "A.loop1"
    assert b2.predicted_referent_id == "A.loop2"
    assert b1.predicted_task_id == b2.predicted_task_id == "A"
    assert b1.predicted_referent_id != b2.predicted_referent_id


def test_c1_lexical_overrides_foreground():
    reg = jwt_frontend()
    seed_mentions(reg, [("A", "A.loop1", 1), ("A", "A.loop1", 2), ("B", "B.loop1", 3)])
    r = _run(reg, "fix that authentication thing", 4)
    assert (r.predicted_task_id, r.predicted_referent_id) == ("A", "A.loop1")
    assert r.transition != Transition.CLARIFY


def test_c2_lexical_overrides_active_task():
    reg = jwt_frontend()
    seed_mentions(reg, [("A", "A.loop1", 1), ("B", "B.loop1", 2), ("A", "A.loop1", 3)])
    r = _run(reg, "the component still renders twice", 4)
    assert (r.predicted_task_id, r.predicted_referent_id) == ("B", "B.loop1")
    assert r.predicted_task_id != "A"


def test_d1_correction_other_one():
    reg = jwt_frontend()
    seed_mentions(reg, [("A", "A.loop1", 1), ("B", "B.loop1", 2), ("A", "A.loop1", 3)])
    reg.set_last_selected_referent("A.loop1")
    r = _run(reg, "no, the other one", 4)
    assert (r.predicted_task_id, r.predicted_referent_id) == ("B", "B.loop1")


def test_e1_oauth_foreground_deictic():
    reg = jwt_oauth()
    seed_mentions(reg, [("JWT", "JWT.loop1", 1), ("OAuth", "OAuth.loop1", 2)])
    r = _run(reg, "fix that", 3)
    assert (r.predicted_task_id, r.predicted_referent_id) == ("OAuth", "OAuth.loop1")


def test_f1_the_401():
    reg = two_loops_a()
    seed_mentions(reg, [("A", "A.loop2", 1), ("B", "B.loop1", 2), ("A", "A.loop2", 3)])
    r = _run(reg, "the 401", 4)
    assert (r.predicted_task_id, r.predicted_referent_id) == ("A", "A.loop1")
    d = _diag(r, "A", "A.loop1", "B")
    assert d["llm_error_recovered"]


def test_invalid_llm_task_id_fail_closed_deictic():
    reg = jwt_frontend()
    seed_mentions(reg, [("A", "A.loop1", 1), ("B", "B.loop1", 2)])
    llm = scripted(**{"fix that": {"task_id": "Z", "is_new_task": False, "confidence": 0.99}})
    r = _run(reg, "fix that", 3, llm)
    assert r.predicted_task_id == "B"
    assert r.transition != Transition.CLARIFY


def test_invalid_llm_id_no_mentions_clarifies():
    reg = jwt_frontend()
    llm = scripted(**{"fix that": {"task_id": "Z", "is_new_task": False, "confidence": 0.99}})
    r = _run(reg, "fix that", 3, llm)
    assert r.transition == Transition.CLARIFY


def test_wrong_high_confidence_llm_on_deictic():
    reg = jwt_frontend()
    seed_mentions(reg, [("A", "A.loop1", 1), ("A", "A.loop1", 2), ("B", "B.loop1", 3)])
    r = _run(reg, "fix that", 4)
    assert r.predicted_task_id == "B"
    assert r.resolution_evidence.get("llm_task_soft") == "A"


def test_task_and_referent_may_differ():
    reg = two_loops_a()
    seed_mentions(reg, [("A", "A.loop1", 1), ("B", "B.loop1", 2), ("A", "A.loop2", 3)])
    r = _run(reg, "fix that", 4)
    assert r.predicted_task_id == "A"
    assert r.predicted_referent_id == "A.loop2"


def test_mention_clocks_update_on_act():
    reg = jwt_frontend()
    seed_mentions(reg, [("A", "A.loop1", 1), ("B", "B.loop1", 2)])
    assert reg.get("B").mention_turn == 2
    _run(reg, "fix that authentication thing", 3)
    assert reg.get("A").mention_turn == 3
    assert reg.get("B").mention_turn == 2
    assert reg.last_selected_referent() == "A.loop1"


def test_old_foreground_does_not_persist():
    reg = jwt_frontend()
    seed_mentions(reg, [("A", "A.loop1", 1), ("B", "B.loop1", 2)])
    r1 = _run(reg, "fix that", 3)
    assert r1.predicted_referent_id == "B.loop1"
    r2 = _run(reg, "fix that", 4)
    assert r2.predicted_referent_id == "B.loop1"
    # newer mention of A must beat stale B
    reg.record_mention("A", 5, "A.loop1")
    r3 = _run(reg, "fix that", 6)
    assert r3.predicted_referent_id == "A.loop1"


def test_compiler_receives_selected_loop():
    reg = two_loops_a()
    seed_mentions(reg, [("A", "A.loop1", 1), ("A", "A.loop2", 2)])
    r = _run(reg, "fix that", 3)
    assert r.package is not None
    assert r.package.selected_referent_id == "A.loop2"
    assert r.package.selected_open_loop == "expired access token"
    rendered = Engine(_wrong(), reg, SETTINGS).compiler.render(r.package)
    assert "SELECTED LOOP:" in rendered
    assert "expired access token" in rendered
    assert "HTTP 401 after refresh" not in rendered
    assert r.package.included_loop_ids == ["A.loop2"]


def test_generate_does_not_mutate_mention():
    class Spy(MockLLM):
        def generate(self, prompt: str) -> str:
            return "I think you mean task B actually"

    reg = jwt_frontend()
    seed_mentions(reg, [("A", "A.loop1", 1), ("B", "B.loop1", 2)])
    before_a, before_b = reg.get("A").mention_turn, reg.get("B").mention_turn
    r = Engine(Spy({"fix that": {
        "task_id": "A", "is_new_task": False, "confidence": 0.95,
        "referent": None, "rationale": "x",
    }}), reg, SETTINGS).handle_turn("fix that", 3)
    assert r.predicted_task_id == "B"
    assert reg.get("A").mention_turn == before_a
    assert reg.get("B").mention_turn == 3
