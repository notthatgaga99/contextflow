# Memory lifecycle results

**Date:** 2026-08-29  
**Substrate:** `synthetic_engineering_fixture`  
**Routing:** frozen (no TAU/DELTA/HYST/weight changes). No Vertex, embeddings, Firestore.

## Verdict

`data/consented/session.json` was **absent**. This run is a **synthetic engineering fixture** (A authentication / B outfit / C travel / D paper). It is a pipeline test, not evidence of real-user behavior. Public dataset hunting was not repeated.

Claim under test: ContextFlow can sit above a memory store and reconstruct a sufficiently small, relevant working set from accumulated conversation state after the user has moved through other intentions.

**On this synthetic fixture the claim is supported for the navy/formal/evening return to B** (items came from incremental extraction, not a pre-seeded store). FULL contained the required strings on every primary return; it is marked `needed+leaks` because competing domains remain in the transcript. That is a legitimate FULL result, not a CF-only invention. Other returns are in the table.

Workstream **cards** (A–D) are the control plane. Working **memory** started empty on the primary path. `handle_turn` does not extract; MockLLM.generate does not write items.

## Counts

- workstreams: 4
- genuine returns: 4
- memory writes (extractor commits): 8
- accepted items: 11
- rejected commits: 0
- uncertain/empty extract turns: 2
- supersessions: 3
- missing required state (CF thin): 0
- correct resolution (ACT + gold task): 4
- wrong-ACT: 0
- CLARIFY (primary probes): 0
- CF beats FULL: ['return_A', 'return_B_navy', 'return_C', 'return_B_again']
- FULL beats CF: none
- both sufficient: none

## Primary returns (incremental extract, no human-seeded items)

| return | task | referent | extraction | persistence | reconstruction | FULL | RECENT | CF | failure |
|---|---|---|---|---|---|---|---|---|---|
| return_A | A | A.loop1 | uncertain | True | ok | needed+leaks | missing+leaks | ok | none |
| return_B_navy | B | B.loop1 | accepted | True | ok | needed+leaks | needed+leaks | ok | none |
| return_C | C | C.loop1 | uncertain | True | ok | needed+leaks | needed+leaks | ok | none |
| return_B_again | B | B.loop1 | accepted | True | ok | needed+leaks | needed+leaks | ok | none |

FULL / RECENT / CF: **needed_state** vs **contamination**. `needed+leaks` means the facts were in the prompt but competing domains were too. On this fixture FULL always had the required strings; CF wins by **exclusion**, not because FULL lacked navy/401/parking. RECENT can miss earlier facts (return_A dropped `15 minutes` in the K=8 window). Mock generate is not scored.

### Layer notes (primary)

- **return_A:** transition=RETURN; winner=CF_beats_FULL; missing={'facts': [], 'decisions': [], 'constraints': [], 'entities': [], 'needed_state': []}; leaks=[]; stale=[]; excluded=['corporate outfit', 'travel', 'paper']; sizes={'full_chars': 1354, 'recent_chars': 752, 'cf_chars': 163, 'cf_answer_tokens': 24}
- **return_B_navy:** transition=RETURN; winner=CF_beats_FULL; missing={'facts': [], 'decisions': [], 'constraints': [], 'entities': [], 'needed_state': []}; leaks=[]; stale=[]; excluded=['authentication', 'travel', 'paper']; sizes={'full_chars': 1595, 'recent_chars': 791, 'cf_chars': 177, 'cf_answer_tokens': 23}
- **return_C:** transition=RETURN; winner=CF_beats_FULL; missing={'facts': [], 'decisions': [], 'constraints': [], 'entities': [], 'needed_state': []}; leaks=[]; stale=[]; excluded=['authentication', 'corporate outfit', 'paper']; sizes={'full_chars': 1782, 'recent_chars': 780, 'cf_chars': 149, 'cf_answer_tokens': 19}
- **return_B_again:** transition=SWITCH; winner=CF_beats_FULL; missing={'facts': [], 'decisions': [], 'constraints': [], 'entities': [], 'needed_state': []}; leaks=[]; stale=[]; excluded=['authentication', 'travel', 'paper']; sizes={'full_chars': 1961, 'recent_chars': 772, 'cf_chars': 199, 'cf_answer_tokens': 27}

## Secondary control (human-seeded memory, extractor skipped)

Same conversation and frozen engine. Items written with MemoryWriter without MockMemoryExtractor. If this succeeds while incremental extract fails, the gap is extraction.

| return | task | CF sufficient | winner | failure |
|---|---|---|---|---|
| return_A | A | True | CF_beats_FULL | none |
| return_B_navy | B | True | CF_beats_FULL | none |
| return_C | C | True | CF_beats_FULL | none |
| return_B_again | B | True | CF_beats_FULL | none |

## Adversarial cases

Desired behavior is not always ACT. CLARIFY is valid when continuation is unsafe.

| case | task | transition | failure | note |
|---|---|---|---|---|
| correct_task_missing_memory | B | RETURN | extraction | No items extracted. Routing may still name B; package lacks navy/formal/evening. |
| correct_task_stale_memory | B | CONTINUE | extraction | Extractor skipped the correction. Store still has black. CF package is stale. |
| correct_task_conflicting_memory | None | None | none | Writer refused unkeyed navy vs black. Store unchanged on second commit. |
| wrong_extractor_workstream | B | CONTINUE | extraction | Writer cannot know A was the wrong id. Reconstruction of B is insufficient. |
| ambiguous_referent_sibling_loops | A | CONTINUE | none | Extractor omitted referent. Frozen resolver on 'no, the other one' → CONTINUE. CLARIFY would also be valid; this run CONTINUEd. Not treated as a routing defect to retune. |
| correction_supersession | B | see_primary_return_B_navy | none | Measured on primary return_B_navy, not a separate world. |
| unrelated_domain_switch | C_then_D | see_primary_route_log | none | Primary turns 5–6 write C then D items into separate workstreams. |
| multiple_returns_same_workstream | B | see_primary_return_B_again | none | Measured on primary return_B_again. |

## Limitations of this experiment

- **Extractor content is scripted** (`MockMemoryExtractor`). The *path* (extract → writer → store → frozen CF → package) is real; an LLM extractor was not run.
- **Proposals to the gate are MockLLM scripts.** Frozen gate/resolver math is production; the soft task_id guess is not a live model.
- **Answer quality is not measured.** Mock generate truncates the prompt.
- **Workstream cards A–D were pre-declared** (control plane). Only MemoryItems started empty.

## What would falsify the architecture

- Routing defect: gold workstream present in store, extractor correct, still wrong-ACT with no ambiguity. Isolated adversarial CLARIFY is allowed and is not a retune trigger.
- Persistence defect: accepted items missing later, or navy not superseding black.
- Reconstruction/compiler defect: asserted navy on B but package omits it or includes Lisbon.
- Answer-model defect: package sufficient, real model still cannot continue. **Not measured** (mock only).

## Reproduce

```
python -m eval.memory_lifecycle.run
```

Machine snapshot: `eval/out/memory_lifecycle.json` (gitignored).

