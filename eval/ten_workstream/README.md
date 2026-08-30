# Ten-workstream stress evaluation

**CONTROLLED ADVERSARIAL ENGINEERING FIXTURE — NOT NATURAL HUMAN CHAT.**

```
conversation → MemoryExtractor → MemoryWriter → MemoryStore
  → frozen ContextFlow → WorkingContextBuilder → ContextPackage → answer
```

Workstream identity is predeclared. Memory content is extracted and committed. Working context is not seeded. Probe gold is evaluator-only.

## Run

```text
python -m eval.ten_workstream.run                      # full mock replay + results md
python -m eval.ten_workstream.poc_harness              # layered POC summary + pitch report
python -m eval.ten_workstream.poc_harness --evaluator-isolated
```

`--evaluator-isolated` loads a **runtime-blind evaluator probe set** derived from the controlled fixture. It is **not** an unseen statistical/generalization holdout and must not be cited as generalization evidence. Purpose: keep gold out of `app/` runtime.

Outputs under `eval/out/` are gitignored. Pitch report: `docs/POC_HARNESS_REPORT.md`.

## Files

| File | Role |
|---|---|
| `fixture.json` | 10 cards, 52 user turns, extract/LLM scripts (no gold) |
| `probes.json` | Expected interpretation (scoring only) |
| `evaluator_isolated_probes.json` | Runtime-blind evaluator probe set (derived; not a statistical holdout) |
| `metrics.py` | Separated layer metrics |
| `answer_usability.py` | Package / working-context evidence usability (not answer quality) |
| `load.py` | Loaders + probe normalization |
| `run.py` | Mock replay + baselines |
| `poc_harness.py` | Machine summary + human report |

See `docs/TEN_WORKSTREAM_STRESS_TEST.md` and `docs/POC_HARNESS_REPORT.md`.
