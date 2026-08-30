# Annotation blanks (pilot)

**Do not look at `ANNOTATION_KEY.md` before labeling.**

Gold must come only from the conversation, candidate cards, active task, mention history, and the **GOLD ANNOTATION POLICY** below. Ignore any model output or imagined system behavior.

For each example fill:

- `gold_task_id` (`A`/`B`/`C`/`D`/`NEW`/`NONE`)
- `gold_referent_id` (`A.loop1`, `B.loop1`, task id, or `NONE`)
- `gold_decision` (`ACT` or `CLARIFY`)
- optional: `utterance_kind`, notes

`ACT` = bind this workstream/loop and continue. `CLARIFY` = do not act as if the item is uniquely identified (asking which item is OK). CLARIFY is **not** “I don’t know how to fix the bug.”

If you ACT, `gold_task_id` is the workstream that **owns** the bound referent. Do not bind a loop on task B while leaving gold_task as A.

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

**LLM / model proposals are never evidence.** Do not copy them even if someone shows you a high-confidence guess later.

---

## P01 — explicit lexical

**History**

1. User: Let's fix JWT authentication. JWT still returns 401 after refresh.
2. User: Also the checkout page component still renders twice.
3. User: CI is failing on the Docker step.

**Candidates**

| id | title | open loops |
|---|---|---|
| A | Authentication | A.loop1 JWT still returns 401 after refresh; A.loop2 expired access token |
| B | Frontend | B.loop1 component still renders twice |
| C | Deployment | C.loop1 CI is failing on the Docker step |

**State before probe:** `active_task_id=C`. Mentions: A.loop1@1, B.loop1@2, C.loop1@3.

**Probe:** `The JWT still returns 401 after refresh.`

gold_task_id:

gold_referent_id:

gold_decision:

notes:

---

## P02 — deictic foreground

**History**

1–4. Same cards created as P01 (auth, frontend, deploy).
5. User: Let's go back to the JWT 401 after refresh.
6. User: Wait, check the Docker step — CI is failing on the Docker step.

**State:** `active_task_id=C`. Mentions: A.loop1@5, C.loop1@6 (most recent loop mention = C.loop1).

**Probe:** `fix that`

gold_task_id:

gold_referent_id:

gold_decision:

notes:

---

## P03 — active task ≠ intended loop’s task

**History**

1. User: JWT 401 after refresh (task A created; A becomes active).
2. User: The checkout component still renders twice (B created).
3. User: Let's keep going on authentication — I'm still on the JWT 401. *(A marked active again; A.loop1 mentioned)*
4. User: By the way, that checkout component still renders twice. *(B.loop1 mentioned; **do not** assume A was deactivated if the sheet says active stays A)*

**Candidates:** A (JWT 401; expired token), B (component still renders twice).

**State:** `active_task_id=A` (workstream clock). Loop mentions: A.loop1@3, **B.loop1@4** (most recent **loop** mention is B).

**Probe:** `fix that`

gold_task_id:

gold_referent_id:

gold_decision:

notes:

---

## P04 — two loops, same task

**History**

1. User: Authentication: JWT still returns 401 after refresh. Also expired access token.
2. User: Let's look at the JWT 401 after refresh first.
3. User: Now the expired access token.

**Candidates:** only A, loops A.loop1 JWT 401 after refresh, A.loop2 expired access token.

**State:** `active_task_id=A`. Mentions: A.loop1@2, **A.loop2@3**.

**Probe:** `fix that`

gold_task_id:

gold_referent_id:

gold_decision:

notes:

---

## P05 — gold CLARIFY (tied deixis)

**History**

1. User: JWT still returns 401 after refresh. (A.loop1)
2. User: Checkout renders twice. (B.loop1)
3. User: In the **same message**: also Docker CI, and also remind me the JWT 401 and the Docker failure both still matter. *(Annotators: treat A.loop1 and C.loop1 as **both** mentioned at turn 3; mention clocks **tied**.)*

**Candidates:** A.loop1 JWT 401, B.loop1 render twice, C.loop1 Docker CI.

**State:** `active_task_id=C`. Loop mention turns: A.loop1=3, C.loop1=3 (tie). B.loop1=2.

**Probe:** `fix that`

gold_task_id:

gold_referent_id:

gold_decision:

notes:

---

## P06 — ignore any LLM guess

**History**

1. Auth JWT 401 (A).
2. Checkout component still renders twice (B).
3. User: The component still renders twice.

**State:** `active_task_id=B`. Mention B.loop1@3.

**Probe:** `The component still renders twice.`

Label from history only. Do **not** use a model proposal even if someone later shows you one.

gold_task_id:

gold_referent_id:

gold_decision:

notes:

---

## P07 — semantic/lexical lure vs foreground

**History**

1. A Authentication, goal text: “fix JWT authentication token refresh”, loop: JWT still returns 401 after refresh.
2. C Deployment, loop: CI is failing on the Docker step.
3. User: CI is failing on the Docker step. (C.loop1 mentioned last)

**State:** `active_task_id=C`. Mentions: A.loop1@1, C.loop1@3.

**Probe:** `fix that`

Note: A’s **goal** contains the word “fix”; C’s loop does not. Short deixis has almost no content words.

gold_task_id:

gold_referent_id:

gold_decision:

notes:

---

## P08 — recency / last-active trap

**History**

1. Docker CI failing (C created, active).
2. User: Actually, jump to authentication — JWT 401 after refresh. (A becomes **active**; A.loop1 mentioned)
3. User: One more thing about Docker: CI is failing on the Docker step. *(C.loop1 mentioned; sheet: **active_task_id remains A** — last **active** workstream was A, last **loop mention** is C.)*

**Candidates:** A JWT 401, C Docker CI.

**State:** `active_task_id=A`. Mentions: A.loop1@2, **C.loop1@3**.

**Probe:** `fix that`

gold_task_id:

gold_referent_id:

gold_decision:

notes:

---

## P09 — correction

**History**

1. JWT 401 (A.loop1 mentioned).
2. Component renders twice (B.loop1 mentioned).
3. Docker CI (C.loop1 mentioned).
4. Assistant/user selected **C.loop1** as the last acted/selected referent (stated in state).

**State:** `active_task_id=C`. `last_selected_referent=C.loop1`. Mentions: A@1, B@2, C@3.

**Probe:** `no, the other one`

gold_task_id:

gold_referent_id:

gold_decision:

notes:

---

## P10 — sibling 401 collision

**History**

1. A.loop1: JWT still returns 401 after refresh.
2. D.loop1: 401 from missing Authorization header (sibling authz).
3. User: Let's stay on the JWT 401 after refresh. (A.loop1 mentioned last)

**Candidates:** A.loop1 (JWT 401), D.loop1 (401 missing Authorization).

**State:** `active_task_id=A`. Mentions: D.loop1@2, **A.loop1@3**.

**Probe:** `still getting the 401`

gold_task_id:

gold_referent_id:

gold_decision:

notes:
