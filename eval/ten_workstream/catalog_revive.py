"""Phase R3 — catalog → selective import → revive harness (local MockLLM).

CONTROLLED engineering scenarios — not natural chat, not a statistical holdout.
Gold lives in scenarios_r3.json (evaluator-only). Frozen gate untouched.

Philosophy (right amount of control):
  - Declarative scenarios; add cases without changing app/.
  - Selective import (subset), never auto-merge-all into generate.
  - ACT when cues uniquely identify an imported hop; CLARIFY gold when
    overlap is intentional (fail-closed is success).
  - Do not require perfect mid-trajectory routing on the source chat.
  - Score layers separately; do not collapse into one vanity score.

  python -m eval.ten_workstream.catalog_revive
  python -m eval.ten_workstream.catalog_revive --out eval/out/r3_catalog_revive.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import SETTINGS
from app.context.compiler import ContextCompiler
from app.context.working_set import WorkingContextBuilder
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.catalog import ConversationCatalog
from app.memory.extractor import MockMemoryExtractor
from app.memory.import_rollup import import_rollup_workstreams
from app.memory.registry import InMemoryRegistry
from app.memory.rollup import build_conversation_rollup
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from app.turn_pipeline import run_turn
from eval.ten_workstream.load import extract_scripts, llm_scripts, load_fixture
from eval.ten_workstream.metrics import (
    attribute_failure,
    candidate_miss,
    clarify_correct,
    policy_match,
    task_match,
    working_context_sufficient,
    wrong_act,
)
from eval.ten_workstream.run import make_registry

ROOT = Path(__file__).resolve().parents[2]
DIR = Path(__file__).resolve().parent
SCENARIOS = DIR / "scenarios_r3.json"
OUT_DEFAULT = ROOT / "eval" / "out" / "r3_catalog_revive.json"


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def load_scenarios(path: Path | None = None) -> dict:
    p = path or SCENARIOS
    return json.loads(p.read_text(encoding="utf-8"))


def replay_source(fixture_path: Path) -> tuple[InMemoryRegistry, InMemoryMemoryStore, dict]:
    """Full source replay. Mid-turn CLARIFY/NEW on source is OK — not scored here."""
    fx = load_fixture(fixture_path)
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id=fx["meta"]["conversation_id"])
    writer = MemoryWriter(store, reg)
    eng = Engine(MockLLM(llm_scripts(fx)), reg, SETTINGS, memory_store=store)
    ext = MockMemoryExtractor(extract_scripts(fx))
    cid = fx["meta"]["conversation_id"]
    for spec in fx["turns"]:
        run_turn(
            eng, writer, ext,
            conversation_id=cid,
            message=spec["message"],
            turn=int(spec["turn"]),
        )
    return reg, store, fx


def _wc_ok(rendered: str, needed: list[str], forbid: list[str]) -> tuple[bool, list[str], list[str]]:
    blob = (rendered or "").lower()
    missing = [n for n in needed if n.lower() not in blob]
    leaked = [f for f in forbid if f.lower() in blob]
    return (not missing and not leaked), missing, leaked


def _score_probe_row(
    *,
    probe: dict,
    acted: bool,
    selected_task: str | None,
    selected_ref: str | None,
    gold_task: str | None,
    gold_ref: str | None,
    open_ids: list[str],
    rendered: str,
    transition: str,
) -> dict:
    gold_policy = probe.get("gold_policy")
    needed = list(probe.get("needed_state") or [])
    forbid = list(probe.get("should_not_carry") or [])
    sufficient, missing, leaked = _wc_ok(rendered, needed, forbid)
    cf_ok = sufficient if acted and gold_policy == "ACT" else None
    tm = task_match(gold_task=gold_task, selected_task=selected_task, acted=acted)
    pm = policy_match(gold_policy=gold_policy, acted=acted)
    wa = wrong_act(
        gold_task=gold_task, selected_task=selected_task,
        acted=acted, gold_policy=gold_policy,
    )
    cm = candidate_miss(gold_task=gold_task, open_task_ids=open_ids)
    wc = working_context_sufficient(
        acted=acted, gold_policy=gold_policy, cf_sufficient_no_leak=cf_ok,
    )
    contam = bool(leaked) if acted else False
    row = {
        "probe_id": probe.get("id"),
        "category": probe.get("category"),
        "gold_policy": gold_policy,
        "gold_source_workstream_id": probe.get("gold_source_workstream_id"),
        "gold_task_id": gold_task,
        "gold_referent_id": gold_ref,
        "selected_task": selected_task,
        "selected_referent": selected_ref,
        "decision": transition,
        "act_or_clarify": "ACT" if acted else "CLARIFY",
        "task_match": tm,
        "policy_match": pm,
        "wrong_act": wa,
        "candidate_miss": cm,
        "clarify_correct": clarify_correct(gold_policy=gold_policy, acted=acted),
        "working_context_sufficient": wc,
        "contamination": contam,
        "missing_state": missing if acted else [],
        "leaked_state": leaked if acted else [],
        "note": probe.get("note"),
        "failure_layer": attribute_failure(
            gold_policy=gold_policy,
            acted=acted,
            task_match=tm,
            wrong_act=wa,
            candidate_miss=cm,
            critical_thin=False,
            contamination=contam,
            persist_ok=True,
            extract_status="uncertain",
            cf_sufficient=wc,
            policy_match=pm,
            answer_usability=None,
        ),
    }
    return row


def run_catalog_capacity(scenario: dict) -> dict:
    n_max = int(scenario.get("catalog_max_entries") or 3)
    n_arch = int(scenario.get("archive_count") or 5)
    expect = int(scenario.get("expect_kept") or n_max)
    cat = ConversationCatalog(max_entries=n_max, persist=False)
    for i in range(n_arch):
        cat.upsert_rollup(
            {
                "conversation_id": f"r3-cap-{i}",
                "blurb": f"chat {i}",
                "open_count": 1,
                "workstreams": [],
            },
            updated_at=float(i),
        )
    kept = [e.conversation_id for e in cat.list()]
    ok = len(kept) == expect and kept == [f"r3-cap-{i}" for i in range(n_arch - 1, n_arch - 1 - expect, -1)]
    return {
        "scenario_id": scenario["id"],
        "kind": "catalog_capacity",
        "pass": ok,
        "kept": kept,
        "expect_kept": expect,
        "probes": [],
        "note": "Structured rollups only; transcripts never enter catalog.",
    }


def run_paused_invariant(scenario: dict, fixture_dir: Path) -> dict:
    fx_path = fixture_dir / scenario["source_fixture"]
    src_reg, src_store, fx = replay_source(fx_path)
    cat = ConversationCatalog(max_entries=5, persist=False)
    entry = cat.touch_from_live(
        src_reg, src_store, conversation_id=fx["meta"]["conversation_id"],
    )
    dst_reg = InMemoryRegistry()
    dst_store = InMemoryMemoryStore(conversation_id="fresh-r3-paused")
    dst_writer = MemoryWriter(dst_store, dst_reg)
    result = import_rollup_workstreams(
        dst_reg, dst_writer, entry.rollup,
        workstream_ids=list(scenario["import_source_ids"]),
        turn=0,
        as_paused=True,
    )
    open_tasks = dst_reg.open_tasks()
    all_paused = bool(open_tasks) and all(t.status == "paused" for t in open_tasks)
    no_active = dst_reg.active() is None
    # No bind yet → no L1 package for any imported hop via builder alone is fine;
    # invariant is: import did not mark active / did not auto-ACT.
    ok = result.ok and all_paused and no_active and len(result.imported) == len(
        scenario["import_source_ids"]
    )
    return {
        "scenario_id": scenario["id"],
        "kind": "import_paused_invariant",
        "pass": ok,
        "imported": result.imported,
        "all_paused": all_paused,
        "active_before_bind": None if no_active else dst_reg.active().id,
        "errors": result.errors,
        "probes": [],
    }


def run_import_revive_scenario(scenario: dict, fixture_dir: Path) -> dict:
    fx_path = fixture_dir / scenario["source_fixture"]
    src_reg, src_store, fx = replay_source(fx_path)
    src_cid = fx["meta"]["conversation_id"]

    cat = ConversationCatalog(
        max_entries=int(scenario.get("catalog_max_entries") or 5),
        persist=False,
    )
    entry = cat.touch_from_live(src_reg, src_store, conversation_id=src_cid)
    catalog_has_source = cat.get(src_cid) is not None

    # Tier C: soft match must surface the archived chat before opt-in import.
    match_query = (scenario.get("match_query") or "").strip()
    match_hits = cat.match(match_query, limit=3) if match_query else []
    match_ok = (
        True if not match_query
        else any(ent.conversation_id == src_cid for ent, _ in match_hits)
    )
    # Import uses catalog entry resolved via match (or direct get) — never live mash.
    matched_entry = None
    if match_hits:
        matched_entry = next(
            (ent for ent, _ in match_hits if ent.conversation_id == src_cid),
            match_hits[0][0],
        )
    import_entry = matched_entry or entry

    dest = scenario.get("destination") or {}
    dst_cid = dest.get("conversation_id") or "fresh-r3"
    dst_reg = InMemoryRegistry()
    dst_store = InMemoryMemoryStore(conversation_id=dst_cid)
    dst_writer = MemoryWriter(dst_store, dst_reg)

    import_ids = list(scenario.get("import_source_ids") or [])
    imp = import_rollup_workstreams(
        dst_reg, dst_writer, import_entry.rollup,
        workstream_ids=import_ids,
        turn=0,
        as_paused=True,
    )
    id_map = {row["source_workstream_id"]: row["new_workstream_id"] for row in imp.imported}
    reverse_map = {v: k for k, v in id_map.items()}

    # Build destination Mock scripts from seed + probes (gold → remapped ids).
    llm_s: dict[str, dict] = {}
    ext_s: dict[str, dict] = {}
    turn_n = 0

    for seed in dest.get("seed_turns") or []:
        msg = seed["message"]
        llm_s[msg] = dict(seed.get("llm") or {
            "task_id": None, "is_new_task": True, "confidence": 0.9,
        })
        patches = []
        for raw in (seed.get("extract") or {}).get("patches") or []:
            p = dict(raw)
            # Writer needs workstream on commit; for NEW, pipeline extracts after create.
            patches.append(p)
        ext_s[msg] = {"patches": patches} if patches else {"patches": [], "uncertain": True}

    for probe in scenario.get("probes") or []:
        msg = probe["message"]
        src = probe.get("gold_source_workstream_id")
        if src and src in id_map:
            llm_s[msg] = {
                "task_id": id_map[src],
                "is_new_task": False,
                "confidence": 0.86,
                "rationale": f"r3_scripted_{src}",
            }
        else:
            # Ambiguity / CLARIFY probes: soft propose none — binder decides.
            llm_s[msg] = {
                "task_id": None,
                "is_new_task": False,
                "confidence": 0.4,
                "rationale": "r3_ambiguous",
            }
        ext_s[msg] = {"patches": [], "uncertain": True}

    eng = Engine(MockLLM(llm_s), dst_reg, SETTINGS, memory_store=dst_store)
    ext = MockMemoryExtractor(ext_s)
    compiler = ContextCompiler()
    builder = WorkingContextBuilder()

    seed_log = []
    for seed in dest.get("seed_turns") or []:
        turn_n += 1
        msg = seed["message"]
        # For NEW extracts that omit workstream_id, patch after plan — use pipeline as-is;
        # attach workstream in extract script if we know it post-facto via second pass.
        pipe = run_turn(
            eng, dst_writer, ext,
            conversation_id=dst_cid, message=msg, turn=turn_n,
        )
        # If NEW and seed wanted patches without workstream_id, commit onto created task.
        if pipe.turn.transition.value == "NEW" and pipe.turn.task_id:
            wanted = (seed.get("extract") or {}).get("patches") or []
            if wanted and not any(
                i.workstream_id == pipe.turn.task_id
                for i in dst_store.asserted(pipe.turn.task_id)
            ):
                patches = [
                    MemoryPatch(
                        kind=p["kind"],
                        text=p["text"],
                        source_turn=turn_n,
                        workstream_id=pipe.turn.task_id,
                        slot=p.get("slot"),
                        proposer="r3_seed",
                    )
                    for p in wanted
                ]
                dst_writer.commit(dst_writer.propose(patches), turn=turn_n)
        seed_log.append({
            "turn": turn_n,
            "message": msg,
            "transition": pipe.turn.transition.value,
            "task_id": pipe.turn.task_id,
        })

    imported_statuses = {
        nid: (dst_reg.get(nid).status if dst_reg.get(nid) else None)
        for nid in id_map.values()
    }

    probe_rows = []
    for probe in scenario.get("probes") or []:
        turn_n += 1
        msg = probe["message"]
        pipe = run_turn(
            eng, dst_writer, ext,
            conversation_id=dst_cid, message=msg, turn=turn_n,
        )
        acted = pipe.turn.transition.value != "CLARIFY"
        src = probe.get("gold_source_workstream_id")
        gold_task = id_map.get(src) if src else None
        gold_ref = None
        loop_i = probe.get("gold_loop_index")
        if gold_task and loop_i:
            gold_ref = f"{gold_task}.loop{int(loop_i)}"
        rendered = compiler.render(pipe.turn.package) if pipe.turn.package else ""
        open_ids = [t.id for t in dst_reg.open_tasks()]
        row = _score_probe_row(
            probe=probe,
            acted=acted,
            selected_task=pipe.turn.task_id,
            selected_ref=pipe.turn.predicted_referent_id,
            gold_task=gold_task,
            gold_ref=gold_ref,
            open_ids=open_ids,
            rendered=rendered,
            transition=pipe.turn.transition.value,
        )
        row["turn"] = turn_n
        row["source_selected"] = reverse_map.get(pipe.turn.task_id or "")
        row["package_chars"] = len(rendered)
        if acted and pipe.turn.task_id and dst_reg.get(pipe.turn.task_id):
            proj = builder.project(
                dst_reg.get(pipe.turn.task_id),
                pipe.turn.predicted_referent_id,
                dst_store,
                dst_reg.open_tasks(),
            )
            row["l1_items"] = len(proj.item_ids)
            row["excluded_workstreams"] = list(proj.excluded_workstreams)
        probe_rows.append(row)

    # Scenario pass: no wrong_act; every probe policy_match; WC true when scored.
    def _probe_ok(r: dict) -> bool:
        if r.get("wrong_act"):
            return False
        if r.get("policy_match") is False:
            return False
        if r.get("task_match") is False:
            return False
        if r.get("working_context_sufficient") is False:
            return False
        if r.get("contamination"):
            return False
        return True

    probes_pass = all(_probe_ok(r) for r in probe_rows) if probe_rows else False
    scenario_pass = (
        imp.ok
        and catalog_has_source
        and match_ok
        and len(imp.imported) == len(import_ids)
        and probes_pass
    )

    return {
        "scenario_id": scenario["id"],
        "kind": "import_revive",
        "description": scenario.get("description"),
        "pass": scenario_pass,
        "source_conversation_id": src_cid,
        "destination_conversation_id": dst_cid,
        "catalog_has_source": catalog_has_source,
        "match_query": match_query or None,
        "match_ok": match_ok,
        "match_top": [
            {"conversation_id": e.conversation_id, "score": round(s, 4)}
            for e, s in match_hits[:3]
        ],
        "catalog_blurb": entry.blurb,
        "import_ok": imp.ok,
        "import_errors": imp.errors,
        "id_map": id_map,
        "imported_statuses": imported_statuses,
        "seed_log": seed_log,
        "open_task_count": len(dst_reg.open_tasks()),
        "probes": probe_rows,
        "probe_pass_count": sum(1 for r in probe_rows if _probe_ok(r)),
        "probe_n": len(probe_rows),
        "wrong_act": sum(1 for r in probe_rows if r.get("wrong_act")),
        "failure_layers": {
            k: sum(1 for r in probe_rows if r.get("failure_layer") == k)
            for k in {r.get("failure_layer") for r in probe_rows}
        },
    }


def run_all(scenarios_path: Path | None = None) -> dict:
    doc = load_scenarios(scenarios_path)
    fixture_dir = DIR
    results = []
    for sc in doc.get("scenarios") or []:
        kind = sc.get("kind") or "import_revive"
        if kind == "catalog_capacity":
            results.append(run_catalog_capacity(sc))
        elif kind == "import_paused_invariant":
            results.append(run_paused_invariant(sc, fixture_dir))
        else:
            results.append(run_import_revive_scenario(sc, fixture_dir))

    n_pass = sum(1 for r in results if r.get("pass"))
    payload = {
        "status": "ran",
        "harness": "r3_catalog_revive",
        "scenarios_path": _rel(scenarios_path or SCENARIOS),
        "meta": doc.get("meta"),
        "summary": {
            "scenarios": len(results),
            "scenarios_pass": f"{n_pass}/{len(results)}",
            "all_pass": n_pass == len(results),
            "wrong_act_total": sum(int(r.get("wrong_act") or 0) for r in results),
            "note": (
                "Controlled catalog→import→revive. Not natural chat. "
                "Gate frozen. CLARIFY gold is an allowed success mode."
            ),
        },
        "scenarios": results,
    }
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenarios", type=Path, default=SCENARIOS)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args()
    payload = run_all(args.scenarios)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    brief = {
        "out": _rel(args.out),
        "all_pass": payload["summary"]["all_pass"],
        "scenarios_pass": payload["summary"]["scenarios_pass"],
        "wrong_act_total": payload["summary"]["wrong_act_total"],
        "per_scenario": [
            {
                "id": r["scenario_id"],
                "pass": r["pass"],
                "kind": r.get("kind"),
                "probes": f"{r.get('probe_pass_count', 0)}/{r.get('probe_n', 0)}"
                if r.get("probe_n") is not None else "n/a",
            }
            for r in payload["scenarios"]
        ],
    }
    print(json.dumps(brief, indent=2))


if __name__ == "__main__":
    main()
