# Annotation key (proposed gold)

**Pilot only.** n=10. These labels were written from the conversation sheets and the **GOLD ANNOTATION POLICY**, **not** from running ContextFlow.

**Do not** treat this file as a score for a second annotator. Independent labels belong in `AGREEMENT_TEMPLATE.md`.

**LLM proposals are not gold.** P06 lists a *later experimental injection* only so a future eval can test recovery. Annotators using blanks never see it.

Annotators must use the same policy text as in `ANNOTATION_BLANKS.md` (copied below so this file is self-contained).

---

## GOLD ANNOTATION POLICY

Apply in this order. This is a **human** labeling policy, not a description of any software.

### 1. UNIQUE REFERENT BIND

If the current utterance contains a cue that **uniquely identifies one** open loop/referent (restatement, distinctive phrase, unique entity), **ACT** that referent even if the cue is short.

“Uniquely identifies” means: among open loops, only one is a plausible match for that cue. Shared tokens (e.g. `401` on two 401 loops) are **not** unique.

### 2. FOREGROUND DEIXIS

If the utterance is **pure deixis** (`that` / `it` / `this` / `fix that` with **no** content that names a loop), foreground/mention state **may** resolve the referent **when there is exactly one plausible foreground candidate**.

Treat the unique plausible foreground as: the loop most recently **mentioned** in the history, provided it is **not tied** with another loop at that same mention turn.

Do **not** use bag-of-words overlap (e.g. the word `fix` appearing in a task **goal**) as if it were a unique lexical bind when the utterance is otherwise empty deixis.

### 3. COLLISION / NON-UNIQUE BIND

If a **lexical** cue (e.g. `401`) matches **multiple** plausible open loops **and** the utterance does not add enough evidence to tell them apart, **CLARIFY**.

Mention recency, last-active workstream, and semantic similarity to a distractor **must not** break a remaining lexical collision.

### 4. CORRECTION

`No, the other one` (and similar) **excludes** the immediately previous selection (`last_selected_referent` on the sheet).

If **more than one** remaining candidate is equally plausible, **CLARIFY**. Do not invent a unique alternative from “the mention just before the rejected one.”

### 5. ACTIVE TASK IS NOT AUTOMATICALLY REFERENT

`active_task_id` is the workstream last marked as being worked on. It is **not** the referent.

It must **not** override a clearly identified referent (unique lexical bind **or** unique foreground for pure deixis).

It must **not** be used to break a mention **tie** or a lexical **collision**.

### 6. LAST MENTION IS NOT AUTOMATICALLY SUFFICIENT

Mention recency is **evidence**, not an unconditional gold rule.

- It **can** resolve **pure deixis** when the foreground candidate is **uniquely** supported (policy 2).
- It **must not** override a **lexical collision** that remains ambiguous (policy 3).
- It **must not** break a **tie** (two loops mentioned at the same last mention turn) for pure deixis — that is **CLARIFY**.

**LLM / model proposals are never evidence.**

### How this resolves P03 vs P10

| | P03 | P10 |
|---|---|---|
| Utterance | `fix that` (pure deixis) | `still getting the 401` (lexical cue) |
| Policy | **2 + 5**: unique last-mentioned loop is B.loop1; `active_task_id=A` does not override | **3 + 6**: `401` hits A.loop1 **and** D.loop1; last mention of A **must not** break the collision |
| Gold | ACT B / B.loop1 | CLARIFY |

These are different utterance kinds, not two applications of “always last mention.”

---

## Label legend

| Field | Meaning |
|---|---|
| gold_task_id | Workstream the human would bind if they ACT |
| gold_referent_id | Loop (or task) they would bind; `NONE` if CLARIFY |
| gold_decision | `ACT` or `CLARIFY` |

---

## P01 — CLEAR EXPLICIT

| Field | Value |
|---|---|
| gold_task_id | A |
| gold_referent_id | A.loop1 |
| gold_decision | ACT |
| utterance_kind | explicit |
| rationale | Probe restates A.loop1 almost verbatim. B and C do not match. |
| evidence | unique_lexical, restatement |
| ambiguity | Low. |
| policy | 1 UNIQUE BIND; 5 (active C does not override) |

---

## P02 — PURE DEIXIS / FOREGROUND

| Field | Value |
|---|---|
| gold_task_id | C |
| gold_referent_id | C.loop1 |
| gold_decision | ACT |
| utterance_kind | deictic |
| rationale | `fix that` has no content. Last **loop mention** is C.loop1 (Docker). Active is also C. |
| evidence | unique_foreground (last mentioned loop C.loop1; not tied) |
| ambiguity | Low under policy 2. Some annotators may refuse all bare deixis; that is a **rule** miss, not missing facts. |
| policy | 2 FOREGROUND DEIXIS (last-active also C; alignment is coincidental, not required) |

---

## P03 — ACTIVE TASK ≠ REFERENT’S TASK

| Field | Value |
|---|---|
| gold_task_id | B |
| gold_referent_id | B.loop1 |
| gold_decision | ACT |
| utterance_kind | deictic |
| rationale | Bare `that` after the last **loop** mention is B.loop1 (render twice). Workstream `active_task_id` is still A. Gold **task** is B because the intended **item** is B’s loop — not “stay on A while pointing at B.” |
| evidence | unique_foreground B.loop1; active A is not the referent |
| ambiguity | Medium **before** policy 5; **low** if policy 5 is applied. Picking A is a protocol miss. |
| policy | 2 + 5 |

**Separability:** `gold_task_id` (B) ≠ `active_task_id` (A). Gold task is the owner of the bound loop. Do not set gold_task=A with gold_referent=B.loop1.

---

## P04 — TWO LOOPS SAME TASK

| Field | Value |
|---|---|
| gold_task_id | A |
| gold_referent_id | A.loop2 |
| gold_decision | ACT |
| utterance_kind | deictic |
| rationale | Only task A. Last mentioned loop is A.loop2 (expired access token), not A.loop1 (JWT 401). |
| evidence | unique_foreground A.loop2 (intra-task) |
| ambiguity | Low if turn 3 is read. |
| policy | 2 (only task A; unique last-mentioned loop) |

---

## P05 — GOLD CLARIFY (tied mention) — *intended “I don’t know”*

| Field | Value |
|---|---|
| gold_task_id | NONE |
| gold_referent_id | NONE |
| gold_decision | **CLARIFY** |
| utterance_kind | deictic |
| rationale | `fix that` with **tied** last-mention on A.loop1 and C.loop1. No unique referent. CLARIFY is the gold, not a guess. |
| evidence | mention_tie; no unique foreground |
| ambiguity | **High — by design.** Picking C via `active_task_id` is forbidden by policy 5. |
| policy | 2 (no unique foreground) + 5 + 6 (do not break ties with last-active or last-mention alone when tied) |

---

## P06 — WRONG-LLM CONDITION (gold independent of proposal)

**Gold (from history only)**

| Field | Value |
|---|---|
| gold_task_id | B |
| gold_referent_id | B.loop1 |
| gold_decision | ACT |
| utterance_kind | explicit |
| rationale | Probe restates B.loop1. A is not mentioned in the probe. |
| evidence | unique_lexical |
| ambiguity | Low. |
| policy | 1 UNIQUE BIND |

**Experimental injection (not gold, not shown on blanks):** after labeling, a system may attach `llm_proposal_task_id=A`, `llm_confidence=0.97`. Annotators and gold **must not** copy A.

---

## P07 — SEMANTIC DISTRACTOR

| Field | Value |
|---|---|
| gold_task_id | C |
| gold_referent_id | C.loop1 |
| gold_decision | ACT |
| utterance_kind | deictic |
| rationale | Last mentioned loop is Docker/CI (C). A’s goal contains “fix” + JWT words; the probe `fix that` can **lexically** resemble A more than C. Human foreground is still C. |
| evidence | unique_foreground C.loop1; `fix` in A’s goal is not a unique bind |
| ambiguity | Medium if annotators treat `fix` as lexical unique-bind for A. Policy 2 forbids that for empty deixis. |
| policy | 2 (unique foreground C) + 1 (`fix` does not uniquely identify A) |

---

## P08 — RECENCY TRAP (last-active ≠ last-mentioned loop)

| Field | Value |
|---|---|
| gold_task_id | C |
| gold_referent_id | C.loop1 |
| gold_decision | ACT |
| utterance_kind | deictic |
| rationale | Last **loop mention** is Docker (C). `active_task_id` is still A (auth). Bare `that` tracks the last **talked-about loop**, not the last **activated** workstream. |
| evidence | unique_foreground C.loop1; active A does not override |
| ambiguity | Same class as P03; protocol 2+5 resolves it. |
| policy | 2 + 5 |

---

## P09 — CORRECTION — *intended “I don’t know”*

| Field | Value |
|---|---|
| gold_task_id | NONE |
| gold_referent_id | NONE |
| gold_decision | **CLARIFY** |
| utterance_kind | correction |
| rationale | `no, the other one` rejects `last_selected_referent=C.loop1` but **does not name** which of A.loop1 vs B.loop1 (two remaining). Unique bind is not licensed. |
| evidence | correction excludes C; A.loop1 and B.loop1 remain equally plausible |
| ambiguity | **High — by design.** Picking B via prior mention is forbidden by policy 4. |
| policy | 4 CORRECTION |

---

## P10 — SIBLING 401 — *intended “I don’t know” if lexical 401 is shared*

| Field | Value |
|---|---|
| gold_task_id | NONE |
| gold_referent_id | NONE |
| gold_decision | **CLARIFY** |
| utterance_kind | partial_lexical |
| rationale | Probe `still getting the 401` matches **both** A.loop1 and D.loop1. Last mention is A.loop1 (JWT), but the protocol’s **unique-bind** bar is not met: the cue is the **shared** token, not a restatement of JWT vs Authorization. A reasonable human should **ask which 401**. |
| evidence | lexical `401` matches A.loop1 and D.loop1; no distinguishing restatement |
| ambiguity | **High — by design.** ACT A via last mention is forbidden by policy 3+6. |
| policy | 3 COLLISION + 6 (last mention not sufficient) |

---

## Counts

| Decision | ids |
|---|---|
| ACT | P01, P02, P03, P04, P06, P07, P08 (7) |
| CLARIFY | P05, P09, P10 (3) |

---

## FINAL ADVERSARIAL REVIEW

Gold labels were **not** rewritten to match ContextFlow. Examples that still resemble mention-clock behavior do so because **policy 2** stipulates unique last-mentioned loop as the unique foreground for *pure deixis*—a general discourse choice, not an engine dump.

Legend: **inferable** = a reader who has only the sheet + this policy, and who has never seen ContextFlow, can defend the gold.

| id | Task inferable? | Referent inferable? | ACT/CLARIFY defensible? | Reasonable disagreement? | Does protocol resolve it? | Encodes CF mention clocks? | Tests a general phenomenon? | Enough info w/o knowing CF? | FLAG |
|---|---|---|---|---|---|---|---|---|---|
| P01 | Yes (A) | Yes (A.loop1; JWT restatement, not A.loop2) | ACT | Unlikely | N/A | No (lexical) | Unique identification | Yes | — |
| P02 | Yes (C) if policy 2 | Yes (C.loop1) if policy 2 | ACT under 2; CLARIFY only if annotator rejects all deixis | Possible if they refuse deixis | Yes: policy 2 says unique foreground **may** ACT | **Partly:** last-mention = last-active, so a last-active heuristic also wins. Coincidental alignment, not a gold rewrite. | Bare deixis | Yes | **Questionable strength:** last-active is not a foil. Keep as deixis smoke test, not as a recency trap. |
| P03 | Yes (B = owner of bound loop) | Yes (B.loop1 unique last mention) | ACT | Yes if they treat active=A as referent | Yes: policy 5 | **Partly:** gold uses last mention as unique foreground. That is now **written policy 2**, not a hidden CF dump. A last-active baseline still **loses**. | Active workstream ≠ referent | Yes | Residual: operationalizing “foreground” as last-mentioned loop is a **stipulation**. Not undefendable. |
| P04 | Yes (only A) | Yes (A.loop2) | ACT | Unlikely if they read turn 3 | Policy 2 | **Partly** (order-of-mention toy) | Intra-task loop vs loop | Yes | **Questionable:** schematic two-loop ordering. Gold still follows policy 2. Do **not** rewrite to help/hurt an engine. |
| P05 | NONE | NONE | CLARIFY | Yes (break tie with active=C) | Yes: 2 (no unique foreground) + 5 | **No** — unique clock win is **blocked** | Genuine non-uniqueness / “I don’t know” | Yes | — |
| P06 | Yes (B) | Yes (B.loop1) | ACT | Only if they see a leaked LLM proposal | Policy 1; proposals are never evidence | No | Gold independent of proposer | Yes | — |
| P07 | Yes (C) under 2 | Yes (C.loop1) | ACT | Yes if they treat `fix` as unique bind to A | Yes: empty deixis; `fix` in a **goal** is not unique loop ID | **Partly** (foreground = last mention) | Semantic/lexical lure vs discourse | Yes | **Questionable strength:** `active_task_id=C` agrees with gold, so this is a **Jaccard foil**, not a last-active foil (P08 is). |
| P08 | Yes (C) | Yes (C.loop1) | ACT | Same class as P03 | Policy 2+5 | **Partly** (same stipulation as P03) | Last-active ≠ intended referent | Yes | Same residual as P03. Keep. |
| P09 | NONE | NONE | CLARIFY | Yes (pick B as “previous”) | Yes: policy 4 | **No** — forbids mention-before-reject as unique | Correction without unique alternative | Yes | — |
| P10 | NONE | NONE | CLARIFY | Yes (ACT A via last mention or last-active) | Yes: policy 3+6 | **No** — last mention is **explicitly insufficient** | Sibling/shared-token collision | Yes | Schematic (two 401 loops) but the collision is real. Gold **not** CF-shaped. |

**No example has a gold label that cannot be defended from the written protocol.** None were retuned so ContextFlow would score well.

**P03 vs P10:** resolved as different utterance kinds (pure deixis with unique foreground vs non-unique lexical cue). Not “always last mention.”

---

## Pilot agreement (not a statistical claim)

n=10 is **too small** for a meaningful Cohen’s κ. If you compute κ, treat it as **exploratory only**.

Do **not** calculate agreement until two people have independently filled the blanks. Do **not** show them this key or any system prediction.

**Practical read of two independent annotators on these 10:**

| Pattern | Interpretation |
|---|---|
| Strong | Same decision on ≥8/10, same referent on ACT items, **and** both mark P05/P09/P10 as CLARIFY. → Then consider a ~50-example sheet. **Not yet.** |
| Mixed | Split on P03/P08 (active vs foreground) or ACT on P05/P09/P10. → The policy was not applied or is still unclear; revise wording and **re-pilot these 10**. Do not jump to 50. |
| Poor | Frequent ACT where gold is CLARIFY, or random task ids. → Stop the real-data experiment until the annotation unit is redesigned. |

Do **not** fill `AGREEMENT_TEMPLATE.md` from this key.
