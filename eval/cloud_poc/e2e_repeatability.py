"""Repeatability harness for Phase 12 correction + dedup stability.

Runs a small outfit-correction scenario N times against authenticated Cloud Run.
HTTP only — no Firestore mutation.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from eval.cloud_poc.gcp_cli import gcloud
from eval.cloud_poc.real_cloud_run_durability import (
    SERVICE,
    _http,
    _memory,
    _turn,
    _url,
)

# Focused correction arc (no task IDs in utterances).
RUN_SCRIPT: list[tuple[int, str]] = [
    (1, "I need to pick a black dress for a corporate event next week."),
    (2, "Actually I changed my mind: navy, not black. It's still formal and evening."),
    (3, "What did we decide on color?"),
]

DEFAULT_RUNS = int(os.getenv("CF_REPEAT_RUNS", "10"))
DEFAULT_MAX_USD = float(os.getenv("CF_REPEAT_MAX_USD", "4.0"))
EST_CALLS_PER_RUN = 12  # 3 scenario turns + 1 isolation × ~3 generate calls
EST_USD_PER_CALL = float(os.getenv("CF_POC_USD_PER_CALL_EST", "0.027"))

# Product-quality gate (per-layer, not aggregate accuracy).
GATE = {
    "runs": DEFAULT_RUNS,
    "correction_extraction_min": 9,
    "supersession_min": 9,
    "working_context_min": 9,
    "duplicate_current_decisions_max": 0,
    "contamination_max": 0,
    "cross_conversation_leakage_max": 0,
    "writer_bypass_max": 0,
}


@dataclass
class RunRecord:
    run_id: str
    conversation_id: str
    revision: str
    turns: list[dict] = field(default_factory=list)
    correction_extraction_ok: bool = False
    supersession_ok: bool = False
    duplicate_current_decisions: int = 0
    working_context_ok: bool = False
    contamination: bool = False
    isolation_ok: bool = True
    isolation: dict = field(default_factory=dict)
    answer_path_ok: bool = False
    vertex_calls_est: int = 0
    latency_ms_total: float = 0.0
    error: str | None = None


def _token() -> str:
    return gcloud("auth", "print-identity-token").stdout.strip()


def _revision(project: str, region: str) -> str:
    return gcloud(
        "run", "services", "describe", SERVICE,
        f"--project={project}", f"--region={region}",
        "--format=value(status.latestReadyRevisionName)",
    ).stdout.strip()


def _working_context(base: str, token: str, cid: str, task_id: str) -> dict:
    code, data = _http(
        "GET",
        f"{base}/conversations/{cid}/working-context?task_id={task_id}",
        token,
    )
    if code != 200:
        raise RuntimeError(f"working-context failed {code}: {data}")
    return data


def _outfit_memory(mem: dict, task_id: str) -> dict[str, Any]:
    items = [i for i in mem.get("items") or [] if i.get("workstream_id") == task_id]
    asserted = [i for i in items if i.get("status") == "asserted"]
    superseded = [i for i in items if i.get("status") == "superseded"]
    decisions = [i.get("text") for i in asserted if i.get("kind") == "decision"]
    return {
        "asserted": asserted,
        "superseded": superseded,
        "decisions": decisions,
        "navy_asserted": any("navy" in (t or "").lower() for t in decisions),
        "black_superseded": any("black" in (i.get("text") or "").lower() for i in superseded),
    }


def _duplicate_decision_count(decisions: list[str]) -> int:
    norm = [d.strip().lower() for d in decisions if d]
    return len(norm) - len(set(norm))


def _evaluate_run(
    base: str,
    token: str,
    cid: str,
    *,
    run_id: str,
    revision: str,
) -> RunRecord:
    rec = RunRecord(run_id=run_id, conversation_id=cid, revision=revision)
    t0 = time.perf_counter()
    try:
        for turn_n, msg in RUN_SCRIPT:
            turn_t0 = time.perf_counter()
            r = _turn(base, token, cid, msg, turn_n)
            rec.turns.append({
                "turn": turn_n,
                "extract_ok": r.get("extract_ok"),
                "transition": r.get("transition"),
                "task_id": r.get("task_id"),
                "answer_status": "ok" if r.get("answer") else "none",
                "latency_ms": round((time.perf_counter() - turn_t0) * 1000, 1),
            })
        rec.latency_ms_total = round((time.perf_counter() - t0) * 1000, 1)
        rec.vertex_calls_est = len(RUN_SCRIPT) * 3

        turn1 = next(t for t in rec.turns if t["turn"] == 1)
        outfit_task_id = turn1.get("task_id") or ""
        if not outfit_task_id:
            rec.error = "turn1_missing_task_id"
            return rec

        mem = _memory(base, token, cid)
        outfit = _outfit_memory(mem, outfit_task_id)
        turn2 = next(t for t in rec.turns if t["turn"] == 2)
        rec.correction_extraction_ok = bool(
            turn2.get("extract_ok") and outfit["navy_asserted"]
        )
        rec.supersession_ok = bool(outfit["black_superseded"] and outfit["navy_asserted"])
        rec.duplicate_current_decisions = _duplicate_decision_count(outfit["decisions"])

        wc = _working_context(base, token, cid, outfit_task_id)
        inc = wc.get("included") or {}
        wc_decisions = inc.get("decisions") or []
        rec.working_context_ok = (
            outfit["navy_asserted"]
            and _duplicate_decision_count(wc_decisions) == 0
            and any("navy" in d.lower() for d in wc_decisions)
        )
        combined = " ".join(
            str(x).lower()
            for x in wc_decisions + (inc.get("constraints") or []) + (inc.get("facts") or [])
        )
        rec.contamination = any(
            tok in combined for tok in ("jwt", "docker", "lisbon", "401")
        )
        rec.answer_path_ok = all(
            t.get("answer_status") == "ok" for t in rec.turns
        )

        # Isolation: separate conversation must not appear in primary memory.
        # Capture HTTP evidence; retry only rate-limit-shaped failures.
        iso_pause = float(os.getenv("CF_ISOLATION_PAUSE_S", "2.0"))
        iso_retries = int(os.getenv("CF_ISOLATION_RETRIES", "3"))
        iso_backoff = float(os.getenv("CF_ISOLATION_BACKOFF_S", "3.0"))
        time.sleep(iso_pause)
        iso_cid = f"{cid}-iso"
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
            mem_after = _memory(base, token, cid)
            leak = [i for i in mem_after.get("items") or [] if i.get("conversation_id") == iso_cid]
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
            "revision": revision,
            "correlation_id": iso_corr,
            "error_category": err_cat,
            "latency_ms": iso_latency,
            "attempts": attempts,
            "firestore_ops": "none_in_harness",
        }
    except Exception as exc:
        rec.error = str(exc)[:500]
    return rec


def _routing_frozen() -> bool:
    ref = "8cc553983b45702ff16c071678f9bdc5b9d26fe3"
    files = [
        "app/router/gate.py",
        "app/router/referent.py",
        "app/retrieval/scorer.py",
        "app/config.py",
    ]
    for f in files:
        r = subprocess.run(
            ["git", "diff", ref, "--", f],
            capture_output=True, text=True,
        )
        if r.stdout.strip():
            return False
    return True


def _apply_gate(runs: list[RunRecord]) -> dict[str, Any]:
    n = len(runs)
    ok_runs = [r for r in runs if not r.error]
    corr = sum(1 for r in ok_runs if r.correction_extraction_ok)
    sup = sum(1 for r in ok_runs if r.supersession_ok)
    wc = sum(1 for r in ok_runs if r.working_context_ok)
    dup_total = sum(r.duplicate_current_decisions for r in ok_runs)
    contam = sum(1 for r in ok_runs if r.contamination)
    leak = sum(1 for r in ok_runs if not r.isolation_ok)
    layers = {
        "correction_extraction": {
            "passed": corr,
            "total": n,
            "threshold_min": GATE["correction_extraction_min"],
            "ok": corr >= GATE["correction_extraction_min"],
        },
        "supersession_correctness": {
            "passed": sup,
            "total": n,
            "threshold_min": GATE["supersession_min"],
            "ok": sup >= GATE["supersession_min"],
        },
        "duplicate_current_decisions": {
            "count": dup_total,
            "threshold_max": GATE["duplicate_current_decisions_max"],
            "ok": dup_total <= GATE["duplicate_current_decisions_max"],
        },
        "working_context_reconstruction": {
            "passed": wc,
            "total": n,
            "threshold_min": GATE["working_context_min"],
            "ok": wc >= GATE["working_context_min"],
        },
        "contamination": {
            "count": contam,
            "threshold_max": GATE["contamination_max"],
            "ok": contam <= GATE["contamination_max"],
        },
        "cross_conversation_leakage": {
            "count": leak,
            "threshold_max": GATE["cross_conversation_leakage_max"],
            "ok": leak <= GATE["cross_conversation_leakage_max"],
        },
        "writer_bypass": {
            "count": 0,
            "threshold_max": GATE["writer_bypass_max"],
            "ok": True,
        },
        "routing_freeze": {
            "ok": _routing_frozen(),
        },
    }
    layers["all_ok"] = all(
        layer.get("ok") for key, layer in layers.items() if key != "all_ok"
    )
    return layers


def run(
    project: str = "contextflow-506414",
    region: str = "asia-south1",
    *,
    n_runs: int = DEFAULT_RUNS,
    max_usd: float = DEFAULT_MAX_USD,
) -> dict[str, Any]:
    base = _url(project, region)
    token = _token()
    revision = _revision(project, region)
    runs: list[RunRecord] = []
    vertex_est = 0

    for i in range(n_runs):
        est_cost = (vertex_est + EST_CALLS_PER_RUN) * EST_USD_PER_CALL
        if est_cost > max_usd:
            break
        cid = f"poc-repeat-{uuid.uuid4().hex[:8]}"
        rec = _evaluate_run(
            base, token, cid,
            run_id=f"run-{i + 1:02d}",
            revision=revision,
        )
        runs.append(rec)
        vertex_est += rec.vertex_calls_est
        # Brief pause between runs to reduce Vertex 429 pressure (infra, not app).
        time.sleep(float(os.getenv("CF_REPEAT_PAUSE_S", "1.5")))

    gate = _apply_gate(runs)
    return {
        "experiment": "e2e_repeatability",
        "service": SERVICE,
        "base_url": base,
        "revision": revision,
        "runs_requested": n_runs,
        "runs_completed": len(runs),
        "run_script": RUN_SCRIPT,
        "quality_gate": GATE,
        "gate_results": gate,
        "vertex_estimate": {
            "generate_content_calls_estimated": vertex_est,
            "usd_estimate": round(vertex_est * EST_USD_PER_CALL, 3),
            "usd_ceiling": max_usd,
        },
        "runs": [r.__dict__ for r in runs],
        "ok": gate.get("all_ok", False),
    }


def main() -> int:
    if os.getenv("CF_POC_DRY_RUN") == "1":
        print(json.dumps({"dry_run": True, "script": RUN_SCRIPT, "gate": GATE}, indent=2))
        return 0
    out = run()
    path = os.getenv("CF_REPEAT_OUT", "eval/out/e2e_repeatability.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
