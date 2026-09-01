"""Small Vertex E2E via authenticated Cloud Run. Budget: <=6 turns, <=20 generate_content."""

from __future__ import annotations

import json
import os
import sys
from urllib import error, request

from eval.cloud_poc.gcp_cli import gcloud

SERVICE = "contextflow-durable"
MAX_TURNS = 4  # ~3 Vertex calls/turn → <=12 generate_content
TURNS = [
    (1, "We need to fix JWT authentication returning 401 after refresh."),
    (2, "For the corporate outfit I decided on a black dress."),
    (3, "Actually make it navy, not black — still formal and evening."),
    (4, "Okay, back to the outfit decision."),
]


def _token() -> str:
    return gcloud("auth", "print-identity-token").stdout.strip()


def _base() -> str:
    proj = os.getenv("GCP_PROJECT", "contextflow-506414")
    region = os.getenv("GCP_REGION", "asia-south1")
    return gcloud(
        "run", "services", "describe", SERVICE,
        f"--project={proj}", f"--region={region}",
        "--format=value(status.url)",
    ).stdout.strip().rstrip("/")


def _turn(base: str, token: str, cid: str, message: str, turn: int) -> dict:
    body = json.dumps({"conversation_id": cid, "message": message, "turn": turn}).encode()
    req = request.Request(
        f"{base}/turn", data=body, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read())
    except error.HTTPError as exc:
        raise RuntimeError(f"turn {turn}: {exc.read().decode()[:500]}") from exc


def main() -> int:
    import uuid
    cid = f"poc-vertex-{uuid.uuid4().hex[:8]}"
    base = _base()
    token = _token()
    out = {"conversation_id": cid, "turns": [], "max_turns": MAX_TURNS}
    for turn_n, msg in TURNS[:MAX_TURNS]:
        r = _turn(base, token, cid, msg, turn_n)
        out["turns"].append({
            "turn": turn_n,
            "transition": r.get("transition"),
            "task_id": r.get("task_id"),
            "extract_ok": r.get("extract_ok"),
            "answer_status": "ok" if r.get("answer") else (
                "clarify" if r.get("transition") == "CLARIFY" else "none"
            ),
        })
    path = os.getenv("CF_POC_OUT", "eval/out/vertex_cloud_smoke.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
