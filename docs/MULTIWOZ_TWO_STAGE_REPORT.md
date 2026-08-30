# MultiWOZ two-stage evaluation (routing first)

**Date:** 2026-08-28  
**Stopped:** full `llama3.1:8b` 5-condition replay (PID 43612). No Vertex. No production edits. No commit/push.  
**Data:** MultiWOZ 2.2 test shard `data/multiwoz/dialogues_001.json` only (512 dialogues).  
**Artifacts:** `eval/multiwoz_stage1/inspect.json`, `stage1.json`, `stage2.json`.

---

## 1. Dataset suitability

**For the product question** (“does naturally occurring human conversation contain enough task switching and *return* structure to make ContextFlow’s working-set abstraction useful?”):

**No — not this MultiWOZ slice.**

The shard is mostly **two-domain tourist WOZ** with **one sequential handoff** (`A → B`). Deep patterns the brief asked for (`A → B → C → D → A`, heterogeneous returns after several unrelated workstreams) **do not appear**.

DST structure (auxiliary, **not** manufactured returns):

| | |
|---|---|
| Dialogues | 512 |
| Multi-service | 409 |
| Distinct DST domains per dialogue | **1: 105, 2: 325, 3: 82, 4+: 0** |
| DST domain switches | **0: 105, 1: 278, 2: 91, 3: 26, 4: 10, 5: 2** |
| DST A–B–A events per dialogue | **0: 450, 1: 31, 2: 26, 3: 4, 4: 1** |
| Max DST gap before reusing a domain | mean **0.36** user-turns, max **6** |

A switch count of 1 is almost always **A then B**, not a return. DST A–B–A on this file is largely leftover `active_intent` and closings; it was **not** used as inclusion gold.

Utterance heuristics (all user turns, **not** DST):

| Class | Count | After hand review |
|---|---|---|
| unclassified (mostly same-domain continue) | 2696 | — |
| unsuitable (thanks/bye) | 846 | — |
| **merely sequential** | **224** | “I also need a train/hotel/…” |
| deictic cue | 37 | **almost all same-domain** (“does it have wifi?”) |
| copy-from cue | 22 | **almost all sequential + copied area/day** |
| correction cue | 12 | **almost all same-domain slot repair** |
| genuine_return cue | 4 | **2 keep, 2 reject** |
| interruption cue | 1 | keep (PMUL0079) |

**Rejected, not manufactured:** PMUL2634 “I forgot. I am also looking for museums” is sequential. PMUL2882 “head back to the guesthouse” is a **new taxi**. Most “I actually need …” lines revise the **current** constraint.

---

## 2. Number of genuine interleaving / return cases

On this 512-dialogue file, after heuristics **and** reading the flagged 76 turns:

| Scheme class | n (honest) |
|---|---|
| 1 genuine return | **2** (MUL0810 t12, MUL2423 t12) |
| 2 interruption | **1** (PMUL0079 t8) |
| 3 correction that re-asserts a prior workstream | **1** (PMUL4186 t8) |
| 4 deictic **cross-workstream** | **1** (MUL0088 t10) |
| 5 copy-from-prior (not a return) | **~2 clean** (MUL2053 t14, PMUL2746 t10); ~20 others are sequential+copy |
| 6 ambiguous / CLARIFY | **1** (MUL2423 t12; theatre unnamed) |
| 7 sequential domain transition | **224+** (dominant MUL pattern) |
| 8 unsuitable | closings, single-domain, DST-only A–B–A |

There is **not** a pool of 50 natural `A→B→C→A` dialogues here. Expanding the shard was not done (per instruction).

---

## 3. Interleaving-depth distribution

See histograms above. In words:

- Typical multi-domain dialogue: **2 domains, 1 switch**.
- **Zero** dialogues with 4+ DST domains in this file.
- Return **distance**, even on noisy DST A–B–A, is **shallow** (max 6 user turns).
- Inferable concurrent unfinished domains: WOZ usually **finishes or parks** domain 1, then starts domain 2. That is **not** several open workstreams.

This **cannot** support the larger claim: “user moved on to several other things, then came back.”

---

## 4. Selected target cases

Selection rule (locked): utterance class ≠ sequential/unsuitable; hand-read; DST ignored as memory.

| ID | Target | Class | Stage 1 | Stage 2 |
|---|---|---|---|---|
| PMUL0079 t8 | guesthouse name + parking, *before we do that* | interruption | yes | yes |
| MUL2423 t12 | which theatre | return + ambiguous | yes | yes |
| MUL0810 t12 | museum postcode you mentioned | genuine return (named) | yes | yes |
| MUL2053 t14 | same day as hotel stay | copy-from | yes | yes |
| PMUL4186 t8 | Belfry, you didn’t answer | correction | yes | no |
| PMUL2746 t10 | same as the hotel | copy-from | yes | no |
| MUL0088 t10 | does it have internet | deictic | yes | no |

These are **all** the strong-ish contacts in the inspected file, not a cherry-pick of CF wins.

---

## 5. Stage-1 routing results

**No answer model.** Eval-only `LexicalCardProposer` (card token overlap → else NEW). Frozen gate/scorer/compiler. System text attached to the **active** card via `apply_update` (eval harness, not DST). Production `MockLLM` default-NEW was **not** used as the only proposer, because that would only test “always NEW.”

| Case | Gate | CF task | Open cards | Hist tok | Compact tok | Notes |
|---|---|---|---|---|---|---|
| PMUL0079 | **CLARIFY** | — | **2** | 166 | 0 | Tie T1.loop4 vs T2.loop2. Clarify asks hotel vs “Sure, that could be nice” |
| MUL0810 | CONTINUE | T1 | **1** | 260 | 61 | **Collapsed** streams; compact loop is museum SYSTEM line |
| MUL2423 | **CLARIFY** | — | 1 | 282 | 0 | Clarify quotes **restaurant** opening turn |
| PMUL4186 | CONTINUE | T1 | 1 | 189 | 54 | Compact loop is Belfry SYSTEM line on the **Nando’s** card |
| MUL2053 | CONTINUE | T2 | 2 | 315 | 48 | Compact = “how many people / what day” hotel prompt, **not** Tuesday |
| PMUL2746 | CONTINUE | T1 | 1 | 214 | 166 | Hotel card ate later attraction SYSTEM line |
| MUL0088 | CONTINUE | T1 | 1 | 225 | 140 | Hotel card; Hamilton Lodge in loops |

`selection_match` in `stage1.json` is **too generous** when one card contains both domains. Do not treat it as gold. Honest routing:

- **Workstream split happened once** (PMUL0079: T1 hotel vs T2 underspecified “Sure…”).
- **Five of seven targets ran on a single mixed card.**
- **CLARIFY** on the best interrupt (PMUL0079) and the ambiguous theatre (MUL2423).

---

## 6. Failure classifications

| ID | Failure |
|---|---|
| PMUL0079 | Resolver **tie** / CLARIFY. Cards are utterance-sliced, not hotel vs restaurant. **Not** auto-wrong. |
| MUL0810 | **State:** restaurant CONTINUE on T1; museum recovered only as a **loop** on the same task. |
| MUL2423 | CLARIFY **wrong object** (restaurant card). Theatre never became its own workstream. |
| PMUL4186 | Hotel facts glued onto restaurant task. Compact luckily hit Belfry line. |
| MUL2053 | Selected hotel **wifi/booking-prompt** loop, not `bookday=Tuesday`. |
| PMUL2746 / MUL0088 | One card absorbs later domains. Recency-on-a-blob, not a workstream index. |

---

## 7. Context reconstruction sizes

Heuristic `ceil(chars/4)`:

| Case | Full history | Compact answer | Full-task answer |
|---|---|---|---|
| PMUL0079 | 166 | 0 (CLARIFY) | 0 |
| MUL0810 | 260 | 61 | 215 |
| MUL2423 | 282 | 0 | 0 |
| PMUL4186 | 189 | 54 | (see json) |
| MUL2053 | 315 | 48 | 181 |
| PMUL2746 | 214 | 166 | (see json) |
| MUL0088 | 225 | 140 | (see json) |

Compact can be smaller than history. On collapsed cards it is **not** a clean “other workstreams omitted” win.

---

## 8. Stage-2 answer results (4 cases × 3 contexts)

`llama3.1:8b` **generate only**. One answer per condition. Checkpointed in `stage2.json`.

| Case | Full history | Full task | Referent compact |
|---|---|---|---|
| **PMUL0079** | Abstains on name/parking (history **did** contain cheap + phone; model unused). Rubric pass on “guest/parking.” | Abstain (empty CF context) | Abstain (empty) |
| **MUL2423** | **Hallucinated** “Cambridge Arts Theatre” (not in history; that name is held-out). | CF CLARIFY about **halal restaurant** | same CLARIFY |
| **MUL0810** | Correct: postcode was never given | Same | Says postcode not mentioned; rubric miss (no “museum” token) — factually OK |
| **MUL2053** | **Tuesday** correct | **Wrong:** “Yes, it includes internet.” | Insufficient / no day |

Downstream: **full history** is the only condition that bound **Tuesday**. Compact/full-task followed the **wrong loop** on the hotel card. CLARIFY on MUL2423 asked the **wrong** workstream; full history invented a theatre.

---

## 9. Does Task + loop + mention clocks survive real conversation?

**Partially, and the failures are representational, not threshold noise.**

Observed:

- **Multiple domains “active” in the transcript** usually became **one CF task** with many SYSTEM loops.
- **Same domain twice** / 4-domain return: **absent** in this file.
- **Similar lexical loops:** area/price words shared; PMUL0079 **tied** loops → CLARIFY.
- **Return after unrelated turns:** rare; when it exists (PMUL0079), gate **CLARIFY**s rather than RETURN to a hotel card with a restaurant sibling.
- **Active task ≠ foreground referent:** engine still emits a referent id under CLARIFY (`T1.loop4`) while `task_id` is null.
- **Correction (PMUL4186):** no separate hotel task; Belfry sits in restaurant loops.
- **CLARIFY genuinely required:** MUL2423 (unnamed theatre) **yes**; CF’s question was about **dining**, so the *act* of clarifying is right and the **object** is wrong.

Default `NEW` cards titled from the raw user string (`Sure, that could be nice`) are **not** a domain workstream index. That is a **memory construction** gap (`apply_update` is a no-op in production). **Do not patch production from this report.**

---

## 10. PoC claim: expand, narrow, or unchanged?

**Unchanged.**

The frozen claim remains: interference-resistant resolution on the **controlled** interleaved family. This MultiWOZ contact does **not** justify “ContextFlow reconstructs working context when users return after several other intentions” as a **human-conversation** result.

Do not advertise the four Stage-2 rows as a MultiWOZ win. Compact **lost** the copy-from day; CLARIFY **misfired** on theatre vs restaurant.

---

## 11. Is a scalable workstream index justified?

**Not from this evidence.** Density of genuine returns is too low, depth is too shallow, and CF’s cards did not stably equal domains. Building Firestore / vector indexes / Cloud Run for “MultiWOZ-scale returns” would be **premature**.

---

## 12. Recommended next experiment

1. **Stop scaling MultiWOZ** on this question. Do not download another shard “to find D→A.”
2. Keep **human annotation** on the synthetic interleaved 18 / Type B protocol if the goal is ACT vs CLARIFY agreement.
3. If a human substrate is still required, treat MultiWOZ as **copy-from and shallow interrupt** only, or look at a **different** already-audited corpus (not a new large download) that is actually long-horizon — LongMemEval was already rejected as glue.
4. **Memory construction** (how SYSTEM/USER turns become loops vs new tasks) is the blocker, not TAU/DELTA. Any change needs explicit approval after this report.
5. No Vertex until a **non-WOZ** conversation actually shows deep return.

---

## Most important research answer

**Naturally occurring MultiWOZ 2.2 test-shard dialogue does not contain enough genuine return/interleaving to make ContextFlow’s memory-management abstraction look useful at product scale.**

It contains a **handful** of interrupts, named recovers, one correction, and copy-from days/areas. Those are worth **mechanism contact**, not a new claim, and not infrastructure spend.
