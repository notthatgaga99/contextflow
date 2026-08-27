# ContextFlow — submission draft

Keep claims aligned with `docs/POC_FREEZE.md`. This is a hackathon / PoC
write-up, not a production spec.

## One-line pitch

Watch four unfinished problems; the user says “fix that”; ContextFlow
resumes the right loop even when the LLM guesses the wrong task.

## Problem

Long conversations do not mainly fail because the model cannot read the
transcript. They fail because the system does not know **which piece of
unfinished work** the user is pointing at. Recency and keyword overlap mix
up sibling tasks. Replaying everything is bulky and can distract generation.

## Solution

ContextFlow is a state layer around an LLM:

- structured tasks and open loops
- mention clocks (task + loop) → derived foreground referent
- LLM **proposal** (soft)
- deterministic **act / clarify** gate
- answer context = selected task + selected loop

The LLM proposes. ContextFlow maintains state and decides whether that
proposal is safe to act on.

## 60-second demo script

No network. No API key.

```text
python -m eval.demo
```

Optional UI: `python -m eval.demo --serve`

Talk track:

1. Four open workstreams: Authentication (JWT 401 + expired token),
   Frontend (double render), Deployment (Docker CI), OAuth (redirect URI).
2. The user jumps between them.
3. The user says **fix that**.
4. Show **LLM PROPOSAL = Authentication (0.97)** vs
   **CONTEXTFLOW = Deployment / C.loop1** vs **GATE = CONTINUE C**.
5. Answer context is Docker CI, not the whole card dump.
6. Line: FULL HISTORY = everything; CONTEXTFLOW = what matters now.
7. Do **not** quote a token-savings percentage.

## Architecture

```
User message → LLM proposal → referent resolution (clocks + cues)
  → deterministic gate (ACT | CLARIFY)
  → selected task + loop → compact answer context → LLM answer
```

Frozen defaults: TAU=0.20, DELTA=0.08, HYST=0.05. LLM confidence is not
P(correct). Decision context still grows with open cards.

## Evidence

Controlled scenario family only.

1. MockLLM — deterministic mechanism tests.
2. Ollama 1.5B — weak-model answer probe.
3. Ollama 8B — answer-context probe.
4. 512-cell scale — open-task count × interference.
5. Gemini 2.5 Flash-Lite — hosted proposer validation (~135 proposes,
   ~$0.007 list-price heuristic; do not re-run casually).

Highlight, then qualify: on the Gemini HIGH-interference scale grid,
**wrong-ACT = 0**; sibling-401 cases **clarified** rather than acting
wrong. Recency/similarity degraded earlier. This is **not** a general
benchmark win.

## Limitations

- Generic NEW card extraction is still simple (utterance → short card).
- Registry is in-memory.
- Embeddings in the PoC path are hash-seeded, not semantic RAG.
- Gemini is optional validation, not required to demo.
- Decision context still dumps open cards.
- PoC ≠ production accuracy.

## Future work

Durable store, semantic embeddings, compact **decision** context, richer
NEW extraction — none of these are required to tell the “fix that” story.

## How to reproduce

```text
pip install -r requirements.txt
pytest -q
python -m eval.demo
```

Full experiment commands and Vertex warning: `docs/REPRODUCE.md`.
Frozen claim text: `docs/POC_FREEZE.md`.
Measured tables: `eval/out/POC_RESULTS.md`.
