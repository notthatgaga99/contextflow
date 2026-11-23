"""Short live smoke for ft6: health + focused TTL extract slot on Cloud Run.

  python -m eval.cloud_poc.ft6_extract_smoke
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
    cid = f"ft6-{uuid.uuid4().hex[:8]}"
    checks: list[dict] = []
    out = {"service": SERVICE, "base_url": base, "conversation_id": cid, "checks": checks}

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail[:400]})

    code, health = _http("GET", f"{base}/health", token)
    check(
        "health_ok",
        code == 200 and isinstance(health, dict) and health.get("status") == "ok",
        str(health)[:400],
    )
    if isinstance(health, dict):
        check("catalog_firestore", health.get("catalog_backend") == "firestore",
              str(health.get("catalog_backend")))
        check("llm_extract", health.get("extract") == "llm", str(health.get("extract")))

    time.sleep(PACE_S)
    code, t1 = _http("POST", f"{base}/turn", token, {
        "conversation_id": cid,
        "message": "JWT refresh still returns 401 on the auth path",
        "turn": 1,
    })
    check("turn1_ok", code == 200 and isinstance(t1, dict), str(t1)[:300])

    time.sleep(PACE_S)
    code, t2 = _http("POST", f"{base}/turn", token, {
        "conversation_id": cid,
        "message": "TTL looks wrong — set refresh TTL to 5 minutes on the auth service",
        "turn": 2,
    })
    check("turn2_ok", code == 200 and isinstance(t2, dict), str(t2)[:300])

    code, mem = _http("GET", f"{base}/conversations/{cid}/memory", token)
    items = (mem.get("items") if isinstance(mem, dict) else None) or []
    ttl_asserted = [
        i for i in items
        if i.get("status") == "asserted"
        and (i.get("slot") == "ttl" or "5" in str(i.get("text") or ""))
    ]
    check(
        "ttl_slot_or_value_asserted",
        code == 200 and bool(ttl_asserted),
        str([{ "slot": i.get("slot"), "text": i.get("text"), "ws": i.get("workstream_id")} for i in ttl_asserted])[:400],
    )
    slotted = any(i.get("slot") == "ttl" for i in ttl_asserted)
    check("ttl_slot_present", slotted, f"slotted={slotted}")

    code, cat = _http("GET", f"{base}/catalog?user_key=local&limit=5", token)
    check(
        "catalog_list_ok",
        code == 200 and isinstance(cat, dict) and cat.get("catalog_backend") == "firestore",
        str(cat)[:300],
    )

    out["ok"] = all(c["ok"] for c in checks)
    return out


def main() -> int:
    out_path = os.getenv("CF_FT6_OUT", "eval/out/ft6_extract_smoke.json")
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
