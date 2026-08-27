"""Model-strength control for context sufficiency. Not a benchmark.

Does not change routing, compiler semantics, cards, probes, or token accounting.
The only independent variable is the downstream answer model.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

from app.llm.ollama import OllamaLLM
from app.models.context import FULL_TASK, MERGED_COMPACT, REFERENT_COMPACT
from app.router.referent import loop_index_from_id
from eval.context_sufficiency import (
    run_provider,
    scenarios,
    summarize,
)

# Already installed. ~4.9 GB on disk; usable on 16 GB RAM. Do not pull another model.
ANSWER_MODEL = "llama3.1:8b"
BASELINE_MODEL = "qwen2.5:1.5b"

FAILURE_KEY = {
    "A": "missing selected-loop information",
    "B": "missing task-level information",
    "C": "genuinely required cross-loop information",
    "D": "model capability",
    "E": "prompt/rendering issue",
    "F": "resolver error",
    "G": "compiler error",
}


def _gold_loop_text(sc) -> str | None:
    task = next((t for t in sc.tasks if t.id == sc.gold_task), None)
    if task is None:
        return None
    idx = loop_index_from_id(task.id, sc.gold_referent)
    if idx is None or idx >= len(task.anchor.open_loops):
        return None
    return task.anchor.open_loops[idx]


def _task_level_text(sc) -> str:
    task = next((t for t in sc.tasks if t.id == sc.gold_task), None)
    if task is None:
        return ""
    a = task.anchor
    return " ".join([a.goal, *a.decisions, *a.constraints, *a.entities])


def _sibling_loop_texts(sc, extra_ids: list[str]) -> list[str]:
    out: list[str] = []
    for tid_loop in extra_ids:
        if "." not in tid_loop:
            continue
        tid = tid_loop.split(".loop")[0]
        task = next((t for t in sc.tasks if t.id == tid), None)
        if task is None:
            continue
        idx = loop_index_from_id(tid, tid_loop)
        if idx is not None and 0 <= idx < len(task.anchor.open_loops):
            out.append(task.anchor.open_loops[idx])
    return out


def classify_compact_miss_full_hit(sc, compact: dict, full: dict) -> str:
    if compact["pred_task"] != sc.gold_task or compact["pred_referent"] != sc.gold_referent:
        return "F"
    included = compact.get("included_loop_ids") or []
    if sc.gold_referent not in included:
        return "G"
    gold_loop = _gold_loop_text(sc) or ""
    task_level = _task_level_text(sc)
    extra = [i for i in (full.get("included_loop_ids") or []) if i not in included]
    siblings = " ".join(_sibling_loop_texts(sc, extra))
    compact_src = f"{gold_loop} {task_level}".lower()
    missing = [k for k in sc.expect_any if k.lower() not in compact_src]
    if missing:
        if any(k.lower() in siblings.lower() for k in missing):
            return "C"
        if any(k.lower() in gold_loop.lower() for k in missing):
            return "A"
        return "B"
    return "D"


def annotate(rows: list[dict]) -> None:
    for r in rows:
        r["failure_class"] = None
        r.pop("failure_class_meaning", None)
        r.pop("interference_extra_loops", None)
        r.pop("interference_extra_loop_texts", None)
        r.pop("interference_note", None)
    by: dict[str, dict] = defaultdict(dict)
    for r in rows:
        by[r["scenario_id"]][r["context_mode"]] = r
    sc_map = {s.scenario_id: s for s in scenarios()}
    for sid, modes in by.items():
        sc = sc_map[sid]
        compact = modes.get(REFERENT_COMPACT)
        full = modes.get(FULL_TASK)
        if not compact or not full:
            continue
        extra = [
            i for i in (full.get("included_loop_ids") or [])
            if i not in (compact.get("included_loop_ids") or [])
        ]
        if (not compact["answer_correct"]) and full["answer_correct"]:
            compact["failure_class"] = classify_compact_miss_full_hit(sc, compact, full)
            compact["failure_class_meaning"] = FAILURE_KEY[compact["failure_class"]]
        if (not full["answer_correct"]) and compact["answer_correct"]:
            full["interference_extra_loops"] = extra
            full["interference_extra_loop_texts"] = _sibling_loop_texts(sc, extra)
            full["interference_note"] = (
                "FULL included sibling loops that COMPACT omitted; "
                "compact answered the probe, full did not."
            )


def summarize_with_latency(rows: list[dict], provider: str) -> dict:
    out = summarize(rows, provider)
    rs = [r for r in rows if r["provider"] == provider]
    for mode, block in out["by_mode"].items():
        ms = [r for r in rs if r["context_mode"] == mode]
        lats = [r["latency_s"] for r in ms if r.get("latency_s") is not None]
        block["mean_latency_s"] = round(sum(lats) / len(lats), 3) if lats else None
    out["answer_model"] = ANSWER_MODEL
    out["routing"] = "MockLLM proposals + frozen production resolver/gate"
    return out


def print_table(rows: list[dict]) -> None:
    print(f"\n=== MODEL-STRENGTH CONTROL  answer={ANSWER_MODEL}  (not a benchmark) ===\n")
    print(f"{'scenario':24} {'mode':18} ok     wrongL  lat    loops")
    for r in rows:
        loops = ",".join(r["included_loop_ids"] or [])
        print(
            f"{r['scenario_id']:24} {str(r['context_mode']):18} "
            f"{str(r['answer_correct']):5} {str(r.get('wrong_loop')):6} "
            f"{str(r.get('latency_s')):6} {loops}"
        )


def main() -> None:
    llm = OllamaLLM(model=ANSWER_MODEL, timeout_s=180.0)
    rows = run_provider(ANSWER_MODEL, llm)
    annotate(rows)
    summary = summarize_with_latency(rows, ANSWER_MODEL)

    compact_miss_full_hit = [
        r for r in rows
        if r["context_mode"] == REFERENT_COMPACT and r.get("failure_class")
    ]
    full_miss_compact_hit = [
        r for r in rows
        if r["context_mode"] == FULL_TASK and r.get("interference_extra_loops")
    ]

    payload = {
        "note": "mechanism validation with a stronger local answer model; not a benchmark",
        "answer_model": ANSWER_MODEL,
        "baseline_model_for_comparison": BASELINE_MODEL,
        "controls": {
            "router": "unchanged production B",
            "routing_llm": "MockLLM (same scripts as sufficiency experiment)",
            "scenarios": [s.scenario_id for s in scenarios()],
            "probes": "unchanged",
            "compiler": "unchanged FULL_TASK / REFERENT_COMPACT / MERGED_COMPACT",
            "token_accounting": "ceil(chars/4)",
            "prompt": "rendered context + QUESTION + one short sentence",
        },
        "failure_key": FAILURE_KEY,
        "compact_fail_full_succeed": compact_miss_full_hit,
        "full_fail_compact_succeed": [
            {
                "scenario_id": r["scenario_id"],
                "extra_loops": r.get("interference_extra_loops"),
                "extra_loop_texts": r.get("interference_extra_loop_texts"),
                "full_answer": r.get("answer"),
            }
            for r in full_miss_compact_hit
        ],
        "summary": summary,
        "rows": rows,
    }
    out_dir = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "context_model_strength.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print_table(rows)
    print("\nsummary:", json.dumps(summary, indent=2))
    print("\ncompact fail / full succeed:", json.dumps(payload["compact_fail_full_succeed"], indent=2)[:2000])
    print("\nfull fail / compact succeed:", json.dumps(payload["full_fail_compact_succeed"], indent=2)[:3000])
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
