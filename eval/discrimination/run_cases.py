"""Offline discrimination casefile scorer (Mock math path — no Vertex).

  python -m eval.discrimination.run_cases
  python -m eval.discrimination.run_cases --json eval/out/discrimination_cases.json

Reports per-bucket accuracy and (c_S, delta_I) for drift analysis.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.domain import Transition
from app.models.task import Task, TaskAnchor
from app.router.thread_discriminate import IdentityCues, decide_discrimination
from app.router.topic_align import is_underspecified

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases.jsonl"


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


def _load_cases(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def _cues_for_rows(open_rows: list[dict]) -> dict[str, IdentityCues]:
    out: dict[str, IdentityCues] = {}
    for r in open_rows:
        slots = tuple(s for s in (r.get("slots") or []) if s)
        entities = tuple(e for e in (r.get("entities") or []) if e)
        if slots or entities:
            out[r["id"]] = IdentityCues(slots=slots, entities=entities)
    return out


def _run_one(case: dict, *, ablate_slots: bool = False) -> dict:
    open_rows = case["open"]
    tasks = [_task(r) for r in open_rows]
    mem = {r["id"]: list(r.get("memory") or []) for r in open_rows}
    cues = {} if ablate_slots else _cues_for_rows(open_rows)
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
        identity_cues_by_task=cues or None,
        underspecified=is_underspecified(msg),
    )

    if decided is None:
        final_tr = gate_tr
        final_tid = gate_tid
        reason = "keep_gate"
        ev = {}
        # Still build evidence for plot via a decide call with forced path —
        # re-score by calling decide and reading None path: use score from a dummy
        from app.router.thread_discriminate import build_evidence, score_threads
        ev = build_evidence(score_threads(msg, tasks, mem)).to_dict()
        ev["region"] = ev.get("region") or "keep_gate"
    else:
        final_tr = decided.transition
        final_tid = decided.task_id
        reason = decided.reason
        ev = decided.evidence.to_dict()

    gold_tr = case.get("gold_transition") or []
    if isinstance(gold_tr, str):
        gold_tr = [gold_tr]
    # null in gold_transition means keep-gate with gold_task_id is OK
    allow_keep = None in gold_tr or "null" in gold_tr
    gold_tr_norm = [t for t in gold_tr if t not in (None, "null")]

    tr_ok = final_tr.value in gold_tr_norm or (
        allow_keep and decided is None and (
            case.get("gold_task_id") in (None, final_tid)
        )
    )
    # If keep_gate and gold wants CONTINUE on active with same task
    if decided is None and case.get("gold_task_id") and final_tid == case["gold_task_id"]:
        if "CONTINUE" in gold_tr_norm or allow_keep:
            tr_ok = True

    gold_tid = case.get("gold_task_id")
    if gold_tid is None and "CLARIFY" in gold_tr_norm:
        tid_ok = final_tr == Transition.CLARIFY
    elif gold_tid is None and "NEW" in gold_tr_norm:
        tid_ok = final_tr == Transition.NEW and final_tid is None
    else:
        tid_ok = final_tid == gold_tid

    ok = bool(tr_ok and tid_ok)
    return {
        "id": case["id"],
        "bucket": case.get("bucket"),
        "ok": ok,
        "final_transition": final_tr.value,
        "final_task_id": final_tid,
        "reason": reason,
        "gold_task_id": gold_tid,
        "gold_transition": gold_tr_norm,
        "c_S": ev.get("c_S"),
        "delta_I": ev.get("delta_I"),
        "high_confusion": ev.get("high_confusion"),
        "region": ev.get("region"),
        "winner_id": ev.get("winner_id"),
        "slot_hits": ev.get("slot_hits") or {},
        "notes": case.get("notes"),
        "used_identity_cues": bool(cues),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, default=CASES)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument(
        "--ablate-slots",
        action="store_true",
        help="Score without slot/entity I-channel (insight A/B).",
    )
    args = ap.parse_args()
    cases = _load_cases(args.cases)
    results = [_run_one(c, ablate_slots=args.ablate_slots) for c in cases]
    by_bucket: dict[str, list[bool]] = {}
    for r in results:
        by_bucket.setdefault(r["bucket"] or "?", []).append(r["ok"])
    n_ok = sum(1 for r in results if r["ok"])
    summary = {
        "n": len(results),
        "n_ok": n_ok,
        "accuracy": round(n_ok / max(len(results), 1), 3),
        "by_bucket": {
            b: {"n": len(v), "ok": sum(v), "acc": round(sum(v) / len(v), 3)}
            for b, v in sorted(by_bucket.items())
        },
        "failures": [r for r in results if not r["ok"]],
        "results": results,
        "literature_note": (
            "Casefile probes switch bind (genre vs identity), not memory-SaaS retrieval. "
            "Aligned with thread disentanglement + anti-similarity-only memory work; "
            "detour would be becoming DST/Mem0 instead of bind→L1."
        ),
    }
    out = json.dumps(summary, indent=2, ensure_ascii=False)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(out + "\n", encoding="utf-8")
        print(
            f"acc={summary['accuracy']} {summary['n_ok']}/{summary['n']} "
            f"fail={[f['id'] for f in summary['failures']]} wrote={args.json}",
            flush=True,
        )
    else:
        print(out)
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
