"""Ten-workstream stress replay. Frozen routing. Mock by default. No Vertex."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from app.config import SETTINGS
from app.context.compiler import ContextCompiler
from app.context.working_set import WorkingContextBuilder
from app.engine import Engine
from app.llm.mock import MockLLM
from app.llm.tokens import count
from app.memory.extractor import MockMemoryExtractor
from app.memory.registry import InMemoryRegistry
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.task import Task, TaskAnchor
from app.turn_pipeline import run_turn
from eval.consented_case.contexts import (
    RECENT_K,
    contextflow_answer_prompt,
    full_history_prompt,
    recent_prompt,
)
from eval.memory_lifecycle.score import condition_score, winner
from eval.ten_workstream.load import extract_scripts, llm_scripts, load_fixture, load_probes
from eval.ten_workstream.metrics import score_probe_row, summarize as summarize_metrics

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "out" / "ten_workstream.json"
JACCARD_M = 8


def make_registry(fx: dict) -> InMemoryRegistry:
    reg = InMemoryRegistry()
    for spec in fx["workstreams"]:
        reg.add(Task(
            id=spec["id"], title=spec["title"], status="paused",
            retrieval_cues=list(spec["cues"]),
            anchor=TaskAnchor(goal=spec["goal"], open_loops=list(spec["loops"])),
        ))
    return reg


def _brief(item) -> dict:
    return {
        "id": item.id, "kind": item.kind, "text": item.text, "status": item.status,
        "workstream_id": item.workstream_id, "referent_id": item.referent_id,
        "slot": item.slot, "source_turn": item.source_turn,
        "superseded_by": item.superseded_by, "provenance": item.provenance,
        "uncertain": item.uncertain,
    }


def _wordset(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def jaccard(a: str, b: str) -> float:
    sa, sb = _wordset(a), _wordset(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def jaccard_prompt(history: list[dict], message: str) -> str:
    ranked = sorted(history, key=lambda t: jaccard(t.get("text") or "", message), reverse=True)
    picked = ranked[:JACCARD_M]
    blob = "\n".join(f"{t.get('role','USER').upper()}: {t.get('text','')}" for t in picked)
    return f"JACCARD RETRIEVAL (top {JACCARD_M}):\n{blob}\n\nUSER: {message}"


def last_turn_for(turns: list[dict], ws: str, before: int) -> int | None:
    hits = [t["turn"] for t in turns if t["ws"] == ws and t["turn"] < before]
    return hits[-1] if hits else None


def _idempotency_smoke(fx: dict) -> bool:
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="ten-idemp")
    writer = MemoryWriter(store, reg)
    eng = Engine(MockLLM(llm_scripts(fx)), reg, SETTINGS, memory_store=store)
    ext = MockMemoryExtractor(extract_scripts(fx))
    msg = fx["turns"][0]["message"]
    run_turn(eng, writer, ext, conversation_id="ten-idemp", message=msg, turn=1)
    n, ver = len(store.all()), store.namespace_version()
    run_turn(eng, writer, ext, conversation_id="ten-idemp", message=msg, turn=1)
    return len(store.all()) == n and store.namespace_version() == ver


def _isolation_smoke(fx: dict) -> bool:
    from app.models.memory import MemoryPatch
    a = InMemoryMemoryStore(conversation_id="ten-iso-a")
    b = InMemoryMemoryStore(conversation_id="ten-iso-b")
    ra, rb = make_registry(fx), make_registry(fx)
    MemoryWriter(a, ra).commit([
        MemoryPatch(kind="fact", text="secret-a", source_turn=1, workstream_id="A",
                    conversation_id="ten-iso-a"),
    ], turn=1)
    MemoryWriter(b, rb).commit([
        MemoryPatch(kind="decision", text="navy-b", source_turn=1, workstream_id="E",
                    conversation_id="ten-iso-b", slot="color"),
    ], turn=1)
    return (
        all("navy" not in (i.text or "") for i in a.all())
        and all("secret-a" not in (i.text or "") for i in b.all())
    )


def replay() -> dict:
    fx = load_fixture()
    probes = load_probes()
    probe_by_turn = {p["turn"]: p for p in probes}
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id=fx["meta"]["conversation_id"])
    writer = MemoryWriter(store, reg)
    llm = MockLLM(llm_scripts(fx))
    eng = Engine(llm, reg, SETTINGS, memory_store=store)
    ext = MockMemoryExtractor(extract_scripts(fx))
    cid = fx["meta"]["conversation_id"]
    compiler = ContextCompiler()
    history: list[dict] = []
    extract_log = []
    route_log = []
    probes_out = []
    t0 = time.perf_counter()

    for spec in fx["turns"]:
        et, msg = spec["turn"], spec["message"]
        ids_before = {i.id for i in store.all()}
        n_before = len(store.all())
        pipe = run_turn(eng, writer, ext, conversation_id=cid, message=msg, turn=et)
        ids_after = {i.id for i in store.all()}
        elog = {
            "ok": pipe.extract.ok,
            "errors": list(pipe.extract.errors or []),
            "accepted": [_brief(i) for i in pipe.extract.items if i.status == "asserted"],
            "status": (
                "rejected" if not pipe.extract.ok else
                ("accepted" if pipe.extract.items else "empty")
            ),
        }
        if any("uncertain" in e for e in (pipe.extract.errors or [])):
            elog["status"] = "uncertain"
        extract_log.append({"turn": et, "ws": spec["ws"], **elog})
        route_log.append({
            "turn": et,
            "intended_ws": spec["ws"],
            "transition": pipe.turn.transition.value,
            "task_id": pipe.turn.task_id,
            "referent": pipe.turn.predicted_referent_id,
            "generate_did_not_write": ids_after == ids_before or (
                ids_after - ids_before <= {i.id for i in pipe.extract.items}
            ),
        })

        if et in probe_by_turn:
            probe = probe_by_turn[et]
            rendered = compiler.render(pipe.turn.package) if pipe.turn.package else ""
            full_p = full_history_prompt(history, msg)
            rec_p = recent_prompt(history, msg, RECENT_K)
            jac_p = jaccard_prompt(history, msg)
            full_s = condition_score(full_p, probe)
            rec_s = condition_score(rec_p, probe)
            jac_s = condition_score(jac_p, probe)
            cf_s = condition_score(rendered, probe)
            full_s["stale_present"] = []
            rec_s["stale_present"] = []
            jac_s["stale_present"] = []
            full_s["sufficient_no_leak"] = (
                full_s["sufficient_for_continuation"] and not full_s["leaks"]
            )
            rec_s["sufficient_no_leak"] = (
                rec_s["sufficient_for_continuation"] and not rec_s["leaks"]
            )
            jac_s["sufficient_no_leak"] = (
                jac_s["sufficient_for_continuation"] and not jac_s["leaks"]
            )
            gold = probe.get("gold_task_id")
            gold_ref = probe.get("gold_referent_id")
            gold_policy = probe.get("gold_policy")
            acted = pipe.turn.transition.value != "CLARIFY"
            persist_ok = all(
                store.get(i["id"]) is not None for i in elog.get("accepted") or []
            )
            # empty accepted list is still persistence-correct for no-op extracts
            if not (elog.get("accepted") or []):
                persist_ok = True
            gap = None
            if gold:
                prev = last_turn_for(fx["turns"], gold, et)
                gap = et - prev if prev else None
            active_before = None
            if len(route_log) >= 2:
                active_before = route_log[-2]["task_id"]
            proj = None
            if pipe.turn.task_id and reg.get(pipe.turn.task_id):
                proj = WorkingContextBuilder().project(
                    reg.get(pipe.turn.task_id), pipe.turn.predicted_referent_id,
                    store, reg.open_tasks(),
                )
            pkg = pipe.turn.package
            open_ids = [t.id for t in reg.open_tasks()]
            metrics = score_probe_row(
                gold_task=gold,
                gold_ref=gold_ref,
                gold_policy=gold_policy,
                selected_task=pipe.turn.task_id,
                selected_ref=pipe.turn.predicted_referent_id,
                acted=acted,
                open_task_ids=open_ids,
                cf_sufficient_no_leak=cf_s.get("sufficient_no_leak") if acted else None,
                thin_context=bool(cf_s.get("thin_context")) if acted else False,
                has_package=pkg is not None,
                contamination=cf_s.get("leaks") if acted else [],
                supersession_ok=not bool(cf_s.get("stale_present")),
                persist_ok=persist_ok,
                extract_status=elog["status"],
            )
            # Declared vs observed open count / gap (diagnostic; not a retune signal)
            exp_open = probe.get("expected_open_workstream_count")
            open_ok = (len(open_ids) == exp_open) if exp_open is not None else None
            exp_gap = probe.get("expected_gap")
            gap_ok = (gap == exp_gap) if exp_gap is not None and gap is not None else None
            probes_out.append({
                "probe_id": probe["id"],
                "turn": et,
                "category": probe.get("category"),
                "utterance_kind": probe.get("utterance_kind"),
                "intended_workstream": gold,
                "intended_referent": gold_ref,
                "gold_policy": gold_policy,
                "competing_similar": list(probe.get("competing_similar") or []),
                "expected_open_workstream_count": exp_open,
                "expected_gap": exp_gap,
                "gap_since_relevant": gap,
                "gap_matches_expected": gap_ok,
                "active_workstream_before": active_before,
                "decision": pipe.turn.transition.value,
                "act_or_clarify": "CLARIFY" if not acted else "ACT",
                "selected_task": pipe.turn.task_id,
                "selected_referent": pipe.turn.predicted_referent_id,
                "task_match": metrics["task_match"],
                "referent_match": metrics["referent_match"],
                "policy_match": metrics["policy_match"],
                "wrong_ACT": metrics["wrong_act"],
                "wrong_act": metrics["wrong_act"],
                "candidate_miss": metrics["candidate_miss"],
                "working_context_sufficient": metrics["working_context_sufficient"],
                "critical_thin_context": metrics["critical_thin_context"],
                "critical_missing_state": metrics["critical_thin_context"],
                "contamination": metrics["contamination"],
                "contamination_state": cf_s.get("leaks") if acted else [],
                "supersession_correct": metrics["supersession_correct"],
                "superseded_excluded": metrics["supersession_correct"],
                "persistence_correct": metrics["persistence_correct"],
                "package_absent_because_clarify": metrics["package_absent_because_clarify"],
                "extracted_patches": elog.get("accepted"),
                "extract_status": elog["status"],
                "extract_errors": elog["errors"],
                "working_context_items": list(pkg.memory_item_ids) if pkg else [],
                "required_state": probe.get("needed_state") or probe.get("required_working_state"),
                "missing_state": (cf_s.get("missing") or {}).get("needed_state") if acted else [],
                "stale_present": cf_s.get("stale_present") if acted else [],
                "answer_output": (pipe.turn.answer or "")[:400],
                "latency_ms": None,
                "context_package_size": {
                    "cf_chars": len(rendered or ""),
                    "full_chars": len(full_p),
                    "recent_chars": len(rec_p),
                    "jaccard_chars": len(jac_p),
                    "cf_tokens": pkg.total_context_tokens if pkg else 0,
                    "full_tokens": count(full_p),
                    "recent_tokens": count(rec_p),
                },
                "failure_layer": metrics["failure_layer"],
                "FULL": full_s,
                "RECENT": rec_s,
                "JACCARD": jac_s,
                "CF": cf_s if acted else {
                    "sufficient_no_leak": None,
                    "thin_context": None,
                    "leaks": [],
                    "note": "no_package_clarify",
                },
                "winner": winner(full_s, rec_s, cf_s) if acted else "n/a_clarify",
                "excluded_workstreams": list(proj.excluded_workstreams) if proj else [],
                "open_workstream_count": len(open_ids),
                "open_workstream_count_ok": open_ok,
                "frozen_behavior_note": probe.get("frozen_behavior_note"),
                "note": probe.get("note"),
            })

        history.append({"i": et, "role": "user", "text": msg})
        if pipe.turn.answer:
            history.append({"i": et + 0.5, "role": "assistant", "text": pipe.turn.answer})

    elapsed = time.perf_counter() - t0
    n_asserted = len(store.asserted())
    metric_summary = summarize_metrics(probes_out)
    metric_summary["idempotency_correct"] = _idempotency_smoke(fx)
    metric_summary["isolation_correct"] = _isolation_smoke(fx)
    metric_summary["open_workstream_count_ok"] = all(
        p.get("open_workstream_count_ok") is not False for p in probes_out
    )
    summary = {
        "user_turns": len(fx["turns"]),
        "workstreams_open": len(reg.open_tasks()),
        "probes": len(probes_out),
        "asserted_items": n_asserted,
        "all_items": len(store.all()),
        "elapsed_s": round(elapsed, 3),
        "mock_generate_calls": len(fx["turns"]),
        "vertex_calls": 0,
        **metric_summary,
        # Explicit: do not treat legacy alias as primary quality.
        "note_metrics": (
            "Prefer task_match / referent_match / policy_match / "
            "critical_thin_context over routing_correct_legacy."
        ),
    }

    payload = {
        "status": "ran",
        "substrate": fx["meta"]["kind"],
        "summary": summary,
        "probes": probes_out,
        "extract_log": extract_log,
        "route_log": route_log,
        "store_snapshot": [_brief(i) for i in store.all()],
        "note": (
            "Controlled adversarial engineering fixture. Not natural human behavior. "
            "Not a benchmark. Routing frozen. Probe gold is scoring-only."
        ),
    }
    return payload, store, fx


def answer_compare(snaps_payload: dict, fx: dict, probes: list[dict]) -> dict:
    from eval.answer_consume import ollama_available
    if os.getenv("CF_TEN_ANSWER") != "1":
        return {"status": "skipped", "reason": "CF_TEN_ANSWER not set"}
    if not ollama_available():
        return {"status": "skipped", "reason": "ollama_unreachable"}
    from app.llm.ollama import OllamaLLM
    llm = OllamaLLM()
    # Rebuild packages via a second mock replay for prompts, then generate.
    # Use recorded CF package sizes from payload; regenerate history from fixture.
    subset = [
        p for p in probes
        if p["id"] in {
            "p06_return_e_after_navy_correction",
            "p07_return_b_superseded_builder",
            "p08_deictic_fix_that",
            "p11_long_gap_return_a",
            "p15_full_history_has_extra",
        }
    ]
    # Need rendered packages: re-run mock replay collecting packages
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="ten-answer")
    writer = MemoryWriter(store, reg)
    eng = Engine(MockLLM(llm_scripts(fx)), reg, SETTINGS, memory_store=store)
    ext = MockMemoryExtractor(extract_scripts(fx))
    compiler = ContextCompiler()
    history = []
    by_turn = {}
    for spec in fx["turns"]:
        pipe = run_turn(
            eng, writer, ext, conversation_id="ten-answer",
            message=spec["message"], turn=spec["turn"],
        )
        by_turn[spec["turn"]] = pipe
        if spec["turn"] in {s["turn"] for s in subset}:
            pass
        history.append({"role": "user", "text": spec["message"]})
        # Keep history *before* probe: we append after scoring that turn
        # Fix: build hist excluding current — handled below
    rows = []
    n = 0
    for probe in subset:
        et = probe["turn"]
        msg = next(t["message"] for t in fx["turns"] if t["turn"] == et)
        hist = []
        for t in fx["turns"]:
            if t["turn"] >= et:
                break
            hist.append({"role": "user", "text": t["message"]})
        pkg = by_turn[et].turn.package
        rendered = compiler.render(pkg) if pkg else ""
        prompts = {
            "full": full_history_prompt(hist, msg),
            "recent": recent_prompt(hist, msg, RECENT_K),
            "contextflow": contextflow_answer_prompt(rendered, msg),
        }
        answers = {}
        for k, v in prompts.items():
            answers[k] = llm.generate(v)
            n += 1
        needed = list(probe.get("needed_state") or [])
        used = {
            name: {s: s.lower() in (ans or "").lower() for s in needed}
            for name, ans in answers.items()
        }
        rows.append({
            "probe_id": probe["id"],
            "turn": et,
            "needed": needed,
            "used_in_answer": used,
            "answers": {k: (v or "")[:500] for k, v in answers.items()},
        })
    return {
        "status": "ran",
        "provider": "ollama",
        "model": llm.model,
        "n_generate": n,
        "probes": rows,
        "note": "String overlap is a weak signal. FULL winning on extra facts is recorded honestly.",
    }


def write_results_md(payload: dict) -> None:
    s = payload["summary"]
    lines = [
        "# Ten-workstream results (mock)",
        "",
        "**Controlled adversarial engineering fixture** — not natural human behavior, "
        "not a benchmark, not production accuracy.",
        "",
        f"**Date:** local mock run. Elapsed **{s['elapsed_s']}s**. "
        f"Mock generates: **{s['mock_generate_calls']}**. Vertex: **{s['vertex_calls']}**.",
        "",
        "## Separated metrics",
        "",
        f"- User turns: {s['user_turns']}",
        f"- Open workstreams: {s['workstreams_open']}",
        f"- Probes: {s['probes']} (ACT={s['act_probes']}, CLARIFY={s['clarify_probes']})",
        f"- task_match: **{s['task_match']}**",
        f"- referent_match: **{s['referent_match']}**",
        f"- policy_match: **{s['policy_match']}**",
        f"- wrong_act: **{s['wrong_act']}**",
        f"- candidate_miss: **{s['candidate_miss']}**",
        f"- working_context_sufficient (ACT only): **{s['working_context_sufficient']}**",
        f"- critical_thin_context: **{s['critical_thin_context']}**",
        f"- contamination: **{s['contamination']}**",
        f"- supersession_correct: **{s['supersession_correct']}**",
        f"- persistence_correct: **{s['persistence_correct']}**",
        f"- idempotency_correct: **{s['idempotency_correct']}**",
        f"- isolation_correct: **{s['isolation_correct']}**",
        f"- Failure layers: {s['failure_layers']}",
        "",
        "CLARIFY probes are not scored for working-context sufficiency "
        "(`package_absent_because_clarify`).",
        "",
        "## Probes",
        "",
        "| id | turn | gold | got | policy | task | ref | WC | layer |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for p in payload["probes"]:
        lines.append(
            f"| {p['probe_id']} | {p['turn']} | {p['intended_workstream']}/{p['gold_policy']} "
            f"| {p['selected_task']}/{p['selected_referent']} | {p['policy_match']} "
            f"| {p['task_match']} | {p['referent_match']} "
            f"| {p['working_context_sufficient']} | {p['failure_layer']} |"
        )
    lines += [
        "",
        "## Status",
        "",
        "| Claim | Status |",
        "|---|---|",
        "| 10-workstream fixture | TESTED (mock) |",
        "| Separated eval metrics | IMPLEMENTED / TESTED |",
        "| Working-context reconstruction | TESTED (mock) |",
        "| Hosted Vertex five-probe slice | see TEN_WORKSTREAM_VERTEX_RESULTS.md |",
        "| Full 50-turn Vertex replay | NOT YET |",
        "",
        "Do not retune the gate from this table.",
        "",
    ]
    path = ROOT / "docs" / "TEN_WORKSTREAM_RESULTS.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    t0 = time.perf_counter()
    payload, store, fx = replay()
    probes = load_probes()
    payload["answer_compare"] = answer_compare(payload, fx, probes)
    payload["summary"]["wall_s"] = round(time.perf_counter() - t0, 3)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    write_results_md(payload)
    print(json.dumps({
        "status": payload["status"],
        "summary": payload["summary"],
        "answer_compare": payload["answer_compare"].get("status"),
        "out": str(OUT),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
