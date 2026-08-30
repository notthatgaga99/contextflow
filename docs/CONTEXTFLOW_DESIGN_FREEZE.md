# ContextFlow design freeze (proposal)

**Date:** 2026-08-29  
**Status:** proposed freeze for human review. **Not implemented. Not production-ready.**  
**Authority after approval:** implement **exactly** this document. Do not redesign in the implementation agent.  
**Does not authorize:** retuning TAU/DELTA/HYST/W_*, changing resolver/gate math, Vertex spends, dataset downloads, commits.

Companion: `docs/MEMORY_ARCHITECTURE_RESEARCH.md`, `docs/MEMORY_BENCHMARK_GAP.md`, `docs/POC_FREEZE.md`.

Classification: **KEEP** | **ADAPT** | **NEW** | **DEFER**

---

## A. Core thesis

ContextFlow is a **working-context control layer** over persistent conversational memory.

Persistent memory answers *what has been established*.  
Retrieval answers *what might be relevant*.  
ContextFlow answers *which workstream/referent is live NOW* and reconstructs a **working set** for the answer model.

The LLM may **propose** routing and memory patches. It is **not** the authority that mutates canonical memory or the ACT/CLARIFY decision.

**Name of the distinctive step:** referent-bound working-set reconstruction (RB-WSR).

---

## B. Memory model

**KEEP** workstream as the control object (`Task` today).  
**ADAPT** `TaskAnchor` string lists into addressable **MemoryItems** (same information, first-class ids).  
**NEW** provenance, supersession, temporal validity, item status.  
**DEFER** graph edges, preference as a separate product type if unused, event graphs.

```
ConversationNamespace(conversation_id)
  Workstream
    id, title, status ∈ {active, paused, resolved, abandoned}
    objective
    referents[]          # loops; id = {workstream}.loop{k}
    clocks               # mention_turn, last_active_turn, loop_mention_turns, last_selected_referent
    retrieval_cues[]
    item_ids[]
  MemoryItem
    id, kind ∈ {fact, decision, constraint, entity, preference, event, correction}
    text
    workstream_id | null
    referent_id | null
    status ∈ {asserted, superseded, retracted}
    valid_from_turn, valid_to_turn | null
    superseded_by | null
    source_turn
    proposer ∈ {user, extractor, system}
    proposal_confidence  # diagnostic only
    version
```

Not every utterance creates a workstream. Non-tasks have `workstream_id=null` items or are dropped by the writer.

Exactly one workstream `active` per namespace (**KEEP** PoC).

---

## C. Memory write lifecycle

**NEW** (PoC `apply_update` is a no-op).

```
after user turn (not from generate()):
  proposals = MemoryWriter.propose(turn, prior_namespace)   # LLM or rules
  valid = MemoryWriter.validate(proposals, namespace)
  commit = MemoryWriter.commit(valid)  # append items; supersede on explicit conflict policy
```

**Policy:**

1. Unknown workstream/referent ids → drop proposal (fail closed).  
2. New decision contradicting an asserted decision on the same `(workstream, referent, kind+slot)` → insert new item, set old `superseded_by`, old status `superseded`. Do not delete.  
3. Ambiguous contradiction without a slot key → do not commit a silent winner; leave both asserted **or** skip and rely on CLARIFY next turn. Prefer skip+log in v1.  
4. `generate()` **KEEP**: no clock writes, no item writes.  
5. Clocks **KEEP**: only user mention + gate ACT/NEW as today.

---

## D. Retrieval layer

**KEEP** current scorer inputs (proposal, lexical/hash sim, recency, loop) for **routing candidates**.  
**NEW** interface `Retriever.candidates(message, namespace) -> workstreams`.  
**ADAPT** first implementation = `open_tasks()` (structured), not vectors.  
**DEFER** embeddings / Vertex Vector Search / Graphiti until a **logged miss**: gold workstream not in candidate set on real traffic.

Retriever **does not** choose the referent. It only bounds who can be scored.

---

## E. ContextFlow layer

**KEEP frozen (PoC):**

- LLM `propose` sanitized; unknown ids discarded  
- `resolve_referent` (explicit / partial / deictic / correction)  
- deictic/correction: `apply_llm=False`  
- `detect_conflict`  
- `decide` / `bind_task`  
- TAU=0.20, DELTA=0.08, HYST=0.05, W_*, LAMBDA, COLD  
- `raw_margin` gating; LLM confidence not P(correct)  
- no ForegroundReferent object  

**ADAPT:** candidate list may come from Retriever; default = all open workstreams (today).

---

## F. Working-set schema

**ADAPT** `ContextPackage` into **WorkingSet** for the answer model:

Required on ACT:

- workstream title + objective  
- selected referent / loop text  
- asserted decisions, constraints, facts, entities **for that workstream** (and selected loop if scoped)  
- pending open item = selected loop  

Optional:

- last commit summaries on that stream  
- provenance turn ids  
- exclusion list (competing workstream titles) if contamination observed  

On CLARIFY: question only; no fake working set that pretends to ACT.

**Eval:** `should_not_carry` filters competing items. Compiler **must not** include other workstreams’ loops in compact answer context (**KEEP**).

---

## G. ACT/CLARIFY semantics

**KEEP** PoC transitions: CONTINUE / SWITCH / RETURN / NEW / CLARIFY.

CLARIFY is success when the user is ambiguous or sibling lexical collision. It is not an automatic product failure.

NEW still creates a workstream; **ADAPT** card body from MemoryWriter when present, else current default truncated utterance (**KEEP** as fallback).

---

## H. Answer-context contract

Same user message; three baselines remain: full history, recent window, ContextFlow working set.

Success = (resolution correct **or** honest CLARIFY) **and** required MemoryItems present **and** answer model can continue.

`task_id` correct + missing decision/constraint/fact = **E2E failure** (writer/representation).

Token counts diagnostic only. No savings claim.

---

## I. Production interfaces

Implement as protocols; swap storage without touching gate math.

| Interface | Responsibility |
|---|---|
| `MemoryStore` | Durable namespace CRUD, version |
| `MemoryWriter` | propose / validate / commit |
| `Retriever` | candidate workstreams |
| `Engine` | existing composition root |
| `WorkingContextBuilder` | items + selection → WorkingSet |
| `ContextCompiler` | WorkingSet → strings (**KEEP** compact/full/merged modes) |
| `LLM` | propose, generate, embed |

`ConversationStore` **KEEP** as in-memory `MemoryStore` impl.

---

## J. Google Cloud deployment path

**Phase 0:** local, in-memory store, Ollama/Mock.  
**Phase 1:** Cloud Run + FastAPI + in-memory (demo URL). Secret Manager only if Vertex. Logging of decisions.  
**Phase 2:** one durable `MemoryStore` (Firestore **or** Cloud SQL, not both) when restart/multi-instance is required.  
**Phase 3:** Vertex `generate` only with a filled cost table.  
**Never by default:** Vector Search, graph DB, BigQuery, Pub/Sub.

---

## K. Evaluation strategy

1. **KEEP** controlled PoC grid as mechanism baseline (`docs/POC_FREEZE.md`). Do not retune on new data.  
2. **Consented real conversation** FULL vs RECENT vs CF on reconstruction + usability (`docs/CONSENTED_E2E.md`).  
3. **Do not** use LongMemEval/LoCoMo/WildChat as CF gold (see gap doc).  
4. Future CF eval (when we have real traces): in-stream return probes; joint resolution; working-set sufficiency; wrong-ACT; contamination; **not** factoid QA.

---

## L. Explicit non-goals

- Inventing persistent memory  
- Beating Mem0/Zep on LoCoMo/LME  
- Token-savings marketing  
- ForegroundReferent domain object  
- Neural reranker / Platt in the gate  
- Multi-agent orchestration  
- Training on customer chats  

---

## M. What stays frozen from the PoC

Resolver semantics, W_*, TAU, DELTA, HYST, COLD, raw_margin, apply_llm=False on deictic/correction, compiler compact-vs-full **behavior**, Mock/Ollama/Gemini protocol, hash embeddings in reported routing until Retriever swap is evidenced, wrong-ACT=0 claim **only** on the controlled family.

---

## N. What must change (after approval, not now)

| Change | Class |
|---|---|
| MemoryWriter + MemoryItems + supersession | **NEW** |
| Fill decisions/constraints from extraction | **NEW** |
| WorkingSet built from items not empty lists | **ADAPT** |
| Durable MemoryStore | **NEW** when restart matters |
| Retriever interface | **NEW** (impl = open list first) |

---

## O. What is deferred

Vector DB, Graphiti/Neo4j, embeddings in the scorer, Cloud Run until local case study, BigQuery, Pub/Sub, preference/event types until a real transcript requires them, automatic CLARIFY on all item conflicts (v1 skip+log).

---

## KEEP / ADAPT / NEW / DEFER register

| Item | Class |
|---|---|
| Task/workstream + clocks | KEEP |
| Loop referents `{id}.loopk` | KEEP |
| Gate thresholds and weights | KEEP |
| Referent resolver | KEEP |
| Compiler compact answer / full-task fallback | KEEP |
| LLM propose ≠ decision | KEEP |
| generate() does not write clocks | KEEP |
| Conversation isolation by id | KEEP |
| Hash W_SIM | KEEP until miss |
| Anchor lists → MemoryItems | ADAPT |
| ContextPackage → WorkingSet fields | ADAPT |
| Compiler reading items | ADAPT |
| NEW card from writer vs utterance stub | ADAPT |
| MemoryWriter lifecycle | NEW |
| Provenance / supersession / validity | NEW |
| Retriever protocol | NEW |
| Durable store | NEW (triggered) |
| Vector / graph | DEFER |
| Forget curves / paging OS | DEFER |
| DST as gold | DEFER (rejected as CF eval) |

---

## Implementation agent instructions (after human approval)

1. Do not edit `app/router/gate.py` thresholds or `scorer.py` weights.  
2. Add `MemoryItem` + store/writer **beside** the engine; engine consumes workstreams as today.  
3. WorkingSet must include asserted decisions/constraints for the selected workstream.  
4. Tests: isolation; supersession does not delete; generate does not commit; empty required fields fail a sufficiency assertion in eval, not by relaxing the gate.  
5. No Vertex in pytest.
