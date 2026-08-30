# Minimum Google Cloud production path

**Status:** design for review. **Do not deploy** until this is accepted.  
**Do not spend Vertex credits** for the consented case study. Local Ollama answers the same comparison.

Frozen engine math stays local. Cloud is only for **hosting** and an optional **hosted LLM** behind the existing `LLM` protocol.

---

## Smallest credible topology

```
Client
  → HTTPS
  → Cloud Run (FastAPI `app.api.main`)
       → Engine (frozen)
       → MemoryProvider (in-memory first)
       → LLM protocol: Mock | Ollama (not in Cloud Run) | Vertex Gemini
  → Cloud Logging (decision traces)
```

Later, only if required:

```
  → Firestore (or equivalent) implementing the existing registry Protocol
  → Secret Manager for Vertex ADC / keys
```

Not in the MVP: Vector Search, BigQuery, Pub/Sub, multi-agent mesh.

---

## Component table

| Component | Why | What state | Minimum viable | Fails without it | Cost | Demo stub? |
|---|---|---|---|---|---|---|
| **FastAPI `/turn`** | Product surface | None (stateless handler) | Already exists | No HTTP product | $0 local | **IMPLEMENTED** |
| **Engine + gate** | Resolution + ACT/CLARIFY | None (pure + registry I/O) | Frozen PoC | No product | $0 | **IMPLEMENTED** |
| **In-memory registry** | Task cards, clocks | Per-process dict | Single Cloud Run instance / local | Restart loses cards | $0 | **IMPLEMENTED** |
| **ConversationStore** | Isolation | Map `conversation_id` → Engine | Process memory | Users share memory | $0 | **IMPLEMENTED** (not durable) |
| **Context compiler** | Answer package | None | Existing split mode | Full transcript only | $0 | **IMPLEMENTED** |
| **Cloud Run** | Host the same API | Container only | 1 service, min instances 0, MockLLM | No public URL | Pennies–dollars/mo idle | **DESIGNED**, not deployed |
| **Artifact Registry** | Store image | Image bytes | Required with Cloud Run | Cannot deploy | Storage cents | **DESIGNED** |
| **Cloud Logging** | Debug ACT vs CLARIFY | Decision JSON, **redacted** text | Structured logs | Cannot support live demo failures | Included in Run | **DESIGNED** |
| **Secret Manager** | Keep Vertex out of image | Secrets | Only if `CF_USE_VERTEX=1` | Keys in git/env on disk | Cents | Stub: `.env` local |
| **Vertex AI (Gemini)** | Hosted `propose`/`generate` | None in CF | Existing `GeminiClient` | Local Ollama/Mock still work | See `docs/COST_ESTIMATE.md` | **DEMONSTRATED** propose-only on frozen grid; generate **not** required for Sep 7 case study |
| **Firestore** | Durable cards + clocks | Tasks, mention clocks, `last_selected_referent`, conversation id | `FirestoreRegistry` is a **NotImplemented** seam | Multi-instance / crash recovery | Storage + ops | **NOT YET** — keep stub |
| **Vector DB** | Semantic retrieve | Embeddings | **Not needed** until lexical/hash candidate miss is measured on real traffic | Gold card never scored | High relative to value | **Do not add** |
| **Memory extractor** | Fill `TaskAnchor` from history | Decisions, constraints, loops | Human sheet in the case study | Native NEW = raw utterance | LLM tokens later | **NOT YET** (`apply_update` no-op) |

---

## What would fail without each “yes”

- Without **Cloud Run**: still a local library. Fine for Sep 7 evidence.
- Without **Firestore**: one demo user, one instance, state dies on deploy. Acceptable for a judged demo.
- Without **Vertex**: still Mock + Ollama. Hosted-provider evidence already exists (Gemini propose grid).
- Without **extractor**: CF can only route over **whatever cards you put in**. The consented experiment uses a human snapshot for that reason.

**Restart:** the state that must survive a process kill is per-`conversation_id` task cards, clocks, and last selected referent. **That** is the Firestore trigger — not a vector DB. Isolation without durability is already in `ConversationStore`.

---

## Recommended path to 7 September

1. Local consented case study (Ollama). **$0 cloud.**
2. Optional: one Cloud Run **MockLLM** URL if a hosted HTTP demo is required — **no Vertex**.
3. Vertex **only** if a reviewer must see **hosted generate** on the same three conditions. Cost that experiment **before** running (next section in `docs/COST_ESTIMATE.md`).

Do not deploy Firestore “because production.”
