"""Harness integrity tests for e2e_repeatability (no live GCP required)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "eval" / "cloud_poc" / "e2e_repeatability.py"


def _src() -> str:
    return HARNESS.read_text(encoding="utf-8")


def test_repeatability_no_firestore_mutation():
    src = _src()
    for token in ("FirestoreMemoryStore", "FirestoreRegistry", "batch.set"):
        assert token not in src


def test_repeatability_uses_http():
    src = _src()
    assert "_turn(" in src and "_http(" in src


def test_repeatability_quality_gate_layers():
    src = _src()
    assert "correction_extraction" in src
    assert "duplicate_current_decisions" in src
    assert "routing_freeze" in src
    assert "all_ok" in src


def test_repeatability_configurable_runs():
    src = _src()
    assert "CF_REPEAT_RUNS" in src


def test_repeatability_isolation_retries_rate_limits():
    src = _src()
    assert "CF_ISOLATION_RETRIES" in src
    assert "error_category" in src
    assert "turn_failed" in src


def test_repeatability_pauses_between_runs():
    src = _src()
    assert "CF_REPEAT_PAUSE_S" in src
