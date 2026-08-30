# Memory semantics (v1)

**Date:** 2026-08-30  
**Authority:** `MemoryWriter` is the deterministic memory authority. The LLM proposes patches only. ContextFlow (gate/resolver) is the routing authority. The compiler builds the context package. `generate()` is answer-only.

## Representation

| Field | Role |
|---|---|
| `MemoryItem` | Canonical stored assertion with lifecycle status |
| `MemoryPatch` | Proposed change; not canonical until `validate` + `commit` |
| `kind` | `fact`, `decision`, `constraint`, `entity`, `preference`, `event`, `correction` |
| `slot` | Optional key for supersession within a workstream/referent |
| `status` | `asserted` \| `superseded` \| `retracted` |
| `provenance` | Required on commit: `conversation:{id}:turn:{n}:proposer:{who}` |
| `source_turn` | Turn that introduced the patch |
| `workstream_id` / `referent_id` | Association to open workstreams and loops |
| `uncertain` | If true on a patch → **writer rejects** (never active memory) |

Goals and unresolved objectives live on `Task.anchor` (registry). Memory items carry decisions, constraints, facts, entities, preferences, and corrections.

## Writer operations

### ASSERT (`action=assert`)

Creates **current** state. New `MemoryItem` with `status=asserted`. If `slot` matches an existing asserted peer, the prior item is **superseded** (see SUPERSEDE). Unkeyed `decision` conflicts without `slot`/`supersedes_id` → **reject** (no silent winner).

### SUPERSEDE (implicit)

Triggered when an ASSERT shares `slot` (+ workstream/referent) with an existing asserted item. Prior item → `status=superseded`, `superseded_by` set, `valid_to_turn` set. History is **append-only**; superseded rows remain auditable via `store.historical()`.

Peer kinds for slot supersession: `decision` ↔ `correction`.

### RETRACT (`action=retract`, `retract_id`)

Invalidates a previously asserted item. Target → `status=retracted`. Requires known item id.

### UNCERTAIN (`uncertain=true` on patch)

Does **not** become active working memory. Writer **rejects** at validate. Extractor should return empty/`uncertain` result instead of proposing uncertain patches.

### ABANDON (`action=abandon`, `workstream_id`)

Closes a workstream: registry `Task.status → abandoned`. **No memory rows deleted.** Abandoned workstreams are excluded from `open_tasks()` / retriever candidates. Existing items remain in the store for audit.

### CORRECT (`kind=correction`, ASSERT + slot)

Creates the new asserted state and links to superseded state via slot-based SUPERSEDE (same as decision correction). Historical value remains auditable.

## Separation of concerns

```
MemoryStore     → accumulated user state (all statuses)
Retriever         → candidate workstreams (open only)
ContextFlow       → task/referent + ACT/CLARIFY/SWITCH/RETURN
WorkingContextBuilder → project asserted, non-uncertain items for selected task/referent
ContextCompiler   → ContextPackage for the answer model
LLM.generate()    → answer only; must not commit memory
MemoryExtractor   → proposes patches; must not route or write store
```

## Working set rules

- Only `status=asserted` items are projected.
- `uncertain=true` items never appear in working context.
- Superseded and retracted items are excluded.
- Items from other workstreams are excluded (listed in `excluded_workstreams`).

## Not in v1

- Graph / vector database
- Durable cross-restart storage (in-memory only)
- Firestore / Vector Search (until explicitly required)
