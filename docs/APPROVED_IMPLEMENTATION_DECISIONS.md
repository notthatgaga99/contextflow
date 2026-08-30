# Approved implementation decisions (2026-08-29)

Recorded before coding. Do not reopen during this slice.

1. Keep `apply_update` as a **legacy** path for registry/MultiWOZ tests. It is **not** the production MemoryWriter.
2. MemoryWriter stays **beside** the engine. Not inside `LLM.generate()`. The engine **reads** canonical memory when building working context.
3. Optional `slot` on `MemoryItem`. Supersession key = `(workstream_id, referent_id, kind, slot)` when `slot` is set. Else require explicit `supersedes_id`. No silent winner.
4. Reuse `ContextPackage` as compiler I/O. No second prompt type.
5. Optional Engine kwargs only: `retriever=`, `memory_store=`, `working_context_builder=`. Existing `Engine(llm, reg, SETTINGS)` call sites unchanged.
6. In-memory optimistic **namespace** versioning only. No Firestore, Cloud Run, Vector Search, Vertex, Graphiti.
