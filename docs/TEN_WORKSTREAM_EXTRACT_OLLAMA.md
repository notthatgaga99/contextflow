# Ten-workstream Ollama extraction

**CONTROLLED SYNTHETIC EXTRACTION EXPERIMENT** — local Ollama only. Not natural human-chat evidence. Not a production accuracy claim. No Vertex. Frozen routing unused.

**Model:** `qwen2.5:1.5b` · generates: **13** · elapsed **491.687s** · Vertex: **0**

## Path

extract → MemoryPatch → Writer.validate/commit → Store → WorkingContextBuilder (no ContextFlow routing in this experiment)

## Taxonomy

```{'USEFUL': 2, 'EXTRACTION_FAILURE': 8, 'RECONSTRUCTION_FAILURE': 1}```

- Useful: **2**
- Partial: **1**
- Writer rejects: **0**
- Fabricated IDs dropped: **1**
- Fail-closed OK (uncertain/empty cases): **2**
- Idempotency note: `True`

## Per-turn

| id | category | proposed | ws ok | writer | persist | recon | class |
|---|---|---|---|---|---|---|---|
| e01_fact_jwt | simple_fact | 1 | True | ok | True | ok | USEFUL |
| e02_decision_dress | decision | 1 | False | ok | True | missing_required | EXTRACTION_FAILURE |
| e03_constraint_evening | constraint | 2 | True | ok | True | ok | USEFUL |
| e04_fact_orders_401 | similar_technical | 1 | False | ok | True | missing_required | EXTRACTION_FAILURE |
| e05_decision_alpine | decision | 0 | False | ok | [] | missing_required | EXTRACTION_FAILURE |
| e06_travel_parking | unrelated_domain | 2 | True | ok | True | missing_required | RECONSTRUCTION_FAILURE |
| e07_correction_navy | correction_supersession | 0 | False | ok | [] | missing_required | EXTRACTION_FAILURE |
| e08_uncertain_maybe | uncertain | 2 | True | ok | True | n/a | EXTRACTION_FAILURE |
| e09_deictic_fix | deictic | 2 | False | ok | True | ok | EXTRACTION_FAILURE |
| e10_ambiguous_other | ambiguous | 0 | True | ok | [] | n/a | EXTRACTION_FAILURE |
| e11_unanchored_no_cards | unanchored | 0 | True | ok | [] | n/a | EXTRACTION_FAILURE |

## Examples (useful vs insufficient)

**Useful (e01_fact_jwt):** `fact`/A: JWT still returns 401 after refresh on the auth service.
**Insufficient (e02_decision_dress):** wrong_ws=True; `fact`/A: I need a black dress for a corporate event.

## Failure taxonomy (this run)

- **A Schema/prompt:** `llm_extract_not_json`, bracketed/title ids
- **B Anchoring:** patches attached to wrong known workstream (e.g. dress→A, orders→A)
- **C Semantic compression:** empty or underspecified content for required tokens
- **D Uncertainty:** model invents patches on ambiguous/uncertain turns (should `[]`)
- **E Supersession:** navy correction did not emit slot/supersedes lifecycle patch
- **F Model capability:** small local model unreliable for structured anchoring

## Status

| Claim | Status |
|---|---|
| LlmMemoryExtractor interface | IMPLEMENTED |
| Writer validates; extractor never writes store | TESTED |
| Local Ollama extraction on synthetic turns | DEMONSTRATED (this doc) |
| Robust extraction on organic/consented chat | NOT YET |
| Vertex extraction comparison | NOT YET |

CONTROLLED SYNTHETIC / LOCAL OLLAMA. Not natural human-chat evidence. Not a production extraction benchmark. Routing frozen and unused here.

## Lifecycle (navy supersession)

```json
{
  "black_historical": [
    {
      "id": "M1",
      "kind": "decision",
      "text": "black",
      "status": "asserted",
      "workstream_id": "E",
      "referent_id": "E.loop1",
      "slot": "color",
      "source_turn": 3,
      "provenance": "conversation:ten-extract-ollama:turn:3:proposer:extractor",
      "superseded_by": null
    }
  ],
  "black_superseded": false,
  "navy_asserted": [],
  "navy_in_working": false,
  "black_excluded_from_working": false
}
```

LLM did not drive supersession in this run; black remains Mock-seeded asserted state.
