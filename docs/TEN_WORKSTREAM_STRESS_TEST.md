# Ten-workstream heterogeneous stress test

**Controlled adversarial engineering fixture** — not natural human behavior and not an organic conversation benchmark.

Ten simultaneously open workstreams, abrupt domain switches, and overlapping technical vocabulary (A/C/D share 401/token/API). The question is whether ContextFlow can **persist** many open workstreams and **reconstruct minimum sufficient working context** on return.

Critical failure mode: correct workstream/referent but **missing required working state**.

Frozen routing is unchanged by this evaluation. Probe gold is scoring-only and never enters runtime prompts.

## Fixture

| id | Domain |
|---|---|
| A | JWT / auth service |
| B | Docker / CI deploy |
| C | orders API 401 at gateway |
| D | checkout UI / frontend 401 |
| E | corporate outfit |
| F | Lisbon trip |
| G | dairy-free dinner |
| H | presentation deck (Lisbon chart, not trip) |
| I | Stripe application |
| J | Pokémon trivia |

52 user turns in `eval/ten_workstream/fixture.json`. Workstream **cards** are predeclared; memory **content** flows extract → writer → store. Working context is **not** seeded.

## Probe metadata (Phase 2)

Each probe may declare: `expected_task` / `expected_referent` / `expected_policy`, `required_working_state`, `forbidden_state` / `should_not_carry`, `utterance_kind`, `competing_similar`, `expected_open_workstream_count`, `expected_gap`.

## Separated metrics

| Metric | Meaning |
|---|---|
| `task_match` | Selected workstream == expected (ACT only) |
| `referent_match` | Selected referent == expected (ACT only) |
| `policy_match` | ACT vs CLARIFY matches expected policy |
| `wrong_act` | ACT to a non-gold task (CLARIFY-gold ACT is policy, not wrong-ACT) |
| `candidate_miss` | Expected task absent from open candidates |
| `working_context_sufficient` | Package has required state and no leaks (**ACT only**) |
| `critical_thin_context` | Correct task but thin package |
| `contamination` | Forbidden state in CF package |
| `supersession_correct` | Stale superseded strings absent |
| `persistence_correct` | Accepted extracts present in store |
| `idempotency_correct` / `isolation_correct` | Harness smoke checks |

CLARIFY with no package is **not** scored as thin-context failure (`package_absent_because_clarify`).

Failure layers: `CANDIDATE_MISS` · `RESOLUTION` · `POLICY` · `EXTRACTION` · `PERSISTENCE` · `RECONSTRUCTION` · `CONTAMINATION` · `ANSWER` · `AMBIGUITY` · `OTHER` · `NONE` (success).

## Coverage

Returns after unrelated work, A amid B/C/D 401 overlap, fashion/travel/food/job/deck/**trivia (J)**, deictic `fix that`, ambiguous `the other one`, ordinal out-of-range CLARIFY, long/short gaps, recent/Jaccard traps, FULL noisier than CF, supersession, uncertain exclusion, idempotent retry, conversation isolation.

Known frozen disagreements (document, do not retune): **p07**, **p09**, **p18**.

## Reproduce

```text
python -m eval.ten_workstream.run
pytest -q tests/test_ten_workstream.py tests/test_ten_workstream_metrics.py
```

## Vertex

A separate five-probe Vertex slice (not this mock run) is documented in `docs/TEN_WORKSTREAM_VERTEX_RESULTS.md`. **Not** a full 50-turn hosted Vertex replay.
