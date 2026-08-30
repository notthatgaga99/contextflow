# ContextFlow POC harness report

> **CONTROLLED ADVERSARIAL ENGINEERING FIXTURE — NOT NATURAL HUMAN CHAT.**
>
> Demo-ready / research-product checkpoint — not a production benchmark,
> not organic conversation evidence, not hosted-model accuracy.

## Hypothesis

After many simultaneous context switches, ContextFlow can reconstruct the
minimum sufficient working state for the selected workstream while excluding
unrelated and superseded context — and failing closed when ambiguity is material —
providing a **materially better continuation context** than naive full-history
or recent-history packing.

## Experiment

- Substrate: `synthetic_adversarial_engineering_fixture` / ten-workstream fixture
- Probe source: `probes.json` (evaluator-only gold)
- Probe-source note: Primary evaluator probes. Gold never enters app runtime.
- Workstreams: **10**
- User turns: **52**
- Trajectory RETURN transitions (all turns): **33**
- Probe turns with decision=RETURN: **14**
- Probes scored: **19** (ACT=17, CLARIFY=2)
- Context packs compared with the **same** continuation utterance:
  **FULL** · **RECENT** · **CONTEXTFLOW**
- Runtime never receives gold task/policy/required/forbidden state.

## Stress pattern

Ten open workstreams spanning auth, deploy, overlapping 401 APIs,
fashion, travel, food, deck, Stripe, and trivia; abrupt switches;
returns after long gaps; deictic and ordinal ambiguity; supersession;
uncertain exclusion; conversation isolation.

## Results (separated layers — not one score)

### RESOLUTION
- task_match: **15/17**
- referent_match: **15/17**
- candidate_miss: **0**

### POLICY
- policy_match: **16/19**
- wrong_act: **0**
- clarify_correct: **1/2**

### MEMORY
- persistence_correct: **19**
- supersession_correct: **19**
- idempotency_correct: **True**
- isolation_correct: **True**

### WORKING CONTEXT
- working_context_sufficient: **15/15**
- critical_thin_context: **0**
- contamination: **0**

### WORKING-CONTEXT / PACKAGE USABILITY

Package evidence labels from token/string presence on context packs.
**Not** an answer-quality benchmark; does **not** judge generated replies.

- counts: `{'correct_continuation': 15}`

### Context-package comparison (evidence criteria — not answer-model superiority)

`cf_package_beats_full_on_context_criteria` means: the CF package has the
required evidence with less forbidden context than FULL (reconstruction/
token-presence criteria). It is **not** a claim that answers are better.

- cf_package_beats_full_on_context_criteria: **15**
- both_packages_sufficient_on_context_criteria: **1**
- full_package_beats_cf_on_context_criteria: **0**

### Failure counts by layer
```
{
  "POLICY": 3
}
```

## Failure cases

| probe | layer | gold → got | note |
|---|---|---|---|
| p07_return_b_superseded_builder | POLICY | B/ACT → None/CLARIFY | Frozen RESOLUTION: gold ACT B may CLARIFY. Document, do not retune. |
| p18_uncertain_navy_probe | POLICY | E/ACT → None/CLARIFY | Gold ACT E; product may CLARIFY on underspecified maybe. Document, do not retune |
| p09_the_other_one | POLICY | None/CLARIFY → A/ACT | Frozen correction often ACTs; gold CLARIFY. Document, do not retune. |

## Why ContextFlow succeeds / fails

**Succeeds when** the selected workstream is correct and asserted memory for
that referent is projected without sibling/unrelated/superseded/uncertain leaks.
FULL history often *contains* required tokens but also contaminates with
competing workstreams; CF wins on **package evidence criteria** when exclusion
matters.

**Fails when** frozen routing CLARIFYs on an ACT-gold return (document as
POLICY, do not retune), when extraction never asserted required state
(RECONSTRUCTION / EXTRACTION), or when ambiguity is material.

## Limitations

- Fixture is **synthetic and adversarial**, not organic chat.
- MockLLM soft proposals + scripted extracts; not a hosted-model study.
- Package usability classifies **context packages** via token/string presence,
  not judged model replies (optional Ollama consume is separate and weak).
- Evaluator-isolated probes are derived from the same controlled fixture —
  **not** an unseen statistical holdout and **not** generalization evidence.
- Known frozen disagreements (p07, p09, p18) are documented, not retuned.
- Do not collapse layers into a single accuracy claim.

