"""Unit tests for the isolated referent probe. Production engine is not modified."""

from eval.referent_controlled import (
    classify_utterance,
    mock_wrong_llm,
    run_suite,
    scenarios,
    system_b_resolve,
)


def test_a1_a2_cards_identical():
    by_id = {s.scenario_id: s for s in scenarios()}
    a1, a2 = by_id["A1"], by_id["A2"]
    assert [(t.task_id, t.goal, [(lp.loop_id, lp.text) for lp in t.loops])
            for t in a1.tasks] == [
        (t.task_id, t.goal, [(lp.loop_id, lp.text) for lp in t.loops])
        for t in a2.tasks
    ]
    assert a1.message == a2.message == "fix that"
    assert a1.mentions != a2.mentions


def test_classify():
    assert classify_utterance("fix that") == "deictic"
    assert classify_utterance("fix that authentication thing") == "explicit"
    assert classify_utterance("the 401") == "explicit"
    assert classify_utterance("no, the other one") == "correction"


def test_b_swaps_a1_a2():
    a1 = next(s for s in scenarios() if s.scenario_id == "A1")
    a2 = next(s for s in scenarios() if s.scenario_id == "A2")
    r1 = system_b_resolve(a1, llm_task="A")
    r2 = system_b_resolve(a2, llm_task="A")
    assert (r1.pred_task, r1.pred_referent) == ("B", "B.loop1")
    assert (r2.pred_task, r2.pred_referent) == ("A", "A.loop1")
    assert r1.pred_referent != r2.pred_referent


def test_b_swaps_loop_foreground():
    b1 = next(s for s in scenarios() if s.scenario_id == "B1")
    b2 = next(s for s in scenarios() if s.scenario_id == "B2")
    r1 = system_b_resolve(b1, llm_task="A")
    r2 = system_b_resolve(b2, llm_task="A")
    assert r1.pred_referent == "A.loop1"
    assert r2.pred_referent == "A.loop2"


def test_explicit_overrides_foreground_and_wrong_llm():
    c1 = next(s for s in scenarios() if s.scenario_id == "C1")
    f1 = next(s for s in scenarios() if s.scenario_id == "F1")
    c2 = next(s for s in scenarios() if s.scenario_id == "C2")
    assert system_b_resolve(c1, "B").pred_referent == "A.loop1"
    assert system_b_resolve(f1, "B").pred_referent == "A.loop1"
    assert system_b_resolve(c2, "A").pred_referent == "B.loop1"


def test_mock_suite_runs():
    rows = run_suite(mock_wrong_llm(), "mock")
    assert len(rows) == 20
    b = [r for r in rows if r["system"] == "B_referent"]
    a1 = next(r for r in b if r["scenario_id"] == "A1")
    a2 = next(r for r in b if r["scenario_id"] == "A2")
    assert a1["joint_correct"] and a2["joint_correct"]
    assert a1["pred_referent"] != a2["pred_referent"]
