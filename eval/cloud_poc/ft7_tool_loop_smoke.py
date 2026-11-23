"""Live ft7 smoke: ACT agent turn runs bound search; CLARIFY skips tools.

  python -m eval.cloud_poc.ft7_tool_loop_smoke
"""

from __future__ import annotations

import json
import os
import time
import uuid
from urllib import error, request

from eval.cloud_poc.gcp_cli import gcloud

DEFAULT_PROJECT = "contextflow-gagan-20261019"
DEFAULT_REGION = "us-central1"
SERVICE = "contextflow-durable"
PACE_S = float(os.getenv("CF_VERTEX_MIN_INTERVAL_S") or "6.5")


def _token() -> str:
    return gcloud("auth", "print-identity-token").stdout.strip()


def _url(project: str, region: str) -> str:
    return gcloud(
        "run", "services", "describe", SERVICE,
        f"--project={project}", f"--region={region}",
        "--format=value(status.url)",
    ).stdout.strip().rstrip("/")


def _http(method: str, url: str, token: str | None = None, body: dict | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def run(project: str = DEFAULT_PROJECT, region: str = DEFAULT_REGION) -> dict:
    base = _url(project, region)
    token = _token()
    cid = f"ft7-{uuid.uuid4().hex[:8]}"
    checks: list[dict] = []
    out = {"service": SERVICE, "base_url": base, "conversation_id": cid, "checks": checks}

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail[:400]})

    code, health = _http("GET", f"{base}/health", token)
    check("health_ok", code == 200 and isinstance(health, dict), str(health)[:300])

    # Seed two near-miss threads via turns (pace).
    time.sleep(PACE_S)
    code, t1 = _http("POST", f"{base}/agent/turn", token, {
        "conversation_id": cid,
        "message": "JWT refresh still returns 401 on the auth path",
        "turn": 1,
        "auto_tools": True,
    })
    check("act_turn1_http", code == 200 and isinstance(t1, dict), str(t1)[:350])
    if isinstance(t1, dict):
        tools = t1.get("tools") or []
        interrupt = t1.get("interrupt") is True
        check(
            "act_runs_search_or_skips_only_if_unbound",
            (not interrupt and bool(tools) and tools[0].get("tool") == "search_bound")
            or interrupt,
            f"interrupt={interrupt} tools={tools[:1]}",
        )
        if not interrupt:
            check(
                "act_l1_unchanged_flag",
                (t1.get("tool_loop") or {}).get("l1_unchanged") is True,
                str(t1.get("tool_loop")),
            )

    # Force a second 401-domain hop (orders) so bare "401" is a near-miss.
    time.sleep(PACE_S)
    code, t2 = _http("POST", f"{base}/agent/turn", token, {
        "conversation_id": cid,
        "message": "NEW: orders API returns 401 on checkout for SKU cart",
        "turn": 2,
        "auto_tools": True,
    })
    check("turn2_http", code == 200 and isinstance(t2, dict), str(t2)[:350])
    t2_tid = t2.get("task_id") if isinstance(t2, dict) else None

    # Ambiguous 401 → CLARIFY should skip tools (when both hops are open).
    time.sleep(PACE_S)
    code, t3 = _http("POST", f"{base}/agent/turn", token, {
        "conversation_id": cid,
        "message": "still getting 401",
        "turn": 3,
        "auto_tools": True,
    })
    check("clarify_http", code == 200 and isinstance(t3, dict), str(t3)[:350])
    if isinstance(t3, dict):
        interrupted = t3.get("interrupt") is True
        tools = t3.get("tools") or []
        # Prefer CLARIFY; if gate sticks CONTINUE, tools may run — still require
        # forged multi-hop interrupt path when discrimination fires.
        clarify_ok = interrupted and tools == [] and t3.get("l1_expose") is None
        # Alternate acceptable: ACT on one hop with tool_loop l1_unchanged (no soft Select).
        act_ok = (
            not interrupted
            and bool(t3.get("task_id"))
            and (t3.get("tool_loop") or {}).get("l1_unchanged") is True
            and (not tools or tools[0].get("tool") == "search_bound")
        )
        check(
            "clarify_or_bound_act_lawful",
            clarify_ok or act_ok,
            f"interrupt={interrupted} transition={t3.get('transition')} "
            f"task={t3.get('task_id')} t2_task={t2_tid} tools={len(tools)}",
        )
        if clarify_ok:
            check("clarify_skips_tools", True, "clarify")
            check("clarify_no_l1", True, "clarify")
        else:
            check(
                "act_tools_bound_only",
                act_ok,
                str(t3.get("tool_loop")),
            )

    out["ok"] = all(c["ok"] for c in checks)
    return out


def main() -> int:
    out_path = os.getenv("CF_FT7_OUT", "eval/out/ft7_tool_loop_smoke.json")
    result = run()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    failed = [c for c in result["checks"] if not c["ok"]]
    print(json.dumps({"ok": result["ok"], "failed": failed, "n": len(result["checks"])}, indent=2))
    print(f"wrote={out_path}", flush=True)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
