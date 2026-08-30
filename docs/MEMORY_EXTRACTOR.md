# Memory extractor (v1)

**Date:** 2026-08-29  
**Boundary:** conversation → **MemoryExtractor** → `MemoryWriter.propose` → `validate` → `commit` → `MemoryStore`. The extractor **never** writes the store. It is **not** inside `Engine.handle_turn` and **not** inside `LLM.generate()`. HTTP `/turn` uses `app/turn_pipeline.py` (extract then route). The extractor still does not choose ACT/CLARIFY.

## What this slice is

- Protocol: `MemoryExtractor.extract(ExtractRequest) → ExtractResult` (`app/memory/extractor.py`)
- Commit path: `apply_extraction(...)` only
- `MockMemoryExtractor` for deterministic tests
- `LlmMemoryExtractor` fail-closed JSON stub for a later plug-in (**do not call Vertex from pytest**)

## Provenance

Patches/items carry `source_turn`, `workstream_id` / `referent_id` when known, and optional `conversation_id`. Uncertainty: omit workstream/referent rather than invent; extractor `uncertain=True` skips commit. Writer rejects `uncertain` patches at validate. See `docs/MEMORY_SEMANTICS.md`.

## Limitations (do not paper over in the router)

1. **Not on the hot path.** `handle_turn` still only *reads* asserted items. Extraction is an explicit call beside the engine. An LLM-backed extractor will not run until wired later.
2. **Writer cannot detect a plausible-but-wrong workstream.** If the extractor names a real id (e.g. A instead of B), commit succeeds. Reconstruction of B is then insufficient. That is extractor error, not a gate-weight problem.
3. **Sibling loops.** If two loops on the same workstream are plausible, the mock omits `referent_id`. The frozen resolver is unchanged.
4. **Unkeyed decisions** still require `slot` or `supersedes_id`. The extractor must propose an explicit supersession; the writer will not pick a silent winner.
5. **Omitted constraints** stay omitted. Sufficiency is evaluated on the working set after commit; we do not invent evening/formal to make routing look good.
6. **`LlmMemoryExtractor`** drops unknown workstream ids and unanchored rows. Empty/invalid JSON → no patches. It is unused by `Engine`.
7. **`MockLLM.generate`** only echoes the first tokens of the compiled prompt. Working-set fields (`DECISIONS` / `CONSTRAINTS`) sit later in `ContextCompiler.render`. A real answer model could continue from the package; the mock cannot prove answer quality.
