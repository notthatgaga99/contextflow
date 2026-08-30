# Real-interaction annotation protocol

**Status:** local research planning. Do not commit or push unless explicitly approved.  
**Date:** 2026-08-27  
**Submission freeze:** `feat/submission-polish` @ `4b1b4e9`  
**Hypothesis (falsifiable):** given an interleaved conversation with multiple ongoing workstreams and plausible memories, a resolution layer can identify the intended **task** and **specific referent** separately from ordinary memory retrieval.

Do **not** assume the hypothesis is true. This protocol exists so we can collect labels that could **disprove** it.

Do **not** download datasets, run Vertex, or write production code from this document.

---

## 1. Unit of annotation

**One example = one probe turn**, not a whole dialogue as a single label.

| Field | Required? | Why it exists |
|---|---|---|
| `example_id` | yes | Stable id for splits and disagreement review |
| `dialogue_id` | yes | Group turns that share history |
| `turn_index` | yes | Probe position; clocks are history-dependent |
| `history` | yes | Prior user/assistant turns **and** the evolving task/loop cards as they stood **before** this utterance (or a pointer to them). Resolution is not a single-sentence problem |
| `user_utterance` | yes | The probe |
| `candidates_tasks` | yes | Workstreams a retriever or registry could plausibly consider (open cards). Tests resolution **given** candidates, not “did RAG find the needle in the whole web” |
| `candidates_referents` | yes | Open loops (and task-level referents if a task has no loops). Must be listed even if unused |
| `gold_task_id` | yes | Intended workstream, or `NEW` / `NONE` |
| `gold_referent_id` | yes | Specific loop or task-level id. **May belong to a different task than `gold_task_id` only if that is genuinely what the user meant** — see §2. Use `NONE` if no referent can be assigned |
| `gold_policy` | yes | `ACT` or `CLARIFY` — what a careful assistant should do **next**, not “did we guess the ids” |
| `utterance_kind` | yes | `explicit` / `partial` / `deictic` / `correction` — human linguistic class, not a model output |
| `interference` | recommended | `LOW` / `HIGH` — sibling cue collision |
| `open_task_count` | recommended | N at probe time |
| `notes` | optional | Disagreement rationale |
| `evidence_flags` | optional | §5 categories present in **history+utterance**, not predictions |
| `llm_proposal_if_scripted` | optional | For corruption items: the wrong proposal we will inject |

**Why not label the whole conversation as one example?** Interleaving means gold changes every turn. A dialogue is a **source**; the unit of evaluation is the probe.

**Why list candidates?** Otherwise we cannot tell “retriever missed the gold card” from “resolver picked the wrong card among those retrieved.” Production telemetry should log the same split.

---

## 2. Task vs referent

Keep **two independent gold ids**.

- **Task** = workstream / card (`A` Authentication).
- **Referent** = the thing being continued, usually `{task_id}.loop{k}` or the task id if there is no loop.

**The scheme MUST allow `gold_task_id` ≠ task-of(`gold_referent_id`).** That case is rare and should be rare in gold; when it occurs it is a **hard** item (user points at a loop while the workstream label is contested). More commonly:

- same task, different loops (`A` + `A.loop2`)
- gold task matches referent’s task

**Do not collapse referent into task.** If annotators only mark “authentication,” the experiment cannot test loop-level deixis (`JWT 401` vs `expired token`).

If the user clearly means a loop but the workstream is ambiguous, prefer:

- `gold_referent_id` = the loop if uniquely identifiable
- `gold_policy` = `CLARIFY` if two tasks could own that meaning
- do **not** invent a task id to force joint accuracy

`gold_task_id = A` and `gold_referent_id = B.loop1` is **legal in the schema**. Use it only when the utterance’s intended **workstream** and **loop owner** genuinely diverge (e.g. user is on task A operationally but points at B’s open item). If annotators cannot agree, that item is `CLARIFY` or is **dropped**, not force-labeled.

---

## 3. Referent types (minimal)

Only:

| Type | Id pattern | Meaning |
|---|---|---|
| `TASK` | `A` | Whole workstream; no loop or loop not specified |
| `OPEN_LOOP` | `A.loop1` | Unresolved item on a card |

Do **not** add ENTITY / MESSAGE / ACTION / DECISION types until annotators repeatedly fail to encode an utterance with TASK + OPEN_LOOP.

---

## 4. ACT vs CLARIFY

These labels are **policy**: what the system should do **now**.

**ACT** when a competent human, seeing the same history and candidate cards, would **proceed** on a **unique** intended (task, referent) without asking which item they mean.

**CLARIFY** when proceeding would be **reckless**, even if a private guess exists.

| Situation | Typical gold_policy |
|---|---|
| Unique lexical match to one loop; no sibling collision | ACT |
| Unique deictic foreground (one loop clearly last mentioned / last selected) | ACT |
| Unique correction (“no, the other one”) with exactly one remaining salient loop | ACT |
| Two loops share the cue (`401` on A and H5); utterance is only that cue | **CLARIFY** even if annotators have a private favorite |
| Deixis (`fix that`) with **tied** loop mention clocks / no mention clocks | **CLARIFY** |
| Explicit conflict (e.g. ordinal vs evidence) | **CLARIFY** |
| Gold ids are clear to annotators **but** a product should still ask (safety, destructive action) | **CLARIFY** — “insufficient evidence to **act**,” not “we don’t know the ids” |
| Annotator does not know the **answer to the user’s problem** (how to fix Docker) | still **ACT** if the **referent** is clear — CLARIFY is not “I don’t know the fix” |

**CLARIFY is not** “the model should refuse the user’s domain question.” It is “do not bind workstream/loop and generate as if bound.”

Record both:

- whether gold **ids** are filled (`NONE` allowed)
- `gold_policy`

So we can score **clarify-and-correct** (ids right, policy CLARIFY) vs **clarify-and-wrong** (ids wrong or empty, policy CLARIFY).

---

## 5. Evidence annotation (optional flags)

Human-observed **cues in the example**, not model scores.

| Flag | Meaning |
|---|---|
| `explicit_lexical` | Content words uniquely overlap one candidate loop/card |
| `deictic_cue` | `that` / `it` / `this` / `fix that` without extra discriminating content |
| `correction_cue` | `no`, `the other one`, `not that` |
| `mention_recency` | A candidate was the last mentioned loop/task |
| `unresolved_loop` | Gold item is still an open loop |
| `entity_overlap` | Shared named entities across siblings (weak) |
| `task_semantic_similarity` | Annotator judges two cards “about the same kind of work” |
| `active_task_evidence` | Active workstream matches gold task |
| `assistant_action_evidence` | Last assistant action on a card (use sparingly; PoC clocks are **user** mention, not answer text) |

These support error analysis (“recency pointed at C, lexical at A”). They are **not** features we must implement.

---

## 6. Gold label rules (utterance patterns)

Apply **in order**. If still tied → `CLARIFY`, ids `NONE` or the tied set recorded in `notes`.

1. **Correction** (`no`, `the other one`, `not that one`): gold referent = the salient alternative **excluding** the last selected / last acted referent, if **exactly one** such alternative is clearly foregrounded. If two alternatives remain → CLARIFY.
2. **Explicit unique lexical**: if content tokens match **exactly one** candidate loop (or one task with no loops) more than all others (no tie) → that referent; task = owner of that referent; ACT.
3. **Partial cue with collision** (`the 401` when two loops contain `401`) → CLARIFY; do not pick the “more authentication-y” card.
4. **Deixis** (`fix that`, `continue that`, `yes, that one`): follow **loop mention clocks**, then task mention, as in the frozen resolver **only as a labeling heuristic if clocks are unambiguous in the history we show annotators**. If clocks are missing or tied → CLARIFY. Do **not** follow recency of the last **assistant** message unless the protocol later adds that evidence type.
5. **`back to the authentication issue`**: explicit workstream; if that task has **one** open loop, referent = that loop; if **two** loops and the utterance does not name which → task = A, referent = TASK-level `A` or CLARIFY (prefer **CLARIFY** if both loops are still open and the next action would differ).
6. **`that component`**: lexical `component` if unique; else deixis+lexical; collision → CLARIFY.
7. **`the other one` without a clear prior selection** → CLARIFY.

**Ambiguous examples that should be gold CLARIFY (include in the set):**

- “still getting the 401” with two open 401 loops.
- “fix that” as the first utterance, empty clocks.
- “the other one” with three paused tasks, no last selected referent.
- “continue that” while two loops were mentioned in the **same** user turn.

---

## 7. Hard negatives (must include)

Items where **retrieval/similarity/recency succeed at the wrong thing** or **task is right and loop is wrong**:

| Trap | What it tests |
|---|---|
| Semantic/Jaccard lure | Sibling “OAuth 401” vs “JWT 401”; similarity → wrong card |
| Recency lure | Last active = Frontend; user means Docker via deixis after Docker was last **mentioned** |
| Active ≠ referent | Active A; utterance points at B.loop1 |
| Shared keyword | Two `401` loops |
| Scripted wrong LLM proposal | Propose A @ 0.97; gold C.loop1 (judge demo pattern) |
| Right task, wrong loop | Gold A.loop2; lexical/recency on A.loop1 |
| Clear referent, don’t ACT | Unique ids but policy CLARIFY (destructive / two interpretations of the **same** loop) |
| Retriever includes gold | Gold is in `candidates_*`; a dumb ranker still picks a distractor — **resolution vs retrieval** |

If we cannot write such items, we cannot claim ContextFlow beats retrieval.

---

## 8. Interleaving levels vs realistic talk

**Controlled synthetic axis** (like the PoC grid, **held-out paraphrases**, not the submission demo script copied as “real data”):

- N ∈ {1, 2, 5, 10} open tasks  
- distractors LOW vs HIGH lexical overlap  

Label these `source = synthetic_controlled`. They stress **mechanism**, not naturalness.

**Realistic conversational axis:** `source = human_written` | `public_reannotated`. N is whatever the dialogue has; do not force N=10.

**Never mix** the two in one accuracy headline. Report **separately**.

---

## 9. Realistic conversation sources (no download yet)

| Source | Gives | Does not give | Defensible claim? |
|---|---|---|---|
| **A. Public TOD / memory corpora** (MultiWOZ, SGD, ATOD, LoCoMo, LongMemEval) as **raw text only** | Interleaving-ish or long history | ContextFlow gold; ATOD goal tags ≠ loop ids and may be LLM-made | Only after **re-annotation** under this protocol; then claim is “on re-labeled public dialogues,” not “ATOD proves ContextFlow” |
| **B. Synthetic augmentation** | Hard negatives, N, HIGH/LOW | Ecological validity | Mechanism stress; **not** “real users” |
| **C. Human-written interleaved work logs** | Natural phrasing, deixis | Scale; author bias | Honest **pilot** if authors ≠ sole annotators |
| **D. Human annotation of public/real chats** | Closer to traffic | Privacy; license; missing cards | Strongest **if** licensed and re-labeled; still not “our production traffic” unless it is |

**Default for the smallest falsifying experiment:** C + B hard negatives, tiny N. A/D only after protocol works on C.

---

## 10. Annotator agreement

Two independent annotators on the **same** candidate lists and history. A third adjudicates disagreements.

Report separately:

- task id agreement (exact match; `NEW`/`NONE` included)
- referent id agreement
- ACT/CLARIFY agreement

**Cohen’s κ** is justified if we have ≥2 raters and we care whether agreement exceeds chance on **imbalanced** ACT vs CLARIFY. Also report **raw % agreement** (easier to interpret at n=50).

If κ_task or κ_referent is low (e.g. &lt; 0.4 as a **warning**, not a magic cutoff), **stop**: gold is too subjective; do not tune ContextFlow on it.

Do not use one author as both writer and only annotator for the headline number.

---

## 11. Train / calibration / test

| If | Split |
|---|---|
| **Pilot (recommended first)** | **No train.** Optional **dev** (≤20% or 10 items) for error analysis only. **Test** frozen. **No** TAU/W_* search on test. |
| Later ML calibration (Platt, etc.) | Need enough ACT/CLARIFY labels; **this pilot will not**. Say so. If ever: train / **calibration** / test, thresholds **never** fit on test. |
| Tiny n | Prefer a **predeclared** threshold **sweep on synthetic_controlled dev only**, freeze, then **one** pass on realistic test. |

PoC gate stays frozen unless a **held-out** (non-test) set shows fail-open wrong-ACT.

---

## 12. Baselines (keep dumb)

On the **same** `candidates_*`:

| Id | Method |
|---|---|
| A | Recency (last active / last mention) |
| B | Lexical / Jaccard on loop+goal+cues |
| C | Semantic retrieval (real embeddings **only** in this experiment; disclose if still hash) |
| D | Full-history / all cards as “context”; ranking as in PoC full-history analogue |
| E | ContextFlow (frozen resolver+gate) |
| F | Later: MemoryProvider retrieval **then** ContextFlow |

No fancy RAG. No tuning baselines on test.

---

## 13. Metrics (do not collapse)

- task resolution accuracy  
- referent resolution accuracy  
- joint resolution accuracy  
- ACT rate / CLARIFY rate  
- **wrong-ACT** among ACT  
- clarify-and-correct / clarify-and-wrong  
- risk–coverage (wrong-ACT vs ACT rate)  

Optional later: downstream answer quality **only** if the probe has a checkable continuation — **not** required for the smallest falsifier.

---

## 14. Falsifiers

Conclude **“ContextFlow does not add meaningful value”** if any hold on the **frozen** test (after agreement is acceptable):

- Task ≠ referent almost never appears **and** loop-level gold is redundant with task gold (referent accuracy ≈ task accuracy for all systems).
- Semantic or lexical retrieval **already** matches CF joint accuracy and wrong-ACT (CF ≈ best baseline).
- Ablating mention clocks (recency-only CF) matches full CF.
- CF **raises CLARIFY** a lot **without** lowering wrong-ACT vs recency/similarity.
- Compact context does not help (or hurts) a **pre-registered** continuation probe.
- Annotator agreement too low (§10).

---

## 15. Sample size (practical)

Time-constrained. Prefer quality.

| n probe turns | Can say | Cannot say |
|---|---|---|
| **~50** | Protocol works; κ visible; 1–2 hard-negative classes illustrated; **anecdote-level** comparison | Significance, generalization, calibration |
| **~100** | Separate synthetic vs realistic slices; more stable wrong-ACT **descriptively** | Population inference; “production accuracy” |
| **~250** | Rough subgroup (N, HIGH/LOW, kind) **descriptive** tables | Benchmark superiority; statistical claims without a pre-registered test |

**Pilot recommendation:** **40–60 probes**: ~25 human-written interleaved, ~20 hard negatives (including 401 collision + wrong LLM proposal), ~10 gold-CLARIFY ties. Two annotators on all. **No Vertex.**

---

## 16. Future real-world demo (not `python -m eval.demo`)

Keep the $0 judge demo **unchanged**.

A later demo (research branch):

1. Show a **long** history (many cards).  
2. Show **retrieval**: 4–8 plausible memories (including a lure).  
3. Show **ContextFlow**: proposal vs referent vs gate.  
4. Show **selected** task/loop.  
5. Show **compact** answer context vs collapsed full dump.  
6. Show the agent reply.

Caption: **retrieval found candidates; resolution chose meaning.** Do not claim live production traffic.

---

## 17. Production telemetry mapping

| Annotation | Runtime log (no raw chat by default) |
|---|---|
| `gold_*` | Only on eval sets |
| `predicted_task_id` / `predicted_referent_id` | yes |
| `decision` / transition | yes |
| `top_raw`, `raw_margin`, `plausible_candidate_count` | yes (not P(correct)) |
| `llm_task` | diagnostic |
| retrieval candidate ids | yes |
| `user_utterance` / `history` | **off by default**; hash or redacted store if debugging; privacy/retention policy required for real users |

Logging full transcripts “for convenience” is a **privacy incident waiting**. Eval fixtures in git must be synthetic or licensed + scrubbed.

---

## 18. Google Cloud later (not now)

| Service | Role if Stage 2+ ever runs in cloud |
|---|---|
| Cloud Run | Host eval API / demo **after** local labels exist |
| Vertex / Gemini | Optional `propose` with **hard call cap** + cache; not pytest |
| Firestore | Only if MemoryProvider must persist across instances |
| Cloud Logging | Decision telemetry (§17) |
| Secret Manager | Vertex credentials |
| Artifact Registry | Image for Cloud Run |

None of these are required to **annotate** or to run the 50-item MockLLM pilot.

---

## 19. Cost control

- `pytest` = MockLLM, $0, no Gemini.  
- Default eval = MockLLM / optional Ollama.  
- Vertex = explicit `CF_ALLOW_PAID=1` + max calls.  
- Cache Gemini JSON by prompt hash.  
- Sampled eval only.  
- No accidental loops.

---

## 20. Recommended next experiment

**Smallest experiment that can falsify the hypothesis:**

1. Write **50 probe turns** under this protocol (human-written + hard negatives + gold-CLARIFY).  
2. Two annotators; report κ / % agreement; adjudicate.  
3. If agreement fails → **stop** (labels not usable).  
4. If agreement holds: run **frozen** ContextFlow vs recency vs Jaccard vs full-history on the **same candidate lists**, MockLLM, **one** wrong-proposal corruption subset.  
5. **Pre-register** the falsifiers in §14. **No** threshold tuning. **No** Vertex.

If CF joint/wrong-ACT is indistinguishable from recency and Jaccard on that frozen test, the hypothesis is **not supported** at this scale — do **not** deploy.

Do not recommend production deployment from this protocol alone.
