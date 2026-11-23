"""A/B insight: slot/entity I-channel vs text-only blobs + (c_S, Δ_I) plane.

  python -m eval.discrimination.insights

Writes:
  eval/out/discrimination_insights.json
  eval/out/discrimination_plane.json
"""

from __future__ import annotations

import json
from pathlib import Path

from eval.discrimination.run_cases import CASES, _load_cases, _run_one

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "out" / "discrimination_insights.json"
PLANE = ROOT / "eval" / "out" / "discrimination_plane.json"


def _plane_rows(results: list[dict], cases: list[dict]) -> list[dict]:
    by_case = {c["id"]: c for c in cases}
    rows = []
    for r in results:
        gold = by_case.get(r["id"], {})
        wid = r.get("winner_id")
        scores = r.get("scores") or {}
        d_emb = None
        if wid and isinstance(scores.get(wid), dict):
            d_emb = scores[wid].get("d_emb")
        rows.append({
            "id": r["id"],
            "bucket": r.get("bucket") or gold.get("bucket"),
            "c_S": r.get("c_S"),
            "delta_I": r.get("delta_I"),
            "C_S_count": r.get("C_S_count"),
            "region": r.get("region"),
            "high_confusion": r.get("high_confusion"),
            "winner_id": wid,
            "final_transition": r.get("final_transition"),
            "final_task_id": r.get("final_task_id"),
            "gold_task_id": gold.get("gold_task_id"),
            "gold_transition": gold.get("gold_transition"),
            "ok": r.get("ok"),
            "d_emb_winner": d_emb,
        })
    return rows


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
            "like 'what's the TTL?' hop only when that unique slot is wired. "
            "CF_DISC_EMBED mixes Dist-Share embed contrast into d only."
        ),
        "law": {
            "unique_slot_or_entity": "bind argmax d (even if underspecified)",
            "shared_slot_name": "genre — CLARIFY if no other identity",
            "no_slot_thin_ok": "CONTINUE ACTIVE",
            "embed_i_only": "d_emb = max(0, cos(msg,Dist)-cos(msg,Share)); never pick by o/s",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    plane_rows = _plane_rows(with_cues, cases)
    plane = {
        "n": len(plane_rows),
        "axes": {"x": "c_S", "y": "delta_I"},
        "note": (
            "Plot every casefile row in the (c_S, delta_I) plane. "
            "High c_S + low delta_I → CLARIFY; high delta_I → bind by d."
        ),
        "points": plane_rows,
    }
    PLANE.write_text(json.dumps(plane, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    hi_c = [p for p in plane_rows if (p.get("c_S") or 0) >= 0.05]
    clarify = sum(1 for p in plane_rows if p.get("final_transition") == "CLARIFY")
    print(
        f"insights with={n_ok}/{n} text_only={n_ok_wo}/{n} "
        f"lift={payload['lift_ids']} wrote={OUT}",
        flush=True,
    )
    print(
        f"plane n={len(plane_rows)} high_c_S={len(hi_c)} clarify={clarify} wrote={PLANE}",
        flush=True,
    )
    return 0 if n_ok == n and not regress else 1


if __name__ == "__main__":
    raise SystemExit(main())
