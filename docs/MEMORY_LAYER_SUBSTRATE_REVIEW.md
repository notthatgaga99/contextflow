# Memory-layer substrate review

**Date:** 2026-08-28  
**Status:** design review only. No code, no download, no Vertex, no `app/` changes, no commit/push.  
**Constraint:** do not scale MultiWOZ; do not manufacture `A→B→C→D→A`; do not build an extractor.

This document answers whether ContextFlow can sit **on top of** an existing conversation/memory representation, and whether any **already local** conversation data can support a heterogeneous-return demonstration.

---

## 1. Product hypothesis

ContextFlow is **not** the agent’s memory.

An ordinary long session accumulates history (and, in a product, durable task records or extracted memories). The user maintains several **unrelated** unfinished intentions. They switch abruptly and later point with underspecified language (`black or navy?`, `still getting that 401`, `what did we decide about the experiment?`, `fix that`).

ContextFlow’s job is to **manage the working set** of that memory:

1. which intention/workstream is being addressed,
2. which open loop / referent is meant,
3. whether evidence is strong enough to **ACT** or the system should **CLARIFY**,
4. which **compact answer context** to reconstruct — without replaying the full transcript.

The PoC already showed this **control loop** when **task cards were supplied**. MultiWOZ showed that **raw turns do not automatically become those cards**. The product thesis therefore depends on a **memory construction** layer (or an existing store) **under** ContextFlow, not on retuning TAU/DELTA/HYST.

**Hypothesis to keep:** ContextFlow is a **memory-management / resolution layer**, not a memory store.

---

## 2. Why MultiWOZ is insufficient

`docs/MULTIWOZ_TWO_STAGE_REPORT.md` is the evidence. Do not reopen shards.

- Related **tourist** domains, sampled goals, mostly `A → B` concatenation.
- This test slice: **zero** 4+ DST-domain dialogues; genuine returns are **handfuls**, not a distribution.
- Replay without DST as memory collapsed history into **one mixed card** plus SYSTEM loops. That is a **construction** failure, not a gate-threshold failure.
- It cannot support the demo story (JWT ↔ dress ↔ paper ↔ trip).

MultiWOZ remains useful only as a **negative result**: WOZ multi-domain ≠ heterogeneous personal+work interleaving.

---

## 3. Candidate real-conversation substrates already available

Only what is **already on disk or already audited without a new download**.

| Source | Where | Coherent one-user session? | Human-authored? | Unrelated intentions in one session? | Returns? | 4+ intentions? | Long enough that replay matters? | License / provenance | Leak-safe replay? |
|---|---|---|---|---|---|---|---|---|---|
| **MultiWOZ 2.2 test shard** | `data/multiwoz/dialogues_001.json` | Yes (WOZ) | Human–wizard, **goal-scripted** | No (same ontology) | Rare, shallow | **No** in this file | Short (~10–20 turns) | MIT | Yes if wizard-at-target held out |
| **LongMemEval-S cleaned** | `data/longmemeval/longmemeval_s_cleaned.json` | **No** | Mix of simulated persona + **ShareGPT/UltraChat glue** | Heterogeneity is **compilation** | Across **stranger** sessions | Fake | Long haystack | MIT | Wrong unit (post-hoc QA); fillers leak other people |
| **LongMemEval oracle** | `data/longmemeval/longmemeval_oracle.json` | Per **evidence session**, yes-ish | **LLM-simulated** persona chats, not organic logs | Mild (car vs move vs concert — still “life”) | Occasional “going back to…” | Rare in one session | Medium (med ~23 turns / instance) | MIT | Hold out LME `question`/`answer`; do not use as CF gold |
| **Synthetic interleaved 5** | `eval/interleaved_corpus/` | Yes | **No** (`human_behavior: false`) | **Yes** (S03/S04 match the demo story) | **Yes** (authored) | **Yes** (S04) | Designed to | Internal research | Yes; we wrote the future turns |
| **Interleaved 18 packet** | `docs/annotation_pilot/interleaved_18/` | Yes | **No** (authored probes) | Yes | Yes | Yes in S03–S05 | Probe-sized | Internal | Yes |
| **MUDiC** | Audited, **not downloaded** | Group Telegram + bot | Human–agent | Off-topic vs **one** scheduling task | Off-topic then return | No | Small N (~12 user turns) | CC BY 4.0 | Would need download — **out of scope this step** |
| **MultiDoGO** | Audited, not downloaded | **Per-domain files** | Human–human | **Not in one chat** | Same-domain correction | No | — | CDLA | Stitching would **manufacture** sessions |
| **SGD** | Audited, not downloaded | In-dialogue multi-API | Hybrid simulator + paraphrase | Related services | Slot transfer | Possible across APIs | Medium | CC BY-SA | Not local; still not JWT+dress |
| **STAR** | Audited, not downloaded | Typically **one schema** | Human–human | Weak | Weak | No | — | MIT | Not local |
| **LMSYS / raw ShareGPT dumps** | Previously rejected | No | Human, but **not** one product user | Compilation | No | Fake | Long | PII/license | Unsuitable |
| **Private / Ericsson / Cursor chats** | **Not in this repo** | Would be, if exported as one thread | Would be | Unknown until inspect | Unknown | Unknown | Possibly | Must be consented | Only if the owner supplies them |

**Local inventory does not contain 10–20 ordinary long human sessions with unrelated work+life returns.** Pretending otherwise would manufacture the substrate.

Ten-question grid (honest):

1. **One session:** MultiWOZ yes; LME-S no; LME oracle per evidence session; synthetic yes.  
2. **Human vs glued:** MultiWOZ WOZ-human; LME-S glued; LME oracle simulated; synthetic authored.  
3. **Multiple unrelated intentions:** only synthetic (local) and (weakly) LME oracle life-adjacent.  
4. **Returns:** MultiWOZ almost none; LME oracle some named “going back”; synthetic designed.  
5. **Interrupt / correction / deixis:** MultiWOZ sparse; LME oracle has a few corrections (`I meant FreshMart`); synthetic 18 is built for this.  
6. **4+ intentions:** not MultiWOZ this shard; not honestly LME-S; synthetic S04 yes.  
7. **Target turns resuming earlier intention:** cannot fill 20–30 **human** targets locally without using authored or simulated text.  
8. **History long enough:** LME-S is long but **wrong**; MultiWOZ too short; synthetic S04 is the local “long return” **story**.  
9. **License:** MultiWOZ/LME MIT; synthetic internal; do not ingest LMSYS.  
10. **No leak:** always hold out the turn after the target; never use LME official `answer` as the CF bind.

---

## 4. Which substrate best matches heterogeneous human sessions?

**None of the local human/public files match the product session** (debug ↔ clothing ↔ paper ↔ travel, then `navy` / `401` / `the experiment`).

Ranked **for the demo story**, not for “we didn’t write it”:

1. **Synthetic S03 / S04 / interleaved 18** — only local match for abrupt **unrelated** returns. Label them as **authored demonstration transcripts**, not organic logs.  
2. **LongMemEval oracle evidence sessions** — licensed, not written as CF probes; **same-life** resumptions and a few corrections; **not** the killer heterogeneous demo; not a drop-in 10–20 replay set.  
3. **MultiWOZ** — **reject** for this claim (already measured).  
4. **LME-S** — **reject** as one user.  
5. **A consented export of one real agent/chat session** (not in repo) — the only path to a **true** ordinary-human demo. That is Option **C** if the export includes or can sit beside a memory store.

---

## 5. Evidence of genuine topic switching / returns

| Substrate | What is actually there |
|---|---|
| MultiWOZ shard | 1 interrupt, 2 named recovers, 1 hotel correction, copy-from days/areas; **224** sequential domain starts. Documented in the two-stage report. |
| LME-S | Adjacent-session “switches” are **ShareGPT hops**. Already documented; do not re-mine. |
| LME oracle | Sparse in-stream: `going back to Rachel’s team`, Holiday Market, Denver concert, `I meant FreshMart`, `125 stars not 400`, Juan Tue vs Thu. Regex: `fix that` occurs as **new** faucet DIY, not a pointer. See `eval/longmemeval/CANDIDATE_TURNS.md` (not gold). |
| Synthetic S03–S05 | Technical → clothing → technical; work → travel → debug → shopping; ambiguous `that` / `the other one`. **Designed**, not discovered. |

There is **no** local human corpus in which we counted 10–20 sessions with 4+ concurrent unfinished unrelated intentions.

---

## 6. Proposed 10–20 session replay (design only — not implemented)

**Do not fill this with MultiWOZ IDs or LME-S haystacks.**

**If the next approved substrate is a real memory-backed user log (Option C):**

- Take **10–20 sessions** (or one long session sliced into inspectable windows) from **one** consenting user.
- Per session record: turn count, distinct intentions (human-described, **not** CF ids), switches, returns, max return distance, concurrent unfinished (if inferable), deictic/correction counts, candidate targets.
- Manually inspect **20–30 target user turns**.
- Classify only: `RETURN | INTERRUPTION | CORRECTION | DEIXIS | COPY-FROM | NEW INTENTION | AMBIGUOUS/CLARIFY | NOT USEFUL`.
- **No** `gold_task_id` / `gold_referent_id` invented as ContextFlow truth.

**If we must stay inside this repo until a real log exists:**

| Set | n | Role | Honest label |
|---|---|---|---|
| Interleaved corpus S01–S05 | 5 | Only local 4+ domain **story** | Synthetic |
| Interleaved 18 probes | 18 **turns**, not 18 sessions | Target inspection packet | Synthetic; humans not yet labeled |
| LME oracle “human subset” | at most **~12 turns** across **~10 instances** | Optional personal-domain flavor | Simulated persona; not JWT+dress |

That is **not** “10–20 real conversations.” It is the **maximum honest local replay design**. Padding to 20 with MultiWOZ or S fillers would violate the brief.

Mechanism test (when approved, still no Vertex): full transcript vs recency vs Jaccard vs **store cards as-is** vs ContextFlow **on those cards**. Answer generation on **3–5** targets only. Local Ollama. Not in this step.

---

## 7. Memory construction vs resolution (three layers)

Keep these separate in every later experiment:

```
RAW CONVERSATION
        ↓
MEMORY CONSTRUCTION     ← production gap (PoC skipped this; MultiWOZ exposed it)
        ↓
  Task A + loops
  Task B + loops
  ...
        ↓
CONTEXTFLOW RESOLUTION  ← frozen PoC (proposal, clocks, gate, compiler)
        ↓
ANSWER CONTEXT
        ↓
hosted / local LLM
```

**PoC:** construction is **external** (scenario registries, demo `NEW_CARDS`, judge script). Resolution is what was measured.

**MultiWOZ eval harness:** construction was “NEW from utterance + append SYSTEM to active.” Result: **T1 absorbs the session**. Resolution never got a clean A/B/C/D index.

**Product:** do not pretend `Engine._default_new_task` is a memory system. Do not retune the gate to compensate.

---

## 8. Can an existing memory representation sit under ContextFlow? (A / B / C)

| Option | Meaning | Prefer? | Local reality |
|---|---|---|---|
| **A** | Structured conversation/task memory **already in the dataset** (DST frames, LME session ids, schema states) → CF | Only if that structure **is** the product’s memory | MultiWOZ DST must **not** be CF memory (already decided). LME session ids are a store of **chats**, not one user’s open loops. |
| **B** | Conversation → **lightweight extractor** → CF cards | Last resort | **Do not build now.** Would be a second research object (segmentation + naming). |
| **C** | Conversation → **existing memory system** → CF | **Yes** | **Nothing in-repo.** Candidates later (not to implement): agent memory APIs (Letta/MemGPT-style blocks), product “memories,” issue/task trackers, Cursor/chat export **plus** whatever the host already stores as threads. CF consumes `open_tasks` / loops / mention clocks **or maps onto them**. |

**Preference: C.** ContextFlow should **read** candidate workstreams from a replaceable `MemoryProvider` (already sketched in `docs/PRODUCTION_ROADMAP.md`). The PoC `InMemoryRegistry` is a **stub** of that provider, not a durable store.

Until C exists in data, the **smallest honest demo** is: **hand-maintained cards** (current PoC) or **synthetic session + authored cards**, labeled as such — **not** “we extracted MultiWOZ.”

---

## 9. Smallest convincing real-conversation demo

**Ideal (not available locally):** one consented session that actually contains work + a personal thread + a third intention, with an abrupt return (`navy` / `401` / `the paper`) after unrelated talk. Show:

- left: full messy transcript,
- right: CF working set (A,B,C,…), foreground referent, compact context,
- killer turn: underspecified return; LLM proposal may be wrong; gate ACT/CLARIFY; compact context is the **point**, not zero errors.

**Smallest demo we can stage without new downloads or production work:**

- Use **S03 or S04** (or one interleaved-18 killer turn) **and say they are authored**.
- Cards come from the **session’s declared workstreams** (Option A on **our** structure, or C if we treat that JSON as a fake memory store).
- Do **not** call this a human-log result.

**Do not** use MultiWOZ or LME-S as that demo.

**Do not** run the 5-condition llama marathon again on MultiWOZ.

---

## 10. What production architecture would eventually need

Conceptual only — **no Cloud Run, Firestore, or vectors in this step.**

```
durable conversation / task / memory store     (replaceable; Option C)
        ↓  candidates: tasks, loops, texts, clocks if the store has them
ContextFlow resolution                         (existing engine idea)
        ↓  selected task + referent + ACT|CLARIFY
compiler                                       (compact answer context)
        ↓
hosted LLM
        ↓
observability: decision, margin, clarify, context size
```

Eventually: persist registry fields (`active_task_id`, mention clocks) **or** derive clocks from the store’s timestamps. Map store records → `Task` / `TaskAnchor` **without** changing gate math. Observability on GCP later.

**Not needed to prove the thesis:** a ContextFlow-owned vector DB or a new ontology.

**Needed before a human-log demo:** a **source of cards** that is not “append every turn to T1.”

---

## 11. What must remain unproven

- That ordinary **human** traffic contains enough deep heterogeneous returns (we **do not** have that corpus locally).
- That an extractor (B) can build cards good enough for the gate.
- That CF **beats** recency/similarity on real logs (no such experiment this step).
- Production accuracy, token savings, Vertex quality, RAG replacement.
- That MultiWOZ or LongMemEval-S validates the product question.
- That `apply_update` / NEW-from-utterance is a memory architecture.

---

## Architecture decision (explicit)

**Is ContextFlow a memory store, or a memory-management/resolution layer on an existing store?**

**The second.**

| Layer | Owns |
|---|---|
| **Memory store** | Conversation history, task records, extracted memories, whatever the host already keeps |
| **ContextFlow** | Working-set selection, referent resolution, task switch vs return vs new, fail-closed **CLARIFY**, answer-context reconstruction |

The PoC is valid as a **resolution** demonstration **given cards**. MultiWOZ is valid as proof that **cards are not free**. The next approved experiment should **choose a store (C)** or **keep authored cards**, not search another dialogue benchmark.

---

## Stop

No implementation. No download. No Vertex. No production patch. Substrate and architecture wait for explicit approval before any replay code.
