# ContextFlow PoC freeze

Research exploration is closed. This document freezes the architecture, the
allowed claim, and the evidence as of the Gemini-validation gate.
It is not a product spec for unbounded users.

Do not treat this as permission to retune weights, thresholds, the resolver,
the compiler, or embeddings.

---

## 1. Problem

Users interleave multiple tasks. A later utterance often under-specifies which
task and which open loop it continues (`"fix that"`, `"still getting the 401"`,
`"no, the other one"`). Recency and lexical similarity confuse sibling tasks
that share cues. Dumping the full transcript or every open card into the answer
model is neither necessary nor always safe: extra sibling loops can distract a
weak generator.

## 2. Product objective

Keep useful continuity by reconstructing **decision-sufficient** context for
routing and **answer-sufficient** context for generation, without replaying the
full transcript.

PoC success is **interference-resistant resolution plus fail-closed policy** on
a controlled scenario family — not benchmark ranking, not production accuracy.

## 3. Architecture (frozen)

```
message
  → LLM proposal (soft; never the decision)
  → referent resolution (deterministic; clocks + lexical overlap)
  → scoring (raw blend; hash embeddings in this PoC)
  → conflict check
  → deterministic gate: ACT (CONTINUE / SWITCH / RETURN / NEW) or CLARIFY
  → compiler: selected task + selected loop
  → compact answer context
  → LLM answer
  → registry mention/active clocks (not written from the answer)
```

Composition root: `app/engine.py`. The LLM proposes; the gate decides.
`generate()` does not mutate mention clocks.

Default compiler mode: `split` → `REFERENT_COMPACT` when a referent is selected;
`FULL_TASK` if no referent (do not invent `loop1`).

## 4. State model

Persisted on `Task` / registry (in-memory PoC):

- task cards: id, title, status (`active` | `paused` | `resolved`), retrieval cues, `TaskAnchor`
- open loops (strings on the anchor)
- `active_task_id` (exactly one `active` task)
- `last_active_turn` (workstream clock)
- `mention_turn` (last user mention of the task)
- `loop_mention_turns` (parallel to `open_loops`)
- derived referent id `{task_id}.loop{k}`
- last selected referent (correction excludes it)
- utterance kind: explicit / deictic / correction (plus eval labels for partial)

There is no persistent `ForegroundReferent` domain object. Foregrounding is
derived from mention/active clocks.

Firestore is a unused seam (`app/memory/firestore_registry.py`). Not in the PoC path.

## 5. Routing algorithm

1. Build a registry-conditioned proposal prompt (open-task cards).
2. Sanitize unknown task ids (fail closed; not evidence).
3. `resolve_referent(...)` before policy.
4. Score candidates. On deictic/correction, **do not apply LLM confidence**
   (`apply_llm=False`).
5. Detect explicit-reference conflicts.
6. If the referent route is used and unambiguous: `bind_task` (CONTINUE / SWITCH / RETURN).
   Resolver ambiguity → CLARIFY even if the scorer would act.
7. Otherwise `decide(...)` (TAU / HYST / DELTA / NEW).
8. ACT compiles context and calls `generate`. CLARIFY returns a question; no act.

## 6. Confidence / gating mathematics

Score (defaults in `app/config.py`; **not retuned after experiments**):

```
raw = W_LLM * llm + W_SIM * cos + W_REC * rec + W_LOOP * loop
```

- `W_LLM=0.5`, `W_SIM=0.35`, `W_REC=0.15`, `W_LOOP=0.15` (sum 1.15)
- `rec = exp(-LAMBDA * (turn - last_active_turn))`, `LAMBDA=0.15`
- `cos` is cosine of **hash-seeded** vectors in Mock/Ollama/Gemini-validation
  (not `text-embedding-004` in the reported runs)
- `norm = raw / (sum(raw) + EPS)` is **logged only** for ranking display

Gating quantity: `raw_margin = top_raw - runner_raw`. **Not a probability.**
LLM `confidence` is diagnostic only. Never interpret it as P(correct).
Platt calibration is unused.

Gate order (`app/router/gate.py`):

1. explicit conflict → CLARIFY
2. `top_raw < TAU` → CLARIFY (`TAU=0.20`)
3. HYST: if challenger beats active by `< HYST` (`0.05`), stick CONTINUE
4. `raw_margin < DELTA` → CLARIFY (`DELTA=0.08`; `THETA` is a deprecated alias)
5. NEW / CONTINUE / SWITCH / RETURN (`COLD=3` for RETURN vs SWITCH)

`bind_task` does not re-apply TAU/DELTA/HYST.

## 7. Referent resolution

Pure function: `app/router/referent.py`. No registry writes, no gate, no LLM calls.

- **explicit / partial lexical:** content-token overlap with loop+goal; unique
  max overlap selects; tie → ambiguous CLARIFY route
- **deictic** (`fix that` / `that` / `it`): loop mention clocks, then task clocks
- **correction** (`no, the other one`): exclude last selected referent, then clocks

Lexical `"401"` can match multiple sibling loops. That is the known boundary.
It was **not patched** after observation.

## 8. Context compiler

`app/context/compiler.py`

| Mode | Answer loops | Token split |
|---|---|---|
| `REFERENT_COMPACT` (`split`) | selected loop only | decision + answer counted separately |
| `FULL_TASK` | all loops on the selected task | same |
| `MERGED_COMPACT` | compact loops in one blob | `decision_tokens=0`; one merged string |

**Decision text** (split): message + **all open-task cards** + selected ids.
Therefore **decision context grows with open-task count n**.

**Answer text** (compact): selected task summary + selected loop (+ decisions /
constraints / entities). Compact **answer** context does not dump sibling tasks.

Token heuristic: `ceil(chars/4)` (`app/llm/tokens.py`). **Diagnostic, not savings.**

## 9. Provider abstraction

Protocol `LLM`: `propose`, `generate`, `embed`.

| Provider | Role in PoC |
|---|---|
| `MockLLM` | $0 deterministic tests and 512-cell scale (scripted / lure proposals; hash embed) |
| `OllamaLLM` | optional local propose/generate; tests must not require it |
| `GeminiClient` | hosted propose/generate behind the same interface |

Gemini-validation used Gemini **only for propose**, hash embeddings, **skipped generate**.
That keeps the provider as the experimental variable.

## 10. Experimental ladder

1. **MockLLM** — routing/gate unit tests; deterministic mechanism.
2. **Ollama `qwen2.5:1.5b`** — provider wiring; weak-model answer interference.
3. **Ollama `llama3.1:8b`** — stronger local **answer** model; same frozen router.
4. **512-cell task-count stress** (`eval/task_count_scale.py`) — MockLLM;
   n={1,2,3,5,8,10} × LOW/HIGH × explicit/partial/deictic/correction × foregrounds.
5. **Gemini 2.5 Flash-Lite** — Vertex; same 128 ContextFlow scale cells + 4-cell
   401-collision pair; temperature 0; 1 rep.

## 11. Baselines

Identical definitions on the scale grid (no RAG):

1. **ContextFlow** — production engine
2. **recency** — max `last_active_turn` / mention clocks; always ACT
3. **similarity** — Jaccard of message vs goal+loop+cues; always ACT
4. **full-history cards** — same lexical rule over the card dump (deictic → recency);
   token diagnostic is the concatenated cards

## 12. Metrics (keep separate)

- **resolution:** task accuracy, referent accuracy, joint accuracy
- **policy:** ACT vs CLARIFY (`CONTINUE`/`SWITCH`/`RETURN`/`NEW` vs `CLARIFY`)
- **wrong ACT:** acted and joint resolution is false
- **clarification:** CLARIFY rate; split clarify+gold vs clarify+wrong
- **answer-context size** vs **decision-context size** (diagnostic)

CLARIFY is not automatically a failure.

## 13. Results (summary)

See `eval/out/POC_RESULTS.md` for tables.

HIGH interference, ContextFlow joint vs n (Mock and Gemini **identical**):

`1.00, 1.00, 1.00, 1.00, 0.92, 0.92` at n=`1,2,3,5,8,10`

ContextFlow **wrong-ACT = 0** on that grid (Mock and Gemini).

n=8/10 drop is HIGH + PARTIAL `"still getting the 401"` with sibling H5 also
containing 401 → CLARIFY (fail closed). Recency/similarity degrade earlier.

Gemini record (experiment, not product cost): Vertex `gemini-2.5-flash-lite`,
region `us-central1`, 135 propose calls (3 smoke + 132), 41,265 prompt +
13,302 candidate tokens, usage-based list-price estimate **~$0.007**.
`gemini-2.0-flash-lite` was not available on the project in `asia-south1` or
`us-central1`.

## 14. Failure cases

Frozen, not optimized:

- Sibling lexical collision on `"401"` (HIGH PARTIAL, n≥8 distractor-last; exp2).
- Hash embeddings are not semantic; `W_SIM` is not RAG.
- Decision package still lists every open card.
- Weak generators can attend to sibling loops under `FULL_TASK` (qwen probe).
- `llama3.1:8b` compact vs full **probe accuracy both 0.90** — not a compact-vs-full
  accuracy victory.

Failure classes used in Gemini eval: A resolver, B task, C gate, D LLM proposal,
E lexical collision, F state, G compiler, H intentional fail-closed clarification.

## 15. What the results prove

For the **controlled scenario family**:

ContextFlow demonstrates interference-resistant task and referent resolution
across interleaved tasks, using explicit referent/mention state plus a
deterministic act/clarify gate. Across controlled high-interference scenarios,
the system maintained zero wrong-action rate and degraded through clarification
rather than confident misrouting at the hardest tested sibling-collision cases,
while recency and similarity baselines degraded earlier as open-task count
increased.

A hosted Gemini proposer did not invalidate that mechanism on the frozen grid.

## 16. What they do not prove

Do **not** claim:

- general benchmark superiority
- production accuracy
- generalization to arbitrary users
- statistically significant superiority
- mathematically minimum context
- deterministic AI
- novel routing architecture
- decision-context efficiency
- total token savings
- Gemini superiority
- semantic RAG superiority
- human-level task resumption
- lifetime memory solved

Answer context is compact. Decision context scales with the open-card dump.
Do not call the system “context efficient” without that qualification.

## 17. Known limitations

- In-memory registry only; no durable store in the live path
- Hash embeddings in reported routing experiments
- Token counts are a character heuristic
- Proposal prompt includes all open cards (grows with n)
- Sibling 401 collision unpatched
- Gemini 2.0 default IDs in `.env.example` may not exist on a given Vertex region
- README still describes an older TAU/THETA story; this freeze is the authority
- `apply_update` is a no-op in the demo engine path

## 18. Deferred work

Not in this freeze: retuning TAU/DELTA/HYST/W_*, semantic embeddings, vector DB,
Firestore/BigQuery, Cloud Run, calibration, compact decision context, patching
401 collision, production compiler changes, new memory abstractions.

## 19. Reproduction commands

See `docs/REPRODUCE.md`. Default path is MockLLM (`pytest -q`, `python -m app`).
Do not re-run the Gemini scale suite unless intentionally reproducing billing.

## 20. Exact current git state

Filled at freeze time by the working-tree check. Re-run:

```
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git rev-parse main
git status
git log -1 --oneline
```

Recorded when this file was written (pre-commit; working tree dirty):

- Branch: `feat/contextflow-engine`
- Feature HEAD (last commit): `91d58987f85cf8893f06bb0cff8a4c85eec6844e` — `chore: establish ContextFlow implementation baseline`
- `main` / `origin/main`: `011bce5db38554887cb57aaecd14748c20a6f941` — `chore: initialize ContextFlow project structure`
- Do not merge to `main` as part of freeze
- Working tree contains the frozen engine + eval + these docs (uncommitted)
- `eval/out/*.json` remain gitignored; `eval/out/POC_RESULTS.md` is the intended committed summary
- `.env` (absent locally), `.venv/`, `CONTEXTFLOW_AGENT_NOTES.md` stay untracked
