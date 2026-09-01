"""Ten-thread cloud resurrection — engineering proof, not benchmark."""

from __future__ import annotations

import json
import os
import time
import uuid

from eval.cloud_poc.gcp_cli import gcloud
from eval.cloud_poc.real_cloud_run_durability import _force_new_revision, _memory, _turn

SERVICE = "contextflow-durable"

TURNS = [
    (1, "JWT auth 401 issue"),
    (2, "Docker CI step failing"),
    (3, "orders API is slow"),
    (4, "checkout renders twice"),
    (5, "outfit black dress for corporate event"),
    (6, "Lisbon travel hotel"),
    (7, "vegetarian dinner restaurant"),
    (8, "closing slide deck"),
    (9, "update job resume"),
    (10, "trivia capital Portugal"),
    (11, "navy not black outfit"),
    (12, "evening formal constraint outfit"),
    (13, "return to orders API"),
    (14, "back to the outfit thread"),
    (15, "JWT auth 401 issue"),
    (16, "trivia capital Portugal"),
]


def _tasks(base, token, cid):
    from eval.cloud_poc.real_cloud_run_durability import _http
    code, data = _http("GET", f"{base}/conversations/{cid}/tasks", token)
    if code != 200:
        raise RuntimeError(data)
    return data


def run(project="contextflow-506414", region="asia-south1") -> dict:
    cid = f"poc-ten-{uuid.uuid4().hex[:8]}"
    base = gcloud(
        "run", "services", "describe", SERVICE,
        f"--project={project}", f"--region={region}",
        "--format=value(status.url)",
    ).stdout.strip().rstrip("/")
    token = gcloud("auth", "print-identity-token").stdout.strip()
    out = {"conversation_id": cid, "turns": [], "returns": {}, "checks": []}

    def check(name, ok, detail=""):
        out["checks"].append({"name": name, "ok": ok, "detail": detail})

    for turn_n, msg in TURNS:
        r = _turn(base, token, cid, msg, turn_n)
        out["turns"].append({
            "turn": turn_n, "transition": r.get("transition"),
            "task_id": r.get("task_id"), "referent_id": r.get("predicted_referent_id"),
        })

    rev = _force_new_revision(project, region)
    out["revision_after_bump"] = rev
    time.sleep(10)

    # Return probes
    probes = [
        ("A", 17, "JWT auth 401 issue"),
        ("C", 18, "return to orders API"),
        ("E", 19, "back to the outfit thread"),
        ("J", 20, "trivia capital Portugal"),
    ]
    for ws, turn_n, msg in probes:
        r = _turn(base, token, cid, msg, turn_n)
        mem = _memory(base, token, cid)
        tasks = _tasks(base, token, cid)
        ws_row = [t for t in tasks.get("tasks", []) if t.get("id") == ws]
        out["returns"][ws] = {
            "transition": r.get("transition"),
            "task_recovered": bool(ws_row),
            "referent_recovered": r.get("predicted_referent_id") is not None,
            "title": ws_row[0].get("title") if ws_row else None,
        }
        check(f"return_{ws}_task_exists", bool(ws_row), str(ws_row))

    mem_final = _memory(base, token, cid)
    e_items = [i for i in mem_final.get("items", []) if i.get("workstream_id") == "E"]
    check("e_navy_current", any(
        i.get("text") == "navy" and i.get("status") == "asserted" for i in e_items
    ))
    check("e_black_history", any(
        i.get("text") == "black" and i.get("status") == "superseded" for i in e_items
    ))
    clarify = sum(1 for t in out["turns"] if t.get("transition") == "CLARIFY")
    out["clarify_count"] = clarify
    out["http_turns"] = len(TURNS) + len(probes)
    out["ok"] = all(c["ok"] for c in out["checks"])
    return out


def main() -> int:
    out = run()
    path = os.getenv("CF_POC_OUT", "eval/out/ten_thread_resurrection.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
