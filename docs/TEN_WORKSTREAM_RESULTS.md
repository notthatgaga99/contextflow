# Ten-workstream results (mock)

**Controlled adversarial engineering fixture** — not natural human behavior, not a benchmark, not production accuracy.

**Date:** local mock run. Elapsed **0.305s**. Mock generates: **52**. Vertex: **0**.

## Separated metrics

- User turns: 52
- Open workstreams: 10
- Probes: 19 (ACT=17, CLARIFY=2)
- task_match: **15/17**
- referent_match: **15/17**
- policy_match: **16/19**
- wrong_act: **0**
- candidate_miss: **0**
- working_context_sufficient (ACT only): **15/15**
- critical_thin_context: **0**
- contamination: **0**
- supersession_correct: **19**
- persistence_correct: **19**
- idempotency_correct: **True**
- isolation_correct: **True**
- Failure layers: {'OTHER': 15, 'POLICY': 3, 'AMBIGUITY': 1}

CLARIFY probes are not scored for working-context sufficiency (`package_absent_because_clarify`).

## Probes

| id | turn | gold | got | policy | task | ref | WC | layer |
|---|---|---|---|---|---|---|---|---|
| p01_return_c_after_unrelated | 21 | C/ACT | C/C.loop1 | True | True | True | True | OTHER |
| p03_return_fashion_after_technical | 22 | E/ACT | E/E.loop1 | True | True | True | True | OTHER |
| p02_return_a_amid_bcd_401 | 23 | A/ACT | A/A.loop1 | True | True | True | True | OTHER |
| p04_return_travel_after_work | 24 | F/ACT | F/F.loop1 | True | True | True | True | OTHER |
| p12_short_gap_return_b | 25 | B/ACT | B/B.loop1 | True | True | True | True | OTHER |
| p05_return_food_after_travel | 26 | G/ACT | G/G.loop1 | True | True | True | True | OTHER |
| p08_deictic_fix_that | 37 | C/ACT | C/C.loop1 | True | True | True | True | OTHER |
| p06_return_e_after_navy_correction | 38 | E/ACT | E/E.loop1 | True | True | True | True | OTHER |
| p14_jaccard_trap_401 | 40 | D/ACT | D/D.loop1 | True | True | True | True | OTHER |
| p11_long_gap_return_a | 41 | A/ACT | A/A.loop1 | True | True | True | True | OTHER |
| p16_return_g_after_risotto | 43 | G/ACT | G/G.loop1 | True | True | True | True | OTHER |
| p17_return_i_deadline | 44 | I/ACT | I/I.loop1 | True | True | True | True | OTHER |
| p07_return_b_superseded_builder | 45 | B/ACT | None/B.loop1 | False | False | False | None | POLICY |
| p18_uncertain_navy_probe | 46 | E/ACT | None/None | False | False | False | None | POLICY |
| p15_full_history_has_extra | 48 | H/ACT | H/H.loop1 | True | True | True | True | OTHER |
| p09_the_other_one | 49 | None/CLARIFY | A/A.loop1 | False | None | None | None | POLICY |
| p13_recent_favors_wrong | 50 | C/ACT | C/C.loop1 | True | True | True | True | OTHER |
| p20_ordinal_out_of_range_clarify | 51 | None/CLARIFY | None/C.loop1 | True | None | None | None | AMBIGUITY |
| p19_return_j_trivia | 52 | J/ACT | J/J.loop1 | True | True | True | True | OTHER |

## Status

| Claim | Status |
|---|---|
| 10-workstream fixture | TESTED (mock) |
| Separated eval metrics | IMPLEMENTED / TESTED |
| Working-context reconstruction | TESTED (mock) |
| Hosted Vertex five-probe slice | see TEN_WORKSTREAM_VERTEX_RESULTS.md |
| Full 50-turn Vertex replay | NOT YET |

Do not retune the gate from this table.
