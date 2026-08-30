# ContextFlow product demo

**DEMO-READY / RESEARCH-PRODUCT CHECKPOINT** — not production-ready.

**Fixture label:** CONTROLLED ADVERSARIAL ENGINEERING FIXTURE (synthetic). Not organic chat. Not a production accuracy claim.

## 1. What is ContextFlow?

ContextFlow is a **working-memory layer for context-switching assistants**.

It does not try to remember everything equally. It keeps multiple open workstreams separate and reconstructs the **minimum useful working state** when the user returns.

## 2. What problem does it solve?

Long assistants lose the thread when users jump among unfinished work. Ordinary approaches flatten everything into:

- a chat history window
- naive recency
- RAG over old messages
- task classification
- a memory dump

Those are not the same as a **current working set**.

## 3. Why is ordinary long context insufficient?

FULL HISTORY can contain the right facts and still bury them under unrelated threads.
RECENT windows can forget older decisions.
Retrieval can surface similar text from the wrong workstream.

ContextFlow selects a workstream, then projects only that thread's current decisions/constraints/facts into the answer package — and keeps superseded history auditable without presenting it as current.

## 4. What does the demo show?

A ~60–120 second walkthrough of the synthetic ten-workstream fixture:

1. Several workstreams become active
2. Abrupt switching across unrelated domains
3. Outfit correction: **black → navy** (black retained as superseded)
4. Return to the outfit thread after distraction
5. Working context reconstructs **navy / formal / evening**
6. Unrelated state (Lisbon, Docker, JWT, dinner, …) stays **excluded**
7. Underspecified "maybe the navy one?" → **CLARIFY** (refuse to guess)
8. Side-by-side **FULL / RECENT / ContextFlow** contrast (qualitative, not a leaderboard)

## 5. What happens with 10 workstreams?

The fixture keeps ten open threads (auth, Docker/CI, orders, checkout, outfit, Lisbon, dinner, deck, Stripe app, trivia). Switching does not erase prior working state. Returning reconstructs the selected thread's current package.

## 6. How does ContextFlow preserve working state?

```
conversation → extractor → MemoryWriter → MemoryStore
→ ContextFlow (route) → WorkingContextBuilder → ContextPackage → answer
```

The extractor proposes; the writer is memory authority; ContextFlow is routing authority; `generate()` does not mutate memory.

## 7. How does it prevent unrelated leakage?

`WorkingContextBuilder` projects **asserted** items for the **selected** workstream/referent. Other workstreams remain stored but are listed as excluded from the current package.

## 8. How does it handle uncertainty?

Underspecified or ambiguous turns may produce **no asserted memory** and/or a **CLARIFY** route. That is a safety feature. This demo uses an already-supported fixture turn (`maybe the navy one?`) that yields CLARIFY under frozen routing + MockLLM — routing was not retuned to force it.

## 9. Demonstrated vs not demonstrated

| Claim | Status |
|---|---|
| Local deterministic product demo (MockLLM) | DEMONSTRATED |
| Multi-thread persistence / exclusion / supersession / return | DEMONSTRATED (synthetic) |
| CLARIFY instead of guessing (fixture turn) | DEMONSTRATED (synthetic) |
| FULL ≠ RECENT ≠ working set (qualitative) | DEMONSTRATED |
| Organic / consented-chat accuracy | NOT YET |
| Durable multi-instance persistence | NOT YET |
| Authenticated production deployment | NOT YET |
| Benchmark superiority | NOT CLAIMED |

## 10. How do I run the demo?

```bash
# from the contextflow package root
python -m eval.product_demo          # build snapshot (writes eval/out/product_demo.json; gitignored)
python -m eval.product_demo --serve  # http://127.0.0.1:8766/
```

- **Default path:** MockLLM · $0 · no network · no credentials · no private transcripts
- **Optional Ollama / Vertex:** separate eval harnesses — **not** required for this demo
- Judge interleaved demo (different story): `python -m eval.demo` / `python -m eval.demo --serve`

### Pitch line

> ContextFlow doesn't try to remember everything equally.
> It maintains multiple open workstreams and reconstructs the working state that matters when you return.
