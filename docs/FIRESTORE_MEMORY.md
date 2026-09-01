# Firestore memory schema (ContextFlow)

Firestore is **persistence only**. It is not a router, scorer, or ACT/CLARIFY authority.

## Collection structure

```
conversations/{conversation_id}/memory/{memory_item_id}
conversations/{conversation_id}/meta/namespace
conversations/{conversation_id}/idempotency/{idempotency_key}
conversations/{conversation_id}/workstreams/{workstream_id}   # Phase 10
conversations/{conversation_id}/meta/registry                 # Phase 10
```

Workstream registry schema: `docs/WORKSTREAM_DURABILITY.md`.

Conversation id is the document path namespace. Cross-conversation reads are
impossible through `FirestoreMemoryStore` (each store instance is bound to one id).

## Document identity

- **memory item id**: stable `MemoryItem.id` (writer-assigned). Document id = item id.
- **idempotency key**: writer `idempotency_key` (hash of conversation+turn+patch). Document id = key.
- **meta/namespace**: singleton per conversation for version + last commit fingerprint.

## Fields (memory documents)

Exact `MemoryItem` fields:

| Field | Notes |
|---|---|
| `id`, `kind`, `text` | Canonical assertion |
| `source_turn` | Provenance turn |
| `workstream_id`, `referent_id`, `slot` | Workstream isolation |
| `status` | `asserted` \| `superseded` \| `retracted` |
| `valid_from_turn`, `valid_to_turn` | Lifecycle bounds |
| `superseded_by` | Successor item id when superseded |
| `proposer`, `proposal_confidence`, `version` | Provenance |
| `conversation_id` | Must match path namespace |
| `provenance`, `uncertain`, `idempotency_key` | Audit / retry |

Malformed / unknown kinds / status / conversation mismatch → **fail closed** (`StorageError`).

## Idempotency strategy

1. Before write, load `meta/namespace`.
2. If `last_turn == turn` and item ids or keys match → return current version (no-op).
3. If same turn with different content → `DuplicateTurnError`.
4. Else batch-write memory docs + idempotency docs + bump `version`.

Optimistic concurrency: `expected_version` must equal `meta.version` or `StaleNamespaceError`.

## Supersession representation

Append-only: old item remains with `status=superseded` and `superseded_by=<new_id>`.
New item `status=asserted`. Working context uses `asserted()` only; history via `historical()`.

## Query patterns

| Need | Pattern |
|---|---|
| Current working set | Stream `memory/`, filter `status == asserted` (+ workstream) |
| Audit / history | Stream `memory/`, include superseded/retracted |
| Lookup by id | `memory/{id}.get()` |
| Lookup by idempotency | `idempotency/{key}` → `item_id` → get |

No collection-group queries required for the POC. No vector index. No graph edges.

## Indexes

POC uses full stream + in-process filter. If volume grows, add a composite index on
`(workstream_id, status)` — **not required for initial POC**.

## Security model

- Runtime SA: least-privilege Firestore access to this database only.
- Prefer security rules denying client SDK access; server (Cloud Run) uses Admin SDK + ADC.
- Store API never returns another conversation’s documents (path-bound client).

## Failure behavior

| Failure | Behavior |
|---|---|
| Network / Firestore error | `StorageError` — surface to caller; no silent fallback |
| Malformed document | `StorageError` — fail closed |
| Wrong conversation_id on item | reject commit / reject read |
| Missing dependency | `StorageError` at client init |

Never fall back to another conversation’s state or to in-memory silently.

## Migration / backfill

- Greenfield POC: empty collections.
- No automatic migration from in-memory demo state.
- Backfill (if ever): write MemoryItem docs + rebuild meta version from max commit order — out of scope until approved.

## Current status (Phase 14)

Firestore memory **and** the workstream registry are the durable backends for the production-shaped research POC (`CF_MEMORY_BACKEND=firestore`).

- Schema: this doc + `docs/WORKSTREAM_DURABILITY.md`
- Reviewer walkthrough: `docs/CLOUD_POC_REVIEWER.md`
- Phase 11 historical E2E narrative: `docs/END_TO_END_GCP_PROOF.md`
- Current tip evidence: `eval/out/phase14_gcp_validation.json` (revision end `contextflow-durable-00029-h74`)

Harnesses use authenticated HTTP only — no direct document writes to manufacture evidence. **Not production-ready.**
