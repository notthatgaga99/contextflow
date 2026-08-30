# Implementation-readiness audit

**Date:** 2026-08-29  
**Authority:** `docs/CONTEXTFLOW_DESIGN_FREEZE.md`, `docs/POC_FREEZE.md`, `docs/MEMORY_ARCHITECTURE_RESEARCH.md`  
**Scope:** inspect vs freeze. **No implementation in this step.** No Vertex. No threshold/weight changes. No dataset hunt.

---

## A. KEEP (use as-is)

| Component | Location | Why |
|---|---|---|
| Gate math | `app/config.py`, `app/router/gate.py` | TAU=0.20 DELTA=0.08 HYST=0.05 COLD=3 |
| Scorer weights | `app/retrieval/scorer.py` | W_LLM/W_SIM/W_REC/W_LOOP, LAMBDA, hash embed |
| Referent resolver | `app/router/referent.py` | explicit / deictic / correction; clocks |
| Proposal sanitize | `app/engine.py` `_sanitize_proposal`, `app/router/proposal.py` | LLM ≠ decision |
| Conflict detect | `app/router/references.py` | |
| Engine control flow | `app/engine.py` `handle_turn` | propose → resolve → score → gate → compile → generate |
| `generate()` vs clocks | `app/engine.py` `_act` | clocks written **before** generate; generate does not call `record_mention` |
| LLM protocol | `app/domain.py` `LLM`, mock/ollama/gemini | |
| Task as control plane | `app/models/task.py` | objective, loops, clocks, cues |
| Loop ids | `{task}.loopk` | |
| Compact/full/merged compile **modes** | `app/context/compiler.py` | compact answer excludes sibling **loops on other tasks** already |
| Isolation of engines | `app/memory/sessions.py`, `tests/test_conversation_isolation.py` | one registry per `conversation_id` |
| InMemoryRegistry as workstream map | `app/memory/registry.py` | add/get/open/active/clocks |
| Firestore stub | `app/memory/firestore_registry.py` | stay unimplemented |
| FastAPI `/turn` + isolation | `app/api/main.py` | |
| PoC eval/demo | `eval/demo.py`, `eval/task_count_scale.py`, frozen tests | mechanism evidence |
| Hash embeddings | `MockLLM.embed` / Ollama hash | no Vector Search |

---

## B. ADAPT

| Component | Current | Target |
|---|---|---|
| `TaskAnchor` lists | `decisions` / `constraints` / `entities` are anonymous strings; compiler copies them into `ContextPackage` | Data plane moves to `MemoryItem`; compiler/WorkingSetBuilder **projects asserted items** into those package fields (keep field names so existing render tests still make sense) |
| `ContextPackage` | No exclusions, no item ids, `source_event_ids` always `[]`, facts = entities | Add WorkingSet fields (or a thin wrapper) without breaking `to_dict` used by demo |
| `ContextCompiler.build` | Reads only `task.anchor.*` | After selection, fill decisions/constraints/facts from **asserted** items for that workstream (+ loop scope if set) |
| `Engine` | Hard-codes `self.reg.open_tasks()` as candidates; `ContextCompiler()` constructed internally | Inject `Retriever` (default: open workstreams) and optional `MemoryStore` / `WorkingContextBuilder`; **do not** change gate call sequence |
| `Engine._act` | `apply_update(task_id, {})` after generate | Stop treating this as the writer. Clocks stay. Optional: call WorkingSetBuilder then compile. Writer is **not** `generate()`. |
| `ConversationStore` | Map id → `Engine`+`InMemoryRegistry` only | Same isolation; attach `MemoryStore` namespace per id |
| `Task.status` | `active \| paused \| resolved` | Allow `abandoned` as freeze B; gate already treats non-open as absent via `open_tasks()` |
| `Registry` protocol | `apply_update` mutates lists | Keep method for **legacy eval** (MultiWOZ harness, `test_registry`); **do not** use it as MemoryWriter |
| API `TurnOut` | titles from package | Can expose working-set titles; not required for v1 |

---

## C. NEW

| Piece | Notes |
|---|---|
| `MemoryItem` model | kinds: fact, decision, constraint, entity, preference, event, correction + freeze fields |
| `MemoryStore` protocol + in-memory impl | namespace version, items by id, list by workstream, optimistic version, idempotent `turn` commits **in-process** |
| `MemoryWriter` | `propose` / `validate` / `commit`; first `propose` may be **deterministic/rules or injected patches** (no Vertex) |
| `Retriever` protocol + `OpenWorkstreamRetriever` | `candidates(message, namespace) -> list[Task]`; does not pick referent |
| `WorkingContextBuilder` | selected task+referent + store → package fields; exclude competing workstreams’ loops; exclude superseded/retracted |
| Sufficiency helper | `correct task + missing required state ⇒ insufficient` (eval/test, not gate) |
| Optional `item_ids` on `Task` | freeze B; small field add is ADAPT of Task not a new control object |

Durable Firestore/SQL: **not** in this implementation slice (freeze: triggered by restart need).

---

## D. DEFERRED (do not build)

- Vector Search, embeddings in scorer, Graphiti/Neo4j, graph edges  
- Cloud Run deploy, Secret Manager, Vertex experiments  
- BigQuery, Pub/Sub  
- Forget curves, MemGPT paging  
- Automatic CLARIFY on every item conflict (v1 skip+log)  
- Dual durable backends  
- Replacing Mock/Ollama/Gemini  
- Consent case study as “proof”  
- Neural reranker, ForegroundReferent, Platt in gate  

**Freeze O vs this ticket:** freeze deferred *productizing* preference/event **types**. This ticket still **requires those kind enums** on `MemoryItem`. Audit recommendation: implement the **kinds** as data; do not add graph/event-product behavior. That matches both documents.

---

## E. Contradictions (code vs freeze)

1. **`apply_update` is not append-only / supersession.** It appends strings and can **remove** loops (`resolved_loops`). Freeze: do not silently overwrite; supersede decisions. **Engine** passes `{}` so production path is a no-op; **tests and MultiWOZ eval** still mutate lists.  
   **Do not “fix” by changing gate.** Implementation: new writer beside this; leave `apply_update` for legacy tests unless you approve deprecating it.

2. **Compiler source of truth is `TaskAnchor`, often empty.** Live NEW cards are truncated utterances; decisions never appear unless pre-seeded (demo factory / sufficiency scenarios). Freeze: working set from MemoryItems. Not a gate bug.

3. **Entities vs facts.** Compiler puts `anchor.entities` in `relevant_facts`. Freeze splits fact vs entity kinds. WorkingSetBuilder should map `kind=fact` → facts, `kind=entity` → entities (extend `ContextPackage` or render lines).

4. **No `MemoryStore` namespace version.** Registry versions **per task**, not conversation. Freeze: optimistic namespace version + idempotent turn commits.

5. **`ConversationStore` ≠ `MemoryStore`.** Isolation is engine-scoped; there is no item namespace. Two conversations can both have `T1` (already tested). Items must be keyed by `(conversation_id, item_id)`.

6. **`generate()` cannot mutate items (true today)** but **could** if we wrongly put Writer inside `LLM.generate`. Must not.

7. **CLARIFY already returns `package=None`.** Freeze: no fake working set. **KEEP** this behavior; tests should lock it.

8. **Retriever does not exist.** Engine always scores all `open_tasks()`. Default retriever = that list is **compatible**, not a contradiction.

9. **`abandoned` status** missing. Low risk.

10. **Write timing vs this-turn working set.** Freeze: writer after user turn, not from generate. If writer runs **after** `handle_turn`, the **current** ACT package will not include this turn’s new decision (only later returns will). The A→B→C→D→return-B fixture must **commit B’s navy/formal items before the return probe**. That is correct and must be explicit in tests.

11. **Decision context still dumps all open card headers.** Freeze KEEP. Compact **answer** must not dump other workstreams’ loops (already true). Do not “fix” decision-context growth.

12. **Freeze vs user ticket on engine composition:** freeze says add store/writer **beside** engine; ticket says engine composes Retriever + WorkingContextBuilder. **Not a conflict** if Retriever default is `open_tasks()` and writer is **not** inside generate.

No freeze/code conflict that requires changing TAU/DELTA/HYST/W_* or resolver.

---

## F. Exact files intended to change (after approval)

**New**

- `app/models/memory.py` — `MemoryItem`  
- `app/memory/store.py` — protocol + `InMemoryMemoryStore`  
- `app/memory/writer.py` — propose / validate / commit  
- `app/memory/retriever.py` — protocol + open-workstream impl  
- `app/context/working_set.py` — `WorkingContextBuilder` + sufficiency check  
- `tests/test_memory_store.py`  
- `tests/test_memory_writer.py`  
- `tests/test_working_set.py`  
- `tests/test_abcd_return_fixture.py` — synthetic A/B/C/D integration (not empirical evidence)  
- `docs/IMPLEMENTATION_READINESS_AUDIT.md` — this file  

**Adapt (minimal)**

- `app/models/task.py` — `item_ids`; optional `abandoned`  
- `app/models/context.py` — optional WorkingSet fields (exclusions, item ids, recent changes) if needed without breaking demo JSON  
- `app/context/compiler.py` — **only** extra kwargs / fill from builder-supplied lists; **do not** change compact-vs-full loop selection rules  
- `app/engine.py` — inject retriever + optional store/builder; **do not** change `decide`/`bind_task`/thresholds; generate still no writer  
- `app/domain.py` — `MemoryStore` / `Retriever` / `MemoryWriter` protocols  
- `app/memory/sessions.py` — namespace includes store  
- `app/api/main.py` — wire store per conversation if engine needs it  
- `tests/test_conversation_isolation.py` — extend to MemoryItems; **preserve** existing cases  

**Do not change**

- `app/router/gate.py`, `app/retrieval/scorer.py` weights/thresholds  
- `app/router/referent.py` semantics  
- `eval/demo.py` story (may keep reading `ContextPackage`)  
- Firestore implementation  
- `.env` / Vertex modules beyond unused imports  

---

## G. Exact tests to add/change

**Add**

| Test file | Cases |
|---|---|
| `tests/test_memory_store.py` | create item; provenance required; version increment; append-only (no delete of superseded); isolation across namespaces |
| `tests/test_memory_writer.py` | validate rejects unknown workstream, unknown referent, bad kind, missing `source_turn`; invalid proposal does not commit; supersession on explicit correction (navy); retraction; skip+log on unkeyed contradiction; `propose` does not commit |
| `tests/test_working_set.py` | selected workstream’s decisions only; selected loop state; competing loops excluded; superseded excluded; missing required state ⇒ `insufficient=True`; CLARIFY ⇒ no package / no fake set |
| `tests/test_memory_safety.py` | `generate()` does not commit items (spy/store snapshot); MockLLM generate + writer not called |
| `tests/test_abcd_return_fixture.py` | Seed A auth, B outfit (navy, corporate/formal, evening), C travel, D paper; clocks so return-to-B; assert CF package contains navy + constraints, not C/D loops |
| Isolation | Conversation A items invisible to B |

**Change (lightly)**

- `tests/test_conversation_isolation.py` — keep current JWT vs dress tests; add item leak check  
- `tests/test_compiler.py` / `test_context_reconstruction.py` — should still pass if compact rules unchanged; if `build()` gains optional `working_set=`, default None = current behavior  
- `tests/test_registry.py` `apply_update` — **leave** unless you approve deprecating it  

**Do not change to make routing “pass”**

- `tests/test_routing.py`, `test_gate.py`, `test_demo.py`, `test_task_count_scale.py`  

**Eval (not this slice)**

- Consented E2E remains blocked on transcript; not these fixtures.

---

## H. Decisions that still need your approval

1. **`apply_update` legacy path.** Keep mutating `TaskAnchor` lists for MultiWOZ eval + `test_registry`, while MemoryItems are the production data plane? (Recommended: **yes**, do not rewrite MultiWOZ harness now.)

2. **Writer inside `handle_turn` vs beside it.** Recommended: **beside** — tests/API commit items **before** the return turn; engine only **reads** store when building the working set. No LLM extract in v1 `propose` (deterministic/injected patches only).

3. **Slot key for supersession.** Freeze: `(workstream, referent, kind+slot)`. v1 can use optional `slot` on the item (e.g. `color`) so “navy” supersedes “black”; without `slot`, skip commit (unresolved). Confirm `slot` as an extra field (not in freeze list). **If you reject `slot`, say so** — then supersession only when `validate` is given an explicit `supersedes_id`.

4. **`ContextPackage` vs new `WorkingSet` type.** Recommended: **keep `ContextPackage`** as the compiler I/O object; builder fills it. Avoid dual prompt types that break demo.

5. **Engine constructor break.** Adding optional `retriever=` / `memory_store=` with defaults preserves all current `Engine(llm, reg, SETTINGS)` call sites. Confirm optional kwargs only.

6. **Namespace optimistic versioning in v1.** In-memory `version` + reject stale `commit(expected_version=)` is enough; no etcd. Confirm no Firestore in this PR.

None of these require changing frozen routing.

---

## Intended pipeline (after approval)

```
turn (user)
  → MemoryWriter.propose/validate/commit     # not generate()
  → MemoryStore
  → Retriever.candidates = open workstreams
  → FROZEN Engine (same gate)
  → selected workstream + referent
  → WorkingContextBuilder (asserted items only)
  → ContextCompiler (compact rules KEEP)
  → LLM.generate
```

If implementation later hits a freeze conflict, **stop and report** rather than retune the gate.
