# Production readiness

**Date:** 2026-08-30  
Frozen routing unchanged.

Statuses: **IMPLEMENTED** · **TESTED** · **DEMONSTRATED** · **NOT YET**.

| Layer | IMPLEMENTED | TESTED | DEMONSTRATED | NOT YET |
|---|---|---|---|---|
| Frozen routing | gate / resolver / scorer | pytest + judge demo | controlled PoC + mock product path | organic real chat |
| MemoryItem → Writer → Store | models + writer + store | store / writer / 10-ws tests (**163** pytest) | mock ABCD + 10-ws supersession | durable restart |
| Working-context reconstruction | `WorkingContextBuilder` + compiler | ABCD + 10-ws package checks | mock 10-ws returns; 5-probe Vertex packages | organic reconstruction quality |
| Conversation isolation | `ConversationStore` | pytest + negatives | Mock Cloud Run rev `00001` | cross-instance durability |
| 10-workstream stress (mock) | fixture + harness | `tests/test_ten_workstream.py` | 50 turns / 17 probes; 0 wrong-ACT; 0 contam | natural-human evaluation |
| Cloud Run | Dockerfile + deploy | — | rev `00002-95x` `/health`, `/docs`, `/turn` | authn; private invoker |
| Hosted HTTP Vertex turn | turn pipeline on Cloud Run | — | **1** `/turn` on `00002-95x` | multi-turn hosted ABCD; full 50-turn hosted replay |
| Vertex five-probe slice (local) | `eval/ten_workstream/vertex_slice.py` | — | **15** calls; 5/5 route match; 0 wrong-ACT | full 50-turn Vertex; extraction robustness |
| Durable memory | — | — | — | Firestore / persistence |
| Auth / production SLOs | — | — | — | all |

## Product path

```
LLM          → proposer (extract + soft task id)
MemoryWriter → memory authority (validate + commit)
ContextFlow  → routing authority (ACT/CLARIFY/SWITCH/RETURN)
Compiler     → context authority (ContextPackage)
LLM.generate → answer only (no store mutation)
```

## Evidence (preserved)

### Cloud Run

| Revision | Role |
|---|---|
| `contextflow-00001-zmp` | MockLLM: health, isolation, ABCD HTTP |
| `contextflow-00002-95x` | Vertex: one `/turn` (`diag-turn-1`, SWITCH→A, ~11.6s warm) |

The hosted `/turn` is **separate** from the five-probe local Vertex client slice.

### Ten-workstream mock stress

Controlled adversarial engineering fixture — **not** natural human behavior.

- 10 open workstreams, 50 turns, 17 probes
- 14/17 routing-correct (14/16 ACT + 0/1 CLARIFY-ok); **0** wrong-ACT; **0** critical missing state; **0** contamination
- See `docs/TEN_WORKSTREAM_RESULTS.md`

### Five-probe Vertex slice (local client)

Vertex exercised the production-shaped extract → writer → frozen routing → working-context → answer path at five selected probes, while non-probe fixture history was seeded.

| Field | Value |
|---|---|
| Probes | p08, p06, p11, p15, p13 |
| Calls | **15** |
| Tokens | **5373** in / **6065** out |
| Est. cost | **~$0.002963** (token table, not an invoice) |
| Routing | **5/5** match; **0** wrong-ACT; **0** contam |
| Report | `docs/TEN_WORKSTREAM_VERTEX_RESULTS.md` |

## Cost notes

| Item | Kind | Notes |
|---|---|---|
| Cloud Build / AR / Run | inventory estimate | cents-scale; not scraped invoices |
| Hosted `/turn` | tokens unavailable in logs | amount unknown |
| Ten-ws Vertex slice | token-table estimate | ~$0.002963 |

## Explicitly NOT YET

- Robust LLM extraction on real/consented transcripts
- Durable memory across restart / multi-instance
- Authentication on the public demo URL
- Organic evaluation; production SLOs
- Full 50-turn hosted Vertex evaluation
