# Consented conversation — FULL vs RECENT vs ContextFlow

**Status:** not executed on a real session (`data/consented/session.json` absent).  
**Controlled PoC evidence** remains `docs/POC_FREEZE.md` / `eval/out/POC_RESULTS.md`. This document is the **case-study** protocol.

---

## Question

Does ContextFlow reconstruct **useful working context** for a downstream model on a real return, or only **name** a task?

A result counts as end-to-end success only if:

1. Resolution is right **or** an honest CLARIFY, **and**
2. The reconstructed package contains `needed_state`, **and**
3. The same answer model can continue **from that package**.

A result counts as end-to-end success only if reconstruction is **sufficient for continuation**, not merely `task_match`.

**Critical failure (do not hide):** correct workstream/referent + thin package + unusable answer. Classify as **memory extraction / representation**, not a gate bug. That list is the production memory spec (`docs/MEMORY_SCHEMA_FROM_CONVERSATION.md`).

---

## Conditions (same user message)

| | Context given to the answer model |
|---|---|
| **A FULL HISTORY** | All messages with `i` &lt; probe, plus the probe utterance |
| **B RECENT** | Last **K=8** messages before the probe (configurable `--recent`), plus the probe |
| **C CONTEXTFLOW** | Frozen engine `handle_turn` on a **human memory snapshot**; `generate()` sees `compiler.render(package)` |

Same `LLM.generate` implementation. Default **Ollama** (`--provider ollama`). **No Vertex** for this case study unless a later, costed hosted-generate demo is approved.

Mock (`--provider mock`) checks wiring only; it is not an answer-quality result.

---

## What is seeded (primary experiment)

At each probe, `InMemoryRegistry` is built from the interpretation sheet (workstreams + clocks). That is **working memory as a human extractor would have stored it**.

This matches the product: ContextFlow sits **on** memory, it does not replace extraction.

`--native-replay` is a **secondary** diagnostic: empty registry, default NEW = raw user text. Expected limitation: one card per utterance, weak returns. **Do not patch routing if this fails.**

---

## Metrics (separate; not a scoreboard)

1. **Resolution** — predicted task/referent vs sheet; CLARIFY vs `gold_policy`
2. **Reconstruction** — `needed_state` present in rendered package; omissions listed
3. **Answer usability** — human: can you continue the workstream from this answer? (yes / partial / no)
4. **Contamination** — `contamination_cues` in package or CF answer
5. **Omission** — needed strings missing from package
6. **Size** — diagnostic `ceil(chars/4)` plus compiler `decision_tokens` / `answer_tokens`. **Not token savings.**
7. **Failure mode** — resolver / representation / compiler / answer model / ambiguity / snapshot clocks / other

---

## Results

| probe | resolution | reconstruction | usability FULL | usability RECENT | usability CF | contamination | omission | sizes | winner | failure |
|---|---|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | — | — | — |

If FULL HISTORY wins a probe, **say so**. If CF CLARIFY is correct, show it.

---

## Visual demo

After a real `e2e.json`:

```
python -m eval.consented_case.render_demo
```

Opens a local HTML grid: bulky full reply vs recent vs compact working context. File is gitignored. Do not paste private utterances into public docs; paraphrase in `docs/CONSENTED_E2E.md` after the run.
