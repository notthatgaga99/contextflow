# ContextFlow Cloud POC

**Thesis:** ContextFlow lets you leave a thought without losing it.

This document describes a **production-shaped POC** on Google Cloud — not a
production-scale guarantee and not a deployed system until explicitly approved.

---

## WHY

Chat history is not working memory. Transcripts bury decisions; models re-guess.
Users lose constraints when they switch tasks.

## WHAT

ContextFlow maintains **durable, evolving workstreams**: asserted facts and
decisions with lifecycle (supersession, retraction), scoped per conversation,
separated from routing and answer generation.

## ARCHITECTURE

```
HTTP (authenticated)
  → Cloud Run service
  → MemoryExtractor (proposer only)
  → MemoryWriter (authority + validation)
  → Firestore-backed MemoryStore
  → frozen ContextFlow (gate / referent / scorer)
  → WorkingContextBuilder
  → ContextPackage
  → Vertex answer (when enabled; answer model only)
```

Firestore is persistence only. It must not become a router.

## PROPERTIES

| Property | Meaning |
|---|---|
| Durable | Memory survives process restart when `CF_MEMORY_BACKEND=firestore` |
| Conversation-scoped | Store API cannot read another conversation |
| Auditable | Superseded/retracted items remain in history |
| Lifecycle-aware | Current projection uses asserted items only |
| Fail-closed | Malformed docs / storage errors surface explicitly |
| Model/routing separation | Vertex proposes extracts / answers; never ACT/CLARIFY |

## DEMO (product)

A user can leave one task, work on nine others, then return — working context
restores current decisions without stale superseded state. See product demo UI
and ten-workstream fixture for the narrative proof locally.

## CONFIGURATION

```bash
# Local default (tests)
CF_MEMORY_BACKEND=memory

# Durable POC
CF_MEMORY_BACKEND=firestore
GCP_PROJECT=...
GCP_REGION=...
CF_FIRESTORE_DATABASE=(default)

# Vertex (optional; smoke only — do not run broad experiments)
CF_LLM_EXTRACT=1
CF_USE_VERTEX=1
```

Auth: Application Default Credentials. No service-account JSON keys in git or image.

## BOUNDARY

This is a **production-shaped POC**, not an SLO, not multi-region HA, not a
claim of production readiness. Durable proof plan: `eval/cloud_poc/`.

**Phase 8 status:** implementation + docs + tests only.  
**Not done:** IAM apply, Firestore database create, Cloud Run deploy, Vertex smoke execution.

## IAM (document / commands only)

```bash
# Create dedicated runtime SA (do not apply until approved)
gcloud iam service-accounts create contextflow-run \
  --display-name="ContextFlow Cloud Run" \
  --project=$GCP_PROJECT

# Logging
gcloud projects add-iam-policy-binding $GCP_PROJECT \
  --member="serviceAccount:contextflow-run@$GCP_PROJECT.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"

# Firestore (prefer database-scoped custom role in production; POC may use datastore.user)
gcloud projects add-iam-policy-binding $GCP_PROJECT \
  --member="serviceAccount:contextflow-run@$GCP_PROJECT.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

# Vertex ONLY if CF_USE_VERTEX=1
# gcloud projects add-iam-policy-binding $GCP_PROJECT \
#   --member="serviceAccount:contextflow-run@$GCP_PROJECT.iam.gserviceaccount.com" \
#   --role="roles/aiplatform.user"
```

Do **not** grant Owner, Editor, Storage Admin, or elevate the Compute default SA.

## Secret Manager

Use only for actual secrets (e.g. local `GEMINI_API_KEY`). Vertex on Cloud Run
uses workload identity — no key secret required.

## Observability

See `deploy/README.md` and `app/obs.py`. No SLO until measured.

## Estimated cost (order-of-magnitude, idle POC)

| Resource | Rough monthly if idle / light |
|---|---|
| Cloud Run (min 0) | ~$0–few USD at low traffic |
| Firestore | free-tier friendly for tiny POC |
| Vertex smoke | pay-per-call — keep ceiling (see `eval/cloud_poc/`) |

Exact spend depends on region and traffic. Do not treat as a budget commitment.

## Deploy configs

- Demo: `deploy/cloudrun.yaml`
- Durable: `deploy/cloudrun-durable.yaml` (authenticated; Firestore)
