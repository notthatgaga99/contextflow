"""Authored organic-shaped interleaved slice scorer (Mock math — no Vertex).

Claim hygiene: not human_behavior, not production accuracy, gate frozen.

  python -m eval.organic.run
  python -m eval.organic.run --json eval/out/organic_slice.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.domain import Transition
from app.models.task import Task, TaskAnchor
from app.router.thread_discriminate import decide_discrimination
from app.router.topic_align import is_underspecified
from eval.ten_workstream.metrics import score_probe_row, summarize

ROOT = Path(__file__).resolve().parents[2]
DIR = Path(__file__).resolve().parent
SLICE = DIR / "slice_s03_mini.jsonl"
OUT_DEFAULT = ROOT / "eval" / "out" / "organic_slice.json"

BANNER = {
    "kind": "authored_organic_shaped",
    "human_behavior": False,
    "not_production_accuracy": True,
    "gate_frozen": True,
    "note": (
        "Authored interleaved mini-slice for layered metrics. "
        "Not real chat logs. Do not retune TAU/W_* from this file."
    ),
}


def _task(row: dict) -> Task:
    return Task(
        id=row["id"],
        title=row.get("title") or row["id"],
        retrieval_cues=list(row.get("cues") or []),
        anchor=TaskAnchor(
            goal=row.get("title") or "",
            open_loops=list(row.get("loops") or [row.get("title") or row["id"]]),
        ),
    )


def _load(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def _wc_ok(blob: str, needed: list[str], forbid: list[str]) -> tuple[bool, list[str], list[str]]:
    low = (blob or "").lower()
    missing = [n for n in needed if n.lower() not in low]
    leaked = [f for f in forbid if f.lower() in low]
    return (not missing and not leaked), missing, leaked


def _run_one(case: dict) -> dict:
    open_rows = case["open"]
    tasks = [_task(r) for r in open_rows]
    mem = {r["id"]: list(r.get("memory") or []) for r in open_rows}
    gate_tr = Transition[str(case["gate_transition"]).upper()]
    gate_tid = case.get("gate_task_id")
    active = case.get("active")
    msg = case["message"]

    decided = decide_discrimination(
        message=msg,
        gate_transition=gate_tr,
        gate_task_id=gate_tid,
        open_tasks=tasks,
        active_id=active,
        memory_texts_by_task=mem,
        underspecified=is_underspecified(msg),
    )

    if decided is None:
        final_tr = gate_tr
        final_tid = gate_tid
        reason = "keep_gate"
        region = "keep_gate"
    else:
        final_tr = decided.transition
        final_tid = decided.task_id
        reason = decided.reason
        region = decided.evidence.region

    acted = final_tr != Transition.CLARIFY
    gold_policy = case.get("gold_policy")
    gold_tid = case.get("gold_task_id")

    # Working-context proxy: card header + asserted memory (no generate).
    selected_blob = ""
    if final_tid:
        row = next((r for r in open_rows if r["id"] == final_tid), {})
        selected_blob = " ".join(
            [
                str(row.get("title") or ""),
                " ".join(row.get("cues") or []),
                " ".join(row.get("loops") or []),
                " ".join(mem.get(final_tid) or []),
            ]
        )
    needed = list(case.get("required_working_state") or [])
    forbid = list(case.get("forbidden_state") or [])
    sufficient, missing, leaked = _wc_ok(selected_blob, needed, forbid)
    cf_ok = sufficient if acted and gold_policy == "ACT" else None

    scored = score_probe_row(
        gold_task=gold_tid,
        gold_ref=None,
        gold_policy=gold_policy,
        selected_task=final_tid if acted else None,
        selected_ref=None,
        acted=acted,
        open_task_ids=[t.id for t in tasks],
        cf_sufficient_no_leak=cf_ok,
        thin_context=False,
        has_package=acted and bool(selected_blob.strip()),
        contamination=leaked if acted else None,
        supersession_ok=True,
        persist_ok=True,
        extract_status="n/a",
        answer_usable=None,
    )

    gold_tr = case.get("gold_transition") or []
    if isinstance(gold_tr, str):
        gold_tr = [gold_tr]
    tr_ok = final_tr.value in [t for t in gold_tr if t]
    if gold_policy == "CLARIFY":
        tr_ok = final_tr == Transition.CLARIFY
    tid_ok = True
    if gold_policy == "ACT" and gold_tid is not None:
        tid_ok = final_tid == gold_tid
    elif gold_policy == "CLARIFY":
        tid_ok = final_tr == Transition.CLARIFY

    probe_pass = (
        bool(scored.get("policy_match"))
        and not scored.get("wrong_act")
        and (scored.get("contamination") is not True)
        and (scored.get("working_context_sufficient") is not False)
        and (scored.get("task_match") is not False)
        and tr_ok
        and tid_ok
    )

    return {
        "id": case["id"],
        "dialogue_id": case.get("dialogue_id"),
        "turn_index": case.get("turn_index"),
        "utterance_kind": case.get("utterance_kind"),
        "message": msg,
        "gold_policy": gold_policy,
        "gold_task_id": gold_tid,
        "transition": final_tr.value,
        "task_id": final_tid,
        "reason": reason,
        "region": region,
        "pass": probe_pass,
        "missing_state": missing if acted else [],
        "leaked_state": leaked if acted else [],
        **scored,
        "source": case.get("source"),
        "human_behavior": False,
    }


def run(path: Path | None = None) -> dict:
    cases = _load(path or SLICE)
    rows = [_run_one(c) for c in cases]
    summary = summarize(rows)
    summary["wrong_act_total"] = sum(1 for r in rows if r.get("wrong_act"))
    summary["contamination_total"] = sum(1 for r in rows if r.get("contamination"))
    summary["pass_count"] = sum(1 for r in rows if r.get("pass"))
    summary["all_pass"] = summary["pass_count"] == len(rows) and summary["wrong_act_total"] == 0
    hops = sorted({
        tid
        for c in cases
        for tid in (r["id"] for r in c.get("open") or [])
    })
    return {
        **BANNER,
        "slice": str((path or SLICE).relative_to(ROOT)) if (path or SLICE).is_relative_to(ROOT) else str(path or SLICE),
        "n_probes": len(rows),
        "n_hops_in_slice": len(hops),
        "hop_ids": hops,
        "summary": summary,
        "probes": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--slice", type=Path, default=SLICE)
    args = ap.parse_args()
    payload = run(args.slice)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    s = payload["summary"]
    print(json.dumps({
        "all_pass": s.get("all_pass"),
        "pass": f"{s.get('pass_count')}/{payload['n_probes']}",
        "wrong_act": s.get("wrong_act_total"),
        "contamination": s.get("contamination_total"),
        "policy_match": s.get("policy_match"),
        "clarify_correct": s.get("clarify_correct"),
        "working_context": s.get("working_context_sufficient"),
        "wrote": str(args.json),
    }, indent=2))
    return 0 if s.get("all_pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
