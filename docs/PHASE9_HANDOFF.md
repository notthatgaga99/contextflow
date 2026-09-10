# Phase 9 handoff — COMPLETED (2026-08-31)

**Status:** Real GCP POC executed. See `docs/REAL_GCP_POC.md` for full evidence.

Checkpoint / routing freeze: `8cc553983b45702ff16c071678f9bdc5b9d26fe3` (unchanged)

---

## What was done

| Step | Status |
|---|---|
| Firestore `contextflow-poc` @ asia-south1 | ✅ Created |
| Firestore CRUD smoke (real ADC) | ✅ Pass |
| SA `contextflow-run@…` + IAM | ✅ |
| Cloud Run `contextflow-durable` | ✅ Deployed (auth only) |
| Durability test (restart via revision bump) | ✅ All 12 checks |
| Multi-workstream (15 HTTP turns) | ✅ |
| Vertex smoke (4 turns, flash-lite) | ✅ |
| Cloud Logging redaction verified | ✅ |
| `docs/REAL_GCP_POC.md` | ✅ |

**Service URL:** `https://contextflow-durable-cjraqyv4hq-el.a.run.app`  
**Latest revision:** `contextflow-durable-00004-nln` (Vertex enabled)

**Not done:** formal Monitoring dashboard, exact billing pull, git commit/push.

---

## Pre-flight (confirmed)

| Item | Value |
|---|---|
| Account | `09.gaganacm@gmail.com` |
| Project | `contextflow-506414` (name: ContextFlow, ACTIVE) |
| Project number | `810061766045` |
| Intended Cloud Run region | `asia-south1` |
| Intended Firestore location | `asia-south1` (native) — **DB not created yet** |
| Intended Firestore database id | `contextflow-poc` (labeled POC; not `(default)`) |
| Vertex region / model | `us-central1` / `gemini-2.5-flash-lite` |
| Vertex call ceiling | ≤ **20** `generate_content`; cost ceiling **$2** |
| ADC | Present locally |

Existing (leave alone unless needed):

- Demo Cloud Run: `contextflow` @ `asia-south1` → `https://contextflow-cjraqyv4hq-el.a.run.app` (SA `cf-run@…`, revision `contextflow-00002-95x`)
- SAs already present: `cf-run@…`, `cf-build@…`, Compute default
- Artifact Registry: `cloud-run-source-deploy`

---

## Done in this session

1. **APIs enabled** (were missing): `firestore.googleapis.com`, `secretmanager.googleapis.com`  
   Already on: run, aiplatform, artifactregistry, cloudbuild, logging, monitoring
2. **SA created:** `contextflow-run@contextflow-506414.iam.gserviceaccount.com`
3. **IAM granted to that SA:**
   - `roles/datastore.user`
   - `roles/logging.logWriter`
   - `roles/aiplatform.user`
   - `roles/monitoring.metricWriter`
4. **Code/config tweaks (local, uncommitted):**
   - `app/llm/gemini.py` — `CF_VERTEX_LOCATION` support (Vertex region ≠ Run region)
   - `deploy/cloudrun-durable.yaml` — filled with real project / SA / `contextflow-poc` / Vertex env placeholders (`CF_USE_VERTEX=0` for first durable deploy)

**Not done:** Firestore DB create, image build, `contextflow-durable` deploy, durability/Vertex/multi-WS scripts, logs/monitoring evidence, `docs/REAL_GCP_POC.md`, local validation sweep.

---

## Resume checklist (in order)

### 1. Verify IAM stuck

```bash
gcloud projects get-iam-policy contextflow-506414 \
  --flatten="bindings[].members" \
  --filter="bindings.members:contextflow-run@contextflow-506414.iam.gserviceaccount.com" \
  --format="table(bindings.role)"
```

### 2. Create Firestore (native, POC-labeled)

```bash
gcloud firestore databases create \
  --database=contextflow-poc \
  --location=asia-south1 \
  --type=firestore-native \
  --project=contextflow-506414
```

Then local CRUD via `FirestoreMemoryStore` + ADC (`CF_FIRESTORE_DATABASE=contextflow-poc`) — isolation, idempotency, supersession. **No FakeFirestore.**

### 3. Deploy authenticated durable Cloud Run

- Build from **working tree** (Phase 8 store code is uncommitted; do not deploy bare `8cc5539` alone).
- Service name: `contextflow-durable`
- SA: `contextflow-run@…`
- **No** `--allow-unauthenticated`
- Grant invoker to operator: `roles/run.invoker` for `user:09.gaganacm@gmail.com`
- First revision: Firestore on, Vertex **off**, `CF_EMBED_LOCAL=1`
- Verify: `/healthz`, `/docs`, auth `POST /turn`, unauth rejected

### 4. Real durability (`eval/cloud_poc/real_cloud_run_durability.py`)

- Real Cloud Run + real Firestore only
- A: auth + outfit + black→navy; B: Docker; redeploy revision to recycle instance; return to A
- Capture machine-readable results

### 5. Vertex (tight budget)

- Redeploy with `CF_USE_VERTEX=1`, `CF_LLM_EXTRACT=1`, models `gemini-2.5-flash-lite`, `CF_VERTEX_LOCATION=us-central1`, `CF_EMBED_LOCAL=1`
- Keep ≤20 `generate_content` (~propose+extract+answer ≈ 3/turn → ~6 full Vertex turns max)
- Routing still frozen gate; Vertex never ACT/CLARIFY authority

### 6. Compact 10-workstream HTTP scenario (~20–30 turns)

- Prefer Mock for volume; Vertex only within remaining call budget
- Prove isolation + reconstruction, not “natural chat accuracy”

### 7. Logs / light monitoring / security / cost notes → `docs/REAL_GCP_POC.md`

### 8. Local gate before any commit

```bash
pytest -q
python -m app
python -m eval.demo
python -m eval.product_demo
git diff --check
# routing hashes vs 8cc5539
```

**Still: do not commit/push until explicitly asked.**

---

## Hard rules (unchanged)

Do not touch: `gate.py`, `referent.py`, `scorer.py`, `config.py`, TAU/DELTA/HYST/W_*.  
No public durable invoke, no SA keys, no Vector Search, no silent Firestore→memory fallback.

---

## Cost note so far

API enable + SA/IAM only — no Firestore writes, no Run deploy, no Vertex calls yet this phase.
