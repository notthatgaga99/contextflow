# Consented conversation — substrate inspection

**Date:** 2026-08-29  
**Deadline context:** 7 September  
**Public datasets:** closed. WildChat long-tail (`docs/WILDCHAT_LONGTAIL_INSPECTION.md`) is enough to stop hunting. Heterogeneous-return count there was **0**.

**Routing freeze:** TAU=0.20, DELTA=0.08, HYST=0.05, W_* unchanged. No ForegroundReferent, no embeddings, no Gemini grid, no synthetic “realistic” corpus.

---

## Status

**BLOCKED on the raw consented transcript.**

There is no `data/consented/session.json` in this workspace. Phases 3–4 (interpretation of *this* chat, FULL vs RECENT vs ContextFlow answers) cannot be filled with honest numbers yet.

This is the correct outcome. Manufacturing a clothing/travel/coding dialogue would repeat the synthetic-substrate mistake.

**What you do next:** paste or save a consented JSON session (schema in `data/consented/session.schema.json`). Then we fill the interpretation sheet and run `python -m eval.consented_case.run`.

---

## Sampling / filter (this substrate)

| Rule | |
|---|---|
| Source | One owner-consented thread, not a public dump |
| Unit | One conversation, chronology preserved |
| Prefer | Multiple heterogeneous intentions; returns if they occur **naturally** |
| Do not | Rewrite, insert boundaries, or pick turns because they look good for ContextFlow |
| Privacy | Strip names, addresses, phones, emails, credentials, keys **before** the file exists |
| Public artifacts | Paraphrase only; raw stays gitignored |

---

## Inspection checklist (run after the file exists)

For the whole thread, count (same criteria as WildChat, one session):

1. Distinct intentions / workstreams (not every topic is a task)
2. Unrelated topic switches
3. Genuine returns (`A → unrelated B → return to A`)
4. Heterogeneous returns (different domains, not sibling slots)
5. Unresolved paused vs abandoned
6. Correction / retraction
7. Deixis (`that`, `the other one`, `back to…`)
8. Ambiguous reference (CLARIFY would be reasonable)

**Selected demonstration turns** are the genuine returns (and any honest CLARIFY cases). Not every user turn.

---

## Length / structure (fill when file exists)

| | |
|---|---|
| session_id | — |
| n messages | — |
| n user turns | — |
| n workstreams (human) | — |
| n genuine returns | — |
| n selected probes | — |

---

## Why this substrate (once present)

The product claim is: ContextFlow is a **working-context layer over conversation history / extracted memory**, not “WildChat contains CF gold.”

The experiment is a **case study**, not a statistical benchmark.

---

## Harness (ready, not executed on real data)

```
python -m eval.consented_case.run --provider ollama
python -m eval.consented_case.run --provider mock --native-replay
python -m eval.consented_case.render_demo
```

`--native-replay` replays user turns through the **frozen** engine with default NEW cards (raw utterance as goal/loop). That is a **representation** diagnostic. It is not the product path. Production memory extraction is still `apply_update` no-op.

The **primary** comparison seeds the registry from the **human interpretation snapshot** at each probe. That tests the layer **given** working memory, which is what a production extractor must eventually supply.

If native replay cannot return to A, **document it**. Do not patch the gate.
