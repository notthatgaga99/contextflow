# Workstream durability (Phase 10)

## Problem (was process-local)

| Component | Before Phase 10 | After Phase 10 (`CF_MEMORY_BACKEND=firestore`) |
|---|---|---|
| Memory items | Firestore | Firestore |
| Workstream registry (task cards) | In-process only | **Firestore** |
| Engine routing state | Rebuilt from registry | Reloaded from Firestore |
| `last_selected_referent` | In-process | `meta/registry` |

Without durable registry, a Cloud Run instance replacement could reload memory but lose workstream **identity** — routing could not reconstruct which threads existed.

## Authority boundary (unchanged)

```
Extractor     → proposes memory patches only
MemoryWriter  → commits memory
Registry      → persists workstream identity/state
ContextFlow   → routes (frozen gate/referent/scorer)
WC Builder    → projects memory for selected workstream
generate()    → answers only; never mutates registry or memory
```

## Firestore schema

```
conversations/{conversation_id}/workstreams/{workstream_id}
conversations/{conversation_id}/meta/registry
```

### Workstream document fields

| Field | Purpose |
|---|---|
| `id`, `title`, `status` | Identity + lifecycle (`active`/`paused`/`resolved`/`abandoned`) |
| `anchor` | `goal`, `open_loops`, `decisions`, `constraints`, `entities` |
| `retrieval_cues` | Routing cues (not memory content) |
| `item_ids` | Optional pointers to memory items |
| `last_active_turn`, `mention_turn` | Activity clocks |
| `loop_mention_turns` | Per-loop mention clocks |
| `created_at`, `updated_at`, `version` | Provenance |
| `conversation_id` | Must match path namespace |

Memory text remains in `memory/` documents only — not duplicated in registry.

### Meta/registry

```json
{
  "conversation_id": "...",
  "last_selected_referent": "E.loop1",
  "workstream_count": 10
}
```

## Operations

| Operation | Behavior |
|---|---|
| `add` | Create workstream; idempotent if identical |
| `mark_active` | Pause others, activate one; persist all changed |
| `record_mention` | Update mention clocks |
| `mark_abandoned` | Close workstream; memory remains auditable |
| `apply_update` | Anchor delta (legacy path) |
| Load on init | Stream `workstreams/` into cache |

Fail-closed on malformed docs (`StorageError`). No cross-conversation reads.

## Configuration

```bash
CF_MEMORY_BACKEND=memory      # InMemoryMemoryStore + InMemoryRegistry (default)
CF_MEMORY_BACKEND=firestore   # FirestoreMemoryStore + FirestoreRegistry
CF_SEED_TEN=1                 # Ten-workstream engineering fixture (cloud resurrection)
CF_SEED_E2E=1                 # Four-workstream E2E fixture (A auth / B outfit / C Lisbon / D deploy)
```

## Tests

- `tests/test_firestore_registry.py` — FakeFirestore unit tests
- `eval/cloud_poc/workstream_resurrection.py` — real Cloud Run + Firestore
- `eval/cloud_poc/ten_thread_resurrection.py` — 10-thread return proof
- `eval/cloud_poc/end_to_end_resurrection.py` — Phase 11 Vertex E2E + revision survival

## Product claim (precise)

**DEMONSTRATED:** Workstream identity + memory survive Cloud Run revision replacement; conversation isolation; supersession (when extraction succeeds); working-context reconstruction; full HTTP path with Vertex extract + answer.

**TESTED:** Engineering fixtures (synthetic/adversarial), not natural-chat accuracy.

**NOT YET:** Production SLO, multi-region HA, organic user studies. (Vertex 429 under revision-bump stress: see Phase 14.)

## Phase 12 — Extractor stabilization (2026-08-31) — historical

- Duplicate recall assertions: fixed in `LlmMemoryExtractor` (recall abstention + redundant patch filter)
- Repeatability harness: `eval/cloud_poc/e2e_repeatability.py`
- Dynamic workstream audit: `docs/DYNAMIC_WORKSTREAM_DESIGN.md`
- Cloud revision: `contextflow-durable-00012-sz7` (image `poc4-stabilize`)
- Gate result **at Phase 12 (historical):** duplicate decisions **PASS** (0/10); correction extraction **FAIL** (**2/10**). Superseded by Phase 13/14.

## Phase 13 — Dynamic NEW workstream (2026-08-31) — historical baseline

**DEMONSTRATED (Phase 13):**
- Organic NEW without seed fixtures (`CF_SEED_*=0`)
- Registry card created on frozen gate `NEW` before extraction
- Multi-topic creation (T1/T2/T3), return, revision survival
- Harness: `eval/cloud_poc/dynamic_workstream_e2e.py` — **5/5 NEW created**, 4/5 memory post-restart

**TESTED:** `tests/test_dynamic_new_workstream.py`

**Phase 13 gap (historical):** 4/5 memory persistence after revision (rep-02 Vertex abstain / empty extract). Closed locally then re-proven on GCP in Phase 14 — see below.

## Phase 14 — Reliability (local implementation)

- `try_parse_new_focus_fact` for NEW + `focus_workstream_id` only
- `extract_committed` on `/turn` response
- Isolation harness: pause + capped retries on 429/`turn_failed` 500; do not mask failures as OK
- Routing / MemoryWriter freeze: unchanged vs `8cc5539`

## Phase 14 — Real GCP validation (2026-08-31) — current

**DEMONSTRATED:** correction **10/10**; supersession **10/10**; duplicate current decisions **0**; working context **10/10**; contamination **0**; isolation **10/10 HTTP 200 / 0 leaks**; dynamic NEW creation **10/10**; dynamic memory persistence pre-restart **10/10**; dynamic revision survival **9/10** (1× Vertex 429); dynamic return **9/10** error-free.  
**Seed flags:** OFF. **Image:** `poc6-phase14`. **Revision end:** `00029-h74`.  
**Artifact:** `eval/out/phase14_gcp_validation.json`  
**NOT YET:** zero 429 under continuous revision-bump stress; production SLO / organic chat.
