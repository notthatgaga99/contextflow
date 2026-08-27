# ContextFlow

Watch what happens when a conversation contains four unfinished problems
and the user says **"fix that"**.

Long conversations usually fail because the system does not know **which
piece of unfinished work** the user is referring to — not because the model
cannot read a transcript.

ContextFlow keeps structured task/loop state and foregrounding so a user can
switch workstreams and later say `fix that` without restating everything.

The LLM **proposes**. ContextFlow **maintains state** and **decides** whether
that proposal is safe to act on.

## Why ContextFlow?

**What problem?**
Users interleave tasks. Later they point with underspecified language
(`fix that`, `the other one`). Recency and keyword similarity mix up sibling
work. Dumping the whole transcript (or every open card) into the answer model
is bulky and can distract a generator.

**What does ContextFlow do?**
It tracks open tasks and open loops, mention clocks, and a derived foreground
referent. A deterministic gate then ACTS (continue/switch/return/new) or
CLARIFIES. The answer model sees the **selected task + selected loop**, not
the full dump.

**What evidence do we have?**
A controlled PoC on a fixed scenario family: MockLLM tests, local Ollama
probes, a 512-cell interference/scale grid, and Gemini 2.5 Flash-Lite as a
hosted **proposer** (not a product cost claim). Details: `docs/POC_FREEZE.md`,
`eval/out/POC_RESULTS.md`.

**How do I run it?**
See the 60-second demo below. No API key. No network.

## 60-second demo

    python -m eval.demo

Optional local UI (still MockLLM, no cloud):

    python -m eval.demo --serve

Every-turn dump: `python -m eval.demo --verbose`

You should see Authentication / Frontend / Deployment / OAuth, then:

```
USER                "fix that"
LLM PROPOSAL        Authentication (0.97)     [soft; not the decision]
CONTEXTFLOW         Deployment / C.loop1      [deictic mention clocks]
GATE                CONTINUE C
ANSWER CONTEXT      Deployment + Docker CI failure
```

FULL HISTORY = everything. CONTEXTFLOW = what matters now.
No numerical token-savings claim.

## Architecture

```
User message
     │
     ▼
LLM proposal          (soft; never the decision)
     │
     ▼
Referent resolution
     ├── task mention clocks
     ├── loop mention clocks
     └── explicit / deictic / correction cues
     │
     ▼
Deterministic gate
     ├── ACT   (CONTINUE / SWITCH / RETURN / NEW)
     └── CLARIFY
     │
     ▼
Selected task + loop
     │
     ▼
Compact answer context
     │
     ▼
LLM answer
```

The LLM proposes; ContextFlow maintains state and decides whether the
proposal is safe to act on. Gate thresholds (TAU / DELTA / HYST) and score
weights are frozen PoC defaults, not calibrated probabilities.

## Evidence ladder (controlled PoC)

1. **MockLLM** — deterministic routing/gate tests.
2. **Ollama qwen2.5:1.5b** — local weak-model answer probe.
3. **Ollama llama3.1:8b** — stronger local answer-context probe.
4. **512-cell scale stress** — open-task count × LOW/HIGH interference.
5. **Gemini 2.5 Flash-Lite** — hosted proposer validation (Vertex; billed;
   do not re-run the large suite casually).

Most defensible Gemini-scale result, still **controlled evidence only**:
ContextFlow **wrong-ACT remained 0**; the hardest sibling-401 collisions
degraded through **clarification** rather than confident misrouting, while
recency/similarity baselines degraded earlier as *n* grew.

Allowed PoC claim (verbatim, `docs/POC_FREEZE.md`):

> ContextFlow demonstrates interference-resistant task and referent
> resolution across interleaved tasks, using explicit referent/mention
> state plus a deterministic act/clarify gate. Across controlled
> high-interference scenarios, the system maintained zero wrong-action
> rate and degraded through clarification rather than confident
> misrouting at the hardest tested sibling-collision cases, while recency
> and similarity baselines degraded earlier as open-task count increased.

## What this is NOT

- not a claim of a novel routing mechanism
- not a replacement for an LLM
- not “perfect memory” or lifetime memory solved
- not mathematically minimum context
- not a production accuracy benchmark
- not a claim that Gemini (or any LLM) confidence is P(correct)
- not decision-context efficiency or total token savings
  (answer context is compact; **decision** context still lists open cards)

The PoC contribution is the **combination** of structured task/referent
state, interference-aware resolution, and fail-closed act/clarify behavior,
validated on a **controlled scenario family**.

## How to reproduce

    python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    pytest -q
    python -m app
    python -m eval.demo

Experiments (optional; some cost money): `docs/REPRODUCE.md`.
Submission draft: `docs/SUBMISSION.md`.

## Layout

- `app/engine.py` — composition root (propose → resolve → gate → compile).
- `app/router/` — proposal, referent, references, gate.
- `app/context/compiler.py` — split / compact answer context.
- `app/memory/` — in-memory registry (Firestore is an unused seam).
- `eval/demo.py` — canonical $0 judge demo.
- `docs/POC_FREEZE.md` — frozen architecture and allowed claims.
