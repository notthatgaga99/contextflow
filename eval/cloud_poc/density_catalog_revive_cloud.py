"""Live density revive: deepen one hop → archive → match → import → SELECT.

Paced Free Trial Vertex. Fail-closed: match does not auto-merge; import is paused
until bind SELECT. No gate retune.

  python -m eval.cloud_poc.density_catalog_revive_cloud
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


def _turn(base: str, token: str, cid: str, message: str, turn: int) -> tuple[int, dict | str]:
    _pace()
    return _http(
        "POST", f"{base}/turn", token,
        {"conversation_id": cid, "message": message, "turn": turn},
    )


def run(project: str = DEFAULT_PROJECT, region: str = DEFAULT_REGION) -> dict:
    suffix = uuid.uuid4().hex[:8]
    src = f"dens-src-{suffix}"
    dst = f"dens-dst-{suffix}"
    user_key = f"dens-user-{suffix}"
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
        checks.append({"name": name, "ok": bool(ok), "detail": detail[:500]})

    code, health = _http("GET", f"{base}/health", token)
    check(
        "health_catalog_firestore",
        code == 200
        and isinstance(health, dict)
        and health.get("catalog_backend") == "firestore",
        str(health)[:400] if isinstance(health, dict) else str(health),
    )

    # Density on JWT hop (several deepening turns), then a second hop for contrast.
    density_turns = [
        (1, "JWT refresh still returns 401 on the auth path"),
        (2, "TTL looks wrong — set refresh TTL to 5 minutes on the auth service"),
        (3, "also check aud claim must be api.internal for JWT"),
        (4, "cookie path for refresh is still broken on JWT"),
        (5, "switch: navy peplum dress for the formal corporate evening"),
    ]
    last_jwt_task = None
    for turn, msg in density_turns:
        code, data = _turn(base, token, src, msg, turn)
        ok = code == 200 and isinstance(data, dict)
        check(f"density_turn_{turn}", ok, str(data)[:350])
        if ok and turn <= 4 and data.get("task_id"):
            last_jwt_task = data.get("task_id")

    code, roll = _http("GET", f"{base}/conversations/{src}/rollup", token)
    open_count = int(roll.get("open_count") or 0) if isinstance(roll, dict) else 0
    check("rollup_dense", code == 200 and open_count >= 1, str(roll)[:400])

    code, archived = _http(
        "POST", f"{base}/conversations/{src}/archive?user_key={user_key}", token,
    )
    check("archive_ok", code == 200 and isinstance(archived, dict) and archived.get("ok"),
          str(archived)[:300])

    code, matched = _http(
        "GET",
        f"{base}/catalog/match?q=JWT+TTL+aud+refresh&user_key={user_key}&limit=3",
        token,
    )
    hits = (matched.get("matches") if isinstance(matched, dict) else None) or []
    check(
        "match_surfaces_src",
        code == 200 and any(h.get("conversation_id") == src for h in hits),
        str(matched)[:400],
    )

    code, imported = _http(
        "POST", f"{base}/conversations/{dst}/import-rollup", token,
        {"source_conversation_id": src, "user_key": user_key, "turn": 0},
    )
    rows = (imported.get("imported") if isinstance(imported, dict) else None) or []
    check("import_paused", code == 200 and len(rows) >= 1, str(imported)[:400])
    auth_row = next(
        (r for r in rows if "auth" in (r.get("title") or "").lower()
         or "jwt" in (r.get("title") or "").lower()),
        rows[0] if rows else None,
    )
    imported_auth_id = (auth_row or {}).get("new_workstream_id") if auth_row else None

    # SELECT revive: distinctive JWT identity after density + import.
    _pace()
    code, bound = _http(
        "POST", f"{base}/bind", token,
        {
            "conversation_id": dst,
            "message": "Final check: JWT 401 after refresh — TTL 5 minutes and aud api.internal",
            "turn": 1,
        },
    )
    check("select_bind_http_ok", code == 200 and isinstance(bound, dict), str(bound)[:400])
    if isinstance(bound, dict):
        trans = bound.get("transition")
        tid = bound.get("task_id")
        l1 = str(bound.get("l1_expose") or "")
        interrupt = bound.get("interrupt") is True
        # Prefer ACT on imported auth; CLARIFY is acceptable under seed overlap (fail-closed).
        # NEW on an unrelated fresh card is wrong for this revive probe.
        clarify_ok = interrupt and trans == "CLARIFY"
        act_on_import = (
            not interrupt
            and bool(imported_auth_id)
            and tid == imported_auth_id
            and trans in ("SWITCH", "RETURN", "CONTINUE")
        )
        check(
            "select_or_clarify_not_wrong_act",
            act_on_import or clarify_ok,
            f"transition={trans} task={tid} imported_auth={imported_auth_id} interrupt={interrupt}",
        )
        if act_on_import:
            blob = l1.lower()
            check(
                "l1_has_jwt_identity",
                "jwt" in blob or "ttl" in blob or "401" in blob or "aud" in blob,
                l1[:300],
            )
            check(
                "l1_no_dress_bleed",
                "peplum" not in blob and "navy" not in blob,
                l1[:300],
            )

    out["source_jwt_task"] = last_jwt_task
    out["imported_auth_id"] = imported_auth_id
    out["ok"] = all(c["ok"] for c in checks)
    return out


def main() -> int:
    project = os.getenv("GCP_PROJECT", DEFAULT_PROJECT)
    region = os.getenv("GCP_REGION", DEFAULT_REGION)
    # Avoid colliding with other smokes that set CF_POC_OUT.
    out_path = os.getenv(
        "CF_DENSITY_OUT",
        "eval/out/density_catalog_revive_cloud.json",
    )
    result = run(project, region)
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
