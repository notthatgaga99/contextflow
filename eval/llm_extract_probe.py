"""Tiny LLM extractor probe. Isolated from routing. No Vertex. No sweep.

Uses existing ABCD fixture turns only. Ollama generate. Pytest does not call this live.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.memory.extractor import ExtractRequest, LlmMemoryExtractor, apply_extraction
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from eval.answer_consume import ollama_available
from eval.memory_lifecycle.fixture import NAVY_MSG
from eval.memory_lifecycle.run import make_registry

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "out" / "llm_extract_probe.json"

TURNS = [
    {"id": "fact", "turn": 1, "message": "JWT still returns 401 after refresh.",
     "expect_kind": "fact", "expect_ws": "A"},
    {"id": "decision", "turn": 3, "message": "I need a black dress for a corporate event.",
     "expect_kind": "decision", "expect_ws": "B"},
    {"id": "constraint", "turn": 4, "message": "The event is formal and in the evening.",
     "expect_kind": "constraint", "expect_ws": "B"},
    {"id": "correction", "turn": 9, "message": NAVY_MSG,
     "expect_kind": "decision", "expect_ws": "B"},
    {"id": "uncertain", "turn": 11, "message": "maybe the navy one?",
     "expect_kind": None, "expect_ws": None},
]


def _brief(items):
    return [{"id": i.id, "kind": i.kind, "text": i.text, "status": i.status,
             "workstream_id": i.workstream_id, "referent_id": i.referent_id,
             "slot": i.slot, "source_turn": i.source_turn, "provenance": i.provenance}
            for i in items]


def run() -> dict:
    if not ollama_available():
        payload = {"status": "skipped", "reason": "ollama_unreachable"}
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    from app.llm.ollama import OllamaLLM
    llm = OllamaLLM()
    reg = make_registry()
    store = InMemoryMemoryStore(conversation_id="llm-extract")
    writer = MemoryWriter(store, reg)
    ext = LlmMemoryExtractor(llm)
    rows = []
    retry_ok = None
    n_generate = 0
    for spec in TURNS:
        req = ExtractRequest(
            message=spec["message"],
            source_turn=spec["turn"],
            conversation_id="llm-extract",
            open_workstreams=reg.open_tasks(),
            asserted_items=store.asserted(),
        )
        extracted = ext.extract(req)
        n_generate += 1
        before = len(store.all())
        committed = apply_extraction(ext, writer, req)
        n_generate += 1
        if spec["id"] == "decision":
            n = len(store.all())
            again = apply_extraction(ext, writer, req)
            n_generate += 1
            retry_ok = again.ok and len(store.all()) == n
        kinds = [p.kind for p in extracted.patches]
        ws = [p.workstream_id for p in extracted.patches]
        ok_kind = spec["expect_kind"] is None or spec["expect_kind"] in kinds
        ok_ws = spec["expect_ws"] is None or spec["expect_ws"] in ws
        if spec["id"] == "uncertain":
            ok_kind = extracted.uncertain or not extracted.patches
        rows.append({
            "id": spec["id"],
            "message": spec["message"],
            "uncertain": extracted.uncertain,
            "notes": extracted.notes,
            "proposed": [
                {"kind": p.kind, "text": p.text, "workstream_id": p.workstream_id,
                 "referent_id": p.referent_id, "slot": p.slot}
                for p in extracted.patches
            ],
            "commit_ok": committed.ok,
            "commit_errors": committed.errors,
            "kind_ok": ok_kind,
            "workstream_ok": ok_ws,
            "store_grew": len(store.all()) > before,
        })
    black = [i for i in store.historical("B") if "black" in i.text.lower()]
    navy = [i for i in store.asserted("B") if "navy" in i.text.lower()]
    payload = {
        "status": "ran",
        "provider": "ollama",
        "model": llm.model,
        "n_generate": n_generate,
        "isolation": "extract_then_writer_only_no_handle_turn",
        "rows": rows,
        "idempotent_retry": retry_ok,
        "store_snapshot": _brief(store.all()),
        "supersession": {
            "black_historical": _brief(black),
            "navy_asserted": _brief(navy),
        },
        "provenance_present": all(bool(i.provenance) for i in store.all()) if store.all() else True,
        "note": "Exploratory. Failures are extraction-layer, not routing.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def main() -> int:
    payload = run()
    print(json.dumps({
        "status": payload.get("status"),
        "out": str(OUT),
        "kind_ok": [r.get("kind_ok") for r in payload.get("rows") or []],
        "idempotent": payload.get("idempotent_retry"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
