from app.config import SETTINGS, NEW_ID
from app.domain import Transition
from app.models.context import Conflict, Reference
from app.models.proposal import Candidate
from app.router.gate import decide
import pytest


def _cands(*pairs: tuple[str, float]) -> list[Candidate]:
    xs = [Candidate(tid, raw, 0.0, {}) for tid, raw in pairs]
    total = sum(c.raw for c in xs) + SETTINGS.EPS
    for c in xs:
        c.norm = c.raw / total
    xs.sort(key=lambda c: c.raw, reverse=True)
    return xs


def _decide(cands, active="A", conflict=None, statuses=None, turns_since=None):
    statuses = statuses if statuses is not None else {"A": "active", "B": "paused"}
    turns_since = turns_since if turns_since is not None else {"A": 0, "B": 4}
    return decide(cands, conflict, active, SETTINGS, statuses=statuses, turns_since=turns_since)


def test_irrelevant_distractors_do_not_change_decision():
    base = _cands(("A", 0.70), ("B", 0.20), (NEW_ID, 0.0))
    d0 = _decide(base, active="A")
    noisy = _cands(("A", 0.70), ("B", 0.20), ("C", 0.02), ("D", 0.02),
                   ("E", 0.02), ("F", 0.02), ("G", 0.02), (NEW_ID, 0.0))
    d1 = _decide(noisy, active="A")
    assert d0.transition == d1.transition == Transition.CONTINUE
    assert d0.task_id == d1.task_id == "A"
    assert d0.raw_margin == pytest.approx(0.50)
    assert d1.raw_margin == pytest.approx(0.50)
    assert d0.open_task_count == 2
    assert d1.open_task_count == 7
    assert d0.plausible_candidate_count == d1.plausible_candidate_count == 2
    assert d1.norm_margin < d0.norm_margin


def test_plausible_competitors_can_clarify():
    close = _cands(("A", 0.70), ("B", 0.65), (NEW_ID, 0.0))
    d = _decide(close, active=None, statuses={"A": "active", "B": "paused"},
                turns_since={"A": 1, "B": 1})
    assert d.transition == Transition.CLARIFY
    assert d.raw_margin == pytest.approx(0.05)
    assert d.plausible_candidate_count == 2
    assert d.open_task_count == 2


def test_hysteresis_keeps_barely_beaten_incumbent():
    cands = _cands(("B", 0.62), ("A", 0.60), (NEW_ID, 0.0))
    d = _decide(cands, active="A")
    assert d.transition == Transition.CONTINUE and d.task_id == "A"
    assert d.top_raw == 0.62
    assert abs(d.active_gap - 0.02) < 1e-9
    assert d.norm_margin < SETTINGS.DELTA  # would have clarified if norm/DELTA mixed


def test_clear_challenger_switches():
    cands = _cands(("B", 0.90), ("A", 0.60), (NEW_ID, 0.0))
    d = _decide(cands, active="A", turns_since={"A": 0, "B": 1})
    assert d.transition == Transition.SWITCH and d.task_id == "B"
    assert d.active_gap == pytest.approx(0.30)
    assert d.raw_margin == pytest.approx(0.30)


def test_low_absolute_evidence_clarifies():
    cands = _cands(("A", 0.10), ("B", 0.05), (NEW_ID, 0.0))
    d = _decide(cands, active="A")
    assert d.transition == Transition.CLARIFY
    assert d.top_raw < SETTINGS.TAU


def test_explicit_conflict_clarifies():
    cands = _cands(("A", 0.90), ("B", 0.20), (NEW_ID, 0.0))
    conflict = Conflict(
        kind="entity_mismatch",
        explicit_ref=Reference(kind="entity", value="oauth"),
        evidence_task_id="A",
        reason="test",
    )
    d = _decide(cands, active="A", conflict=conflict)
    assert d.transition == Transition.CLARIFY
    assert d.conflict is conflict


def test_norm_margin_is_logged_but_does_not_gate():
    cands = _cands(("A", 0.70), ("B", 0.20), (NEW_ID, 0.0))
    d0 = _decide(cands, active="A")
    for c in cands:
        c.norm = 1.0 / len(cands)  # destroy simplex separation
    d1 = _decide(cands, active="A")
    assert d0.transition == d1.transition == Transition.CONTINUE
    assert d1.norm_margin == 0.0
    assert d1.raw_margin == pytest.approx(d0.raw_margin)
    assert d1.raw_margin == pytest.approx(0.50)
    assert d1.gating_quantity == d1.raw_margin


def test_diagnostics_distinguish_open_count_from_plausible_count():
    cands = _cands(("A", 0.70), ("B", 0.20), ("C", 0.02), ("D", 0.02), (NEW_ID, 0.0))
    d = _decide(cands, active="A")
    assert d.open_task_count == 4
    assert d.plausible_candidate_count == 2
    assert d.active_task == "A"
    assert d.top_raw == pytest.approx(0.70)
    assert d.runner_raw == pytest.approx(0.20)
    assert d.top_norm > 0
    assert d.norm_margin > 0
