# PoC measured results

Mechanism tables only. Not a benchmark. Token columns are **diagnostic**.
Decision context includes open-task cards and **grows with n**. Answer context
is compact after referent selection. Do not convert those sizes into savings
or “context efficiency.”

Sources (gitignored JSON, generated locally):

- `eval/out/task_count_scale.json` — MockLLM, 512 cells (128 scenarios × 4 systems)
- `eval/out/gemini_validation.json` — Gemini propose-only validation
- `eval/out/context_sufficiency.json` — Mock + Ollama qwen2.5:1.5b answer probes
- `eval/out/context_model_strength.json` — Ollama llama3.1:8b answer probes

---

## Metric vocabulary

| Term | Meaning |
|---|---|
| resolution | predicted task/referent vs gold |
| joint | both task and referent correct |
| policy | ACT vs CLARIFY |
| wrong ACT | acted with incorrect joint resolution |
| clarification | gate/resolver abstained |
| answer-context size | compiled answer package tokens (`ceil(chars/4)`) |
| decision-context size | compiled decision package tokens (open cards + message) |

CLARIFY is not automatically a miss. Split clarify+gold vs clarify+wrong vs wrong ACT.

---

## 1. MockLLM routing (512-cell scale)

Grid: n ∈ {1,2,3,5,8,10}, LOW/HIGH, EXPLICIT/PARTIAL/DEICTIC/CORRECTION,
foregrounds `target_last` / `distractor_last` / `target_active_distractor_fg`
(n=1 uses `target_last` only). ContextFlow uses a lure MockLLM proposal.

### HIGH interference — joint resolution vs n

| system | 1 | 2 | 3 | 5 | 8 | 10 |
|---|---|---|---|---|---|---|
| ContextFlow | 1.00 | 1.00 | 1.00 | 1.00 | 0.92 | 0.92 |
| recency | 0.75 | 0.58 | 0.58 | 0.58 | 0.58 | 0.58 |
| similarity | 0.75 | 0.75 | 0.58 | 0.58 | 0.33 | 0.33 |
| full-history cards | 0.75 | 0.75 | 0.75 | 0.75 | 0.50 | 0.50 |

### HIGH — wrong-ACT rate vs n

| system | 1 | 2 | 3 | 5 | 8 | 10 |
|---|---|---|---|---|---|---|
| ContextFlow | 0 | 0 | 0 | 0 | 0 | 0 |
| recency | 0.25 | 0.42 | 0.42 | 0.42 | 0.42 | 0.42 |
| similarity | 0.25 | 0.25 | 0.42 | 0.42 | 0.67 | 0.67 |
| full-history | 0.25 | 0.25 | 0.25 | 0.25 | 0.50 | 0.50 |

### HIGH — ContextFlow clarification vs n

| n | clarify rate | notes |
|---|---|---|
| 1–5 | 0.00 | joint 1.00 |
| 8 | 0.25 | 3 of 12 cells; sibling-401 PARTIAL |
| 10 | 0.25 | same pattern |

### HIGH — ContextFlow task / referent vs n

| n | task | referent | joint | mean decision toks | mean answer toks |
|---|---|---|---|---|---|
| 1 | 1.00 | 1.00 | 1.00 | 35.5 | 13.0 |
| 2 | 1.00 | 1.00 | 1.00 | 54.5 | 13.8 |
| 3 | 1.00 | 1.00 | 1.00 | 71.7 | 13.8 |
| 5 | 1.00 | 1.00 | 1.00 | 106.5 | 13.7 |
| 8 | 0.92 | 0.92 | 0.92 | 116.8 | 9.7 |
| 10 | 0.92 | 0.92 | 0.92 | 142.0 | 9.3 |

Answer tokens dip at n=8/10 because CLARIFY has no answer package on those cells.

### LOW interference — ContextFlow

Joint **1.00** at every n. Wrong-ACT **0**. Clarify **0**.
Baselines still degrade (recency ~0.58 from n=2; similarity down to 0.33 at n=8/10;
full-history 0.75 then 0.50). Decision tokens still grow with n (e.g. ~36 at n=1
to ~179 at n=10 on ContextFlow ACT cells).

---

## 2. Gemini 2.5 Flash-Lite validation

**Experimental record, not a product cost claim.**

| field | value |
|---|---|
| provider | Vertex AI |
| model | `gemini-2.5-flash-lite` |
| region used | `us-central1` |
| temperature | 0 |
| reps | 1 |
| scale ContextFlow cells | 128 |
| exp2 ContextFlow cells | 4 |
| propose calls | 135 (3 smoke + 132) |
| generate / embed | 0 |
| prompt tokens | 41,265 |
| candidate tokens | 13,302 |
| usage-based USD estimate | ~0.007 (list-price heuristic in the eval script) |
| embeddings | hash MockLLM (not Gemini embeddings) |

HIGH joint vs n for ContextFlow: **same as Mock**
`1.00, 1.00, 1.00, 1.00, 0.92, 0.92`. Wrong-ACT **0**.

Scale ContextFlow: 128 cells, 6 clarifications, 0 Gemini errors on the full run.

Clarify split:

- clarify + gold resolution: 4 (class H)
- clarify + wrong resolution: 2 (class E: `HIGH-PARTIAL-distractor_last` n=8 and n=10 → H5)
- wrong ACT: 0

Gemini did not remove the sibling-401 boundary and did not turn it into wrong ACT.

### Exp2 — paired `"still getting the 401"` (n=2 sibling 401 loops)

Gold follows the foregrounded 401-loop. ContextFlow predicted gold task/referent
in all four conditions and **CLARIFY** (no wrong ACT). Recency followed last
mention (wrong when active-task and last mention disagree). Similarity / full-history
often ACT on the colliding sibling loop.

---

## 3. Answer-context probes (Ollama)

Routing frozen (MockLLM proposals + production resolver/gate). Independent
variable is the **answer** model. 10 scenarios × 3 compiler modes.

### qwen2.5:1.5b (`context_sufficiency.json`)

| mode | probe accuracy | wrong-loop rate | mean answer toks | mean total toks |
|---|---|---|---|---|
| FULL_TASK | 0.60 | 0.30 | 37.1 | 86.6 |
| REFERENT_COMPACT | 0.90 | 0.00 | 27.7 | 77.2 |
| MERGED_COMPACT | 0.70 | 0.00 | 76.9 | 76.9 |

### llama3.1:8b (`context_model_strength.json`)

| mode | probe accuracy | wrong-loop rate | mean answer toks | mean total toks |
|---|---|---|---|---|
| FULL_TASK | 0.90 | 0.10 | 37.1 | 86.6 |
| REFERENT_COMPACT | 0.90 | 0.00 | 27.7 | 77.2 |
| MERGED_COMPACT | 0.70 | 0.00 | 76.9 | 76.9 |

Compact **answer** context is smaller than FULL_TASK. On 8b, probe accuracy of
FULL vs COMPACT is the same (0.90). This is **not** a compact-vs-full accuracy
win and is **not** a Gemini result.

Mock scripted answers: FULL and COMPACT probe accuracy 1.00; MERGED 0.00 (mock
truncation / render), not a routing result.

---

## 4. What not to read into these tables

- Decision-token growth is expected from the open-card dump.
- Baseline wrong-ACT is high because baselines always ACT.
- Gemini cost is one experimental run, not an operating budget.
- Joint 0.92 at n=8/10 is fail-closed clarification on a designed collision,
  not “92% production accuracy.”
