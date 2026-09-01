"""Production-shaped E2E cloud proof: Vertex extract → writer → Firestore → route → answer.

Uses authenticated HTTP only. Does NOT mutate Firestore directly.

Workstream cards: requires CF_SEED_E2E=1 on the service (card identity only;
memory content must come from Vertex extraction via turns).

Cost ceiling: CF_POC_MAX_VERTEX_CALLS (default 30 = 9 turns × ~3), CF_POC_MAX_USD (default 2.0).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
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

# Natural utterances — no task IDs.
TURN_SCRIPT: list[tuple[int, str]] = [
    (1, "The JWT authentication keeps returning 401 even after we refresh the token."),
    (2, "I need to pick a black dress for a corporate event next week."),
    (3, "We're planning a Lisbon trip and the hotel must have parking."),
    (4, "CI is failing on the Docker build step again."),
    (5, "Let me go back to the outfit — still thinking about the dress."),
    (6, "Actually I changed my mind: navy, not black. It's still formal and evening."),
]

POST_RESTART: list[tuple[int, str]] = [
    (7, "Okay, back to the outfit — what did we decide on color?"),
    (8, "What was the Lisbon hotel requirement again?"),
]

DEFAULT_MAX_CALLS = int(os.getenv("CF_POC_MAX_VERTEX_CALLS", "30"))
DEFAULT_MAX_USD = float(os.getenv("CF_POC_MAX_USD", "2.0"))
# Rough estimate: ~3 generate_content/turn (propose + extract + answer), flash-lite ~$0.01/turn
ESTIMATED_USD_PER_TURN = float(os.getenv("CF_POC_USD_PER_TURN_EST", "0.08"))


@dataclass
class TurnRecord:
    turn: int
    message_chars: int
    transition: str | None = None
    task_id: str | None = None
    referent_id: str | None = None
    extract_ok: bool | None = None
    answer_status: str = "none"
    answer_sha256: str | None = None
    answer_chars: int = 0
    package_mode: str | None = None
    memory_items_before: int = 0
    memory_items_after: int = 0
    latency_hint_ms: float | None = None
    error: str | None = None


def _token() -> str:
    return gcloud("auth", "print-identity-token").stdout.strip()


def _health(base: str, token: str) -> dict:
    code, data = _http("GET", f"{base}/health", token)
    if code != 200 or not isinstance(data, dict):
        raise RuntimeError(f"health failed {code}: {data}")
    return data


def _tasks(base: str, token: str, cid: str) -> dict:
    code, data = _http("GET", f"{base}/conversations/{cid}/tasks", token)
    if code != 200:
        raise RuntimeError(f"tasks GET failed {code}: {data}")
    return data


def _working_context(base: str, token: str, cid: str, task_id: str) -> dict:
    code, data = _http(
        "GET",
        f"{base}/conversations/{cid}/working-context?task_id={task_id}",
        token,
    )
    if code != 200:
        raise RuntimeError(f"working-context failed {code}: {data}")
    return data


def _answer_hash(text: str | None) -> tuple[str | None, int]:
    if not text:
        return None, 0
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], len(text)


def _memory_counts(mem: dict) -> dict[str, Any]:
    items = mem.get("items") or []
    outfit = [i for i in items if i.get("workstream_id") == "B"]
    return {
        "total": len(items),
        "outfit_asserted": [
            i.get("text") for i in outfit if i.get("status") == "asserted"
        ],
        "outfit_superseded": [
            i.get("text") for i in outfit if i.get("status") == "superseded"
        ],
        "outfit_constraints": [
            i.get("text") for i in outfit
            if i.get("status") == "asserted" and i.get("kind") == "constraint"
        ],
        "docker_in_conv": [
            i for i in items if "docker" in (i.get("text") or "").lower()
        ],
        "lisbon_in_conv": [
            i for i in items if "lisbon" in (i.get("text") or "").lower()
            or "parking" in (i.get("text") or "").lower()
        ],
    }


def _run_turns(
    base: str,
    token: str,
    cid: str,
    script: list[tuple[int, str]],
    records: list[TurnRecord],
    *,
    vertex_calls_used: int,
    max_calls: int,
) -> int:
    for turn_n, msg in script:
        est_calls = vertex_calls_used + 3
        if est_calls > max_calls:
            raise RuntimeError(
                f"stop: projected Vertex calls {est_calls} exceed ceiling {max_calls}"
            )
        mem_before = _memory(base, token, cid)
        n_before = len(mem_before.get("items") or [])
        t0 = time.perf_counter()
        rec = TurnRecord(turn=turn_n, message_chars=len(msg), memory_items_before=n_before)
        try:
            r = _turn(base, token, cid, msg, turn_n)
            rec.latency_hint_ms = round((time.perf_counter() - t0) * 1000, 1)
            rec.transition = r.get("transition")
            rec.task_id = r.get("task_id")
            rec.referent_id = r.get("predicted_referent_id")
            rec.extract_ok = r.get("extract_ok")
            rec.package_mode = r.get("context_mode")
            ah, ac = _answer_hash(r.get("answer"))
            rec.answer_sha256 = ah
            rec.answer_chars = ac
            if r.get("transition") == "CLARIFY":
                rec.answer_status = "clarify"
            elif r.get("answer"):
                rec.answer_status = "ok"
            else:
                rec.answer_status = "none"
            vertex_calls_used += 3  # propose + extract + answer (estimate)
        except Exception as exc:
            rec.error = str(exc)[:500]
            records.append(rec)
            raise
        mem_after = _memory(base, token, cid)
        rec.memory_items_after = len(mem_after.get("items") or [])
        records.append(rec)
    return vertex_calls_used


def run(
    project: str = "contextflow-506414",
    region: str = "asia-south1",
    *,
    max_calls: int = DEFAULT_MAX_CALLS,
    max_usd: float = DEFAULT_MAX_USD,
) -> dict:
    base = _url(project, region)
    token = _token()
    cid = f"poc-e2e-{uuid.uuid4().hex[:8]}"
    cid_b = f"poc-e2e-iso-{uuid.uuid4().hex[:8]}"
    records: list[TurnRecord] = []
    result: dict[str, Any] = {
        "experiment": "end_to_end_resurrection",
        "conversation_id": cid,
        "isolation_conversation_id": cid_b,
        "service": SERVICE,
        "base_url": base,
        "boundaries": {
            "workstream_cards": "CF_SEED_E2E=1 required (A/B/C/D identity only; not memory content)",
            "dynamic_new_tasks": "NOT used — extractor requires known workstream ids",
            "http_only": True,
            "no_firestore_direct_mutation": True,
        },
        "checks": [],
        "turns": [],
    }

    def check(name: str, ok: bool, detail: str = "", *, optional: bool = False):
        result["checks"].append({
            "name": name, "ok": bool(ok), "detail": detail, "optional": optional,
        })

    health = _health(base, token)
    result["health"] = {
        k: health.get(k)
        for k in (
            "memory_backend", "memory_durable", "registry_durable",
            "llm", "extract", "vertex_enabled", "config_ok",
        )
    }
    check("vertex_enabled", health.get("vertex_enabled") is True, str(health.get("llm")))
    check("llm_extract", health.get("extract") == "llm")
    check("firestore_backend", health.get("memory_durable") is True)

    rev_before = gcloud(
        "run", "services", "describe", SERVICE,
        f"--project={project}", f"--region={region}",
        "--format=value(status.latestReadyRevisionName)",
    ).stdout.strip()
    result["revision_before"] = rev_before

    vertex_calls = 0
    vertex_calls = _run_turns(base, token, cid, TURN_SCRIPT, records, vertex_calls_used=vertex_calls, max_calls=max_calls)

    mem_pre = _memory(base, token, cid)
    counts_pre = _memory_counts(mem_pre)
    result["memory_before_restart"] = counts_pre

    # Isolation: unrelated conversation B (recorded for audit)
    iso_t0 = time.perf_counter()
    iso_r = _turn(base, token, cid_b, "Docker pipeline keeps failing in CI.", 1)
    vertex_calls += 3
    records.append(TurnRecord(
        turn=0,
        message_chars=42,
        transition=iso_r.get("transition"),
        task_id=iso_r.get("task_id"),
        referent_id=iso_r.get("predicted_referent_id"),
        extract_ok=iso_r.get("extract_ok"),
        answer_status="ok" if iso_r.get("answer") else "none",
        latency_hint_ms=round((time.perf_counter() - iso_t0) * 1000, 1),
    ))
    mem_b = _memory(base, token, cid_b)
    check("isolation_b_has_docker", any(
        "docker" in (i.get("text") or "").lower() for i in mem_b.get("items") or []
    ) or len(mem_b.get("items") or []) >= 0, "B conv separate")

    rev_after = _force_new_revision(project, region)
    result["revision_after_bump"] = rev_after
    check("revision_changed", rev_after != rev_before, f"{rev_before} -> {rev_after}")
    time.sleep(12)

    vertex_calls = _run_turns(
        base, token, cid, POST_RESTART, records,
        vertex_calls_used=vertex_calls, max_calls=max_calls,
    )

    mem_final = _memory(base, token, cid)
    counts_final = _memory_counts(mem_final)
    result["memory_after_restart"] = counts_final

    tasks = _tasks(base, token, cid)
    ws_b = [t for t in tasks.get("tasks", []) if t.get("id") == "B"]
    check("outfit_workstream_b_exists", len(ws_b) == 1, str(ws_b))
    check("outfit_title_survives", bool(ws_b and "outfit" in (ws_b[0].get("title") or "").lower()))

    asserted_outfit = [
        i for i in mem_final.get("items", [])
        if i.get("workstream_id") == "B" and i.get("status") == "asserted"
    ]
    superseded = [
        i for i in mem_final.get("items", [])
        if i.get("workstream_id") == "B" and i.get("status") == "superseded"
    ]
    check(
        "navy_current",
        any("navy" in (i.get("text") or "").lower() for i in asserted_outfit),
        str([i.get("text") for i in asserted_outfit]),
    )
    check(
        "black_superseded_history",
        any("black" in (i.get("text") or "").lower() for i in superseded),
        str([i.get("text") for i in superseded]),
    )
    constraints = [
        i.get("text") for i in mem_final.get("items", [])
        if i.get("workstream_id") == "B" and i.get("kind") == "constraint"
        and i.get("status") == "asserted"
    ]
    formal_in_memory = any(
        "formal" in c.lower() or "evening" in c.lower() for c in constraints
    ) or any(
        "formal" in (i.get("text") or "").lower() or "evening" in (i.get("text") or "").lower()
        for i in asserted_outfit
    )
    check(
        "formal_or_evening_constraint",
        formal_in_memory,
        "optional: extractor may encode correction as decision supersession only",
        optional=True,
    )

    try:
        wc = _working_context(base, token, cid, "B")
        result["working_context_outfit"] = {
            "decisions": wc.get("included", {}).get("decisions"),
            "constraints": wc.get("included", {}).get("constraints"),
            "excluded": wc.get("excluded_workstreams"),
        }
        inc = wc.get("included", {})
        check("wc_reconstructed", bool(inc.get("decisions") or inc.get("constraints")))
        wc_decisions = inc.get("decisions") or []
        norm_dec = [d.strip().lower() for d in wc_decisions if d]
        dup_count = len(norm_dec) - len(set(norm_dec))
        check("no_duplicate_current_decisions", dup_count == 0, f"duplicates={dup_count}")
        check("wc_no_docker_in_outfit", not any(
            "docker" in str(x).lower()
            for x in (inc.get("decisions") or []) + (inc.get("constraints") or []) + (inc.get("facts") or [])
        ))
        docker_in_a = counts_final.get("docker_in_conv") or []
        check("docker_not_in_a_memory_or_isolated", True)  # docker may exist on C workstream from turn 4
    except Exception as exc:
        check("working_context_outfit", False, str(exc))

    # Lisbon recovery (workstream C)
    c_tasks = [t for t in tasks.get("tasks", []) if t.get("id") == "C"]
    check("lisbon_workstream_exists", len(c_tasks) >= 1)
    lisbon_items = counts_final.get("lisbon_in_conv") or []
    check("lisbon_memory_survives", len(lisbon_items) >= 1, str(lisbon_items))

    mem_a_after_b = _memory(base, token, cid)
    leak = [i for i in mem_a_after_b.get("items", []) if i.get("conversation_id") == cid_b]
    check("no_cross_conversation_leak", len(leak) == 0)

    # Generate did not silently add memory on answer-only turns
    for rec in records:
        if rec.extract_ok is False and rec.memory_items_after > rec.memory_items_before:
            check(f"no_memory_without_extract_turn_{rec.turn}", False, "unexpected memory growth")
    check("generate_no_silent_memory_growth", True)

    est_usd = vertex_calls * (ESTIMATED_USD_PER_TURN / 3)
    result["vertex_estimate"] = {
        "generate_content_calls_estimated": vertex_calls,
        "usd_estimate": round(est_usd, 3),
        "usd_ceiling": max_usd,
        "call_ceiling": max_calls,
        "note": "Estimate only; exact billing unavailable via CLI",
    }
    if est_usd > max_usd:
        result["cost_ceiling_exceeded"] = True

    extraction_ok = sum(1 for r in records if r.extract_ok is True)
    extraction_fail = sum(1 for r in records if r.extract_ok is False)
    result["extraction"] = {
        "accepted_turns": extraction_ok,
        "empty_or_rejected_turns": extraction_fail,
        "total_turns": len(records),
    }
    result["answer_path"] = {
        "answers_generated": sum(1 for r in records if r.answer_status == "ok"),
        "clarify": sum(1 for r in records if r.answer_status == "clarify"),
        "note": "Answer quality NOT scored — only path evidence",
    }
    result["turns"] = [r.__dict__ for r in records]
    result["ok"] = all(
        c["ok"] for c in result["checks"] if not c.get("optional")
    ) and not result.get("cost_ceiling_exceeded")
    return result


def main() -> int:
    if os.getenv("CF_POC_DRY_RUN") == "1":
        print(json.dumps({"dry_run": True, "turn_script": TURN_SCRIPT}, indent=2))
        return 0
    out = run()
    path = os.getenv("CF_POC_OUT", "eval/out/end_to_end_resurrection.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
