"""Five-probe Vertex integration slice for the 10-workstream fixture.

Approved scope only:
  p06, p08, p11, p15, p13
  ≤15 generate_content calls
  gemini-2.5-flash-lite @ us-central1
  CF_EMBED_LOCAL=1
  frozen routing unchanged

Historical turns before/between probes are Mock-seeded (cards + extract scripts).
Vertex extract/propose/generate run ONLY on the five probe turns.
Not a statistical benchmark. Not natural human behavior. Do not retune routing.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from app.config import SETTINGS
from app.context.compiler import ContextCompiler
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.extractor import LlmMemoryExtractor, MockMemoryExtractor
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.obs import correlation_id
from app.turn_pipeline import run_turn
from eval.memory_lifecycle.score import condition_score
from eval.ten_workstream.load import extract_scripts, llm_scripts, load_fixture, load_probes
from eval.ten_workstream.run import make_registry

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "out" / "ten_workstream_vertex.json"
RESULTS_MD = ROOT / "docs" / "TEN_WORKSTREAM_VERTEX_RESULTS.md"

PRICE_IN_PER_M = 0.10
PRICE_OUT_PER_M = 0.40
MAX_CALLS = 15
MAX_INPUT_TOKENS = 18_000
MAX_OUTPUT_TOKENS = 8_000
SAFETY_ENVELOPE_USD = 0.05

PROBE_IDS = (
    "p06_return_e_after_navy_correction",
    "p08_deictic_fix_that",
    "p11_long_gap_return_a",
    "p15_full_history_has_extra",
    "p13_recent_favors_wrong",
)


def estimate_block() -> dict:
    max_usd = round(
        MAX_INPUT_TOKENS * PRICE_IN_PER_M / 1_000_000
        + MAX_OUTPUT_TOKENS * PRICE_OUT_PER_M / 1_000_000,
        6,
    )
    return {
        "purpose": (
            "10-ws fixture cards → mock seed → Vertex extract → Writer → Store → "
            "frozen CF → WorkingContextBuilder → ContextPackage → Vertex answer"
        ),
        "not_purpose": [
            "statistical benchmark",
            "natural human behavior",
            "routing retune",
            "full 50-turn Cloud Run Vertex replay",
        ],
        "probes": list(PROBE_IDS),
        "model": "gemini-2.5-flash-lite",
        "region": "us-central1",
        "project": "contextflow-506414",
        "calls_per_probe": "extract generate + propose + answer generate ≤ 3",
        "max_calls": MAX_CALLS,
        "embed_calls": 0,
        "embed_mode": "CF_EMBED_LOCAL=1",
        "input_tokens_est": f"≤ {MAX_INPUT_TOKENS}",
        "output_tokens_est": f"≤ {MAX_OUTPUT_TOKENS}",
        "price_in_per_m_usd": PRICE_IN_PER_M,
        "price_out_per_m_usd": PRICE_OUT_PER_M,
        "expected_max_cost_usd": max_usd,
        "safety_envelope_usd": SAFETY_ENVELOPE_USD,
        "seeding": (
            "Non-probe turns use MockLLM + MockMemoryExtractor scripts from "
            "fixture.json. Those historical memory items were NOT Vertex-extracted."
        ),
    }


def _usage(resp) -> dict:
    meta = getattr(resp, "usage_metadata", None)
    if meta is None:
        return {}
    return {
        "prompt_tokens": getattr(meta, "prompt_token_count", None),
        "candidates_tokens": getattr(meta, "candidates_token_count", None),
        "total_tokens": getattr(meta, "total_token_count", None),
    }


class CountingGemini:
    """Vertex client wrapper with hard call cap and per-call telemetry."""

    def __init__(self, inner, *, max_calls: int = MAX_CALLS):
        self.inner = inner
        self.max_calls = max_calls
        self.calls = 0
        self.prompt_tokens = 0
        self.candidates_tokens = 0
        self.call_log: list[dict] = []
        self.phase = "unspecified"
        self.probe_id: str | None = None
        self.turn: int | None = None
        self.correlation: str | None = None
        self._types = inner._types_mod
        self._client = inner._client
        self.LITE_MODEL = inner.LITE_MODEL
        self.GEN_MODEL = inner.GEN_MODEL

    def _bump(self, r, *, call_type: str, model: str) -> dict:
        self.calls += 1
        if self.calls > self.max_calls:
            raise RuntimeError(
                f"vertex_ten_slice_call_cap_{self.max_calls}_STOP_no_retry"
            )
        u = _usage(r)
        pt = int(u.get("prompt_tokens") or 0)
        ct = int(u.get("candidates_tokens") or 0)
        self.prompt_tokens += pt
        self.candidates_tokens += ct
        cost = pt * PRICE_IN_PER_M / 1_000_000 + ct * PRICE_OUT_PER_M / 1_000_000
        # google-genai rarely exposes Cloud Trace ids on the response object.
        trace = getattr(r, "response_id", None) or getattr(r, "model_version", None)
        entry = {
            "n": self.calls,
            "probe": self.probe_id,
            "turn": self.turn,
            "call_type": call_type,
            "model": model,
            "region": os.environ.get("GCP_REGION"),
            "latency_ms": None,  # filled by caller wrapper
            "prompt_tokens": pt,
            "output_tokens": ct,
            "estimated_cost_usd": round(cost, 8),
            "correlation_id": self.correlation,
            "vertex_response_id": trace,
        }
        self.call_log.append(entry)
        return entry

    def propose(self, prompt: str, schema: dict) -> dict:
        t0 = time.perf_counter()
        r = self._client.models.generate_content(
            model=self.LITE_MODEL,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        entry = self._bump(r, call_type="propose", model=self.LITE_MODEL)
        entry["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return json.loads(r.text)

    def generate(self, prompt: str) -> str:
        t0 = time.perf_counter()
        call_type = self.phase if self.phase in ("extract", "answer") else "generate"
        r = self._client.models.generate_content(
            model=self.GEN_MODEL,
            contents=prompt,
            config=self._types.GenerateContentConfig(temperature=0.2),
        )
        entry = self._bump(r, call_type=call_type, model=self.GEN_MODEL)
        entry["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return r.text

    def embed(self, texts: list[str]):
        return MockLLM().embed(texts)

    def cost_usd(self) -> float:
        return (
            self.prompt_tokens * PRICE_IN_PER_M / 1_000_000
            + self.candidates_tokens * PRICE_OUT_PER_M / 1_000_000
        )


def _brief(item) -> dict:
    return {
        "id": item.id,
        "kind": item.kind,
        "text": item.text,
        "status": item.status,
        "workstream_id": item.workstream_id,
        "referent_id": item.referent_id,
        "slot": item.slot,
        "source_turn": item.source_turn,
    }


def _failure_layer(row: dict) -> str:
    gold = row.get("gold_task_id")
    gold_pol = row.get("gold_policy")
    acted = row["decision"] != "CLARIFY"
    task = row.get("selected_task")
    if gold_pol == "CLARIFY":
        return "AMBIGUITY" if not acted else "RESOLUTION"
    if acted and gold and task and task != gold:
        return "RESOLUTION"
    if gold_pol == "ACT" and not acted:
        return "RESOLUTION"
    if row.get("critical_missing_state"):
        if row.get("extract_status") in ("rejected", "uncertain", "empty", "failed"):
            return "EXTRACTION"
        if not row.get("writer_ok"):
            return "WRITER"
        return "COMPILER"
    if row.get("contamination"):
        return "COMPILER"
    if acted and row.get("answer") and len(row["answer"]) < 20:
        return "ANSWER_MODEL"
    return "OTHER"


def _load_mock_compare() -> dict[str, dict]:
    path = ROOT / "eval" / "out" / "ten_workstream.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {p["probe_id"]: p for p in data.get("probes") or []}


def run() -> dict:
    est = estimate_block()
    print(json.dumps({"pre_execution_estimate": est}, indent=2))
    if est["expected_max_cost_usd"] > SAFETY_ENVELOPE_USD:
        print("STOP: estimate above <$0.05 envelope")
        return {"status": "stopped_estimate_above_envelope", "estimate": est}

    os.environ["GCP_PROJECT"] = os.getenv("GCP_PROJECT") or "contextflow-506414"
    os.environ["GCP_REGION"] = "us-central1"
    os.environ["CF_USE_VERTEX"] = "1"
    os.environ["CF_EMBED_LOCAL"] = "1"
    os.environ["CF_LITE_MODEL"] = "gemini-2.5-flash-lite"
    os.environ["CF_GEN_MODEL"] = "gemini-2.5-flash-lite"

    # Class attrs on GeminiClient are read at import; force Lite after construct.
    from app.llm.gemini import GeminiClient

    fx = load_fixture()
    probes_all = {p["id"]: p for p in load_probes()}
    probes = [probes_all[i] for i in PROBE_IDS]
    probe_by_turn = {p["turn"]: p for p in probes}
    mock_by_id = _load_mock_compare()

    exp_corr = correlation_id(f"ten-ws-vertex-{uuid.uuid4().hex[:10]}")
    cid = fx["meta"]["conversation_id"] + "-vertex"

    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id=cid)
    writer = MemoryWriter(store, reg)
    mock_llm = MockLLM(llm_scripts(fx))
    mock_ext = MockMemoryExtractor(extract_scripts(fx))
    eng = Engine(mock_llm, reg, SETTINGS, memory_store=store)

    raw = GeminiClient(use_vertex=True)
    raw.LITE_MODEL = "gemini-2.5-flash-lite"
    raw.GEN_MODEL = "gemini-2.5-flash-lite"
    vertex = CountingGemini(raw, max_calls=MAX_CALLS)
    compiler = ContextCompiler()
    rows: list[dict] = []
    seed_turns: list[int] = []
    vertex_turns: list[int] = []

    for spec in fx["turns"]:
        et, msg = spec["turn"], spec["message"]
        if et in probe_by_turn:
            probe = probe_by_turn[et]
            vertex_turns.append(et)
            probe_corr = correlation_id(f"{exp_corr}-{probe['id']}")
            vertex.probe_id = probe["id"]
            vertex.turn = et
            vertex.correlation = probe_corr
            calls_before = vertex.calls
            log_before = len(vertex.call_log)

            ids_before = {i.id for i in store.all()}
            n_before = len(store.all())

            # extract uses generate(); mark phase for telemetry
            vertex.phase = "extract"
            eng.llm = vertex
            ext = LlmMemoryExtractor(vertex)

            # Split phases: extract first, then route/answer with phase flip.
            from app.memory.extractor import ExtractRequest, apply_extraction

            req = ExtractRequest(
                message=msg,
                source_turn=et,
                conversation_id=cid,
                history=[],
                open_workstreams=eng.reg.open_tasks(),
                asserted_items=store.asserted(),
            )
            t0 = time.perf_counter()
            extracted = apply_extraction(ext, writer, req)
            vertex.phase = "answer"  # next generate is answer; propose is separate
            routed = eng.handle_turn(msg, et)
            wall_ms = round((time.perf_counter() - t0) * 1000, 1)

            # Restore mock llm for subsequent seed turns
            eng.llm = mock_llm

            pkg = routed.package
            rendered = compiler.render(pkg) if pkg else ""
            cf_s = condition_score(rendered, probe)
            acted = routed.transition.value != "CLARIFY"
            gold = probe.get("gold_task_id")
            wrong_act = bool(
                acted and gold and routed.task_id and routed.task_id != gold
            )
            critical = bool(
                gold and acted and routed.task_id == gold and cf_s.get("thin_context")
            )
            accepted = [
                _brief(i) for i in extracted.items if i.status == "asserted"
            ]
            extract_status = (
                "rejected" if not extracted.ok else
                ("accepted" if extracted.items else "empty")
            )
            if any("uncertain" in e or "llm_extract" in e for e in (extracted.errors or [])):
                if not extracted.items:
                    extract_status = "uncertain" if "uncertain" in str(extracted.errors) else extract_status

            new_ids = {i.id for i in store.all()} - ids_before
            row = {
                "probe_id": probe["id"],
                "turn": et,
                "utterance_kind": probe.get("utterance_kind"),
                "category": probe.get("category"),
                "message_summary": msg[:80],
                "correlation_id": probe_corr,
                "gold_task_id": gold,
                "gold_referent_id": probe.get("gold_referent_id"),
                "gold_policy": probe.get("gold_policy"),
                "extraction": {
                    "status": extract_status,
                    "ok": extracted.ok,
                    "errors": list(extracted.errors or []),
                    "accepted_items": accepted,
                    "usable_canonical_patches": bool(accepted),
                },
                "persistence": {
                    "writer_ok": extracted.ok,
                    "store_grew": len(store.all()) > n_before,
                    "new_item_ids": sorted(new_ids),
                },
                "routing": {
                    "decision": routed.transition.value,
                    "selected_task": routed.task_id,
                    "selected_referent": routed.predicted_referent_id,
                    "task_match": (routed.task_id == gold) if gold else None,
                    "wrong_ACT": wrong_act,
                    "clarify_question": routed.clarify_question,
                },
                "working_context": {
                    "rendered_chars": len(rendered),
                    "memory_item_ids": list(pkg.memory_item_ids) if pkg else [],
                    "included_loop_ids": list(pkg.included_loop_ids) if pkg else [],
                    "summary": rendered[:600],
                    "required_state": list(probe.get("needed_state") or []),
                    "missing_state": (cf_s.get("missing") or {}).get("needed_state") or [],
                    "sufficient_no_leak": cf_s.get("sufficient_no_leak"),
                    "thin_context": cf_s.get("thin_context"),
                    "stale_present": cf_s.get("stale_present") or [],
                },
                "contamination": cf_s.get("leaks") or [],
                "answer": (routed.answer or "")[:600],
                "answer_continued": bool(routed.answer and len(routed.answer) > 40),
                "critical_missing_state": critical,
                "wall_ms": wall_ms,
                "vertex_calls_this_probe": vertex.calls - calls_before,
                "call_log": vertex.call_log[log_before:],
                "decision": routed.transition.value,
                "selected_task": routed.task_id,
                "extract_status": extract_status,
                "writer_ok": extracted.ok,
            }
            row["failure_layer"] = _failure_layer(row)

            mock = mock_by_id.get(probe["id"]) or {}
            row["compare_mock"] = {
                "mock_decision": mock.get("decision"),
                "mock_task": mock.get("selected_task"),
                "mock_referent": mock.get("selected_referent"),
                "mock_cf_sufficient": (mock.get("CF") or {}).get("sufficient_no_leak"),
                "mock_contamination": mock.get("contamination_state"),
                "mock_failure_layer": mock.get("failure_layer"),
                "diverged": (
                    mock.get("selected_task") != routed.task_id
                    or mock.get("decision") != routed.transition.value
                ),
            }
            # Layer attribution for divergence
            if row["compare_mock"]["diverged"]:
                if mock.get("selected_task") != routed.task_id:
                    # Vertex propose may differ; frozen CF still decides.
                    row["compare_mock"]["divergence_layer_hint"] = (
                        "RESOLUTION_or_proposal_input — check propose vs frozen gate; "
                        "do not blame answer model for routing"
                    )
                else:
                    row["compare_mock"]["divergence_layer_hint"] = "OTHER"
            rows.append(row)
        else:
            seed_turns.append(et)
            eng.llm = mock_llm
            run_turn(
                eng, writer, mock_ext,
                conversation_id=cid, message=msg, turn=et,
            )

    cost = vertex.cost_usd()
    payload = {
        "status": "ran",
        "experiment_correlation_id": exp_corr,
        "estimate": est,
        "provider": "vertex",
        "project": os.environ["GCP_PROJECT"],
        "region": os.environ["GCP_REGION"],
        "models": {"lite": vertex.LITE_MODEL, "gen": vertex.GEN_MODEL},
        "seeding": {
            "method": "MockLLM + MockMemoryExtractor on non-probe turns",
            "seed_turns": seed_turns,
            "vertex_turns": vertex_turns,
            "honest_note": (
                "Memory items established on seed turns were scripted mock "
                "extractions, not Vertex. Vertex extraction applies only on "
                f"turns {vertex_turns}."
            ),
        },
        "calls": vertex.calls,
        "prompt_tokens": vertex.prompt_tokens,
        "candidates_tokens": vertex.candidates_tokens,
        "actual_usd_est": round(cost, 6),
        "within_envelope": cost <= SAFETY_ENVELOPE_USD,
        "cloud_run_cost_usd": 0.0,
        "cloud_run_used": False,
        "call_log": vertex.call_log,
        "probes": rows,
        "store_asserted_count": len(store.asserted()),
        "open_workstreams": len(reg.open_tasks()),
        "note": (
            "Integration demonstration only. Not a quality benchmark. "
            "Frozen routing unchanged. Not committed."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                   encoding="utf-8")
    write_results_md(payload)
    print(json.dumps({
        "status": payload["status"],
        "calls": payload["calls"],
        "prompt_tokens": payload["prompt_tokens"],
        "candidates_tokens": payload["candidates_tokens"],
        "actual_usd_est": payload["actual_usd_est"],
        "within_envelope": payload["within_envelope"],
        "out": str(OUT),
        "md": str(RESULTS_MD),
        "probe_summary": [
            {
                "id": r["probe_id"],
                "decision": r["decision"],
                "task": r["selected_task"],
                "layer": r["failure_layer"],
                "calls": r["vertex_calls_this_probe"],
            }
            for r in rows
        ],
    }, indent=2))
    return payload


def write_results_md(payload: dict) -> None:
    est = payload["estimate"]
    lines = [
        "# Ten-workstream Vertex slice results",
        "",
        "**Integration demonstration only.** Not a statistical benchmark. "
        "Not natural human behavior. Frozen routing unchanged. Not committed.",
        "",
        f"**Date:** local Vertex client run. Correlation: `{payload['experiment_correlation_id']}`.",
        "",
        "## Scope",
        "",
        f"- Probes: {', '.join(PROBE_IDS)}",
        f"- Model: `{payload['models']['lite']}`",
        f"- Region: `{payload['region']}`",
        f"- Project: `{payload['project']}`",
        f"- Embeddings: local (`CF_EMBED_LOCAL=1`)",
        f"- Hard call cap: {MAX_CALLS}",
        f"- Cloud Run: **not used**",
        "",
        "## Seeding honesty",
        "",
        payload["seeding"]["honest_note"],
        "",
        "Control-plane workstream cards came from `fixture.json`. "
        "Historical memory content on non-probe turns was Mock-scripted.",
        "",
        "## Pre-execution estimate",
        "",
        f"- Input tokens est: {est['input_tokens_est']}",
        f"- Output tokens est: {est['output_tokens_est']}",
        f"- Expected max cost: **${est['expected_max_cost_usd']}**",
        f"- Safety envelope: **< ${est['safety_envelope_usd']}**",
        "",
        "## Actual cost / calls",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Vertex `generate_content` calls | **{payload['calls']}** |",
        f"| Prompt tokens | {payload['prompt_tokens']} |",
        f"| Candidate tokens | {payload['candidates_tokens']} |",
        f"| Est. USD (Flash-Lite table) | **${payload['actual_usd_est']}** |",
        f"| Within <$0.05 envelope | {payload['within_envelope']} |",
        f"| Cloud Run | $0 (not used) |",
        "",
        "Not an exact GCP invoice amount — token-table estimate only.",
        "",
        "## Per-probe results",
        "",
    ]
    for r in payload["probes"]:
        wc = r["working_context"]
        ex = r["extraction"]
        rt = r["routing"]
        cmp_ = r["compare_mock"]
        lines += [
            f"### {r['probe_id']} (turn {r['turn']})",
            "",
            f"- Utterance kind: `{r.get('utterance_kind')}`",
            f"- Correlation: `{r['correlation_id']}`",
            f"- Vertex calls this probe: {r['vertex_calls_this_probe']}",
            f"- Wall: {r['wall_ms']} ms",
            "",
            "| Layer | Result |",
            "|---|---|",
            f"| 1. Extraction | status=`{ex['status']}`; usable patches={ex['usable_canonical_patches']}; errors={ex['errors'][:4]} |",
            f"| 2. Persistence | writer_ok={r['persistence']['writer_ok']}; store_grew={r['persistence']['store_grew']}; new={r['persistence']['new_item_ids']} |",
            f"| 3. Routing (frozen CF) | `{rt['decision']}` → task=`{rt['selected_task']}` ref=`{rt['selected_referent']}`; task_match={rt['task_match']}; wrong_ACT={rt['wrong_ACT']} |",
            f"| 4. Working context | sufficient_no_leak={wc['sufficient_no_leak']}; missing={wc['missing_state']}; items={wc['memory_item_ids']} |",
            f"| 5. Contamination | {r['contamination'] or 'none'} |",
            f"| 6. Answer | continued={r['answer_continued']}; chars={len(r.get('answer') or '')} |",
            f"| 7. Failure layer | **{r['failure_layer']}** |",
            "",
            "**Mock compare**",
            "",
            f"- Mock: `{cmp_.get('mock_decision')}` / `{cmp_.get('mock_task')}` / `{cmp_.get('mock_referent')}`; CF sufficient={cmp_.get('mock_cf_sufficient')}",
            f"- Vertex: `{rt['decision']}` / `{rt['selected_task']}` / `{rt['selected_referent']}`; CF sufficient={wc['sufficient_no_leak']}",
            f"- Diverged: {cmp_.get('diverged')}"
            + (f" — {cmp_.get('divergence_layer_hint')}" if cmp_.get('diverged') else ""),
            "",
            "<details><summary>Working-context summary (truncated)</summary>",
            "",
            "```",
            (wc.get("summary") or "(empty)")[:500],
            "```",
            "",
            "</details>",
            "",
            "<details><summary>Answer (truncated)</summary>",
            "",
            "```",
            (r.get("answer") or "(none / CLARIFY)")[:500],
            "```",
            "",
            "</details>",
            "",
        ]

    lines += [
        "## What mock already showed vs what Vertex newly showed",
        "",
        "| | Mock | Vertex slice |",
        "|---|---|---|",
        "| Historical memory | scripted | same seed (scripted); not Vertex |",
        "| Probe extract | Mock scripts / empty | **real** `LlmMemoryExtractor` |",
        "| Probe propose | scripted task_id/confidence | **real** Vertex propose |",
        "| Routing | frozen CF | **same** frozen CF |",
        "| Answer | `[mock answer]…` | **real** Vertex generate |",
        "",
        "Divergence must be attributed by layer (extraction / proposal-input / "
        "resolution / reconstruction / answer). Do not collapse answer quality "
        "into a routing failure.",
        "",
        "## STOP",
        "",
        "Five-probe experiment complete. No further probes, no Cloud Run 50-turn "
        "replay, no routing retune, no commit/push from this step.",
        "",
        "## Recommendation",
        "",
    ]
    # Fill recommendation after we know outcomes — placeholder filled by caller
    # via payload flag if present
    rec = payload.get("recommendation") or "HOLD — review results before any next step."
    lines.append(rec)
    lines.append("")
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    est = estimate_block()
    print(json.dumps({"pre_execution_estimate": est, "execute": True}, indent=2))
    if est["expected_max_cost_usd"] > SAFETY_ENVELOPE_USD:
        print("STOP: estimate materially above <$0.05 envelope.")
        return 2
    payload = run()
    # GO/HOLD after results
    rows = payload.get("probes") or []
    wrong = sum(1 for r in rows if r.get("routing", {}).get("wrong_ACT"))
    calls_ok = payload.get("calls", 99) <= MAX_CALLS
    cost_ok = payload.get("within_envelope", False)
    if payload.get("status") != "ran" or not calls_ok or not cost_ok:
        rec = "**HOLD** — experiment incomplete, over budget, or over envelope. Review before any next step."
    elif wrong:
        rec = (
            "**HOLD** — at least one wrong-ACT under frozen routing with live propose. "
            "Review proposal/resolution layers before further Vertex spend. Do not retune yet."
        )
    else:
        # Integration path demonstrated; still review-gated
        rec = (
            "**GO (review-gated)** — production-shaped Vertex path exercised on 5 probes "
            "within budget/envelope, wrong-ACT=0. Next step is **human review of this "
            "report**, not automatic further experimentation."
        )
    payload["recommendation"] = rec
    write_results_md(payload)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                   encoding="utf-8")
    print(rec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
