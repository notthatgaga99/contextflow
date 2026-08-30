# Consented conversation — failure analysis

**Status:** taxonomy pre-registered. No probe-level table until the transcript exists.  
**Rule:** if the real session exposes an architectural limit, **write it here first**. Do not retune TAU/DELTA/HYST/W_* or patch the 401-style lexical collision.

---

## Pre-registered failure classes

| Code | Layer | Typical symptom | Product implication |
|---|---|---|---|
| R1 | Resolver | Deixis binds the last mentioned loop, not the intended paused workstream | Clocks were wrong **or** human snapshot clocks were wrong |
| R2 | Resolver | Correction / “the other one” with two siblings | CLARIFY is legitimate |
| P1 | Representation | Native NEW cards = truncated raw utterances; return cannot match A | **Memory extraction** is missing (`apply_update` no-op) |
| P2 | Representation | Human sheet omitted a decision/constraint the answer needed | Extractor spec: store that field |
| C1 | Compiler | Right task, compact loop missing `needed_state` | correct referent + insufficient context = E2E fail |
| C2 | Compiler | Decision text still dumps all open cards (known PoC) | Compact **answer** ≠ small **decision** context |
| A1 | Answer model | Package sufficient, model still mixes streams | Model limitation; do not “fix” by stuffing full history into CF |
| A2 | Answer model | FULL HISTORY wins because the fact only lived in a forgotten assistant turn never extracted | Extractor must persist that fact onto the card |
| G1 | Ambiguity | Two live workstreams, underspecified “that” | CLARIFY is success if `gold_policy=CLARIFY` |
| S1 | Snapshot | Clocks in the sheet do not match chronology | Sheet error, not a gate bug |

---

## Known PoC limits that will likely appear

- Hash embeddings: `W_SIM` is not semantic relatedness.
- Default NEW factory titles are 48 characters of the utterance.
- No durable store; case study is single-process.
- Isolation is process-local (`ConversationStore`). Restart still loses cards.

---

## After the run (fill)

For each probe: failure code, whether FULL or RECENT was more usable, and whether the miss was **naming** vs **working context**.

Example class (only if the real chat contains it):

| Probe | Code | What happened | What production memory must keep |
|---|---|---|---|
| (after run) | C1 | Right clothing workstream; package omitted “rejected black / venue lighting” | Extract that **decision**; do not retune the gate |

> “The model named task A but could not continue because the package lacked ___.”

If we cannot say that, we are only testing the resolver.
