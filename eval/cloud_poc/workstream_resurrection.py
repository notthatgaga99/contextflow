"""Real Cloud Run + Firestore workstream resurrection proof."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from urllib import error, request

from eval.cloud_poc.gcp_cli import gcloud
from eval.cloud_poc.real_cloud_run_durability import _force_new_revision, _http, _memory, _turn

SERVICE = "contextflow-durable"


def _tasks(base: str, token: str, cid: str) -> dict:
    code, data = _http("GET", f"{base}/conversations/{cid}/tasks", token)
    if code != 200:
        raise RuntimeError(f"tasks GET failed {code}: {data}")
    return data


def run(project: str = "contextflow-506414", region: str = "asia-south1") -> dict:
    suffix = uuid.uuid4().hex[:8]
    conv_a = f"poc-res-a-{suffix}"
    conv_b = f"poc-res-b-{suffix}"
    base = gcloud(
        "run", "services", "describe", SERVICE,
        f"--project={project}", f"--region={region}",
        "--format=value(status.url)",
    ).stdout.strip().rstrip("/")
    token = gcloud("auth", "print-identity-token").stdout.strip()
    results = {"conversation_a": conv_a, "conversation_b": conv_b, "checks": []}

    def check(name: str, ok: bool, detail: str = ""):
        results["checks"].append({"name": name, "ok": ok, "detail": detail})

    # Conversation A: multi-thread + outfit E
    _turn(base, token, conv_a, "JWT auth 401 issue", 1)
    _turn(base, token, conv_a, "outfit black dress for corporate event", 2)
    _turn(base, token, conv_a, "evening formal constraint outfit", 3)
    _turn(base, token, conv_a, "orders API is slow", 4)
    _turn(base, token, conv_a, "Lisbon travel hotel", 5)
    _turn(base, token, conv_a, "navy not black outfit", 6)

    tasks_before = _tasks(base, token, conv_a)
    ws_e = [t for t in tasks_before.get("tasks", []) if t.get("id") == "E"]
    check("workstream_e_exists", len(ws_e) == 1, str(ws_e))

    mem_before = _memory(base, token, conv_a)
    colors = [i for i in mem_before.get("items", []) if i.get("slot") == "color"]
    check("navy_before_restart", any(
        i.get("text") == "navy" and i.get("status") == "asserted" for i in colors
    ))

    # Conversation B: docker isolated
    _turn(base, token, conv_b, "Docker CI step failing", 1)
    mem_b = _memory(base, token, conv_b)

    # Force instance replacement
    rev = _force_new_revision(project, region)
    results["revision_after_bump"] = rev
    time.sleep(10)

    # Return to outfit thread E
    _turn(base, token, conv_a, "back to the outfit thread", 7)
    tasks_after = _tasks(base, token, conv_a)
    ws_e_after = [t for t in tasks_after.get("tasks", []) if t.get("id") == "E"]
    check("workstream_e_survives", bool(len(ws_e_after) == 1 and ws_e_after[0].get("title")))
    mem_after = _memory(base, token, conv_a)
    items = mem_after.get("items") or []
    asserted = [i for i in items if i.get("workstream_id") == "E" and i.get("status") == "asserted"]
    superseded = [i for i in items if i.get("workstream_id") == "E" and i.get("status") == "superseded"]
    constraints = [i for i in asserted if i.get("kind") == "constraint"]
    check("navy_survives", any(i.get("text") == "navy" for i in asserted if i.get("slot") == "color"))
    check("formal_survives", any("formal" in (i.get("text") or "") for i in constraints))
    check("evening_survives", any("evening" in (i.get("text") or "") for i in constraints))
    check("black_superseded", any(i.get("text") == "black" for i in superseded))
    check("no_docker_in_a", not any(
        "docker" in (i.get("text") or "").lower() for i in items if i.get("workstream_id") != "B"
    ))
    check("b_isolated", any(
        "docker" in (i.get("text") or "").lower() for i in (mem_b.get("items") or [])
    ))

    # Return to technical thread C
    _turn(base, token, conv_a, "return to orders API", 8)
    mem_c = _memory(base, token, conv_a)
    check("orders_fact_survives", any(
        i.get("workstream_id") == "C" and "orders" in (i.get("text") or "").lower()
        for i in mem_c.get("items") or []
    ))

    results["ok"] = all(c["ok"] for c in results["checks"])
    return results


def main() -> int:
    out = run()
    path = os.getenv("CF_POC_OUT", "eval/out/workstream_resurrection.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
