# Architecture

ContextFlow separates **memory proposal**, **memory authority**, **routing**, and **answer generation**.

```
Conversation
    → MemoryExtractor          # proposes MemoryPatch only
    → MemoryWriter             # propose → validate → commit
    → MemoryStore              # namespaced by conversation_id
    → ContextFlow resolver/gate
    → WorkingContextBuilder
    → ContextPackage
    → Answer model
```

| Role | Authority |
|---|---|
| LLM / extractor | Propose memory patches and a soft task id |
| `MemoryWriter` | Validate and commit memory (only mutation path) |
| ContextFlow | Decide ACT / CLARIFY / SWITCH / RETURN and which workstream is active |
| `WorkingContextBuilder` | Reconstruct minimum useful asserted state for the selected task |
| `LLM.generate` | Answer from the package — must not write memory |

Extractor answers: what this turn established or changed.  
ContextFlow answers: what should matter right now.

`Engine.handle_turn` does not extract. `app/turn_pipeline.py` sequences extract-then-route.

Frozen routing (`gate.py`, `scorer.py`, `referent.py`, TAU / DELTA / HYST / weights) is not retuned from evaluation results.
