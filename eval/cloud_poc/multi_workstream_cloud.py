"""Compact 10-workstream cloud scenario via authenticated Cloud Run."""

from __future__ import annotations

import json
import os
import sys
import uuid
from urllib import error, request

from eval.cloud_poc.gcp_cli import gcloud

DEFAULT_PROJECT = "contextflow-506414"
DEFAULT_REGION = "asia-south1"
SERVICE = "contextflow-durable"

# Synthetic/adversarial — durability + isolation + reconstruction, not natural-chat accuracy.
TURNS = [
    (1, "JWT still returns 401"),
    (2, "CI is failing on the Docker step"),
    (3, "black dress for a corporate"),
    (4, "Lisbon trip; the hotel needs parking"),
    (5, "should use APA"),
    (6, "go back to the JWT"),
    (7, "navy, not black"),
    (8, "Lisbon hotel"),
    (9, "fix that"),
    (10, "back to the dress"),
    (11, "navy dress for the formal"),
    (12, "Access token TTL is 15 minutes"),
    (13, "CI is failing on the Docker step"),
    (14, "navy dress — add pockets"),
    (15, "go back to the JWT"),
]


def _token() -> str:
    return gcloud("auth", "print-identity-token").stdout.strip()


def _base(project: str, region: str) -> str:
    return gcloud(
        "run", "services", "describe", SERVICE,
        f"--project={project}", f"--region={region}",
        "--format=value(status.url)",
    ).stdout.strip().rstrip("/")


def _turn(base: str, token: str, cid: str, message: str, turn: int) -> dict:
    body = json.dumps({"conversation_id": cid, "message": message, "turn": turn}).encode()
    req = request.Request(
        f"{base}/turn", data=body, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except error.HTTPError as exc:
        raise RuntimeError(f"turn {turn} failed: {exc.read().decode()}") from exc


def run(project: str = DEFAULT_PROJECT, region: str = DEFAULT_REGION) -> dict:
    cid = f"poc-multi-{uuid.uuid4().hex[:8]}"
    base = _base(project, region)
    token = _token()
    results = {"conversation_id": cid, "turns": [], "http_turns": 0}
    clarify = 0
    for turn_n, msg in TURNS:
        r = _turn(base, token, cid, msg, turn_n)
        results["turns"].append({
            "turn": turn_n,
            "transition": r.get("transition"),
            "task_id": r.get("task_id"),
            "referent_id": r.get("predicted_referent_id"),
            "extract_ok": r.get("extract_ok"),
        })
        if r.get("transition") == "CLARIFY":
            clarify += 1
    results["http_turns"] = len(TURNS)
    results["clarify_count"] = clarify
    results["ok"] = len(TURNS) > 0
    return results


def main() -> int:
    out = run()
    path = os.getenv("CF_POC_OUT", "eval/out/multi_workstream_cloud.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
