# Dataset discovery: naturally occurring heterogeneous returns

**Date:** 2026-08-29  
**Status:** discovery only. No ContextFlow run. No Vertex. No production changes. No large downloads. No commit/push.  
**Question:** Is there a **public** conversation dataset whose **individual sessions** already contain fickle, in-stream `A → unrelated B → … → return to A` behavior?

**Gold:** none. No ContextFlow labels. Classifications below are **phenomenon tags**, not routing gold.

---

## Decision gate

**Overall: C — public conversational datasets, as currently published, are unsuitable as a dense substrate for this phenomenon.**

No candidate is **A (strong)**.

The only **B (promising but thin)** lead is the **WildChat long tail** (conversations with ≥10 user–assistant rounds). Paper-level evidence shows **topic-switching exists**, but **most conversations are 2-turn**, **returns after an unrelated topic are not measured**, and we **did not** download the corpus. Until a **tiny filtered sample** is approved and hand-read, WildChat must not be treated as proven.

**If the requirement is the JWT ↔ clothing ↔ travel pattern at usable density inside one session: no public dataset currently satisfies it. Do not manufacture it.**

---

## How to read “diversity”

Corpus-level diversity (coding **and** travel **and** recipes **in the collection**) is **not** within-session diversity. ThoughtTrace, LMSYS, and WildChat all look “topically diverse” **across rows**. The product question is **one row / one session**.

---

## 1–3. Candidates investigated (provenance, license, session integrity)

| Dataset | Provenance | Human? | Session integrity | License | Length (published) |
|---|---|---|---|---|---|
| **WildChat / WildChat-1M / 4.8M** | Opt-in free ChatGPT via HF Spaces; hashed IP; 2023–2025 | Human–LLM, in the wild | One conversation id = one chat thread (turns linked by header). **Not** ShareGPT glue. Same **user** can have **many** conversations (hashed_ip). | ODC-BY (WildChat); 4.8M similarly research-oriented; **PII redaction + toxicity filter**; still residual PII/toxicity risk | **Mean ~2.5 turns**; ~41% multi-turn; **3.7% >10 turns** (1M paper). 4.8M still short on average. |
| **LMSYS-Chat-1M** | Vicuna demo + Chatbot Arena, 210k IPs, 2023 | Human–LLM | One sample = one site conversation. Arena is often **one prompt**, not a life session. | LMSYS terms (gated); PII stripped; unsafe kept in some releases | **Avg 2.0 turns**; ~67% two-turn |
| **ThoughtTrace** (2026) | Prolific + IRB; 10 min × **two self-defined tasks**; 20 models | Human–LLM, **elicited** | **One conversation = one task attempt.** Users **start a new chat** for a new task. Ids like `user897_task1` vs `task2`. | Public HF (`SCAI-JHU/ThoughtTrace`, ~30 MB full set — **not downloaded here**). Inspected **official examples JSONL** (~20 convos) from GitHub. | **Median 8 turns**; longer than WildChat/LMSYS |
| **ShareGPT / ShareGPT52K** | Scraped shared ChatGPT links | Human–LLM | **Unknown / messy.** HTML; canned replies; possible **multi-chat paste**; later pipelines **split** long threads by token budget. | Informal scrape; **PII**; 4chan-era collection | Long threads exist; **integrity not trustworthy** |
| **ShareLM** (ACL 2025) | Voluntary plugin + **union of other public sets** (incl. WildChat, LMSYS, PRISM, HH) | Mixed | Plugin subset: consenting one-thread chats. **Collection union is not a new phenomenon source.** | Permissive where model ToS allow | Not a dedicated long multi-topic benchmark |
| **PRISM** | 1.5k survey participants; 8k live LLM chats | Human–LLM | One conversation tree; **unguided / values / controversy** | CC (see HF card) | **3.4 ± 1.6 turns** |
| **OASST1** | Crowd **conversation trees**; many **contributors** per tree | Human–human (prompter/assistant roles) | A **thread** is a path in a **tree**. Different people can continue. **Not one user’s fickle session.** | Apache-2.0 | Trees can be deep; **not one-user traffic** |
| **Multi-Session Chat (MSC)** | Crowd **persona** chat over **5 sessions** | Human–human WOZ | Returns are **across sessions** (hours/days), not in-stream A–B–C–A | ParlAI research | ~6–7 turns **per session** |
| **TopiOCQA** | Two annotators; Wikipedia **related** docs | Human–human WOZ | One conversation; **~4 Wikipedia pages** as “topics” | CC BY-NC-SA | ~13 QA turns |
| **NTM / Context-Agent** (2026) | **LLM-generated**, then human polish | **Synthetic** | Designed topic shifts (planning + coding) | GitHub | Long, **manufactured** |
| **CANDOR** | Strangers on **video chat** | Human–human | One call | Request-only | Social, not agent workstreams |
| **HH-RLHF, UltraChat, SODA, Magpie** | Preference / **synthetic** instruct | Not organic multi-intention agent use | Short or simulated | Various | Unsuitable |
| **MultiWOZ 2.2** | Tourist WOZ | Human–wizard, **scripted goals** | One dialogue | MIT | See prior report |
| **LongMemEval** | Simulated persona + **ShareGPT/UltraChat haystack** | Mixed | **S is glued strangers** | MIT | See prior report |

**ShareChat** (Indic social app) is **not** a public LLM-session corpus; ignored.

---

## 4–10. Within-session structure (what we actually know)

### WildChat

- **Length:** Too short for working-set demo in the bulk. Upper tail exists (3.7% >10 turns on 1M).
- **Topic diversity:** **Across** the corpus: coding, writing, politics, roleplay, Midjourney prompts, toxicity. **Within** a typical session: one request or a short follow-up.
- **Switching:** Paper **explicitly lists topic-switching**. Published example is **two consecutive user turns** in **one** conversation: Chinese slang → circle equation. That is **A → B**, **not** a return. Classification: **new intention**.
- **Returns / heterogeneous return / deixis:** **Not reported.** Independent work (**Do LLMs Benefit from Their Own Words?**, 2026) **filters out** “off-topic or loosely structured” WildChat/ShareLM chats when studying technical multi-turn QA — i.e. **fickleness is treated as noise**, not as a labeled phenomenon.
- **One analysis** (personalized-RLHI writeups) reports ~**40%** of user **messages** as “new request / topic shift.” In 2-turn chats that is **opening a new ask**, not `A→B→C→A`.
- **Unresolved intentions:** Possible in the long tail; **unmeasured**.
- **Demo artifact:** Possible **only after** a **small** `turn≥10` (or ≥15) English, non-toxic sample is hand-inspected. **Not done** (no large download).

### LMSYS-Chat-1M

- **C.** Arena/demo usage: coding and one-shot questions. Avg 2 turns. Topic clustering is **prompt-level**, not in-session return.

### ThoughtTrace (examples inspected)

Official sample (~20 conversations, GitHub `ThoughtTrace_examples.jsonl`):

| session_id (examples) | Apparent intention | In-session return to an *unrelated* prior intention? |
|---|---|---|
| user804_task2 | Soy-milk straining | No — deepen one task |
| user584_task1 | Easy cooking | No |
| user584_task2 | Back workout | **Separate conversation** from cooking |
| user897_task1 | Asset allocation | No |
| user897_task2 | Bitcoin in FIRE portfolio | **New conversation**, same user, **not** a return inside task1 |
| user369_task2 | Laptop purchase | Single decision task |
| user528 / 1020 / 353 | Study / language / motivation | Single-task deepening |

Paper: **57%** of user turns **extend the current task**; **12.5%** “completely new request”; **Task Reorientation** exists as a **thought** type. Collection: **10-minute task windows**; **new chat for a new task**.

**Classification of this sample:** ordinary continuation / new intention **across conversations**. **No** genuine in-session heterogeneous return in the published examples.

Corpus topic pie (travel, food, business, …) is **between** conversations.

### TopiOCQA

- **~4 topics/session** by **Wikipedia document**. Switches are **related** encyclopedia hops (seed NQ article → hyperlink neighbors). **Not** clothing after JWT. Human WOZ, not organic agent use. **C** for this product claim. (Useful later only as **related-topic** retrieval, not as the killer demo.)

### MSC

- **C** for in-stream CF. Returns are **session 3 recalls session 1 persona**, like LongMemEval’s **wrong unit**.

### NTM

- **C / manufacture.** LLM-written non-linear dialogues. Matches the **story** and **fails** “naturally occurring.”

### OASST / PRISM / CANDOR / ShareGPT

- OASST: crowd trees, **C**.
- PRISM: short value chats, **C**.
- CANDOR: social video, **C**.
- ShareGPT: **integrity + PII → C** as primary substrate.

### MultiWOZ / LongMemEval

See §§14–15.

---

## 11. Privacy

| | |
|---|---|
| WildChat / 4.8M | Consent + redaction; **toxicity**, residual PII, hashed IP **re-identification** if combined with headers. Demo use needs filtering and no raw dump in public slides. |
| LMSYS | Gated; similar. |
| ThoughtTrace | IRB, anonymized, Prolific; safer for a **demo**, but **wrong phenomenon**. |
| ShareGPT | Weakest provenance. |
| Any in-the-wild LLM log | Sexual/violent content; do not put unfiltered logs in a submission artifact. |

---

## 12–13. Best candidate and runner-up

**Best (only plausible public lead): WildChat family, restricted to the long tail.**  
Real one-thread chats; documented **A→B** topic switches; length tail might contain returns. **Density of heterogeneous return is unknown.** Gate: **B-thin**, not A.

**Runner-up: ThoughtTrace.**  
Best **length** and **clean consent** among recent public sets; **protocol and examples show single-task chats**. Heterogeneity is **task1 vs task2 as separate conversations**. **C** for in-session `A→B→C→A`.

**Do not** pick TopiOCQA or NTM as “the” substrate to look like the demo.

---

## 14. Why MultiWOZ is rejected here

Already measured (`docs/MULTIWOZ_TWO_STAGE_REPORT.md`): related tourist domains, mostly sequential `A→B`, almost no deep heterogeneous return. DST is not CF memory. **Wrong ontology and wrong interleaving shape.**

---

## 15. Why LongMemEval is rejected here

Already measured (`docs/LONGMEMEVAL_SUBSTRATE_REVIEW.md`): **oracle** = simulated life sessions; **S** = **glued** ShareGPT/UltraChat. Evaluation unit is **post-hoc memory QA**, not in-stream workstream return. **Wrong session integrity and wrong eval unit.**

---

## 16. Does the best candidate satisfy the ContextFlow substrate requirement?

**Not yet.**

Required: one ordinary session with **unrelated** unfinished intentions and a **later return** (`navy` / `401` / `the paper`) after another domain.

**WildChat** can contain **A→B** (published). That is **necessary but not sufficient**. Without a hand-read long-tail sample we cannot claim **A→B→C→A**.

**ThoughtTrace** is **explicitly** “complete **an** everyday task” per conversation.

**Public data collection** (arena, 10-minute tasks, WOZ, shared ChatGPT links) **selects against** the fickle multi-intention agent session. That behavior may exist mainly in **private product logs**.

---

## 17. Proposed next experiment (not implemented)

1. **Do not** run ContextFlow, Gemini, or 8B answer sweeps.  
2. **If** continuing public data: **approve a tiny WildChat inspect** — stream or download **only** a filter such as English, `turn ≥ 10`, non-toxic, **≤200 conversations** (or first 200 matching), then **hand-read**. Report the same structural table (3+ topics, 4+ topics, return-after-unrelated, deixis). **Stop** if the long tail is still single-task coding/roleplay.  
3. **Do not** expand if the filter is empty of returns.  
4. **Parallel product path:** one **consented** internal/user session (Option C memory store). That is still the only guaranteed match to the demo story.  
5. **Do not** use NTM/synthetic interleaving as “we found a dataset.”

---

## Structural inspection (this step)

| Dataset | Sessions inspected | Median / P90 turns | 3+ / 4+ topics | Genuine / heterogeneous returns | Deixis/correction | Max return distance |
|---|---|---|---|---|---|---|
| ThoughtTrace **examples** | ~20 (official sample) | ~single-task, order 8 (paper median) | **0 / 0** in-session unrelated | **0 / 0** | Corrections as **task refine**, not cross-domain | n/a |
| WildChat | **0 downloaded**; paper + published 2-turn switch | median ~2; P90 unknown without download; 3.7% >10 | unknown in-session | **1 published A→B**; returns **unknown** | unmeasured | unknown |
| MultiWOZ shard | 512 (prior) | short WOZ | related 2–3 | handful | see prior report | ≤6 DST (weak) |
| LME | prior | n/a as one user | fake in S | no | — | — |

**No 10–20 real target turns listed:** listing them would require either manufacturing or pretending WildChat is inspected. The published WildChat switch:

- **session:** paper appendix “Topic-switching” example (no public id in the paper table)
- **turn:** 2nd user message
- **preceding:** Chinese compliment question
- **target:** math circle equation
- **why:** user **changed domain**
- **prior intention:** none resumed
- **confidence:** high as **new intention**
- **class:** `new intention` — **not** a return

---

## Architecture reminder

ContextFlow remains a **working-set / resolution layer** over whatever history/memory exists. The **dataset problem** is: public logs rarely **are** that messy multi-intention history **inside one session**. Finding a store (Option C) does not create the phenomenon if the transcripts are still single-task.

---

## Stop

No implementation. No large download. Next action requires explicit approval: **tiny WildChat long-tail inspect** vs **stop public search and use consented logs**.
