# Cloud cost discipline (through 7 September)

**Rule:** before every Vertex/GCP experiment, fill the table below. No large sweep. Do **not** re-run the 135-cell propose grid.

---

## Pricing check (2026-08-29)

Sources consulted: Google AI / Vertex Flash-class listings (third-party aggregators aligned with Google Developer API table).

| Model | Input / 1M tokens | Output / 1M tokens |
|---|---|---|
| `gemini-2.5-flash-lite` | **$0.10** | **$0.40** |
| `gemini-2.5-flash` (reference) | ~$0.30 | ~$2.50 |

Smoke models (env): `CF_LITE_MODEL=gemini-2.5-flash-lite`, `CF_GEN_MODEL=gemini-2.5-flash-lite` (both Lite — extract + propose + answer).

---

## GCP spend so far (pre-Vertex, this project)

Inspected 2026-08-29 on `contextflow-506414` (billing account linked: `019C94-CFAD83-F56E65`).

| Resource | Evidence | Vertex? | Est. spend |
|---|---|---|---|
| Cloud Build | 1 successful source build (`94512798-…`) | no | cents |
| Artifact Registry | `cloud-run-source-deploy` ~**88 MB** | no | cents |
| Cloud Run | revision `contextflow-00001-zmp`, min=0, MockLLM smoke traffic | no | cents |
| Vertex AI / Gemini | **no** `aiplatform.googleapis.com` audit/log hits in 90d | — | **$0** |

Exact dollar invoices were not scraped from the Billing console API; figures above are resource-inventory estimates only.

---

## Already spent (do not repeat)

| Experiment | Calls | Prompt / candidate tokens (reported) | Estimate | Why it existed |
|---|---|---|---|---|
| Gemini Flash-Lite scale + smoke | 135 propose | 41,265 + 13,302 | ~$0.007 | Hosted proposer ≠ Mock; wrong-ACT still 0 on that grid |

Do **not** re-run `eval/gemini_validation.py` at 128/135 cells.

---

## Approved tiny Vertex smoke (local client) — execute only with `CF_VERTEX_SMOKE=1`

**Purpose:** prove `conversation → Vertex extract → Writer → Store → frozen CF → package → Vertex answer`. Not accuracy. Not a grid.

| Item | Value |
|---|---|
| Probes | **3** (assertion · heterogeneous return · ambiguous/sibling) |
| Calls / probe | extract `generate` + propose + answer `generate` = **3** |
| Max calls | **9** (hard cap **12**) |
| Embeddings | **0** |
| Input tokens (est.) | ≤ **12k** (3× ~1.2k extract + 3× ~0.5k propose + 3× ~0.8k answer, padded) |
| Output tokens (est.) | ≤ **3k** |
| Max USD @ Flash-Lite $0.10 / $0.40 | `12k×0.10/1M + 3k×0.40/1M` = **$0.0024** |
| Safety envelope | **&lt; $0.03** (includes retries / longer packages) |
| Stop if | realized cost materially above envelope, or extractor begins changing gate math |

Script: `python -m eval.vertex_smoke` (prints estimate; runs only if `CF_VERTEX_SMOKE=1`).

---

## Approved Cloud Run hosted Vertex smoke — only after local Vertex smoke OK

| Item | Value |
|---|---|
| HTTP `/turn` | **≤ 4** (isolation + 3 probes) |
| Vertex calls | ≤ **12** (extract + propose + answer per turn) |
| Max USD | **&lt; $0.05** Flash-Lite envelope |
| Runtime SA | `cf-run` + `roles/aiplatform.user` only |
| Secrets in image | **none** (ADC / Vertex) |

Script: `CF_E2E_SMOKE=1 CF_SMOKE_URL=https://… python -m eval.production_smoke` (or dedicated probe notes in `FINAL_VALIDATION.md`).

---

## Local Ollama (already done; not Vertex)

| | |
|---|---|
| Extractor probe | 5 fixture turns; quality failed (extraction layer) |
| Answer consume | up to 9 local generates |

---

## Approval gate

If a proposed run is not in this file with numbers, **do not run it**.
