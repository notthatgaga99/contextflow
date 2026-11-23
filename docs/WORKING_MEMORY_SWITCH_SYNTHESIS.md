# Working-memory switch — literature revisit → enablement

**Status:** Synthesis for product direction (learning). Revisits `docs/MEMORY_ARCHITECTURE_RESEARCH.md` (2026-08-29 audit) against the current goal.  
**Does not unfreeze** gate / referent / scorer / config / MemoryWriter contracts.

---

## 0. Are we clear?

Yes. The product is:

> A **working-memory manager that switches**: many turns on one concept (e.g. 50), then jump to another; the manager **dynamically loads only the compact notation** for the active avenue into the LLM — it does **not** hog the context with the whole history or all threads.

Switching was always the wedge. Market memory systems already do persistence/recall well. You **compose** their concepts under your binder so **one resolved thread’s working memory** is what the model sees.

Precise name (from literature audit): **RB-WSR** — referent-bound working-set reconstruction.

---

## 1. Three questions (do not collapse) — still the spine

From the original literature review:

| Layer | Question | Market default | ContextFlow |
|---|---|---|---|
| Persistent memory | What was established over time? | Mem0 facts, Zep graph, Letta archival | Store + workstreams + asserted/superseded items |
| Retrieval | What *might* be relevant? | Vector / BM25 / graph top-k | Open-thread index (+ optional cold search later) |
| **Working context** | What is the user on **now**? | Usually “stuff top-k” | **Bind thread → compact L1 only** |

Your ask lives almost entirely in the third row. Persistence/retrieval are support.

---

## 2. Literature concepts to **bring back** (adopt into existing setup)

| Source | Useful concept | How it maps into CF today / next |
|---|---|---|
| **MemGPT / Letta** | Core vs recall vs archival tiers | L1 working set / L2 hop CURRENT / L5–L6 store+catalog — **not** agent self-edit as authority |
| **Zep / Graphiti** | Invalidate don’t delete; temporal validity | Supersession + `valid_to` / HISTORY (already) |
| **Mem0** | Namespace isolation; extract-on-write; hybrid recall | `conversation_id`; extractor→writer; cold search **after** bind only |
| **MemoryBank** | Optional summaries as memory, not as router | Rollup blurb / hop summary items — never replace gate |
| **LangMem / LangGraph** | Background extract vs hot path; namespaced store | Extract separate from generate; ConversationStore |
| **DST / slots** | Current belief state for continuation | Asserted decisions/constraints per workstream+slot |
| **LongMemEval / LoCoMo** | Abstain when unsure; temporal consistency | Abstain extract; CLARIFY ≠ abstain QA metric |
| **Cursor / IDE harnesses** | Dynamic pull; don’t static-dump | Load L1 on demand after switch; history as recoverable cold |

### Explicitly **avoid** (same audit — still valid)

- Mem0/search **as the only** context to the answer model  
- Letta **unvalidated** self-edit of canonical memory  
- Graphiti/Neo4j as MVP  
- Ebbinghaus decay as routing  
- Full history / NIAH as the eval of RB-WSR  

---

## 3. Target loop (50 turns on A, switch to B, …)

```text
for each prompt:
  1. BIND     plan_turn → which workstream/referent | CLARIFY | NEW
  2. WRITE    extract → patches → Writer (or abstain)     # grows L2/L5, not prompt
  3. LOAD     if ACT: read L2 for THAT id → project → L1 compact notation
  4. EXPOSE   generate(L1 + user message) only
  5. (opt)    rollup/catalog touch for H2
```

**Efficiency claim you can defend:**

- 50 turns on concept A → many writes to A’s memory; prompt each turn still ≈ **compact L1(A)**  
- Switch to B → unload A’s L1, load **compact L1(B)**  
- A’s full history stays in L2/L3/L5; not in the LLM context  
- Ambiguous switch → CLARIFY (fail closed), not a mashed multi-thread prompt  

That is “entire working memory handling **and** switch.”

---

## 4. Compact notation (what the LLM is allowed to see)

**L1 package (answer contract)** — keep small on purpose:

| Field | Role |
|---|---|
| Workstream title / goal | Which avenue |
| Selected loop / referent | Which sub-thread |
| Asserted decisions | CURRENT choices |
| Constraints | Hard bounds |
| Facts / entities | Needed continuation state |
| Recent changes (capped) | Local delta |
| USER message | Always |

**Not in L1:** other hops’ facts, superseded HISTORY, full transcript, catalog of last-N chats, cold top-k from other threads.

**L4 (open index)** may still list short **card headers** for the binder (grows with hop count). That is routing context, not answer hogging — keep headers thin (goal + cues), not full L2 dumps.

---

## 5. Enablement checklist (compose market + CF)

| Step | Action | Status |
|---|---|---|
| 1 | Keep binder frozen (switch / CLARIFY) | Have |
| 2 | Typed MemoryItems + Writer supersession | Have |
| 3 | RB-WSR + referent compact + caps | Have (+ caps) |
| 4 | Hierarchy L0–L6 documented | Have (research docs) |
| 5 | Catalog / opt-in import (archival tier) | **Done** — rollup + archive + import-rollup + `/catalog/match` (suggest only) |
| 6 | `MemoryPort` + **real** cold search | **Done** — lexical+hash rank over store (`cold_search.py`); bound-scoped enrich into L1 |
| 7 | L1 compact notation | **Done** — `CompactNotation` + `expose_bound_thread` + `GET …/compact-notation` |
| 7a | Memory planes (STM / LTM / procedural / relevant) | **Done** — `MemoryManager` + `docs/MEMORY_MANAGEMENT.md` (RB-WSR; not a vendor clone) |
| 7b | File-backed last-N catalog | **Done** — `.data/catalog.json` via `CF_CATALOG_PATH` / `CF_CATALOG_PERSIST` |
| 7c | Firestore last-N catalog | **Done** — `FirestoreConversationCatalog` via `CF_CATALOG_BACKEND=firestore` |
| 8 | Density stress: long run on one hop then revive others | **Done** — R3 + match suggest; `eval.cloud_poc.density_catalog_revive_cloud` |
| 9 | Bound cold enrich after bind | **Done** — superseded-slot filter + provenance ids |

---

## 6. One-sentence product line

> ContextFlow is a **working-memory switch**: it maintains durable per-thread memory (using standard memory lifecycle ideas) and, on each prompt, **binds one avenue** and exposes only that avenue’s **compact working notation** to the LLM.

---

## 7. Related docs

| Doc | Role |
|---|---|
| `docs/MEMORY_ARCHITECTURE_RESEARCH.md` | Original literature audit |
| `docs/RESEARCH_10x20_REVIVE.md` | Density + hierarchy + MemoryPort thesis |
| `docs/MEMORY_MANAGEMENT.md` | Our planes (RB-WSR); learn-from field, not clone |
| `docs/CONTEXT_MANAGEMENT_AND_HORIZON.md` | Industry spine + H2 |
| `docs/MEMORY_SEMANTICS.md` | Writer / asserted rules |
| `docs/ARCHITECTURE.md` | Authority split |
