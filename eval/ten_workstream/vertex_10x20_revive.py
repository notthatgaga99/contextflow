"""Proper Vertex harness: 10×20 density revive under frozen ContextFlow.

Pricing is per *million tokens* (Flash-Lite ~$0.10/in + $0.40/out) — not
per million requests. Hard call cap is a safety stop, not a quality target.

Protocol:
  - Non-probe turns: MockLLM + MockMemoryExtractor (scripted seed — honest).
  - Probe turns (10 density revives): Vertex extract → Writer → frozen gate
    propose → L1 package → Vertex answer.
  - Gate / scorer / referent untouched.

  . .\\scripts\\env_vertex_local.ps1
  python -m eval.ten_workstream.vertex_10x20_revive
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
from app.memory.extractor import ExtractRequest, LlmMemoryExtractor, MockMemoryExtractor, apply_extraction
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.obs import correlation_id
from app.turn_pipeline import run_turn
from eval.memory_lifecycle.score import condition_score
from eval.ten_workstream.load import extract_scripts, llm_scripts, load_fixture, load_probes
from eval.ten_workstream.metrics import score_probe_row, summarize as summarize_metrics
from eval.ten_workstream.run import make_registry

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "eval" / "ten_workstream" / "fixture_10x20.json"
PROBES = ROOT / "eval" / "ten_workstream" / "probes_10x20.json"
MOCK_BASELINE = ROOT / "eval" / "out" / "ten_workstream_10x20.json"
OUT = ROOT / "eval" / "out" / "vertex_10x20_revive.json"
RESULTS_MD = ROOT / "docs" / "VERTEX_10x20_REVIVE.md"

PRICE_IN_PER_M = 0.10
PRICE_OUT_PER_M = 0.40
# 10 probes × (structured extract + route propose + answer) + headroom
MAX_CALLS = 48
SAFETY_NOTE_USD = 0.25  # soft expectation; not a hard stop


def _usage(resp) -> dict:
    meta = getattr(resp, "usage_metadata", None)
    if meta is None:
        return {}
    return {
        "prompt_tokens": getattr(meta, "prompt_token_count", None),
        "candidates_tokens": getattr(meta, "candidates_token_count", None),
    }


class CountingVertex:
    """Shared Vertex client for extract propose + route propose + answer generate."""

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
        self.LITE_MODEL = inner.LITE_MODEL
        self.GEN_MODEL = inner.GEN_MODEL
        self._types = inner._types_mod
        self._client = inner._client

    def _bump(self, r, *, call_type: str, model: str, t0: float) -> None:
        self.calls += 1
        if self.calls > self.max_calls:
            raise RuntimeError(f"vertex_10x20_call_cap_{self.max_calls}")
        u = _usage(r)
        pt = int(u.get("prompt_tokens") or 0)
        ct = int(u.get("candidates_tokens") or 0)
        self.prompt_tokens += pt
        self.candidates_tokens += ct
        self.call_log.append({
            "n": self.calls,
            "probe": self.probe_id,
            "turn": self.turn,
            "call_type": call_type,
            "model": model,
            "prompt_tokens": pt,
            "output_tokens": ct,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "est_usd": round(
                pt * PRICE_IN_PER_M / 1_000_000 + ct * PRICE_OUT_PER_M / 1_000_000, 8,
            ),
        })

    def propose(self, prompt: str, schema: dict) -> dict:
        t0 = time.perf_counter()
        call_type = "extract_propose" if self.phase == "extract" else "route_propose"
        r = self._client.models.generate_content(
            model=self.LITE_MODEL,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        self._bump(r, call_type=call_type, model=self.LITE_MODEL, t0=t0)
        return json.loads(r.text)

    def generate(self, prompt: str) -> str:
        t0 = time.perf_counter()
        r = self._client.models.generate_content(
            model=self.GEN_MODEL,
            contents=prompt,
            config=self._types.GenerateContentConfig(temperature=0.2),
        )
        self._bump(r, call_type="answer", model=self.GEN_MODEL, t0=t0)
        return r.text

    def embed(self, texts: list[str]):
        # Cost control: never bill Vertex embeddings in this harness.
        from app.llm.mock import MockLLM
        return MockLLM(dim=SETTINGS.EMBED_DIM).embed(texts)

    def cost_usd(self) -> float:
        return (
            self.prompt_tokens * PRICE_IN_PER_M / 1_000_000
            + self.candidates_tokens * PRICE_OUT_PER_M / 1_000_000
        )


def _brief(i) -> dict:
    return {
        "id": i.id, "kind": i.kind, "text": i.text, "workstream_id": i.workstream_id,
        "slot": i.slot, "status": i.status,
    }


def _load_mock_baseline() -> dict[str, dict]:
    if not MOCK_BASELINE.exists():
        return {}
    data = json.loads(MOCK_BASELINE.read_text(encoding="utf-8"))
    return {r["probe_id"]: r for r in (data.get("probes") or [])}


def run(
    model: str | None = None,
    *,
    write_artifacts: bool = True,
    max_calls: int | None = None,
) -> dict:
    """Run 10×20 Vertex revive. ``model`` sets both extract/propose and answer."""
    if not (
        os.getenv("CF_USE_VERTEX") == "1"
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    ):
        payload = {
            "status": "skipped",
            "reason": "set_env_via_scripts/env_vertex_local.ps1",
        }
        if write_artifacts:
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    os.environ.setdefault("CF_USE_VERTEX", "1")
    os.environ.setdefault("GCP_PROJECT", "contextflow-gagan-20261019")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ["GCP_PROJECT"])
    os.environ.setdefault("GCP_REGION", "us-central1")
    os.environ.setdefault("CF_VERTEX_LOCATION", "us-central1")
    os.environ.setdefault("CF_EMBED_LOCAL", "1")
    model_id = (
        (model or "").strip()
        or os.getenv("CF_LITE_MODEL")
        or "gemini-2.5-flash-lite"
    )
    os.environ["CF_LITE_MODEL"] = model_id
    os.environ["CF_GEN_MODEL"] = model_id

    from app.llm.gemini import GeminiClient

    fx = load_fixture(FIXTURE)
    probes = load_probes(path=PROBES)
    probe_by_turn = {int(p["turn"]): p for p in probes}
    mock_by_id = _load_mock_baseline()

    safe_model = model_id.replace("/", "_").replace(":", "_")
    exp_corr = correlation_id(f"v10x20-{safe_model}-{uuid.uuid4().hex[:8]}")
    cid = f"{fx['meta']['conversation_id']}-vertex-10x20-{safe_model}"

    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id=cid)
    writer = MemoryWriter(store, reg)
    mock_llm = MockLLM(llm_scripts(fx))
    mock_ext = MockMemoryExtractor(extract_scripts(fx))
    eng = Engine(mock_llm, reg, SETTINGS, memory_store=store)

    raw = GeminiClient(use_vertex=True)
    raw.LITE_MODEL = model_id
    raw.GEN_MODEL = model_id
    vertex = CountingVertex(raw, max_calls=max_calls or MAX_CALLS)
    compiler = ContextCompiler()

    rows: list[dict] = []
    seed_n = 0
    t_wall0 = time.perf_counter()

    for spec in fx["turns"]:
        et, msg = int(spec["turn"]), spec["message"]
        if et not in probe_by_turn:
            eng.llm = mock_llm
            run_turn(
                eng, writer, mock_ext,
                conversation_id=cid, message=msg, turn=et,
            )
            seed_n += 1
            continue

        probe = probe_by_turn[et]
        vertex.probe_id = probe["id"]
        vertex.turn = et
        calls_before = vertex.calls
        log_before = len(vertex.call_log)
        n_before = len(store.all())

        # 1) Live extract (structured propose inside LlmMemoryExtractor)
        vertex.phase = "extract"
        eng.llm = vertex
        ext = LlmMemoryExtractor(vertex)
        req = ExtractRequest(
            message=msg,
            source_turn=et,
            conversation_id=cid,
            open_workstreams=eng.reg.open_tasks(),
            asserted_items=store.asserted(),
        )
        t0 = time.perf_counter()
        extracted = apply_extraction(ext, writer, req)

        # 2) Frozen route + answer (propose + generate)
        vertex.phase = "answer"
        routed = eng.handle_turn(msg, et)
        wall_ms = round((time.perf_counter() - t0) * 1000, 1)
        eng.llm = mock_llm

        acted = routed.transition.value != "CLARIFY"
        gold = probe.get("gold_task_id")
        gold_ref = probe.get("gold_referent_id")
        gold_policy = probe.get("gold_policy")
        rendered = compiler.render(routed.package) if routed.package else ""
        cf_s = condition_score(rendered, probe) if acted else {}
        accepted = [_brief(i) for i in extracted.items if i.status == "asserted"]
        extract_status = (
            "rejected" if not extracted.ok else
            ("accepted" if extracted.items else "empty")
        )
        if extracted.errors and not extracted.items:
            if any("uncertain" in e or "abstain" in e or "recall" in e
                   for e in extracted.errors):
                extract_status = "uncertain"

        metrics = score_probe_row(
            gold_task=gold,
            gold_ref=gold_ref,
            gold_policy=gold_policy,
            selected_task=routed.task_id,
            selected_ref=routed.predicted_referent_id,
            acted=acted,
            open_task_ids=[t.id for t in reg.open_tasks()],
            cf_sufficient_no_leak=cf_s.get("sufficient_no_leak") if acted else None,
            thin_context=bool(cf_s.get("thin_context")) if acted else False,
            has_package=routed.package is not None,
            contamination=cf_s.get("leaks") if acted else [],
            supersession_ok=not bool(cf_s.get("stale_present")),
            persist_ok=True,
            extract_status=extract_status,
            answer_usability=cf_s.get("usability") if acted else None,
        )

        mock = mock_by_id.get(probe["id"]) or {}
        row = {
            "probe_id": probe["id"],
            "turn": et,
            "category": probe.get("category"),
            "message": msg,
            "correlation_id": f"{exp_corr}-{probe['id']}",
            "gold_task_id": gold,
            "gold_referent_id": gold_ref,
            "gold_policy": gold_policy,
            "decision": routed.transition.value,
            "selected_task": routed.task_id,
            "selected_referent": routed.predicted_referent_id,
            "task_match": metrics["task_match"],
            "referent_match": metrics["referent_match"],
            "policy_match": metrics["policy_match"],
            "wrong_act": metrics["wrong_act"],
            "working_context_sufficient": metrics["working_context_sufficient"],
            "critical_thin_context": metrics["critical_thin_context"],
            "contamination": metrics["contamination"],
            "failure_layer": metrics["failure_layer"],
            "layers": metrics["layers"],
            "extract_status": extract_status,
            "extract_errors": list(extracted.errors or []),
            "accepted_items": accepted,
            "store_grew": len(store.all()) > n_before,
            "required_state": list(probe.get("needed_state") or []),
            "missing_state": (cf_s.get("missing") or {}).get("needed_state") if acted else [],
            "leaked_state": cf_s.get("leaks") if acted else [],
            "package_chars": len(rendered),
            "answer": (routed.answer or "")[:500],
            "wall_ms": wall_ms,
            "vertex_calls_this_probe": vertex.calls - calls_before,
            "call_log": vertex.call_log[log_before:],
            "compare_mock": {
                "mock_decision": mock.get("decision"),
                "mock_task": mock.get("selected_task"),
                "mock_policy_match": mock.get("policy_match"),
                "mock_wc": mock.get("working_context_sufficient"),
                "mock_failure_layer": mock.get("failure_layer"),
                "diverged_route": (
                    bool(mock)
                    and (
                        mock.get("selected_task") != routed.task_id
                        or mock.get("decision") != routed.transition.value
                    )
                ),
            },
        }
        rows.append(row)

    summary = summarize_metrics(rows)
    cost = vertex.cost_usd()
    payload = {
        "status": "ran",
        "harness": "vertex_10x20_revive",
        "experiment_correlation_id": exp_corr,
        "fixture": "eval/ten_workstream/fixture_10x20.json",
        "probes_file": "eval/ten_workstream/probes_10x20.json",
        "provider": "vertex",
        "project": os.environ.get("GCP_PROJECT"),
        "region": os.environ.get("CF_VERTEX_LOCATION"),
        "models": {"lite": vertex.LITE_MODEL, "gen": vertex.GEN_MODEL},
        "pricing_note": (
            "USD estimates use Flash-Lite list rates per *million* tokens "
            f"(${PRICE_IN_PER_M}/1M in + ${PRICE_OUT_PER_M}/1M out). "
            "Not per-request; not an invoice."
        ),
        "seeding": {
            "method": "MockLLM + MockMemoryExtractor on non-probe turns",
            "seed_turns": seed_n,
            "vertex_probe_turns": [r["turn"] for r in rows],
            "honest_note": (
                "History memory is scripted. Vertex runs extract+propose+answer "
                "only on the 10 density revive probes."
            ),
        },
        "calls": vertex.calls,
        "max_calls": MAX_CALLS,
        "prompt_tokens": vertex.prompt_tokens,
        "candidates_tokens": vertex.candidates_tokens,
        "actual_usd_est": round(cost, 6),
        "soft_budget_usd": SAFETY_NOTE_USD,
        "within_soft_budget": cost <= SAFETY_NOTE_USD,
        "elapsed_s": round(time.perf_counter() - t_wall0, 3),
        "summary": {
            **summary,
            "wrong_act": sum(1 for r in rows if r.get("wrong_act")),
            "task_match": summary.get("task_match"),
            "policy_match": summary.get("policy_match"),
            "working_context_sufficient": summary.get("working_context_sufficient"),
            "mock_route_divergences": sum(
                1 for r in rows if (r.get("compare_mock") or {}).get("diverged_route")
            ),
        },
        "probes": rows,
        "call_log": vertex.call_log,
        "note": (
            "CONTROLLED density revive under live Vertex. "
            "Not natural chat. Gate frozen. Do not retune from this run alone."
        ),
    }
    if write_artifacts:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _write_md(payload)
    return payload


def _write_md(payload: dict) -> None:
    if payload.get("status") != "ran":
        RESULTS_MD.write_text(
            f"# Vertex 10×20 revive\n\nSkipped: {payload.get('reason')}\n",
            encoding="utf-8",
        )
        return
    s = payload.get("summary") or {}
    lines = [
        "# Vertex 10×20 density revive harness",
        "",
        "**Controlled engineering test** — not natural chat, not a statistical holdout.",
        "Frozen gate. Mock-seeded history; live Vertex on 10 revive probes.",
        "",
        f"**Model:** `{payload['models']['lite']}` @ `{payload.get('project')}` / "
        f"`{payload.get('region')}`",
        f"**Calls:** {payload.get('calls')} / cap {payload.get('max_calls')} · "
        f"tokens in={payload.get('prompt_tokens')} out={payload.get('candidates_tokens')} · "
        f"**est. USD ~{payload.get('actual_usd_est')}** "
        f"(per-million-token Flash-Lite rates; {payload.get('pricing_note')})",
        f"**Wall:** {payload.get('elapsed_s')}s · correlation `{payload.get('experiment_correlation_id')}`",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| task_match | {s.get('task_match')} |",
        f"| referent_match | {s.get('referent_match')} |",
        f"| policy_match | {s.get('policy_match')} |",
        f"| working_context_sufficient | {s.get('working_context_sufficient')} |",
        f"| wrong_act | {s.get('wrong_act')} |",
        f"| mock route divergences | {s.get('mock_route_divergences')} |",
        f"| failure_layers | `{s.get('failure_layers')}` |",
        "",
        "## Per-probe",
        "",
        "| probe | gold | vertex | task | policy | WC | wrong_act | extract | vs mock |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in payload.get("probes") or []:
        cm = r.get("compare_mock") or {}
        diverged = "diverged" if cm.get("diverged_route") else "same"
        lines.append(
            f"| {r['probe_id']} | {r.get('gold_task_id')}/{r.get('gold_policy')} | "
            f"{r.get('decision')} {r.get('selected_task')} | "
            f"{r.get('task_match')} | {r.get('policy_match')} | "
            f"{r.get('working_context_sufficient')} | {r.get('wrong_act')} | "
            f"{r.get('extract_status')} | {diverged} |"
        )
    lines += [
        "",
        "## Reproduce",
        "",
        "```powershell",
        ". .\\scripts\\env_vertex_local.ps1",
        "python -m eval.ten_workstream.vertex_10x20_revive",
        "```",
        "",
        "## Limits",
        "",
        "- History extracts are Mock scripts, not Vertex.",
        "- Answer quality is not a routing metric.",
        "- Do not retune TAU/DELTA from a single harness run.",
        "",
    ]
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="", help="Vertex model id for extract+propose+answer")
    args = ap.parse_args()
    payload = run(model=args.model or None)
    s = payload.get("summary") or {}
    print(json.dumps({
        "status": payload.get("status"),
        "project": payload.get("project"),
        "model": (payload.get("models") or {}).get("lite"),
        "calls": payload.get("calls"),
        "actual_usd_est": payload.get("actual_usd_est"),
        "task_match": s.get("task_match"),
        "policy_match": s.get("policy_match"),
        "working_context_sufficient": s.get("working_context_sufficient"),
        "wrong_act": s.get("wrong_act"),
        "mock_route_divergences": s.get("mock_route_divergences"),
        "failure_layers": s.get("failure_layers"),
        "out": str(OUT.relative_to(ROOT)),
        "md": str(RESULTS_MD.relative_to(ROOT)),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
