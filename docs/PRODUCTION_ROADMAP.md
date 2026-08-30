# ContextFlow productionization roadmap

**Status:** local reference only. Do not commit or push unless explicitly approved.  
**Date:** 2026-08-27  
**Submission checkpoint (do not destabilize):** `feat/submission-polish` @ `4b1b4e9`  
**PoC freeze:** `e84dd04`  
**Engine+demo freeze:** `e9ec062`  
**GCP project:** `contextflow-506414`

This document is a plan, not an implementation license. No Vertex runs, dataset downloads, or production code follow from writing it.

---

## 1. Executive summary

ContextFlow is **not** a memory database. It is a **resolution/control layer** that sits between (a) whatever retrieved or stored work-state exists and (b) the LLM/agent action.

The PoC showed, on a **controlled scenario family**, that mention clocks + a deterministic act/clarify gate can recover from a wrong LLM proposal and keep **wrong-ACT = 0** on the Gemini HIGH-interference scale grid, degrading via clarification on sibling-401 collisions. That is **not** production accuracy, not a general benchmark, not token savings.

The next research question is whether the same control loop works on **realistic interleaved interactions**, not another synthetic grid.

The next product question is the **simplest** Google Cloud shape that can host the existing FastAPI + in-memory registry without inventing ontologies, vector DBs, or Firestore until an experiment requires them.

**Recommended posture:** keep the $0 judge demo frozen for Sep 5; run Stage 0 locally; only then a tiny Vertex smoke; do **not** retune TAU/DELTA/HYST/W_* on any test set.

---

## 2. Production problem

Users maintain several unfinished workstreams. Later they point with underspecified language (`fix that`, `the other one`, `continue this`). A retriever can return **several plausible memories**. Recency and similarity often pick the wrong sibling. Dumping the full history into the generator is bulky and can distract.

ContextFlow’s job is only:

1. Which workstream/task is being resumed?
2. Which specific open loop / referent does the user mean?
3. Is evidence strong enough to **ACT**, or should the system **CLARIFY**?
4. Which **minimal answer context** should be reconstructed from memory for the generator/agent?

It does **not** replace RAG, transcripts, or enterprise memory. It **selects and gates** among candidates those systems already produced.

---

## 3. Architecture

Conceptual production stack:

```
User interaction
      |
      v
Memory / retrieval layer     (replaceable)
      |  candidate tasks, loops, memories
      v
ContextFlow resolution layer (frozen control idea)
      |  task + referent + ACT|CLARIFY
      v
Context compiler
      |  selected task + selected loop
      v
LLM answer / agent action
```

**PoC mapping (keep):** LLM proposal → referent resolution → score/gate → ACT/CLARIFY → compact answer context → generate. State: task cards, open loops, `active_task_id`, task/loop mention clocks, derived referent, explicit/deictic/correction.

**Do not add** a `ForegroundReferent` domain object; foregrounding stays derived from clocks.

### Interfaces (conceptual)

```
MemoryProvider
  retrieve_candidates(message, turn, k) -> list[Task|MemoryHit]
  get_task(id) -> Task | None
  get_loop(task_id, referent_id) -> str | None
  open_tasks() -> list[Task]
  active() -> Task | None
  add(task) / mark_active / record_mention / set_last_selected_referent
  update_state(task_id, delta) -> None   # later; PoC apply_update is mostly no-op

LLM (existing protocol)
  propose(prompt, schema) -> dict     # soft; never the decision
  generate(prompt) -> str
  embed(texts) -> vectors             # optional; PoC uses hash

Compiler (existing)
  build(task, mode, selected_referent, open_tasks) -> ContextPackage
```

ContextFlow should not care whether `MemoryProvider` is in-memory, Firestore, a vector store, or an enterprise memory product. The LLM stays behind the existing protocol (Mock / Ollama / Gemini).

**Product sentence:** ContextFlow is a resolution layer that can be inserted between memory retrieval and agent execution.

---

## 4. Component responsibilities

| Component | Role | Deterministic? | LLM? | Cloud? |
|---|---|---|---|---|
| MemoryProvider | Candidates + persist clocks/cards | I/O only | No (unless a memory product uses one internally) | Later Firestore/vector **if** needed |
| Proposal | Soft task guess | No | Yes (`propose`) | Vertex optional |
| Referent resolver | explicit / deictic / correction | **Yes** | Soft only on deictic tie (already) | No |
| Scorer | `raw = W_LLM*llm + W_SIM*cos + W_REC*rec + W_LOOP*loop` | **Yes** given embeddings | Embeddings may be model-backed later | Vertex embeddings **only if** experiment fails hash/lexical |
| Gate | TAU / HYST / DELTA → ACT/CLARIFY | **Yes** | Never | No |
| Compiler | Selected loop vs full cards | **Yes** | No | No |
| Generate | User-facing text | No | Yes | Vertex optional |
| Observability | Decision logs | Yes | No | Cloud Logging in Stage 3+ |

**Remain frozen until evidence says otherwise:** resolver semantics, W_*, TAU=0.20, DELTA=0.08, HYST=0.05, `raw_margin` as gating quantity (not a probability), Gemini confidence not P(correct).

---

## 5. Cloud deployment architecture

**Adversarial filter:** do not add a Google service because it exists.

| Service | Required? | Why |
|---|---|---|
| **Cloud Run** | Stage 3 only | Host existing FastAPI as a stateless HTTP service. Simplest production-like deploy. |
| **Artifact Registry** | With Cloud Run | Store the container image. |
| **Secret Manager** | If Vertex in prod | Keep `GEMINI_API_KEY` / ADC config out of the image. Not needed for MockLLM. |
| **Cloud Logging** | Stage 3+ | Decision traces (transition, ids, margins). Required to debug ACT vs CLARIFY in prod-like runs. |
| **Vertex AI / Gemini** | Optional provider | `propose`/`generate` behind LLM protocol. Already validated small-scale. |
| **Firestore** | **Not** Stage 0–3 | Only if we need durable task/loop clocks across instances/restarts. Single Cloud Run instance can stay in-memory for a demo. Multi-instance or real users → then Firestore (or equivalent) implementing `MemoryProvider`. |
| **Vector DB / Vertex Vector Search** | **Not yet** | Only if Stage 2 shows lexical/hash retrieval cannot surface the gold candidate. Retrieval is the memory layer’s job; ContextFlow ranks/gates. |
| **Cloud Storage** | Optional Stage 2 | Eval artifacts, **cached** Gemini JSON. Cheap; avoids re-billing. |
| **BigQuery** | No | Overkill until there is real traffic volume. |

Candidate topology when Stage 3 is justified:

```
Cloud Run (FastAPI)
  ├── MemoryProvider (in-memory first)
  ├── ContextFlow resolver/gate (unchanged math)
  ├── LLM provider (Mock default; Gemini via flag)
  ├── compiler
  └── Cloud Logging
Secret Manager ──► Vertex (only if CF_USE_VERTEX=1)
```

---

## 6. Dataset strategy

**Do not download a random chat corpus.** Most public “conversations” lack gold **task + referent + ACT/CLARIFY**.

### Type A — already has something like task/workstream labels

| Source | What it has | Why it is **not** a drop-in ContextFlow test |
|---|---|---|
| **ATOD** (2025 OpenReview; ~1k multi-goal TOD, turn-level goal **status**, interleaving/resume) | Closest **task/goal** tracking; explicit OPEN/PENDING/etc. | Labels appear **LLM-annotated**, not human referent/loop IDs; no ACT/CLARIFY policy gold; ontology ≠ `{task}.loopk`; treat as **candidate scaffold**, not proof. Confirm license/release before any use. |
| **MultiWOZ / SGD** | Domain/intent, some domain switches | Domain ≠ workstream; weak deixis; no open-loop cards. |
| **TACT** | TOD↔chitchat switch/recovery | Mode switch, not sibling-loop resolution. |
| **LongMemEval / LoCoMo** | Long history + QA / abstention | Tests **memory recall**, not “which unfinished loop does *that* mean?” |

**Conclusion:** There is **no** public Type A dataset that already labels ContextFlow’s `(gold_task, gold_referent, ACT|CLARIFY)` jointly. Claiming ATOD or MultiWOZ “validates ContextFlow” would be dishonest.

### Type B — annotation protocol (preferred next experiment)

Build a **small** labeled set (order **80–150 probe turns**, not thousands):

**Source options (pick one, do not mix blindly):**

1. **Extend the frozen judge scenario family** with held-out paraphrases (cheap, still synthetic).
2. **Human-written interleaved work logs** (engineering/support style), 15–25 dialogues × 8–20 turns.
3. **Optional later:** sample ATOD/MultiWOZ domain-switch dialogues **only** as raw text, then **re-annotate** under our protocol (do not reuse their LLM goal tags as referent gold).

**Annotation fields (per probe utterance):**

- `gold_task_id` (or NEW / none)
- `gold_referent_id` (loop or task-level)
- `utterance_kind`: explicit | partial | deictic | correction
- `policy_gold`: ACT | CLARIFY (when two siblings share the cue, gold may be CLARIFY)
- `interference`: LOW | HIGH (sibling lexical collision?)
- optional: `plausible_distractors[]`

**Protocol rules:** two annotators + adjudication; freeze guidelines **before** labeling; **no threshold tuning on test**. Split: **dev** (for error analysis only) / **test** (once). If N is tiny, skip a train set; **do not** fit W_* or TAU on these labels.

**Label honesty:** if we authored the dialogues, say so. If we mapped ATOD goals to tasks, say **constructed**. LLM-prelabel + human verify is allowed only if humans can override and we report agreement.

---

## 7. Real-data experiment design

Compare **on the same labeled probes**:

1. Full-history / all-card dump (current `full_history` analogue)
2. Recency
3. Semantic retrieval (real embeddings **only** in this experiment; not in pytest). Until then, lexical/Jaccard is the PoC “similarity” baseline — disclose it is **not** production RAG.
4. **ContextFlow on retrieved candidates** (MemoryProvider = retriever top-k + clocks)
5. Optional: ContextFlow + oracle/full memory (upper bound on resolution given perfect candidates)

**Corruption study (cheap, high value):** replace `propose` with a **wrong** task id at high confidence (already in the judge demo). Measure recovery. No extra Gemini grid.

**Splits:** if we ever fit anything (e.g. a retriever), use train / **calibration held-out** / test. Gate thresholds stay **frozen** from PoC; calibration layer remains unused.

**Sample size:** start with ~30 HIGH-interference deictic/correction probes. Go/no-go before any Vertex batch.

**Do not** optimize TAU/DELTA/HYST on this set.

---

## 8. Evaluation metrics

Keep separate (same as PoC):

- task accuracy  
- referent accuracy  
- joint accuracy  
- ACT vs CLARIFY rates  
- **wrong-ACT** among ACT  
- clarify ∧ gold resolution  
- clarify ∧ wrong resolution  
- risk/coverage (wrong-ACT vs ACT rate)  
- recovery from corrupted LLM proposals  

Token counts remain **diagnostic**. Do not report “savings.” Decision context still grows with open cards.

---

## 9. Cost-control strategy

A developer must **never** trigger Vertex from `pytest`.

| Control | Rule |
|---|---|
| Default LLM | MockLLM |
| `CF_USE_VERTEX` / `CF_USE_GEMINI` | Explicit env; default off |
| pytest | No network; construction tests only for Gemini eval modules |
| Ollama | Optional local; not required |
| Paid eval | Separate module + `--paid` / env `CF_ALLOW_PAID=1` |
| Cache | Store Gemini JSON by prompt hash on disk/GCS; replay |
| Budgets | Max N calls and max tokens in the paid harness; abort |
| No loops | No retry-until-success; fixed 1–3 reps if stochastic |
| Fixtures | Deterministic transcripts in git (no PII) |

**Do not** re-run the 135-call Gemini scale suite.

---

## 10. Security / privacy

Real conversation traffic is **not** in the PoC. Before any live logs:

- No secrets in git (already: `.env` ignored).
- Secret Manager for Vertex in Cloud Run.
- Do not log raw user text to public artifacts; redact in eval dumps or keep local.
- Retention limits; no training on customer chats without consent.
- Project `contextflow-506414` IAM least privilege (no broad Owner for runtime SA).
- In-memory Stage 3 demo: data dies with the instance (acceptable for a private demo; not for real users).

---

## 11. Observability

Log **decisions**, not novels: `turn`, `transition`, `pred_task`, `pred_referent`, `top_raw`, `raw_margin`, `plausible_candidate_count`, `llm_task` (diagnostic), `context_mode`, token diagnostics.

Do **not** treat logged `confidence` as P(correct).

Stage 0: stdout / `eval/out` (gitignored JSON). Stage 3: Cloud Logging with the same schema.

---

## 12. Productionization phases

| Stage | Purpose | Infra | Cost | Evidence | Go / no-go |
|---|---|---|---|---|---|
| **0** | Submission + mechanism | Local MockLLM, Ollama optional | **$0** | 89 tests, `python -m eval.demo` | Already go for Sep 5 |
| **1** | Provider still works | Vertex smoke, **≤5** Gemini proposes, cache on | **cents** | Same 3 smoke cells as before | Schema parse + no 403; **stop** if not |
| **2** | Realistic probes | Local labels + optional tiny Gemini propose | **low** (prefer Mock on labeled set) | Metrics in §8 on Type B set | Wrong-ACT not exploding vs recency; else **do not** Cloud Run |
| **3** | Production-like host | Cloud Run + Artifact Registry + Logging; **in-memory** MemoryProvider; Gemini **off** by default | Run cost small; Vertex **0** unless flagged | External HTTP `POST /turn` | Demo URL works with Mock |
| **4** | Persistence + optional retrieve | Firestore **or** other store **if** multi-instance/real users; embeddings **if** Stage 2 retrieval miss rate demands it | Storage + possible embed calls | Durable clocks; still frozen gate | Only if Stage 3 users/restarts actually lose state |

---

## 13. Go / no-go criteria

- **Submit Sep 5:** Stage 0 demo + frozen PoC docs. Independent of cloud.
- **Spend more Vertex:** only Stage 1 smoke or a **predeclared** Stage 2 budget.
- **Firestore:** no-go until in-memory Cloud Run is insufficient.
- **Vector DB:** no-go until labeled probes show gold loop not in lexical/hash candidate set.
- **Retune gate:** no-go unless Stage 2 shows systematic fail-open wrong-ACT **and** a held-out calibration set exists (not the test set).
- **Falsify ContextFlow-as-layer:** if on Type B data, CF wrong-ACT ≥ recency and ≥ similarity, and recovery from bad proposals disappears.

---

## 14. Risks and falsifiers

- **Synthetic overfitting:** judge demo + scale grid share the same skeleton family.
- **ATOD/MultiWOZ misuse:** treating domain or LLM goal tags as referent gold.
- **Decision-context growth:** still an open-card dump; do not market as “minimum context.”
- **Hash embeddings:** W_SIM is not semantic RAG.
- **NEW extraction:** still a short card / demo factory.
- **Cloud sprawl:** Firestore + Vector + BigQuery without a failing Stage 2.

---

## 15. What we should NOT build yet

- New ontology / `ForegroundReferent`
- Neural reranker, calibration/Platt in the gate
- Multi-agent orchestration
- Vector DB, RAG product, memory graphs
- Firestore, Cloud Run, extra Gemini grids **before** Stage 2 go
- Threshold search on test labels
- Another 512-cell or n=10 Gemini sweep

Keep the $0 judge demo **unchanged** for submission.

---

## 16. Recommended next 3 concrete actions

1. **Do not touch `feat/submission-polish` for research.** Use a new branch from `e9ec062` or `4b1b4e9` only after Sep 5 (or a clearly named research branch) so the submission SHA stays reviewable.
2. **Write the Type B annotation guideline + 10 example labeled turns** (no download, no Vertex). Review whether gold CLARIFY vs ACT is even agree-able. Stop if annotators cannot agree.
3. **Implement `MemoryProvider` as a Protocol alias of today’s registry** (research branch only) **without** Firestore — so later backends can slot in. No new math.

After (2) looks sane: a **tiny** Stage 2 MockLLM run on those 10–30 probes vs recency/similarity/full-history. Only then consider Stage 1 Vertex smoke.

---

## Future “real interaction” demo (not the judge demo)

Separate from `python -m eval.demo`:

1. Bulky history  
2. Retriever returns **several** hits  
3. ContextFlow resolves task/referent / ACT|CLARIFY  
4. Show **retrieval found candidates** vs **resolution chose meaning**  
5. Compact answer context  

Do not claim real traffic until Type B (or licensed real logs) exist.
