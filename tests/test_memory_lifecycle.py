"""Lifecycle experiment. Synthetic fixture only unless consented session exists."""

from eval.consented_case.load import session_ready
from eval.memory_lifecycle.run import replay_primary, run, run_adversarial


def test_consented_session_absent():
    assert not session_ready()


def test_primary_does_not_preseed_memory():
    out = replay_primary(seed_memory=False)
    first = out["extract_log"][0]
    assert first["status"] == "accepted"
    assert first["accepted"]
    assert out["counts"]["memory_writes"] >= 1
    snap = out["store_snapshot"]
    assert any(i["text"] == "navy" and i["status"] == "asserted" for i in snap)
    assert any(i["text"] == "black" and i["status"] == "superseded" for i in snap)


def test_primary_returns_recover_b_without_lisbon():
    out = replay_primary(seed_memory=False)
    b = next(p for p in out["probes"] if p["return"] == "return_B_navy")
    assert b["task"] == "B"
    assert b["persistence"] is True
    assert b["CF"]["sufficient_no_leak"]
    assert "Lisbon" not in (b["CF"].get("leaks") or [])
    assert not b["wrong_ACT"]
    assert out["route_log"][7]["generate_did_not_write"]


def test_adversarial_does_not_always_act():
    rows = {r["case"]: r for r in run_adversarial()}
    assert rows["correct_task_missing_memory"]["failure"] == "extraction"
    assert rows["correct_task_stale_memory"]["live_color"] == "black"
    assert rows["correct_task_conflicting_memory"]["extraction"] == "rejected"
    assert rows["wrong_extractor_workstream"]["failure"] == "extraction"
    assert rows["ambiguous_referent_sibling_loops"]["persistence"] is True


def test_runner_writes_artifacts():
    payload = run()
    assert payload["status"] == "ran"
    assert payload["substrate"] == "synthetic_engineering_fixture"
    assert payload["summary"]["workstreams"] == 4
