# Ten-workstream Vertex extraction comparison

**CONTROLLED ADVERSARIAL SYNTHETIC FIXTURE** — Phase 4 model comparison + Phase 5 extractor harden re-check.
Not organic or real-user evidence. Not a production accuracy claim.

**Question:** Is poor Phase-3 extraction primarily a small-local-model limitation, or a defect in the extraction contract/schema/pipeline?

## Before / after extractor harden (same 11 turns, Vertex Flash-Lite)

| | Phase 4 (pre-harden) | Phase 5A (post-harden) |
|---|---|---|
| Useful | 3 | **5** |
| Writer rejects (unknown referent) | 3 | **0** |
| Lifecycle navy supersedes black | no | **yes** |
| Uncertainty fail-closed | weak | improved (e08/e09) |
| Calls / cost | 11 / ~$0.000836 | **9** / ~$0.000823 |

Phase-5 extractor changes: omit invented `*.loopN` before writer; underspecified → no assert; auto `supersedes_id` for slotted decisions. Writer semantics unchanged.

## Methodology

- Same 11 Phase-3 turns; same `LlmMemoryExtractor` prompt/schema/writer/store
- Variable: model only (`qwen2.5:1.5b` recorded vs `gemini-2.5-flash-lite`)
- Anchored turns receive open workstream cards `[id] title/goal/loops` + asserted summaries
- e11 receives **no** workstream cards
- No probe gold, no expected labels, no ACT/CLARIFY choice, no ContextFlow routing
- No answer model, no embeddings, no propose calls

**Vertex model:** `gemini-2.5-flash-lite` @ `us-central1`
**Calls:** **9** extract · tokens in/out **5877**/**587** · est. cost **$0.000823** · elapsed **14.704s**

## Comparison summary

| | Ollama 1.5B (Phase 3) | Vertex Flash-Lite |
|---|---|---|
| Useful | **2** | **5** |
| Writer rejects | (see Phase 3) | **0** |
| Fabricated IDs dropped | (see Phase 3) | **0** |
| Lifecycle (navy supersedes black) | no | yes |

**Interpretation (A):** Vertex substantially better than 1.5B — evidence for model-capability limitation of the local model.

## Taxonomy (Vertex)

```{'USEFUL': 5, 'RECONSTRUCTION_FAILURE': 2, 'UNCERTAINTY_OK': 2, 'EMPTY_OK': 1, 'UNCERTAINTY_FAILURE': 1}```

## Per-turn

| id | category | patches | ws ok | writer | persist | recon | layer | vs 1.5B |
|---|---|---|---|---|---|---|---|---|
| e01_fact_jwt | simple_fact | 1 | True | ok | True | ok | USEFUL | USEFUL→USEFUL |
| e02_decision_dress | decision | 3 | True | ok | True | missing_required | RECONSTRUCTION_FAILURE | EXTRACTION_FAILURE→RECONSTRUCTION_FAILURE |
| e03_constraint_evening | constraint | 2 | True | ok | True | ok | USEFUL | USEFUL→USEFUL |
| e04_fact_orders_401 | similar_technical | 1 | True | ok | True | ok | USEFUL | EXTRACTION_FAILURE→USEFUL |
| e05_decision_alpine | decision | 1 | True | ok | True | ok | USEFUL | EXTRACTION_FAILURE→USEFUL |
| e06_travel_parking | unrelated_domain | 1 | True | ok | True | missing_required | RECONSTRUCTION_FAILURE | RECONSTRUCTION_FAILURE→RECONSTRUCTION_FAILURE |
| e07_correction_navy | correction_supersession | 1 | True | ok | True | ok | USEFUL | EXTRACTION_FAILURE→USEFUL |
| e08_uncertain_maybe | uncertain | 0 | True | ok | [] | n/a | UNCERTAINTY_OK | EXTRACTION_FAILURE→UNCERTAINTY_OK |
| e09_deictic_fix | deictic | 0 | True | ok | [] | ok | EMPTY_OK | EXTRACTION_FAILURE→EMPTY_OK |
| e10_ambiguous_other | ambiguous | 1 | True | ok | True | n/a | UNCERTAINTY_FAILURE | EXTRACTION_FAILURE→UNCERTAINTY_FAILURE |
| e11_unanchored_no_cards | unanchored | 0 | True | ok | [] | n/a | UNCERTAINTY_OK | EXTRACTION_FAILURE→UNCERTAINTY_OK |

## Critical turns

- **e02_decision_dress** [RECONSTRUCTION_FAILURE]: decision/E/color: black; constraint/E/dress_code: corporate/formal; constraint/E/event_time: evening event
- **e03_constraint_evening** [USEFUL]: constraint/E/dress_code: corporate/formal; constraint/E/event_time: evening event
- **e07_correction_navy** [USEFUL]: correction/E/color: navy
- **e08_uncertain_maybe** [UNCERTAINTY_OK]: (none)
- **e09_deictic_fix** [EMPTY_OK]: (none)
- **e10_ambiguous_other** [UNCERTAINTY_FAILURE]: correction/E/color: navy
- **e11_unanchored_no_cards** [UNCERTAINTY_OK]: (none)

## Lifecycle (e07 navy)

```json
{
  "black_historical": [
    {
      "id": "M1",
      "kind": "decision",
      "text": "black",
      "status": "superseded",
      "workstream_id": "E",
      "referent_id": "E.loop1",
      "slot": "color",
      "source_turn": 3,
      "provenance": "conversation:ten-extract-vertex:turn:3:proposer:extractor",
      "superseded_by": "M13"
    }
  ],
  "black_superseded": true,
  "navy_asserted": [
    {
      "id": "M13",
      "kind": "correction",
      "text": "navy",
      "status": "asserted",
      "workstream_id": "E",
      "referent_id": "E.loop1",
      "slot": "color",
      "source_turn": 32,
      "provenance": "conversation:ten-extract-vertex:turn:32:proposer:extractor",
      "superseded_by": null
    }
  ],
  "navy_in_working": true,
  "black_excluded_from_working": true
}
```


## What this proves

- Whether Flash-Lite outperforms 1.5B on the **same** extraction contract
- Whether supersession/uncertainty/unanchored fail-closed behave under Vertex

## What this does not prove

- Organic or consented-chat extraction quality
- Production robustness
- Routing quality (routing unused here)
- That the architecture is broken if Vertex also fails (may be context/contract)

## Status

| Claim | Status |
|---|---|
| Extract contract unchanged | IMPLEMENTED |
| Phase-3 1.5B limitation preserved | DEMONSTRATED |
| Tiny Vertex extractor comparison (11 turns) | DEMONSTRATED (this doc) |
| Organic extraction quality | NOT YET |

CONTROLLED ADVERSARIAL SYNTHETIC FIXTURE. Not organic/real-user evidence. Not a production extraction benchmark. Routing frozen and unused. Phase-3 qwen2.5:1.5b finding preserved.
