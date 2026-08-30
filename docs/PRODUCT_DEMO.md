# ContextFlow product demo

**DEMO-READY / RESEARCH-PRODUCT CHECKPOINT** — not production-ready.

**Fixture label:** CONTROLLED ADVERSARIAL ENGINEERING FIXTURE (synthetic). Not organic chat. Not a production accuracy claim.

## Pitch

> ContextFlow doesn't try to remember everything equally.
> It maintains multiple open workstreams and reconstructs the working state that matters when you return.

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

| View | Meaning |
|---|---|
| **FULL** | Everything is available, including unrelated material. |
| **RECENT** | Recent context can miss older working state. |
| **CONTEXTFLOW** | Only the selected workstream's current working state is projected. |

Retrieval can also surface similar text from the wrong workstream. ContextFlow selects a workstream, then projects only that thread's current decisions/constraints/facts — and keeps superseded history auditable without presenting it as current.

## Demo architecture

```
HTTP
→ extraction / proposal
→ MemoryWriter (validate + commit)
→ MemoryStore (in-memory default)
→ ContextFlow (route: ACT / CLARIFY / SWITCH / RETURN)
→ WorkingContextBuilder
→ ContextPackage
→ answer  (generate does not mutate memory)
```

## Production boundary

### IMPLEMENTED

- Cloud Run service shape (`deploy/cloudrun.yaml`) with demo labeling
- Health / readiness endpoint
- Request correlation IDs (`x-request-id`)
- Structured redacted decision logs (no raw conversation text)
- Bounded request validation
- Predictable error responses with correlation id
- Memory lifecycle (assert / supersede / retract / abandon)
- Fail-closed writer validation
- Extraction contract (omit invented referents; underspecified → no assert)
- Conversation isolation **within a process**
- Deterministic local product demo (MockLLM)

### NOT YET

- Durable memory across restart
- Authenticated users / private invoker as a production default
- Multi-instance durable state
- Organic / consented conversation evaluation
- Production SLO evidence
- Firestore (or other durable adapter) — **deferred**; `MemoryStore` protocol is the boundary

**Explicit:** in-memory state is process-local. Cloud Run scaling/restart requires durable storage for production multi-instance semantics. Public unauthenticated access is a **demo boundary**.

## 4. What does the demo show?

A ~60–120 second walkthrough of the synthetic ten-workstream fixture:

1. Several workstreams become active
2. Abrupt switching across unrelated domains
3. Outfit correction: **black → navy** (black retained as superseded)
4. **Back to the outfit** after distraction
5. Working context reconstructs **navy / formal / evening**
6. Unrelated state (Lisbon, Docker, JWT, dinner, …) stays **excluded**
7. Underspecified "maybe the navy one?" → **CLARIFY** (refuse to guess)
8. Side-by-side **FULL / RECENT / ContextFlow** contrast (qualitative, not a leaderboard)

Hero moment: return to outfit → NAVY · FORMAL · EVENING, with BLACK → SUPERSEDED BY NAVY in history.

## 5. What happens with 10 workstreams?

The fixture keeps ten open threads (auth, Docker/CI, orders, checkout, outfit, Lisbon, dinner, deck, Stripe app, trivia). Switching does not erase prior working state. Returning reconstructs the selected thread's current package.

## 6–8. Preserve, exclude, uncertainty

- **Preserve:** extractor proposes → writer commits → store retains asserted + historical items with provenance
- **Exclude:** `WorkingContextBuilder` projects only the selected workstream; others remain stored but out of package
- **Uncertainty:** underspecified turns may assert nothing and/or **CLARIFY** under frozen routing (not retuned for the demo)

## 9. Demonstrated vs not demonstrated

| Claim | Status |
|---|---|
| Local deterministic product demo (MockLLM) | DEMONSTRATED |
| Multi-thread persistence / exclusion / supersession / return | DEMONSTRATED (synthetic) |
| CLARIFY instead of guessing (fixture turn) | DEMONSTRATED (synthetic) |
| FULL ≠ RECENT ≠ working set (qualitative) | DEMONSTRATED |
| Production-shaped Cloud Run config + redacted logs | IMPLEMENTED |
| Organic / consented-chat accuracy | NOT YET |
| Durable multi-instance persistence | NOT YET |
| Authenticated production deployment | NOT YET |
| Benchmark superiority | NOT CLAIMED |

## 10. How do I run the demo?

```bash
# from the contextflow package root
python -m eval.product_demo          # build snapshot (eval/out; gitignored)
python -m eval.product_demo --serve  # http://127.0.0.1:8766/
```

- **Default path:** MockLLM · $0 · no network · no credentials · no private transcripts
- **Optional Ollama / Vertex:** separate eval harnesses — **not** required for this demo
- **Cloud Run:** see `deploy/README.md` (optional; Mock path; demo boundary)
- Judge interleaved demo (different story): `python -m eval.demo` / `python -m eval.demo --serve`

Vertex remains evidence for production-shaped LLM integration, not the demo's deterministic correctness mechanism.
