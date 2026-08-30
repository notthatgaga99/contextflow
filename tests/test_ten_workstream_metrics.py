"""Metric semantics for ten-workstream eval. Does not touch routing."""

from eval.ten_workstream.metrics import (
    candidate_miss,
    critical_thin_context,
    package_absent_because_clarify,
    policy_match,
    referent_match,
    score_probe_row,
    task_match,
    wrong_act,
)
from eval.ten_workstream.load import load_fixture, load_probes
from eval.ten_workstream.run import replay


def test_task_match_true_referent_match_false():
    assert task_match(gold_task="A", selected_task="A", acted=True) is True
    assert referent_match(
        gold_ref="A.loop1", selected_ref="A.loop2", acted=True, gold_task="A",
    ) is False


def test_clarify_policy_correct_without_package():
    assert policy_match(gold_policy="CLARIFY", acted=False) is True
    assert package_absent_because_clarify(acted=False, has_package=False) is True
    row = score_probe_row(
        gold_task=None, gold_ref=None, gold_policy="CLARIFY",
        selected_task=None, selected_ref=None, acted=False,
        open_task_ids=list("ABCDEFGHIJ"),
        cf_sufficient_no_leak=None, thin_context=False, has_package=False,
        contamination=[], supersession_ok=True, persist_ok=True,
    )
    assert row["policy_match"] is True
    assert row["working_context_sufficient"] is None
    assert row["critical_thin_context"] is False
    assert row["package_absent_because_clarify"] is True
    assert row["failure_layer"] == "NONE"


def test_correct_task_missing_state_is_critical_thin():
    assert critical_thin_context(
        acted=True, gold_task="E", selected_task="E",
        thin_context=True, gold_policy="ACT",
    ) is True
    row = score_probe_row(
        gold_task="E", gold_ref="E.loop1", gold_policy="ACT",
        selected_task="E", selected_ref="E.loop1", acted=True,
        open_task_ids=["E"], cf_sufficient_no_leak=False, thin_context=True,
        has_package=True, contamination=[], supersession_ok=True, persist_ok=True,
    )
    assert row["task_match"] is True
    assert row["critical_thin_context"] is True
    assert row["failure_layer"] == "RECONSTRUCTION"


def test_candidate_miss_distinct_from_resolver_miss():
    assert candidate_miss(gold_task="A", open_task_ids=["B", "C"]) is True
    # Gold present but wrong selection → not candidate_miss; wrong_act
    assert candidate_miss(gold_task="A", open_task_ids=["A", "B"]) is False
    assert wrong_act(
        gold_task="A", selected_task="B", acted=True, gold_policy="ACT",
    ) is True
    row = score_probe_row(
        gold_task="A", gold_ref="A.loop1", gold_policy="ACT",
        selected_task="B", selected_ref="B.loop1", acted=True,
        open_task_ids=["A", "B"], cf_sufficient_no_leak=True, thin_context=False,
        has_package=True, contamination=[], supersession_ok=True, persist_ok=True,
    )
    assert row["candidate_miss"] is False
    assert row["wrong_act"] is True
    assert row["failure_layer"] == "RESOLUTION"


def test_contamination_distinct_from_omission():
    thin = score_probe_row(
        gold_task="C", gold_ref="C.loop1", gold_policy="ACT",
        selected_task="C", selected_ref="C.loop1", acted=True,
        open_task_ids=["C"], cf_sufficient_no_leak=False, thin_context=True,
        has_package=True, contamination=[], supersession_ok=True, persist_ok=True,
    )
    leak = score_probe_row(
        gold_task="C", gold_ref="C.loop1", gold_policy="ACT",
        selected_task="C", selected_ref="C.loop1", acted=True,
        open_task_ids=["C"], cf_sufficient_no_leak=False, thin_context=False,
        has_package=True, contamination=["navy"], supersession_ok=True, persist_ok=True,
    )
    assert thin["critical_thin_context"] is True
    assert thin["contamination"] is False
    assert leak["contamination"] is True
    assert leak["failure_layer"] == "CONTAMINATION"


def test_supersession_and_persistence_independent():
    row = score_probe_row(
        gold_task="E", gold_ref="E.loop1", gold_policy="ACT",
        selected_task="E", selected_ref="E.loop1", acted=True,
        open_task_ids=["E"], cf_sufficient_no_leak=True, thin_context=False,
        has_package=True, contamination=[], supersession_ok=False, persist_ok=True,
    )
    assert row["supersession_correct"] is False
    assert row["persistence_correct"] is True
    row2 = score_probe_row(
        gold_task="E", gold_ref="E.loop1", gold_policy="ACT",
        selected_task="E", selected_ref="E.loop1", acted=True,
        open_task_ids=["E"], cf_sufficient_no_leak=True, thin_context=False,
        has_package=True, contamination=[], supersession_ok=True, persist_ok=False,
    )
    assert row2["supersession_correct"] is True
    assert row2["persistence_correct"] is False


def test_clarify_gold_act_is_policy_not_wrong_act():
    assert wrong_act(
        gold_task=None, selected_task="A", acted=True, gold_policy="CLARIFY",
    ) is False
    row = score_probe_row(
        gold_task=None, gold_ref=None, gold_policy="CLARIFY",
        selected_task="A", selected_ref="A.loop1", acted=True,
        open_task_ids=list("ABCDEFGHIJ"),
        cf_sufficient_no_leak=True, thin_context=False, has_package=True,
        contamination=[], supersession_ok=True, persist_ok=True,
    )
    assert row["wrong_act"] is False
    assert row["policy_match"] is False
    assert row["failure_layer"] == "POLICY"


def test_frozen_p07_p09_p18_interpretations_unchanged():
    payload, _, _ = replay()
    by = {p["probe_id"]: p for p in payload["probes"]}
    assert by["p07_return_b_superseded_builder"]["gold_policy"] == "ACT"
    assert by["p09_the_other_one"]["gold_policy"] == "CLARIFY"
    assert by["p18_uncertain_navy_probe"]["gold_policy"] == "ACT"
    # Frozen outcomes: document as-is (not retune targets)
    assert by["p07_return_b_superseded_builder"]["act_or_clarify"] == "CLARIFY"
    assert by["p09_the_other_one"]["act_or_clarify"] == "ACT"
    assert by["p18_uncertain_navy_probe"]["act_or_clarify"] == "CLARIFY"


def test_probe_gold_not_in_fixture_runtime_scripts():
    fx = load_fixture()
    probes = load_probes()
    blob = json_dumps_lower(fx)
    for p in probes:
        # gold policy labels must not appear as runtime script keys
        assert "gold_task_id" not in fx
        assert "needed_state" not in str(fx.get("extract_scripts", {}))
        assert "should_not_carry" not in blob
        assert "competing_similar" not in blob
    # probes file itself is scoring-only
    assert all("gold_policy" in p for p in probes)


def json_dumps_lower(obj) -> str:
    import json
    return json.dumps(obj).lower()


def test_new_j_return_and_clarify_probes_present():
    ids = {p["id"] for p in load_probes()}
    assert "p19_return_j_trivia" in ids
    assert "p20_ordinal_out_of_range_clarify" in ids
    fx = load_fixture()
    assert len(fx["turns"]) == 52
    payload, _, _ = replay()
    by = {p["probe_id"]: p for p in payload["probes"]}
    assert by["p19_return_j_trivia"]["intended_workstream"] == "J"
    assert by["p20_ordinal_out_of_range_clarify"]["gold_policy"] == "CLARIFY"
    # p20 should CLARIFY under frozen ordinal conflict when successful
    assert by["p20_ordinal_out_of_range_clarify"]["policy_match"] is True
    assert by["p20_ordinal_out_of_range_clarify"]["package_absent_because_clarify"] is True
    assert by["p19_return_j_trivia"]["task_match"] is True
    assert payload["summary"]["idempotency_correct"] is True
    assert payload["summary"]["isolation_correct"] is True
    assert payload["summary"]["wrong_act"] == 0
    assert payload["summary"]["vertex_calls"] == 0
