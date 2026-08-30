# Locked architecture (2026-08-29)

Do not retune gate weights, scorer weights, or referent resolver to make new tests pass.

```
Conversation
    → MemoryExtractor          # proposes only
    → MemoryPatch
    → MemoryWriter             # propose → validate → commit
    → MemoryStore              # namespaced by conversation_id
    → ContextFlow resolver/gate
    → WorkingContextBuilder
    → ContextPackage
    → Answer model
```

The LLM may propose memory and a soft task id. It must not mutate `MemoryStore` and must not be the final ACT/CLARIFY decision.

Extractor answers: what this turn established or changed.  
ContextFlow answers: what should matter right now.

`Engine.handle_turn` does not extract. `app/turn_pipeline.py` sequences extract-then-route.
