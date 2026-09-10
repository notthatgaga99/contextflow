# ContextFlow Medium article — paste into Medium

**Publish as:** Public  
**Title:** ContextFlow: Leave a Thought Without Losing It  
**Subtitle:** An attention-aware context layer that reconstructs the right working state when AI agents switch tasks

**Live demo (judges):** https://contextflow-demo-cjraqyv4hq-el.a.run.app/  
**Code:** https://github.com/notthatgaga99/contextflow/tree/feat/submission-polish  
**Technical doc:** https://docs.google.com/document/d/1-HXFMotpgncacqAH342cJ3l0V_I-ojsTuP0H2dqcANs/edit?usp=sharing

**Images to upload (in order):**
1. `contextflow-blog-hero.png` — under the title
2. `contextflow-blog-problem.png` — in “The problem”
3. `contextflow-blog-architecture.png` — in “How it works”
4. `contextflow-blog-return.png` — in “One demo moment”
5. Optional: screenshot of the live UI on the hero return beat

Image files are in your Cursor assets folder (generated this session).

---

## Body (copy below)

### Title and description

AI agents don’t mainly fail because they can’t read a long chat.  
They fail because they don’t know **which unfinished task** you mean when you say “fix that” or “back to the outfit.”

**ContextFlow** is a working-context control layer for multi-task agents. It keeps several unfinished workstreams alive and reconstructs only what should matter **now**.

> Tagline: *Leave a thought without losing it.*

*[Insert image: contextflow-blog-hero.png]*

---

### Use case (the problem)

In one conversation you might be debugging a **401**, choosing an **outfit**, planning **travel**, and chasing a **deadline**.

Today’s defaults break in two ways:

| Approach | What goes wrong |
|---|---|
| **Full history** | Everything is dumped into the model — noise, cost, wrong-thread contamination |
| **Recent window** | Older decisions fall out — you lose the correction you already made |

*[Insert image: contextflow-blog-problem.png]*

**Example failure:** you assumed the outfit was **black**, later corrected to **navy**, then jumped away. When you return, a naive agent either forgets navy or mixes in auth/travel trivia.

---

### How we solve it

One principle: **the model proposes; the runtime decides.**

1. **Route every turn** into a bounded state: CONTINUE / SWITCH / RETURN / NEW / or **CLARIFY** (ask instead of guessing).  
2. **Keep durable workstreams** — goal, open loops, decisions, constraints.  
3. **Commit structured memory** with explicit updates (assert / supersede / retract) — corrections don’t silently delete history.  
4. **Build a minimum working set** for the answer model:
   - **CURRENT** — what is true now (e.g. navy)  
   - **HISTORY** — what was superseded (e.g. black)  
   - **EXCLUDED** — other open threads that must not leak in  

*[Insert image: contextflow-blog-architecture.png]*

On Google Cloud: **Cloud Run** serves the demo, **Firestore** holds durable state on the technical proof path, **Gemini 2.5 Flash-Lite** is used for extract/answer where enabled.

---

### Architecture (simple)

```
User message
  → propose memory patches (LLM)
  → MemoryWriter commits (authority)
  → soft LLM task proposal
  → deterministic gate (ACT or CLARIFY)
  → reconstruct CURRENT / HISTORY / EXCLUDED
  → answer model (read-only)
```

---

### Implementation steps (step-by-step)

1. Model each unfinished task as a **workstream** (not a flat transcript).  
2. After each user turn, extract proposed memory changes; only a writer commits them.  
3. Resolve what “that” refers to using task/loop mention state + a fail-closed gate.  
4. On RETURN, rebuild the working set for the selected workstream only.  
5. If evidence is thin or sibling cues collide → **CLARIFY**.  
6. Ship a public Cloud Run product demo so anyone can press PLAY.

**Try it (no login):** https://contextflow-demo-cjraqyv4hq-el.a.run.app/  
Click **RESET** → **PLAY SCENARIO**. Watch the caption strip guide you through 15 beats.

---

### One demo moment (what judges should notice)

*[Insert image: contextflow-blog-return.png]*

When the user says **“Okay, back to the outfit.”**:

- **CURRENT** shows **navy** (and formal/evening constraints if shown)  
- **HISTORY** keeps **black** as superseded — the assumption we falsified  
- **EXCLUDED** lists unrelated threads (auth, orders, travel, trivia, …)

Then **“Maybe the navy one?”** → **NEEDS CLARIFICATION** — ContextFlow refuses a blind guess.

This is a **controlled synthetic engineering demo** (MockLLM), not a claim of natural-chat benchmark wins.

---

### What makes it unique

- Not “more RAG.” Not “dump more tokens.”  
- **Authority split:** propose vs decide vs commit vs answer.  
- **Fail closed:** wrong-action avoidance under interleaved tasks.  
- **Human-shaped resume:** leave a thread, come back, don’t restate everything.

---

### Stack

Python · FastAPI · Cloud Run · Firestore · Gemini 2.5 Flash-Lite · Docker · Artifact Registry · Cloud Logging · pytest

---

### Closing

Don’t make AI remember everything.  
Make it remember **what makes the next interaction obvious**.

*ContextFlow — leave a thought without losing it.*

---

## Medium upload checklist

- [ ] Create story on medium.com  
- [ ] Paste title + subtitle + body  
- [ ] Upload 4 images in the slots marked above  
- [ ] Add 1 live screenshot of the hero beat from the demo URL  
- [ ] Links: demo, GitHub branch, Google Doc  
- [ ] Publish → copy public URL into the hackathon form  
