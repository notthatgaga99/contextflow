"""A/B insight: slot/entity I-channel vs text-only blobs.

  python -m eval.discrimination.insights

Writes eval/out/discrimination_insights.json. Mock only — not CI-blocking.
Shows which existing prompts need MemoryItem.slot to bind.
"""

from __future__ import annotations

import json
from pathlib import Path

from eval.discrimination.run_cases import CASES, _load_cases, _run_one

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "out" / "discrimination_insights.json"


def main() -> int:
    cases = _load_cases(CASES)
    with_cues = [_run_one(c, ablate_slots=False) for c in cases]
    without = [_run_one(c, ablate_slots=True) for c in cases]
    by_id_with = {r["id"]: r for r in with_cues}
    by_id_wo = {r["id"]: r for r in without}

    lift = []
    regress = []
    for cid, ok_w in ((r["id"], r["ok"]) for r in with_cues):
        ok_n = by_id_wo[cid]["ok"]
        if ok_w and not ok_n:
            lift.append({
                "id": cid,
                "bucket": by_id_with[cid].get("bucket"),
                "without": {
                    "transition": by_id_wo[cid]["final_transition"],
                    "task_id": by_id_wo[cid]["final_task_id"],
                    "region": by_id_wo[cid].get("region"),
                },
                "with": {
                    "transition": by_id_with[cid]["final_transition"],
                    "task_id": by_id_with[cid]["final_task_id"],
                    "region": by_id_with[cid].get("region"),
                    "slot_hits": by_id_with[cid].get("slot_hits"),
                },
            })
        if ok_n and not ok_w:
            regress.append(cid)

    n = len(cases)
    n_ok = sum(1 for r in with_cues if r["ok"])
    n_ok_wo = sum(1 for r in without if r["ok"])
    payload = {
        "n": n,
        "with_cues": {"n_ok": n_ok, "accuracy": round(n_ok / max(n, 1), 3)},
        "text_only": {"n_ok": n_ok_wo, "accuracy": round(n_ok_wo / max(n, 1), 3)},
        "lift_ids": [x["id"] for x in lift],
        "lift": lift,
        "regress_ids": regress,
        "insight": (
            "MemoryItem.slot / kind=entity were already stored and used by L1 "
            "ranking, but the binder only hashed item.text. Unique slot names "
            "(ttl, sku, color) are I-channel tokens; a shared slot name "
            "(window on two threads) is genre and must CLARIFY. Thin prompts "
            "like 'what's the TTL?' hop only when that unique slot is wired."
        ),
        "law": {
            "unique_slot_or_entity": "bind argmax d (even if underspecified)",
            "shared_slot_name": "genre — CLARIFY if no other identity",
            "no_slot_thin_ok": "CONTINUE ACTIVE",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"insights with={n_ok}/{n} text_only={n_ok_wo}/{n} "
        f"lift={payload['lift_ids']} wrote={OUT}",
        flush=True,
    )
    return 0 if n_ok == n and not regress else 1


if __name__ == "__main__":
    raise SystemExit(main())
