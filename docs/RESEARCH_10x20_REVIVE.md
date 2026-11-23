# Research target: 10 workstreams × ≥20 turns + revive

**Status:** R0–R3 local MockLLM proven. Next research: real extract under density (optional cloud answer).  
**Does not unfreeze** gate / referent / scorer / config / MemoryWriter contracts.

## Where we stand (honor the work)

| Claim | Evidence | Honest limit |
|---|---|---|
| Working-memory **switch** (bind → L1 only) | MemoryPort + compact-notation + product path | Mock / in-process; Mem0/Zep adapters not required yet |
| **10×20 density + revive** | `fixture_10x20` + probes; task/policy/WC **10/10**, wrong_act=0 | Controlled adversarial fixture — not natural chat |
| Fail-closed CLARIFY under ambiguity | Referent lexical_tie dig; gate untouched | Cue quality still matters; density ≠ “always ACT” |
| **Condensation** (L1 ≪ transcript) | R2: ~301 CF tokens vs ~7000 full (~23×); caps never dropped needed_state | Scripted extract; real LLM extract noise unproven at 10×20 |
| Hierarchy L0–L6 story | Docs + rollup/catalog + **R3 harness 4/4** | Real extract under density; Mem0/Zep port still optional |
| Memory planes (STM / LTM / procedural / relevant) | `MemoryManager` + `docs/MEMORY_MANAGEMENT.md` + tests | Natural-chat extract→procedure still thin; ARCHIVE opt-in only |

**Do not overclaim:** MockLLM 10×20 ≠ production accuracy. Free GCP via alt Gmail is out of plan.

Related: `docs/MEMORY_MANAGEMENT.md`, `docs/VERTEX_10x20_MODEL_SWEEP.md`.

## Goal (your words)

Keep **10 open hops (workstreams)** alive; deepen each to **~20 turns** of interleaved conversation; prove **revive** (return to an older hop with sufficient working context, no sibling contamination).

Rough scale: \(10 \times 20 = 200\) user turns (vs today’s fixture **10 ws × ~5 turns avg = 52 turns**).

## GCP / “free” (decision for this research)

| Option | Verdict |
|---|---|
| **Legitimate first Free Trial** on your own Gmail (e.g. never paid GCP/Maps/Firebase; never signed up for Free Trial before) | **OK.** Official: once per eligible user; $300 / 90 days; card for identity; not charged unless you upgrade to paid. Use hard budgets + don’t auto-upgrade blindly. |
| Second Free Trial via another Gmail to dodge “already used trial” | **Do not plan on this.** Against program intent; identity/payment checks often block it. |
| Same account reopen after trial spent/expired without upgrade | **Paid** path (or Always Free tier only), not a new $300. |
| **Local MockLLM + Ollama extract / pytest** | **Primary science path.** Zero cloud cost; does not wait on billing. |
| Vertex answer/extract slice on a real trial | **Optional packaging / R4** once eligibility is honest and budgets are set. |

**Eligibility (Google’s docs):** never a paying GCP/Maps/Firebase user **and** never previously signed up for Free Trial.  
**Research does not depend on cloud.** Trial is optional acceleration for live models — not permission to retune the gate.

## Baseline today (`eval/ten_workstream`)

| Metric | Current |
|---|---|
| Open workstreams | 10 (A–J) |
| User turns | 52 |
| Turns per ws | Uneven (~3–8 typical; not 20) |
| Probes | Return / interference / WC sufficiency (controlled) |
| Answer model | Mock scripts (+ optional Vertex slice, 5 probes) |

This already proves the **shape** of multi-hop revive. It does **not** yet prove deep per-hop memory under 20-turn density.

## What “better hops” means (metrics)

Do not chase “200 turns ran.” Chase these:

1. **Persistence** — after many unrelated turns, expected card still in `open_tasks`.  
2. **Revive resolution** — RETURN/SWITCH to gold task (or honest CLARIFY).  
3. **Working-context sufficient** — required facts present; forbidden sibling state absent.  
4. **Supersession** — late corrections win; stale CURRENT absent.  
5. **Wrong-ACT rate** — must stay near fail-closed behavior as density grows.  
6. **Package size** — condensation caps hold under noisier extract over 20 turns/hop.

Layers already in `eval/ten_workstream/metrics.py` — extend probes, don’t invent vanity scores.

## Research phases (polish path)

### Phase R0 — Measure current hop depth (done conceptually)

Script: count `turns` grouped by `ws` in `fixture.json`. Confirm avg ≪ 20.

### Phase R1 — Design a **deep-hop** fixture (no gate retune)

Add `eval/ten_workstream/fixture_10x20.json` (or generate):

- Same 10 domains (keep adversarial overlap A/C/D 401).  
- Per workstream: ≥20 messages that **establish, correct, and reopen** loops.  
- Global schedule: **interleave** (never 20 straight turns on one ws — that doesn’t test revive).  
- Target pattern: for each hop, clusters of 2–4 turns, then long gap, then revive probe.

Probe set additions:

- One **late revive** per workstream after ≥N intervening turns.  
- At least one **correction supersession** per fashion/CI-style hop.  
- Keep evaluator-only gold; runtime-blind probe file.

### Phase R2 — Condensation stress ✅

With 20 turns/hop, extract noise grows. Validate:

- `WorkingSetLimits` still keep packages lean.  
- Rollup blurb + per-ws rollup remain usable for H2.  
- `working_context_sufficient` doesn’t collapse because caps dropped required slots — **tune caps via eval**, not gate thresholds.

**Run:** `python -m eval.ten_workstream.condensation_stress` → `eval/out/condensation_10x20.json`

| Metric | Result |
|---|---|
| Pass | **true** |
| Mean L1 items on revive probes | 5.9 (max 8; soft kind-cap sum 28) |
| Caps dropped needed_state | **never** |
| Mean CF tokens vs full history | **301 vs 7001 (~23× smaller)** |
| Store asserted after 200 turns | 59 (commits ≪ turns; abstain works) |
| Rollup | blurb ok; ~1088 tokens; open_count 10 |

### Phase R3 — Catalog / import revive ✅

**Harness:** `python -m eval.ten_workstream.catalog_revive`  
**Scenarios:** `eval/ten_workstream/scenarios_r3.json` (evaluator-only gold)  
**Out:** `eval/out/r3_catalog_revive.json`

| Scenario | What it proves | Control level |
|---|---|---|
| `r3_selective_import_revive` | 10×20 → catalog → import **A/B/E only** → local NEW interference → revive ACT + WC isolation | Selective import; remapped ids; sibling/local forbid lists |
| `r3_honest_clarify_overlap` | Import A+C; underspecified 401 → **CLARIFY** | Fail-closed is success — not forced ACT |
| `r3_catalog_last_n` | Last-N structured rollups only | Capacity invariant |
| `r3_paused_until_bind` | Imported cards paused; no active until bind | Opt-in L6→L4/L2 |

**Result (MockLLM):** scenarios **4/4**, wrong_act **0**. Gate untouched.

**Design rules (not restrictive, rooted in facts):**

1. Declarative scenarios — add cases without changing `app/`.  
2. Do not require perfect mid-trajectory routing on the source chat.  
3. ACT gold only when cues uniquely identify an imported hop.  
4. CLARIFY gold when overlap is intentional.  
5. Never auto-merge catalog into generate().

### Phase R4 — (Optional) Hosted answer slice

Only if free/paid cloud is consciously available: small revive probe slice on Flash-Lite, cost-capped. **Not** required to claim R1–R3.

### Real extract under density

| Backend | Useful | Abstain OK | Wrong WS | Revive-critical A/B/E | Est. USD |
|---|---|---|---|---|---|
| Ollama `llama3.1:8b` | 2 | 1 | 0 | thin | $0 |
| **Vertex `gemini-2.5-flash-lite`** | **10** | **2** | **0** | **all present** | ~$0.001 |

**Write-quality harden (2026-11):** non-NEW extract gets `focus_workstream_id=plan.task_id`;
post-LLM `infer_known_slots` for ttl/aud/builder/mem/color; deterministic ttl/aud slot
corrections. Stub suite: `tests/test_extract_slot_enforce.py`.

**Runs:**
- `python -m eval.ten_workstream.extract_density_ollama`
- `. .\scripts\env_vertex_local.ps1; python -m eval.ten_workstream.extract_density_vertex`

**Polish landed (gate untouched):**
- Structured Vertex extract via wrappers (not free-form JSON generate)
- Recall abstain: `did we…` / `Final check` / `Confirm…?`
- Writer: same-slot supersession across fact/decision/correction/entity

### Vertex 10×20 revive harness ✅

**Run:** `. .\scripts\env_vertex_local.ps1; python -m eval.ten_workstream.vertex_10x20_revive`  
**Out:** `eval/out/vertex_10x20_revive.json` · `docs/VERTEX_10x20_REVIVE.md`

| | |
|---|---|
| Model | `gemini-2.5-flash-lite` |
| Protocol | Mock seed history → Vertex extract+propose+answer on 10 revive probes |
| Calls / tokens | 37 · ~in/out tracked |
| Est. USD | ~**$0.0035** (per-million-token rates) |
| task / policy / WC | **10/10** |
| wrong_act | **0** |
| vs Mock routes | **0 divergences** |

### What more to research (priority order)

1. **Optional:** Vertex extract on seed turns (not only probes) — heavier, still no gate retune.  
2. **Cardinality later** — raise open hops after denser live-extract holds.  
3. **Market MemoryPort adapter** — when a real backend exists; never replace gate with top-k.  
4. **Natural / annotated substrate** — separate from synthetic fixtures.

## Best practices while polishing

1. **Interleave, don’t batch** — revive needs gaps.  
2. **Gold stays out of `app/`** — evaluator-isolated probes.  
3. **Don’t retune TAU/DELTA** to pass a harder fixture — document frozen disagreements.  
4. **Separate density from cardinality** — first deepen 10×20; only later try n=15/20 open cards.  
5. **Local first** — cloud is packaging, not the science.

## Immediate next actions

1. ~~hop_density analyzer~~ — `python -m eval.ten_workstream.hop_density`  
2. ~~10×20 fixture~~ — `python -m eval.ten_workstream.build_fixture_10x20` → `fixture_10x20.json` (200 turns, 20/ws)  
3. Replay:  
   `python -m eval.ten_workstream.run --fixture eval/ten_workstream/fixture_10x20.json --probes eval/ten_workstream/probes_10x20.json --out eval/out/ten_workstream_10x20.json --skip-md`  
4. ~~**Density run (MockLLM)**~~ — wrong_act=0; task/referent/policy/WC **10/10**; open_workstream_count_ok. Gate untouched.  
5. Demo UI shows **L1 COMPACT** via `GET …/compact-notation`.  
6. ~~**R2 condensation_stress**~~ — L1 ≪ full; caps hold; rollup usable.  
7. ~~**R3 catalog_revive**~~ — scenarios 4/4; selective import + honest CLARIFY + last-N + paused-until-bind.  
8. ~~**Density extract Ollama slice**~~ — weak (useful 2).  
9. ~~**Density extract Vertex Flash-Lite**~~ — useful **10**/abstain **2**; revive tokens ready; ~$0.001.  
10. ~~**Vertex 10×20 revive harness**~~ — live extract+propose+answer on 10 probes: task/policy/WC **10/10**, wrong_act=0, ~$0.0035, 0 mock divergences.  
11. **Next:** optional Cloud Run host, or longer live-extract seed (not just probe turns).

### POLICY misses dig (r20_A / r20_B) — resolved without gate retune

| Probe | Symptom | Root cause (frozen path) | Fix (fixture only) |
|---|---|---|---|
| `r20_A` | gold ACT → CLARIFY; pred ref `D.loop1` | Referent `lexical_tie`: message tokens overlapped A/C/D at score 1 (`api`/`auth`); `use_referent_route` + `ambiguous` → CLARIFY | Late A cues include **JWT 401 after refresh** so A.loop1 wins uniquely |
| `r20_B` | gold ACT → CLARIFY; pred ref `B.loop1` | Same-task `lexical_tie` B.loop1 vs B.loop2 (shared `docker` from goal; `/healthz` ≠ loop2 uniquely) | Late B cues prefer **CI failing on Docker step** + debian/4Gi; drop bare `/healthz` revive |
| open count 12 | T1/T2 NEW | Topic-align `force_new` / MockLLM miss on cache-only + quoted Celesteela height lines | Add Docker/failing-step tokens; plain “Celesteela height…Pokemon trivia” |

**Lesson:** under 10×20 density, fail-closed CLARIFY on revive is often **referent lexical uniqueness**, not TAU/DELTA. Tighten hop-distinct utterances + extract-adjacent cues; do not retune the gate.

## Per-prompt effectiveness (how we accommodate more)

“Accommodate as much” is not “stuff more into every prompt.” It is **per-turn discipline**: most of the conversation stays in the store; only the bound hop’s CURRENT asserted state enters generate.

### What happens on each user prompt

```text
message
  ├─ plan_turn          → which hop? ACT | CLARIFY | NEW   (soft LLM propose + hard gate)
  ├─ extract            → 0..k MemoryPatches OR abstain (recall / deixis / uncertain)
  │     └─ Writer       → validate → commit (supersede by slot) OR no-op
  └─ execute
        ├─ CLARIFY      → question only; no package; no generate
        └─ ACT/NEW      → project asserted(selected) → cap/rank → render → generate
```

| Concern | Effective behavior | Why it scales |
|---|---|---|
| Prompt ≠ memory | Recall/deixis often **abstain** write | 20 turns/hop ≠ 20 new facts |
| Corrections | Same `slot` → prior SUPERSEDED | CURRENT stays one value (navy not navy+black) |
| Routing | Gate binds **one** workstream (or CLARIFY) | Answer never sees 9 sibling hops’ facts |
| Assemble | RB-WSR + per-kind caps | Package size ≈ O(caps), not O(total turns) |
| Decision side | Still lists open **cards** | Grows with **open hop count**, not turn count |
| Store | Append-only asserted+history | Grows with writes; generate does not read it all |

### Cost / size intuition (density stress)

Let \(H\) = open hops, \(T\) = turns, \(W_h\) = asserted items on hop \(h\) after supersession.

| Blob | Rough growth | Control knob |
|---|---|---|
| Answer package | \(O(\mathrm{caps})\) on selected hop | `WorkingSetLimits`, referent filter |
| Decision / propose cards | \(O(H)\) | Keep H=10 first; don’t raise H before density works |
| Extract input | message + optional history + open cards | Abstain rules; don’t dump full transcript |
| Durable store | \(O(\text{commits})\) ≤ \(O(T)\) | Slots + abstain keep commits ≪ T |

**Effectiveness thesis:** revive after long gaps stays cheap because generate cost tracks **selected CURRENT**, not full history. Failure modes under 10×20 are usually **extract noise** (junk asserts) or **wrong bind** — not “window full.”

### Memory handling rules (effectiveness checklist)

1. **Write only when the turn establishes something** — underspecified / recall → empty patches.  
2. **One CURRENT per slot** — supersession is condensation.  
3. **Never put HISTORICAL or other hops into generate** — only asserted ∩ selected ∩ caps.  
4. **CLARIFY is a success mode** under ambiguity — cheaper than wrong-thread ACT.  
5. **Rollup/catalog for H2** — cold index; opt-in import; not auto-inject.  
6. **Measure package usability + wrong-ACT**, not “tokens in store.”

### What to polish for denser hops (effectiveness order)

1. Extract quality / abstain (biggest lever for clean CURRENT under 20 turns/hop).  
2. Slot discipline in scripts + real extract (so supersession fires).  
3. Working-set caps under noisy asserts (already started).  
4. Only then deepen fixture to 10×20 interleaved + revive probes.  
5. Raise \(H\) beyond 10 only after density metrics hold.

## Memory hierarchy (how we handle “the same” effectively)

Yes — this is the right framing. Effectiveness comes from **tiers**, not one flat memory the model always sees.

Industry analogue: Letta-style core / recall / archival; Cursor-style hot window + summary + files-on-demand.  
ContextFlow analogue: **bind a hop, then read only that hop’s hot tier.**

### Proposed hierarchy (align with code + H2 work)

```text
L0  EPHEMERAL TURN     this message (+ short extract hints)
L1  WORKING SET        asserted ∩ selected hop ∩ referent ∩ caps   → generate()
L2  HOP CURRENT        all asserted on that workstream (pre-cap)     → project source
L3  HOP HISTORY        superseded / retracted on that workstream     → audit / UI HISTORY
L4  OPEN INDEX         workstream cards + clocks (all open hops)     → retrieve / gate / propose
L5  CONVERSATION STORE full store for this conversation_id           → extract context, rollup
L6  CATALOG / ROLLUP   last-N condensed conversations (H2)           → opt-in import only
L7  COLD (future)      prefs / docs / vector-graph (H3)              → never overrides gate
```

| Tier | Hot for | Cold for | Already in CF? |
|---|---|---|---|
| L0 | Extract + plan | — | Yes |
| L1 | **Answer model** | Everything else | Yes (`WorkingContextBuilder` + caps) |
| L2 | Projection input | Other hops | Yes (`store.asserted(task)`) |
| L3 | UI / supersession checks | Generate | Yes (`historical`, status) |
| L4 | Scorer / gate / propose | Generate facts | Yes (registry open cards) |
| L5 | Writer + rollup build | Cross-chat | Yes (per `conversation_id`) |
| L6 | Catalog list / import | Auto-generate | Scaffolding (catalog + rollup) |
| L7 | Optional compose later | Binding | Not built |

### Promotion / demotion rules (hierarchy policy)

| Event | Move |
|---|---|
| Extract assert | L0 → Writer → L2 (and thus eligible for L1) |
| Same slot corrected | Old L2 value → L3 (superseded); new value stays L2 |
| Gate SELECT hop | L2∩referent∩caps → L1 for this turn only |
| CLARIFY | No L1 package |
| Turn ends | L1 discarded (rebuilt next turn); L2–L5 persist |
| Archive / touch catalog | L5 summarized → L6 rollup |
| Opt-in import | L6 → new conversation’s L4 cards + L2 seeds (**paused**) |
| Abandon hop | L4 drops from open index; L2/L3 retained for audit |

**Hard rule:** generate() may read **L1 only** (plus the user message).  
L4 may inform *which* hop; it must not dump all hops’ L2 into L1.  
L6/L7 never auto-merge into L1.

### Why hierarchy answers “accommodate as much”

- **More turns** → more L5/L3 growth; L1 stays capped.  
- **More hops** → L4 grows (card list); L1 still one hop.  
- **Revive** → gate picks hop from L4, rebuild L1 from that hop’s L2.  
- **Cross-chat** → L6; user promotes into a new L4/L2 explicitly.

Without hierarchy, “more effective memory” collapses to retrieve-and-stuff.  
With hierarchy, effectiveness = **correct tier + correct promotion.**

### Research checklist (hierarchy-aware)

When deepening 10×20, score failures by tier:

- Wrong hop → L4/select failure  
- Thin revive → L2 missing (extract/persist)  
- Contamination → L1 included foreign L2 (projection bug)  
- Stale fact → L3 not demoted / L2 not superseded  
- Bloated package → L1 caps / ranking failure  
- Cross-chat bleed → L6 auto-injected (must not happen)

## Product thesis: switcher + market memory (how to enable it)

**Idea (yours):** The market already has strong memory systems (Mem0 / Zep / Letta-style).  
ContextFlow’s job is not to replace them. It is to **dynamically resolve one avenue/thread** and feed **only that** into the answer — using those memory concepts underneath.

```text
                    ┌─────────────────────────────┐
  user message  →   │  ContextFlow BINDER         │
                    │  open index → score/referent│
                    │  → ACT | CLARIFY | NEW      │
                    └─────────────┬───────────────┘
                                  │ selected workstream_id
                                  ▼
                    ┌─────────────────────────────┐
                    │  MEMORY BACKEND (pluggable) │
                    │  your store | Mem0 | Zep…   │
                    │  read CURRENT for that id   │
                    └─────────────┬───────────────┘
                                  │ asserted items (L2)
                                  ▼
                    ┌─────────────────────────────┐
                    │  RB-WSR → L1 package → LLM  │
                    └─────────────────────────────┘
```

### Division of labor

| Layer | Owns | Does not own |
|---|---|---|
| **ContextFlow (yours)** | Which thread is live; ACT vs CLARIFY; L1 assembly | Being the best vector/graph DB |
| **Memory product (market)** | Persist / recall / temporal facts / cross-session | Deciding ACT under multi-open-task interference |
| **Answer model** | Wording | Writes to memory; routing |

### Enablement steps (concrete)

1. **Freeze the binder contract** (already mostly true)  
   - Input: message + open thread index.  
   - Output: `{transition, workstream_id, referent_id}` or CLARIFY.  
   - No memory vendor in this step.

2. **Define a narrow MemoryPort** (adapter over today’s `MemoryStore` + registry cues)  
   ```text
   list_open_threads(conversation_id) -> cards[]
   read_asserted(conversation_id, workstream_id, referent?) -> items[]
   write_patches(conversation_id, patches) -> ok
   search_cold(conversation_id, query, limit) -> hits[]   # optional L7
   ```
   - In-memory / Firestore implement the port today.  
   - Mem0/Zep implement `write`/`search_cold` + map hits into **patches on the selected thread** (or candidate card text) — never straight into generate.

3. **Resolve-then-read (dynamic one avenue)**  
   ```text
   bind = plan_turn(message)           # CF
   if CLARIFY: return question
   items = memory.read_asserted(bind.workstream_id)
   # optional: cold = memory.search_cold(message); merge only into that workstream's L2
   package = project(items) → generate
   ```

4. **Use market concepts without losing the wedge**  
   | Market concept | Where it plugs in |
   |---|---|
   | Fact extract on write (Mem0-like) | Your extractor → `write_patches` |
   | Temporal invalidate (Zep-like) | Map to supersede / valid_to (L2→L3) |
   | Core vs archival (Letta-like) | L1/L2 vs L6/L7 |
   | Vector recall | `search_cold` **after** bind, scoped to thread or import-as-paused |
   | Session journal | L5 / L6 catalog |

5. **Fail-closed compose rule**  
   - Cold hits may **enrich the selected thread** or **propose a NEW/paused card**.  
   - Cold hits must **not** override an ACT decision or flood L1 with multi-thread top-k.

6. **Prove enablement with tests**  
   - Fake `MemoryPort` that returns different L2 per workstream_id.  
   - Assert: after SWITCH to B, generate package contains B facts only.  
   - Assert: cold search results for A never appear when bind=B.  
   - Swap port implementation later without touching gate.

### What “enabled” looks like for you

- Switching/revive stays the product demo (badges + CURRENT/HISTORY).  
- Memory durability/recall quality can improve by **swapping backends**.  
- Any avenue: bind → read that avenue’s memory → use it.  
- You are not competing with Mem0 on storage; you are the **thread resolver** in front of them.

### Do not do

- Replace gate with “top-k memories from Mem0 → stuff prompt.”  
- Auto-merge all cold hits across threads into L1.  
- Retune frozen routing just to fit a vendor SDK.

## Claim hygiene

- 10×20 is a **controlled density stress**, not natural chat.  
- Passing MockLLM 10×20 ≠ production accuracy.  
- “Free GCP via second Gmail” is **not** part of the research plan.  
- Accommodating more turns means **better per-prompt memory discipline**, not larger prompts.
