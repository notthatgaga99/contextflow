"""Optional live Vertex smoke on a small discrimination slice.

Not CI. Pace-aware. Bind/clarify only — does not redefine the Mock trust bar.

  . .\\scripts\\env_vertex_local.ps1
  python -m eval.discrimination.vertex_smoke

Skip unless CF_USE_VERTEX=1 and credentials exist.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from eval.discrimination.kernel_probe import run_kernel_probe
from eval.discrimination.run_cases import _load_cases

ROOT = Path(__file__).resolve().parents[2]
CASES = Path(__file__).resolve().parent / "cases.jsonl"
OUT = ROOT / "eval" / "out" / "discrimination_vertex_smoke.json"

# Capped: clarify + near-miss + NEW. ~1 propose + 1 generate per ACT row.
SMOKE_IDS = [
    "nm_jwt_vs_orders",
    "nm_clarify_bare_401",
    "nm_orders_sku_401",
    "new_fashion_after_iot",
    "nm_three_way_resolve",
]


def _ready() -> str | None:
    if os.getenv("CF_USE_VERTEX") != "1":
        return "CF_USE_VERTEX!=1"
    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds or not Path(creds).exists():
        return "missing GOOGLE_APPLICATION_CREDENTIALS"
    if not (os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")):
        return "missing GCP_PROJECT"
    return None


def main() -> int:
    why = _ready()
    if why:
        payload = {"status": "skipped", "reason": why, "n": 0}
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"skipped: {why}", flush=True)
        return 0

    from app.llm.gemini import GeminiClient

    # Same bind policy as Mock casefile. Live path is propose + generate only.
    os.environ.setdefault("CF_TOPIC_LLM", "0")
    os.environ.setdefault("CF_VERTEX_MIN_INTERVAL_S", "6.5")
    llm = GeminiClient()
    by_id = {c["id"]: c for c in _load_cases(CASES)}
    results = []
    for cid in SMOKE_IDS:
        case = by_id.get(cid)
        if not case:
            results.append({"id": cid, "ok": False, "error": "missing_case"})
            continue
        try:
            out = run_kernel_probe(case, llm=llm)
            results.append({
                "id": cid,
                "ok": out["ok"],
                "bind_ok": out["bind_ok"],
                "l1_ok": out["l1_ok"],
                "transition": out["transition"],
                "task_id": out["task_id"],
                "forbid_hits": out.get("forbid_hits"),
                "discrimination": out.get("discrimination"),
            })
        except Exception as exc:
            results.append({"id": cid, "ok": False, "error": str(exc)[:240]})

    n_ok = sum(1 for r in results if r.get("ok"))
    payload = {
        "status": "ran",
        "provider": "vertex",
        "model": getattr(llm, "LITE_MODEL", None),
        "n": len(results),
        "n_ok": n_ok,
        "accuracy": round(n_ok / max(len(results), 1), 3),
        "results": results,
        "note": "Optional smoke. Mock casefile remains the adoption bar.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"vertex_smoke {n_ok}/{len(results)} wrote={OUT}",
        flush=True,
    )
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
