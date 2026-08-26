# ContextFlow

Task-state-conditioned context controller. The LLM proposes which task a message
belongs to; a pure, LLM-free deterministic gate decides CONTINUE / SWITCH / RETURN /
NEW / CLARIFY. Context is compiled in `split` or `merged` modes with separate
decision/answer token accounting. Runs fully on MockLLM for $0.

## Layout
- `app/config.py` — all tunable constants (weights, thresholds, seed).
- `app/domain.py` — Transition enum + LLM/Registry Protocols.
- `app/models/` — Task/TaskAnchor, TaskEvent, ContextPackage/Reference/Conflict, TaskProposal/Candidate/GateDecision.
- `app/llm/` — tokens (single source of truth), base (proposal validation), mock, gemini (isolated adapter).
- `app/memory/` — InMemoryRegistry (+ Firestore seam).
- `app/retrieval/scorer.py` — embeddings + blended candidate scoring (owns the math).
- `app/router/` — proposal (registry-conditioned), references (conflict detection), gate (pure decision).
- `app/context/compiler.py` — split/merged ContextPackage.
- `app/engine.py` — the only composition root.
- `app/api/main.py` — FastAPI boundary.
- `eval/` — scenarios, baselines, harness, metrics (split-vs-merged go/no-go).

## Run
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env

    python -m app            # A->B->C->"fix that" demo; final = RETURN task=A
    pytest -q                # MockLLM only, $0
    python -m eval.harness   # split-vs-merged experiment -> eval/out/rows.csv

## Go live
Set CF_USE_GEMINI=1 and GEMINI_API_KEY in .env. No engine code changes.

## Notes
- `run_tests.py` is a sandbox-only convenience runner for environments without pytest.
  Use real `pytest` in normal development.
- The gate checks TAU against the RAW top score (absolute match quality) and THETA
  against the NORMALIZED margin (relative confidence) — normalized scores are bounded
  below by 1/n, so TAU must be absolute.
- Ordinal references require a cue (fix/do/#/number/item/step/task) and a small value,
  so content numbers like HTTP 401 are not misread as references.
