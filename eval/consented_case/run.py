"""Consented case study: FULL vs RECENT vs ContextFlow.

Does not retune routing. Does not invent a conversation.
Requires local files: data/consented/session.json and
eval/consented_case/interpretation.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import SETTINGS
from app.context.compiler import ContextCompiler
from app.engine import Engine
from app.llm.mock import MockLLM
from app.llm.ollama import OllamaLLM
from app.memory.registry import InMemoryRegistry
from eval.consented_case import contexts
from eval.consented_case.load import (
    INTERPRETATION_PATH,
    SESSION_PATH,
    interpretation_ready,
    load_json,
    registry_for_probe,
    session_ready,
    turns_before,
    user_text,
)
from eval.consented_case.reconstruction import reconstruction_report

OUT_DIR = Path(__file__).resolve().parents[2] / "eval" / "out" / "consented"


def _llm(provider: str):
    if provider == "mock":
        return MockLLM()
    if provider == "ollama":
        return OllamaLLM()
    raise SystemExit(f"unknown provider {provider}")


def _blocked(reason: str) -> dict:
    return {
        "status": "blocked",
        "reason": reason,
        "probes": [],
        "note": (
            "This is not a failed experiment. The substrate is not present. "
            "Do not manufacture a conversation to unblock."
        ),
    }


def run_native_replay(session: dict, llm) -> list[dict]:
    """Diagnostic: default NEW cards = raw utterances. Documents extraction gap."""
    eng = Engine(llm, InMemoryRegistry(), SETTINGS, mode="split")
    rows = []
    turn_no = 0
    for t in session["turns"]:
        if t.get("role") != "user":
            continue
        turn_no += 1
        res = eng.handle_turn(str(t["text"]), turn_no)
        rows.append({
            "user_turn_i": t["i"],
            "engine_turn": turn_no,
            "transition": res.transition.value,
            "task_id": res.task_id,
            "referent": res.predicted_referent_id,
            "clarify": res.clarify_question,
            "open_count": len(eng.reg.open_tasks()),
            "answer_tokens": res.package.answer_tokens if res.package else None,
        })
    return rows


def run_probes(session: dict, interp: dict, llm, recent_k: int, provider: str) -> list[dict]:
    out = []
    for probe in interp.get("probes") or []:
        idx = int(probe["user_turn_index"])
        message = user_text(session, idx)
        history = turns_before(session, idx)
        gold_task = probe.get("gold_task_id")
        gold_ref = probe.get("gold_referent_id")
        needed = list(probe.get("needed_state") or [])

        full_p = contexts.full_history_prompt(history, message)
        rec_p = contexts.recent_prompt(history, message, recent_k)

        reg = registry_for_probe(interp, probe)
        eng = Engine(llm, reg, SETTINGS, mode="split")
        res = eng.handle_turn(message, idx)

        compiler = ContextCompiler()
        rendered = compiler.render(res.package) if res.package is not None else None
        cf_prompt = None
        if rendered:
            cf_prompt = contexts.contextflow_answer_prompt(rendered, message)
        elif res.clarify_question:
            cf_prompt = None

        answers = {"full": None, "recent": None, "contextflow": None}
        # ContextFlow continuation uses the production generate() path (compiler.render).
        # FULL/RECENT use the same LLM.generate with a history prompt. Same model, same user message.
        if provider != "mock":
            answers["full"] = llm.generate(full_p)
            answers["recent"] = llm.generate(rec_p)
        else:
            answers["full"] = "[mock] no full-history generate"
            answers["recent"] = "[mock] no recent generate"
        if res.clarify_question and res.answer is None:
            answers["contextflow"] = None
        else:
            answers["contextflow"] = res.answer

        resolved_task = res.task_id
        resolved_ref = res.predicted_referent_id
        joint = (
            resolved_task == gold_task
            and (gold_ref is None or resolved_ref == gold_ref)
            if gold_task and res.transition.value != "CLARIFY"
            else False
        )
        if res.transition.value == "CLARIFY":
            joint = None

        leak_cues = list(probe.get("should_not_carry") or probe.get("contamination_cues") or [])
        rec_score = reconstruction_report(rendered, probe)
        task_match = resolved_task == gold_task if gold_task else None
        ref_match = resolved_ref == gold_ref if gold_ref else None
        acted = res.transition.value != "CLARIFY"
        critical = bool(
            acted and task_match and rec_score["thin_context"]
        )
        policy_ok = None
        gold_policy = probe.get("gold_policy")
        if gold_policy == "CLARIFY":
            policy_ok = res.transition.value == "CLARIFY"
        elif gold_policy == "ACT":
            policy_ok = acted

        out.append({
            "probe_id": probe.get("id"),
            "user_turn_index": idx,
            "message": message,
            "human": {
                "workstream": probe.get("human_workstream") or probe.get("intention_a"),
                "open_loop": probe.get("human_open_loop"),
                "phenomenon": probe.get("phenomenon"),
            },
            "gold_task_id": gold_task,
            "gold_referent_id": gold_ref,
            "gold_policy": gold_policy,
            "short_description": probe.get("short_description"),
            "why_return": probe.get("why_it_qualifies"),
            "confidence": probe.get("confidence"),
            "resolution": {
                "transition": res.transition.value,
                "predicted_task_id": resolved_task,
                "predicted_referent_id": resolved_ref,
                "task_match": task_match,
                "referent_match": ref_match,
                "joint_on_act": joint,
                "policy_ok": policy_ok,
                "clarify_question": res.clarify_question,
            },
            "sizes": {
                "full_chars": len(full_p),
                "recent_chars": len(rec_p),
                "cf_decision_tokens": res.package.decision_tokens if res.package else None,
                "cf_answer_tokens": res.package.answer_tokens if res.package else None,
                "full_diag_tokens": contexts.diagnostic_size(full_p),
                "recent_diag_tokens": contexts.diagnostic_size(rec_p),
                "cf_prompt_diag_tokens": contexts.diagnostic_size(cf_prompt or ""),
            },
            "reconstruction": {
                "rendered": rendered,
                "omission_cues_missing_from_package": rec_score["missing"]["needed_state"],
                "contamination_cues_in_cf": rec_score["leaks"],
                **rec_score,
            },
            "critical_failure": {
                "correct_referent_or_task_thin_context": critical,
                "note": (
                    "Routing named the workstream but the package lacked required "
                    "facts/decisions/constraints. This is a memory-extraction gap, not a gate bug."
                    if critical else None
                ),
            },
            "answers": answers,
            "required_facts": list(probe.get("required_facts") or []),
            "required_decisions": list(probe.get("required_decisions") or []),
            "required_constraints": list(probe.get("required_constraints") or []),
            "required_entities": list(probe.get("required_entities") or []),
            "should_not_carry": leak_cues,
            "needed_state": needed,
        })
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--session", type=Path, default=SESSION_PATH)
    p.add_argument("--interpretation", type=Path, default=INTERPRETATION_PATH)
    p.add_argument("--provider", choices=("ollama", "mock"), default="ollama")
    p.add_argument("--recent", type=int, default=contexts.RECENT_K)
    p.add_argument("--native-replay", action="store_true")
    args = p.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not session_ready(args.session):
        payload = _blocked(f"missing {args.session}")
        (OUT_DIR / "status.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(payload["reason"])
        return 2
    if not interpretation_ready(args.interpretation):
        payload = _blocked(f"missing {args.interpretation}")
        (OUT_DIR / "status.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(payload["reason"])
        return 2

    session = load_json(args.session)
    interp = load_json(args.interpretation)
    llm = _llm(args.provider)

    payload = {
        "status": "ran",
        "provider": args.provider,
        "recent_k": args.recent,
        "session_id": session.get("session_id"),
        "n_turns": len(session.get("turns") or []),
        "n_probes": len(interp.get("probes") or []),
        "settings": {
            "TAU": SETTINGS.TAU, "DELTA": SETTINGS.DELTA, "HYST": SETTINGS.HYST,
            "W_LLM": SETTINGS.W_LLM, "W_SIM": SETTINGS.W_SIM,
            "W_REC": SETTINGS.W_REC, "W_LOOP": SETTINGS.W_LOOP,
        },
        "probes": run_probes(session, interp, llm, args.recent, args.provider),
    }
    if args.native_replay:
        payload["native_replay"] = run_native_replay(session, llm)

    (OUT_DIR / "e2e.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "n_probes": payload["n_probes"],
                      "out": str(OUT_DIR / "e2e.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
