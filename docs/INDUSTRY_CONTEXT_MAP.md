# Industry context map — Cursor / Claude / peers vs ContextFlow

**Purpose:** Chart how agentic products manage context, what nuance ContextFlow owns, and the locked host integration.

**Product lock:** Bet A = working-memory **switch** (bind → L1). Not memory SaaS. Not a Cursor/Claude clone.

---

## 1. Landscape (one row per system)

| System | Working context | Durable memory | Near-miss hop | Role vs CF |
|--------|-----------------|----------------|---------------|------------|
| **Cursor** | Agent + open files; Projects share context files across agents | Project learnings / prefs grow over time | Implicit / model-led | **Shell** — coding loop |
| **Claude** | Chat window; Projects = parallel threads + auto-compact | Account memory + project `MEMORY.md` | Search / remember | **Worker / consumer** |
| **ChatGPT** | Single chat context; new chat when full | Saved memories + preferences | Soft relevance | Consumer |
| **LangGraph** | Checkpoint by `thread_id` | Cross-thread store | You implement | **Best host** for a CF node |
| **CrewAI / AutoGen** | Crew / conversation state | Opt-in persist / `save_state` | Weak / none | Optional host |
| **ContextFlow** | Bound **L1 only** after hop | Planes + Writer (support) | Genre \(S\) vs identity \(I\) + CLARIFY | **Middleware wedge** |

---

## 2. Layer split (do not collapse)

```text
┌─────────────────────────────────────────────────────────┐
│  Orchestration shell  (Cursor / Claude Projects / LG)   │  ← they own
├─────────────────────────────────────────────────────────┤
│  BIND / CLARIFY / NEW   ← genre S vs identity I + slots │  ← YOU own
├─────────────────────────────────────────────────────────┤
│  L1 compact expose (one hop only)                       │  ← YOU own
├─────────────────────────────────────────────────────────┤
│  Generate + tools  (any model / agent loop)             │  ← they own
│  Tools MUST NOT re-bind                                 │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Locked decision: framework-agnostic facade (Approach A)

**Shipped:** in-process + HTTP share one door. No `langgraph` / `crewai` package in this repo.

| Piece | Location |
|-------|----------|
| Facade | `app/kernel/bind_api.py` → `bind_and_expose` |
| HTTP turn | `POST /turn` — answer + host fields (`interrupt`, `l1_expose`, …) |
| HTTP bind | `POST /bind` — full `BindExposeResult` JSON for shells that own generate |
| Agent shell | `app/agent/turn.py` → bind then tools (skipped on interrupt) |
| Latency | `resolve_llm_mode()` / `CF_LLM_MODE`; Mock via `scripts/env_mock_local.ps1` |

### Contract

```text
bind_and_expose(store, extractor, conversation_id=, message=, turn=) →
  BindExposeResult:
    transition, task_id, l1_expose, clarify_question,
    discrimination, interrupt, latency_ms, answer, llm_mode, …
```

**Laws**

1. `interrupt=True` when `transition==CLARIFY` → host **pauses**; `answer` and `l1_expose` are null.  
2. On ACT/NEW/… host generate uses **`l1_expose` only**; never re-bind.  
3. Discrimination evidence always present for audit.

### Host adapter sketches (docs only — no vendor deps)

**LangGraph-shaped node (host writes this):**

```python
from app.kernel.bind_api import bind_and_expose

def contextflow_node(state, *, store, extractor):
    out = bind_and_expose(
        store, extractor,
        conversation_id=state["conversation_id"],
        message=state["message"],
        turn=state["turn"],
    )
    if out.interrupt:
        # Same idea as LangGraph interrupt(): pause for human
        return {"__interrupt__": out.clarify_question, **out.to_dict()}
    return {
        "task_id": out.task_id,
        "l1_expose": out.l1_expose,
        "transition": out.transition,
        "discrimination": out.discrimination,
    }
```

**Cursor / custom agent:** call `POST /turn` or in-process `bind_and_expose` before the model; if `interrupt`, show clarify UI.

**Claude-style coordinator:** one coordinator turn runs CF; workers receive only that `l1_expose`.

---

## 4. Nuance you bought (keep)

1. Relevance ≠ resolution (shared `401` ≠ which saga).  
2. Bind before assemble — wrong hop cannot be fixed by nicer L1.  
3. Generate sees one L1; tools never re-bind.  
4. Weak near-miss → CLARIFY (product-locked).  
5. Unique slot/entity → I-channel; shared slot name → genre.

---

## 5. Latency modes

| Mode | How | UI feel |
|------|-----|---------|
| `mock` | `. .\scripts\env_mock_local.ps1` | ~100ms turns |
| `vertex` | `. .\scripts\env_vertex_local.ps1` | paced ~6.5s/call |

`/health` reports `llm_mode` and `vertex_pace_s` (0 when mock).

---

## 6. Trust bar

```powershell
. .\scripts\env_mock_local.ps1
# I-channel embed boost on by default (CF_DISC_EMBED=1); hash embeds via CF_EMBED_LOCAL=1
pytest -m "trust or integration or h2 or organic" -q
python -m eval.discrimination.run_cases --json eval/out/discrimination_cases.json
python -m eval.discrimination.insights   # also writes eval/out/discrimination_plane.json
python -m eval.organic.run
python -m eval.ten_workstream.catalog_revive
```

Latest local freeze stamp: `docs/STABILITY_FREEZE.md` (exit codes only; not production accuracy).

Optional live: `. .\scripts\env_vertex_local.ps1` then `python -m eval.discrimination.vertex_smoke`.

---

## Related

- Bet A / study: `docs/CONCEPTS_REVIEW.md`
- Switch synthesis: `docs/WORKING_MEMORY_SWITCH_SYNTHESIS.md`
- Discrimination: `docs/THREAD_DISCRIMINATION_MODEL.md`
