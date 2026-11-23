"""Phase R2 — condensation stress under 10×20 density (local MockLLM).

Honors frozen gate. Measures whether L1 packages stay lean while L5 store grows,
and whether rollups stay usable for H2. Does not retune TAU/DELTA.

  python -m eval.ten_workstream.condensation_stress
  python -m eval.ten_workstream.condensation_stress --out eval/out/condensation_10x20.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import SETTINGS
from app.context.compiler import ContextCompiler
from app.context.working_set import DEFAULT_LIMITS, WorkingContextBuilder
from app.engine import Engine
from app.llm.mock import MockLLM
from app.llm.tokens import count
from app.memory.extractor import MockMemoryExtractor
from app.memory.rollup import build_conversation_rollup
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.turn_pipeline import run_turn
from eval.ten_workstream.load import extract_scripts, llm_scripts, load_fixture, load_probes
from eval.ten_workstream.run import make_registry

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = ROOT / "eval" / "ten_workstream" / "fixture_10x20.json"
DEFAULT_PROBES = ROOT / "eval" / "ten_workstream" / "probes_10x20.json"
DEFAULT_REPLAY = ROOT / "eval" / "out" / "ten_workstream_10x20.json"


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def analyze(
    fixture_path: Path,
    probes_path: Path,
    replay_path: Path | None = None,
) -> dict:
    fx = load_fixture(fixture_path)
    probes = load_probes(path=probes_path) if probes_path.exists() else []
    probe_by_turn = {int(p["turn"]): p for p in probes}

    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id=fx["meta"]["conversation_id"])
    writer = MemoryWriter(store, reg)
    eng = Engine(MockLLM(llm_scripts(fx)), reg, SETTINGS, memory_store=store)
    ext = MockMemoryExtractor(extract_scripts(fx))
    compiler = ContextCompiler()
    cid = fx["meta"]["conversation_id"]
    builder = WorkingContextBuilder()

    probe_rows: list[dict] = []
    store_growth: list[dict] = []

    for spec in fx["turns"]:
        et, msg = int(spec["turn"]), spec["message"]
        pipe = run_turn(eng, writer, ext, conversation_id=cid, message=msg, turn=et)
        if et % 50 == 0 or et == len(fx["turns"]):
            store_growth.append({
                "turn": et,
                "asserted": len([i for i in store.all() if i.status == "asserted"]),
                "all_items": len(store.all()),
                "open_tasks": len(reg.open_tasks()),
            })

        if et not in probe_by_turn:
            continue
        probe = probe_by_turn[et]
        acted = pipe.turn.transition.value != "CLARIFY"
        rendered = compiler.render(pipe.turn.package) if pipe.turn.package else ""
        l2 = list(store.asserted(probe["gold_task_id"])) if probe.get("gold_task_id") else []
        proj = None
        if acted and pipe.turn.task_id and reg.get(pipe.turn.task_id):
            proj = builder.project(
                reg.get(pipe.turn.task_id),
                pipe.turn.predicted_referent_id,
                store,
                reg.open_tasks(),
            )
        needed = list(probe.get("needed_state") or [])
        pkg_blob = " ".join(
            (proj.decisions if proj else [])
            + (proj.constraints if proj else [])
            + (proj.facts if proj else [])
            + (proj.entities if proj else [])
        ).lower()
        needed_present = [
            n for n in needed if n.lower() in pkg_blob or n.lower() in rendered.lower()
        ]
        needed_missing = [n for n in needed if n not in needed_present]
        probe_rows.append({
            "probe_id": probe.get("id"),
            "turn": et,
            "task_id": pipe.turn.task_id,
            "acted": acted,
            "l2_asserted_on_gold": len(l2),
            "l1_item_ids": len(proj.item_ids) if proj else 0,
            "l1_decisions": len(proj.decisions) if proj else 0,
            "l1_constraints": len(proj.constraints) if proj else 0,
            "l1_facts": len(proj.facts) if proj else 0,
            "cf_chars": len(rendered),
            "cf_tokens": count(rendered) if rendered else 0,
            "needed_state": needed,
            "needed_present": needed_present,
            "needed_missing_after_caps": needed_missing,
            "caps_dropped_required": bool(needed_missing) and acted,
        })

    roll = build_conversation_rollup(reg, store, conversation_id=cid)
    roll_json = json.dumps(roll.to_dict(), ensure_ascii=False)
    per_ws_l2 = {
        t.id: len(store.asserted(t.id))
        for t in reg.open_tasks()
    }

    replay_summary = {}
    if replay_path and replay_path.exists():
        prev = json.loads(replay_path.read_text(encoding="utf-8"))
        replay_summary = {
            "path": _rel(replay_path),
            "task_match": (prev.get("summary") or {}).get("task_match"),
            "working_context_sufficient": (prev.get("summary") or {}).get(
                "working_context_sufficient"
            ),
            "wrong_act": (prev.get("summary") or {}).get("wrong_act"),
            "cf_tokens_from_probes": [
                (r.get("context_package_size") or {}).get("cf_tokens")
                for r in (prev.get("probes") or [])
            ],
            "full_tokens_from_probes": [
                (r.get("context_package_size") or {}).get("full_tokens")
                for r in (prev.get("probes") or [])
            ],
        }
        cf_toks = [t for t in replay_summary["cf_tokens_from_probes"] if t is not None]
        full_toks = [t for t in replay_summary["full_tokens_from_probes"] if t is not None]
        if cf_toks and full_toks:
            replay_summary["mean_cf_tokens"] = round(sum(cf_toks) / len(cf_toks), 1)
            replay_summary["mean_full_tokens"] = round(sum(full_toks) / len(full_toks), 1)
            replay_summary["compression_vs_full"] = round(
                sum(full_toks) / max(1, sum(cf_toks)), 1
            )

    caps_ok = not any(r["caps_dropped_required"] for r in probe_rows)
    l1_counts = [r["l1_item_ids"] for r in probe_rows if r["acted"]]
    soft_cap = (
        DEFAULT_LIMITS.max_decisions
        + DEFAULT_LIMITS.max_constraints
        + DEFAULT_LIMITS.max_facts
        + DEFAULT_LIMITS.max_entities
    )

    return {
        "phase": "R2_condensation_stress",
        "fixture": _rel(fixture_path),
        "probes": _rel(probes_path),
        "limits": {
            "max_decisions": DEFAULT_LIMITS.max_decisions,
            "max_constraints": DEFAULT_LIMITS.max_constraints,
            "max_facts": DEFAULT_LIMITS.max_facts,
            "max_entities": DEFAULT_LIMITS.max_entities,
            "soft_total_cap": soft_cap,
        },
        "store_final": {
            "asserted": len([i for i in store.all() if i.status == "asserted"]),
            "all_items": len(store.all()),
            "open_tasks": len(reg.open_tasks()),
            "asserted_per_workstream": per_ws_l2,
        },
        "store_growth": store_growth,
        "rollup": {
            "open_count": roll.open_count,
            "blurb": roll.blurb,
            "chars": len(roll_json),
            "tokens": count(roll_json),
            "per_ws_item_counts": {w.workstream_id: w.item_count for w in roll.workstreams},
        },
        "probe_condensation": probe_rows,
        "verdict": {
            "l1_stays_under_soft_cap": all(c <= soft_cap for c in l1_counts) if l1_counts else False,
            "max_l1_items_on_probe": max(l1_counts) if l1_counts else 0,
            "mean_l1_items_on_probe": round(sum(l1_counts) / len(l1_counts), 2) if l1_counts else 0,
            "caps_never_dropped_needed_state": caps_ok,
            "rollup_usable": bool(roll.blurb) and roll.open_count >= 10,
            "pass": caps_ok
            and (all(c <= soft_cap for c in l1_counts) if l1_counts else False)
            and bool(roll.blurb),
        },
        "prior_replay": replay_summary,
        "note": (
            "L1 package size tracks WorkingSetLimits, not turn count. "
            "Store/asserted grows with commits; generate reads L1 only. "
            "No gate retune."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    ap.add_argument("--probes", type=Path, default=DEFAULT_PROBES)
    ap.add_argument("--replay", type=Path, default=DEFAULT_REPLAY,
                    help="Prior ten_workstream_10x20.json for CF vs full token ratios")
    ap.add_argument("--out", type=Path, default=ROOT / "eval" / "out" / "condensation_10x20.json")
    args = ap.parse_args()

    report = analyze(args.fixture, args.probes, args.replay if args.replay.exists() else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    v = report["verdict"]
    print(json.dumps({
        "out": _rel(args.out),
        "pass": v["pass"],
        "caps_never_dropped_needed_state": v["caps_never_dropped_needed_state"],
        "max_l1_items_on_probe": v["max_l1_items_on_probe"],
        "mean_l1_items_on_probe": v["mean_l1_items_on_probe"],
        "rollup_tokens": report["rollup"]["tokens"],
        "rollup_blurb": report["rollup"]["blurb"],
        "store_asserted": report["store_final"]["asserted"],
        "compression_vs_full": (report.get("prior_replay") or {}).get("compression_vs_full"),
        "mean_cf_tokens": (report.get("prior_replay") or {}).get("mean_cf_tokens"),
        "mean_full_tokens": (report.get("prior_replay") or {}).get("mean_full_tokens"),
    }, indent=2))


if __name__ == "__main__":
    main()
