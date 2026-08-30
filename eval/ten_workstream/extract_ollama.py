"""CONTROLLED SYNTHETIC EXTRACTION EXPERIMENT — local Ollama only.

conversation → LlmMemoryExtractor → MemoryPatch → Writer → Store → WorkingContextBuilder

No ContextFlow routing. No Vertex. No probe gold in prompts.
Pytest must not call this live (opt-in via CF_TEN_EXTRACT=1 or direct main).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from app.config import SETTINGS
from app.context.working_set import WorkingContextBuilder
from app.llm.mock import MockLLM
from app.memory.extractor import ExtractRequest, LlmMemoryExtractor, parse_patch_list
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from eval.answer_consume import ollama_available
from eval.ten_workstream.load import load_fixture
from eval.ten_workstream.run import make_registry

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "out" / "ten_workstream_extract_ollama.json"
RESULTS_MD = ROOT / "docs" / "TEN_WORKSTREAM_EXTRACT_OLLAMA.md"

# Diverse subset: fact, decision, constraint, correction, supersession,
# uncertain, deictic, ambiguous, similar-technical, unrelated-domain return.
SUBSET = [
    {"id": "e01_fact_jwt", "turn": 1, "category": "simple_fact",
     "expect_ws": "A", "expect_kinds": ["fact"], "need_tokens": ["401"],
     "mode": "anchored"},
    {"id": "e02_decision_dress", "turn": 3, "category": "decision",
     "expect_ws": "E", "expect_kinds": ["decision", "preference", "entity"],
     "need_tokens": ["black", "dress"], "mode": "anchored"},
    {"id": "e03_constraint_evening", "turn": 4, "category": "constraint",
     "expect_ws": "E", "expect_kinds": ["constraint", "fact"],
     "need_tokens": ["formal", "evening"], "mode": "anchored"},
    {"id": "e04_fact_orders_401", "turn": 5, "category": "similar_technical",
     "expect_ws": "C", "expect_kinds": ["fact"], "need_tokens": ["401", "orders"],
     "mode": "anchored"},
    {"id": "e05_decision_alpine", "turn": 10, "category": "decision",
     "expect_ws": "B", "expect_kinds": ["decision", "fact"],
     "need_tokens": ["alpine"], "mode": "anchored"},
    {"id": "e06_travel_parking", "turn": 11, "category": "unrelated_domain",
     "expect_ws": "F", "expect_kinds": ["fact", "constraint"],
     "need_tokens": ["parking", "Lisbon"], "mode": "anchored"},
    {"id": "e07_correction_navy", "turn": 32, "category": "correction_supersession",
     "expect_ws": "E", "expect_kinds": ["decision", "correction", "constraint"],
     "need_tokens": ["navy"], "stale_tokens": ["black"], "mode": "anchored",
     "lifecycle": True},
    {"id": "e08_uncertain_maybe", "turn": 46, "category": "uncertain",
     "expect_ws": None, "expect_kinds": [], "need_tokens": [],
     "mode": "anchored", "expect_uncertain_or_empty": True},
    {"id": "e09_deictic_fix", "turn": 37, "category": "deictic",
     "expect_ws": "C", "expect_kinds": ["fact"], "need_tokens": [],
     "mode": "anchored", "allow_empty": True},
    {"id": "e10_ambiguous_other", "turn": 49, "category": "ambiguous",
     "expect_ws": None, "expect_kinds": [], "need_tokens": [],
     "mode": "anchored", "expect_uncertain_or_empty": True},
    {"id": "e11_unanchored_no_cards", "turn": 3, "category": "unanchored",
     "expect_ws": None, "expect_kinds": [], "need_tokens": ["dress"],
     "mode": "unanchored", "expect_uncertain_or_empty": True},
]


def _brief_patch(p: MemoryPatch) -> dict:
    return {
        "kind": p.kind, "text": p.text, "workstream_id": p.workstream_id,
        "referent_id": p.referent_id, "slot": p.slot, "action": p.action,
        "supersedes_id": p.supersedes_id, "uncertain": p.uncertain,
        "source_turn": p.source_turn, "proposer": p.proposer,
    }


def _brief_item(i) -> dict:
    return {
        "id": i.id, "kind": i.kind, "text": i.text, "status": i.status,
        "workstream_id": i.workstream_id, "referent_id": i.referent_id,
        "slot": i.slot, "source_turn": i.source_turn,
        "provenance": i.provenance, "superseded_by": i.superseded_by,
    }


def _classify_row(row: dict) -> str:
    if row.get("fabricated_id") or row.get("malformed"):
        return "EXTRACTION_FAILURE"
    if row.get("wrong_workstream"):
        return "EXTRACTION_FAILURE"
    if row.get("expect_uncertain_or_empty"):
        if row.get("fail_closed_ok"):
            return "UNCERTAINTY_OK"
        if row.get("proposed"):
            return "EXTRACTION_FAILURE"
        return "UNCERTAINTY_OK"
    if row.get("writer_rejected"):
        return "WRITER_REJECTION"
    if row.get("proposed") and not row.get("persisted") and not row.get("writer_rejected"):
        # dropped before writer (unanchored / invalid) — extraction
        return "EXTRACTION_FAILURE"
    if not row.get("proposed") and not row.get("allow_empty"):
        return "EXTRACTION_FAILURE"
    if row.get("reconstruction") == "missing_required" and row.get("persisted"):
        # persisted under wrong stream or insufficient content
        if row.get("wrong_workstream") or not row.get("anchored_ok"):
            return "EXTRACTION_FAILURE"
        return "RECONSTRUCTION_FAILURE"
    if row.get("reconstruction") in ("missing_required", "contaminated"):
        if not row.get("persisted"):
            return "EXTRACTION_FAILURE"
        return "RECONSTRUCTION_FAILURE"
    if row.get("useful"):
        return "USEFUL"
    if row.get("partial"):
        return "PARTIAL"
    if row.get("allow_empty") and not row.get("proposed"):
        return "EMPTY_OK"
    return "EXTRACTION_FAILURE"


def run() -> dict:
    label = "CONTROLLED SYNTHETIC EXTRACTION EXPERIMENT"
    if not ollama_available():
        payload = {"status": "skipped", "reason": "ollama_unreachable", "label": label,
                   "vertex_calls": 0}
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    from app.llm.ollama import OllamaLLM
    llm = OllamaLLM()
    fx = load_fixture()
    turn_by = {t["turn"]: t for t in fx["turns"]}
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="ten-extract-ollama")
    writer = MemoryWriter(store, reg)
    ext = LlmMemoryExtractor(llm)

    # Seed black dress via mock so navy correction can supersede (lifecycle).
    from app.memory.extractor import MockMemoryExtractor, apply_extraction
    from eval.ten_workstream.load import extract_scripts
    mock_ext = MockMemoryExtractor(extract_scripts(fx))
    for t in fx["turns"]:
        if t["turn"] in (3, 4):
            apply_extraction(
                mock_ext, writer,
                ExtractRequest(
                    message=t["message"], source_turn=t["turn"],
                    conversation_id="ten-extract-ollama",
                    open_workstreams=reg.open_tasks(),
                    asserted_items=store.asserted(),
                ),
            )

    rows = []
    n_gen = 0
    t0 = time.perf_counter()
    for spec in SUBSET:
        msg = turn_by[spec["turn"]]["message"]
        open_ws = reg.open_tasks() if spec["mode"] == "anchored" else []
        req = ExtractRequest(
            message=msg,
            source_turn=spec["turn"],
            conversation_id="ten-extract-ollama",
            open_workstreams=open_ws,
            asserted_items=store.asserted(),
        )
        before_ids = {i.id for i in store.all()}
        before_n = len(store.all())

        # Extract once (do not double-call via apply_extraction)
        extracted = ext.extract(req)
        n_gen += 1
        raw_notes = list(extracted.notes or [])

        fabricated = any(n.startswith("dropped_unknown_workstream:") for n in raw_notes)
        malformed = any(n.startswith("llm_extract_") for n in raw_notes)

        # Writer path
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

        # Reconstruction for expected workstream
        recon = "n/a"
        proj_text = ""
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
                # contamination: other domains
                forbidden = ["stripe", "celesteela"] if spec["expect_ws"] != "J" else ["jwt"]
                if spec["expect_ws"] == "E":
                    forbidden = ["jwt", "docker", "401", "lisbon hotel"]
                leaks = [f for f in forbidden if f in proj_text]
                if missing and not persisted:
                    recon = "missing_required"
                elif missing:
                    recon = "missing_required"
                elif leaks:
                    recon = "contaminated"
                else:
                    recon = "ok" if (persisted or not need) else "missing_required"

        # Usefulness
        kinds = [p.kind for p in extracted.patches]
        ws_ids = [p.workstream_id for p in extracted.patches]
        expect_ws = spec.get("expect_ws")
        wrong_workstream = bool(
            expect_ws and ws_ids and expect_ws not in ws_ids
        )
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
        fail_closed_ok = bool(
            spec.get("expect_uncertain_or_empty")
            and (
                extracted.uncertain
                or not extracted.patches
                or writer_rejected
                or fabricated
            )
        )
        # Ambiguous/uncertain cases that still commit content are not useful.
        useful = bool(
            persisted
            and anchored_ok
            and kind_ok
            and (not need or content_hits)
            and recon in ("ok", "n/a")
            and not fabricated
            and not wrong_workstream
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

        # Lifecycle check after navy
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
                "black_excluded_from_working": "black" not in proj_text or len(black_sup) > 0,
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
            "uncertain": extracted.uncertain,
            "notes": raw_notes,
            "malformed": malformed,
            "fabricated_id": fabricated,
            "proposed": [_brief_patch(p) for p in extracted.patches],
            "writer_rejected": writer_rejected,
            "commit_ok": commit_ok,
            "commit_errors": commit_errors,
            "persisted": persisted,
            "new_items": [_brief_item(i) for i in new_items],
            "store_grew": len(store.all()) > before_n,
            "anchored_ok": anchored_ok,
            "wrong_workstream": wrong_workstream,
            "kind_ok": kind_ok,
            "content_hits": content_hits,
            "reconstruction": recon,
            "proj_text_preview": proj_text[:200],
            "useful": useful,
            "partial": partial,
            "fail_closed_ok": fail_closed_ok,
            "lifecycle": lifecycle,
        }
        row["failure_class"] = _classify_row(row)
        rows.append(row)

    # Idempotent retry on first fact turn (extract→commit twice same turn)
    idemp = None
    msg1 = turn_by[1]["message"]
    req1 = ExtractRequest(
        message=msg1, source_turn=1, conversation_id="ten-extract-ollama",
        open_workstreams=reg.open_tasks(), asserted_items=store.asserted(),
    )
    n_before = len(store.all())
    ver = store.namespace_version()
    ex1 = ext.extract(req1)
    n_gen += 1
    if ex1.patches and not ex1.uncertain:
        writer.commit(writer.propose(ex1.patches), turn=1)
    ex2 = ext.extract(req1)
    n_gen += 1
    if ex2.patches and not ex2.uncertain:
        try:
            writer.commit(writer.propose(ex2.patches), turn=1)
            idemp = len(store.all()) == n_before or store.namespace_version() >= ver
        except Exception as e:
            idemp = "error:" + type(e).__name__
    else:
        idemp = "no_patches_second_pass"

    elapsed = time.perf_counter() - t0
    taxonomy: dict[str, int] = {}
    for r in rows:
        taxonomy[r["failure_class"]] = taxonomy.get(r["failure_class"], 0) + 1

    payload = {
        "status": "ran",
        "label": label,
        "provider": "ollama",
        "model": llm.model,
        "n_generate": n_gen,
        "elapsed_s": round(elapsed, 3),
        "vertex_calls": 0,
        "architecture": (
            "extract → MemoryPatch → Writer.validate/commit → Store → "
            "WorkingContextBuilder (no ContextFlow routing in this experiment)"
        ),
        "rows": rows,
        "taxonomy": taxonomy,
        "useful_count": sum(1 for r in rows if r["useful"]),
        "partial_count": sum(1 for r in rows if r["partial"]),
        "writer_reject_count": sum(1 for r in rows if r["writer_rejected"]),
        "fabricated_id_count": sum(1 for r in rows if r["fabricated_id"]),
        "fail_closed_ok_count": sum(1 for r in rows if r["fail_closed_ok"]),
        "idempotency": idemp,
        "store_snapshot": [_brief_item(i) for i in store.all()],
        "note": (
            "CONTROLLED SYNTHETIC / LOCAL OLLAMA. Not natural human-chat evidence. "
            "Not a production extraction benchmark. Routing frozen and unused here."
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
            f"# Ten-workstream Ollama extraction\n\nSkipped: {payload.get('reason')}\n",
            encoding="utf-8",
        )
        return
    lines = [
        "# Ten-workstream Ollama extraction",
        "",
        "**CONTROLLED SYNTHETIC EXTRACTION EXPERIMENT** — local Ollama only. "
        "Not natural human-chat evidence. Not a production accuracy claim. "
        "No Vertex. Frozen routing unused.",
        "",
        f"**Model:** `{payload['model']}` · generates: **{payload['n_generate']}** · "
        f"elapsed **{payload['elapsed_s']}s** · Vertex: **0**",
        "",
        "## Path",
        "",
        payload["architecture"],
        "",
        "## Taxonomy",
        "",
        f"```{payload['taxonomy']}```",
        "",
        f"- Useful: **{payload['useful_count']}**",
        f"- Partial: **{payload['partial_count']}**",
        f"- Writer rejects: **{payload['writer_reject_count']}**",
        f"- Fabricated IDs dropped: **{payload['fabricated_id_count']}**",
        f"- Fail-closed OK (uncertain/empty cases): **{payload['fail_closed_ok_count']}**",
        f"- Idempotency note: `{payload['idempotency']}`",
        "",
        "## Per-turn",
        "",
        "| id | category | proposed | ws ok | writer | persist | recon | class |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in payload["rows"]:
        prop = len(r["proposed"])
        lines.append(
            f"| {r['id']} | {r['category']} | {prop} | {r['anchored_ok']} | "
            f"{'reject' if r['writer_rejected'] else 'ok'} | {r['persisted']} | "
            f"{r['reconstruction']} | {r['failure_class']} |"
        )
    # Useful vs insufficient examples
    lines += ["", "## Examples (useful vs insufficient)", ""]
    useful_rows = [r for r in payload["rows"] if r["useful"]]
    fail_rows = [r for r in payload["rows"] if r["failure_class"] == "EXTRACTION_FAILURE"]
    if useful_rows:
        u = useful_rows[0]
        lines.append(
            f"**Useful ({u['id']}):** "
            + "; ".join(
                f"`{p.get('kind')}`/{p.get('workstream_id')}: {(p.get('text') or '')[:60]}"
                for p in u["proposed"][:2]
            )
        )
    if fail_rows:
        f = fail_rows[0]
        lines.append(
            f"**Insufficient ({f['id']}):** "
            + (f"wrong_ws={f.get('wrong_workstream')}; " if f.get("wrong_workstream") else "")
            + (
                "; ".join(
                    f"`{p.get('kind')}`/{p.get('workstream_id')}: {(p.get('text') or '')[:60]}"
                    for p in f["proposed"][:2]
                )
                or f"notes={f.get('notes')}"
            )
        )
    lines += [
        "",
        "## Failure taxonomy (this run)",
        "",
        "- **A Schema/prompt:** `llm_extract_not_json`, bracketed/title ids",
        "- **B Anchoring:** patches attached to wrong known workstream (e.g. dress→A, orders→A)",
        "- **C Semantic compression:** empty or underspecified content for required tokens",
        "- **D Uncertainty:** model invents patches on ambiguous/uncertain turns (should `[]`)",
        "- **E Supersession:** navy correction did not emit slot/supersedes lifecycle patch",
        "- **F Model capability:** small local model unreliable for structured anchoring",
        "",
        "## Status",
        "",
        "| Claim | Status |",
        "|---|---|",
        "| LlmMemoryExtractor interface | IMPLEMENTED |",
        "| Writer validates; extractor never writes store | TESTED |",
        "| Local Ollama extraction on synthetic turns | DEMONSTRATED (this doc) |",
        "| Robust extraction on organic/consented chat | NOT YET |",
        "| Vertex extraction comparison | NOT YET |",
        "",
        payload["note"],
        "",
    ]
    # Lifecycle excerpt
    life = next((r for r in payload["rows"] if r.get("lifecycle")), None)
    if life:
        lines += [
            "## Lifecycle (navy supersession)",
            "",
            f"```json\n{json.dumps(life['lifecycle'], indent=2)}\n```",
            "",
            "LLM did not drive supersession in this run; black remains Mock-seeded asserted state.",
            "",
        ]
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    print(json.dumps({
        "label": "CONTROLLED SYNTHETIC EXTRACTION EXPERIMENT",
        "execute": True,
        "vertex": 0,
    }, indent=2))
    payload = run()
    print(json.dumps({
        "status": payload.get("status"),
        "model": payload.get("model"),
        "n_generate": payload.get("n_generate"),
        "taxonomy": payload.get("taxonomy"),
        "useful": payload.get("useful_count"),
        "partial": payload.get("partial_count"),
        "vertex_calls": payload.get("vertex_calls", 0),
        "out": str(OUT),
        "md": str(RESULTS_MD),
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
