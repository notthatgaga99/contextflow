"""Answer-context follows the selected referent. Routing is not changed here."""

from app.config import SETTINGS
from app.context.compiler import ContextCompiler
from app.domain import Transition
from app.engine import Engine
from app.memory.registry import InMemoryRegistry
from app.models.context import FULL_TASK, MERGED_COMPACT, REFERENT_COMPACT
from app.models.task import Task, TaskAnchor
from app.llm.mock import MockLLM
from tests.test_referent import _run, jwt_frontend, seed_mentions


def _three_loop_a() -> Task:
    t = Task(
        id="A", title="auth", status="paused",
        retrieval_cues=["jwt", "401", "token", "deploy"],
        anchor=TaskAnchor(
            goal="fix authentication and release",
            open_loops=[
                "JWT 401 after refresh",
                "expired access token",
                "deployment pipeline failing",
            ],
            decisions=["refresh in middleware"],
            constraints=["do not change public API"],
            entities=["JWT middleware"],
        ),
    )
    t.anchor.decisions = ["refresh in middleware"]
    t.anchor.constraints = ["do not change public API"]
    t.anchor.entities = ["JWT middleware"]
    return t


def _reg_three() -> InMemoryRegistry:
    r = InMemoryRegistry()
    r.add(_three_loop_a())
    r.add(Task(
        id="B", title="frontend", status="paused",
        retrieval_cues=["react", "render", "component"],
        anchor=TaskAnchor(goal="Frontend rendering",
                          open_loops=["component renders twice"]),
    ))
    return r


def test_loop1_answer_excludes_unrelated_loops():
    pkg = ContextCompiler().build(
        _three_loop_a(), "split",
        selected_referent_id="A.loop1",
        selected_open_loop="JWT 401 after refresh",
    )
    rendered = ContextCompiler().render(pkg)
    assert pkg.context_mode == REFERENT_COMPACT
    assert pkg.included_loop_ids == ["A.loop1"]
    assert "JWT 401 after refresh" in rendered
    assert "expired access token" not in rendered
    assert "deployment pipeline failing" not in rendered
    assert pkg.task_id == "A"
    assert pkg.selected_referent_id == "A.loop1"


def test_loop2_answer_excludes_unrelated_loops():
    pkg = ContextCompiler().build(
        _three_loop_a(), "split",
        selected_referent_id="A.loop2",
        selected_open_loop="expired access token",
    )
    rendered = ContextCompiler().render(pkg)
    assert pkg.included_loop_ids == ["A.loop2"]
    assert "expired access token" in rendered
    assert "JWT 401 after refresh" not in rendered
    assert "deployment pipeline failing" not in rendered
    assert "refresh in middleware" in rendered


def test_b_referent_package_not_from_active_a():
    reg = jwt_frontend()
    seed_mentions(reg, [("A", "A.loop1", 1), ("A", "A.loop1", 2), ("B", "B.loop1", 3)])
    r = _run(reg, "fix that", 4)
    assert r.predicted_task_id == "B"
    assert r.predicted_referent_id == "B.loop1"
    assert r.package is not None
    assert r.package.task_id == "B"
    assert r.package.included_loop_ids == ["B.loop1"]
    rendered = Engine(MockLLM(), reg, SETTINGS).compiler.render(r.package)
    assert "component renders twice" in rendered
    assert "HTTP 401 after token refresh" not in rendered


def test_task_and_referent_separately_represented():
    pkg = ContextCompiler().build(
        _three_loop_a(), "split",
        selected_referent_id="A.loop2",
        selected_open_loop="expired access token",
    )
    assert pkg.task_id == "A"
    assert pkg.selected_referent_id == "A.loop2"
    assert pkg.task_id != pkg.selected_referent_id
    assert "REFERENT: A.loop2" in ContextCompiler().render(pkg)


def test_no_referent_does_not_invent_a_loop():
    pkg = ContextCompiler().build(_three_loop_a(), "split")
    assert pkg.selected_referent_id is None
    assert pkg.context_mode == FULL_TASK
    assert pkg.included_loop_ids == ["A.loop1", "A.loop2", "A.loop3"]
    rendered = ContextCompiler().render(pkg)
    assert "JWT 401 after refresh" in rendered
    assert "expired access token" in rendered
    assert "deployment pipeline failing" in rendered


def test_invalid_referent_falls_back_without_inventing():
    pkg = ContextCompiler().build(
        _three_loop_a(), "split", selected_referent_id="A.loop99",
    )
    assert pkg.context_mode == FULL_TASK
    assert pkg.included_loop_ids == ["A.loop1", "A.loop2", "A.loop3"]


def test_full_task_keeps_all_loops_even_with_selection():
    pkg = ContextCompiler().build(
        _three_loop_a(), "full",
        selected_referent_id="A.loop2",
        selected_open_loop="expired access token",
    )
    assert pkg.context_mode == FULL_TASK
    assert pkg.included_loop_ids == ["A.loop1", "A.loop2", "A.loop3"]


def test_merged_compact_one_representation():
    pkg = ContextCompiler().build(
        _three_loop_a(), "merged",
        selected_referent_id="A.loop2",
        selected_open_loop="expired access token",
        message="fix that",
        open_tasks=[_three_loop_a()],
    )
    assert pkg.context_mode == MERGED_COMPACT
    assert pkg.decision_tokens == 0
    assert pkg.answer_tokens == pkg.total_context_tokens > 0
    assert pkg.included_loop_ids == ["A.loop2"]
    rendered = ContextCompiler().render(pkg)
    assert "expired access token" in rendered
    assert "JWT 401 after refresh" not in rendered


def test_instrumentation_fields_present():
    pkg = ContextCompiler().build(
        _three_loop_a(), "split",
        selected_referent_id="A.loop1",
        selected_open_loop="JWT 401 after refresh",
        message="the 401",
        open_tasks=[_three_loop_a()],
    )
    assert pkg.decision_context_tokens > 0
    assert pkg.answer_context_tokens > 0
    assert pkg.total_context_tokens == pkg.decision_tokens + pkg.answer_tokens
    log = pkg.to_dict()
    assert log["context_mode"] == REFERENT_COMPACT
    assert log["included_loop_ids"] == ["A.loop1"]


def test_engine_three_loop_compact_on_deictic():
    reg = _reg_three()
    seed_mentions(reg, [("A", "A.loop1", 1), ("A", "A.loop3", 2), ("A", "A.loop2", 3)])
    r = _run(reg, "fix that", 4)
    assert r.transition != Transition.CLARIFY
    assert r.predicted_referent_id == "A.loop2"
    assert r.package.included_loop_ids == ["A.loop2"]
    rendered = Engine(MockLLM(), reg, SETTINGS).compiler.render(r.package)
    assert "expired access token" in rendered
    assert "JWT 401 after refresh" not in rendered
    assert "deployment pipeline failing" not in rendered
