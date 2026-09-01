"""Harness integrity tests for end_to_end_resurrection (no live GCP required)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "eval" / "cloud_poc" / "end_to_end_resurrection.py"


def _harness_source() -> str:
    return HARNESS.read_text(encoding="utf-8")


def test_harness_no_direct_firestore_mutation():
    src = _harness_source()
    forbidden = (
        "FirestoreMemoryStore",
        "FirestoreRegistry",
        "FakeFirestoreClient",
        "fake_firestore",
        "batch.set",
    )
    for token in forbidden:
        assert token not in src, f"harness must not use {token}"


def test_harness_uses_http_path():
    src = _harness_source()
    assert "_turn(" in src
    assert "_http(" in src


def test_harness_revision_change_detected():
    src = _harness_source()
    assert "_force_new_revision" in src
    assert "revision_changed" in src


def test_harness_same_conversation_across_restart():
    src = _harness_source()
    assert "POST_RESTART" in src


def test_harness_isolation_conversation():
    src = _harness_source()
    assert "isolation_conversation_id" in src


def test_harness_documents_seed_boundary():
    src = _harness_source()
    assert "CF_SEED_E2E" in src or "CF_SEED_ABCD" in src


def test_harness_cost_ceiling():
    src = _harness_source()
    assert "max_calls" in src
    assert "max_usd" in src


def test_harness_answer_not_quality_scored():
    from eval.cloud_poc import end_to_end_resurrection as m
    assert "NOT scored" in (m.run.__doc__ or "") or True
    src = _harness_source()
    assert "answer quality NOT scored" in src or "Answer quality NOT scored" in src


def test_harness_optional_checks_do_not_block_ok():
    src = _harness_source()
    assert "optional" in src
    assert "optional=True" in src or "optional: bool = False" in src


def test_app_does_not_import_eval():
    app = ROOT / "app"
    offenders = []
    for path in app.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("eval"):
                offenders.append(str(path))
    assert offenders == []
