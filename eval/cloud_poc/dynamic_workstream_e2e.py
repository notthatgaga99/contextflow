"""Dynamic NEW workstream E2E — no seed flags, authenticated HTTP only."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from eval.cloud_poc.gcp_cli import gcloud
from eval.cloud_poc.real_cloud_run_durability import (
    SERVICE,
    _force_new_revision,
    _http,
    _memory,
    _turn,
    _url,
)

FORBIDDEN_SEED_FLAGS = (
    "CF_SEED_E2E",
    "CF_SEED_TEN",
    "CF_SEED_ABCD",
    "CF_SMOKE_FIXTURE",
)

RUN_SCRIPT: list[tuple[int, str]] = [
    (1, "I need to figure out why my espresso machine keeps leaking water."),
    (2, "Separate issue: my tax filing deadline is next month and I have not started."),
    (3, "Also I need to plan a weekend hiking trip in the Dolomites."),
    (4, "Going back to the espresso machine — is it still leaking?"),
]

POST_RESTART: list[tuple[int, str]] = [
    (5, "Right, the espresso machine problem — what was going wrong again?"),
]

DEFAULT_REPS = int(os.getenv("CF_DYNAMIC_REPS", "10"))
DEFAULT_MAX_USD = float(os.getenv("CF_DYNAMIC_MAX_USD", "6.0"))
EST_CALLS_PER_REP = 20
EST_USD_PER_CALL = float(os.getenv("CF_POC_USD_PER_CALL_EST", "0.027"))


@dataclass
class RepRecord:
    rep_id: str
    conversation_id: str
    revision: str
    revision_after: str | None = None
    new_workstream_created: bool = False
    new_task_id: str | None = None
    extraction_success: bool = False
    extract_committed: bool = False
    registry_persisted: bool = False
    memory_persisted: bool = False
    return_success: bool = False
    working_context_ok: bool = False
    revision_survival: bool = False
    duplicate_registry_count: int = 0
    duplicate_memory_count: int = 0
    contamination: bool = False
    isolation_ok: bool = True
    isolation: dict = field(default_factory=dict)
    turns: list[dict] = field(default_factory=list)
    error: str | None = None


def _token() -> str:
    return gcloud("auth", "print-identity-token").stdout.strip()


def _revision(project: str, region: str) -> str:
    return gcloud(
        "run", "services", "describe", SERVICE,
        f"--project={project}", f"--region={region}",
        "--format=value(status.latestReadyRevisionName)",
    ).stdout.strip()


def _tasks(base: str, token: str, cid: str) -> dict:
    code, data = _http("GET", f"{base}/conversations/{cid}/tasks", token)
    if code != 200:
        raise RuntimeError(f"tasks failed {code}: {data}")
    return data


def _working_context(base: str, token: str, cid: str, task_id: str) -> dict:
    code, data = _http(
        "GET",
        f"{base}/conversations/{cid}/working-context?task_id={task_id}",
        token,
    )
    if code != 200:
        raise RuntimeError(f"wc failed {code}: {data}")
    return data


def _verify_seed_off(project: str, region: str) -> dict[str, str]:
    env = gcloud(
        "run", "services", "describe", SERVICE,
        f"--project={project}", f"--region={region}",
        "--format=json(spec.template.spec.containers[0].env)",
    ).stdout
    data = json.loads(env) if env.strip() else []
    values = {e.get("name"): e.get("value", "1") for e in data if isinstance(e, dict)}
    status = {}
    for flag in FORBIDDEN_SEED_FLAGS:
        status[flag] = values.get(flag, "0")
    return status


def _run_rep(base: str, token: str, *, rep_id: str, revision: str) -> RepRecord:
    cid = f"poc-dyn-{uuid.uuid4().hex[:8]}"
    rec = RepRecord(rep_id=rep_id, conversation_id=cid, revision=revision)
    try:
        for turn_n, msg in RUN_SCRIPT:
            r = _turn(base, token, cid, msg, turn_n)
            rec.turns.append({
                "turn": turn_n,
                "transition": r.get("transition"),
                "task_id": r.get("task_id"),
                "extract_ok": r.get("extract_ok"),
                "extract_committed": r.get("extract_committed"),
                "correlation_id": r.get("correlation_id"),
            })
            if turn_n == 1:
                rec.new_workstream_created = r.get("transition") == "NEW"
                rec.new_task_id = r.get("task_id")
                rec.extract_committed = bool(r.get("extract_committed"))
                # extract_ok alone is insufficient — abstain returns ok with zero items.
                rec.extraction_success = bool(
                    r.get("extract_committed")
                    if r.get("extract_committed") is not None
                    else r.get("extract_ok")
                )

        tasks = _tasks(base, token, cid)
        task_ids = [t.get("id") for t in tasks.get("tasks", [])]
        rec.duplicate_registry_count = len(task_ids) - len(set(task_ids))
        rec.registry_persisted = rec.new_task_id in task_ids if rec.new_task_id else False

        mem = _memory(base, token, cid)
        espresso_items = [
            i for i in mem.get("items") or []
            if rec.new_task_id and i.get("workstream_id") == rec.new_task_id
        ]
        rec.memory_persisted = len(espresso_items) >= 1
        # Require durable memory on the new workstream — stronger than extract_ok.
        rec.extraction_success = bool(rec.extraction_success and rec.memory_persisted)
        texts = [i.get("text", "").lower() for i in espresso_items if i.get("status") == "asserted"]
        rec.duplicate_memory_count = len(texts) - len(set(texts))

        turn4 = next(t for t in rec.turns if t["turn"] == 4)
        rec.return_success = (
            turn4.get("task_id") == rec.new_task_id
            and turn4.get("transition") in ("RETURN", "CONTINUE", "SWITCH")
        )

        if rec.new_task_id:
            wc = _working_context(base, token, cid, rec.new_task_id)
            inc = wc.get("included") or {}
            facts = [str(x).lower() for x in (inc.get("facts") or [])]
            decisions = [str(x).lower() for x in (inc.get("decisions") or [])]
            combined = " ".join(facts + decisions)
            rec.contamination = any(tok in combined for tok in ("tax", "dolomites", "hiking"))
            # Working context for the NEW workstream should include its own memory text.
            t1_blob = " ".join(
                (i.get("text") or "").lower() for i in espresso_items if i.get("status") == "asserted"
            )
            rec.working_context_ok = (
                rec.memory_persisted
                and not rec.contamination
                and (any(tok in combined for tok in ("espresso", "leak", "leaking", "machine"))
                     or any(tok in combined for tok in t1_blob.split()[:8] if len(tok) > 4))
            )

        rev_after = _force_new_revision(
            os.getenv("GCP_PROJECT", "contextflow-506414"),
            os.getenv("GCP_REGION", "asia-south1"),
        )
        rec.revision_after = rev_after
        time.sleep(10)

        for turn_n, msg in POST_RESTART:
            r = _turn(base, token, cid, msg, turn_n)
            rec.turns.append({
                "turn": turn_n,
                "transition": r.get("transition"),
                "task_id": r.get("task_id"),
                "extract_ok": r.get("extract_ok"),
                "extract_committed": r.get("extract_committed"),
                "correlation_id": r.get("correlation_id"),
            })

        mem_after = _memory(base, token, cid)
        espresso_after = [
            i for i in mem_after.get("items") or []
            if rec.new_task_id and i.get("workstream_id") == rec.new_task_id
        ]
        rec.revision_survival = len(espresso_after) >= 1 and rec.registry_persisted

        iso_cid = f"{cid}-iso"
        iso_pause = float(os.getenv("CF_ISOLATION_PAUSE_S", "2.0"))
        iso_retries = int(os.getenv("CF_ISOLATION_RETRIES", "3"))
        iso_backoff = float(os.getenv("CF_ISOLATION_BACKOFF_S", "3.0"))
        time.sleep(iso_pause)
        iso_t0 = time.perf_counter()
        iso_code, iso_data = _http("POST", f"{base}/turn", token, {
            "conversation_id": iso_cid,
            "message": "Docker pipeline keeps failing in CI.",
            "turn": 1,
        })
        attempts = 1
        while iso_code != 200 and attempts <= iso_retries:
            detail = iso_data.get("detail") if isinstance(iso_data, dict) else None
            rate_shaped = iso_code == 429 or (
                iso_code == 500 and (
                    (isinstance(detail, dict) and detail.get("error") == "turn_failed")
                    or (isinstance(detail, str) and "turn_failed" in detail)
                )
            )
            if not rate_shaped:
                break
            time.sleep(iso_backoff * (2 ** (attempts - 1)))
            iso_code, iso_data = _http("POST", f"{base}/turn", token, {
                "conversation_id": iso_cid,
                "message": "Docker pipeline keeps failing in CI.",
                "turn": 1,
            })
            attempts += 1
        iso_latency = round((time.perf_counter() - iso_t0) * 1000, 1)
        iso_corr = None
        if isinstance(iso_data, dict):
            iso_corr = iso_data.get("correlation_id")
            if not iso_corr and isinstance(iso_data.get("detail"), dict):
                iso_corr = iso_data["detail"].get("correlation_id")
        err_cat = None
        if iso_code == 200:
            leak = [i for i in _memory(base, token, cid).get("items") or []
                    if i.get("conversation_id") == iso_cid]
            rec.isolation_ok = len(leak) == 0
            err_cat = None if rec.isolation_ok else "cross_conversation_leak"
        else:
            rec.isolation_ok = False
            if iso_code == 429:
                err_cat = "vertex_resource_exhausted"
            elif iso_code == 500:
                err_cat = "turn_failed_http_500"
            else:
                err_cat = f"http_{iso_code}"
            rec.error = f"isolation:{err_cat}:{iso_code}"
        rec.isolation = {
            "http_status": iso_code,
            "revision": rec.revision_after or revision,
            "correlation_id": iso_corr,
            "error_category": err_cat,
            "latency_ms": iso_latency,
            "attempts": attempts,
            "firestore_ops": "none_in_harness",
        }
    except Exception as exc:
        rec.error = str(exc)[:500]
    return rec


def run(
    project: str = "contextflow-506414",
    region: str = "asia-south1",
    *,
    reps: int = DEFAULT_REPS,
    max_usd: float = DEFAULT_MAX_USD,
) -> dict[str, Any]:
    seed_status = _verify_seed_off(project, region)
    if any(v not in ("0", "", None) for v in seed_status.values()):
        return {
            "experiment": "dynamic_workstream_e2e",
            "ok": False,
            "error": "seed_flags_enabled",
            "seed_flags": seed_status,
        }

    base = _url(project, region)
    token = _token()
    revision = _revision(project, region)
    records: list[RepRecord] = []
    vertex_est = 0

    for i in range(reps):
        if vertex_est * EST_USD_PER_CALL > max_usd:
            break
        rec = _run_rep(base, token, rep_id=f"rep-{i+1:02d}", revision=revision)
        records.append(rec)
        vertex_est += EST_CALLS_PER_REP

    def _pass(fn):
        return sum(1 for r in records if not r.error and fn(r))

    n = len(records)
    result = {
        "experiment": "dynamic_workstream_e2e",
        "service": SERVICE,
        "base_url": base,
        "revision": revision,
        "seed_flags": seed_status,
        "reps_requested": reps,
        "reps_completed": n,
        "results": {
            "new_workstream_created": _pass(lambda r: r.new_workstream_created),
            "extraction_success": _pass(lambda r: r.extraction_success),
            "registry_persisted": _pass(lambda r: r.registry_persisted),
            "memory_persisted": _pass(lambda r: r.memory_persisted),
            "return_success": _pass(lambda r: r.return_success),
            "working_context_ok": _pass(lambda r: r.working_context_ok),
            "revision_survival": _pass(lambda r: r.revision_survival),
            "duplicate_registry_zero": _pass(lambda r: r.duplicate_registry_count == 0),
            "duplicate_memory_zero": _pass(lambda r: r.duplicate_memory_count == 0),
            "contamination_zero": _pass(lambda r: not r.contamination),
            "isolation_ok": _pass(lambda r: r.isolation_ok),
        },
        "vertex_estimate": {
            "calls": vertex_est,
            "usd": round(vertex_est * EST_USD_PER_CALL, 3),
            "ceiling": max_usd,
        },
        "reps": [r.__dict__ for r in records],
        "ok": (
            n >= 10
            and _pass(lambda r: r.new_workstream_created) >= max(9, n - 1)
            and _pass(lambda r: r.memory_persisted) >= max(9, n - 1)
            and _pass(lambda r: r.revision_survival) >= max(9, n - 1)
            and all(r.duplicate_registry_count == 0 for r in records)
        ),
    }
    return result


def main() -> int:
    out = run()
    path = os.getenv("CF_DYNAMIC_OUT", "eval/out/dynamic_workstream_e2e.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
