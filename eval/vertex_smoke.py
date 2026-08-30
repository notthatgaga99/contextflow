"""Vertex production-path smoke. Default: estimate only. Do not re-run 135-call grid.

Demonstrates (when CF_VERTEX_SMOKE=1):
  conversation → Vertex extract → Writer → Store → frozen CF → package → Vertex answer

Three probes only: assertion, heterogeneous return, ambiguous/sibling.
Hard cap: 12 generate_content-class calls. Pytest never imports this for live calls.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.config import SETTINGS
from app.context.compiler import ContextCompiler
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.extractor import LlmMemoryExtractor, MockMemoryExtractor
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.turn_pipeline import run_turn
from eval.memory_lifecycle.fixture import EXTRACT_SCRIPTS, LLM_SCRIPTS, NAVY_MSG
from eval.memory_lifecycle.run import make_registry

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "out" / "vertex_smoke.json"

# Pricing snapshot 2026-08-29 (Flash-Lite). See docs/COST_ESTIMATE.md.
PRICE_IN_PER_M = 0.10
PRICE_OUT_PER_M = 0.40
MAX_INPUT_TOKENS = 12_000
MAX_OUTPUT_TOKENS = 3_000
MAX_CALLS = 12

ESTIMATE = {
    "purpose": (
        "conversation → Vertex extract → Writer → Store → frozen CF → "
        "working context → Vertex answer"
    ),
    "not_purpose": "Accuracy benchmark. Do not expand to 135 cells.",
    "probes": [
        "assertion_jwt_401",
        "heterogeneous_return_dress",
        "ambiguous_sibling_other_one",
    ],
    "calls_per_probe": "extract generate + propose + answer generate = 3",
    "max_calls": 9,
    "hard_cap_calls": MAX_CALLS,
    "embed_calls": 0,
    "model": "gemini-2.5-flash-lite (propose + generate)",
    "input_tokens_est": f"≤ {MAX_INPUT_TOKENS}",
    "output_tokens_est": f"≤ {MAX_OUTPUT_TOKENS}",
    "price_in_per_m_usd": PRICE_IN_PER_M,
    "price_out_per_m_usd": PRICE_OUT_PER_M,
    "max_usd_calc": round(
        MAX_INPUT_TOKENS * PRICE_IN_PER_M / 1_000_000
        + MAX_OUTPUT_TOKENS * PRICE_OUT_PER_M / 1_000_000,
        6,
    ),
    "safety_envelope_usd": 0.03,
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
    """Thin wrapper: same propose/generate contract; counts calls + tokens."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0
        self.prompt_tokens = 0
        self.candidates_tokens = 0
        self._types = inner._types_mod
        self._client = inner._client
        self.LITE_MODEL = inner.LITE_MODEL
        self.GEN_MODEL = inner.GEN_MODEL

    def _bump(self, r) -> None:
        self.calls += 1
        if self.calls > MAX_CALLS:
            raise RuntimeError(f"vertex_smoke_call_cap_{MAX_CALLS}")
        u = _usage(r)
        self.prompt_tokens += int(u.get("prompt_tokens") or 0)
        self.candidates_tokens += int(u.get("candidates_tokens") or 0)

    def propose(self, prompt: str, schema: dict) -> dict:
        r = self._client.models.generate_content(
            model=self.LITE_MODEL, contents=prompt,
            config=self._types.GenerateContentConfig(
                temperature=0.2, response_mime_type="application/json",
                response_schema=schema),
        )
        self._bump(r)
        return json.loads(r.text)

    def generate(self, prompt: str) -> str:
        r = self._client.models.generate_content(
            model=self.GEN_MODEL, contents=prompt,
            config=self._types.GenerateContentConfig(temperature=0.2),
        )
        self._bump(r)
        return r.text

    def embed(self, texts: list[str]):
        # Local deterministic vectors only — no Vertex embeddings API.
        return MockLLM().embed(texts)

    def cost_usd(self) -> float:
        return (
            self.prompt_tokens * PRICE_IN_PER_M / 1_000_000
            + self.candidates_tokens * PRICE_OUT_PER_M / 1_000_000
        )


def _seed_return_world():
    """Mock-only setup so the return probe has multi-workstream memory. Free."""
    reg = make_registry()
    store = InMemoryMemoryStore(conversation_id="vertex-smoke")
    writer = MemoryWriter(store, reg)
    llm = MockLLM(LLM_SCRIPTS)
    eng = Engine(llm, reg, SETTINGS, memory_store=store)
    ext = MockMemoryExtractor(EXTRACT_SCRIPTS)
    for turn, msg in (
        (1, "JWT still returns 401 after refresh."),
        (2, "Access token TTL is 15 minutes."),
        (3, "I need a black dress for a corporate event."),
        (4, "The event is formal and in the evening."),
        (5, "Planning a Lisbon trip; the hotel needs parking."),
        (6, "The paper related-work section should use APA."),
    ):
        run_turn(eng, writer, ext, conversation_id="vertex-smoke",
                 message=msg, turn=turn)
    return reg, store, writer, eng


def _seed_sibling_world():
    reg = make_registry()
    store = InMemoryMemoryStore(conversation_id="vertex-sibling")
    writer = MemoryWriter(store, reg)
    llm = MockLLM({
        "JWT still returns 401": {"task_id": "A", "is_new_task": False, "confidence": 0.4},
        "token still expired": {"task_id": "A", "is_new_task": False, "confidence": 0.35},
        "the other one": {"task_id": "A", "is_new_task": False, "confidence": 0.4},
    })
    eng = Engine(llm, reg, SETTINGS, memory_store=store)
    ext = MockMemoryExtractor({
        "JWT still returns 401": {
            "patches": [{"kind": "fact", "text": "401 after refresh",
                         "workstream_id": "A", "referent_id": "A.loop1"}],
        },
        "token still expired": {
            "omit_referent": True,
            "patches": [{"kind": "fact", "text": "token still expired",
                         "workstream_id": "A"}],
        },
    })
    run_turn(eng, writer, ext, conversation_id="vertex-sibling",
             message="JWT still returns 401 after refresh.", turn=1)
    run_turn(eng, writer, ext, conversation_id="vertex-sibling",
             message="token still expired on this auth work", turn=2)
    return reg, store, writer, eng


def _probe(llm, *, conversation_id: str, message: str, turn: int,
           eng, writer, label: str) -> dict:
    before = [i.text for i in writer.store.all()]
    ext = LlmMemoryExtractor(llm)
    pipe = run_turn(
        eng, writer, ext,
        conversation_id=conversation_id, message=message, turn=turn,
    )
    compiler = ContextCompiler()
    pkg = pipe.turn.package
    rendered = compiler.render(pkg) if pkg else ""
    after = writer.store.all()
    asserted = [i for i in after if i.status == "asserted"]
    return {
        "label": label,
        "message": message,
        "extract_ok": pipe.extract.ok,
        "extract_errors": list(pipe.extract.errors or []),
        "items_committed": [
            {"id": i.id, "kind": i.kind, "text": i.text,
             "workstream_id": i.workstream_id, "referent_id": i.referent_id,
             "slot": i.slot, "status": i.status}
            for i in pipe.extract.items
        ],
        "store_grew": len(after) > len(before),
        "asserted_count": len(asserted),
        "transition": pipe.turn.transition.value,
        "task_id": pipe.turn.task_id,
        "referent_id": pipe.turn.predicted_referent_id,
        "clarify_question": pipe.turn.clarify_question,
        "included_loop_ids": list(pkg.included_loop_ids) if pkg else [],
        "rendered_package": rendered[:1200],
        "answer": (pipe.turn.answer or "")[:800],
        "layer_notes": [],
    }


def _classify(row: dict) -> None:
    notes = row["layer_notes"]
    if not row["extract_ok"] or (not row["items_committed"] and "ambiguous" in row["label"]):
        if "ambiguous" in row["label"]:
            notes.append("extractor_may_omit_under_ambiguity")
        elif not row["items_committed"]:
            notes.append("extraction_limitation_or_writer_reject")
    if row["task_id"] and row["transition"] != "CLARIFY":
        # Package sufficiency vs answer quality
        rendered = (row.get("rendered_package") or "").lower()
        answer = (row.get("answer") or "").lower()
        if row["label"] == "heterogeneous_return_dress":
            if "lisbon" in rendered or "apa" in rendered:
                notes.append("package_leaked_irrelevant_workstream")
            if "dress" not in rendered and "outfit" not in rendered and "navy" not in rendered and "black" not in rendered and "formal" not in rendered:
                notes.append("package_missing_dress_state")
            if answer and "lisbon" not in answer and len(answer) > 20:
                notes.append("answer_continued_from_package")
            elif answer:
                notes.append("answer_model_limitation_or_thin")
        if row["label"] == "assertion_jwt_401":
            if row["items_committed"]:
                notes.append("writer_accepted_patch")
            elif row["extract_errors"]:
                notes.append("writer_or_parse_rejected")
        if row["label"] == "ambiguous_sibling_other_one":
            if row["transition"] == "CLARIFY":
                notes.append("clarify_legitimate")
            else:
                notes.append(
                    f"frozen_resolver_{row['transition']}_clarify_also_valid_not_a_retune"
                )


def run() -> dict:
    print(json.dumps({"estimate": ESTIMATE, "execute": True}, indent=2))
    os.environ.setdefault("GCP_PROJECT", os.getenv("GCP_PROJECT") or "contextflow-506414")
    os.environ.setdefault("GCP_REGION", os.getenv("GCP_REGION") or "asia-south1")
    os.environ["CF_USE_VERTEX"] = "1"
    os.environ.setdefault("CF_LITE_MODEL", "gemini-2.5-flash-lite")
    os.environ.setdefault("CF_GEN_MODEL", "gemini-2.5-flash-lite")

    from app.llm.gemini import GeminiClient
    llm = CountingGemini(GeminiClient(use_vertex=True))

    rows = []

    # Probe 1 — straightforward assertion on seeded cards (no prior mock memory).
    reg = make_registry()
    store = InMemoryMemoryStore(conversation_id="vertex-assert")
    writer = MemoryWriter(store, reg)
    eng = Engine(llm, reg, SETTINGS, memory_store=store)
    r1 = _probe(
        llm, conversation_id="vertex-assert",
        message="JWT still returns 401 after refresh.", turn=1,
        eng=eng, writer=writer, label="assertion_jwt_401",
    )
    _classify(r1)
    rows.append(r1)

    # Probe 2 — heterogeneous return (Mock setup, Vertex for the return turn).
    reg, store, writer, eng = _seed_return_world()
    eng.llm = llm
    r2 = _probe(
        llm, conversation_id="vertex-smoke",
        message="back to the dress for the corporate event", turn=7,
        eng=eng, writer=writer, label="heterogeneous_return_dress",
    )
    # Required-state check against store, not only package text.
    asserted_b = " ".join(i.text for i in store.asserted("B")).lower()
    rendered = (r2.get("rendered_package") or "").lower()
    if "black" in asserted_b or "formal" in asserted_b or "evening" in asserted_b:
        if r2["task_id"] == "B" and "lisbon" not in rendered and "apa" not in rendered:
            r2["layer_notes"].append("memory_survived_unrelated_still_stored")
    _classify(r2)
    rows.append(r2)

    # Probe 3 — ambiguous sibling referent (Mock setup, Vertex on deictic turn).
    reg, store, writer, eng = _seed_sibling_world()
    eng.llm = llm
    r3 = _probe(
        llm, conversation_id="vertex-sibling",
        message="no, the other one", turn=3,
        eng=eng, writer=writer, label="ambiguous_sibling_other_one",
    )
    _classify(r3)
    rows.append(r3)

    cost = llm.cost_usd()
    payload = {
        "status": "ran",
        "estimate": ESTIMATE,
        "provider": "vertex",
        "project": os.environ.get("GCP_PROJECT"),
        "region": os.environ.get("GCP_REGION"),
        "models": {"lite": llm.LITE_MODEL, "gen": llm.GEN_MODEL},
        "calls": llm.calls,
        "prompt_tokens": llm.prompt_tokens,
        "candidates_tokens": llm.candidates_tokens,
        "actual_usd_est": round(cost, 6),
        "within_envelope": cost <= ESTIMATE["safety_envelope_usd"],
        "rows": rows,
        "navy_msg_unused_here": NAVY_MSG[:40],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                   encoding="utf-8")
    print(json.dumps({
        "status": "ran",
        "calls": llm.calls,
        "prompt_tokens": llm.prompt_tokens,
        "candidates_tokens": llm.candidates_tokens,
        "actual_usd_est": round(cost, 6),
        "labels": [r["label"] for r in rows],
        "transitions": [r["transition"] for r in rows],
        "tasks": [r["task_id"] for r in rows],
    }, indent=2))
    return payload


def main() -> int:
    print(json.dumps({"estimate": ESTIMATE, "execute": os.getenv("CF_VERTEX_SMOKE") == "1"},
                     indent=2))
    if os.getenv("CF_VERTEX_SMOKE") != "1":
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"status": "not_executed", "estimate": ESTIMATE}, indent=2),
                       encoding="utf-8")
        print("Set CF_VERTEX_SMOKE=1 to run ≤9 Vertex calls after reviewing the estimate.")
        return 0
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
