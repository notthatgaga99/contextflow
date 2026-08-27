"""Judge-mode demo construction. No network."""

from eval.demo import TURNS, run_script


def test_demo_is_offline_mock():
    frames = run_script()
    assert 15 <= len(frames) <= 25
    assert len(frames) == len(TURNS)
    assert all(f["provider"] == "MockLLM" and f["network"] is False for f in frames)


def test_new_is_engine_state_not_harness_insert():
    frames = run_script()
    created = [f["engine_created_task"]["id"] for f in frames if f["engine_created_task"]]
    assert created == ["A", "B", "C", "D"]
    assert all(f["gate"]["transition"] == "NEW" for f in frames if f["engine_created_task"])
    assert frames[0]["state"]["active_task_id"] == "A"
    assert frames[0]["answer_context"]["task_id"] == "A"


def test_auth_has_two_loops_in_naive_dump():
    frames = run_script()
    late = frames[-1]
    auth = next(t for t in late["naive_full_history"] if t["id"] == "A")
    assert len(auth["loops"]) == 2


def test_fix_that_uses_clocks_not_llm_lure():
    frames = run_script()
    first, second = [f for f in frames if f["message"] == "fix that"]
    assert first["llm_proposal"]["task_id"] == "A"
    assert first["highlight"] is True
    assert first["resolution"]["kind"] == "deictic"
    assert first["resolution"]["predicted_task_id"] == "C"
    assert first["resolution"]["predicted_referent_id"] == "C.loop1"
    assert first["gate"]["transition"] in ("CONTINUE", "SWITCH", "RETURN")
    assert first["answer_context"]["included_loop_ids"] == ["C.loop1"]
    assert "JWT" not in " ".join(first["answer_context"]["open_loops"])

    assert second["resolution"]["predicted_task_id"] == "A"
    assert second["resolution"]["predicted_referent_id"] == "A.loop1"
    assert "Docker" not in " ".join(second["answer_context"]["open_loops"])


def test_correction_is_not_the_llm_guess():
    frames = run_script()
    corr = next(f for f in frames if f["message"] == "no, the other one")
    assert corr["resolution"]["kind"] == "correction"
    assert corr["llm_proposal"]["task_id"] == "A"
    assert corr["resolution"]["predicted_task_id"] != "A"


def test_naive_history_is_bulky_answer_context_is_selected_loop():
    frames = run_script()
    lure = next(f for f in frames if f["highlight"])
    ids = {t["id"] for t in lure["naive_full_history"]}
    assert ids == {"A", "B", "C", "D"}
    assert len(lure["answer_context"]["included_loop_ids"]) == 1


def test_proposal_is_not_silently_the_decision():
    frames = run_script()
    first = next(f for f in frames if f["highlight"])
    assert first["llm_proposal"]["task_id"] != first["resolution"]["predicted_task_id"]
    assert first["final_decision"] == first["gate"]["transition"]
