"""Hostile bind proofs: paraphrase / 3-way / L1+generate sibling exclusion."""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.discrimination.kernel_probe import run_kernel_probe
from eval.discrimination.run_cases import _load_cases, _run_one

pytestmark = pytest.mark.trust

CASES = Path(__file__).resolve().parents[1] / "eval" / "discrimination" / "cases.jsonl"

_HOSTILE_IDS = {
    "nm_paraphrase_unauthorized_refresh",
    "nm_orders_sku_401",
    "nm_clarify_jwt_or_cart",
    "nm_portugal_alfama",
    "ext_lisbon_late_checkout",
    "thin_ok_on_auth",
    "nm_three_way_clarify",
    "nm_three_way_resolve",
}


def _by_id():
    return {c["id"]: c for c in _load_cases(CASES)}


def test_hostile_lexical_rows_pass():
    rows = _by_id()
    missing = _HOSTILE_IDS - set(rows)
    assert not missing, missing
    fails = []
    for cid in sorted(_HOSTILE_IDS):
        r = _run_one(rows[cid])
        if not r["ok"]:
            fails.append(r)
    assert not fails, fails


def test_kernel_l1_and_generate_exclude_siblings():
    """Bound hop: sibling tokens absent from L1 and the actual generate prompt."""
    rows = _by_id()
    probes = [
        cid for cid, c in rows.items()
        if c.get("forbid_in_l1") and c.get("gold_task_id")
    ]
    assert len(probes) >= 4
    fails = []
    for cid in probes:
        out = run_kernel_probe(rows[cid])
        if not out["ok"]:
            fails.append({
                "id": cid,
                "bind_ok": out["bind_ok"],
                "l1_ok": out["l1_ok"],
                "task_id": out["task_id"],
                "transition": out["transition"],
                "forbid_hits": out["forbid_hits"],
                "l1": (out.get("l1_expose") or "")[:240],
            })
    assert not fails, fails


def test_generate_prompt_captured_for_act():
    rows = _by_id()
    out = run_kernel_probe(rows["nm_jwt_vs_orders"])
    assert out["bind_ok"]
    assert out["generate_prompt"]
    blob = out["generate_prompt"].lower()
    assert "checkout" not in blob and "sku" not in blob
    assert "refresh" in blob or "jwt" in blob or "ttl" in blob
