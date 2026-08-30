# Memory / working-context benchmark gap

**Date:** 2026-08-29  
**Status:** audit. No new downloads. No manufactured benchmark. No CF gold invented.

**Target phenomenon (product):** in **one** conversation, `A → unrelated B → (optional C) → return to A`, possibly without an explicit “switching tasks” announcement; A may have **multiple unresolved loops**; later language may be deictic or corrective; the correct **continuation** needs reconstructed **state** (decisions, constraints), not only a retrieved fact.

---

## What existing benchmarks can test

| Resource | Can test | Unit of evaluation |
|---|---|---|
| **LongMemEval** | Fact extraction, multi-session QA, temporal QA, knowledge update, abstention over a **compiled** history | Post-hoc **question → answer** after all sessions |
| **LoCoMo** | Long two-party recall, temporal/event QA, summarization | Post-hoc QA / summary on constructed long chats |
| **MultiWOZ / SGD** | Domain/slot tracking in a **tourist/API schema** | DST / intent at a turn |
| **Needle / RULER / long-context** | Finding a planted span in a long prompt | Retrieval/attention |
| **WildChat long-tail** (our inspect, n=80) | Whether public ChatGPT logs contain the phenomenon | Manual: **0** heterogeneous returns |
| **ContextFlow PoC grid** | Interference-resistant **resolution + wrong-ACT** on a **controlled family** | Probe utterances we authored |
| **Consented case study** (planned) | RB-WSR vs full vs recent on **one real thread** | Human sufficiency, not leaderboard |

---

## What they cannot test (for us)

| Gap | Why |
|---|---|
| Heterogeneous **in-thread** returns (coding ↔ clothing ↔ travel) | LME-S glue ≠ one user; MultiWOZ related domains; WildChat sample had shotgun Q&A **without** resume; LoCoMo is long **persona** chat |
| Unannounced switch | Benchmarks often use explicit QA (“what did I say about X?”) not “fix that” amid siblings |
| Multiple open loops on A | Memory QA usually one fact; DST one slot bundle per domain |
| Deixis / correction as **policy** (ACT vs CLARIFY) | Gold is an answer string, not a gate |
| Working-set **sufficiency** | Retrieving the navy fact ≠ excluding AUTH and including the lighting constraint |
| Fail-closed routing | Abstention in LME is “event didn’t happen,” not “which loop now?” |

**Do not** treat vendor LoCoMo/LME accuracy as ContextFlow evidence.

---

## What a future ContextFlow-specific evaluation should measure

When we have **consented real** (or later licensed) in-stream probes — **not** a synthetic win-set:

1. **Resolution:** workstream, referent, utterance kind  
2. **Policy:** ACT vs CLARIFY vs gold_policy  
3. **Wrong-ACT**  
4. **Working-set sufficiency:** required decisions/constraints/facts present; `should_not_carry` absent  
5. **Downstream usability:** same answer model, FULL vs RECENT vs CF  
6. **Critical miss:** correct id + thin set  
7. **Candidate miss:** gold workstream not retrieved (store/retriever), vs resolver miss  

Sample size: case study first (one session, several returns if they exist). Scale only after the phenomenon is real.

---

## Next experiment (not a leaderboard)

Use the owner-consented transcript when provided. Public hunting is **closed**. Do not author a clothing/JWT dialogue to fill this gap.
