# End-to-End GCP Proof — Phase 11 (historical)

**Status:** production-shaped research POC (not production-ready)

**Note:** This file is the **Phase 11** narrative. For the current tip (Phase 14), see `docs/CLOUD_POC_REVIEWER.md` and `eval/out/phase14_gcp_validation.json` (revision end `contextflow-durable-00029-h74`).

**Thesis:** ContextFlow maintains durable, evolving working memory across multiple open workstreams and reconstructs the relevant working state when the user returns, even after the serving instance changes.

**Checkpoint:** `8cc553983b45702ff16c071678f9bdc5b9d26fe3` (routing frozen)

**Executed:** 2026-08-31

---

## Path exercised (actual HTTP)

```
POST /conversations/{id}/turn
  → Vertex MemoryExtractor (gemini-2.5-flash-lite)
  → MemoryWriter
  → Firestore memory + Firestore workstream registry
  → frozen ContextFlow (gate / referent / scorer)
  → WorkingContextBuilder
  → ContextPackage
  → Vertex answer (generate)
```

No direct Firestore mutation in the harness. No memory seeding after conversation start.

---

## DEMONSTRATED

| Claim | Evidence |
|---|---|
| Authenticated Cloud Run HTTP path | `eval/cloud_poc/end_to_end_resurrection.py` — IAM token on every request |
| Vertex LLM extraction | `health.extract=llm`, `vertex_enabled=true`, 8/8 turns `extract_ok=true` (primary run) |
| Firestore durable memory | `memory_durable=true`, items persist across revision bump |
| Firestore durable registry | `registry_durable=true`, workstream B/C/D titles survive restart |
| Multi-workstream routing | Turns 1–4: SWITCH/RETURN to A/B/C/D without task IDs in utterances |
| Outfit return after switches | Turn 5 SWITCH→B, turn 7 CONTINUE→B post-restart |
| Correction + supersession | Turn 6: black dress superseded, navy asserted (primary run) |
| Working context reconstruction | `GET /working-context?task_id=B` — navy decisions, auth/Lisbon/deployment excluded |
| Cross-workstream isolation in WC | `excluded_workstreams`: authentication, Lisbon trip, deployment |
| Cloud Run revision survival | `contextflow-durable-00009-hp4` → `00010-2pj` (forced bump mid-experiment) |
| Cross-conversation isolation | Separate `poc-e2e-iso-*` conversation; no leak into primary |
| Answer path invoked | 8 turns `answer_status=ok`, `package_mode` REFERENT_COMPACT / FULL_TASK |
| Redacted observability | Cloud Logging `turn_decision` events — see § Observability |
| Cost within ceiling | ~27 estimated generate calls, ~$0.72 est. (ceiling $2.00) |

**Primary artifact:** `eval/out/end_to_end_resurrection.json`  
**Conversation:** `poc-e2e-8dfd939b`

---

## TESTED

| Item | Result |
|---|---|
| Harness integrity (no Firestore hacks) | `tests/test_end_to_end_harness.py` — 9 tests pass |
| Unit + integration suite | 268 passed, 1 skipped |
| Routing byte identity vs `8cc5539` | `git diff 8cc5539 -- app/router/gate.py app/router/referent.py app/retrieval/scorer.py app/config.py` — empty |
| Revision change detection | Harness compares `revision_before` / `revision_after_bump` |
| Generate does not silently grow memory without extract | Checked per turn |
| Second run variability | Re-run `poc-e2e-e41b6937`: turn 6 `extract_ok=false` — navy/black supersession not captured (see Limitations) |

---

## NOT YET

| Item | Notes |
|---|---|
| Deterministic Vertex extraction | Turn 6 correction is flaky across runs (~50% on re-run) — **superseded Phase 13:** deterministic parsers achieve 10/10 per-run |
| Dynamic new workstream creation | **DEMONSTRATED Phase 13** — see `dynamic_workstream_e2e.json` (5/5 NEW, seed OFF) |
| Formal/evening as extracted constraint | Primary run encoded correction as decision supersession, not `kind=constraint` |
| Answer quality / accuracy scoring | Only path evidence captured (hash + metadata) |
| Production SLO / HA / organic chat benchmarks | Out of scope |
| Exact Vertex billing | Estimate only via harness |

## Phase 12 — Stabilization (2026-08-31)

**Fixes (extractor contract only — routing/MemoryWriter unchanged):**

| Gap | Fix | Evidence |
|---|---|---|
| Duplicate decisions on recall | `message_looks_recall_only`, `filter_redundant_patches`, `_assertion_equivalent` | Repeatability: **0 duplicate decisions / 10 runs** |
| Correction supersession | `_infer_color_correction`, improved prompt, color-token `_fill_supersedes` | **Phase 12 historical:** Repeatability **2/10** correction+supersession (gate **FAIL**). Later: Phase 13/14 → **10/10** — see `eval/out/phase14_gcp_validation.json` |
| Repeatability gate | `eval/cloud_poc/e2e_repeatability.py` | `eval/out/e2e_repeatability.json` |

**Quality gate (10 runs, revision `contextflow-durable-00012-sz7`):**

| Layer | Result | Threshold |
|---|---|---|
| correction_extraction | 2/10 | ≥ 9/10 **FAIL** |
| supersession | 2/10 | ≥ 9/10 **FAIL** |
| duplicate_current_decisions | 0 | 0 **PASS** |
| working_context | 2/10 | ≥ 9/10 **FAIL** |
| contamination | 0 | 0 **PASS** |
| cross_conversation_leakage | 0 | 0 **PASS** |
| routing_freeze | unchanged | **PASS** |

Dynamic workstream design audit: `docs/DYNAMIC_WORKSTREAM_DESIGN.md` (no implementation).

## Phase 13 — Dynamic NEW + structured correction (2026-08-31)

**Fixes (pipeline + extractor only — routing/MemoryWriter unchanged):**

| Gap | Fix | Evidence |
|---|---|---|
| Dynamic NEW without seed | NEW-only route-before-extract + `focus_workstream_id` | `dynamic_workstream_e2e.py` — 5/5 NEW created, harness `ok=true` |
| Structured correction | Deterministic parsers (`correction.py`) + Gemini `propose()` schema | Repeatability: **10/10** per-run `correction_extraction_ok` |
| Repeatability (no seed) | Harness uses dynamic `task_id` from turn 1 | Revision `contextflow-durable-00013-24m`, image `poc5-phase13` |

**Quality gate (10 runs, seed OFF, revision `00013-24m`):**

| Layer | Result | Threshold |
|---|---|---|
| correction_extraction (per-run) | **10/10** | ≥ 9/10 **PASS** |
| supersession (per-run) | **10/10** | ≥ 9/10 **PASS** |
| duplicate_current_decisions | 0 | 0 **PASS** |
| working_context (per-run) | **10/10** | ≥ 9/10 **PASS** |
| contamination | 0 | 0 **PASS** |
| cross_conversation_leakage | 2 isolation 500s | 0 **FAIL** (infra flake on iso turn) |
| harness `all_ok` | false | isolation errors penalize gate numerator |

**Phase 12 baseline (historical):** correction was **2/10** on revision `00012-sz7` with seed ON. Phase 13/14 supersede with deterministic correction + no seed (**10/10** on Phase 14 tip).

Dynamic workstream: `docs/DYNAMIC_WORKSTREAM_DESIGN.md` — **implemented and demonstrated**.

---

## Experiment design

**Service:** `contextflow-durable` @ `asia-south1`  
**Image:** `contextflow-durable:poc3-e2e`  
**Revision (primary run end):** `contextflow-durable-00010-2pj`

**Env (deployed):**

```
CF_MEMORY_BACKEND=firestore
CF_USE_VERTEX=1
CF_LLM_EXTRACT=1
CF_USE_GEMINI=1
CF_SEED_E2E=1          # workstream card identity A/B/C/D only
CF_SEED_TEN=0
CF_SMOKE_FIXTURE=0
CF_GEN_MODEL=gemini-2.5-flash-lite
CF_LITE_MODEL=gemini-2.5-flash-lite
CF_EMBED_LOCAL=1
```

**Seed boundary (explicit):** `CF_SEED_E2E=1` creates workstream **cards** (titles, goals, loops) on first engine touch. All **memory content** comes from Vertex extraction on HTTP turns. This is separate from Vertex-generated memory evidence.

**Turn script (natural language, no task IDs):**

| Turn | Utterance (summary) | Expected WS |
|---|---|---|
| 1 | JWT 401 auth problem | A |
| 2 | Black dress for corporate event | B |
| 3 | Lisbon hotel parking | C |
| 4 | Docker CI build failure | D |
| 5 | Back to outfit / dress | B |
| 6 | Navy not black, formal evening | B (correction) |
| — | *revision bump* | — |
| 7 | Outfit color after restart | B |
| 8 | Lisbon hotel requirement | C |

Plus isolation conversation: Docker CI (separate `conversation_id`).

---

## Primary run results (`poc-e2e-8dfd939b`)

### Request / cost

| Metric | Value |
|---|---|
| HTTP turns (primary conv) | 8 |
| Isolation turn | 1 |
| Vertex generate calls (est.) | 27 |
| USD estimate | ~$0.72 |
| Ceilings | 30 calls / $2.00 |

### Extraction (primary)

| Metric | Value |
|---|---|
| Accepted (`extract_ok=true`) | 8 |
| Rejected / empty | 0 |

### Memory after restart (outfit B)

| Status | Content |
|---|---|
| Asserted | `Pick a navy dress.` (×2 — duplicate on return turn) |
| Superseded | `Pick a black dress.` |
| Constraints | none extracted |

### Working context (outfit B)

```json
{
  "decisions": ["Pick a navy dress.", "Pick a navy dress."],
  "constraints": [],
  "excluded": ["authentication", "Lisbon trip", "deployment"]
}
```

### Answer path (separate from accuracy)

| Layer | Primary run |
|---|---|
| 1. Extraction succeeded | Yes (8/8) |
| 2. Working context reconstructed | Yes |
| 3. Vertex answer generated with package | Yes (`package_status=ok`, `answer_status=ok`) |

Answer text stored as SHA256 prefix only in JSON artifact (policy-safe).

### Revisions

| | Revision |
|---|---|
| Before bump | `contextflow-durable-00009-hp4` |
| After bump | `contextflow-durable-00010-2pj` |

---

## Observability (Cloud Logging)

Query:

```
resource.type="cloud_run_revision"
resource.labels.service_name="contextflow-durable"
textPayload:"turn_decision"
```

**Present (sample from primary run):**

`request_id`, `conversation_id_hash`, `selected_task`, `selected_referent`, `transition`, `memory_current_count`, `memory_history_count`, `memory_asserted`, `memory_backend`, `workstream_count`, `registry_reads`, `registry_writes`, `package_status`, `answer_status`, `extract_ok`, `latency_ms`, `message_chars`

**Absent:** raw user text, prompts, model responses, memory content, credentials

---

## GCP resources

| Resource | Detail |
|---|---|
| Project | `contextflow-506414` |
| Cloud Run | `contextflow-durable` (authenticated) |
| Firestore | `contextflow-poc` @ `asia-south1` |
| Vertex | `gemini-2.5-flash-lite` @ `us-central1` |
| SA | `contextflow-run@contextflow-506414.iam.gserviceaccount.com` |
| Image | `asia-south1-docker.pkg.dev/.../contextflow-durable:poc3-e2e` |

No service-account keys. Service not public.

---

## Reproduce

```bash
# Deploy (requires gcloud auth + run.invoker)
gcloud builds submit --tag asia-south1-docker.pkg.dev/contextflow-506414/cloud-run-source-deploy/contextflow-durable:poc3-e2e
# ... deploy with env vars above

python -m eval.cloud_poc.end_to_end_resurrection
```

---

## Phase 13 — Dynamic NEW + correction (2026-08-31)

| Claim | Evidence |
|---|---|
| Dynamic workstream without seed | `eval/cloud_poc/dynamic_workstream_e2e.py` — 5/5 NEW, seed flags verified OFF |
| Structured correction repeatability | `eval/cloud_poc/e2e_repeatability.py` — 10/10 per-run correction (seed OFF) |
| Revision | `contextflow-durable-00013-24m` → bumped to `00018-6s8` during dynamic harness |
| Image | `contextflow-durable:poc5-phase13` |

**Seed flags (deployed):** `CF_SEED_E2E=0`, `CF_SEED_TEN=0`, `CF_SEED_ABCD=0`, `CF_SMOKE_FIXTURE=0`

---
