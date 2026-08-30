"""POC harness invariants — gold stays evaluator-only; metrics stay layered."""

from __future__ import annotations

import ast
from pathlib import Path

from eval.ten_workstream.answer_usability import classify_usability
from eval.ten_workstream.load import (
    EVALUATOR_ISOLATED_PROBES_PATH,
    load_fixture,
    load_probes,
)
from eval.ten_workstream.metrics import (
    candidate_miss,
    clarify_correct,
    critical_thin_context,
    poc_machine_summary,
    score_probe_row,
    task_match,
    wrong_act,
)
from eval.ten_workstream.poc_harness import run_poc


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def test_no_gold_enters_runtime_app():
    offenders = []
    for path in APP_ROOT.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("eval."):
                    offenders.append(f"{path.name}:{node.module}")
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith("eval"):
                        offenders.append(f"{path.name}:{a.name}")
        if "probes.json" in src or "evaluator_isolated_probes" in src:
            offenders.append(f"{path.name}:probe_path")
        if "held_out_probes" in src:
            offenders.append(f"{path.name}:held_out_probes")
    assert offenders == [], offenders
    fx = load_fixture()
    blob = str(fx.get("extract_scripts")) + str(fx.get("llm_scripts"))
    assert "gold_policy" not in blob
    assert "needed_state" not in blob
    assert "should_not_carry" not in blob


def test_metric_definitions_do_not_touch_routing_config():
    from app.config import SETTINGS
    before = (SETTINGS.TAU, SETTINGS.DELTA, SETTINGS.HYST, SETTINGS.W_LLM)
    score_probe_row(
        gold_task="A", gold_ref="A.loop1", gold_policy="ACT",
        selected_task="A", selected_ref="A.loop1", acted=True,
        open_task_ids=["A"], cf_sufficient_no_leak=True, thin_context=False,
        has_package=True, contamination=[], supersession_ok=True, persist_ok=True,
    )
    assert (SETTINGS.TAU, SETTINGS.DELTA, SETTINGS.HYST, SETTINGS.W_LLM) == before


def test_task_referent_policy_remain_distinct():
    row = score_probe_row(
        gold_task="A", gold_ref="A.loop1", gold_policy="ACT",
        selected_task="A", selected_ref="A.loop2", acted=True,
        open_task_ids=["A"], cf_sufficient_no_leak=True, thin_context=False,
        has_package=True, contamination=[], supersession_ok=True, persist_ok=True,
    )
    assert row["task_match"] is True
    assert row["referent_match"] is False
    assert row["policy_match"] is True
    assert "RESOLUTION" in row["layers"]
    assert "POLICY" in row["layers"]
    assert "PACKAGE_USABILITY" in row["layers"]


def test_clarify_does_not_count_as_thin_context():
    row = score_probe_row(
        gold_task=None, gold_ref=None, gold_policy="CLARIFY",
        selected_task=None, selected_ref=None, acted=False,
        open_task_ids=list("ABCDEFGHIJ"),
        cf_sufficient_no_leak=None, thin_context=True, has_package=False,
        contamination=[], supersession_ok=True, persist_ok=True,
    )
    assert row["critical_thin_context"] is False
    assert row["working_context_sufficient"] is None
    assert row["package_absent_because_clarify"] is True
    assert row["clarify_correct"] is True
    assert clarify_correct(gold_policy="CLARIFY", acted=False) is True


def test_critical_thin_requires_correct_task():
    assert critical_thin_context(
        acted=True, gold_task="E", selected_task="A",
        thin_context=True, gold_policy="ACT",
    ) is False
    assert critical_thin_context(
        acted=True, gold_task="E", selected_task="E",
        thin_context=True, gold_policy="ACT",
    ) is True


def test_contamination_separate_from_missing_state():
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
    assert thin["critical_thin_context"] is True and thin["contamination"] is False
    assert leak["contamination"] is True and leak["failure_layer"] == "CONTAMINATION"
    assert classify_usability(
        {"leaks": ["navy"], "stale_present": [], "missing": {"needed_state": []},
         "sufficient_no_leak": False, "sufficient_for_continuation": True,
         "thin_context": False},
        acted=True, gold_policy="ACT", needed_total=2,
    ) == "contaminated"
    assert classify_usability(
        {"leaks": [], "stale_present": [], "missing": {"needed_state": ["a", "b"]},
         "sufficient_no_leak": False, "sufficient_for_continuation": False,
         "thin_context": True},
        acted=True, gold_policy="ACT", needed_total=2,
    ) == "missing_state"


def test_candidate_miss_separate_from_resolver_miss():
    assert candidate_miss(gold_task="A", open_task_ids=["B"]) is True
    assert candidate_miss(gold_task="A", open_task_ids=["A", "B"]) is False
    assert wrong_act(
        gold_task="A", selected_task="B", acted=True, gold_policy="ACT",
    ) is True
    assert task_match(gold_task="A", selected_task="B", acted=True) is False
    row = score_probe_row(
        gold_task="A", gold_ref="A.loop1", gold_policy="ACT",
        selected_task="B", selected_ref="B.loop1", acted=True,
        open_task_ids=["A", "B"], cf_sufficient_no_leak=True, thin_context=False,
        has_package=True, contamination=[], supersession_ok=True, persist_ok=True,
    )
    assert row["candidate_miss"] is False
    assert row["failure_layer"] == "RESOLUTION"


def test_evaluator_isolated_probes_loadable_and_excluded_from_app():
    iso = load_probes(evaluator_isolated=True)
    assert EVALUATOR_ISOLATED_PROBES_PATH.exists()
    assert len(iso) >= 3
    assert all("gold_policy" in p for p in iso)
    meta = __import__("json").loads(
        EVALUATOR_ISOLATED_PROBES_PATH.read_text(encoding="utf-8")
    )["meta"]
    assert meta.get("statistical_holdout") is False
    assert meta.get("derived_from_primary") is True
    for path in APP_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "evaluator_isolated_probes" not in text
        assert "held_out_probes" not in text


def test_poc_machine_summary_has_required_keys():
    rows = [
        score_probe_row(
            gold_task="A", gold_ref="A.loop1", gold_policy="ACT",
            selected_task="A", selected_ref="A.loop1", acted=True,
            open_task_ids=["A"], cf_sufficient_no_leak=True, thin_context=False,
            has_package=True, contamination=[], supersession_ok=True, persist_ok=True,
            answer_usability="correct_continuation",
        )
    ]
    rows[0]["gold_policy"] = "ACT"
    s = poc_machine_summary(
        rows=rows, number_of_workstreams=10, number_of_turns=52,
        trajectory_return_transitions=33, probe_return_count=8,
        idempotency_correct=True, isolation_correct=True,
    )
    for k in (
        "number_of_workstreams", "number_of_turns",
        "trajectory_return_transitions", "probe_return_count",
        "task_match", "referent_match", "policy_match", "wrong_act",
        "candidate_miss", "working_context_sufficient", "critical_thin_context",
        "contamination", "supersession_correct", "persistence_correct",
        "idempotency_correct", "isolation_correct", "failure_counts_by_layer",
        "RESOLUTION", "POLICY", "MEMORY", "WORKING_CONTEXT", "PACKAGE_USABILITY",
    ):
        assert k in s
    assert "number_of_returns" not in s


def test_poc_harness_mock_run_smoke():
    payload = run_poc(evaluator_isolated=False)
    assert payload["status"] == "ran"
    assert payload["poc"]["number_of_workstreams"] == 10
    assert payload["poc"]["number_of_turns"] == 52
    assert payload["poc"]["trajectory_return_transitions"] == 33
    assert payload["poc"]["probe_return_count"] >= 1
    assert payload["poc"]["idempotency_correct"] is True
    assert payload["poc"]["isolation_correct"] is True
    assert "failure_counts_by_layer" in payload["poc"]
    for p in payload["probes"]:
        assert "layers" in p
        assert "FULL" in p and "RECENT" in p and "CONTEXTFLOW" in p
        assert "package_usability" in p
        assert "context_package_winner" in p
        if p.get("winner") == "CF_beats_FULL":
            assert p["context_package_winner"] == (
                "cf_package_beats_full_on_context_criteria"
            )
