# Real GCP POC — Evidence Report

**Thesis:** ContextFlow is not merely retrieving old chat. It maintains durable, evolving working memory across multiple open threads, then reconstructs the right state when the user returns.

**Project:** `contextflow-506414` · **Region:** `asia-south1` (Run + Firestore) · **Vertex:** `us-central1`  
**Executed:** 2026-08-31 · **Routing checkpoint:** `8cc5539` (frozen files byte-identical)

---

## 1. Architecture

```
HTTP (IAM-authenticated)
  → Cloud Run: contextflow-durable
  → MemoryExtractor (Mock or Vertex proposer)
  → MemoryWriter
  → Firestore database: contextflow-poc
  → frozen ContextFlow (gate / referent / scorer)
  → WorkingContextBuilder
  → ContextPackage
  → Vertex answer (when enabled)
```

Firestore is persistence only — not a router.

## 2. GCP resources created/used

| Resource | Detail |
|---|---|
| Firestore | Native DB `contextflow-poc` @ `asia-south1` |
| Cloud Run | `contextflow-durable` (authenticated only) |
| Artifact Registry | `asia-south1-docker.pkg.dev/.../contextflow-durable:poc1` |
| Service account | `contextflow-run@contextflow-506414.iam.gserviceaccount.com` |
| Cloud Build | Image build `c9690efe-91a6-41ed-aac0-c767b8ead2d7` |

**Left untouched:** demo service `contextflow` (in-memory, separate).

## 3. IAM

**Runtime SA `contextflow-run@…`:**

- `roles/datastore.user`
- `roles/logging.logWriter`
- `roles/aiplatform.user`
- `roles/monitoring.metricWriter`

**Invoker (authenticated only):**

- `user:09.gaganacm@gmail.com` → `roles/run.invoker` on `contextflow-durable`

**Build support (minimal, for image push):**

- `810061766045-compute@developer.gserviceaccount.com` → `roles/artifactregistry.writer`, `roles/logging.logWriter`
- Bucket `objectViewer` on `contextflow-506414_cloudbuild` and `run-sources-contextflow-506414-asia-south1`

No service-account keys created.

## 4. Firestore schema

Path: `conversations/{conversation_id}/memory/{item_id}` + `meta/namespace` + `idempotency/{key}`  
See `docs/FIRESTORE_MEMORY.md`.

**Local CRUD smoke (real Firestore, ADC):** `eval/cloud_poc/firestore_crud_smoke.py` — **all checks passed**.

## 5. Cloud Run deployment

| Field | Value |
|---|---|
| Service | `contextflow-durable` |
| URL | `https://contextflow-durable-cjraqyv4hq-el.a.run.app` |
| Latest revision (Vertex) | `contextflow-durable-00004-nln` |
| Runtime SA | `contextflow-run@…` |
| Memory backend | `firestore` / `contextflow-poc` |
| Concurrency | 8 |
| Min / max instances | 0 / 3 |
| Auth | **Required** (`--no-allow-unauthenticated`) |
| Container | non-root UID 10001 |

## 6. Authentication

- Unauthenticated `GET /health` → **403**
- Authenticated `GET /health` → `memory_durable: true`, `memory_backend: firestore`
- Authenticated `POST /turn` → succeeds
- Token: `gcloud auth print-identity-token`

## 7. Durability proof

Script: `eval/cloud_poc/real_cloud_run_durability.py`  
Output: `eval/out/real_cloud_run_durability.json`

**Scenario (real Cloud Run + Firestore, no FakeFirestore):**

1. Conversation A: auth + outfit + black→navy + formal/evening constraints  
2. Conversation B: Docker CI fact  
3. Forced new revision (`contextflow-durable-00003-klq`) to recycle instance  
4. Return to A

**Result: PASS (all 12 checks)**

- Navy survives restart  
- Black auditable as superseded  
- Formal/evening constraints survive  
- Docker memory does not leak into A  
- B remains isolated  

## 8. Isolation proof

Included in durability test + Firestore CRUD smoke (A/B write/read, no cross-read).

## 9. Vertex proof

Revision `contextflow-durable-00004-nln`:

- `CF_USE_VERTEX=1`, `CF_LLM_EXTRACT=1`
- Model: `gemini-2.5-flash-lite` @ `us-central1`
- `CF_EMBED_LOCAL=1` (routing embeddings local — no Vertex embed spend)

Script: `eval/cloud_poc/vertex_cloud_smoke.py` (4 HTTP turns)  
Output: `eval/out/vertex_cloud_smoke.json`

| Turn | Transition | Task | Extract |
|---|---|---|---|
| 1 | SWITCH | A | ok |
| 2 | SWITCH | B | ok |
| 3 | CONTINUE | B | ok |
| 4 | CONTINUE | B | ok |

Vertex used for extraction + answer only; routing transitions from frozen gate (SWITCH/CONTINUE, not model-chosen CLARIFY authority).

**Estimated Vertex `generate_content` calls:** ~8–12 (within ≤20 ceiling). **Cost ceiling $2:** not exceeded (exact invoice unavailable).

## 10. Multi-workstream cloud test

Script: `eval/cloud_poc/multi_workstream_cloud.py`  
**15 HTTP turns**, 2 CLARIFY — synthetic/adversarial fixture via smoke scripts; proves durability + isolation + reconstruction, **not** natural-chat accuracy.

Output: `eval/out/multi_workstream_cloud.json`

## 11. Observability proof

Cloud Logging query (sample):

```
resource.type="cloud_run_revision"
resource.labels.service_name="contextflow-durable"
textPayload:"turn_decision"
```

**Present:** `request_id`, `conversation_id_hash`, `latency_ms`, `extract_status`, `memory_backend`, `memory_reads`/`writes`, `memory_current_count`, `memory_history_count`, `selected_task`, `selected_referent`, `transition`, `package_status`, `answer_status`

**Absent:** raw user text, prompts, model responses, memory content, credentials

## 12. Cost

**Usage observed; exact invoice unavailable through current interface.**

Observed billable activity:

- Firestore: POC writes (low volume, free-tier eligible)
- Cloud Run: cold starts + ~25 HTTP turns across tests
- Cloud Build: 2 image builds
- Vertex: ~8–12 generate_content (flash-lite, 4-turn smoke)

No SLO claimed.

## 13. Limitations

- Workstream seeding uses engineering fixtures on first engine touch per conversation (`CF_SEED_ABCD=1`, `CF_SEED_E2E=1`, or `CF_SEED_TEN=1`) — **card identity only**; memory from Vertex/Mock extract
- Durability phase used Mock extract scripts (`CF_SMOKE_FIXTURE=1`); Vertex phase used real LLM extract
- Not multi-region HA, not production SLO, not load tested
- Vertex correction extraction is **non-deterministic** on turn 6 (see `docs/END_TO_END_GCP_PROOF.md`)
- Monitoring dashboard not created (logs sufficient for POC)

## 16. Phase 11 — Production-shaped E2E proof (2026-08-31)

**Goal:** One reproducible cloud proof of the full product path (Vertex extract → writer → Firestore → route → answer) with revision survival.

| Field | Value |
|---|---|
| Script | `eval/cloud_poc/end_to_end_resurrection.py` |
| Report | `docs/END_TO_END_GCP_PROOF.md` |
| Artifact | `eval/out/end_to_end_resurrection.json` |
| Image | `contextflow-durable:poc3-e2e` |
| Revision | `contextflow-durable-00010-2pj` (primary successful run) |
| Model | `gemini-2.5-flash-lite` |
| Seed | `CF_SEED_E2E=1` (A/B/C/D cards only) |

**Primary run (`poc-e2e-8dfd939b`): PASS** — navy supersession, revision survival, WC isolation, 8/8 extraction, ~27 Vertex calls (~$0.72 est.).

**Re-run note:** Second execution showed turn-6 extraction flake (`extract_ok=false`); reported as limitation, not compensated in app code.

```bash
python -m eval.cloud_poc.end_to_end_resurrection
```

## 17. Phase 12 — Extractor stabilization (2026-08-31) — historical

| Field | Value |
|---|---|
| Image | `contextflow-durable:poc4-stabilize` |
| Revision | `contextflow-durable-00012-sz7` |
| Harness | `eval/cloud_poc/e2e_repeatability.py` |
| Artifact | `eval/out/e2e_repeatability.json` |
| Design audit | `docs/DYNAMIC_WORKSTREAM_DESIGN.md` |

**Repeatability gate (10 runs, Phase 12 historical):** duplicate decisions **0** (PASS); correction extraction **2/10** (FAIL); supersession **2/10** (FAIL); isolation/contamination **0** (PASS).  
**Superseded by Phase 13/14** (correction/supersession **10/10** on tip — see §19).

```bash
python -m eval.cloud_poc.e2e_repeatability
```

## 18. Phase 13 — Dynamic NEW + structured correction (2026-08-31) — historical baseline

| Field | Value |
|---|---|
| Image | `contextflow-durable:poc5-phase13` |
| Revision | `contextflow-durable-00013-24m` (dynamic harness bumped to `00018-6s8`) |
| Harness (correction) | `eval/cloud_poc/e2e_repeatability.py` |
| Harness (dynamic NEW) | `eval/cloud_poc/dynamic_workstream_e2e.py` |
| Artifacts | `eval/out/e2e_repeatability.json`, `eval/out/dynamic_workstream_e2e.json` |

**Seed flags: OFF** (`CF_SEED_E2E=0`, `CF_SEED_TEN=0`, `CF_SEED_ABCD=0`, `CF_SMOKE_FIXTURE=0`)

| Layer | Result (Phase 13) |
|---|---|
| correction_extraction (per-run) | **10/10** (Phase 12 was 2/10) |
| supersession (per-run) | **10/10** |
| duplicate_current_decisions | **0** |
| working_context (per-run) | **10/10** |
| contamination | **0** |
| dynamic NEW created | **5/5** |
| dynamic memory persisted | **4/5** |
| dynamic revision survival | **4/5** |
| harness `all_ok` (repeatability) | **FAIL** — 2 isolation-check 500s |

**Current tip:** Phase 14 (§19) re-measured dynamic NEW at 10 reps and closed isolation 500s as Vertex 429 (harness retries).

```bash
python -m eval.cloud_poc.e2e_repeatability
python -m eval.cloud_poc.dynamic_workstream_e2e
```

## 19. Phase 14 — Real GCP validation (2026-08-31)

| Field | Value |
|---|---|
| Image | `contextflow-durable:poc6-phase14` |
| Revision | `00019-7kk` → `00029-h74` |
| Seed flags | **OFF** |
| Correction gate | **PASS** 10/10 all layers |
| Dynamic NEW | harness `ok=true`; memory 10/10 pre-restart; revision survival 9/10 |
| Isolation | **0 leaks**; 10/10 HTTP 200 (1 retry) |
| Cost est. | ~$7.83 (ceiling $10) |
| Artifact | `eval/out/phase14_gcp_validation.json` |

## 14. Phase 10 — Durable workstream registry (2026-08-31)

**Gap closed:** Memory was durable; workstream registry was process-local.

**Now:** `CF_MEMORY_BACKEND=firestore` persists both:
- `conversations/{cid}/memory/{item_id}`
- `conversations/{cid}/workstreams/{workstream_id}`

| Proof | Result |
|---|---|
| Unit tests (`test_firestore_registry.py`) | Pass (FakeFirestore) |
| `workstream_resurrection.py` | **Pass** — E survives revision `00006-f5w`; navy/formal/evening; black superseded; B isolated |
| `ten_thread_resurrection.py` | **Pass** — 20 HTTP turns; returns to A/C/E/J after revision `00007-297` |
| Revision deployed | `contextflow-durable-00005-7t9` (image `poc2-registry`) |

See `docs/WORKSTREAM_DURABILITY.md`.

## 15. Local validation

```
pytest -q          → 297 passed, 1 skipped
routing vs 8cc5539 → identical (gate/referent/scorer/config)
```

**Not committed / not pushed** (per instructions).

## Commands to reproduce

```bash
python -m eval.cloud_poc.firestore_crud_smoke
python -m eval.cloud_poc.real_cloud_run_durability
python -m eval.cloud_poc.multi_workstream_cloud
python -m eval.cloud_poc.vertex_cloud_smoke
python -m eval.cloud_poc.end_to_end_resurrection
python -m eval.cloud_poc.e2e_repeatability
python -m eval.cloud_poc.dynamic_workstream_e2e
```
