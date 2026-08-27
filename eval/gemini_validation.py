"""Gemini validation of the frozen scaling experiment. Does not change production.

Provider is the only experimental variable for ContextFlow.propose.
Embeddings stay hash-based (same as Ollama). generate() is skipped.
Baselines do not call Gemini.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

from app.config import SETTINGS
from app.domain import Transition
from app.engine import Engine
from app.llm.base import validate_proposal
from app.llm.mock import MockLLM
from app.memory.registry import InMemoryRegistry
from app.router.proposal import PROPOSAL_SCHEMA
from eval.task_count_scale import (
    SYSTEMS,
    TARGET_ID,
    _agg,
    _mk,
    build_registry,
    clone_task,
    curves,
    gold_for,
    iter_cells,
    message_for,
    run_baseline,
    task_set,
    target_task,
)

LITE_MODEL = os.getenv("CF_LITE_MODEL", "gemini-2.0-flash-lite")
GEN_MODEL = os.getenv("CF_GEN_MODEL", "gemini-2.0-flash")
REPS = 1  # temperature 0; no cherry-pick
SMOKE_CELLS = (
    (1, "HIGH", "EXPLICIT", "target_last"),
    (2, "HIGH", "PARTIAL", "distractor_last"),
    (5, "HIGH", "DEICTIC", "target_active_distractor_fg"),
)


def _vertex_env() -> None:
    os.environ.setdefault("GCP_PROJECT", os.getenv("GCP_PROJECT") or "contextflow-506414")
    os.environ.setdefault("GCP_REGION", os.getenv("GCP_REGION") or "asia-south1")
    if not os.getenv("GEMINI_API_KEY"):
        os.environ.setdefault("CF_USE_VERTEX", "1")


class GeminiProposeOnly:
    """Eval adapter: Gemini propose, hash embed, no answer generation."""

    def __init__(self, model: str = LITE_MODEL, temperature: float = 0.0):
        _vertex_env()
        from app.llm.gemini import GeminiClient
        self._g = GeminiClient()
        self._hash = MockLLM()
        self.model = model
        self.temperature = temperature
        self.calls = 0
        self.prompt_tokens = 0
        self.candidate_tokens = 0
        self.last_latency_s = 0.0
        self.last_raw: dict = {}
        self.last_error: Optional[str] = None

    def propose(self, prompt: str, schema: dict) -> dict:
        types = self._g._types_mod
        t0 = time.perf_counter()
        self.last_error = None
        try:
            r = self._g._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=self.temperature,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            self.last_latency_s = time.perf_counter() - t0
            self.calls += 1
            usage = getattr(r, "usage_metadata", None)
            if usage is not None:
                self.prompt_tokens += int(getattr(usage, "prompt_token_count", 0) or 0)
                self.candidate_tokens += int(getattr(usage, "candidates_token_count", 0) or 0)
            parsed = json.loads(r.text or "{}")
            if not isinstance(parsed, dict):
                parsed = {}
            self.last_raw = parsed
            return parsed
        except Exception as exc:
            self.last_latency_s = time.perf_counter() - t0
            self.calls += 1
            self.last_error = f"{type(exc).__name__}:{exc}"
            self.last_raw = {}
            return {
                "task_id": None, "is_new_task": False, "confidence": 0.0,
                "referent": None, "rationale": f"gemini_error:{type(exc).__name__}",
            }

    def generate(self, prompt: str) -> str:
        return "[gemini-validation: generate skipped]"

    def embed(self, texts: list[str]):
        return self._hash.embed(texts)


def estimate() -> dict:
    scale = list(iter_cells())
    exp2 = 4
    cf_calls = (len(scale) + exp2) * REPS
    baseline_calls = 0
    avg_in = 900
    avg_out = 80
    in_tok = cf_calls * avg_in
    out_tok = cf_calls * avg_out
    # Published flash-lite-ish list prices; diagnostic only.
    usd = (in_tok / 1e6) * 0.075 + (out_tok / 1e6) * 0.30
    return {
        "scale_cells": len(scale),
        "exp2_cf_cells": exp2,
        "contextflow_propose_calls": cf_calls,
        "generate_calls": 0,
        "embed_calls": 0,
        "baseline_gemini_calls": baseline_calls,
        "estimated_input_tokens": in_tok,
        "estimated_output_tokens": out_tok,
        "estimated_usd_flash_lite": round(usd, 4),
        "note": "Decision context grows with n (open cards). Tokens diagnostic, not savings.",
        "model": LITE_MODEL,
        "temperature": 0.0,
        "reps": REPS,
    }


def fail_class(row: dict) -> Optional[str]:
    """A–H. CLARIFY is not automatically a failure."""
    gold_res = row["pred_task"] == row["gold_task"] and row["pred_referent"] == row["gold_referent"]
    if row["wrong_action"]:
        if row["pred_task"] != row["gold_task"] and row["pred_referent"] == row["gold_referent"]:
            return "B"
        if row["pred_task"] == row["gold_task"] and row["pred_referent"] != row["gold_referent"]:
            return "A"
        if row.get("underspecification") == "PARTIAL" or "401" in (row.get("message") or ""):
            return "E"
        return "B"
    if row["clarified"]:
        if gold_res:
            return "H"
        if row.get("underspecification") == "PARTIAL":
            return "E"
        return "H"
    if gold_res:
        return None
    return "A"


def gate_fields(res) -> dict:
    d = res.decision
    return {
        "top_raw": d.top_raw,
        "runner_raw": d.runner_raw,
        "raw_margin": d.raw_margin,
        "top_norm": d.top_norm,
        "norm_margin": d.norm_margin,
        "plausible_candidate_count": d.plausible_candidate_count,
        "llm_confidence_diagnostic": None,
    }


def run_cf(llm: GeminiProposeOnly, reg: InMemoryRegistry, message: str, turn: int) -> dict:
    before = llm.calls
    eng = Engine(llm, reg, SETTINGS, mode="split")
    res = eng.handle_turn(message, turn)
    clarified = res.transition == Transition.CLARIFY
    pkg = res.package
    proposal = validate_proposal(llm.last_raw) if llm.last_raw else None
    out = {
        "pred_task": res.predicted_task_id,
        "pred_referent": res.predicted_referent_id,
        "clarified": clarified,
        "acted": (not clarified) and res.transition != Transition.NEW,
        "decision": res.transition.value,
        "decision_context_tokens": pkg.decision_tokens if pkg else 0,
        "answer_context_tokens": pkg.answer_tokens if pkg else 0,
        "total_context_tokens": pkg.total_context_tokens if pkg else 0,
        "context_mode": pkg.context_mode if pkg else None,
        "llm_task": proposal.task_id if proposal else None,
        "llm_confidence_diagnostic": proposal.confidence if proposal else None,
        "gemini_error": llm.last_error,
        "gemini_calls_this_cell": llm.calls - before,
        "latency_s": round(llm.last_latency_s, 3),
    }
    out.update(gate_fields(res))
    return out


def row_from(system: str, n: int, family: str, underspec: str, fg: str,
             gold_task: str, gold_ref: str, message: str, out: dict, extra: dict | None = None) -> dict:
    pred_t, pred_r = out["pred_task"], out["pred_referent"]
    task_ok = pred_t == gold_task
    ref_ok = pred_r == gold_ref
    joint = task_ok and ref_ok
    acted = out["acted"]
    row = {
        "provider": "gemini",
        "model": LITE_MODEL,
        "scenario_id": f"{family}-{underspec}-{fg}-n{n}",
        "open_task_count": n,
        "interference": family,
        "interference_family": family,
        "underspecification": underspec,
        "foreground": fg,
        "system": system,
        "message": message,
        "gold_task": gold_task,
        "gold_referent": gold_ref,
        "pred_task": pred_t,
        "pred_referent": pred_r,
        "decision": out.get("decision") or ("CLARIFY" if out["clarified"] else "ACT"),
        "task_accuracy": task_ok,
        "referent_accuracy": ref_ok,
        "joint_accuracy": joint,
        "clarified": out["clarified"],
        "wrong_action": bool(acted and not joint),
        "clarify_gold_resolution": bool(out["clarified"] and joint),
        "clarify_wrong_resolution": bool(out["clarified"] and not joint),
        "decision_context_tokens": out["decision_context_tokens"],
        "answer_context_tokens": out["answer_context_tokens"],
        "total_context_tokens": out["total_context_tokens"],
        "llm_task": out.get("llm_task"),
        "llm_confidence_diagnostic": out.get("llm_confidence_diagnostic"),
        "top_raw": out.get("top_raw"),
        "runner_raw": out.get("runner_raw"),
        "raw_margin": out.get("raw_margin"),
        "top_norm": out.get("top_norm"),
        "norm_margin": out.get("norm_margin"),
        "plausible_candidate_count": out.get("plausible_candidate_count"),
        "latency_s": out.get("latency_s"),
        "gemini_error": out.get("gemini_error"),
    }
    if extra:
        row.update(extra)
    row["failure_class"] = fail_class(row)
    return row


def run_scale(llm: GeminiProposeOnly, cells=None) -> list[dict]:
    rows: list[dict] = []
    it = cells if cells is not None else iter_cells()
    for n, family, underspec, fg in it:
        tasks = task_set(n, family)
        message = message_for(underspec)
        for system in SYSTEMS:
            reg, mentions = build_registry(tasks, fg, underspec)
            gold_task, gold_ref = gold_for(underspec, fg, tasks, mentions)
            turn = max(m[2] for m in mentions) + 1
            if system == "contextflow":
                out = run_cf(llm, reg, message, turn)
            else:
                out = run_baseline(system, reg, message)
                out["decision"] = "ACT"
                out["llm_task"] = None
                out["llm_confidence_diagnostic"] = None
                out["top_raw"] = None
                out["runner_raw"] = None
                out["raw_margin"] = None
                out["top_norm"] = None
                out["norm_margin"] = None
                out["plausible_candidate_count"] = None
                out["latency_s"] = None
                out["gemini_error"] = None
            rows.append(row_from(system, n, family, underspec, fg, gold_task, gold_ref, message, out))
    return rows


def exp2_tasks() -> list:
    t = clone_task(target_task())
    s = _mk(
        "S", "authz", "authorization header missing",
        ["401 from missing Authorization"],
        ["authorization", "401", "header"],
    )
    return [t, s]


def exp2_foregrounds() -> list[tuple[str, str, str]]:
    """(name, gold_task, gold_ref) — gold follows the 401-loop that is foregrounded."""
    return [
        ("target_foreground", TARGET_ID, f"{TARGET_ID}.loop1"),
        ("sibling_foreground", "S", "S.loop1"),
        ("target_active_sibling_fg", "S", "S.loop1"),
        ("sibling_active_target_fg", TARGET_ID, f"{TARGET_ID}.loop1"),
    ]


def apply_exp2_fg(reg: InMemoryRegistry, name: str) -> None:
    if name == "target_foreground":
        reg.record_mention("S", 1, "S.loop1")
        reg.mark_active("S", 1)
        reg.record_mention(TARGET_ID, 2, f"{TARGET_ID}.loop1")
        reg.mark_active(TARGET_ID, 2)
    elif name == "sibling_foreground":
        reg.record_mention(TARGET_ID, 1, f"{TARGET_ID}.loop1")
        reg.mark_active(TARGET_ID, 1)
        reg.record_mention("S", 2, "S.loop1")
        reg.mark_active("S", 2)
    elif name == "target_active_sibling_fg":
        reg.record_mention(TARGET_ID, 1, f"{TARGET_ID}.loop1")
        reg.mark_active(TARGET_ID, 1)
        reg.record_mention("S", 2, "S.loop1")
    else:
        reg.record_mention("S", 1, "S.loop1")
        reg.mark_active("S", 1)
        reg.record_mention(TARGET_ID, 2, f"{TARGET_ID}.loop1")


def run_exp2(llm: GeminiProposeOnly) -> list[dict]:
    rows = []
    message = "still getting the 401"
    for name, gold_t, gold_r in exp2_foregrounds():
        for system in SYSTEMS:
            reg = InMemoryRegistry()
            for t in exp2_tasks():
                reg.add(clone_task(t))
            apply_exp2_fg(reg, name)
            if system == "contextflow":
                out = run_cf(llm, reg, message, 3)
            else:
                out = run_baseline(system, reg, message)
                out["decision"] = "ACT"
                out["llm_task"] = None
                out["llm_confidence_diagnostic"] = None
                out["top_raw"] = out.get("top_raw")
                out.setdefault("runner_raw", None)
                out.setdefault("raw_margin", None)
                out.setdefault("top_norm", None)
                out.setdefault("norm_margin", None)
                out.setdefault("plausible_candidate_count", None)
                out.setdefault("latency_s", None)
                out.setdefault("gemini_error", None)
            rows.append(row_from(
                system, 2, "HIGH", "PARTIAL", name,
                gold_t, gold_r, message, out,
                extra={"experiment": "exp2_401_collision", "scenario_id": f"E2-{name}"},
            ))
    return rows


def print_tables(rows: list[dict], curve: list[dict]) -> None:
    print("\n=== GEMINI VALIDATION (not a benchmark) ===\n")
    cf = [r for r in rows if r["system"] == "contextflow" and r.get("experiment") != "exp2_401_collision"]
    print(f"ContextFlow scale rows={len(cf)}  "
          f"wrong_act={sum(r['wrong_action'] for r in cf)}  "
          f"clarify={sum(r['clarified'] for r in cf)}")
    for family in ("LOW", "HIGH"):
        print(f"\n-- {family} joint vs n --")
        ns = sorted({c["n"] for c in curve if c["family"] == family})
        print(f"{'system':16} " + " ".join(f"{n:>6}" for n in ns))
        for system in SYSTEMS:
            vals = []
            for n in ns:
                hit = next((c for c in curve if c["family"] == family and c["system"] == system and c["n"] == n), None)
                vals.append(f"{hit['joint_accuracy']:.3f}" if hit else "  n/a")
            print(f"{system:16} " + " ".join(f"{v:>6}" for v in vals))
        print(f"-- {family} wrong-action vs n --")
        print(f"{'system':16} " + " ".join(f"{n:>6}" for n in ns))
        for system in SYSTEMS:
            vals = []
            for n in ns:
                hit = next((c for c in curve if c["family"] == family and c["system"] == system and c["n"] == n), None)
                vals.append(f"{hit['wrong_action_rate']}" if hit and hit["wrong_action_rate"] is not None else "  n/a")
            print(f"{system:16} " + " ".join(f"{str(v):>6}" for v in vals))
        print(f"-- {family} clarify vs n --")
        print(f"{'system':16} " + " ".join(f"{n:>6}" for n in ns))
        for system in SYSTEMS:
            vals = []
            for n in ns:
                hit = next((c for c in curve if c["family"] == family and c["system"] == system and c["n"] == n), None)
                vals.append(f"{hit['clarification_rate']:.3f}" if hit else "  n/a")
            print(f"{system:16} " + " ".join(f"{v:>6}" for v in vals))


def main() -> None:
    est = estimate()
    print("COST ESTIMATE (before calls)")
    print(json.dumps(est, indent=2))
    llm = GeminiProposeOnly(model=LITE_MODEL, temperature=0.0)
    print("\n--- SMOKE (3 ContextFlow proposes) ---")
    smoke = run_scale(llm, cells=SMOKE_CELLS)
    cf_smoke = [r for r in smoke if r["system"] == "contextflow"]
    print(json.dumps([{
        "scenario_id": r["scenario_id"], "decision": r["decision"],
        "pred": f"{r['pred_task']}/{r['pred_referent']}",
        "gold": f"{r['gold_task']}/{r['gold_referent']}",
        "error": r["gemini_error"],
    } for r in cf_smoke], indent=2))
    if all(r.get("gemini_error") for r in cf_smoke):
        print("SMOKE FAILED: all Gemini proposes errored. Stopping.")
        out_dir = os.path.join(os.path.dirname(__file__), "out")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "gemini_validation.json"), "w", encoding="utf-8") as f:
            json.dump({"estimate": est, "smoke": smoke, "stopped": "smoke_failed"}, f, indent=2)
        return

    print("\n--- FULL SCALE ---")
    scale_rows = run_scale(llm)
    print("--- EXP2 401 collision ---")
    exp2_rows = run_exp2(llm)
    scale_only = [r for r in scale_rows if r.get("experiment") != "exp2_401_collision"]
    curve = curves(scale_only)
    print_tables(scale_only, curve)
    print("\nEXP2:")
    for r in exp2_rows:
        if r["system"] == "contextflow":
            print(f"  {r['scenario_id']:32} gold={r['gold_task']}/{r['gold_referent']:10} "
                  f"pred={r['pred_task']}/{r['pred_referent']} {r['decision']} "
                  f"cls={r['failure_class']} llm={r['llm_task']}")

    usage = {
        "propose_calls": llm.calls,
        "prompt_tokens": llm.prompt_tokens,
        "candidate_tokens": llm.candidate_tokens,
        "generate_calls": 0,
        "embed_calls": 0,
        "model": LITE_MODEL,
        "temperature": 0.0,
        "reps": REPS,
        "estimated_usd_from_usage": round(
            (llm.prompt_tokens / 1e6) * 0.075 + (llm.candidate_tokens / 1e6) * 0.30, 5
        ),
    }
    print("\nUSAGE", json.dumps(usage, indent=2))
    payload = {
        "note": "Gemini validation of frozen mechanism; not a benchmark; not token savings",
        "estimate": est,
        "usage": usage,
        "controls": {
            "router": "production B, unchanged",
            "embeddings": "hash MockLLM (not Gemini embeddings)",
            "generate": "skipped",
            "baselines": "identical to task_count_scale.py",
            "decision_context": "open-task cards; grows with n",
        },
        "smoke": cf_smoke,
        "rows": scale_rows,
        "exp2": exp2_rows,
        "curves": curve,
    }
    out_dir = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "gemini_validation.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print("wrote", path)


if __name__ == "__main__":
    main()
