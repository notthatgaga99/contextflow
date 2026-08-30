# Memory extractor

**Boundary:** conversation → **MemoryExtractor** → `MemoryWriter.propose` → `validate` → `commit` → `MemoryStore`.

The extractor **never** writes the store, is **not** inside `Engine.handle_turn`, and is **not** inside `LLM.generate()`. HTTP `/turn` uses `app/turn_pipeline.py` (extract then route). The extractor does **not** choose ACT/CLARIFY.

## Implementations

- Protocol: `MemoryExtractor.extract(ExtractRequest) → ExtractResult` (`app/memory/extractor.py`)
- Commit path: `apply_extraction(...)` only
- `MockMemoryExtractor` — deterministic tests and scripted eval seeding
- `LlmMemoryExtractor` — fail-closed JSON extractor (`CF_LLM_EXTRACT=1`). Exercised on the five-probe Vertex path. **Not** demonstrated as robust on real/consented conversations. Do not call Vertex from pytest.

## Provenance

Patches carry `source_turn`, `workstream_id` / `referent_id` when known, and optional `conversation_id`. Prefer omitting workstream/referent over inventing them. `uncertain=True` skips commit; the writer also rejects `uncertain` patches. See `docs/MEMORY_SEMANTICS.md`.

## Limitations

1. Extraction runs in the turn pipeline beside the engine; `handle_turn` only *reads* asserted items.
2. The writer cannot detect a plausible-but-wrong workstream id. That is extractor error, not a routing defect.
3. Ambiguous sibling loops: omit `referent_id` rather than guess.
4. Unkeyed decisions still need `slot` or `supersedes_id`.
5. Omitted constraints stay omitted; sufficiency is judged on the working set after commit.
6. `LlmMemoryExtractor` drops unknown workstream ids and unanchored rows; empty/invalid JSON → no patches.
7. `MockLLM.generate` only echoes early prompt tokens and cannot prove answer quality from the full package.
