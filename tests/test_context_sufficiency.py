"""Construction and scoring checks for the sufficiency experiment. No Ollama."""

from app.context.compiler import ContextCompiler
from eval.context_sufficiency import (
    EchoSelectedMock,
    FULL_TASK,
    REFERENT_COMPACT,
    compile_mode,
    probe_prompt,
    route,
    score_answer,
    scenarios,
)


def test_ten_scenarios_defined():
    ids = [s.scenario_id for s in scenarios()]
    assert len(ids) == 10
    assert len(set(ids)) == 10


def test_score_answer_checkable():
    sc = next(s for s in scenarios() if s.scenario_id == "S8_explicit_401")
    assert score_answer("The issue is HTTP 401 after refresh.", sc)["answer_correct"]
    assert not score_answer("The expired access token in Redis.", sc)["answer_correct"]


def test_compact_drops_unrelated_loops():
    sc = next(s for s in scenarios() if s.scenario_id == "S2_resume_loop2")
    res, cards = route(sc)
    assert (res.predicted_task_id, res.predicted_referent_id) == ("A", "A.loop2")
    compact = compile_mode(cards, sc, res.predicted_task_id, res.predicted_referent_id, "split")
    full = compile_mode(cards, sc, res.predicted_task_id, res.predicted_referent_id, "full")
    assert compact.context_mode == REFERENT_COMPACT
    assert compact.included_loop_ids == ["A.loop2"]
    assert full.context_mode == FULL_TASK
    assert set(full.included_loop_ids) == {"A.loop1", "A.loop2", "A.loop3"}


def test_mock_echoes_selected_loop():
    mock = EchoSelectedMock()
    sc = next(s for s in scenarios() if s.scenario_id == "S1_resume_loop1")
    res, cards = route(sc)
    pkg = compile_mode(cards, sc, res.predicted_task_id, res.predicted_referent_id, "split")
    ans = mock.generate(probe_prompt(ContextCompiler().render(pkg), sc.probe))
    assert "401" in ans
