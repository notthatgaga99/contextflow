# Context management — how it is built, and how to think about longer horizons

**Status:** Learning / design notes for the ContextFlow research POC.  
**Not a production spec. Not a claim of organic-chat accuracy.**  
**Companion claims freeze:** `docs/POC_FREEZE.md`, `docs/MEMORY_SEMANTICS.md`, `docs/ARCHITECTURE.md`.

This document captures:

1. Why / what / how of the **current** context-management implementation.  
2. How **model distillation** concepts map (and do not map) here.  
3. How Cursor- / Antigravity-style **agent harnesses** approach long context (public patterns).  
4. What we could whip up next for **last-N conversations**, **summaries**, and **moving work forward** — without retuning frozen routing.

---

## 1. One-sentence thesis

Models are soft proposers. The harness decides what is allowed into the answer prompt. ContextFlow’s bet is **structured workstream memory + ACT/CLARIFY routing + referent-bound working-set reconstruction (RB-WSR)** — not transcript dump, not RAG top-k, and not weight distillation.

### Honest completion vs the 7-stage spine (blunt)

| Stage | Done? | Grade | Notes |
|---|---|---|---|
| 1 Observe | Yes | B | Message + optional extract history; no rich tool/env ingest |
| 2 Write | Partial | B | Assert/supersede/retract solid; focus attach + known-slot enforce (ttl/aud/builder/mem/color) |
| 3 Retrieve | Partial | B | Open cards only — correct for wedge; no cold/global memory yet |
| 4 Select | **Strong** | A− | Gate + referent + fail-closed CLARIFY is the real product |
| 5 Assemble | Good | B+ | RB-WSR + compact; now with per-kind caps / recent-first ranking |
| 6 Generate | Thin | C | Answer-only; no tool loop |
| 7 Compact / H2 | **Yes** | B | Supersession + caps + rollup + last-N catalog (file/Firestore) + match suggest + opt-in import |

**Bottom line:** ~**55–65%** of a full industry context manager if you weight all stages equally; ~**80%+ of the wedge** (stages 4–5) if you grade what you set out to prove. Condensation across chats and industrial retrieve backends were the real gaps — not “the idea is wrong.”

### Gap-fill shipped (best-practice path)

| Piece | API / module | Practice |
|---|---|---|
| Per-kind condensation | `WorkingSetLimits` in `working_set.py` | Recent-first, slotted preferred, capped |
| Structured rollup | `GET …/rollup`, `app/memory/rollup.py` | From asserted memory, not transcript |
| Last-N catalog | `GET /catalog`, `POST …/archive`, `app/memory/catalog.py` | Hot index of rollups; `CF_CATALOG_LIMIT` (default 5) |
| Firestore catalog | `app/memory/firestore_catalog.py` | `CF_CATALOG_BACKEND=firestore` (default when memory is firestore) |
| Soft match suggest | `GET /catalog/match` | Lexical over blurbs/titles — **no** import side effects |
| Opt-in import | `POST …/import-rollup`, `app/memory/import_rollup.py` | Paused cards + Writer seeds; never auto-merge |
| Turn touch | after `POST /turn` | Catalog stays warm without polluting generate |

Still open vs industry: auth/tenancy, extract quality, tool loop, vector/graph cold memory as optional compose, explicit cross-hop merge law (A∪B).

---

## 2. Why this shape exists

Long multi-task chat fails less because the model cannot read, and more because the system does not know **which unfinished workstream** an underspecified utterance continues (`fix that`, `bash exit 4`, `the navy one`).

| Principle | Why |
|---|---|
| Separate propose vs decide | LLM guesses are soft; wrong ACT is worse than asking |
| Separate memory write vs answer | Answering must not invent durable state |
| Reconstruct, don’t dump | Weak models get distracted by sibling loops |
| Fail closed (CLARIFY) | Ambiguity → question, not silent misroute |
| Freeze routing knobs | Eval must not quietly retune TAU/DELTA and claim a win |

Authority map (`docs/ARCHITECTURE.md`):

| Role | Authority |
|---|---|
| Extractor | Propose `MemoryPatch` only |
| `MemoryWriter` | Only memory mutation path |
| Gate / referent / scorer | ACT vs CLARIFY and which workstream |
| `WorkingContextBuilder` | Project asserted items for selected task/referent |
| `ContextCompiler` | Compact package + render |
| `LLM.generate` | Answer only — must not write memory/clocks |

---

## 3. What is built today (layers)

```
User message
    → Engine.plan_turn          # route only: no registry writes, no answer
    → extract → MemoryWriter    # non-NEW: before execute; NEW: after card create
    → Engine.execute_plan       # clocks + package + generate
```

Code anchors:

| Area | Path |
|---|---|
| HTTP sequencing | `app/turn_pipeline.py` |
| Composition root | `app/engine.py` |
| Per-conversation isolation | `app/memory/sessions.py` (`ConversationStore`) |
| Extract / write | `app/memory/extractor.py`, `app/memory/writer.py` |
| Store / registry | `app/memory/store.py`, `app/memory/registry.py` (+ Firestore variants) |
| Propose / score / gate | `app/router/proposal.py`, `app/retrieval/scorer.py`, `app/router/gate.py` |
| Referent | `app/router/referent.py` |
| Post-gate rails | `app/router/topic_discern.py`, `app/router/topic_align.py` |
| Working set / compile | `app/context/working_set.py`, `app/context/compiler.py` |
| Frozen knobs | `app/config.py` |

**Isolation today:** one `Engine` + registry + `MemoryStore` per `conversation_id`. NEW CHAT = new id. There is **no cross-chat global memory** in the public demo path (`CF_MEMORY_BACKEND=memory` was process-local; Firestore path namespaces by conversation).

---

## 4. How a turn runs (implementation)

### 4.1 Pipeline order (`run_turn`)

- **Non-NEW:** `plan_turn` → extract/commit → `execute_plan`.  
  Routing plan is computed on **pre-turn** open cards; the answer package can see **this turn’s** newly asserted items.
- **NEW:** `plan_turn` → `execute_plan` (create card + answer) → extract with `focus_workstream_id` so patches land on the new card.

### 4.2 `plan_turn` (no side effects)

1. Retrieve open workstreams (`OpenWorkstreamRetriever`).  
2. Soft LLM propose → `_sanitize_proposal` (unknown task id → fail closed).  
3. `resolve_referent` (lexical / deictic / correction + clocks).  
4. `score_candidates` — on deictic/correction, `apply_llm=False` so soft confidence does not dominate “fix that”.  
5. Conflict detect → CLARIFY.  
6. Unambiguous referent route → `bind_task` (CONTINUE / SWITCH / RETURN; does **not** re-apply TAU/DELTA/HYST).  
7. Else `decide` with full gate policy.  
8. Optional `_maybe_align` (Lite topic discern or lexical) — **post-gate only**; frozen thresholds unchanged.

### 4.3 Scoring

For each open task:

```text
raw = W_LLM*conf + W_SIM*cos + W_REC*exp(-λ·Δt) + W_LOOP*loopHit
```

Plus a synthetic `__NEW__` candidate. Defaults: see `app/config.py` (`TAU=0.20`, `DELTA=0.08`, `HYST=0.05`, `COLD=3`, …).

`raw_margin = top_raw − runner_raw` is **discriminative evidence, not P(correct)**. PoC embeddings may be hash-seeded — not a semantic-RAG claim.

### 4.4 Gate (`decide`)

Order:

1. Explicit conflict → CLARIFY  
2. `top_raw < TAU` → CLARIFY  
3. Challenger barely beats active (`active_gap < HYST`) → stick CONTINUE  
4. `raw_margin < DELTA` → CLARIFY  
5. Else NEW / CONTINUE / SWITCH / RETURN (paused + cold → RETURN)

CLARIFY returns a question only — no package, no generate.

### 4.5 Execute

- **ACT:** `mark_active` / `record_mention` / `set_last_selected_referent` → `_make_package` → `generate(render(...))`.  
- **NEW:** create card (factory or default from utterance) → same package path.  
- Legacy `reg.apply_update` is a no-op; **MemoryWriter** is the production write path.

### 4.6 Working-set projection (`WorkingContextBuilder.project`)

After the gate selected `task` + `referent_id`:

- `excluded_workstreams` = other open titles (audit / UI; not sibling content in answer).  
- Take `store.asserted(task.id)` only.  
- Drop `uncertain`.  
- Referent filter: keep matching `referent_id` or workstream-scoped (`referent_id is None`).  
- Bucket by kind → decisions / constraints / facts / entities.  
- `recent_changes` = last 3 kind:text.

This is **selection**, not summarization.

### 4.7 Compiler modes

| Mode | Behavior |
|---|---|
| `REFERENT_COMPACT` (default split) | Selected open loop only via `_compact_or_fallback` |
| `FULL_TASK` | All loops on selected task (eval / fallback) |
| `MERGED_COMPACT` | Merged blob for probes |

Honest split:

- **`answer_text` / `render`:** selected task + loop + asserted fields + USER message (production).  
- **`decision_text`:** MESSAGE + **all open CARDS** + SELECTED — **grows with open-task count n**.

Do not claim “all context is mathematically minimal.”

### 4.8 Memory lifecycle (compression without a summarizer)

From `docs/MEMORY_SEMANTICS.md`:

- ASSERT → current.  
- Same `slot` → prior SUPERSEDED (append-only history).  
- RETRACT / ABANDON close without deleting audit rows.  
- Uncertain patches rejected at validate.

**CURRENT** in the working set is asserted-only; **HISTORY** remains queryable via `historical()`.

---

## 5. Distillation concepts — map carefully

### 5.1 Classical knowledge distillation

Teacher → student **training**: soft logits, feature hints, response traces, self-distillation, dataset distillation. The distilled object is usually **weights** (or a synthetic training set).

Cursor’s Composer self-summarization research is closer to this family (train the model to emit condensed context). Antigravity’s public “harness co-trained with Gemini” claim is also on the training/harness side.

### 5.2 What ContextFlow does today

**Runtime context distillation / RB-WSR**, not weight KD:

| Distillation idea | ContextFlow today |
|---|---|
| Soft teacher signal | LLM proposal is soft; gate hardens to ACT/CLARIFY |
| Student sees cleaned targets | Answer LLM gets compact asserted package |
| Drop distractors | Exclude other workstreams / wrong loops |
| Recoverable teacher trace | Superseded items / historical store (not in answer prompt) |
| Train student on teacher | **Not implemented** |

Allowed phrasing: *working-set reconstruction / context distillation (runtime)*.  
Avoid: *we distilled Gemini into Flash-Lite* (false for this POC).

### 5.3 Evidence that the harness helps weaker answer models

Controlled probes only (`eval/out/POC_RESULTS.md`, `docs/MODEL_REVIVE_PARITY.md`):

- Weak local model (qwen2.5:1.5b): FULL_TASK worse than REFERENT_COMPACT on wrong-loop interference.  
- Stronger 8b: compact is not always an accuracy win.  
- Routing scale: fail-closed wrong-ACT = 0 on MockLLM HIGH grid vs baselines that misroute earlier.  
- Revive parity: same compact package → Lite recovers needed state about as well as Flash on that slice — **packaging carried revive**.

---

## 6. How IDE agent harnesses manage context (public patterns)

Useful comparison while learning — different primary problem (coding trajectory + tools vs multi unfinished human threads).

| Pattern | Cursor (public) | Antigravity (public) | ContextFlow |
|---|---|---|---|
| Primary problem | Long tool trajectory + repo | Same + artifacts / browser / subagents | Interleaved unfinished workstreams |
| Static always-on | Short rules; point at files | Rules / skills / workflows | Frozen gate + package schema |
| Dynamic pull | Tool dumps → files; MCP catalogs; terminals; skills | Knowledge / artifacts / skills; `/context` | Open cards → project asserted memory |
| Compaction | Auto summarize near window full; `/summarize`; history recoverable as files | Checkpoint summaries; `/rewind`; `/btw` side questions | Structured reconstruct; not chat summarizer as primary |
| Fail when unsure | User / tools / hooks | Permissions; clear/fork | Deterministic CLARIFY |
| Cross-session | BDK `memory/journal.jsonl` (advisory) | Resume / knowledge surfaces | Per `conversation_id` only today |

**Shared lesson:** less static junk up front → better answers.  
**Your different failure mode:** wrong-thread ACT, not only token overflow. Summarization alone does not name which open loop is live.

---

## 7. Longer horizon: last-N conversations, summaries, moving forward

Tier A/B + opt-in import + soft match are **implemented**. Frozen routing (`gate.py`, `referent.py`, `scorer.py`, `config.py`, `MemoryWriter` contracts) stays untouched.

### 7.1 What exists today vs what “last 5 convos” means

| Layer | Today | Status |
|---|---|---|
| Within one chat | Workstream cards + asserted/superseded memory | Done (revive unit) |
| Across chats | User-level catalog of rollups; opt-in import as paused | Done (file + Firestore) |
| Soft suggest | `GET /catalog/match` — summaries only | Done (no auto-merge) |
| Process | File JSON or Firestore `cf_catalog/{user}/entries/{cid}` | Done |

“Last 5” is a **catalog + retention + optional cross-chat recall** problem sitting *above* RB-WSR, not a replacement for it.

### 7.2 Three horizons to keep separate

Always name which horizon you mean — mixing them causes bad designs.

```text
H0  Turn          — this utterance
H1  Conversation  — one conversation_id (workstreams + memory)   ← ContextFlow today
H2  User / device — last N conversations + rollup catalog        ← shipped (opt-in)
H3  Org / corpus  — shared knowledge, RAG over docs               ← out of PoC scope
```

IDE harnesses mostly optimize **H0–H1 along one coding goal** (plus file tools).  
Cross-chat “last 5” is **H2**.

### 7.3 What you can whip up (incremental, realistic)

Ordered from smallest product step to research-heavy.

#### Tier A — Catalog only (no cross-chat injection)

Store metadata for the last N conversations:

- `conversation_id`, title (first user line or LLM title), `updated_at`, open workstream titles, turn count, optional badge of last transition.  
- UI: list last 5; click resumes that `conversation_id` (Firestore registry + store already know how to namespace).  
- Retention: keep 5 hot; archive or delete older.

**Does not** change routing or answer packages. Pure product UX on top of `ConversationStore`.

#### Tier B — End-of-conversation rollup (structured, not prose dump)

When a chat goes idle or user hits “archive”:

1. For each open workstream, emit a **rollup card**:
   - `title`, `goal`, `status`, top asserted decisions/constraints/facts (capped), `open_loops` short list, `last_active_turn`.  
2. Persist `ConversationRollup` JSON keyed by `user_id` + `conversation_id`.  
3. Keep raw store for the hot N; rollup is the cold summary.

Prefer **structured rollup from asserted memory** over “summarize the whole transcript” — same philosophy as RB-WSR: selection beats lossy chat summary when you already have slots.

Optional: one short **LLM prose blurb** for UI (“Azure CI + peplum hosting + Meghalaya”) derived *from the rollup*, not from full logs.

#### Tier C — Soft cross-chat recall (opt-in, fail closed)

When the user starts a **new** chat and says something that matches a prior rollup:

- Retrieve top-k rollups (embedding or lexical over titles + facts).  
- **Do not** auto-merge into active registry without consent.  
- Offer: “Continue Azure pipeline from chat #3?” → on accept, **import** selected workstream(s) into the new conversation as paused cards + asserted seeds.  
- Gate remains in-conversation; imported cards become normal open-task candidates.

This preserves fail-closed instincts: cross-chat is a **explicit RETURN-from-archive**, not silent contamination.

#### Tier D — Sliding window inside one long chat (IDE-like)

If a single conversation grows huge:

| Mechanism | Role |
|---|---|
| Keep last K turns verbatim for extractor | Local coherence |
| Checkpoint summary of older turns | Like Antigravity checkpoints / Cursor summarize |
| Never let checkpoint replace registry | Cards + asserted memory remain source of truth |
| Working set still from RB-WSR | Summaries feed extract/UI, not sibling dump into generate |

Rule of thumb: **summaries are for the human and for extract proposals; working set for generate stays asserted+selected.**

### 7.4 How to summarise without fighting the architecture

Bad pattern:

```text
full transcript → LLM summary → stuff summary into every generate()
```

That reintroduces sibling interference and undoes the PoC.

Better pattern:

```text
turns → extract → Writer (assert/supersede)
                 → registry clocks
                 ↓
          asserted memory + cards          = durable truth
                 ↓
     on archive: structured rollup         = H2 index
                 ↓
     optional prose title/blurb for UI
                 ↓
     generate() still uses WorkingContextBuilder + Compiler
```

| Summarize what | Method | Inject into generate? |
|---|---|---|
| Slot conflicts (navy vs black) | Supersession (already) | CURRENT only |
| Selected loop facts | Working-set project (already) | Yes, for selected task |
| Whole chat for UI list | Structured rollup ± short blurb | No |
| Older turns in mega-chat | Checkpoint summary file | Only via extract, or on-demand tool |
| Last 5 chats | Catalog + rollups | Only after user accepts import |

### 7.5 Retention policy sketch (“last 5”)

Example policy (product choice, not frozen):

| State | Keep | Drop |
|---|---|---|
| Hot | Full registry + memory for 5 most recently updated `conversation_id`s | — |
| Warm | Rollup JSON only for next M | Full item rows optional |
| Cold | Tombstone id + title | Delete payloads |

Ops notes:

- In-memory backend cannot honor “last 5” across Cloud Run scales without sticky session or external store.  
- Firestore (or any durable DB) is the natural home for catalog + rollups.  
- Demo with `min-instances=0` already taught: process memory ≠ user memory.

### 7.6 Moving things further (research ladder)

Stay claim-honest at each rung:

1. **Tier A catalog** — ship UX; no accuracy claim.  
2. **Tier B structured rollup** — measure rollup completeness vs asserted store (package-usability style metrics).  
3. **Tier C opt-in import** — measure wrong-import rate; default CLARIFY / ask.  
4. **True KD (optional later)** — teacher labels gold ACT|CLARIFY + gold working sets; train tiny router or student answerer on compact packages only. That is *weight* distillation sitting on the harness — new phase, new freeze.  
5. **IDE-style dynamic discovery** — store large tool/transcript blobs as files/objects; agent/extract pulls on demand (Cursor lesson) without bloating `render()`.

### 7.7 Decision checklist (when you design H2)

Ask before building:

1. Is this **within** one `conversation_id` or **across** chats?  
2. Is the source of truth still **asserted memory + registry**, or are we inventing a second prompt brain?  
3. On conflict between rollup and live card, who wins? (Live asserted should win.)  
4. Does cross-chat recall **auto-ACT** or **ask**? (Prefer ask.)  
5. What is retained at N=5 — full store or rollup only?  
6. Does any of this require unfreezing gate thresholds? (Default: no.)

---

## 8. Quintessential context-manager flow (industry spine)

Use this as the shared map. Every serious system walks roughly these **seven stages**. Products differ in *how* they implement each stage — not in inventing a wholly different universe.

```text
1. OBSERVE   → ingest user / tool / env events
2. WRITE     → decide what becomes durable memory
3. RETRIEVE  → pull candidates for this turn
4. SELECT    → choose what is allowed to matter (rank / gate / budget)
5. ASSEMBLE  → pack prompt (system + memory + history + user)
6. GENERATE  → answer and/or tool loop
7. COMPACT   → summarize / tier / retain so the horizon survives
```

Two loops:

- **Write loop:** episode → extract/update → store.  
- **Read loop:** query → retrieve → pack → generate (+ compact when full).

### 8.1 Industry default vs ContextFlow on the same spine

| Stage | Industry default | ContextFlow today |
|---|---|---|
| 1 Observe | Message (+ tools) | Message (+ history to extractor) |
| 2 Write | Facts / vectors / graphs / agent-edited blocks | Extractor → Writer assert/supersede (workstream + slot) |
| 3 Retrieve | Top-k global memory | Open **workstream cards** only |
| 4 Select | Soft rerank / token budget | Referent + score + **ACT\|CLARIFY gate** |
| 5 Assemble | Stuff chunks + recent transcript | **RB-WSR** → `REFERENT_COMPACT` + USER |
| 6 Generate | Answer / tools | Answer from package (tools out of PoC) |
| 7 Compact | Chat summarize / archival tiers / last-N | In-chat supersession; **no cross-chat last-N yet** |

**Punchline:** industry often does *retrieve → stuff → hope*. You do *bind workstream/referent → reconstruct asserted set → generate, else CLARIFY*. Same spine; harder stages 4–5.

### 8.2 How major families specialize the spine

| Family | Emphasizes | Weak on your problem |
|---|---|---|
| Coding harness (Cursor / Antigravity) | 1, 6, 7 + dynamic file pull | Multi unfinished human threads; hard CLARIFY |
| Vector memory (Mem0-like) | 2–3 cross-session facts | Which of many **open** tasks to ACT on |
| Temporal graph (Zep-like) | 2–3 relations + validity time | Live foregrounding / deixis policy |
| Agent-edited blocks (Letta-like) | 2 via model-controlled tools | Deterministic audit if the model mismanages memory |
| Naive chat | 5 = sliding window | Everything under interference |

### 8.3 Expanding scope without losing the wedge

“Increase scope” = cover more of stages 1–7 and horizons H1→H2→H3, while **Select stays fail-closed**.

| Expand | Stages | Better | Trap |
|---|---|---|---|
| Last-N catalog | 7 | Resume real conversations | Auto-stuff all five into generate |
| Structured rollup | 7 | Cold index from asserted state | Transcript summary as sole truth |
| Opt-in import | 3–4 | Cross-chat RETURN with consent | Silent cross-chat ACT |
| Dynamic pull | 3, 5 | Cursor-like on-demand blobs | Static dump of every rollup |
| Compose cold memory | 2–3 | Mem0/Zep for prefs/docs | Top-k overrides the gate |
| Tool loop later | 6 | Tools **after** bind | Tools on multi-thread mush |
| Industrial eval | quality | Wrong-ACT / revive vs *n* | Vanity LLM-judge only |

**Rule for “make it better”:** strengthen Write and Compact; optionally enrich Retrieve; never soften Select into retrieve-and-stuff.

Canvas companion: workspace `canvases/quintessential-context-manager.canvas.tsx`.

---

## 9. Competitive positioning: ContextFlow vs Cursor-class harnesses

### 9.1 Do not compete on Cursor’s battlefield

Cursor (and Antigravity-class IDEs) optimize a **coding agent trajectory**:

- Huge tool surface (edit, search, shell, MCP, browser)
- Dynamic context discovery (files over static dumps)
- Window compaction / summarization / co-trained models
- Product polish at massive scale

Trying to “beat Cursor at Cursor” is the wrong race. They win on IDE integration, model co-training, and repo tooling. Your POC is not an IDE harness.

### 9.2 Compete on the wedge Cursor does not own

Your distinctive problem:

> Many **unfinished human workstreams** in one conversation; underspecified returns; wrong-thread ACT is worse than asking.

Cursor’s compaction answers “window full.” Your gate answers “which open loop is live?” Those stack; they do not substitute.

| Capability | Cursor-class | Mem0 / Zep / Letta-class | ContextFlow wedge |
|---|---|---|---|
| Repo + tools | Strong | Weak / N/A | Out of scope |
| Token compaction | Strong | Partial | Secondary |
| User-fact memory | Light / product-specific | Strong (vector/graph) | Partial (asserted slots) |
| Temporal KG | Rare | Zep/Graphiti strong | Not built |
| **Multi-open-task ACT/CLARIFY** | Weak / implicit | Usually retrieve-then-stuff | **Core product** |
| **Referent-bound working set** | Rare as first-class | Rare | **Core product** |
| Fail-closed under ambiguity | Soft (user steers) | Soft (top-k) | **Hard gate** |
| Auditable CURRENT vs HISTORY | Varies | Varies | Explicit supersession |

Industry peers for *your* category are closer to **agent memory frameworks** (Mem0, Zep/Graphiti, Letta) and **multi-session assistants**, not Cursor itself. Steal Cursor *patterns* (dynamic pull, recoverable history, side-channel questions); do not copy Cursor’s *mission*.

### 9.3 Can yours still work around better?

Yes — **on interleaved unfinished work** — if you stay disciplined:

1. Keep RB-WSR + fail-closed gate as the spine.  
2. Import IDE lessons as **supporting machinery** (catalog, rollups, on-demand files), not as “summarize everything into generate.”  
3. Measure the metric Cursor does not lead on: **wrong-ACT / wrong-thread rate under rising open-task count**, plus package sufficiency after revive.

Where they will still beat you forever: coding UX, tool richness, frontier co-training. That is fine.

### 9.4 What “industry standard / competition-worthy” means here

Not “feature parity with Cursor.” A credible bar:

| Bar | Meaning | Status today |
|---|---|---|
| Clear thesis | Control plane for multi-workstream chat | Have |
| Frozen core + tests | Reproducible routing/memory invariants | Have (PoC) |
| Durable isolation | Per-user / per-conversation persistence | Partial (Firestore path; demo was in-memory) |
| Eval that matches the claim | Interference / revive / wrong-ACT, not vanity LLM-judge only | Partial (controlled; need organic holdout later) |
| Cross-session product | Last-N catalog + opt-in import | Design only |
| Safety / tenancy | Auth, deletion, no cross-tenant bleed | Weak on public demo |
| Cost story | Cheap answer model + compact package | Demonstrated directionally |
| Honest claims | No overclaim vs organic chat | Documented — keep it |

Competition-worthy packaging:

- **SDK / middleware**: `run_turn(message, conversation_id) → {transition, package, answer}` pluggable behind any chat UI.  
- **Bench story**: publish an interleaved-workstream suite (your ten-ws / revive probes generalized) where retrieve-and-stuff baselines fail earlier than CF.  
- **Integrations**: optional Mem0/Zep as *cold fact store*; CF remains the *live workstream router* (compose, don’t clone).  
- **UI contract**: badges NEW/CONTINUE/SWITCH/RETURN/CLARIFY + CURRENT/HISTORY — judges already understood this.

### 9.5 Improvement roadmap that raises the bar (without becoming Cursor)

Phase-shaped; do not unfreeze gate lightly.

1. **Hardening** — durable backend default, auth on non-demo, deletion/export, conversation catalog (Tier A).  
2. **Horizon H2** — structured rollups + opt-in import (Tiers B/C in §7); never auto-dump last-5 into generate.  
3. **Dynamic discovery** — large blobs as objects/files; extract/UI pull on demand (Cursor lesson).  
4. **Eval industrialization** — fixed interleaved corpus + wrong-ACT / revive metrics; optional human labels; separate organic pilot.  
5. **Optional composition** — vector/graph memory for H3 prefs/docs; CF owns H1 open-task binding.  
6. **Optional KD later** — train tiny router / student on gold packages; new freeze phase.

### 9.6 Positioning one-liner (external)

> ContextFlow is a **fail-closed working-context layer for interleaved tasks** — it decides which unfinished workstream is live and reconstructs a compact asserted package for any answer model. Coding agents optimize tools and windows; memory DBs optimize recall; we optimize **referent binding under interference**.

---

## 10. Claim hygiene

**Allowed**

- Working-context control layer for interleaved tasks.  
- Fail-closed CLARIFY under ambiguity.  
- Compact asserted packages reduce wrong-loop interference on weak answer models (controlled probes).  
- Cross-chat last-N is a natural product layer above per-conversation RB-WSR (design only until built).

**Forbidden**

- Solved lifelong / organic memory.  
- Guaranteed token-savings percentage.  
- LLM confidence = P(correct).  
- “Harness makes every model smarter on every task.”  
- Equating runtime working-set reconstruction with classical weight distillation.
- “Better than Cursor” as a blanket product claim.

---

## 11. Related docs

| Doc | Role |
|---|---|
| `docs/ARCHITECTURE.md` | Authority split |
| `docs/MEMORY_SEMANTICS.md` | Writer ops / working-set rules |
| `docs/POC_FREEZE.md` | Frozen algorithm and claim bounds |
| `docs/WORKSTREAM_DURABILITY.md` | Firestore durability phases |
| `docs/MODEL_REVIVE_PARITY.md` | Lite vs Flash on same package |
| `docs/HANDOVER_HLD_LLD.md` | RB-WSR naming / HLD |
| `eval/out/POC_RESULTS.md` | Measured tables |

---

## 12. Bottom line

**Today:** per-conversation structured state, deterministic gate, referent-bound working set into the answer model. That is how ContextFlow “distills” multi-thread chat into something a smaller model can use safely.

**Next (when you choose to build):** treat **last 5 conversations** as a catalog + structured rollup + opt-in import problem at horizon H2 — summarise from **asserted memory**, keep RB-WSR as the generate path, and fail closed across chats the same way the gate fails closed within a chat.

**Competition:** do not out-Cursor Cursor. Be the industry-standard **fail-closed workstream binder** that coding harnesses and memory DBs can sit beside — measured on wrong-thread rate under interference, shipped as durable middleware with honest claims.
