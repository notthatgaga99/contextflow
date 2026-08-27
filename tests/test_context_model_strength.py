"""Guards that the model-strength run reuses the frozen sufficiency scenarios."""

from eval.context_model_strength import ANSWER_MODEL, BASELINE_MODEL
from eval.context_sufficiency import scenarios


def test_reuses_same_ten_scenarios():
    ids = [s.scenario_id for s in scenarios()]
    assert ids == [
        "S1_resume_loop1",
        "S2_resume_loop2",
        "S3_resume_loop3",
        "S4_b_while_a_active",
        "S5_similar_oauth_loops",
        "S6_different_entities",
        "S7_deictic_fix_that",
        "S8_explicit_401",
        "S9_single_loop",
        "S10_tempting_keywords",
    ]


def test_answer_model_is_installed_stronger_local():
    assert ANSWER_MODEL == "llama3.1:8b"
    assert BASELINE_MODEL == "qwen2.5:1.5b"
    assert ANSWER_MODEL != BASELINE_MODEL
