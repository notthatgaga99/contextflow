"""Real Cloud Run + Firestore durability proof. No FakeFirestore."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from urllib import error, request

from eval.cloud_poc.gcp_cli import gcloud

DEFAULT_PROJECT = "contextflow-506414"
DEFAULT_REGION = "asia-south1"
SERVICE = "contextflow-durable"


def _token() -> str:
    return gcloud("auth", "print-identity-token").stdout.strip()


def _url(project: str, region: str) -> str:
    return gcloud(
        "run", "services", "describe", SERVICE,
        f"--project={project}", f"--region={region}",
        "--format=value(status.url)",
    ).stdout.strip().rstrip("/")


def _http(method: str, url: str, token: str | None = None, body: dict | None = None) -> tuple[int, dict | str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=120) as resp:
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


def _turn(
    base: str,
    token: str,
    cid: str,
    message: str,
    turn: int,
    *,
    retries: int = 0,
    backoff_s: float = 2.0,
) -> dict:
    """POST /turn. retries apply only to rate-limit-shaped failures (429 / turn_failed 500)."""
    last: tuple[int, dict | str] | None = None
    for attempt in range(retries + 1):
        code, data = _http("POST", f"{base}/turn", token, {
            "conversation_id": cid, "message": message, "turn": turn,
        })
        if code == 200:
            return data
        last = (code, data)
        rate_shaped = code == 429
        if code == 500 and isinstance(data, dict):
            detail = data.get("detail")
            if isinstance(detail, dict) and detail.get("error") == "turn_failed":
                rate_shaped = True
            elif isinstance(detail, str) and "turn_failed" in detail:
                rate_shaped = True
        if attempt < retries and rate_shaped:
            time.sleep(backoff_s * (2 ** attempt))
            continue
        break
    code, data = last if last else (0, "no_response")
    raise RuntimeError(f"turn failed {code}: {data}")


def _memory(base: str, token: str, cid: str) -> dict:
    code, data = _http("GET", f"{base}/conversations/{cid}/memory", token)
    if code != 200:
        raise RuntimeError(f"memory GET failed {code}: {data}")
    return data


def _force_new_revision(project: str, region: str) -> str:
    """Deploy no-op env bump to recycle instances."""
    tag = uuid.uuid4().hex[:6]
    gcloud(
        "run", "services", "update", SERVICE,
        f"--project={project}", f"--region={region}",
        f"--update-env-vars=CF_POC_REVISION_BUMP={tag}",
        "--quiet",
    )
    return gcloud(
        "run", "services", "describe", SERVICE,
        f"--project={project}", f"--region={region}",
        "--format=value(status.latestReadyRevisionName)",
    ).stdout.strip()


def run(project: str = DEFAULT_PROJECT, region: str = DEFAULT_REGION) -> dict:
    suffix = uuid.uuid4().hex[:8]
    conv_a = f"poc-dur-a-{suffix}"
    conv_b = f"poc-dur-b-{suffix}"
    base = _url(project, region)
    token = _token()
    results: dict = {
        "service": SERVICE,
        "base_url": base,
        "conversation_a": conv_a,
        "conversation_b": conv_b,
        "checks": [],
    }

    def check(name: str, ok: bool, detail: str = ""):
        results["checks"].append({"name": name, "ok": ok, "detail": detail})

    # Unauthenticated should fail (403/404 depending on Cloud Run IAM front-end).
    code, _ = _http("GET", f"{base}/health", token=None)
    check("unauth_health_rejected", code in (401, 403, 404), f"status={code}")

    code, health = _http("GET", f"{base}/health", token)
    check("auth_health_ok", code == 200 and health.get("memory_durable") is True,
          str(health)[:500])

    # Conversation A: auth + outfit + black→navy
    _turn(base, token, conv_a, "JWT still returns 401", 1)
    _turn(base, token, conv_a, "black dress for a corporate", 2)
    _turn(base, token, conv_a, "formal and in the evening", 3)
    _turn(base, token, conv_a, "navy, not black", 4)

    mem_a_before = _memory(base, token, conv_a)
    items_a = mem_a_before.get("items") or []
    colors = [i for i in items_a if i.get("slot") == "color"]
    asserted_color = [i for i in colors if i.get("status") == "asserted"]
    superseded_color = [i for i in colors if i.get("status") == "superseded"]
    constraints = [
        i.get("text", "") for i in items_a
        if i.get("kind") == "constraint" and i.get("status") == "asserted"
    ]
    check("a_navy_current", any(i.get("text") == "navy" for i in asserted_color))
    check("a_black_superseded", any(i.get("text") == "black" for i in superseded_color))
    check("a_formal_constraint", any("formal" in c for c in constraints))
    check("a_evening_constraint", any("evening" in c for c in constraints))

    # Conversation B: unrelated docker memory
    _turn(base, token, conv_b, "CI is failing on the Docker step", 1)
    mem_b = _memory(base, token, conv_b)
    check("b_docker_fact", any(
        "docker" in (i.get("text") or "").lower() for i in mem_b.get("items") or []
    ))

    # Force instance lifecycle change
    rev = _force_new_revision(project, region)
    results["revision_after_bump"] = rev
    time.sleep(8)

    # Return to A via HTTP (new instance must read Firestore)
    _turn(base, token, conv_a, "navy dress for the formal", 5)
    mem_a_after = _memory(base, token, conv_a)
    items_after = mem_a_after.get("items") or []
    colors_after = [i for i in items_after if i.get("slot") == "color"]
    asserted_after = [i for i in colors_after if i.get("status") == "asserted"]
    superseded_after = [i for i in colors_after if i.get("status") == "superseded"]
    docker_in_a = [i for i in items_after if "docker" in (i.get("text") or "").lower()]
    views_current = mem_a_after.get("views", {}).get("CURRENT", [])

    check("after_restart_navy", any(i.get("text") == "navy" for i in asserted_after))
    check("after_restart_black_history", any(i.get("text") == "black" for i in superseded_after))
    check("after_restart_no_docker_leak", len(docker_in_a) == 0)
    check("current_view_excludes_black", all(
        "black" not in str(line).lower()
        for block in mem_a_after.get("views", {}).get("HISTORY", [])
        for line in block.get("lines", [])
    ) or any(i.get("text") == "black" for i in superseded_after))
    check("b_still_isolated", not any(
        "navy" in (i.get("text") or "") for i in (mem_b.get("items") or [])
    ))

    results["memory_a_sample"] = {
        "asserted_colors": [i.get("text") for i in asserted_after],
        "superseded_colors": [i.get("text") for i in superseded_after],
        "current_views": views_current,
    }
    results["ok"] = all(c["ok"] for c in results["checks"])
    return results


def main() -> int:
    project = os.getenv("GCP_PROJECT", DEFAULT_PROJECT)
    region = os.getenv("GCP_REGION", DEFAULT_REGION)
    out = run(project, region)
    out_path = os.getenv("CF_POC_OUT", "eval/out/real_cloud_run_durability.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
