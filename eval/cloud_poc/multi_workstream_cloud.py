"""Compact multi-workstream cloud scenario via authenticated Cloud Run.

Realistic Vertex path: asserts extract + critical bind routes (not smoke scripts).
Requires CF_SEED_E2E=1 for A/B/C/D card identity (auth/outfit/travel/APA).
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from urllib import error, request

from eval.cloud_poc.gcp_cli import gcloud

DEFAULT_PROJECT = "contextflow-gagan-20261019"
DEFAULT_REGION = "us-central1"
SERVICE = "contextflow-durable"
HTTP_TIMEOUT_S = 180

# Synthetic/adversarial — durability + isolation + reconstruction under live Vertex.
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

# Expected task after bind. None = no hard assert (near-miss / NEW / clarify OK).
# Seed E2E: A=auth, B=outfit, C=Lisbon, D=Docker deploy. APA is unseeded → allow NEW.
EXPECT_TASK = {
    1: "A",
    2: "D",
    3: "B",
    4: "C",
    6: "A",
    7: "B",
    8: "C",
    10: "B",
    11: "B",
    12: "A",
    13: "D",
    14: "B",
    15: "A",
}


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
        with request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            return json.loads(resp.read())
    except error.HTTPError as exc:
        raise RuntimeError(f"turn {turn} failed: {exc.read().decode()[:500]}") from exc


def run(project: str = DEFAULT_PROJECT, region: str = DEFAULT_REGION) -> dict:
    cid = f"poc-multi-{uuid.uuid4().hex[:8]}"
    base = _base(project, region)
    token = _token()
    results: dict = {
        "conversation_id": cid,
        "base_url": base,
        "turns": [],
        "checks": [],
        "http_turns": 0,
    }
    clarify = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        results["checks"].append({"name": name, "ok": ok, "detail": detail[:240]})

    for turn_n, msg in TURNS:
        r = _turn(base, token, cid, msg, turn_n)
        row = {
            "turn": turn_n,
            "message": msg,
            "transition": r.get("transition"),
            "task_id": r.get("task_id"),
            "referent_id": r.get("predicted_referent_id") or r.get("referent_id"),
            "extract_ok": r.get("extract_ok"),
            "has_answer": bool(r.get("answer")),
        }
        results["turns"].append(row)
        if r.get("transition") == "CLARIFY":
            clarify += 1
        expect = EXPECT_TASK.get(turn_n)
        if expect is not None:
            check(
                f"route_t{turn_n}",
                row["task_id"] == expect,
                f"got={row['task_id']} want={expect} transition={row['transition']}",
            )

    results["http_turns"] = len(TURNS)
    results["clarify_count"] = clarify
    extract_ok_n = sum(1 for t in results["turns"] if t.get("extract_ok") is True)
    check("extract_all", extract_ok_n == len(TURNS), f"{extract_ok_n}/{len(TURNS)}")
    route_checks = [c for c in results["checks"] if c["name"].startswith("route_")]
    route_ok = sum(1 for c in route_checks if c["ok"])
    check(
        "route_majority",
        route_ok >= max(1, int(0.7 * len(route_checks))),
        f"{route_ok}/{len(route_checks)}",
    )
    results["ok"] = all(c["ok"] for c in results["checks"] if c["name"] in ("extract_all", "route_majority"))
    # Surface per-route misses without failing the whole suite if majority holds.
    results["route_accuracy"] = {
        "ok": route_ok,
        "n": len(route_checks),
        "misses": [c for c in route_checks if not c["ok"]],
    }
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
