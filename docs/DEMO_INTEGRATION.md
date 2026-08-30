# Demo integration plan (Sep 7)

Two demos. Do not merge them into one story.

| | Judge demo | Consented case study |
|---|---|---|
| Command | `python -m eval.demo` | `python -m eval.consented_case.run` then `render_demo` |
| Substrate | Authored interleaved coding tasks | Owner conversation |
| LLM | MockLLM, $0 | Ollama generate (same model for FULL/RECENT/CF) |
| Claim | Interference-resistant **resolution + fail-closed** on a **controlled** family | Working-context reconstruction on **one** real thread |
| Visual | Existing UI: proposal vs gate vs compact package | Human workstream names first; ids in small type; FULL vs RECENT vs CF |

**Do not** change `eval/demo.py` to ingest the consented log. The judge demo is frozen evidence.

---

## Visual distinction (case study)

Must be obvious without a score:

1. **FULL HISTORY** — unrelated workstreams in the prompt; answer may mix or stay generic.
2. **RECENT** — return target **missing** if the window is after the detour.
3. **CONTEXTFLOW** — selected workstream + selected loop + decisions/constraints/entities from the snapshot.
4. **ANSWER** — continuation of **that** work, or an on-screen CLARIFY.

If FULL wins, the slide says FULL won and **why** (usually a fact never extracted onto the card).

---

## Integration steps (after transcript)

1. Sanitize → `data/consented/session.json`.
2. Fill `docs/CONSENTED_INTERPRETATION.md` + `eval/consented_case/interpretation.json`.
3. Run Ollama comparison. Human-score usability.
4. Render local HTML. Screenshot **paraphrased** panels for any public deck.
5. Optional Cloud Run: **Mock judge demo only**, unless architecture review says otherwise.
6. Do not add a second Gemini grid to “make the demo pop.”

---

## Narrative (final story)

A real conversation gets messy. The user leaves a problem, talks about something else, comes back.

ContextFlow does not replay the whole thread. It reconstructs the relevant working context. The downstream model continues — or it fails because the **card** lacked a fact, which tells us what extraction must store.

That sentence is the product. Task-id accuracy alone is not.
