"""Paired-catalog checks for the task-count stress experiment. No Ollama."""

from eval.task_count_scale import (
    TARGET_ID,
    gold_for,
    iter_cells,
    message_for,
    task_set,
    target_task,
)


def test_target_identical_across_n_and_family():
    t0 = target_task()
    for n in (1, 2, 3, 5, 8, 10):
        for family in ("LOW", "HIGH"):
            tasks = task_set(n, family)
            assert len(tasks) == n
            tgt = next(t for t in tasks if t.id == TARGET_ID)
            assert tgt.anchor.goal == t0.anchor.goal
            assert tgt.anchor.open_loops == t0.anchor.open_loops


def test_low_high_distractors_differ():
    low = {t.id for t in task_set(10, "LOW") if t.id != TARGET_ID}
    high = {t.id for t in task_set(10, "HIGH") if t.id != TARGET_ID}
    assert low.isdisjoint(high)
    assert len(low) == len(high) == 9


def test_explicit_gold_is_always_target():
    gold_t, gold_r = gold_for("EXPLICIT", "distractor_last", task_set(5, "HIGH"),
                              [("T", "T.loop1", 1), ("H1", "H1.loop1", 2)])
    assert (gold_t, gold_r) == ("T", "T.loop1")
    assert "401" in message_for("EXPLICIT")
    assert message_for("DEICTIC") == "fix that"


def test_grid_covers_requested_n():
    ns = {n for n, _, _, _ in iter_cells()}
    assert ns == {1, 2, 3, 5, 8, 10}
