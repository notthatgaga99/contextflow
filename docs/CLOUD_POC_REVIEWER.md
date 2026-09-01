# Cloud POC — Technical Reviewer Walkthrough

**Status:** production-shaped research POC · **not production-ready**

This document is the **CLOUD TECHNICAL PROOF** path.  
It is **not** the local product demo.

---

## Two demos — do not conflate

| | LOCAL PRODUCT DEMO | CLOUD TECHNICAL PROOF |
|---|---|---|
| Purpose | Visual product narrative | End-to-end durability + Vertex path |
| Command | `python -m eval.product_demo --serve` | scripts under `eval/cloud_poc/` (below) |
| LLM | MockLLM / scripted extracts | Real Vertex (`gemini-2.5-flash-lite`) |
| Memory | In-process | Firestore `contextflow-poc` |
| Registry | In-process | Firestore workstreams |
| Network | Offline | Authenticated Cloud Run HTTPS |
| Determinism | Yes | No (model + infra variance) |
| Proves | “Leave a thought without losing it” in one window | Real persistence + reconstruction after revision change |
| Docs | `docs/PRODUCT_DEMO.md` | **This page** + `docs/END_TO_END_GCP_PROOF.md` |

Do **not** treat MockLLM UI success as Cloud proof.  
Do **not** treat Cloud harness JSON as a natural-chat accuracy benchmark.

---

## What this walkthrough proves

```
Cloud Run (authenticated HTTP)
  → Vertex extraction
  → MemoryWriter
  → Firestore memory
  → Firestore workstream registry
  → frozen routing (gate / referent / scorer)
  → WorkingContext
  → Vertex answer
  → Cloud Run revision replacement
  → reconstruction (same conversation_id)
```

**Authority (unchanged):** Vertex proposes/extracts/answers. Frozen ContextFlow decides ACT/CLARIFY. MemoryWriter commits memory. Generate does not mutate memory or registry.

---

## Deployed architecture (existing)

| Resource | Value |
|---|---|
| GCP project | `contextflow-506414` |
| Cloud Run | `contextflow-durable` @ `asia-south1` |
| Service URL | `https://contextflow-durable-cjraqyv4hq-el.a.run.app` |
| Auth | **Required** (IAM `roles/run.invoker`) — not public |
| Firestore | Native DB `contextflow-poc` @ `asia-south1` |
| Vertex | `gemini-2.5-flash-lite` @ `us-central1` |
| Runtime SA | `contextflow-run@contextflow-506414.iam.gserviceaccount.com` |
| Latest validated image (Phase 14) | `contextflow-durable:poc6-phase14` |
| Routing freeze | checkpoint `8cc5539` — do not modify gate/referent/scorer/config/MemoryWriter for this review |

Separate in-memory demo service (if present) is **not** this proof path.

---

## Prerequisites (reviewer machine)

1. `gcloud` authenticated to project `contextflow-506414`
2. Identity that can invoke Cloud Run (`roles/run.invoker` on `contextflow-durable`)
3. Python deps from `requirements.txt`
4. Willingness to incur **Vertex + Cloud Run + Firestore** cost (use harness ceilings)

**Never** paste identity tokens, SA keys, or raw model responses into tickets/docs.

```bash
gcloud config set project contextflow-506414
gcloud auth login          # if needed
gcloud auth application-default login   # if scripts need ADC for Firestore smoke
```

---

## Exact review script (recommended order)

### 0) Confirm service is authenticated and durable

```bash
# Expect 403 without token
curl -s -o /dev/null -w "%{http_code}\n" \
  https://contextflow-durable-cjraqyv4hq-el.a.run.app/health

# Expect 200 with identity token
TOKEN=$(gcloud auth print-identity-token)
curl -s -H "Authorization: Bearer $TOKEN" \
  https://contextflow-durable-cjraqyv4hq-el.a.run.app/health
```

**Inspect in JSON (metadata only):**

- `memory_durable: true`
- `memory_backend: firestore` (or equivalent durable flag)
- `vertex_enabled` / extract mode indicating LLM when Vertex is on
- **Do not** expect or paste credentials

### 1) Full path + revision survival (primary technical proof)

```bash
python -m eval.cloud_poc.end_to_end_resurrection
```

**Artifact:** `eval/out/end_to_end_resurrection.json`  
**Narrative report:** `docs/END_TO_END_GCP_PROOF.md`

**Evidence to inspect (fields / booleans — not raw answers):**

| Check | Where |
|---|---|
| Authenticated HTTP turns | per-turn status / HTTP codes in artifact |
| Vertex extract accepted | `extract_ok` (or equivalent) per turn |
| MemoryWriter → Firestore | durable memory counts / asserted + superseded |
| Registry durability | workstream titles / counts survive restart |
| Frozen routing transitions | `transition`, `selected_task` / referent ids |
| WorkingContext | `GET` working-context projection: CURRENT decisions, EXCLUDED other threads |
| Vertex answer path | `answer_status` / `package_status` (hashes OK; **no raw text required**) |
| Revision replacement | `revision_before` ≠ `revision_after_bump` |
| Reconstruction | post-bump return still shows navy current + black history; unrelated excluded |
| Isolation | separate conversation_id does not leak |

### 2) Correction + reconstruction repeatability (Vertex variance)

```bash
python -m eval.cloud_poc.e2e_repeatability
```

**Artifact:** `eval/out/e2e_repeatability.json`  
**Inspect:** per-run correction / supersession / working_context / contamination / isolation gates.  
Phase 14 validated **10/10** correction layers on image `poc6-phase14` (see `eval/out/phase14_gcp_validation.json`).

### 3) Dynamic NEW workstream (seed OFF)

```bash
python -m eval.cloud_poc.dynamic_workstream_e2e
```

**Artifact:** `eval/out/dynamic_workstream_e2e.json`  
**Inspect:** NEW workstreams created via HTTP path; memory persisted; revision survival counts; seed flags OFF.

### 4) Optional supporting smokes

```bash
python -m eval.cloud_poc.firestore_crud_smoke      # Firestore CRUD + isolation (ADC)
python -m eval.cloud_poc.vertex_cloud_smoke        # short Vertex HTTP smoke
python -m eval.cloud_poc.real_cloud_run_durability # earlier durability path
```

Use cost ceilings already coded in harnesses (`CF_POC_MAX_USD`, call caps). Stop if ceiling hit.

---

## Observability (Cloud Logging) — redacted

```
resource.type="cloud_run_revision"
resource.labels.service_name="contextflow-durable"
textPayload:"turn_decision"
```

**Expect present:** `request_id`, hashed conversation id, `selected_task`, `transition`, memory counts, `extract_ok`, `package_status`, `answer_status`, latency.

**Must be absent:** raw user text, prompts, model responses, memory item text, credentials.

---

## Routing freeze check (local, no GCP)

```bash
git diff 8cc553983b45702ff16c071678f9bdc5b9d26fe3 -- \
  app/router/gate.py app/router/referent.py \
  app/retrieval/scorer.py app/config.py app/memory/writer.py
```

Expect **empty** for a freeze-compliant review.

---

## What to claim / what not to claim

**Allowed (with artifacts):**

- Authenticated Cloud Run serves the ContextFlow turn path.
- Vertex extraction + MemoryWriter persist to Firestore.
- Workstream registry persists in Firestore.
- Frozen routing selects workstreams; WorkingContext reconstructs CURRENT / HISTORY / EXCLUDED.
- Vertex answer path runs with a context package (status/hash evidence).
- Memory + registry survive Cloud Run **revision replacement**.
- Cross-conversation isolation holds in the harness checks.

**Not allowed:**

- “Production-ready”
- Natural-chat accuracy / benchmark scores from this POC
- Equating local MockLLM demo with Cloud proof
- Publishing credentials, identity tokens, or raw model outputs

---

## Known limitations

- Vertex extraction is non-deterministic; use repeatability harness + published Phase 13/14 gates.
- Infra flakes (e.g. Vertex 429) can appear as HTTP 500s in isolation turns — report as infra, not silent pass.
- Cost estimates in JSON are harness estimates, not invoices.
- Seed flags: prefer **OFF** for Phase 13+ dynamic/correction proofs; older E2E may use card-only seeds — read the artifact’s env section.
- Not multi-region HA, not SLO, not load-tested.

---

## Deep dives (optional)

| Topic | Doc |
|---|---|
| Full E2E evidence narrative | `docs/END_TO_END_GCP_PROOF.md` |
| GCP resources / IAM / phases | `docs/REAL_GCP_POC.md` |
| Registry durability | `docs/WORKSTREAM_DURABILITY.md` |
| Memory schema | `docs/FIRESTORE_MEMORY.md` |
| Local product UI (separate) | `docs/PRODUCT_DEMO.md` |
