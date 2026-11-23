"""R4-local: real Ollama extract under 10×20 density cues (no routing, no Vertex).

CONTROLLED density-extract slice — not natural chat, not production accuracy.
Frozen gate unused. Writer still validates. Gold is evaluator-only (this file).

Picks a bounded subset of fixture_10x20 fact/decision/correction/abstain turns
so we measure extract quality under the same hop language as R1 — without 200
live LLM calls.

  python -m eval.ten_workstream.extract_density_ollama
  set CF_OLLAMA_MODEL=llama3.1:8b   # optional stronger local model
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from app.config import SETTINGS
from app.context.working_set import WorkingContextBuilder
from app.memory.extractor import ExtractRequest, LlmMemoryExtractor
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from eval.answer_consume import ollama_available
from eval.ten_workstream.load import load_fixture
from eval.ten_workstream.run import make_registry

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "eval" / "ten_workstream" / "fixture_10x20.json"
OUT = ROOT / "eval" / "out" / "extract_density_ollama.json"
RESULTS_MD = ROOT / "docs" / "EXTRACT_DENSITY_OLLAMA.md"

# Bounded slice rooted in 10×20 arcs (turn numbers from fixture_10x20.json).
SUBSET = [
    {"id": "d01_A_ttl15", "turn": 11, "expect_ws": "A", "need_tokens": ["TTL", "15"],
     "category": "fact", "mode": "anchored"},
    {"id": "d02_B_alpine", "turn": 12, "expect_ws": "B", "need_tokens": ["alpine"],
     "category": "decision", "mode": "anchored"},
    {"id": "d03_C_gateway", "turn": 13, "expect_ws": "C", "need_tokens": ["Authorization", "gateway"],
     "category": "fact", "mode": "anchored"},
    {"id": "d04_E_black", "turn": 5, "expect_ws": "E", "need_tokens": ["black"],
     "category": "decision", "mode": "anchored"},
    {"id": "d05_E_navy_corr", "turn": 35, "expect_ws": "E", "need_tokens": ["navy"],
     "stale_tokens": ["black"], "category": "correction_supersession", "mode": "anchored",
     "lifecycle": True},
    {"id": "d06_A_ttl5", "turn": 41, "expect_ws": "A", "need_tokens": ["5", "TTL"],
     "category": "correction_supersession", "mode": "anchored"},
    {"id": "d07_B_debian", "turn": 42, "expect_ws": "B", "need_tokens": ["debian"],
     "category": "decision", "mode": "anchored"},
    {"id": "d08_A_aud", "turn": 61, "expect_ws": "A", "need_tokens": ["aud", "api.internal"],
     "category": "constraint", "mode": "anchored"},
    {"id": "d09_B_4gi", "turn": 72, "expect_ws": "B", "need_tokens": ["4Gi", "4"],
     "category": "decision", "mode": "anchored"},
    {"id": "d10_E_peplum", "turn": 45, "expect_ws": "E", "need_tokens": ["peplum"],
     "category": "decision", "mode": "anchored"},
    {"id": "d11_A_recall_abstain", "turn": 131, "expect_ws": None, "need_tokens": [],
     "category": "recall_abstain", "mode": "anchored", "expect_uncertain_or_empty": True},
    {"id": "d12_A_revive_abstain", "turn": 191, "expect_ws": None, "need_tokens": [],
     "category": "revive_abstain", "mode": "anchored", "expect_uncertain_or_empty": True},
]


def _brief_patch(p: MemoryPatch) -> dict:
    return {
        "kind": p.kind, "text": p.text, "workstream_id": p.workstream_id,
        "slot": p.slot, "uncertain": p.uncertain, "action": p.action,
    }


def _need_hit(text: str, tokens: list[str]) -> bool:
    blob = (text or "").lower()
    return any(t.lower() in blob for t in tokens)


def _classify(row: dict) -> str:
    if row.get("expect_uncertain_or_empty"):
        return "ABSTAIN_OK" if row.get("fail_closed_ok") else "ABSTAIN_FAIL"
    if row.get("wrong_workstream"):
        return "WRONG_WS"
    if row.get("writer_rejected"):
        return "WRITER_REJECT"
    if not row.get("proposed") and not row.get("allow_empty"):
        return "EMPTY_FAIL"
    if row.get("useful"):
        return "USEFUL"
    if row.get("partial"):
        return "PARTIAL"
    return "EXTRACT_FAIL"


def run() -> dict:
    label = "CONTROLLED_10x20_DENSITY_EXTRACT_OLLAMA"
    if not ollama_available():
        payload = {"status": "skipped", "reason": "ollama_unreachable", "label": label}
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    from app.llm.ollama import OllamaLLM
    model = os.getenv("CF_OLLAMA_MODEL", "").strip() or None
    llm = OllamaLLM(model=model) if model else OllamaLLM()
    model_name = getattr(llm, "model", None) or os.getenv("CF_OLLAMA_MODEL") or "default"

    fx = load_fixture(FIXTURE)
    turn_by = {int(t["turn"]): t for t in fx["turns"]}
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="ten-extract-density")
    writer = MemoryWriter(store, reg)
    ext = LlmMemoryExtractor(llm)

    rows = []
    n_gen = 0
    t0 = time.perf_counter()

    # Chronological order so corrections see prior state when useful.
    ordered = sorted(SUBSET, key=lambda s: s["turn"])
    for spec in ordered:
        tspec = turn_by[spec["turn"]]
        msg = tspec["message"]
        open_ws = reg.open_tasks() if spec["mode"] == "anchored" else []
        req = ExtractRequest(
            message=msg,
            source_turn=spec["turn"],
            conversation_id="ten-extract-density",
            open_workstreams=open_ws,
            asserted_items=store.asserted(),
        )
        before = {i.id for i in store.all()}
        extracted = ext.extract(req)
        n_gen += 1
        notes = list(extracted.notes or [])
        patches = list(extracted.patches or [])
        proposed = writer.propose(patches)
        result = writer.validate(proposed)
        persisted = []
        if result.ok and proposed:
            committed = writer.commit(proposed, turn=spec["turn"])
            persisted = [
                i for i in store.all()
                if i.id not in before and i.status == "asserted"
            ]
            _ = committed

        expect_ws = spec.get("expect_ws")
        ws_ids = {p.workstream_id for p in proposed if p.workstream_id}
        wrong_ws = bool(
            expect_ws and proposed and expect_ws not in ws_ids
            and not spec.get("expect_uncertain_or_empty")
        )
        blob = " ".join(p.text for p in proposed)
        need = list(spec.get("need_tokens") or [])
        need_ok = (not need) or _need_hit(blob, need)
        stale = list(spec.get("stale_tokens") or [])
        # Reconstruction on expected hop after commit
        recon = "n/a"
        useful = False
        partial = False
        if expect_ws and not spec.get("expect_uncertain_or_empty"):
            proj = WorkingContextBuilder().project(
                reg.get(expect_ws), None, store, reg.open_tasks(),
            )
            pkg = " ".join(proj.decisions + proj.constraints + proj.facts + proj.entities)
            if need and _need_hit(pkg, need):
                recon = "ok"
                useful = not wrong_ws and bool(persisted)
            elif persisted:
                recon = "missing_required"
                partial = not wrong_ws
            else:
                recon = "missing_required"
            if stale and any(s.lower() in pkg.lower() for s in stale) and "navy" in pkg.lower():
                # black still present alongside navy is soft warn only
                pass

        fail_closed_ok = False
        if spec.get("expect_uncertain_or_empty"):
            fail_closed_ok = len(proposed) == 0 or all(p.uncertain for p in proposed)

        row = {
            "id": spec["id"],
            "turn": spec["turn"],
            "ws_intended": tspec["ws"],
            "category": spec["category"],
            "message": msg,
            "proposed": [_brief_patch(p) for p in proposed],
            "persisted": len(persisted),
            "writer_ok": result.ok,
            "writer_errors": list(result.errors or []),
            "wrong_workstream": wrong_ws,
            "need_ok": need_ok,
            "reconstruction": recon,
            "useful": useful,
            "partial": partial,
            "expect_uncertain_or_empty": bool(spec.get("expect_uncertain_or_empty")),
            "fail_closed_ok": fail_closed_ok,
            "notes": notes[:6],
        }
        row["class"] = _classify(row)
        rows.append(row)

    elapsed = round(time.perf_counter() - t0, 3)
    taxonomy: dict[str, int] = {}
    for r in rows:
        taxonomy[r["class"]] = taxonomy.get(r["class"], 0) + 1

    # Density claim check: after slice, do A/B/E hold revive-critical tokens?
    revive_ready = {}
    for wid, tokens in (
        ("A", ["5", "api.internal"]),
        ("B", ["debian", "4"]),
        ("E", ["navy", "peplum"]),
    ):
        proj = WorkingContextBuilder().project(
            reg.get(wid), None, store, reg.open_tasks(),
        )
        pkg = " ".join(proj.decisions + proj.constraints + proj.facts + proj.entities)
        revive_ready[wid] = {
            "present": [t for t in tokens if t.lower() in pkg.lower()],
            "missing": [t for t in tokens if t.lower() not in pkg.lower()],
            "pkg_chars": len(pkg),
        }

    payload = {
        "status": "ran",
        "label": label,
        "fixture": "eval/ten_workstream/fixture_10x20.json",
        "model": model_name,
        "n_generate": n_gen,
        "elapsed_s": elapsed,
        "vertex_calls": 0,
        "taxonomy": taxonomy,
        "useful": taxonomy.get("USEFUL", 0),
        "abstain_ok": taxonomy.get("ABSTAIN_OK", 0),
        "wrong_ws": taxonomy.get("WRONG_WS", 0),
        "revive_ready_after_slice": revive_ready,
        "rows": rows,
        "note": (
            "Bounded density-extract slice. Not 200-turn live extract. "
            "Not a gate retune. Not natural chat. Local Ollama only."
        ),
        "embed_dim": SETTINGS.EMBED_DIM,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _write_md(payload)
    return payload


def _write_md(payload: dict) -> None:
    if payload.get("status") != "ran":
        RESULTS_MD.write_text(
            f"# Extract density (Ollama)\n\nSkipped: {payload.get('reason')}\n",
            encoding="utf-8",
        )
        return
    tax = payload.get("taxonomy") or {}
    lines = [
        "# Extract density under 10×20 cues (local Ollama)",
        "",
        "**CONTROLLED density-extract slice** — not natural chat, not production accuracy.",
        "No Vertex. No ContextFlow routing. Writer validates. Gate frozen / unused.",
        "",
        f"**Model:** `{payload.get('model')}` · generates: **{payload.get('n_generate')}** · "
        f"elapsed **{payload.get('elapsed_s')}s**",
        "",
        "## Taxonomy",
        "",
        f"```{tax}```",
        "",
        f"- Useful: **{payload.get('useful')}**",
        f"- Abstain OK: **{payload.get('abstain_ok')}**",
        f"- Wrong workstream: **{payload.get('wrong_ws')}**",
        "",
        "## Revive-critical tokens after slice (L2 projection)",
        "",
        "| ws | present | missing |",
        "|---|---|---|",
    ]
    for wid, info in (payload.get("revive_ready_after_slice") or {}).items():
        lines.append(
            f"| {wid} | {', '.join(info.get('present') or []) or '—'} | "
            f"{', '.join(info.get('missing') or []) or '—'} |"
        )
    lines += [
        "",
        "## Per-turn",
        "",
        "| id | turn | class | proposed | need_ok | ws wrong | recon |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in payload.get("rows") or []:
        lines.append(
            f"| {r['id']} | {r['turn']} | {r['class']} | {len(r.get('proposed') or [])} | "
            f"{r.get('need_ok')} | {r.get('wrong_workstream')} | {r.get('reconstruction')} |"
        )
    lines += [
        "",
        "## Honest limits",
        "",
        "- Slice ≠ full 200-turn extract cost/quality.",
        "- Small local models often mis-anchor workstream ids (see prior 1.5b results).",
        "- Cloud Free Trial (legitimate first signup only) is optional for Vertex compare — "
        "not required for this measurement.",
        "",
    ]
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    payload = run()
    print(json.dumps({
        "status": payload.get("status"),
        "model": payload.get("model"),
        "n_generate": payload.get("n_generate"),
        "elapsed_s": payload.get("elapsed_s"),
        "taxonomy": payload.get("taxonomy"),
        "useful": payload.get("useful"),
        "abstain_ok": payload.get("abstain_ok"),
        "wrong_ws": payload.get("wrong_ws"),
        "revive_ready": payload.get("revive_ready_after_slice"),
        "out": str(OUT.relative_to(ROOT)),
        "md": str(RESULTS_MD.relative_to(ROOT)),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
