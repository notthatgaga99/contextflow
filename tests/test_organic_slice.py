"""Authored organic-shaped slice — layered metrics; not production accuracy."""

from __future__ import annotations

import pytest

from eval.organic.run import BANNER, SLICE, _load, run

pytestmark = pytest.mark.organic


@pytest.fixture(autouse=True)
def _organic_env(monkeypatch):
    # Deterministic I-channel mix; same as trust path default.
    monkeypatch.setenv("CF_DISC_EMBED", "1")
    monkeypatch.setenv("CF_DISC_EMBED_W", "0.35")


def test_organic_banner_claim_hygiene():
    assert BANNER["human_behavior"] is False
    assert BANNER["not_production_accuracy"] is True
    assert BANNER["gate_frozen"] is True
    assert BANNER["kind"] == "authored_organic_shaped"


def test_organic_slice_shape():
    cases = _load(SLICE)
    assert 4 <= len(cases) <= 8
    policies = {c["gold_policy"] for c in cases}
    assert "ACT" in policies and "CLARIFY" in policies
    hops = {r["id"] for c in cases for r in c["open"]}
    assert 2 <= len(hops) <= 4
    assert any(c.get("utterance_kind") == "return" for c in cases)
    assert all(c.get("human_behavior") is False for c in cases)
    turns = [int(c.get("turn_index") or 0) for c in cases]
    assert max(turns) - min(turns) + 1 <= 15 or max(c.get("history_turns") or 0 for c in cases) <= 15


def test_organic_slice_all_pass_layered():
    payload = run()
    assert payload["human_behavior"] is False
    assert payload["not_production_accuracy"] is True
    s = payload["summary"]
    assert s["wrong_act_total"] == 0
    assert s["contamination_total"] == 0
    assert s["all_pass"] is True
    assert s["pass_count"] == payload["n_probes"]
    # Layered keys present (do not collapse to one accuracy claim).
    assert "policy_match" in s
    assert "clarify_correct" in s
    assert "working_context_sufficient" in s
