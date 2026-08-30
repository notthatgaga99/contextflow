"""Phase 4 — TINY VERTEX EXTRACTOR COMPARISON.

CONTROLLED ADVERSARIAL SYNTHETIC FIXTURE — same 11 Phase-3 turns.
Variable: model only (Vertex gemini-2.5-flash-lite vs recorded qwen2.5:1.5b).
Contract identical: LlmMemoryExtractor → Writer → Store → WorkingContextBuilder.

≤11 extract generate_content calls. No propose. No answer. No embeddings.
No ContextFlow routing. No probe gold. Extractor cannot choose ACT/CLARIFY.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from app.context.working_set import WorkingContextBuilder
from app.llm.mock import MockLLM
from app.memory.extractor import (
    ExtractRequest,
    LlmMemoryExtractor,
    MockMemoryExtractor,
    apply_extraction,
)
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from eval.ten_workstream.extract_ollama import (
    SUBSET,
    _brief_item,
    _brief_patch,
)
from eval.ten_workstream.load import extract_scripts, load_fixture
from eval.ten_workstream.run import make_registry

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "out" / "ten_workstream_extract_vertex.json"
OLLAMA_OUT = ROOT / "eval" / "out" / "ten_workstream_extract_ollama.json"
RESULTS_MD = ROOT / "docs" / "TEN_WORKSTREAM_EXTRACT_VERTEX.md"

MAX_CALLS = 11
PRICE_IN_PER_M = 0.10
PRICE_OUT_PER_M = 0.40
SAFETY_ENVELOPE_USD = 0.05
# Worst-case envelope: 11 × 2k in + 11 × 500 out
EST_MAX_IN = MAX_CALLS * 2000
EST_MAX_OUT = MAX_CALLS * 500


def estimate_block() -> dict:
    cost = (
        EST_MAX_IN * PRICE_IN_PER_M / 1_000_000
        + EST_MAX_OUT * PRICE_OUT_PER_M / 1_000_000
    )
    return {
        "experiment": "Phase 4 tiny Vertex extractor comparison",
        "fixture_label": "CONTROLLED ADVERSARIAL SYNTHETIC FIXTURE",
        "model": "gemini-2.5-flash-lite",
        "region": "us-central1",
        "max_calls": MAX_CALLS,
        "call_types": ["extract generate only"],
        "no_propose": True,
        "no_answer": True,
        "no_embeddings": True,
        "expected_input_tokens_max": EST_MAX_IN,
        "expected_output_tokens_max": EST_MAX_OUT,
        "expected_max_cost_usd": round(cost, 6),
        "safety_envelope_usd": SAFETY_ENVELOPE_USD,
        "price": f"${PRICE_IN_PER_M}/1M in + ${PRICE_OUT_PER_M}/1M out",
        "anchoring_context": (
            "mode=anchored: open workstream cards [id] title/goal/loops + "
            "asserted memory summaries. mode=unanchored (e11): empty cards."
        ),
    }


def _usage(r) -> dict:
    meta = getattr(r, "usage_metadata", None)
    if meta is None:
        return {}
    return {
        "prompt_tokens": getattr(meta, "prompt_token_count", None),
        "candidates_tokens": getattr(meta, "candidates_token_count", None),
    }


class CountingExtractLLM:
    """Hard-capped extract-only Vertex wrapper. No embed/propose path used."""

    def __init__(self, inner, *, max_calls: int = MAX_CALLS):
        self.inner = inner
        self.max_calls = max_calls
        self.calls = 0
        self.prompt_tokens = 0
        self.candidates_tokens = 0
        self.call_log: list[dict] = []
        self._types = inner._types_mod
        self._client = inner._client
        self.GEN_MODEL = inner.GEN_MODEL
        self.LITE_MODEL = inner.LITE_MODEL
        self.turn: int | None = None
        self.row_id: str | None = None

    def generate(self, prompt: str) -> str:
        self.calls += 1
        if self.calls > self.max_calls:
            raise RuntimeError(f"vertex_extract_call_cap_{self.max_calls}_STOP")
        t0 = time.perf_counter()
        r = self._client.models.generate_content(
            model=self.GEN_MODEL,
            contents=prompt,
            config=self._types.GenerateContentConfig(temperature=0.2),
        )
        u = _usage(r)
        pt = int(u.get("prompt_tokens") or 0)
        ct = int(u.get("candidates_tokens") or 0)
        self.prompt_tokens += pt
        self.candidates_tokens += ct
        cost = pt * PRICE_IN_PER_M / 1_000_000 + ct * PRICE_OUT_PER_M / 1_000_000
        self.call_log.append({
            "n": self.calls,
            "id": self.row_id,
            "turn": self.turn,
            "call_type": "extract",
            "model": self.GEN_MODEL,
            "prompt_tokens": pt,
            "output_tokens": ct,
            "estimated_cost_usd": round(cost, 8),
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        })
        return r.text

    def cost_usd(self) -> float:
        return (
            self.prompt_tokens * PRICE_IN_PER_M / 1_000_000
            + self.candidates_tokens * PRICE_OUT_PER_M / 1_000_000
        )


def _failure_layer(row: dict) -> str:
    """Phase-4 granular layers. Writer rejection of unsafe patches ≠ writer bug."""
    if row.get("malformed"):
        return "SCHEMA_FAILURE"
    if row.get("fabricated_id"):
        return "ANCHORING_FAILURE"
    if row.get("expect_uncertain_or_empty"):
        if row.get("fail_closed_ok") and not row.get("persisted"):
            return "UNCERTAINTY_OK"
        if row.get("proposed") or row.get("persisted"):
            return "UNCERTAINTY_FAILURE"
        return "UNCERTAINTY_OK"
    if row.get("writer_rejected"):
        errs = " ".join(row.get("commit_errors") or []).lower()
        # Writer rejecting invented loops/ids is protection, not a writer defect.
        if "unknown referent" in errs or "unknown workstream" in errs:
            return "ANCHORING_FAILURE"
        if "uncertain" in errs:
            return "UNCERTAINTY_FAILURE"
        return "WRITER_REJECTION"
    if row.get("wrong_workstream"):
        return "ANCHORING_FAILURE"
    if row.get("lifecycle") is not None:
        life = row["lifecycle"]
        if row.get("proposed") and not (
            life.get("black_superseded") and life.get("navy_asserted")
        ):
            # Proposed something but lifecycle incomplete
            if not life.get("navy_asserted"):
                return "LIFECYCLE_FAILURE"
        if not row.get("proposed") and row.get("category") == "correction_supersession":
            return "LIFECYCLE_FAILURE"
    if row.get("proposed") and not row.get("persisted") and not row.get("writer_rejected"):
        return "ANCHORING_FAILURE"  # dropped pre-writer
    if not row.get("proposed") and not row.get("allow_empty"):
        # empty when content expected — model or schema
        if row.get("malformed"):
            return "SCHEMA_FAILURE"
        return "SEMANTIC_COMPRESSION_FAILURE"
    if row.get("reconstruction") == "contaminated":
        return "RECONSTRUCTION_FAILURE"
    if row.get("reconstruction") == "missing_required":
        if row.get("persisted") and row.get("anchored_ok"):
            return "RECONSTRUCTION_FAILURE"
        if row.get("wrong_workstream"):
            return "ANCHORING_FAILURE"
        if not row.get("proposed"):
            return "SEMANTIC_COMPRESSION_FAILURE"
        return "RECONSTRUCTION_FAILURE"
    if row.get("useful"):
        return "USEFUL"
    if row.get("partial"):
        return "PARTIAL"
    if row.get("allow_empty") and not row.get("proposed"):
        return "EMPTY_OK"
    return "OTHER"


def _evaluate_row(spec, msg, extracted, store, writer, reg, before_ids, before_n):
    raw_notes = list(extracted.notes or [])
    fabricated = any(n.startswith("dropped_unknown_workstream:") for n in raw_notes)
    malformed = any(n.startswith("llm_extract_") for n in raw_notes)

    if extracted.uncertain or not extracted.patches:
        commit_ok, commit_errors, items = True, list(raw_notes), []
        writer_rejected = False
    else:
        patches = writer.propose(extracted.patches)
        vr = writer.validate(patches)
        if not vr.ok:
            commit_ok, commit_errors, items = False, list(vr.errors), []
            writer_rejected = True
        else:
            cr = writer.commit(patches, turn=spec["turn"])
            commit_ok, commit_errors, items = cr.ok, list(cr.errors), list(cr.items)
            writer_rejected = not cr.ok

    new_items = [i for i in store.all() if i.id not in before_ids]
    persisted = bool(new_items) or (commit_ok and items)

    recon = "n/a"
    proj_text = ""
    contaminated = False
    if spec.get("expect_ws") and not spec.get("expect_uncertain_or_empty"):
        task = reg.get(spec["expect_ws"])
        if task:
            proj = WorkingContextBuilder().project(
                task, f"{spec['expect_ws']}.loop1", store, reg.open_tasks(),
            )
            proj_text = " ".join(
                list(proj.facts) + list(proj.decisions) + list(proj.constraints)
            ).lower()
            need = [t.lower() for t in (spec.get("need_tokens") or [])]
            missing = [t for t in need if t and t not in proj_text]
            forbidden = ["stripe", "celesteela"] if spec["expect_ws"] != "J" else ["jwt"]
            if spec["expect_ws"] == "E":
                forbidden = ["jwt", "docker", "401", "lisbon hotel"]
            leaks = [f for f in forbidden if f in proj_text]
            contaminated = bool(leaks)
            if missing:
                recon = "missing_required"
            elif leaks:
                recon = "contaminated"
            else:
                recon = "ok" if (persisted or not need) else "missing_required"

    kinds = [p.kind for p in extracted.patches]
    ws_ids = [p.workstream_id for p in extracted.patches]
    expect_ws = spec.get("expect_ws")
    wrong_workstream = bool(expect_ws and ws_ids and expect_ws not in ws_ids)
    anchored_ok = (
        expect_ws is None
        or (expect_ws in ws_ids)
        or bool(spec.get("expect_uncertain_or_empty"))
        or bool(spec.get("allow_empty"))
    )
    if wrong_workstream:
        anchored_ok = False
    kind_ok = (
        not spec.get("expect_kinds")
        or any(k in kinds for k in spec["expect_kinds"])
        or bool(spec.get("expect_uncertain_or_empty"))
        or bool(spec.get("allow_empty"))
    )
    need = [t.lower() for t in (spec.get("need_tokens") or [])]
    text_blob = " ".join(p.text for p in extracted.patches).lower()
    content_hits = [t for t in need if t in text_blob]
    # Fail-closed OK: abstain / reject / drop fabricated — and do not persist asserted junk.
    fail_closed_ok = bool(
        spec.get("expect_uncertain_or_empty")
        and not persisted
        and (
            extracted.uncertain
            or not extracted.patches
            or writer_rejected
            or fabricated
        )
    )

    useful = bool(
        persisted
        and anchored_ok
        and kind_ok
        and (not need or content_hits)
        and recon in ("ok", "n/a")
        and not fabricated
        and not wrong_workstream
        and not contaminated
        and not (spec.get("expect_uncertain_or_empty") and extracted.patches)
    )
    partial = bool(
        extracted.patches
        and not useful
        and not fabricated
        and not wrong_workstream
        and (content_hits or kind_ok)
        and not spec.get("expect_uncertain_or_empty")
    )

    lifecycle = None
    if spec.get("lifecycle"):
        black = [i for i in store.historical("E") if "black" in (i.text or "").lower()]
        navy = [i for i in store.asserted("E") if "navy" in (i.text or "").lower()]
        black_sup = [i for i in black if i.status == "superseded"]
        lifecycle = {
            "black_historical": [_brief_item(i) for i in black],
            "black_superseded": len(black_sup) > 0,
            "navy_asserted": [_brief_item(i) for i in navy],
            "navy_in_working": "navy" in proj_text,
            "black_excluded_from_working": (
                "black" not in proj_text or len(black_sup) > 0
            ),
        }

    row = {
        "id": spec["id"],
        "category": spec["category"],
        "mode": spec["mode"],
        "turn": spec["turn"],
        "message": msg,
        "expect_ws": expect_ws,
        "expect_uncertain_or_empty": bool(spec.get("expect_uncertain_or_empty")),
        "allow_empty": bool(spec.get("allow_empty")),
        "valid_json": not malformed,
        "uncertain": extracted.uncertain,
        "notes": raw_notes,
        "malformed": malformed,
        "fabricated_id": fabricated,
        "proposed": [_brief_patch(p) for p in extracted.patches],
        "patch_count": len(extracted.patches),
        "patch_kinds": kinds,
        "content_hits": content_hits,
        "writer_rejected": writer_rejected,
        "commit_ok": commit_ok,
        "commit_errors": commit_errors,
        "persisted": persisted,
        "new_items": [_brief_item(i) for i in new_items],
        "store_grew": len(store.all()) > before_n,
        "anchored_ok": anchored_ok,
        "wrong_workstream": wrong_workstream,
        "kind_ok": kind_ok,
        "reconstruction": recon,
        "contaminated": contaminated,
        "proj_text_preview": proj_text[:200],
        "useful": useful,
        "partial": partial,
        "fail_closed_ok": fail_closed_ok,
        "lifecycle": lifecycle,
        "slots": [p.slot for p in extracted.patches],
        "supersedes_ids": [p.supersedes_id for p in extracted.patches],
        "referents": [p.referent_id for p in extracted.patches],
        "source_turns": [p.source_turn for p in extracted.patches],
    }
    row["failure_layer"] = _failure_layer(row)
    return row


def run() -> dict:
    est = estimate_block()
    print(json.dumps({"pre_execution_estimate": est}, indent=2))
    if est["expected_max_cost_usd"] > SAFETY_ENVELOPE_USD:
        return {"status": "stopped_estimate_above_envelope", "estimate": est}

    os.environ["GCP_PROJECT"] = os.getenv("GCP_PROJECT") or "contextflow-506414"
    os.environ["GCP_REGION"] = "us-central1"
    os.environ["CF_USE_VERTEX"] = "1"
    os.environ["CF_EMBED_LOCAL"] = "1"
    os.environ["CF_LITE_MODEL"] = "gemini-2.5-flash-lite"
    os.environ["CF_GEN_MODEL"] = "gemini-2.5-flash-lite"

    from app.llm.gemini import GeminiClient

    raw = GeminiClient(use_vertex=True)
    raw.LITE_MODEL = "gemini-2.5-flash-lite"
    raw.GEN_MODEL = "gemini-2.5-flash-lite"
    llm = CountingExtractLLM(raw, max_calls=MAX_CALLS)

    fx = load_fixture()
    turn_by = {t["turn"]: t for t in fx["turns"]}
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="ten-extract-vertex")
    writer = MemoryWriter(store, reg)
    ext = LlmMemoryExtractor(llm)

    # Seed black dress via Mock (same as Phase 3) so navy can supersede.
    mock_ext = MockMemoryExtractor(extract_scripts(fx))
    for t in fx["turns"]:
        if t["turn"] in (3, 4):
            apply_extraction(
                mock_ext, writer,
                ExtractRequest(
                    message=t["message"], source_turn=t["turn"],
                    conversation_id="ten-extract-vertex",
                    open_workstreams=reg.open_tasks(),
                    asserted_items=store.asserted(),
                ),
            )

    rows = []
    t0 = time.perf_counter()
    for spec in SUBSET:
        msg = turn_by[spec["turn"]]["message"]
        open_ws = reg.open_tasks() if spec["mode"] == "anchored" else []
        cards_note = (
            f"{len(open_ws)} workstream cards with [id] title/goal/loops"
            if open_ws else "NO workstream cards (unanchored mode)"
        )
        req = ExtractRequest(
            message=msg,
            source_turn=spec["turn"],
            conversation_id="ten-extract-vertex",
            open_workstreams=open_ws,
            asserted_items=store.asserted(),
        )
        before_ids = {i.id for i in store.all()}
        before_n = len(store.all())
        llm.row_id = spec["id"]
        llm.turn = spec["turn"]
        extracted = ext.extract(req)
        row = _evaluate_row(
            spec, msg, extracted, store, writer, reg, before_ids, before_n,
        )
        row["anchoring_context_supplied"] = cards_note
        rows.append(row)

    elapsed = time.perf_counter() - t0
    taxonomy: dict[str, int] = {}
    for r in rows:
        taxonomy[r["failure_layer"]] = taxonomy.get(r["failure_layer"], 0) + 1

    ollama_cmp = {}
    if OLLAMA_OUT.exists():
        ollama = json.loads(OLLAMA_OUT.read_text(encoding="utf-8"))
        o_by = {r["id"]: r for r in ollama.get("rows") or []}
        for r in rows:
            o = o_by.get(r["id"], {})
            ollama_cmp[r["id"]] = {
                "ollama_class": o.get("failure_class"),
                "ollama_useful": o.get("useful"),
                "ollama_wrong_ws": o.get("wrong_workstream"),
                "ollama_persisted": o.get("persisted"),
                "vertex_layer": r["failure_layer"],
                "vertex_useful": r["useful"],
                "vertex_wrong_ws": r["wrong_workstream"],
                "vertex_persisted": r["persisted"],
            }

    # Interpretation: model capability vs contract (do not blame writer for
    # rejecting invented referents).
    v_useful = sum(1 for r in rows if r["useful"])
    o_useful = sum(1 for v in ollama_cmp.values() if v.get("ollama_useful"))
    v_anchor_fail = sum(1 for r in rows if r["failure_layer"] == "ANCHORING_FAILURE")
    life = next((r for r in rows if r.get("lifecycle")), None)
    life_ok = bool(
        life and life["lifecycle"].get("black_superseded")
        and life["lifecycle"].get("navy_asserted")
    )
    anchor_invent = sum(
        1 for r in rows
        if r["failure_layer"] == "ANCHORING_FAILURE"
        or any("unknown referent" in e for e in (r.get("commit_errors") or []))
    )
    writer_true_bug = sum(
        1 for r in rows
        if r["failure_layer"] == "WRITER_REJECTION"
    )
    if v_useful >= 6 and life_ok:
        interpretation = "E"
        interpretation_text = (
            "Vertex extracts and commits lifecycle changes on this synthetic slice "
            "— architecture can support LLM-backed extraction (not production proof)."
        )
    elif writer_true_bug and any(
        r["writer_rejected"] and r.get("anchored_ok")
        and not any("unknown" in e for e in (r.get("commit_errors") or []))
        for r in rows
    ):
        interpretation = "D"
        interpretation_text = (
            "Vertex extracts plausibly but writer rejects without unknown-id errors — "
            "investigate writer/contract with concrete patch evidence."
        )
    elif v_useful > o_useful and v_anchor_fail + anchor_invent >= 2 and not life_ok:
        interpretation = "A+residual"
        interpretation_text = (
            "Vertex substantially better at workstream anchoring than 1.5B "
            "(evidence for local model-capability limitation). Residual failures are "
            "mostly invented referent loops (writer correctly rejects) and uncertainty "
            "non-abstention — extractor prompt/schema, not memory-authority defects."
        )
    elif v_useful > o_useful + 2 and v_anchor_fail <= 2:
        interpretation = "A"
        interpretation_text = (
            "Vertex substantially better than 1.5B — evidence for model-capability "
            "limitation of the local model."
        )
    elif v_useful <= o_useful + 1 and (v_anchor_fail >= 3 or anchor_invent >= 3):
        sameish = sum(
            1 for v in ollama_cmp.values()
            if v.get("ollama_wrong_ws") and v.get("vertex_wrong_ws")
        )
        if sameish >= 2 and v_useful <= 3:
            interpretation = "B"
            interpretation_text = (
                "Both models fail similarly — investigate extraction "
                "contract/schema/anchoring context."
            )
        else:
            interpretation = "C"
            interpretation_text = (
                "Vertex improves content but still wrong/invented anchoring — "
                "anchoring/context supplied to extractor may be insufficient."
            )
    elif v_useful > o_useful:
        interpretation = "A"
        interpretation_text = (
            "Vertex better than 1.5B on this slice — consistent with model-capability "
            "limitation (not production robustness)."
        )
    else:
        interpretation = "B"
        interpretation_text = (
            "No clear Vertex advantage — investigate contract/schema/anchoring "
            "before more model spend."
        )

    payload = {
        "status": "ran",
        "label": "CONTROLLED ADVERSARIAL SYNTHETIC FIXTURE — Vertex extractor comparison",
        "question": (
            "Is poor Phase-3 extraction primarily a small-local-model limitation, "
            "or a defect in the extraction contract/schema/pipeline?"
        ),
        "provider": "vertex",
        "model": "gemini-2.5-flash-lite",
        "region": "us-central1",
        "n_generate": llm.calls,
        "elapsed_s": round(elapsed, 3),
        "prompt_tokens": llm.prompt_tokens,
        "candidates_tokens": llm.candidates_tokens,
        "estimated_cost_usd": round(llm.cost_usd(), 6),
        "pre_execution_estimate": est,
        "architecture": (
            "extract → MemoryPatch → Writer.validate/commit → Store → "
            "WorkingContextBuilder (no ContextFlow routing; no answer model)"
        ),
        "anchoring_rule": est["anchoring_context"],
        "rows": rows,
        "taxonomy": taxonomy,
        "useful_count": v_useful,
        "partial_count": sum(1 for r in rows if r["partial"]),
        "writer_reject_count": sum(1 for r in rows if r["writer_rejected"]),
        "fabricated_id_count": sum(1 for r in rows if r["fabricated_id"]),
        "fail_closed_ok_count": sum(1 for r in rows if r["fail_closed_ok"]),
        "lifecycle_ok": life_ok,
        "ollama_comparison": ollama_cmp,
        "ollama_useful_count": o_useful,
        "interpretation_code": interpretation,
        "interpretation": interpretation_text,
        "call_log": llm.call_log,
        "store_snapshot": [_brief_item(i) for i in store.all()],
        "note": (
            "CONTROLLED ADVERSARIAL SYNTHETIC FIXTURE. Not organic/real-user evidence. "
            "Not a production extraction benchmark. Routing frozen and unused. "
            "Phase-3 qwen2.5:1.5b finding preserved."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                   encoding="utf-8")
    write_md(payload)
    return payload


def write_md(payload: dict) -> None:
    if payload.get("status") != "ran":
        RESULTS_MD.write_text(
            f"# Ten-workstream Vertex extraction comparison\n\n"
            f"Stopped: {payload.get('status')}\n",
            encoding="utf-8",
        )
        return
    lines = [
        "# Ten-workstream Vertex extraction comparison",
        "",
        "**CONTROLLED ADVERSARIAL SYNTHETIC FIXTURE** — Phase 4 tiny model comparison.",
        "Not organic or real-user evidence. Not a production accuracy claim.",
        "",
        f"**Question:** {payload['question']}",
        "",
        "## Methodology",
        "",
        "- Same 11 Phase-3 turns; same `LlmMemoryExtractor` prompt/schema/writer/store",
        "- Variable: model only (`qwen2.5:1.5b` recorded vs `gemini-2.5-flash-lite`)",
        "- Anchored turns receive open workstream cards `[id] title/goal/loops` + asserted summaries",
        "- e11 receives **no** workstream cards",
        "- No probe gold, no expected labels, no ACT/CLARIFY choice, no ContextFlow routing",
        "- No answer model, no embeddings, no propose calls",
        "",
        f"**Vertex model:** `{payload['model']}` @ `{payload['region']}`",
        f"**Calls:** **{payload['n_generate']}** extract · "
        f"tokens in/out **{payload['prompt_tokens']}**/**{payload['candidates_tokens']}** · "
        f"est. cost **${payload['estimated_cost_usd']}** · elapsed **{payload['elapsed_s']}s**",
        "",
        "## Comparison summary",
        "",
        f"| | Ollama 1.5B (Phase 3) | Vertex Flash-Lite |",
        f"|---|---|---|",
        f"| Useful | **{payload.get('ollama_useful_count', '?')}** | **{payload['useful_count']}** |",
        f"| Writer rejects | (see Phase 3) | **{payload['writer_reject_count']}** |",
        f"| Fabricated IDs dropped | (see Phase 3) | **{payload['fabricated_id_count']}** |",
        f"| Lifecycle (navy supersedes black) | no | "
        f"{'yes' if payload.get('lifecycle_ok') else 'no'} |",
        "",
        f"**Interpretation ({payload['interpretation_code']}):** {payload['interpretation']}",
        "",
        "## Taxonomy (Vertex)",
        "",
        f"```{payload['taxonomy']}```",
        "",
        "## Per-turn",
        "",
        "| id | category | patches | ws ok | writer | persist | recon | layer | vs 1.5B |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    cmp = payload.get("ollama_comparison") or {}
    for r in payload["rows"]:
        o = cmp.get(r["id"], {})
        lines.append(
            f"| {r['id']} | {r['category']} | {r['patch_count']} | {r['anchored_ok']} | "
            f"{'reject' if r['writer_rejected'] else 'ok'} | {r['persisted']} | "
            f"{r['reconstruction']} | {r['failure_layer']} | "
            f"{o.get('ollama_class', '?')}→{r['failure_layer']} |"
        )
    # Critical turns detail
    lines += ["", "## Critical turns", ""]
    for crit in ("e02_decision_dress", "e03_constraint_evening", "e07_correction_navy",
                 "e08_uncertain_maybe", "e09_deictic_fix", "e10_ambiguous_other",
                 "e11_unanchored_no_cards"):
        r = next((x for x in payload["rows"] if x["id"] == crit), None)
        if not r:
            continue
        patches = "; ".join(
            f"{p.get('kind')}/{p.get('workstream_id')}/{p.get('slot')}: "
            f"{(p.get('text') or '')[:50]}"
            for p in r["proposed"][:3]
        ) or "(none)"
        lines.append(
            f"- **{crit}** [{r['failure_layer']}]: {patches}"
        )
    life = next((r for r in payload["rows"] if r.get("lifecycle")), None)
    if life:
        lines += [
            "",
            "## Lifecycle (e07 navy)",
            "",
            f"```json\n{json.dumps(life['lifecycle'], indent=2)}\n```",
            "",
        ]
    lines += [
        "",
        "## What this proves",
        "",
        "- Whether Flash-Lite outperforms 1.5B on the **same** extraction contract",
        "- Whether supersession/uncertainty/unanchored fail-closed behave under Vertex",
        "",
        "## What this does not prove",
        "",
        "- Organic or consented-chat extraction quality",
        "- Production robustness",
        "- Routing quality (routing unused here)",
        "- That the architecture is broken if Vertex also fails (may be context/contract)",
        "",
        "## Status",
        "",
        "| Claim | Status |",
        "|---|---|",
        "| Extract contract unchanged | IMPLEMENTED |",
        "| Phase-3 1.5B limitation preserved | DEMONSTRATED |",
        "| Tiny Vertex extractor comparison (11 turns) | DEMONSTRATED (this doc) |",
        "| Organic extraction quality | NOT YET |",
        "",
        payload["note"],
        "",
    ]
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    print(json.dumps({
        "label": "PHASE 4 TINY VERTEX EXTRACTOR COMPARISON",
        "fixture": "CONTROLLED ADVERSARIAL SYNTHETIC FIXTURE",
        "max_calls": MAX_CALLS,
    }, indent=2))
    payload = run()
    print(json.dumps({
        "status": payload.get("status"),
        "model": payload.get("model"),
        "calls": payload.get("n_generate"),
        "prompt_tokens": payload.get("prompt_tokens"),
        "candidates_tokens": payload.get("candidates_tokens"),
        "estimated_cost_usd": payload.get("estimated_cost_usd"),
        "taxonomy": payload.get("taxonomy"),
        "useful": payload.get("useful_count"),
        "interpretation": payload.get("interpretation_code"),
        "lifecycle_ok": payload.get("lifecycle_ok"),
        "out": str(OUT),
        "md": str(RESULTS_MD),
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
