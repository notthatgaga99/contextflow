# Ten-workstream heterogeneous stress test

**Controlled adversarial engineering fixture** — not natural human behavior and not an organic conversation benchmark.

Ten simultaneously open workstreams, abrupt domain switches, and overlapping technical vocabulary (A/C/D share 401/token/API). The question is whether ContextFlow can **persist** many open workstreams and **reconstruct minimum sufficient working context** on return.

Critical failure mode: correct workstream/referent but **missing required working state**.

Frozen routing is unchanged by this evaluation.

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

50 user turns in `eval/ten_workstream/fixture.json`. Workstream **cards** are predeclared; memory **content** flows extract → writer → store. Working context is **not** seeded.

## Probe coverage

Returns after unrelated work, corrections/supersession, deictic `fix that`, ambiguous `the other one`, long/short gaps, recent/Jaccard traps, FULL-history noisier than CF package.

Expected interpretation lives in `probes.json` (scoring only — not a retune target).

## Baselines

FULL HISTORY · RECENT K=8 · Jaccard top-8 (eval-only) · ContextFlow package.

```text
python -m eval.ten_workstream.run
```

Optional: `CF_TEN_ANSWER=1` for local Ollama FULL/RECENT/CF answer overlap (qualitative only).

## Vertex (separate slice)

Vertex exercised extract → writer → frozen ContextFlow → working-context → answer on **p08, p06, p11, p15, p13** (`gemini-2.5-flash-lite`, `us-central1`). Non-probe history was Mock-seeded. **Not** a full 50-turn hosted Vertex replay.

See `docs/TEN_WORKSTREAM_VERTEX_RESULTS.md`.
