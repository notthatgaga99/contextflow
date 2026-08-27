"""Construction checks for Gemini validation. Does not call Gemini."""

from eval.gemini_validation import SMOKE_CELLS, estimate, exp2_foregrounds, fail_class
from eval.task_count_scale import iter_cells


def test_scale_cell_count_matches_frozen_grid():
    assert len(list(iter_cells())) == 128
    est = estimate()
    assert est["contextflow_propose_calls"] == 132
    assert est["generate_calls"] == 0
    assert est["embed_calls"] == 0


def test_smoke_is_small():
    assert len(SMOKE_CELLS) == 3


def test_exp2_gold_follows_foreground():
    names = {n: (t, r) for n, t, r in exp2_foregrounds()}
    assert names["target_foreground"][0] == "T"
    assert names["sibling_foreground"][0] == "S"
    assert names["target_active_sibling_fg"][0] == "S"
    assert names["sibling_active_target_fg"][0] == "T"


def test_clarify_gold_is_H_not_automatic_failure():
    row = {
        "pred_task": "T", "gold_task": "T",
        "pred_referent": "T.loop1", "gold_referent": "T.loop1",
        "wrong_action": False, "clarified": True,
        "underspecification": "EXPLICIT", "message": "x",
    }
    assert fail_class(row) == "H"
