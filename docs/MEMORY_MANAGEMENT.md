# Context-aware memory management

ContextFlow is a **working-memory switch**. The frozen binder picks one hop; the
**MemoryManager** assembles **our planes** and exposes only **short-term (L1)**
to `generate()`.

## Stance: learn, don’t clone

We study how others separate working vs durable memory, retrieval vs binding,
and skills vs facts — then build **RB-WSR** as our control loop. We do **not**
copy vendor APIs, rename their tiers as our product identity, or hand routing
to “agent self-edited core memory” or multi-thread top-k.

| CF plane | What it means *here* |
|---|---|
| **SHORT_TERM** | Capped L1 after bind — only generate surface |
| **LONG_TERM** | Durable L2/L3/L5; semantic vs episodic kinds |
| **PROCEDURAL** | How-to `procedure` items; goal/loops stay on the card |
| **RELEVANT** | Query cold enrich on the **bound** hop only |
| **INDEX** | L4 cards for routing — not L1 body |
| **ARCHIVE** | L6/L7 catalog — opt-in import only |

**RB-WSR rule:** retrieval relevance ≠ referent resolution. RELEVANT never
replaces the binder (see `MEMORY_ARCHITECTURE_RESEARCH.md`).

**Thread discrimination (post-gate rail):** seemingly close threads that share
a common concept (e.g. both `401`) must stay distinct via *distinctive* cues;
surface-shifted or extended follow-ups on the active thread must CONTINUE even
when wording looks new or shared nouns are dropped. See
`app/router/thread_discriminate.py` and `pytest -m trust`.

### LONG_TERM kinds

| Kind | Subtype |
|---|---|
| `fact`, `preference`, `entity`, `decision`, `correction`, `constraint` | **semantic** |
| `event` | **episodic** |
| `procedure` | **procedural** plane (not LTM) |

### Procedural vs control

- **Control** on the card: `GOAL`, `SELECTED LOOP` / open loops.  
- **How-to** in L1 `PROCEDURAL:`: only `kind=procedure` steps.  
- Do not dump every open loop into `PROCEDURAL:`.

### Cold enrich hygiene

- Cold search may see L3 history.  
- Before L1 merge, **drop superseded hits whose slot is already asserted in CURRENT**.  
- Provenance: cold `item_id`s append to `memory_item_ids` / `source_event_ids`.

## Hard rules

1. `generate()` reads **SHORT_TERM only** (+ user message).  
2. RELEVANT must be **bound-scoped** — never multi-thread top-k.  
3. INDEX informs *which* hop; it does not dump sibling L2 into L1.  
4. ARCHIVE never auto-merges into L1.  
5. Gate / referent / scorer stay frozen.

## Flow

```text
message → BINDER (frozen) → workstream_id + referent
              ↓
        MemoryManager.assemble
          ├─ LONG_TERM   read_asserted (semantic + episodic)
          ├─ PROCEDURAL  how-to items (+ control on card fields)
          ├─ RELEVANT    search_cold → filter superseded-by-slot → merge
          └─ INDEX       list_open_threads (diagnostics only)
              ↓
        SHORT_TERM CompactNotation → generate(L1 + user message)
```

## Code

| Module | Role |
|---|---|
| `app/kernel/session.py` | **Canonical E2E turn** — `run_kernel_turn` (extract→bind→L1→answer) |
| `app/kernel/writes.py` | Bound-hop asserts (`assert_bound`) — tools/extract share Writer door |
| `app/memory/planes.py` | Planes, kinds, policy, design notes |
| `app/memory/manager.py` | `MemoryManager` / `ContextAwareMemory` |
| `app/memory/cold_search.py` | Bound cold rank + L1 filter + provenance |
| `app/context/working_memory_switch.py` | `assemble_bound_memory` / `expose_bound_thread` |
| `POST /turn`, `POST /agent/turn` | Both call the kernel (agent tools after bind only) |
| `GET /memory/planes` | Catalog + design stance |
| `GET …/compact-notation?query=` | L1 + plane diagnostics |

## Tests

```powershell
.\scripts\run_switch_trust.ps1
# or: pytest -m trust -q
pytest tests/test_memory_manager.py tests/test_memory_port_switch.py -q
```

`trust` is the switch-mastery adoption bar (Mock; no Vertex).

**Study guide:** [`CONCEPTS_REVIEW.md`](CONCEPTS_REVIEW.md) — Bet A, kernel, planes, discrimination, clarify.
