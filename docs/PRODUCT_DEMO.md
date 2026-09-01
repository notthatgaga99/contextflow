# ContextFlow product demo

## REVIEWER DEMO

**CONTROLLED SYNTHETIC ENGINEERING DEMO** · **NOT A NATURAL-CHAT BENCHMARK**

Offline. MockLLM. No GCP, Vertex, credentials, internet, or secrets.

### Launch

```bash
python -m eval.product_demo --serve
```

Open the printed URL (default **http://127.0.0.1:8766/**). A browser tab should open automatically.

### What to click

1. **PLAY SCENARIO** — auto-advances the 15-beat pitch, or **STEP** one beat at a time.
2. Optional: **RETURN TO THREAD** jumps to the outfit return (hero).
3. **RESET DEMO** restarts from beat 1.
4. **Evidence** is optional and secondary (collapsed by default).

### What to watch

- Left: many unfinished workstreams stay alive.
- Center: the conversation, including the return and the clarify.
- Right **STATE**: **CURRENT** / **HISTORY** / **EXCLUDED**.

### Expected hero moment

When the user says **“Okay, back to the outfit.”**:

| Panel | Expect |
|---|---|
| **CURRENT** | **navy** (+ formal/evening constraints if shown) |
| **HISTORY** | **black** superseded by navy |
| **EXCLUDED** | unrelated threads (auth, orders, Lisbon, trivia, …) |

Then **“Maybe the navy one?”** → **NEEDS CLARIFICATION** (no blind guess).

### Known limitations

- Synthetic scripted fixture (not organic multi-user chat).
- Deterministic MockLLM / scripted extracts — not a hosted-model accuracy claim.
- In-memory only for this path; no Cloud Run / Firestore in this demo.
- Not production-ready.

---

**DEMO-READY / RESEARCH-PRODUCT CHECKPOINT** — not production-ready.

## THE PROBLEM

Conventional chat treats every message as one flat timeline. When you jump among unfinished work — auth, deploy, an outfit decision, a trip — the assistant either:

- drowns you in **FULL** history (everything, including the wrong threads), or
- forgets what mattered under **RECENT** (the older decision falls out of the window).

You leave a thought. When you come back, the working state is gone — or contaminated.

## THE IDEA

**ContextFlow lets you leave a thought without losing it.**

**ContextFlow keeps multiple unfinished workstreams alive and reconstructs the right working context when you return.**

## THE DEMO

One browser window. ~60–120 seconds. Deterministic. Offline.

If product invariants fail, the UI shows **DEMO ERROR** and will not pretend success.

### Exact sequence (15 beats)

1. Authentication (JWT / 401)
2. Outfit opens (**black**, corporate)
3. Orders API (overlapping 401 vocabulary)
4. Dinner / food
5. Docker / CI
6. Lisbon travel
7. Checkout frontend (another 401)
8. Presentation deck
9. Trivia distraction
10. Stripe / job-application deadline
11. Correction: **black → navy** (black kept as history)
12. Leave the outfit again
13. Deictic “fix that”
14. **Hero:** “Okay, back to the outfit.”
15. “Maybe the navy one?” → **NEEDS CLARIFICATION**

## THE DIFFERENCE

| View | What you get |
|---|---|
| **FULL history** | Everything — including unrelated threads |
| **RECENT** | Latest turns — can miss older working state |
| **ContextFlow** | The resumed thread’s current working context |

A separate GCP durability path exists under `docs/CLOUD_POC_REVIEWER.md` (and `docs/REAL_GCP_POC.md` / `docs/END_TO_END_GCP_PROOF.md`) — do not conflate it with this local product demo.
