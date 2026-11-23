"""Unit: slot/entity I-channel — unique slot binds; shared slot is genre."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain import Transition
from app.models.task import Task, TaskAnchor
from app.router.thread_discriminate import (
    IdentityCues,
    decide_discrimination,
    identity_cues_from_items,
    score_threads,
)
from app.router.topic_align import is_underspecified
from eval.discrimination.run_cases import _load_cases, _run_one

CASES = Path(__file__).resolve().parents[1] / "eval" / "discrimination" / "cases.jsonl"

pytestmark = pytest.mark.trust


def _task(tid: str, title: str, cues: list[str]) -> Task:
    return Task(
        id=tid,
        title=title,
        retrieval_cues=cues,
        anchor=TaskAnchor(goal=title, open_loops=[title]),
    )


def test_identity_cues_from_items_reads_slot_and_entity_skips_generic():
    items = [
        SimpleNamespace(slot="ttl", kind="decision", text="5 minutes"),
        SimpleNamespace(slot="entity", kind="entity", text="Alfama"),
        SimpleNamespace(slot=None, kind="fact", text="noise"),
    ]
    cues = identity_cues_from_items(items)
    assert cues.slots == ("ttl",)
    assert cues.entities == ("Alfama",)
    assert "ttl" in " ".join(cues.extra_texts()).lower()
    assert "alfama" in " ".join(cues.extra_texts()).lower()


def test_unique_slot_beats_text_only_blob():
    """Memory text is '5 minutes'; message says TTL — slot is the identity."""
    auth = _task("A", "JWT auth refresh", ["jwt", "auth", "refresh"])
    orders = _task("C", "orders checkout", ["orders", "cart", "checkout"])
    mem = {"A": ["5 minutes"], "C": ["cart 401"]}
    cues = {"A": IdentityCues(slots=("ttl",))}
    msg = "what's the TTL?"
    bare = score_threads(msg, [auth, orders], mem)
    wired = score_threads(msg, [auth, orders], mem, cues)
    assert wired["A"].distinctive > bare["A"].distinctive
    assert wired["A"].distinctive > wired["C"].distinctive
    assert "ttl" in wired["A"].slot_hits


def test_shared_slot_name_is_genre_not_identity():
    auth = _task("A", "JWT auth", ["jwt", "auth", "refresh"])
    orders = _task("C", "orders", ["orders", "cart", "checkout"])
    cues = {
        "A": IdentityCues(slots=("window",)),
        "C": IdentityCues(slots=("window",)),
    }
    scores = score_threads(
        "what was the window we set?",
        [auth, orders],
        {"A": ["5 minutes"], "C": ["until 2pm"]},
        cues,
    )
    assert scores["A"].slot_hits == ()
    assert scores["C"].slot_hits == ()
    # window is shared → distinctive must not come from the slot name
    assert scores["A"].distinctive_raw == 0.0
    assert scores["C"].distinctive_raw == 0.0


def test_underspecified_ttl_hops_when_slot_identity_recoverable():
    auth = _task("A", "JWT auth refresh", ["jwt", "auth", "refresh"])
    orders = _task("C", "orders checkout", ["orders", "cart", "checkout"])
    msg = "what's the TTL?"
    assert is_underspecified(msg)
    decided = decide_discrimination(
        message=msg,
        gate_transition=Transition.CONTINUE,
        gate_task_id="C",
        open_tasks=[auth, orders],
        active_id="C",
        memory_texts_by_task={"A": ["5 minutes"], "C": ["cart 401"]},
        identity_cues_by_task={"A": IdentityCues(slots=("ttl",))},
        underspecified=True,
    )
    assert decided is not None
    assert decided.task_id == "A"
    assert decided.reason == "discriminate_underspecified_identity"


def test_gate_clarify_resolves_when_entity_identity_clear():
    """Frozen gate CLARIFY must not hide a recoverable entity hop."""
    lisbon = _task("L", "trip hotel parking", ["hotel", "parking", "trip"])
    paris = _task("P", "Paris hotel parking", ["paris", "hotel", "parking", "trip"])
    decided = decide_discrimination(
        message="is the Alfama place still okay for parking?",
        gate_transition=Transition.CLARIFY,
        gate_task_id=None,
        open_tasks=[lisbon, paris],
        active_id="P",
        memory_texts_by_task={
            "L": ["need parking near center"],
            "P": ["Louvre area"],
        },
        identity_cues_by_task={"L": IdentityCues(entities=("Alfama",)), "P": IdentityCues(entities=("Marais",))},
        underspecified=False,
    )
    assert decided is not None
    assert decided.task_id == "L"
    assert decided.transition != Transition.CLARIFY


def test_deictic_fix_that_keeps_gate():
    """Shared verb 'fix' is not genre confusion — clocks own 'fix that'."""
    auth = _task("A", "fix jwt auth", ["jwt", "auth"])
    docker = _task("C", "fix docker build", ["docker", "build"])
    decided = decide_discrimination(
        message="fix that",
        gate_transition=Transition.CONTINUE,
        gate_task_id="C",
        open_tasks=[auth, docker],
        active_id="C",
        underspecified=True,
    )
    assert decided is None


def test_correction_other_one_not_undone_by_underspecified_stick():
    auth = _task("A", "jwt auth", ["jwt", "auth", "token"])
    front = _task("B", "frontend", ["react", "render", "component"])
    decided = decide_discrimination(
        message="no, the other one",
        gate_transition=Transition.RETURN,
        gate_task_id="B",
        open_tasks=[auth, front],
        active_id="A",
        underspecified=True,
    )
    assert decided is None


def test_thin_ok_still_sticks_without_identity():
    auth = _task("A", "JWT auth", ["jwt", "auth", "refresh"])
    orders = _task("C", "orders", ["orders", "cart"])
    decided = decide_discrimination(
        message="ok",
        gate_transition=Transition.NEW,
        gate_task_id=None,
        open_tasks=[auth, orders],
        active_id="A",
        memory_texts_by_task={"A": ["JWT refresh"], "C": ["cart sku"]},
        underspecified=True,
    )
    assert decided is not None
    assert decided.task_id == "A"
    assert decided.transition == Transition.CONTINUE


def test_slot_ablation_lifts_ttl_and_sku_rows():
    rows = {c["id"]: c for c in _load_cases(CASES)}
    # color is also in the outfit loop text — not a pure slot lift.
    for cid in ("slot_ttl_vs_orders", "slot_sku_vs_auth"):
        assert rows[cid]["id"] == cid
        assert _run_one(rows[cid], ablate_slots=False)["ok"]
        assert not _run_one(rows[cid], ablate_slots=True)["ok"], cid
