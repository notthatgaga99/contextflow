"""Durability proof plan — FakeFirestore restart simulation (not in-memory backend)."""

from eval.cloud_poc import DURABILITY_PLAN, simulate_restart_roundtrip


def test_durability_plan_documented():
    assert "conversation A" in DURABILITY_PLAN
    assert "conversation B" in DURABILITY_PLAN
    assert "Restart" in DURABILITY_PLAN


def test_simulate_restart_no_leak_supersession_auditable():
    result = simulate_restart_roundtrip()
    assert result["a_current"] == ["black"]
    assert "navy" in result["a_superseded"]
    assert result["b_current"] == ["paris"]
    assert result["leak_into_a"] == []
    assert any("black" in d for d in result["projection_decisions"])
    assert not any("navy" in d for d in result["projection_decisions"])
