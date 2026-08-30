# Cloud Run deploy notes (demo / research)

**Tier:** DEMO-READY / RESEARCH-PRODUCT — not production-ready.

## Runtime shape

| Item | Choice |
|---|---|
| LLM | MockLLM (`CF_SMOKE_FIXTURE=1`) for deterministic demo |
| Memory | In-memory (`CF_MEMORY_BACKEND=memory`) |
| Scale | `maxScale: 1` (process-local store) |
| Auth | Public invoke = **demo boundary** unless invoker IAM is configured |
| Secrets | None required for Mock path |

## Dedicated service account (recommended)

Create `contextflow-run@PROJECT_ID.iam.gserviceaccount.com` and grant **only**:

- `roles/logging.logWriter`
- `roles/monitoring.metricWriter` (optional)
- `roles/aiplatform.user` **only** if enabling Vertex later

Set `serviceAccountName` in `cloudrun.yaml`. Do **not** use Owner/Editor.

## Multi-instance / durability

In-memory `ConversationStore` is **process-local**. Cloud Run restart or
`maxScale > 1` does **not** share memory across instances. Durable multi-instance
semantics require a later storage adapter (NOT YET). See `docs/PRODUCT_DEMO.md`.

## Observability

Turn handlers emit redacted JSON logs (`event=turn_decision`) with correlation ID,
transition, task id, extract status, latency, and memory counts — never raw text.

## Deploy (optional; incurs GCP cost)

```bash
# Replace PROJECT, REGION, IMAGE
gcloud run services replace deploy/cloudrun.yaml --region=REGION
# or build+deploy via Cloud Build / your existing pipeline
```

Smoke after deploy: `GET /health`, `GET /docs`, one `POST /turn` with Mock path.
Do **not** run a 50-turn Vertex replay for the presentation demo.
