# Memory extractor

**Boundary:** conversation → **MemoryExtractor** → `MemoryWriter.propose` → `validate` → `commit` → `MemoryStore`.

Memory extraction converts conversational observations into structured **candidate** memory. Candidates are validated by a separate memory authority before becoming persistent working state. The extractor **never** writes the store, is **not** inside `Engine.handle_turn`, and is **not** inside `LLM.generate()`. HTTP `/turn` uses `app/turn_pipeline.py` (extract then route). The extractor does **not** choose ACT/CLARIFY.

## Implementations

- Protocol: `MemoryExtractor.extract(ExtractRequest) → ExtractResult` (`app/memory/extractor.py`)
- Commit path: `apply_extraction(...)` only
- `MockMemoryExtractor` — deterministic tests and scripted eval seeding
- `LlmMemoryExtractor` — fail-closed JSON extractor (`CF_LLM_EXTRACT=1`). Drops unknown/unanchored ids; strips routing fields; normalizes accidental `[A]` bracket copies from card formatting.

## Provenance

Patches carry `source_turn`, `workstream_id` / `referent_id` when known, and optional `conversation_id`. Prefer omitting workstream/referent over inventing them. `uncertain=True` skips commit; the writer also rejects `uncertain` patches. See `docs/MEMORY_SEMANTICS.md`.

## Evidence status

| Claim | Status |
|---|---|
| Extractor → writer → store contract | IMPLEMENTED / TESTED |
| Referent fail-closed (omit invented loops before writer) | IMPLEMENTED / TESTED |
| Underspecified utterances → no asserted memory | IMPLEMENTED / TESTED |
| Controlled synthetic extraction via local Ollama (`qwen2.5:1.5b`) | DEMONSTRATED — see `docs/TEN_WORKSTREAM_EXTRACT_OLLAMA.md` |
| Tiny Vertex extractor comparison (`gemini-2.5-flash-lite`, 11 turns) | DEMONSTRATED — see `docs/TEN_WORKSTREAM_EXTRACT_VERTEX.md` |
| Phase-5 extractor harden + Vertex re-check | DEMONSTRATED when `extract_vertex` re-run completes |
| Robust extraction on organic/consented chat | NOT YET |

CONTROLLED SYNTHETIC / LOCAL OLLAMA results are **not** natural human-chat evidence.

## Limitations

1. Extraction runs in the turn pipeline beside the engine; `handle_turn` only *reads* asserted items.
2. The writer cannot detect a plausible-but-wrong workstream id. That is extractor error, not a routing defect.
3. Ambiguous sibling loops: omit `referent_id` rather than guess.
4. Unkeyed decisions still need `slot` or `supersedes_id`.
5. Omitted constraints stay omitted; sufficiency is judged on the working set after commit.
6. `LlmMemoryExtractor` drops unknown workstream ids and unanchored rows; empty/invalid JSON → no patches.
7. Small local models often fail anchoring, supersession expression, and ambiguity fail-closed; do not weaken the writer to accommodate them.
8. `MockLLM.generate` only echoes early prompt tokens and cannot prove answer quality from the full package.
