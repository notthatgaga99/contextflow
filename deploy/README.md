# Cloud Run deploy notes

Two identifiable configurations:

| File | Tier | Memory | Auth default |
|---|---|---|---|
| `deploy/cloudrun.yaml` | **Demo** | in-memory | Public invoke = demo boundary |
| `deploy/cloudrun-durable.yaml` | **Durable POC** | Firestore | **Authenticated** (invoker IAM) |

**Neither file has been applied in Phase 8.** Do not deploy without an approved plan.

---

## Demo (`cloudrun.yaml`)

- `CF_DEMO_ONLY=1`, `CF_MEMORY_BACKEND=memory`, `maxScale: 1`
- MockLLM / smoke fixture for deterministic presentation
- Process-local memory — restart loses state

## Durable POC (`cloudrun-durable.yaml`)

- `CF_MEMORY_BACKEND=firestore`
- Dedicated runtime SA (`contextflow-run@…`)
- `containerConcurrency: 8`, `minScale: 0`, `maxScale: 3`
- Health: `/healthz` startup + liveness probes
- Graceful shutdown: uvicorn SIGTERM drain within `timeoutSeconds`
- Structured redacted logs (`event=turn_decision`, correlation / request id)
- Vertex/Gemini **off** until an explicit smoke with cost ceiling

### Authenticated invocation (required)

```bash
# Do NOT use --allow-unauthenticated for durable POC.
gcloud run services replace deploy/cloudrun-durable.yaml --region=$GCP_REGION --project=$GCP_PROJECT

gcloud run services add-iam-policy-binding contextflow-durable \
  --region=$GCP_REGION --project=$GCP_PROJECT \
  --member="user:YOU@example.com" \
  --role="roles/run.invoker"

TOKEN=$(gcloud auth print-identity-token)
curl -sS -H "Authorization: Bearer $TOKEN" \
  "https://SERVICE_URL/healthz"
```

### Non-root container

`Dockerfile` runs as UID `10001`. Compatible with Cloud Run gen2.

---

## IAM (commands only — do not apply in Phase 8)

See `docs/CLOUD_POC.md` § IAM. Least privilege:

- Firestore data access on the memory database/collection path
- `roles/logging.logWriter`
- optional `roles/monitoring.metricWriter`
- `roles/aiplatform.user` **only** if `CF_USE_VERTEX=1`

Never: Owner, Editor, project-wide Storage Admin, Compute SA Owner/Editor.
Never create service-account keys — use ADC / workload identity.

---

## Secret Manager

Only for real secrets (e.g. a developer Gemini API key for **local** non-Vertex runs).
Vertex on Cloud Run must use the runtime SA + ADC — **no** JSON key, **no** secret for ADC.

Local vs Cloud Run:

| Env | Auth |
|---|---|
| Local Mock | none |
| Local Gemini API | `GEMINI_API_KEY` from env / Secret Manager fetch — never commit |
| Cloud Run Vertex | workload identity (runtime SA) |

Secrets must not appear in git, logs, demo output, or exception messages.

---

## Observability

Turn logs include (redacted): `request_id`, `conversation_id_hash`, `latency_ms`,
`extract_status`, `memory_backend`, `memory_reads`/`writes`, current/history counts,
`selected_task`, `selected_referent`, `transition`, `package_status`, `answer_status`.

Never: raw user text, prompts, model responses, memory content, credentials.

Cloud Monitoring-oriented signals (document only until measured): turn latency,
turn errors, memory read/write failures, CLARIFY rate, storage failures.
**No SLO claimed until measurements exist.**
