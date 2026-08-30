# Ten-workstream stress evaluation

**Controlled adversarial engineering fixture** — not natural human behavior.

```
conversation → MemoryExtractor → MemoryWriter → MemoryStore
  → frozen ContextFlow → WorkingContextBuilder → ContextPackage → answer
```

Workstream identity is predeclared. Memory content is extracted and committed. Working context is not seeded.

## Run

```text
python -m eval.ten_workstream.run                    # mock; no Vertex
CF_TEN_ANSWER=1 python -m eval.ten_workstream.run    # optional local Ollama answers
python -m eval.ten_workstream.vertex_slice           # optional ≤15-call Vertex slice
```

Outputs under `eval/out/` are gitignored.

## Files

| File | Role |
|---|---|
| `fixture.json` | 10 cards, 52 user turns, extract/LLM scripts |
| `probes.json` | Expected interpretation + Phase-2 metadata (scoring only) |
| `metrics.py` | Separated metric definitions |
| `load.py` | Loaders |
| `run.py` | Mock replay + baselines |
| `vertex_slice.py` | Five-probe Vertex harness (Phase 5; not run in Phase 2) |

See `docs/TEN_WORKSTREAM_STRESS_TEST.md` and `docs/TEN_WORKSTREAM_RESULTS.md`.
