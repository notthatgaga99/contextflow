# Dynamic workstream creation — design + Phase 13 implementation

**Checkpoint:** `8cc553983b45702ff16c071678f9bdc5b9d26fe3` (routing frozen)

**Phase 13 executed:** 2026-08-31

---

## DEMONSTRATED

| Claim | Evidence |
|---|---|
| Frozen gate emits `NEW` for novel topics (no seed) | `eval/cloud_poc/dynamic_workstream_e2e.py` — 5/5 reps turn-1 `transition=NEW`, `task_id=T1` |
| Registry card created before extraction on NEW | `Engine.execute_plan()` → `registry.add()` then `focus_workstream_id` extract pass |
| Memory attaches to dynamically created id | 4/5 reps `memory_persisted`; 5/5 `extract_ok` on turn 1 |
| Multi-topic dynamic creation (A/B/C) | Turns 1–3 each `NEW` → T1/T2/T3 without seed fixtures |
| Return to first topic | 5/5 `return_success` (turn 4 `SWITCH→T1`) |
| Registry survives revision replacement | 5/5 `registry_persisted`; 4/5 `revision_survival` |
| No duplicate registry cards | 5/5 `duplicate_registry_count=0` |
| Cross-conversation isolation | 5/5 `isolation_ok` |
| Seed flags disabled at runtime | Harness verified `CF_SEED_E2E=0`, `CF_SEED_TEN=0`, `CF_SEED_ABCD=0`, `CF_SMOKE_FIXTURE=0` |

**Artifact:** `eval/out/dynamic_workstream_e2e.json`  
**Revision:** `contextflow-durable-00013-24m` (image `poc5-phase13`)

---

## TESTED

| Item | Result |
|---|---|
| Local NEW pipeline | `tests/test_dynamic_new_workstream.py` — 4 tests pass |
| `plan_turn` has no side effects | Registry unchanged until `execute_plan` |
| Non-NEW path unchanged | extract → route (same order as Phase 12) |
| Routing freeze | `git diff 8cc5539 -- gate.py referent.py scorer.py config.py` — empty |
| Full unit suite | 297 passed, 1 skipped |

---

## NOT YET (Phase 13 snapshot — see Phase 14 for current)

| Item | Notes |
|---|---|
| 5/5 memory persistence after revision *(Phase 13)* | Rep-02: `extract_ok=true` but no espresso fact in Firestore post-restart (Vertex extraction flake). **Superseded:** Phase 14 measured pre-restart memory **10/10**; revision survival **9/10** (1× Vertex 429). |
| Semantic task slugs | Still `T1`, `T2`, … not user-visible titles as ids |
| Multi-region registry consistency | Single region only |
| Production SLO / organic chat benchmarks | Engineering harness only |

---

## Pipeline (implemented — Phase 13)

```
POST /turn (main.py)
  → ConversationStore.engine / writer
  → run_turn (turn_pipeline.py)
       │
       ├─ plan_turn (engine.py) — route without mutations
       │
       ├─ if NEW:
       │     execute_plan → registry.add(Tn) → answer generated
       │     extract(focus_workstream_id=Tn) → MemoryWriter.commit
       │
       └─ else (ACT/SWITCH/RETURN/CLARIFY):
             extract → execute_plan → answer
  → WorkingContextBuilder (on read paths)
  → generate() answer (already in execute_plan)
```

**Key insight:** Routing authority unchanged. Only NEW turns reorder to create the registry card before extraction.

---

## Authority boundary (unchanged)

| Component | Role |
|---|---|
| Frozen gate/scorer | Emits `NEW` — LLM proposal informs, does not replace |
| `Engine.execute_plan` | Creates registry card on `NEW` |
| `LlmMemoryExtractor` | Proposes patches for **known** ids (+ `focus_workstream_id` on NEW) |
| `MemoryWriter` | Validates + commits — not weakened |
| `generate()` | Answers only |

The LLM does **not** decide NEW, write memory, or route.

---

## Prior limitation (Phase 11–12)

Extraction ran before routing on every turn. Memory could not target a workstream that did not yet exist. Engineering seeds (`CF_SEED_E2E`, etc.) pre-created card identity.

**Phase 13 fix:** NEW-only route-before-extract with `focus_workstream_id`. Maximum one extraction pass per turn (no infinite retry).

---

## Phase 14 — Reliability fixes (implemented + GCP-proven)

| Fix | Change |
|---|---|
| NEW memory without Vertex | `try_parse_new_focus_fact` — only when `focus_workstream_id` set after gate NEW |
| Misleading `extract_ok` | API adds `extract_committed`; harness requires memory on new workstream |
| Isolation HTTP 500 | Vertex 429 during `generate()` — harness retries rate-limit-shaped failures only |

**Still frozen:** gate / referent / scorer / config / MemoryWriter vs `8cc5539`.

## Phase 14 — Real GCP validation (2026-08-31) — current

**Image:** `poc6-phase14` · **Revision start:** `00019-7kk` · **End:** `00029-h74`  
**Seed flags:** OFF · **Artifacts:** `eval/out/e2e_repeatability.json`, `eval/out/dynamic_workstream_e2e.json`, `eval/out/phase14_gcp_validation.json`

### DEMONSTRATED

| Claim | Evidence |
|---|---|
| Correction repeatability | **10/10** extraction + supersession; dup=0; WC 10/10; contam=0 |
| Isolation (correction harness) | **10/10** HTTP 200, **0 leaks** (1 run needed retry after rate-limit shape) |
| Dynamic NEW creation (no seed) | **10/10** turn-1 NEW + T1 + `extract_committed` |
| Dynamic NEW memory persistence | **10/10** pre-restart Firestore memory on T1 |
| Dynamic NEW return + WC | **9/10** completed error-free; 9/10 WC ok |
| Dynamic revision survival | **9/10** completed; 1 post-restart turn hit Vertex 429 |
| Routing / writer freeze | empty vs `8cc5539` |

### TESTED

Local suite + authenticated Cloud Run HTTP only; Firestore `contextflow-poc`.

### FAILED / incomplete

| Item | Detail |
|---|---|
| Dynamic rep-08 post-restart turn | HTTP 500 / Vertex **429 RESOURCE_EXHAUSTED** on `generate()` (`ff28d925-…`); memory already persisted before bump |

### NOT YET

Organic-chat benchmarks; production SLO; zero Vertex 429 under sustained revision-bump load.

Turn 3 NEW/CONTINUE edge cases under frozen cues: `docs/PHASE14_TURN3_FORENSIC.md` (known limitation; routing not retuned).

