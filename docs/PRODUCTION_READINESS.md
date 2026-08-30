# Production readiness

**Date:** 2026-08-30  
**Engineering frozen.** Frozen routing unchanged. **Not committed yet.**

Statuses: **IMPLEMENTED** · **TESTED** · **DEMONSTRATED** · **NOT YET**.

| Layer | IMPLEMENTED | TESTED | DEMONSTRATED | NOT YET |
|---|---|---|---|---|
| Frozen routing PoC | gate/resolver/scorer | 135+ pytest (pre-stabilization) + invariants | controlled PoC + mock product path | organic real chat |
| MemoryItem → Writer → Store | models + writer + store | store/writer/invariant/negative tests (**153** pytest) | mock ABCD lifecycle + supersession | durable restart |
| Working-context reconstruction | `WorkingContextBuilder` + compiler | invariant tests on ABCD return-B | mock path + one hosted turn metadata | hosted return/supersession on Vertex |
| Conversation isolation | `ConversationStore` | pytest + negative tests | Mock rev `00001` live | hosted Vertex path; cross-instance |
| Cloud Run live | Dockerfile + deploy | — | rev `00002-95x` serves `/health`, `/docs`, `/turn` | authn; private invoker |
| End-to-end hosted HTTP | turn pipeline on Cloud Run | — | **1** Vertex `/turn` (`diag-1`, SWITCH→A) | multi-turn hosted ABCD |
| Vertex extraction (hosted) | `LlmMemoryExtractor` | unit fail-closed tests | **1** hosted turn `extract_ok=true` | quality/robustness |
| Vertex answer (hosted) | `GeminiClient` | — | **1** hosted non-mock answer (~9.5 KB) | quality benchmark |
| Local Vertex client smoke | `eval/vertex_smoke.py` | — | 9 calls, 3 probes, ~$0.001896 est. | — |
| Memory semantics doc | `docs/MEMORY_SEMANTICS.md` | negative + invariant tests | — | production enforcement at scale |
| Durable memory | — | — | — | Firestore / persistence |
| Auth / production reliability | — | — | — | all |

## Evidence preserved (do not re-run)

### Mock Cloud Run (`contextflow-00001-zmp`)

- Health, isolation, ABCD HTTP, structured `turn_decision` logs.

### Hosted Vertex (`contextflow-00002-95x`)

| Field | Value |
|---|---|
| Turn time (UTC) | `2026-08-30T04:23:15Z` |
| Correlation | `diag-turn-1` |
| Trace | `projects/contextflow-506414/traces/4ded0ec6fa34e53d2b5f7f851e640ddb` |
| Latency | **11.63 s** (warm) |
| Models | `gemini-2.5-flash-lite` via Vertex `us-central1` |
| Gate | SWITCH → A / A.loop1 |
| Mock path | **off** (`CF_SMOKE_FIXTURE` unset) |

### Local stabilization (this phase)

- **153** pytest pass (invariant + negative memory tests added).
- `docs/MEMORY_SEMANTICS.md`: ASSERT, SUPERSEDE, RETRACT, UNCERTAIN, ABANDON, CORRECT.
- Writer: uncertain patches rejected; abandon closes workstream; correction supersedes decision on slot.

## Architecture boundary (locked)

```
LLM          → proposer (extract + soft task id)
MemoryWriter → memory authority (validate + commit)
ContextFlow  → routing authority (ACT/CLARIFY/SWITCH/RETURN)
Compiler     → context authority (ContextPackage)
LLM.generate → answer only (no store mutation)
```

Retriever → candidates. Store → accumulated state. WorkingContextBuilder → projection for selected task only.

## Billing (last audited 2026-08-30)

| Resource | Actual invoice via CLI | Notes |
|---|---|---|
| Cloud Build / AR / Run | **Not scraped** | cents-scale estimate |
| Vertex hosted | **Not scraped** | 1 turn; no token metadata in logs |
| Vertex local smoke | **~$0.001896** | token counts in `eval/out/vertex_smoke.json` (gitignored) |

## Explicitly NOT YET

- Robust LLM extraction on real/consented transcripts
- Durable memory across restart / multi-instance
- Authentication; unauthenticated public URL remains a demo boundary
- Organic evaluation; production SLOs
- Firestore, Vector Search, embeddings batch, 135-call grid

## Remaining product question

**Memory quality and persistence semantics** — not routing. Next work is durable store + extraction quality on consented traffic, not gate retuning.
