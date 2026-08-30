# Final validation (LLM extraction + Cloud Run smoke)

**Date:** 2026-08-29  
**Routing:** unchanged.

## Local LLM extractor (Ollama qwen2.5:1.5b, 5 fixture turns)

Isolated path: extract → writer → store. **No `handle_turn`.**

| Turn | Intent | Result | Layer |
|---|---|---|---|
| JWT 401 | fact | Model used title `authentication` as id; dropped / writer rejected | **extraction** |
| black dress | decision | Proposed B but invalid referent `corporate outfit`; writer rejected | **extraction** |
| formal evening | constraint | Unanchored; no write | **extraction** (uncertainty preserved) |
| navy not black | correction | Invalid referent `C`; writer rejected | **extraction** |
| maybe the navy one? | uncertain | Proposed junk; no durable growth | **extraction** |

Store ended **empty**. That is fail-closed persistence, not a routing bug.

Idempotent retry: **not demonstrated** on this run (nothing committed). Writer retry remains **TESTED** via MockMemoryExtractor.

## Cloud Run

`gcloud run deploy` **failed**: default Compute SA `810061766045-compute@developer.gserviceaccount.com` missing Cloud Build / GCS source-bucket IAM. **NOT YET demonstrated.**

Vertex HTTP smoke was **not executed** (no URL; estimate only).

## Isolation

HTTP `/conversations/{id}/memory` **TESTED** locally. Two conversation IDs cannot share a store. Not demonstrated on Cloud Run.
