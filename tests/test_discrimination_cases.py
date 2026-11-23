"""Trust: offline discrimination casefile must stay green."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.discrimination.run_cases import _load_cases, _run_one

pytestmark = pytest.mark.trust

CASES = Path(__file__).resolve().parents[1] / "eval" / "discrimination" / "cases.jsonl"


def test_discrimination_casefile_all_pass():
    rows = _load_cases(CASES)
    assert len(rows) >= 25
    results = [_run_one(c) for c in rows]
    fails = [r for r in results if not r["ok"]]
    assert not fails, json.dumps(fails, indent=2)
