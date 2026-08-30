# Human annotation — interleaved 18 (Pilot 0 subset)

**Read this file first.** Then fill **only** your blank sheet (`ANNOTATOR_A_BLANKS.md` or `ANNOTATOR_B_BLANKS.md`). Do not open any other project documents while labeling.

You are **not** scoring software. Do **not** run code, models, or chatbots on these examples.

---

## What you are answering

For each **target user message**, given the transcript **up to and including that message**:

**What is the user actually referring to — which ongoing piece of work, and which specific object or issue (if any) — based only on this conversation?**

If you cannot tell with genuine confidence because **two or more interpretations remain plausible**, choose **CLARIFY**. Do not invent certainty.

This is **not**:

- what an algorithm should pick
- what a product “ought” to do for engagement
- a test of whether you remember a system’s rules

---

## How to label

For every example fill:

| Field | What to write |
|---|---|
| `gold_task_id` | The workstream / thread the user is pointing at, from that example’s **thread list**, or `NEW`, or `NONE` |
| `gold_referent_id` | The specific issue/object/loop if you can name it, from the thread list, or `NONE` |
| `gold_decision` | `ACT` = it is reasonable to continue as if that thread/object is identified; `CLARIFY` = a careful human would ask which one (or equivalent) rather than proceed as if it were unique |
| `reference_kind` | `explicit` / `partial` / `deictic` / `correction` / `resumption` / `none` |
| `domain` | Short label in your own words (e.g. debugging, clothing, travel) |
| `confidence` | `high` / `medium` / `low` |
| `uncertainty_reason` | Required if confidence is not high, or if you chose CLARIFY; otherwise `none` |
| `short_rationale` | One to three sentences from the transcript |

`CLARIFY` is a **full answer**, not a failure. If two or more interpretations remain genuinely plausible from the conversation, choose **CLARIFY** rather than inventing certainty.

If you ACT, `gold_task_id` should be the thread that **owns** the object you bound. Do not bind an object from thread B while leaving the task as A unless the user is truly doing that (unusual). If the object is clear but the thread label is not, prefer **CLARIFY** (or `NONE` task) rather than guessing.

---

## NEW

Use `gold_task_id = NEW` (and usually `gold_referent_id = NONE` or a short note in rationale) when the user appears to **start a genuinely new** piece of work that is not a pointer back into an already-open thread.

You may still `ACT` on NEW if the new request is itself clear (e.g. a new, unambiguous question). You may `CLARIFY` if the new request is itself underspecified.

## ABANDON

If the user **explicitly drops or defers** a thread (“never mind”, “leave that”, “I’ll do it tomorrow” as dismissal, etc.), that dropped thread does **not** automatically become “what they mean now” merely because it was mentioned earlier.

Abandon of thread X plus a vague “fix that / the other one” still often requires **CLARIFY** if something else could be meant.

## One conversation, not a card database

Some stretches of talk are **one human situation** even if you could split them into smaller tickets (for example, a Friday event and what to wear to it). Label **what the user is talking about**, not an imagined ticket system.

If a thread list offers two IDs that feel like the same conversation, pick the one that matches the user’s object, note the merge in `short_rationale`, or **CLARIFY** if splitting would change the answer.

---

## Snapshot lines (“before this message”)

Each example includes a short **snapshot** of what the transcript already showed:

- `active_task_at_turn` — what they appeared to be in the middle of
- `last_mentioned_task` — last workstream that came up
- `last_mentioned_referent` — last specific object/issue named

These are **descriptions of the transcript**, like stage directions. They are **not** instructions to copy them into `gold_*`. People change topic, point at older things, or speak vaguely. The snapshot may describe something that is **not** what the target message refers to.

---

## Transcripts

Each example includes **all turns from the start of that session through the target user message**. Later turns are omitted on purpose (they are not available to you at the moment of the message).

The **target** is marked once as `>>> TARGET USER MESSAGE`. Nothing else in the transcript is highlighted.

Thread lists under each example are **memory of what has already come up**, so you have stable IDs to write. They are not a ranking of correctness.

---

## Process

1. Work **alone**. Do not discuss examples with the other annotator until both sheets are submitted.
2. Do not look up other files in this repository for answers.
3. If you are unsure, say so (`confidence: low` + `uncertainty_reason`). Guessing is worse than CLARIFY.

When finished, return the filled sheet only.
