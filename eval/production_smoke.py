"""Production-path HTTP smoke. Estimate first. No grid.

Env:
  CF_SMOKE_URL  default http://127.0.0.1:8080
  CF_E2E_SMOKE=1 to execute
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "out" / "production_smoke.json"

# Hosted Vertex: ≤4 HTTP turns → ≤12 generate_content. Flash-Lite envelope < $0.05.
ESTIMATE = {
    "purpose": "HTTP → extract → writer → store → frozen CF → Vertex answer",
    "http_requests": 4,
    "vertex_calls_if_extract_and_answer": "up to 4 extract + 4 propose + 4 generate ≈ 12",
    "input_tokens_est": "~8k–12k",
    "output_tokens_est": "~1.5k–4k (may include thinking tokens)",
    "estimated_usd_flash_lite": "< 0.05",
    "price_check": "gemini-2.5-flash-lite $0.10 in / $0.40 out per 1M (2026-08-29)",
    "embed_calls": 0,
    "not": "135-cell grid or embeddings batch",
}

# Same tiny set: isolation pair + assertion + return-style dress turn.
REQUESTS = [
    {"conversation_id": "hosted-a", "turn": 1,
     "message": "JWT still returns 401 after refresh."},
    {"conversation_id": "hosted-b", "turn": 1,
     "message": "I need a black dress for a corporate event."},
    {"conversation_id": "hosted-a", "turn": 2,
     "message": "Access token TTL is 15 minutes."},
    {"conversation_id": "hosted-b", "turn": 2,
     "message": "back to the dress for the corporate event"},
]


def _req(base: str, path: str, payload: dict | None = None, rid: str = "smoke") -> tuple[int, dict, dict]:
    url = base.rstrip("/") + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "X-Request-Id": rid},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        return resp.status, dict(resp.headers), body


def main() -> int:
    print(json.dumps({"estimate": ESTIMATE, "execute": os.getenv("CF_E2E_SMOKE") == "1"}, indent=2))
    if os.getenv("CF_E2E_SMOKE") != "1":
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"status": "not_executed", "estimate": ESTIMATE}, indent=2), encoding="utf-8")
        print("Set CF_E2E_SMOKE=1 to hit CF_SMOKE_URL (4 HTTP turns).")
        return 0
    base = os.getenv("CF_SMOKE_URL", "http://127.0.0.1:8080")
    health_code, health_hdrs, health = _req(base, "/health", rid="health")
    rows = []
    for i, t in enumerate(REQUESTS, 1):
        code, hdrs, body = _req(base, "/turn", t, rid=f"hosted-{i}")
        rows.append({
            "request": t, "status": code, "x_request_id": hdrs.get("x-request-id"),
            "body": {
                "transition": body.get("transition"),
                "task_id": body.get("task_id"),
                "predicted_referent_id": body.get("predicted_referent_id"),
                "extract_ok": body.get("extract_ok"),
                "correlation_id": body.get("correlation_id"),
                "answer_snip": (body.get("answer") or "")[:300],
                "included_loop_ids": body.get("included_loop_ids"),
            },
        })
    _, _, mem_a = _req(base, "/conversations/hosted-a/memory", rid="mem-a")
    _, _, mem_b = _req(base, "/conversations/hosted-b/memory", rid="mem-b")
    texts_a = " ".join(i.get("text") or "" for i in mem_a.get("items") or [])
    texts_b = " ".join(i.get("text") or "" for i in mem_b.get("items") or [])
    payload = {
        "status": "ran",
        "base": base,
        "estimate": ESTIMATE,
        "health": {"status": health_code, "body": health, "x_request_id": health_hdrs.get("x-request-id")},
        "turns": rows,
        "isolation": {
            "a_item_count": len(mem_a.get("items") or []),
            "b_item_count": len(mem_b.get("items") or []),
            "a_texts": texts_a[:500],
            "b_texts": texts_b[:500],
            "b_has_401": "401" in texts_b,
            "a_has_dress_black": "black" in texts_a.lower() or "dress" in texts_a.lower(),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "status": "ran", "n": len(rows),
        "health": health_code,
        "isolation": payload["isolation"],
        "tasks": [r["body"]["task_id"] for r in rows],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
