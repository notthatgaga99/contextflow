# Phase 14 forensic note — Turn 3 routing (NEW vs CONTINUE)

**Scope:** documentation only. Routing files remain frozen at `8cc553983b45702ff16c071678f9bdc5b9d26fe3`.  
**Do not** retune gate / referent / scorer / config.

---

## Observed

1. **Dynamic NEW harness (Phase 14 tip)**  
   Script turn 3 is a third novel topic: *“Also I need to plan a weekend hiking trip in the Dolomites.”* (`eval/cloud_poc/dynamic_workstream_e2e.py`).  
   Phase 14 artifact shows turn 3 `transition=NEW` on completed reps (`eval/out/dynamic_workstream_e2e.json`).

2. **Frozen-routing edge cases (forensic review)**  
   Under the same frozen gate, short or cue-overlapping utterances (for example color-only or sibling-401 vocabulary) can still resolve as **CONTINUE** / **SWITCH** to an already-open workstream when mention clocks and retrieval cues dominate — even if a human reader might frame the line as “another new thing.”  
   The LLM proposal is soft; it does **not** choose ACT/CLARIFY/NEW.

## Expected

With routing frozen at `8cc5539`, transitions are produced by gate + referent + scorer from the proposal, open cards, and cues. Phase 13/14 pipeline changes (NEW-before-extract, `focus_workstream_id`, correction parsers, `extract_committed`) do **not** alter those thresholds.

## Why it was not changed

Retuning cues or gate thresholds would break the routing freeze and invalidate prior PoC evidence. Phase 14 intentionally fixed extract/harness honesty (empty `extract_ok`, Vertex 429 handling), not routing policy.

## Classification

**Known limitation** of frozen cue/recency routing on sparse or overlapping language — **not** an implementation regression in MemoryWriter, Firestore registry, or the Phase 13 NEW workstream pipeline.

**Not claimed:** organic-chat routing accuracy; that every human-intended “new topic” yields `NEW`.
