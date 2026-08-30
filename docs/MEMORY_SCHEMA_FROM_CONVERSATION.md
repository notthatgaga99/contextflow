# Working-memory schema from real conversation

**Status:** template. Fill only after `data/consented/session.json` exists.  
**Do not** add a large ontology first. Start from existing `Task` / `TaskAnchor`.

Frozen routing is unchanged. This document is about **what must be stored** so reconstruction is useful.

---

## Existing fields (PoC)

| Field | Role |
|---|---|
| goal | Unresolved objective |
| open_loops | Unresolved items |
| decisions | Already decided |
| constraints | Hard limits |
| entities | Names, places, versions |
| retrieval_cues | Lexical retrieval |
| mention / last_active / loop clocks | Referent / return |
| status active / paused / resolved | Workstream lifecycle |

---

## Empirical check (per real probe)

For each selected return, ask: **could the downstream agent continue if it saw only the compact package?**

If no, name the missing string and which column it belongs in:

| Probe | Human workstream | Required to continue | Present on card? | If missing, is it a new field or a missing extraction? |
|---|---|---|---|---|
| | | | | |

**Rule:** demonstrate the miss with a **real** utterance from the transcript (paraphrased in public docs) **before** proposing a schema change.

Pattern we will look for (not a fake transcript):

> User: “What did we decide about the dress?”  
> Routing: clothing workstream (correct).  
> Package: “pick an outfit” only.  
> Missing: “rejected black because of venue lighting.”  
> **Class:** extraction / representation, **not** TAU/DELTA.

That is the highest-value Sep 7 finding if it occurs.

---

## Phenomena to tag if they actually occur

Do not invent turns to fill the list.

- A → B → A  
- A → B → C → A  
- A → B → C → B  
- Multiple returns to the same workstream  
- Multiple loops on one workstream  
- Unrelated domain switch  
- Correction  
- Ambiguous return (CLARIFY appropriate)  
- Completed or abandoned workstream  
- Simultaneous unresolved workstreams  

---

## Verdict (after transcript)

- [ ] Current TaskAnchor is sufficient  
- [ ] Sufficient if we actually fill decisions/constraints (extraction gap)  
- [ ] Missing field X, shown by probe Y  

No Firestore/embeddings from this file alone.
