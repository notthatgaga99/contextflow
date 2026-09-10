# ContextFlow — Handover: HLD, LLD, Design & Novelty

**Audience:** engineer taking over the codebase, or interviewer/reviewer who needs design depth.  
**Status:** research POC / production-shaped durable path — **not production-ready**.  
**Routing freeze:** `8cc5539` — do not retune `gate.py`, `referent.py`, `scorer.py`, `config.py`, `MemoryWriter` without an explicit new phase.  
**Companions:** `ARCHITECTURE.md`, `POC_FREEZE.md`, `MEMORY_SEMANTICS.md`, `CLOUD_POC_REVIEWER.md`, `PRODUCT_DEMO.md`.

---

## 0. One-paragraph thesis

Long multi-task chat fails less because the model cannot read a transcript, and more because the system does not know **which unfinished workstream** the user is pointing at (`fix that`, sibling `401`s, `the other one`). ContextFlow is a **working-context control layer**: it keeps multiple open workstreams alive, resolves task/referent with deterministic state + an ACT/CLARIFY gate, and reconstructs a **minimum useful working set** for the answer model. The LLM **proposes**; ContextFlow **decides** routing; MemoryWriter **commits** memory. Distinctive step name used in design freeze: **referent-bound working-set reconstruction (RB-WSR)**.

---

# Part I — High-Level Design (HLD)

## 1. Problem framing

| Failure mode | What typical stacks do | What ContextFlow targets |
|---|---|---|
| Underspecified return (`fix that`) | Recency or keyword RAG | Mention/active clocks + deictic/correction rules |
| Sibling lexical collision (`401` on two tasks) | Always ACT on best match | Fail-closed **CLARIFY** when margin/ambiguity is unsafe |
| Contaminated answer context | Full history / recent window | Compact package: selected task + selected loop + asserted items only |
| Memory drift on correction (`black` → `navy`) | Overwrite or forget | Append-only supersession; CURRENT vs HISTORY vs EXCLUDED |

**Product line:** *ContextFlow lets you leave a thought without losing it.*

## 2. System context

```
┌─────────────┐     HTTPS      ┌──────────────────┐
│ Reviewer /  │ ─────────────► │ Cloud Run        │
│ harness     │                │ FastAPI /turn    │
└─────────────┘                └────────┬─────────┘
                                        │
         ┌──────────────────────────────┼──────────────────────────────┐
         ▼                              ▼                              ▼
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│ Vertex LLM      │          │ Firestore       │          │ Frozen router   │
│ extract+answer  │          │ memory+registry │          │ gate/referent/  │
│ (propose only)  │          │ (persist only)  │          │ scorer          │
└─────────────────┘          └─────────────────┘          └─────────────────┘
```

**Two surfaces (do not conflate):**

| Surface | Purpose | Auth | LLM | Memory |
|---|---|---|---|---|
| Local product demo `eval.product_demo` | Narrative UI (15-beat) | localhost | Mock | in-process |
| Public Cloud Run `contextflow` | Swagger/API smoke | `allUsers` | Mock (older revision) | in-memory |
| Durable Cloud Run `contextflow-durable` | Technical proof | IAM invoker only | Vertex | Firestore |

## 3. Logical architecture (authority map)

```
User message
    → MemoryExtractor          # proposes MemoryPatch only (never routes)
    → MemoryWriter             # propose → validate → commit (only mutation path)
    → MemoryStore / Registry   # conversation-scoped persistence
    → LLM proposal (soft)      # soft task id; never the decision
    → Referent resolver        # deterministic clocks + lexical rules
    → Scorer + Gate            # ACT (CONTINUE/SWITCH/RETURN/NEW) | CLARIFY
    → WorkingContextBuilder    # CURRENT / HISTORY / EXCLUDED projection
    → ContextCompiler          # compact answer package
    → LLM.generate             # answer only — must not write memory/clocks
```

| Component | Authority | Must not |
|---|---|---|
| Extractor / Vertex | Propose patches & soft ids | Choose ACT/CLARIFY; mutate store |
| MemoryWriter | Validate + commit memory | Route |
| Gate / referent / scorer | Route & policy | Persist memory items |
| Firestore | Survive restart / isolation | Score or decide |
| `generate()` | Answer text | Write memory, clocks, registry |

## 4. Deployment topology (GCP POC)

| Resource | Role |
|---|---|
| Project `contextflow-506414` | Research POC |
| Cloud Run `contextflow-durable` @ `asia-south1` | Authenticated turn path |
| Firestore DB `contextflow-poc` | Memory + workstream registry |
| Vertex `gemini-2.5-flash-lite` @ `us-central1` | Extract + answer |
| Runtime SA `contextflow-run@…` | Datastore + AI Platform + logging |

Ingress may be “all”, but **IAM** on durable service is authenticated-only (`roles/run.invoker` for the owner). URL ≠ public access.

## 5. Evidence layers (what each proves)

1. **MockLLM unit / product demo** — mechanism + narrative, offline.  
2. **512-cell scale grid** — interference vs open-task count; wrong-ACT = 0 on controlled family.  
3. **Ten-workstream stress** — multi-thread reconstruction (synthetic).  
4. **Cloud durability / Phase 11–14** — Firestore + revision survival + dynamic NEW + correction supersession under Vertex variance.

Do **not** claim organic-chat benchmark wins or production SLO.

---

# Part II — Low-Level Design (LLD)

## 6. Key modules (code map)

| Path | Responsibility |
|---|---|
| `app/api/main.py` | FastAPI: `/health`, `POST /turn`, conversation projections |
| `app/turn_pipeline.py` | Extract-then-route; NEW: plan → create card → focused extract |
| `app/engine.py` | Composition root: `plan_turn` / `execute_plan` / handle turn |
| `app/router/proposal.py` | Soft LLM proposal schema |
| `app/router/referent.py` | Pure referent resolution (no writes) |
| `app/retrieval/scorer.py` | Raw score blend |
| `app/router/gate.py` | ACT/CLARIFY policy |
| `app/config.py` | Frozen weights & thresholds |
| `app/memory/writer.py` | Memory authority |
| `app/memory/extractor.py` | Patch proposals (+ structured correction helpers) |
| `app/memory/firestore_store.py` | Durable memory |
| `app/memory/firestore_registry.py` | Durable workstream cards |
| `app/context/working_set.py` | Working-set projection |
| `app/context/compiler.py` | Package modes: REFERENT_COMPACT / FULL_TASK / MERGED |
| `eval/product_demo/` | Local browser demo |
| `eval/cloud_poc/` | Authenticated cloud harnesses |

## 7. Turn pipeline (sequence)

### Non-NEW turn

```
POST /turn {conversation_id, message, turn}
  → ConversationStore.engine / writer / memory
  → run_turn:
       plan_turn (side-effect free routing plan)   # or extract-first then route
       extract → MemoryWriter.validate/commit
       Engine execute: propose → resolve → score → gate
       if ACT: WorkingContextBuilder → compile → generate
       if CLARIFY: question only; no fake ACT package
```

### NEW turn (dynamic workstream — Phase 13+)

```
plan_turn → Transition.NEW
  → execute_plan: registry.add(new card)   # before extract
  → extract with focus_workstream_id
  → answer from package
```

Seed fixtures (`CF_SEED_*`) are for older harnesses; Phase 13+ dynamic proof prefers seeds **OFF**.

## 8. State model

### Workstream / Task (registry)

- `id`, `title`, `status` ∈ {active, paused, resolved, abandoned}  
- `goal` / anchor open loops  
- clocks: `last_active_turn`, `mention_turn`, `loop_mention_turns`  
- derived referent ids: `{task_id}.loop{k}`  
- exactly one `active` workstream per conversation (PoC rule)

### MemoryItem

- `kind`: fact | decision | constraint | entity | preference | event | correction  
- `status`: asserted | superseded | retracted  
- `slot` for supersession; `superseded_by`; provenance turn  
- `uncertain=true` → **rejected** by writer (never in working set)

### Working set projection

- **CURRENT:** asserted items for selected task/referent  
- **HISTORY:** superseded/retracted (audit; not answer-active)  
- **EXCLUDED:** other open workstreams (contamination guard)

## 9. Routing algorithm (frozen)

1. Build registry-conditioned proposal prompt (open cards).  
2. Sanitize unknown task ids (fail closed).  
3. `resolve_referent` **before** policy.  
4. Score candidates. On **deictic/correction**, `apply_llm=False` (ignore LLM confidence in blend).  
5. Explicit-reference conflict check.  
6. If unambiguous referent route → `bind_task` (CONTINUE / SWITCH / RETURN). Resolver ambiguity → **CLARIFY**.  
7. Else `decide(...)` with TAU / HYST / DELTA / NEW.  
8. ACT → compile + generate. CLARIFY → question; no act.

### Score (diagnostic blend, not a probability)

```
raw = W_LLM * llm + W_SIM * cos + W_REC * rec + W_LOOP * loop
```

Defaults (`app/config.py`):

| Knob | Default | Meaning |
|---|---|---|
| `W_LLM` | 0.5 | Soft proposal weight |
| `W_SIM` | 0.35 | Similarity (hash embed in PoC path) |
| `W_REC` | 0.15 | Recency `exp(-λ Δt)`, `λ=0.15` |
| `W_LOOP` | 0.15 | Loop mention affinity |
| `TAU` | 0.20 | Absolute floor on top_raw → CLARIFY |
| `DELTA` | 0.08 | Margin top−runner → CLARIFY |
| `HYST` | 0.05 | Stick to active if challenger not ahead enough |
| `COLD` | 3 | RETURN vs SWITCH after pause |

**Gate order:** conflict → TAU → HYST → DELTA → NEW/CONTINUE/SWITCH/RETURN.  
`raw_margin` is **not** P(correct). LLM confidence is diagnostic only.

### Referent rules (`referent.py`)

| Utterance kind | Behavior |
|---|---|
| Explicit / partial lexical | Token overlap with loop+goal; unique max wins; tie → ambiguous |
| Deictic (`fix that` / `it`) | Loop mention clocks, then task clocks |
| Correction (`no, the other one`) | Exclude last selected referent, then clocks |

**Known frozen boundary:** lexical `"401"` can match sibling loops → intentional CLARIFY at scale; **not patched** after observation.

## 10. Memory write lifecycle

```
patches = extractor.propose(...)
valid   = writer.validate(patches)   # reject uncertain / illegal ids / unkeyed decision conflicts
commit  = writer.commit(valid)       # append-only; supersede on slot match
```

| Action | Effect |
|---|---|
| ASSERT | New asserted item; may supersede same slot |
| SUPERSEDE | Prior → superseded; history retained |
| RETRACT | Target → retracted |
| ABANDON | Workstream abandoned; items kept for audit |
| CORRECT | New decision/correction + slot supersession |

## 11. Context compiler modes

| Mode | Answer content |
|---|---|
| `REFERENT_COMPACT` (default split) | Selected loop only |
| `FULL_TASK` | All loops on selected task |
| `MERGED_COMPACT` | Single merged blob |

**Nuance:** answer context is compact; **decision** context still lists open-task cards and **grows with n**. Do not market “token savings” without that caveat.

## 12. API contract

`POST /turn`

```json
{
  "conversation_id": "string",
  "message": "string",
  "turn": 0
}
```

Returns transition, task ids, answer / clarify_question, extract flags, correlation_id.  
Projections: `/conversations/{id}/tasks`, `/memory`, `/working-context`.

---

# Part III — Novelty & technical nuances (what you proposed)

## 13. What is novel *as a product/system claim* (honest framing)

ContextFlow’s contribution is **not** “we invented neural routing” or “we beat Mem0 on LoCoMo.” The PoC freeze explicitly forbids claiming a novel routing architecture in the academic sense.

**Defensible novelty / distinctive design:**

1. **Authority separation as the product**  
   Soft LLM proposal vs deterministic ACT/CLARIFY vs MemoryWriter commit vs answer-only generate. Most agent stacks blur these; ContextFlow makes them hard boundaries.

2. **Referent-bound working-set reconstruction (RB-WSR)**  
   After selecting workstream *and* loop/referent, reconstruct **asserted** working memory for that bound — not “retrieve similar chunks” and not “replay transcript.”

3. **Fail-closed interference policy**  
   Under sibling cue collision and thin margins, **CLARIFY is success**, not a bug. Wrong-ACT is the primary failure class to minimize.

4. **Mention/active clocks as foregrounding**  
   No separate `ForegroundReferent` object; foreground is **derived** from clocks + last selected referent (correction excludes it).

5. **Append-only memory with CURRENT / HISTORY / EXCLUDED**  
   Corrections supersede; history stays auditable; excluded streams prevent contamination in the working set.

6. **Durable control plane without giving Firestore routing power**  
   Firestore is persistence only. Routing math stays frozen and local to the process.

7. **Dynamic NEW without seed** (Phase 13+)  
   Plan NEW → create registry card → focused extract → memory attaches to real id; survives revision replacement in cloud harnesses.

## 14. Nuances an inheritor must not break

| Nuance | Why it matters |
|---|---|
| Extractor never selects working context | Contaminates authority story |
| `generate()` never writes clocks/memory | Answer loop would silently mutate state |
| Deictic/correction disable `W_LLM` | Stops confident wrong proposals from dominating |
| Uncertain patches rejected | Working set never shows soft guesses as CURRENT |
| Unkeyed decision conflicts rejected | No silent winner on ambiguous contradiction |
| Hash embeddings in PoC routing path | `W_SIM` ≠ semantic RAG; don’t claim vector-DB wins |
| Decision context dumps open cards | Compact answer ≠ compact decision |
| Sibling 401 CLARIFY | Frozen failure class; don’t “fix” with a retune |
| Durable service is IAM-gated | Don’t tell reviewers the Vertex URL is public |
| Local demo ≠ cloud proof | Mock offline UI vs authenticated Firestore+Vertex |

## 15. Allowed vs forbidden claims (paste into interviews)

**Allowed (with controlled evidence):**

> ContextFlow demonstrates interference-resistant task and referent resolution across interleaved tasks, using explicit referent/mention state plus a deterministic act/clarify gate. Across controlled high-interference scenarios, the system maintained zero wrong-action rate and degraded through clarification rather than confident misrouting at the hardest sibling-collision cases, while recency and similarity baselines degraded earlier as open-task count increased.

**Forbidden:**

- production-ready / general benchmark win / lifetime memory solved  
- mathematically minimum context / total token savings  
- LLM confidence as P(correct)  
- “novel routing architecture” as a research claim without qualification  
- equating MockLLM demo success with Cloud/Vertex accuracy  

## 16. How to verify freeze + health quickly

```bash
# Routing freeze (expect empty)
git diff 8cc553983b45702ff16c071678f9bdc5b9d26fe3 -- \
  app/router/gate.py app/router/referent.py \
  app/retrieval/scorer.py app/config.py app/memory/writer.py

pytest -q
python -m eval.product_demo --serve   # http://127.0.0.1:8766/
```

Cloud technical path: `docs/CLOUD_POC_REVIEWER.md` (needs `roles/run.invoker`).

---

# Part IV — Handover checklist

| Topic | Owner next step |
|---|---|
| Product story | `PRODUCT_DEMO.md` + README REVIEWER DEMO |
| Frozen math | `POC_FREEZE.md` + `config.py` |
| Memory rules | `MEMORY_SEMANTICS.md` |
| Cloud proof | `CLOUD_POC_REVIEWER.md` + Phase 14 artifact |
| What not to redesign | Anything under routing freeze without a new phase charter |
| Public vs durable URLs | Public Swagger on `contextflow`; durable is 403 without IAM |

---

*End of handover. Prefer extending this file over rewriting frozen router code.*
