# LongMemEval as ContextFlow substrate — candidate mining (no gold)

**Date:** 2026-08-28  
**Freeze:** `feat/submission-polish` @ `4b1b4e9`  
**Not an experiment result.** No engine run. No Gemini/Vertex. No gold `task`/`referent`/`ACT` labels.

**Question:** Can LongMemEval replace most of our **hand-authored interleaved** conversations as the next evaluation substrate?

**Short answer:** **No, not as a drop-in user stream.** Use it only as a **licensed public source of session *style* and post-hoc memory QA**, then human-annotate a **tiny in-stream subset** if we want personal-life domains. It does **not** replace the synthetic 18-probe packet for in-conversation task/referent/CLARIFY.

---

## 1. License / provenance

| Item | Value |
|---|---|
| Dataset | LongMemEval (ICLR 2025); **cleaned** Hugging Face revision |
| Paper | Wu et al., *LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory*, arXiv:2410.10813 |
| Code | https://github.com/xiaowu0162/LongMemEval (MIT) |
| Data used here | https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned (license: **MIT** on the dataset card) |
| Files downloaded | `longmemeval_oracle.json` (15.4 MB), `longmemeval_s_cleaned.json` (277.4 MB) |
| SHA-256 oracle | `821a2034d219ab45…` (full: compute locally; 15 388 478 bytes) |
| SHA-256 S | `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` |
| Not downloaded | `longmemeval_m_cleaned.json` (~2.74 GB) — unnecessary for this inspection |
| Local path | `data/longmemeval/` (**gitignored**; do not commit) |
| Construction (authors) | Attribute/background facts → **simulated** evidence sessions; haystacks padded with **ShareGPT** and **UltraChat** filler sessions; then a **held-out question** |
| Privacy | Public benchmark. Fillers are third-party chat dumps. Not Ericsson/user logs. Still: do not treat ShareGPT lines as *this product’s* users. |

Official LME gold is **`question` → `answer` string** (and `has_answer` / `answer_session_ids` for retrieval). That is **not** ContextFlow gold.

---

## 2. Scale (what we actually opened)

| Split | Instances | Sessions / instance | Turns / instance (all roles) | User turns / instance | Role of split |
|---|---|---|---|---|---|
| **oracle** | 500 | min 1 / med **2** / max 6 (**948** sessions total) | med **23** (10 960 turns) | med **11.5** (5 479 user) | Evidence sessions only |
| **S cleaned** | 500 | min 38 / med **48** / max 62 (**23 867** sessions) | med **491** (246 750 turns) | med **243** (122 416 user) | Evidence + fillers |

Question types (both splits, 500 each): temporal-reasoning 133, multi-session 133, knowledge-update 78, single-session-user 70, single-session-assistant 56, single-session-preference 30. **Abstention** (`*_abs`): **30**.

S session-id prefixes (counts): `sharegpt*` **6179**, `ultrachat*` **6008**, `answer*` **948**, plus hashed simulated ids. Fillers dominate the long history.

---

## 3. What the conversations actually are

### 3.1 Oracle / `answer_*` sessions (best-case “one persona”)

These are **LLM-simulated personal chats**: cars, mortgages, book clubs, yoga, pets. Facts are often injected with **“By the way, …”** (~**17%** of oracle user turns). Assistants frequently say they have no local knowledge (generic LLM). Sessions stay **thematically nearby** (detailing + GPS + mpg + insurance) rather than coding ↔ clothing in one turn.

This is **not** production agent/debug traffic. It is also **not** raw human logs.

### 3.2 S haystacks (what “long history” means here)

Adjacent sessions are usually **different chats glued together**, not one user switching intention.

Example openings on instance 0 (`What degree did I graduate with?`): river-crossing puzzle (ShareGPT) → fitness + “by the way” fact → radiation-therapy lecture outline → *Heat*/Joker rewrite → “please continue 10 examples” → entrepreneurship podcasts → pet grooming → mussel larvae → trading UI mouse clicks → luxury cruises → “explain bitcoin like I’m 10” → Europe trip.

A crude keyword check on 80 random S instances: **255** adjacent first-user messages in different coarse buckets vs **41** overlapping, when both sides matched a bucket at all. That “heterogeneity” is **compilation**, not a single interlocutor.

**Implication:** treating S as one ContextFlow registry of open loops would test **retrieval over a junk drawer of strangers’ chats**, not **routing under one user’s interleaved workstreams**.

### 3.3 Evaluation unit mismatch

| LongMemEval | ContextFlow hypothesis |
|---|---|
| After all sessions, answer a **memory QA** | At a **user turn inside** the stream, bind task/referent and ACT vs CLARIFY |
| Gold = factoid / count / date / “not enough info” | Gold = workstream + object + decision |
| Abstention = question about a **non-event** | CLARIFY = **which open loop** is meant **now** |

You cannot score ContextFlow by LME’s `answer` field.

---

## 4. Phenomena vs the hypothesis

| Phenomenon | In oracle in-stream? | In S as one user? | Notes |
|---|---|---|---|
| Heterogeneous domain switch | Mild (car vs friend-move; still “life”) | **Fake** (ShareGPT hops) | Does not substitute S03-style clothing-after-JWT |
| Return to a prior topic | Occasional (`going back to…`, Holiday Market) | Returns are **across compiled sessions**, not earned | |
| Ambiguous reference | Rare genuine (`Tue or Thu` meeting) | QA abstention is **post-hoc** | |
| Correction | Rare real (`I meant FreshMart`; `Wait, 125 stars not 400`) | “actually” usually = **hedge**, not referent repair | |
| Lexical collision | Weak (two sneaker models; Tableau vs Power BI) | Many collisions are **different speakers** | |
| Abstention-worthy **in-stream** | Sparse | LME abs questions are **after** history | |
| Task ≠ referent | Not represented as workstream cards | — | |
| Agent coding loops | Essentially absent | Occasional ShareGPT code, **not** the same user as the persona facts | |

Regex on **5 479** oracle user turns (illustrative, not labels): `by the way` 926; `which one` 43; `go back` 14; `wait,` 8; `what about that/the` 6; `the other` 2; `fix that` 1; `I meant` 1. Strong in-stream routing language is **scarce**. The one `fix that` is **“fix that leaky faucet”** as a **new DIY topic**, not a pointer to an open loop.

---

## 5. Candidate turns (mining only — **no gold**)

Full table: `eval/longmemeval/CANDIDATE_TURNS.md` (40 items). Categories are **hypotheses for later humans**, not answers.

**Do not** copy LME `answer` into ContextFlow gold.

---

## 6. Unsuitable as ContextFlow probes (why)

1. **All ShareGPT/UltraChat sessions in S** — not the same speaker as `answer_*` facts.  
2. **Most “By the way, [dated fact]” turns** — benchmark fact injection, not natural deixis.  
3. **LME `question` rows** — wrong unit (post-hoc QA).  
4. **`fix that leaky faucet`** — introduces work; does not resume a loop.  
5. **“which one feels more comfortable”** for two products **just listed by the assistant** — local choice, not memory routing.  
6. **S adjacent-session “switches”** — compilation artifacts.  
7. **Abstention LME questions** — useful analog for “I don’t know the fact,” **not** “which open 401.”  
8. **Duplicate `*_abs` haystacks** that clone a non-abs instance’s sessions.

---

## 7. Smallest human-annotation subset (if we proceed at all)

**Do not expand the hand-authored 18.** Optional **add-on** only:

**12 in-stream user turns**, all from **oracle `answer_*` sessions**, windows = that session (or the 1–6 evidence sessions of that instance), **never** S fillers:

| Priority | Instance (approx.) | Why try |
|---|---|---|
| 1 | `e56a43b9` “I meant FreshMart” | Entity correction |
| 2 | `0f05491a` “Wait… 125 stars not 400” | Self-correction |
| 3 | `80ec1f4f` “Wait, I might have misspoken” | Correction |
| 4 | `dfde3500` Juan meeting Tue vs Thu | Genuine ambiguity → likely CLARIFY |
| 5 | `ba61f0b9` “Going back to … Rachel’s team” | Resumption |
| 6 | `c8090214` go back to Holiday Market | Resumption / shopping |
| 7 | `gpt4_76048e76` “Anyway, back to the Kuat Transfer” | Same-domain return after aside |
| 8 | `c6853660` drip coffee maker vs French press | Same-domain object switch |
| 9 | `a89d7624` Denver / Red Rocks | Travel return |
| 10 | `gpt4_2f56ae70` Disney+ documentary uncertainty | Partial ID |
| 11 | One **knowledge-update** instance’s *later* user turn that **contradicts** an earlier fact (pick after reading; don’t use the LME question as the probe) | Same entity, new state |
| 12 | One **multi-session** instance where two evidence sessions discuss **similar objects** (two trips, two jobs) and a user line is underspecified | Collision candidate |

If two annotators cannot agree on even these 12, **stop** — the substrate does not yield CF-style gold.

---

## 8. Recommendation

**Do not replace the synthetic interleaved corpus with LongMemEval-S.**

| Use | Don’t use |
|---|---|
| MIT-licensed public data; oracle sessions as **optional personal-domain flavor** after the 18-probe human pilot | S haystack as one conversation |
| LME abstention as a **citation** that “I don’t know” exists in memory QA | LME answers as routing gold |
| Motivate **why** we still need hand-authored in-stream probes | Spend cloud credits running CF or Gemini on 500 LME questions as if that were the hypothesis |

**Next spend:** two humans on the existing **interleaved 18**, not a 500-question LME leaderboard and not more synthetic sessions.

---

## 9. What was not done

- No ContextFlow / Ollama / Gemini / Vertex  
- No `app/` changes  
- No gold labels  
- No LongMemEval-M download  
- No commit / push  
