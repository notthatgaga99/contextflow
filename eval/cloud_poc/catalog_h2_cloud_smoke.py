"""Live Cloud Run H2 catalog smoke: archive → match → import (opt-in).

Uses ADC identity token via gcloud (same pattern as real_cloud_run_durability).
Paced turns for Free Trial Vertex. Never auto-merges.

  python -m eval.cloud_poc.catalog_h2_cloud_smoke
"""

from __future__ import annotations

import json
import os
import sys
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


def _http(
    method: str,
    url: str,
    token: str | None = None,
    body: dict | None = None,
) -> tuple[int, dict | str]:
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


def _pace() -> None:
    time.sleep(max(0.0, PACE_S))


def run(project: str = DEFAULT_PROJECT, region: str = DEFAULT_REGION) -> dict:
    suffix = uuid.uuid4().hex[:8]
    src = f"h2-src-{suffix}"
    dst = f"h2-dst-{suffix}"
    user_key = f"h2-user-{suffix}"
    base = _url(project, region)
    token = _token()
    checks: list[dict] = []
    out: dict = {
        "service": SERVICE,
        "base_url": base,
        "src": src,
        "dst": dst,
        "user_key": user_key,
        "checks": checks,
    }

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail[:400]})

    code, health = _http("GET", f"{base}/health", token)
    check(
        "health_ok",
        code == 200 and isinstance(health, dict),
        str(health)[:400],
    )
    if isinstance(health, dict):
        check(
            "catalog_backend_firestore",
            health.get("catalog_backend") == "firestore",
            f"catalog_backend={health.get('catalog_backend')}",
        )
        check(
            "memory_durable",
            health.get("memory_durable") is True,
            f"memory_backend={health.get('memory_backend')}",
        )

    # Seed two workstreams via turns (paced).
    for turn, msg in (
        (1, "JWT refresh still returns 401 on the auth path"),
        (2, "also pick a navy dress for the formal evening"),
    ):
        _pace()
        code, data = _http(
            "POST", f"{base}/turn", token,
            {"conversation_id": src, "message": msg, "turn": turn},
        )
        check(f"turn_{turn}_ok", code == 200, str(data)[:300])

    code, roll = _http("GET", f"{base}/conversations/{src}/rollup", token)
    check(
        "rollup_ok",
        code == 200 and isinstance(roll, dict) and int(roll.get("open_count") or 0) >= 1,
        str(roll)[:400] if isinstance(roll, dict) else str(roll)[:200],
    )

    code, archived = _http(
        "POST", f"{base}/conversations/{src}/archive?user_key={user_key}", token,
    )
    check("archive_ok", code == 200 and isinstance(archived, dict) and archived.get("ok"),
          str(archived)[:300])

    code, cat = _http("GET", f"{base}/catalog?user_key={user_key}", token)
    listed = (cat.get("conversations") if isinstance(cat, dict) else None) or []
    check(
        "catalog_lists_src",
        code == 200 and any(e.get("conversation_id") == src for e in listed),
        str(cat)[:400],
    )

    code, matched = _http(
        "GET",
        f"{base}/catalog/match?q=navy+dress+formal&user_key={user_key}&limit=3",
        token,
    )
    hits = (matched.get("matches") if isinstance(matched, dict) else None) or []
    check(
        "match_suggests_src",
        code == 200 and any(h.get("conversation_id") == src for h in hits),
        str(matched)[:400],
    )
    # Match must not create dst workstreams.
    code, fresh_mem = _http("GET", f"{base}/conversations/{dst}/memory", token)
    fresh_items = (fresh_mem.get("items") if isinstance(fresh_mem, dict) else None) or []
    check("match_no_auto_import", len(fresh_items) == 0, f"items={len(fresh_items)}")

    code, imported = _http(
        "POST", f"{base}/conversations/{dst}/import-rollup", token,
        {
            "source_conversation_id": src,
            "user_key": user_key,
            "turn": 0,
        },
    )
    ok_import = code == 200 and isinstance(imported, dict) and imported.get("ok")
    n_imp = len((imported.get("imported") if isinstance(imported, dict) else None) or [])
    check("import_ok", ok_import and n_imp >= 1, str(imported)[:400])

    # Imported cards start paused — bind without identity should interrupt or NEW, not dump catalog.
    _pace()
    code, bound = _http(
        "POST", f"{base}/bind", token,
        {"conversation_id": dst, "message": "hello there", "turn": 1},
    )
    check("bind_after_import_http_ok", code == 200, str(bound)[:300])
    if isinstance(bound, dict):
        check(
            "bind_does_not_expose_catalog_blob",
            "catalog" not in json.dumps(bound.get("l1_expose") or {}).lower(),
            str(bound.get("transition")),
        )

    # Prove catalog survives a new catalog-touch cycle (durable path).
    code, cat2 = _http("GET", f"{base}/catalog/{src}?user_key={user_key}", token)
    check(
        "catalog_get_src_after",
        code == 200 and isinstance(cat2, dict) and (cat2.get("entry") or {}).get("conversation_id") == src,
        str(cat2)[:300],
    )

    out["ok"] = all(c["ok"] for c in checks)
    return out


def main() -> int:
    project = os.getenv("GCP_PROJECT", DEFAULT_PROJECT)
    region = os.getenv("GCP_REGION", DEFAULT_REGION)
    result = run(project, region)
    out_path = os.getenv("CF_POC_OUT", "eval/out/catalog_h2_cloud_smoke.json")
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
