"""CF revive parity: same working-context package, Lite vs Flash answer models.

Thesis: with ContextFlow's compact revive package, a basic Gemini model recovers
needed state about as well as a stronger Flash model — the layer carries the
revive, not model size.

Scope (hard-capped):
  - Mock seed ABCD memory lifecycle (frozen routing; no Vertex extract/propose)
  - 4 revive probes × CF package only × 2 answer models = 8 generate_content
  - Models: gemini-2.5-flash-lite (basic) vs gemini-2.5-flash (good)
  - Metrics: needed-state hit rate, contamination, prompt chars, token/$ estimate
  - NOT an answer-quality or natural-chat benchmark
  - Does NOT retune gate/referent/scorer

Run:
  CF_MODEL_PARITY=1 python -m eval.model_revive_parity
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from app.config import SETTINGS
from app.context.compiler import ContextCompiler
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.extractor import MockMemoryExtractor
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.turn_pipeline import run_turn
from eval.consented_case.contexts import contextflow_answer_prompt, full_history_prompt
from eval.memory_lifecycle.fixture import (
    EXTRACT_SCRIPTS,
    LLM_SCRIPTS,
    PRODUCT_USER_TURNS,
)
from eval.memory_lifecycle.run import make_registry
from eval.memory_lifecycle.score import condition_score

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "out" / "model_revive_parity.json"
DOC = ROOT / "docs" / "MODEL_REVIVE_PARITY.md"

BASIC = "gemini-2.5-flash-lite"
GOOD = "gemini-2.5-flash"
MAX_CALLS = 8
SAFETY_USD = 0.15

# Product-path revive probes (engine_turn → cues). Same world as answer_consume.
PROBES = (
    {
        "id": "return_dress_before_correction",
        "engine_turn": 7,
        "needed_state": ["black", "formal"],
        "should_not_carry": ["Lisbon", "APA", "401"],
        "stale_excluded": [],
    },
    {
        "id": "return_jwt",
        "engine_turn": 8,
        "needed_state": ["401", "15 minutes"],
        "should_not_carry": ["Lisbon", "dress", "navy", "APA"],
        "stale_excluded": [],
    },
    {
        "id": "return_navy_correction",
        "engine_turn": 9,
        "needed_state": ["navy", "formal", "evening"],
        "should_not_carry": ["Lisbon", "APA", "401"],
        "stale_excluded": ["black"],
    },
    {
        "id": "return_navy_again",
        "engine_turn": 10,
        "needed_state": ["navy", "formal", "evening"],
        "should_not_carry": ["Lisbon", "APA"],
        "stale_excluded": ["black"],
    },
)

PRICE = {
    BASIC: {"in": 0.10, "out": 0.40},
    GOOD: {"in": 0.30, "out": 2.50},
}


def estimate_block() -> dict:
    return {
        "purpose": (
            "Same CF revive package answered by basic Flash-Lite vs Flash — "
            "show revive recovery parity across model tiers"
        ),
        "not_purpose": [
            "answer-quality leaderboard",
            "natural human chat benchmark",
            "routing retune",
            "all Gemini models bakeoff",
            "Pro / thinking / TTS / image models",
        ],
        "basic_model": BASIC,
        "good_model": GOOD,
        "max_calls": MAX_CALLS,
        "safety_envelope_usd": SAFETY_USD,
        "seeding": "MockLLM + MockMemoryExtractor on ABCD product path",
        "package": "ContextFlow working context only (not FULL transcript)",
    }


def _usage(resp) -> dict:
    meta = getattr(resp, "usage_metadata", None) or {}
    if not isinstance(meta, dict):
        return {
            "prompt_tokens": getattr(meta, "prompt_token_count", None) or 0,
            "candidates_tokens": getattr(meta, "candidates_token_count", None) or 0,
            "total_tokens": getattr(meta, "total_token_count", None) or 0,
        }
    return {
        "prompt_tokens": meta.get("prompt_token_count") or 0,
        "candidates_tokens": meta.get("candidates_token_count") or 0,
        "total_tokens": meta.get("total_token_count") or 0,
    }


def _cost(model: str, prompt_tok: int, cand_tok: int) -> float:
    p = PRICE[model]
    return prompt_tok * p["in"] / 1_000_000 + cand_tok * p["out"] / 1_000_000


def score_answer(text: str, probe: dict) -> dict:
    blob = (text or "").lower()
    needed = list(probe.get("needed_state") or [])
    leaks = list(probe.get("should_not_carry") or [])
    stale = list(probe.get("stale_excluded") or [])
    hit = [n for n in needed if n and n.lower() in blob]
    miss = [n for n in needed if n and n.lower() not in blob]
    leak_hit = [x for x in leaks if x and x.lower() in blob]
    stale_hit = [x for x in stale if x and x.lower() in blob]
    return {
        "needed_total": len(needed),
        "needed_hit": len(hit),
        "needed_hit_rate": (len(hit) / len(needed)) if needed else None,
        "needed_miss": miss,
        "contaminants": leak_hit,
        "stale_present": stale_hit,
        "clean_hit": bool(needed) and not miss and not leak_hit and not stale_hit,
    }


def replay():
    cid = "model-revive-parity"
    reg = make_registry()
    store = InMemoryMemoryStore(conversation_id=cid)
    writer = MemoryWriter(store, reg)
    eng = Engine(MockLLM(LLM_SCRIPTS), reg, SETTINGS, memory_store=store)
    ext = MockMemoryExtractor(EXTRACT_SCRIPTS)
    snaps = {}
    for turn, msg, _ in PRODUCT_USER_TURNS:
        snaps[turn] = run_turn(
            eng, writer, ext, conversation_id=cid, message=msg, turn=turn,
        )
    return snaps


def history_before(engine_turn: int) -> list[dict]:
    hist = []
    i = 0
    for et, msg, _ in PRODUCT_USER_TURNS:
        if et >= engine_turn:
            break
        hist.append({"i": i, "role": "user", "text": msg})
        i += 1
        hist.append({"i": i, "role": "assistant", "text": "[stub]"})
        i += 1
    return hist


def make_client():
    os.environ.setdefault("CF_USE_VERTEX", "1")
    os.environ.setdefault("GCP_PROJECT", "contextflow-506414")
    os.environ.setdefault("CF_VERTEX_LOCATION", "us-central1")
    os.environ.setdefault("CF_EMBED_LOCAL", "1")
    from app.llm.gemini import GeminiClient
    return GeminiClient(use_vertex=True)


def generate(client, model: str, prompt: str) -> tuple[str, dict]:
    r = client._client.models.generate_content(
        model=model,
        contents=prompt,
        config=client._types_mod.GenerateContentConfig(temperature=0.2),
    )
    return (r.text or ""), _usage(r)


def write_doc(payload: dict) -> None:
    s = payload["summary"]
    lines = [
        "# Model revive parity (CF package × Lite vs Flash)",
        "",
        "**Integration demonstration — not a statistical benchmark, not natural chat.**",
        "",
        f"**Date:** {payload.get('ran_at', '')}",
        f"**Basic model:** `{BASIC}`",
        f"**Good model:** `{GOOD}`",
        f"**Calls:** {s['calls']} / {MAX_CALLS}",
        f"**Est. cost (token table):** ~${s['est_usd']:.4f}",
        "",
        "## Claim under test",
        "",
        "Given the **same ContextFlow working-context package** on revive probes, "
        "a basic Flash-Lite answer model recovers needed state at a similar rate "
        "to Flash — so the revive is carried by the layer, not by model size.",
        "",
        "## Summary",
        "",
        f"| Metric | Lite | Flash |",
        f"|---|---|---|",
        f"| Clean hits (needed all present, no leak/stale) | "
        f"**{s['lite_clean']}/{s['n_probes']}** | **{s['flash_clean']}/{s['n_probes']}** |",
        f"| Mean needed-state hit rate | **{s['lite_hit_rate']:.0%}** | **{s['flash_hit_rate']:.0%}** |",
        f"| Mean CF prompt chars | {s['mean_cf_chars']} | (same package) |",
        f"| Mean FULL prompt chars (ref) | {s['mean_full_chars']} | (not answered) |",
        "",
        f"**Parity gap (Flash − Lite clean hits):** {s['parity_gap_clean']}",
        "",
        "## Per-probe",
        "",
        "| Probe | CF chars | FULL chars | Lite hit | Flash hit | Lite clean | Flash clean |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in payload["probes"]:
        ls = row["lite"]["score"]
        fs = row["flash"]["score"]
        lines.append(
            f"| {row['id']} | {row['cf_chars']} | {row['full_chars']} | "
            f"{ls['needed_hit']}/{ls['needed_total']} | {fs['needed_hit']}/{fs['needed_total']} | "
            f"{ls['clean_hit']} | {fs['clean_hit']} |"
        )
    lines += [
        "",
        "## Limits",
        "",
        "- Synthetic ABCD fixture; Mock extract for history",
        "- Answer cues = string presence of needed_state (not human preference)",
        "- Flash may emit longer prose; we score state recovery, not eloquence",
        "- Pro / Gemini 3.x not included (cost + claim scope)",
        "",
        "## Reproduce",
        "",
        "```text",
        "CF_MODEL_PARITY=1 python -m eval.model_revive_parity",
        "```",
        "",
    ]
    DOC.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict:
    est = estimate_block()
    if os.getenv("CF_MODEL_PARITY") != "1":
        payload = {
            "status": "skipped",
            "reason": "CF_MODEL_PARITY not set",
            "estimate": est,
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    print(json.dumps(est, indent=2), flush=True)
    snaps = replay()
    compiler = ContextCompiler()
    client = make_client()
    calls = 0
    prompt_tok = 0
    cand_tok = 0
    usd = 0.0
    rows = []

    for probe in PROBES:
        if calls >= MAX_CALLS:
            break
        et = probe["engine_turn"]
        msg = next(m for t, m, _ in PRODUCT_USER_TURNS if t == et)
        hist = history_before(et)
        pkg = snaps[et].turn.package
        rendered = compiler.render(pkg) if pkg else ""
        cf_prompt = contextflow_answer_prompt(rendered, msg)
        full_prompt = full_history_prompt(hist, msg)
        pkg_score = condition_score(rendered, probe)

        lite_ans, lite_u = "", {}
        flash_ans, flash_u = "", {}
        if calls < MAX_CALLS:
            lite_ans, lite_u = generate(client, BASIC, cf_prompt)
            calls += 1
            pt, ct = int(lite_u.get("prompt_tokens") or 0), int(lite_u.get("candidates_tokens") or 0)
            prompt_tok += pt
            cand_tok += ct
            usd += _cost(BASIC, pt, ct)
            time.sleep(0.3)
        if calls < MAX_CALLS:
            flash_ans, flash_u = generate(client, GOOD, cf_prompt)
            calls += 1
            pt, ct = int(flash_u.get("prompt_tokens") or 0), int(flash_u.get("candidates_tokens") or 0)
            prompt_tok += pt
            cand_tok += ct
            usd += _cost(GOOD, pt, ct)
            time.sleep(0.3)

        row = {
            "id": probe["id"],
            "engine_turn": et,
            "message": msg,
            "cf_chars": len(cf_prompt),
            "full_chars": len(full_prompt),
            "package_score": pkg_score,
            "lite": {
                "model": BASIC,
                "answer_preview": (lite_ans or "")[:240],
                "usage": lite_u,
                "score": score_answer(lite_ans, probe),
            },
            "flash": {
                "model": GOOD,
                "answer_preview": (flash_ans or "")[:240],
                "usage": flash_u,
                "score": score_answer(flash_ans, probe),
            },
        }
        rows.append(row)
        print(
            f"{probe['id']}: lite={row['lite']['score']['needed_hit']}/"
            f"{row['lite']['score']['needed_total']} clean={row['lite']['score']['clean_hit']} | "
            f"flash={row['flash']['score']['needed_hit']}/"
            f"{row['flash']['score']['needed_total']} clean={row['flash']['score']['clean_hit']}",
            flush=True,
        )

    def mean_rate(key: str) -> float:
        vals = [r[key]["score"]["needed_hit_rate"] for r in rows if r[key]["score"]["needed_hit_rate"] is not None]
        return sum(vals) / len(vals) if vals else 0.0

    summary = {
        "n_probes": len(rows),
        "calls": calls,
        "prompt_tokens": prompt_tok,
        "candidates_tokens": cand_tok,
        "est_usd": round(usd, 6),
        "lite_clean": sum(1 for r in rows if r["lite"]["score"]["clean_hit"]),
        "flash_clean": sum(1 for r in rows if r["flash"]["score"]["clean_hit"]),
        "lite_hit_rate": mean_rate("lite"),
        "flash_hit_rate": mean_rate("flash"),
        "parity_gap_clean": sum(1 for r in rows if r["flash"]["score"]["clean_hit"])
        - sum(1 for r in rows if r["lite"]["score"]["clean_hit"]),
        "mean_cf_chars": int(sum(r["cf_chars"] for r in rows) / len(rows)) if rows else 0,
        "mean_full_chars": int(sum(r["full_chars"] for r in rows) / len(rows)) if rows else 0,
        "within_envelope": usd <= SAFETY_USD,
    }
    payload = {
        "status": "ran",
        "ran_at": time.strftime("%Y-%m-%d"),
        "estimate": est,
        "summary": summary,
        "probes": rows,
        "note": (
            "Scores are needed-state string recovery on CF packages. "
            "Not answer eloquence. Not a full Gemini catalog bakeoff."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_doc(payload)
    print(json.dumps(summary, indent=2), flush=True)
    print(f"Wrote {OUT}", flush=True)
    print(f"Wrote {DOC}", flush=True)
    return payload


if __name__ == "__main__":
    run()
