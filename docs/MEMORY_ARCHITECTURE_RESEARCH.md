# Memory architecture research (audit only)

**Date:** 2026-08-29  
**Status:** research / design. **No implementation. No routing changes. No Vertex. No downloads. No commit/push.**

**Legend:** **Practice** = established industry/research. **Benchmark** = what a dataset actually scores. **PoC** = existing ContextFlow. **Inference** = this audit’s recommendation.

---

## 0. Three questions (do not collapse)

| Layer | Question | Typical industry answer | ContextFlow PoC |
|---|---|---|---|
| **Persistent memory** | What has this conversation established over time? | Extracted facts / summaries / graphs / DST slots | Task cards + string lists; `apply_update` **no-op** |
| **Retrieval** | Which memories *might* be relevant? | Vector, BM25, graph walk, recency, full history | Hash cosine + lexical cues + recency in the **scorer**, not a store |
| **Working context** | What is the user operating on **now**, and what state must the answer model see? | Usually “top-k retrieved chunks” | Referent resolution + ACT/CLARIFY + **selected** task/loop compile |

**Inference:** Retrieval relevance ≠ conversational **referent resolution**. Similarity can surface every dress fact and still bind the wrong workstream, or bind DRESS and omit the navy decision. That gap is the product.

**Precise name:** **Referent-bound working-set reconstruction (RB-WSR).**

**Definition:** Given (a) a durable memory namespace for one `conversation_id` and (b) candidate memories that a retriever *may* have recalled, RB-WSR is the control step that (1) identifies the **current workstream and referent**, (2) **gates** ACT vs CLARIFY, and (3) emits a **working set** — the subset of memory items required to continue *that* work, plus explicit exclusions of competing workstreams — rather than a ranked document list.

This is **not** a claim that we invented long-term memory.

---

## 1. What memory needs to represent

### 1.1 Primitive evaluation

| Primitive | Needed for heterogeneous returns? | PoC today | Recommendation |
|---|---|---|---|
| Workstream / task | **Yes** if unfinished intention | `Task` | **KEEP** as control object |
| Unresolved objective | **Yes** | `anchor.goal` | **KEEP** |
| Loop / sub-objective | **Yes** when one workstream has siblings (`401` vs expired token) | `open_loops[]` + `{id}.loopk` | **KEEP** |
| Fact | **Yes** for continuation | `entities` mixed with facts | **ADAPT**: typed `MemoryItem` `kind=fact` |
| Entity | Useful | mixed into `entities` | **ADAPT**: item `kind=entity` |
| Decision | **Yes** (navy; “don’t change public API”) | `decisions[]` often empty in live path | **KEEP** field; **NEW** writer that fills it |
| Constraint | **Yes** (parking; formal venue) | `constraints[]` | **KEEP** + writer |
| Preference | Sometimes (not always a decision) | none | **ADAPT** as `kind=preference` or fold into decision |
| Event | Optional (trip dates) | none | **DEFER** as separate type unless a real transcript needs “occurred at T” |
| Question / open item | Same as loop | open_loops | **KEEP** loops as the open-item type |
| Correction | **Yes** as *utterance kind* and as *memory supersession* | resolver `correction`; no item history | **NEW** on write path (`supersedes`) |
| Relationship | Nice for graphs | none | **DEFER** (no Graphiti until items+links fail) |
| Temporal validity | **Yes** for “we decided navy” vs later “actually black” | none | **NEW** `valid_from` / `valid_to` / `superseded_by` on items |
| Provenance | **Yes** | `source_event_ids` empty | **NEW** `source_turn` required on writes |
| Confidence | Diagnostic only | LLM conf ≠ P(correct) | **KEEP** policy: never gate on LLM conf; store as diagnostic on proposals |
| Status | **Yes** | task `active\|paused\|resolved` | **KEEP** on workstream; **NEW** `asserted\|superseded\|retracted` on items |
| Superseded / conflicting | **Yes** | none | **NEW** append-only + supersession, not silent overwrite |

**Do not** treat every topic as a workstream. Chitchat, one-shot trivia, and completed asks are **non-workstreams** (or resolved with no open loop). **Inference.**

### 1.2 Normalized conceptual model

**Practice:** DST uses slots; Mem0 uses accumulating fact strings; Graphiti uses temporal triples; MemGPT uses core vs archival blobs.

**PoC:** `Task → TaskAnchor` (goal, loops, decisions, constraints, entities) plus clocks.

**Inference — evolve conceptually, not to a graph DB:**

```
ConversationNamespace   (conversation_id)
  ├── Workstreams[]           # CONTROL PLANE (what user is doing)
  │     id, title, status
  │     objective (goal)
  │     open_referents[]      # loops
  │     clocks (mention, last_active, loop_mention, last_selected_referent)
  │     retrieval_cues
  │     item_ids[]            # references into MemoryItems
  │
  └── MemoryItems[]           # DATA PLANE (what has been established)
        id, kind ∈ {fact, decision, constraint, entity, preference, event, correction}
        text
        workstream_id | null  # null = global persona / not a task
        referent_id | null
        status ∈ {asserted, superseded, retracted}
        valid_from_turn, valid_to_turn | null
        superseded_by | null
        source_turn, proposer ∈ {user, extractor, system}
        proposal_confidence    # diagnostic
        version
```

Workstreams **point to** items. Items are **not** only nested strings on the card. The compiler **selects** items for the working set after the gate.

This is **ADAPT** of `TaskAnchor` lists into addressable items. It is **not** a requirement to deploy Neo4j.

---

## 2. Memory writing

### 2.1 Desired lifecycle

```
turn
  → MemoryWriter.propose(history_delta)     # LLM or rules; SOFT
  → validate (schema, namespace, no unknown ids)
  → conflict / supersession policy
  → MemoryStore.commit(versioned items + workstream patches)
  → clocks updated only from USER mention / gate ACT   # PoC invariant
```

The answer model **must not** be the writer. **PoC already:** `generate()` does not write clocks. **KEEP.** Extend the same rule to MemoryItems: extractor is a **separate** call (or a queued job), proposals are not auto-canonical.

### 2.2 How modern systems handle writes (practice)

| System | Updates | Contradictions | Temporal | Delete / forget | Provenance | Stale |
|---|---|---|---|---|---|---|
| **Mem0 v3** | ADD-only accumulation; explicit `update` API | Dedup; older path had update/delete | Time-aware retrieval claimed | Accumulate rather than overwrite in v3 extract | Metadata / user_id | Rank / decay in product narrative |
| **Graphiti / Zep** | Incremental episodes | Invalidate rather than erase | Bi-temporal (event vs ingest) | Invalidation | Source episodes | Validity windows |
| **MemGPT / Letta** | Agent **self-edits** core/archival via tools | Agent judgment | Implicit in what is paged | Evict from core | Weak vs enterprise graphs | Agent decides |
| **MemoryBank** | Store + Ebbinghaus-style decay | Retrieval mix | Recency in forget curve | Decay | Session summaries | Forget curve |
| **LangMem** | Hot-path tools + background extract | Consolidation in background | Cross-thread store | Tool delete | Namespace | Background merge |
| **DST (TOD)** | Slot overwrite | Last write wins typically | Dialogue state “now” | Slot reset | Rare | Current belief only |

**Inference for ContextFlow (smallest compatible approach):**

1. **Append-only MemoryItems** with `superseded_by` (Graphiti-like invalidation **without** a graph product).  
2. **LLM proposes** structured patches; **validator** rejects unknown workstream ids and empty provenance.  
3. **Conflicts:** if two asserted decisions on the same `(workstream, referent, slot-key)` disagree → do **not** silently overwrite; either supersede with provenance **or** leave both and let the **gate CLARIFY** on the next deictic use.  
4. **User correction** (“I meant navy”) → new `kind=correction` item + supersede the old decision.  
5. **Abandon** → workstream `resolved`/`abandoned`; items remain for audit, excluded from working set.  
6. **No giant event bus.** One `commit` per turn (or batched after the user turn) is enough.

**Avoid:** Letta-style **unquestioned** self-edit of canonical store (agent as authority). **Avoid:** Mem0-style “search then dump top-k” as the **only** context to the answer model.

---

## 3. Retrieval vs working context

### 3.1 Comparison

| Mode | Solves | Fails on |
|---|---|---|
| **A Full history** | Nothing missing if it fits | Interference; cost; our weak-generator probe | **Practice + PoC** |
| **B Recent window** | Local coherence | Return after a long detour | **Practice + intended case study** |
| **C Vector retrieval** | Semantic paraphrase | Sibling cues; “dress” retrieves all dress facts **and** still wrong NOW | **Practice** |
| **D Structured retrieval** | Filter by workstream/slot | Needs ids; DST-like | **Practice (TOD)** |
| **E Hybrid** | Recall | Still a **candidate set**, not a referent | **Practice (Mem0 v3, Graphiti)** |
| **F ContextFlow RB-WSR** | NOW + compact continue | Empty cards → empty working set | **PoC** |

### 3.2 The dress example (illustrative, not a dataset)

History: AUTH, DRESS, TRIP, PAPER. User: *“Okay, back to the dress — what did we decide?”*

- Retriever: many DRESS facts (navy, black, lighting, sizes…).  
- RB-WSR: workstream=DRESS, referent=outfit selection, **include** decision=navy + constraint=formal, **exclude** AUTH/TRIP/PAPER.  
- If navy was never written as a MemoryItem, RB-WSR can still **name** DRESS and **fail continuation**. That is **extraction**, not TAU.

---

## 4. Working-set representation

**PoC `ContextPackage`:** task summary, selected loop, decisions, constraints, entities, token diagnostics, decision_text (all open cards).

**Inference — WorkingSet (answer-model contract):**

| Field | Required for “useful continuation”? |
|---|---|
| Resolved workstream (human title + id) | Yes |
| Resolved referent / loop | Yes if siblings exist |
| Unresolved objective | Yes |
| Current **asserted** decisions (not superseded) | Yes |
| Relevant constraints | Yes |
| Relevant entities / facts | Yes |
| Pending questions / open loops **in this workstream** | Selected loop first; others only if mode FULL_TASK |
| Recent state changes (last 1–2 commits on this stream) | Useful; **ADAPT** |
| Provenance (turn ids) | Useful for debug; optional in user-facing prompt |
| Ambiguity / CLARIFY question | If gated |
| **Exclusions** (`should_not_carry`) | **Internal eval + compiler filter**; optional short “do not mention AUTH” line if contamination is observed |

`should_not_carry` is an **eval and compiler** concept, not a user-facing ontology. **Inference:** keep it as a filter over MemoryItems (`workstream_id != selected`).

**Contract:** `CORRECT_TASK ∧ empty_required_fields ⇒ E2E_FAILURE`.

Decision context (all open workstream **headers**) may still grow with n. **KEEP** that PoC honesty. Compact **answer** working set must not dump sibling workstreams’ loops.

---

## 5. Distinctive contribution (do not oversell)

**Coherent stack:**

```
Persistent MemoryStore
    → Retriever (candidates; optional; start structured+lexical)
        → ContextFlow (proposal + referent + gate)     # FROZEN MATH
            → WorkingSetBuilder / ContextCompiler
                → answer LLM
```

**What is distinctive (modest):** not memory storage; **referent vs task**, **mention clocks**, **deictic/correction routes**, **LLM proposal is not the decision**, **ACT vs fail-closed CLARIFY**, **selected-loop compile**, **contamination avoidance**.

**What is not distinctive:** fact extraction, vector search, temporal KGs, OS-style paging, DST slots, LongMemEval QA.

**Interfaces vs frozen core**

| Piece | Status |
|---|---|
| TAU/DELTA/HYST, W_*, resolver, bind_task vs decide | **KEEP frozen** |
| Hash embeddings | **KEEP** until real miss; then Retriever interface |
| `apply_update` no-op | **must change** (writer) — not the gate |
| Compiler compact vs full | **KEEP behavior**; **ADAPT** input from MemoryItems |
| ConversationStore isolation | **KEEP**; persist later |

---

## 6. Industry / literature survey

For each: problem, representation, update, retrieve, **not solved**, **adopt**, **avoid**.

### LongMemEval (Wu et al., ICLR 2025)

1. Long-term **memory QA** (extract, multi-session, temporal, update, abstain).  
2. Compiled session haystacks + held-out question.  
3. Systems index/retrieve/read.  
4. Retrieval + read.  
5. **Not** in-stream `A→B→A` workstream bind; S-split is often **glued strangers** (**our prior audit**).  
6. Adopt: **abstention ≠ CLARIFY**; index/retrieve/read split; time-aware keys **for the store**, not the gate.  
7. Avoid: scoring ContextFlow on LME `answer`; treating S as one user.

### LoCoMo (Maharana et al., ACL 2024)

1. Very long two-speaker memory (QA, event summary).  
2. Persona + event-graph **constructed** dialogues (~10 convos).  
3. N/A (eval set).  
4. Full context or RAG.  
5. Not heterogeneous **work** returns; not ACT/CLARIFY; synthetic long chat.  
6. Adopt: temporal/event consistency as a **memory-item** concern.  
7. Avoid: claiming LoCoMo proves RB-WSR.

### MemoryBank (Zhong et al., 2023)

1. Companion long-term recall + persona.  
2. Vector memory + summaries + forget curve.  
3. Write + decay.  
4. Dense retrieval + portrait.  
5. No referent gate.  
6. Adopt: **summaries as optional items**, not as the gate.  
7. Avoid: Ebbinghaus as routing.

### MemGPT / Letta (Packer et al. 2023; Letta product)

1. Finite context via **paging** + self-edit.  
2. Core / recall / archival.  
3. Agent tools write memory.  
4. Agent searches archival.  
5. No deterministic sibling-loop policy; LLM is authority.  
6. Adopt: **tiering** (working set vs store) as metaphor.  
7. Avoid: **self-edit as canonical** without validation.

### Zep / Graphiti (Rasmussen et al. 2025; getzep/graphiti)

1. Evolving enterprise facts + time.  
2. Temporal knowledge graph, invalidation.  
3. Episode ingest, invalidate old edges.  
4. Hybrid semantic/BM25/graph.  
5. Does not replace deictic **NOW** resolution among open **workstreams**.  
6. Adopt: **invalidate don’t delete**; provenance; temporal validity **on items**.  
7. Avoid: **Neo4j/Graphiti as MVP**. Unjustified until item lists fail.

### Mem0 (Chhikara et al. 2025; product v3)

1. Managed extract + search for agents.  
2. Fact memories + entity boost + user/session scope.  
3. ADD-only extract (v3) + APIs.  
4. Vector + BM25 + entity fusion.  
5. Top-k ≠ working set; vendor LoCoMo/LME scores are **their** stack.  
6. Adopt: **namespace isolation**; hybrid retrieve as **Retriever** impl later.  
7. Avoid: replacing the gate with `search()`.

### LangGraph / LangMem

1. Cross-thread store + extract tools + checkpoints.  
2. Namespaced KV / embeddings.  
3. Hot-path tools or background manager.  
4. Search tools.  
5. Checkpoint ≠ referent clocks.  
6. Adopt: **background extract** vs hot path; **namespace = conversation_id**.  
7. Avoid: agent-managed memory as the only writer.

### Dialogue state tracking (MultiWOZ, SGD)

1. Slot filling in a **schema**.  
2. Belief state.  
3. Overwrite slots.  
4. Current state in prompt.  
5. Related tourist APIs ≠ clothing after JWT; **our MultiWOZ audit**.  
6. Adopt: **current asserted state** as items.  
7. Avoid: DST labels as CF gold; scaling MultiWOZ.

### RAG / long-context (RULER, needle-in-haystack)

1. Find a fact in long text.  
2. Tokens or chunks.  
3. N/A.  
4. Attention or retrieve.  
5. Not workstream deixis.  
6. Adopt: nothing for the gate.  
7. Avoid: NIAH as RB-WSR eval.

---

## 7. Production architecture (smallest)

```
Client → Cloud Run (FastAPI)
  → Conversation namespace
  → MemoryStore          # durable later
  → MemoryWriter         # propose/validate/commit
  → Retriever            # start: structured filter + lexical; vector DEFER
  → Engine (FROZEN)
  → WorkingSetBuilder / ContextCompiler
  → LLM.generate (Vertex optional)
```

| GCP piece | Verdict |
|---|---|
| Cloud Run | When a URL is needed |
| Secret Manager | If Vertex in prod |
| Cloud Logging | Decision traces, redacted |
| Firestore **or** Cloud SQL | **Only** to survive restart / multi-instance. Prefer one document/row per conversation namespace. SQL if we need item version queries; Firestore if document-shaped namespaces. **Do not pick both.** |
| Vector Search | **DEFER** until lexical miss on real traffic |
| Graph / Neo4j | **DEFER** |
| BigQuery / Pub/Sub | **DEFER** |

**Interfaces (implement later, names stable):**

- `MemoryStore` — get/put namespace, list workstreams, list items, version  
- `MemoryWriter` — `propose`, `validate`, `commit`  
- `Retriever` — `candidates(message, namespace) -> list[Workstream\|Item]`  
- `Resolver` / `Gate` — **existing modules, frozen**  
- `WorkingContextBuilder` — MemoryItems + selected ids → WorkingSet  
- `ContextCompiler` — WorkingSet → prompt strings (**KEEP** compact rules)  
- `LLM` — existing protocol  

---

## 8. Isolation / production semantics (specify, don’t implement)

| Topic | Semantics |
|---|---|
| Isolation | `conversation_id` is the memory namespace. No cross-read. |
| Concurrency | Optimistic version on namespace; stale commit rejected |
| Restart | Store reload; clocks are part of the document |
| Idempotency | `turn` is the idempotency key for commits |
| Versioning | monotonically increasing `namespace.version` |
| Stale writes | reject if client version < store |
| Deletion | retract items / resolve workstream; tombstone; don’t secretly drop provenance |
| Observability | transition, ids, margins, item versions, **not** raw PII in public logs |

In-memory `ConversationStore` already isolates process-lifetime. **KEEP.** Persistence is **NEW** behind `MemoryStore`.

---

## 9. What this audit is not

Not a claim of benchmark superiority, token savings, or production readiness. Not a license to retune the gate. Not a license to download Graphiti/Mem0 as a dependency this week.
