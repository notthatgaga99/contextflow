# Memory layer implementation report (2026-08-29)

No commit/push. Frozen routing untouched (`gate.py` / scorer weights / TAU–HYST).

## Files

**New:** `app/models/memory.py`, `app/memory/store.py`, `app/memory/writer.py`, `app/memory/retriever.py`, `app/context/working_set.py`, tests `test_memory_store.py`, `test_working_set.py`, `test_abcd_return_fixture.py`, `test_memory_safety.py`, `docs/APPROVED_IMPLEMENTATION_DECISIONS.md`

**Adapted:** `app/engine.py` (optional `retriever`, `memory_store`, `working_context_builder`; `_make_package` reads store), `app/context/compiler.py` (optional field overrides), `app/models/context.py`, `app/models/task.py` (`item_ids`), `app/memory/sessions.py`

**Not changed:** `app/router/gate.py`, `app/retrieval/scorer.py`, `app/router/referent.py`

## Tests

`pytest -q`: **110 passed**. Demo `python -m eval.demo`: unchanged judge story.

## Remaining NOT YET

LLM extraction, durable MemoryStore, Cloud Run, Vertex, vectors, consented real conversation, `apply_update` still legacy.
