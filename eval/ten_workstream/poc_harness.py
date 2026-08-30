"""Final POC harness — layered metrics, evaluator-isolated probes, pitch report.

CONTROLLED ADVERSARIAL ENGINEERING FIXTURE — NOT NATURAL HUMAN CHAT.

Does not modify routing, MemoryWriter, or ContextPackage.
Does not call Vertex or Cloud Run.
Gold stays evaluator-only (probes.json / evaluator_isolated_probes.json).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.ten_workstream.answer_usability import context_package_winner_label
from eval.ten_workstream.load import load_fixture, load_probes
from eval.ten_workstream.metrics import poc_machine_summary
from eval.ten_workstream.run import replay, _idempotency_smoke, _isolation_smoke

ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = ROOT / "eval" / "out" / "poc_harness.json"
OUT_MD = ROOT / "docs" / "POC_HARNESS_REPORT.md"


def _count_trajectory_returns(route_log: list[dict]) -> int:
    """All RETURN transitions across the full trajectory (not probe-only)."""
    return sum(1 for r in route_log if (r.get("transition") or "") == "RETURN")


def _count_probe_returns(rows: list[dict]) -> int:
    """Probe turns whose observed decision was RETURN."""
    return sum(1 for p in rows if (p.get("decision") or "") == "RETURN")


def run_poc(*, evaluator_isolated: bool = False, held_out: bool = False) -> dict:
    if held_out:
        evaluator_isolated = True
    fx = load_fixture()
    probes = load_probes(evaluator_isolated=evaluator_isolated)
    payload, _store, _fx = replay(probes=probes)
    rows = payload["probes"]
    idemp = _idempotency_smoke(fx)
    iso = _isolation_smoke(fx)
    traj_returns = _count_trajectory_returns(payload.get("route_log") or [])
    probe_returns = _count_probe_returns(rows)
    machine = poc_machine_summary(
        rows=rows,
        number_of_workstreams=len(fx["workstreams"]),
        number_of_turns=len(fx["turns"]),
        trajectory_return_transitions=traj_returns,
        probe_return_count=probe_returns,
        idempotency_correct=idemp,
        isolation_correct=iso,
    )
    payload["summary"].update({
        "idempotency_correct": idemp,
        "isolation_correct": iso,
        **{k: machine[k] for k in (
            "number_of_workstreams", "number_of_turns",
            "trajectory_return_transitions", "probe_return_count",
            "failure_counts_by_layer",
        ) if k in machine},
    })
    payload["poc"] = machine
    payload["probe_source"] = (
        "evaluator_isolated_probes.json" if evaluator_isolated else "probes.json"
    )
    payload["probe_source_note"] = (
        "evaluator_isolated_probes.json is a runtime-blind evaluator probe set "
        "derived from the controlled fixture — NOT an unseen statistical/"
        "generalization holdout; not generalization evidence."
        if evaluator_isolated else
        "Primary evaluator probes. Gold never enters app runtime."
    )
    payload["fixture_label"] = machine["fixture_label"]
    payload["note"] = (
        "CONTROLLED ADVERSARIAL ENGINEERING FIXTURE — NOT NATURAL HUMAN CHAT. "
        "Not a benchmark. Routing frozen. Probe gold is scoring-only and never "
        "enters runtime prompts."
    )
    return payload


def write_report(payload: dict) -> str:
    s = payload["poc"]
    seen = set()
    fail_rows = []
    for p in payload["probes"]:
        bad = (
            (p.get("gold_policy") == "ACT" and p.get("policy_match") is False)
            or (p.get("gold_policy") == "CLARIFY" and p.get("policy_match") is False)
            or p.get("wrong_act")
            or p.get("candidate_miss") is True
            or p.get("critical_thin_context")
            or p.get("contamination")
            or (p.get("working_context_sufficient") is False)
            or (p.get("task_match") is False)
        )
        if bad and p["probe_id"] not in seen:
            seen.add(p["probe_id"])
            fail_rows.append(p)

    def _pkg_win(p: dict) -> str:
        return p.get("context_package_winner") or context_package_winner_label(
            p.get("winner"),
        )

    cf_better = sum(
        1 for p in payload["probes"]
        if _pkg_win(p) == "cf_package_beats_full_on_context_criteria"
        or p.get("winner") == "CF_beats_FULL"
    )
    both_ok = sum(
        1 for p in payload["probes"]
        if _pkg_win(p) == "both_packages_sufficient_on_context_criteria"
        or p.get("winner") == "both_sufficient"
    )
    full_better = sum(
        1 for p in payload["probes"]
        if _pkg_win(p) == "full_package_beats_cf_on_context_criteria"
        or p.get("winner") == "FULL_beats_CF"
    )

    pkg_counts = s.get("PACKAGE_USABILITY") or s.get("WORKING_CONTEXT_PACKAGE_USABILITY") or {}

    lines = [
        "# ContextFlow POC harness report",
        "",
        "> **CONTROLLED ADVERSARIAL ENGINEERING FIXTURE — NOT NATURAL HUMAN CHAT.**",
        ">",
        "> Demo-ready / research-product checkpoint — not a production benchmark,",
        "> not organic conversation evidence, not hosted-model accuracy.",
        "",
        "## Hypothesis",
        "",
        "After many simultaneous context switches, ContextFlow can reconstruct the",
        "minimum sufficient working state for the selected workstream while excluding",
        "unrelated and superseded context — and failing closed when ambiguity is material —",
        "providing a **materially better continuation context** than naive full-history",
        "or recent-history packing.",
        "",
        "## Experiment",
        "",
        f"- Substrate: `{payload.get('substrate')}` / ten-workstream fixture",
        f"- Probe source: `{payload.get('probe_source')}` (evaluator-only gold)",
        f"- Probe-source note: {payload.get('probe_source_note')}",
        f"- Workstreams: **{s['number_of_workstreams']}**",
        f"- User turns: **{s['number_of_turns']}**",
        f"- Trajectory RETURN transitions (all turns): "
        f"**{s['trajectory_return_transitions']}**",
        f"- Probe turns with decision=RETURN: **{s['probe_return_count']}**",
        f"- Probes scored: **{s['probes']}** (ACT={s['act_probes']}, CLARIFY={s['clarify_probes']})",
        "- Context packs compared with the **same** continuation utterance:",
        "  **FULL** · **RECENT** · **CONTEXTFLOW**",
        "- Runtime never receives gold task/policy/required/forbidden state.",
        "",
        "## Stress pattern",
        "",
        "Ten open workstreams spanning auth, deploy, overlapping 401 APIs,",
        "fashion, travel, food, deck, Stripe, and trivia; abrupt switches;",
        "returns after long gaps; deictic and ordinal ambiguity; supersession;",
        "uncertain exclusion; conversation isolation.",
        "",
        "## Results (separated layers — not one score)",
        "",
        "### RESOLUTION",
        f"- task_match: **{s['RESOLUTION']['task_match']}**",
        f"- referent_match: **{s['RESOLUTION']['referent_match']}**",
        f"- candidate_miss: **{s['RESOLUTION']['candidate_miss']}**",
        "",
        "### POLICY",
        f"- policy_match: **{s['POLICY']['policy_match']}**",
        f"- wrong_act: **{s['POLICY']['wrong_act']}**",
        f"- clarify_correct: **{s['POLICY']['clarify_correct']}**",
        "",
        "### MEMORY",
        f"- persistence_correct: **{s['MEMORY']['persistence_correct']}**",
        f"- supersession_correct: **{s['MEMORY']['supersession_correct']}**",
        f"- idempotency_correct: **{s['MEMORY']['idempotency_correct']}**",
        f"- isolation_correct: **{s['MEMORY']['isolation_correct']}**",
        "",
        "### WORKING CONTEXT",
        f"- working_context_sufficient: **{s['WORKING_CONTEXT']['working_context_sufficient']}**",
        f"- critical_thin_context: **{s['WORKING_CONTEXT']['critical_thin_context']}**",
        f"- contamination: **{s['WORKING_CONTEXT']['contamination']}**",
        "",
        "### WORKING-CONTEXT / PACKAGE USABILITY",
        "",
        "Package evidence labels from token/string presence on context packs.",
        "**Not** an answer-quality benchmark; does **not** judge generated replies.",
        "",
        f"- counts: `{pkg_counts}`",
        "",
        "### Context-package comparison (evidence criteria — not answer-model superiority)",
        "",
        "`cf_package_beats_full_on_context_criteria` means: the CF package has the",
        "required evidence with less forbidden context than FULL (reconstruction/",
        "token-presence criteria). It is **not** a claim that answers are better.",
        "",
        f"- cf_package_beats_full_on_context_criteria: **{cf_better}**",
        f"- both_packages_sufficient_on_context_criteria: **{both_ok}**",
        f"- full_package_beats_cf_on_context_criteria: **{full_better}**",
        "",
        "### Failure counts by layer",
        "```",
        f"{json.dumps(s['failure_counts_by_layer'], indent=2)}",
        "```",
        "",
        "## Failure cases",
        "",
    ]
    if not fail_rows:
        lines.append(
            "_No ACT/policy/working-context failures beyond documented "
            "CLARIFY/policy cases._"
        )
    else:
        lines += [
            "| probe | layer | gold → got | note |",
            "|---|---|---|---|",
        ]
        for p in fail_rows:
            note = p.get("frozen_behavior_note") or p.get("note") or p.get("failure_layer")
            lines.append(
                f"| {p['probe_id']} | {p['failure_layer']} | "
                f"{p.get('intended_workstream')}/{p.get('gold_policy')} → "
                f"{p.get('selected_task')}/{p.get('act_or_clarify')} | "
                f"{(note or '')[:80]} |"
            )

    lines += [
        "",
        "## Why ContextFlow succeeds / fails",
        "",
        "**Succeeds when** the selected workstream is correct and asserted memory for",
        "that referent is projected without sibling/unrelated/superseded/uncertain leaks.",
        "FULL history often *contains* required tokens but also contaminates with",
        "competing workstreams; CF wins on **package evidence criteria** when exclusion",
        "matters.",
        "",
        "**Fails when** frozen routing CLARIFYs on an ACT-gold return (document as",
        "POLICY, do not retune), when extraction never asserted required state",
        "(RECONSTRUCTION / EXTRACTION), or when ambiguity is material.",
        "",
        "## Limitations",
        "",
        "- Fixture is **synthetic and adversarial**, not organic chat.",
        "- MockLLM soft proposals + scripted extracts; not a hosted-model study.",
        "- Package usability classifies **context packages** via token/string presence,",
        "  not judged model replies (optional Ollama consume is separate and weak).",
        "- Evaluator-isolated probes are derived from the same controlled fixture —",
        "  **not** an unseen statistical holdout and **not** generalization evidence.",
        "- Known frozen disagreements (p07, p09, p18) are documented, not retuned.",
        "- Do not collapse layers into a single accuracy claim.",
        "",
    ]
    text = "\n".join(lines) + "\n"
    OUT_MD.write_text(text, encoding="utf-8")
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ContextFlow POC harness (mock only)")
    ap.add_argument(
        "--evaluator-isolated", action="store_true",
        help=(
            "Score evaluator_isolated_probes.json (runtime-blind evaluator set; "
            "NOT a statistical holdout)"
        ),
    )
    ap.add_argument(
        "--held-out", action="store_true",
        help="Deprecated alias for --evaluator-isolated",
    )
    args = ap.parse_args(argv)
    payload = run_poc(
        evaluator_isolated=args.evaluator_isolated or args.held_out,
    )
    write_report(payload)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": payload["status"],
        "probe_source": payload["probe_source"],
        "probe_source_note": payload["probe_source_note"],
        "poc": {
            k: payload["poc"][k]
            for k in (
                "number_of_workstreams", "number_of_turns",
                "trajectory_return_transitions", "probe_return_count",
                "task_match", "referent_match", "policy_match", "wrong_act",
                "candidate_miss", "working_context_sufficient",
                "critical_thin_context", "contamination",
                "supersession_correct", "persistence_correct",
                "idempotency_correct", "isolation_correct",
                "failure_counts_by_layer",
            )
        },
        "out_json": str(OUT_JSON),
        "out_md": str(OUT_MD),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
