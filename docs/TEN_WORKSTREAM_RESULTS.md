# Ten-workstream results (mock)

**Controlled adversarial engineering fixture** — not natural human behavior.

Mock/scripted 50-turn / 17-probe replay. Vertex calls in this run: **0**. A separate five-probe Vertex slice is documented in `docs/TEN_WORKSTREAM_VERTEX_RESULTS.md` and does **not** mean all 50 turns ran through Vertex.

Elapsed ~0.13s · 50 mock generates · frozen routing unchanged.

## Summary

| Metric | Value |
|---|---|
| User turns | 50 |
| Open workstreams | 10 |
| Probes | 17 |
| Routing-correct (ACT match or CLARIFY-ok) | **14 / 17** |
| ACT task+referent match | **14 / 16** |
| CLARIFY-ok | **0 / 1** |
| Wrong-ACT | **0** |
| CF working-set sufficient (no leak) | **15 / 17** |
| Critical missing state | **0** |
| Contamination | **0** |
| Supersession exclusion | **17 / 17** |

## Resolution disagreements (3)

| Probe | Gold | Actual | Notes |
|---|---|---|---|
| p07 debian builder return | ACT B | CLARIFY | Explicit return; gate CLARIFYed — RESOLUTION, not wrong-ACT |
| p18 “maybe the navy one?” | ACT E | CLARIFY | Underspecified / uncertain extract — CLARIFY often legitimate |
| p09 “the other one” | CLARIFY | ACT A | Frozen correction path ACTed — CLARIFY gold disagreement |

## Probe table

| id | turn | gold | got | ACT/CLARIFY | CF sufficient | layer |
|---|---|---|---|---|---|---|
| p01_return_c_after_unrelated | 21 | C/ACT | C/C.loop1 | ACT | True | OTHER |
| p03_return_fashion_after_technical | 22 | E/ACT | E/E.loop1 | ACT | True | OTHER |
| p02_return_a_amid_bcd_401 | 23 | A/ACT | A/A.loop1 | ACT | True | OTHER |
| p04_return_travel_after_work | 24 | F/ACT | F/F.loop1 | ACT | True | OTHER |
| p12_short_gap_return_b | 25 | B/ACT | B/B.loop1 | ACT | True | OTHER |
| p05_return_food_after_travel | 26 | G/ACT | G/G.loop1 | ACT | True | OTHER |
| p08_deictic_fix_that | 37 | C/ACT | C/C.loop1 | ACT | True | OTHER |
| p06_return_e_after_navy_correction | 38 | E/ACT | E/E.loop1 | ACT | True | OTHER |
| p14_jaccard_trap_401 | 40 | D/ACT | D/D.loop1 | ACT | True | OTHER |
| p11_long_gap_return_a | 41 | A/ACT | A/A.loop1 | ACT | True | OTHER |
| p16_return_g_after_risotto | 43 | G/ACT | G/G.loop1 | ACT | True | OTHER |
| p17_return_i_deadline | 44 | I/ACT | I/I.loop1 | ACT | True | OTHER |
| p07_return_b_superseded_builder | 45 | B/ACT | None/B.loop1 | CLARIFY | False | RESOLUTION |
| p18_uncertain_navy_probe | 46 | E/ACT | None/None | CLARIFY | False | RESOLUTION |
| p15_full_history_has_extra | 48 | H/ACT | H/H.loop1 | ACT | True | OTHER |
| p09_the_other_one | 49 | None/CLARIFY | A/A.loop1 | ACT | True | RESOLUTION |
| p13_recent_favors_wrong | 50 | C/ACT | C/C.loop1 | ACT | True | OTHER |

Reproduce: `python -m eval.ten_workstream.run`
