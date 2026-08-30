# WildChat long-tail inspection

**Date:** 2026-08-29  
**No ContextFlow. No Gemini/Vertex. No gold labels. No production changes. No commit/push.**

**Question:** In naturally occurring **one-thread** public ChatGPT logs, do users do `A → unrelated B → return to A` often enough to use WildChat as an external substrate?

**Critical count:** conversations with **heterogeneous return** (`A → unrelated B → return to A`).  
Do **not** count `A → B` only, `A → B → C` continuation, same-user **other** threads, or corpus-level topic mix.

---

## Sampling / filter procedure

| Item | Choice |
|---|---|
| Dataset | `allenai/WildChat` (non-toxic split, ODC-BY) |
| Access | HuggingFace **streaming** `split=train` |
| Order | **Stream order.** First matches kept. **Not** searched for returns or CF-friendly chats. |
| Length | `turn >= 10` **and** ≥10 user utterances |
| Language | `language` English (so we can inspect) |
| Safety | Dataset already dropped OpenAI/Detoxify-toxic chats. Skip if `toxic`. Drop if many empty user turns. |
| PII | Keep `redacted=True` (already anonymized); do not paste addresses/names in this report |
| Stop | **80** conversations (inside 50–100) after scanning **3956** rows |
| Local copy | `data/wildchat/longtail80.json` (gitignored). Preview of user lines only. |

**Not used:** WildChat-4.8M (larger download). Same phenomenon question; 1M-class non-toxic split is enough for a tiny long-tail look.

---

## Number inspected and length

| | |
|---|---|
| Inspected | **80** |
| Rows scanned to collect them | 3956 |
| User turns / session | median **13**, mean **14.4**, P90 **19**, max **55** |
| Redacted (PII tool fired) | **1** |

Long-tail chats exist. Length is **not** the same as multi-intention.

---

## Phenomenon counts (hand + conservative)

Heuristic keyword buckets over-count “ABA” (e.g. `code` ↔ `other` inside one Spring/Firefox task). **Counts below are after reading user turns**, not the bucket script.

| Phenomenon | n / 80 | Notes |
|---|---|---|
| Essentially **one** intention/task | **~55–65** | Homework dumps, SEO copy, ZFS, one coding bug, one RP, Turnitin paraphrase ×55 |
| Switch to **another** intention | **~12–18** | Includes same-domain “next question” on a quiz |
| Switch to a **genuinely unrelated** intention | **~6–10** | Trivia shotgun, recipe→business→jailbreak, language→homework→skincare, meta-chat→essay |
| **Return** to a previous intention | **0–1** | The only near-miss is **same-task** (“answer my first Chinese sentence again”), not an unrelated detour |
| Unresolved prior intention **later resumed** | **0** | Users switch and **do not come back** |
| Correction / retraction | **several** | “I meant what type of outfit”; “Ah I should have asked about name munging”; within **one** topic |
| Deixis (`that`, `the other one`, `back to…`) | **common, same-task** | “the previous question”, “list 1”, “forget all that” (abandons, does not resume) |
| Ambiguous / CLARIFY-shaped | **rare as cross-intention** | Underspecification is usually **inside** one coding or RP thread |
| **`A → unrelated B → return to A`** | **0** | **Critical statistic** |

**3+ distinct intentions in one thread:** **~6** (shotgun Q&A or jailbreak+random asks).  
**4+:** **~2** (notably the Attic-numerals / logic-gate / ocean / clothing / translation / extinct-mammal thread).

**Heterogeneous return:** **0**.

---

## Strongest *switches* (not returns)

These are the closest to “fickle.” They **fail** the return criterion. Listed so we do not inflate the count.

### 48 — `8ee7f70e3b1709e6` (prefix) — 10 user turns

- **Description:** Rapid-fire unrelated questions in **one** thread.  
- **Intentions:** Attic numerals → logic gates → ocean waves → clothing/outfit → Portuguese translate → Sparassodont.  
- **Return turn:** none.  
- **Why it does not qualify:** `A → B → C → D`. No resume of numerals or gates.  
- **Confidence (as switch):** high. **As heterogeneous return:** n/a.

### 53 — `4972785ec61754fd` — 13 user turns

- **Description:** Location joke → Jollibee/pork recipes → business plan / 50k peso loan → DAN jailbreak → weapons/manipulation → forex/gold.  
- **Return:** none (never back to the recipe).  
- **Class:** unrelated switches + **new intention**. Unsafe asks (weapons) — **unsuitable as a demo** even if returns existed.

### 42 — `8866fa8f839d60cb` — 12 user turns

- **U06:** “ok anyways forget all that”  
- **Then:** architecture essay (Osaka Expo).  
- **Class:** **interruption / abandon A, start B.** Not a return.

### 62 — `9de0ae96f067269a` — 10 user turns

- Chinese usage → Filipino homework → student-council advice → collagen product.  
- **No return.**

### 08 — `50614687425e3c93` — 13 user turns

- Chinese↔English practice. U02 asks to **respond to the first message again**.  
- **Class:** **same intention** (language practice), not unrelated B then back to A.

---

## Examples rejected and why

| Sample # | Why rejected |
|---|---|
| 00, 06, 16, 49 | Chemistry / entropy **homework dump** — one course, many items |
| 15 | **55** Turnitin paraphrases of **one** medical-imaging paper |
| 01, 25–32, 41 | Single **coding/sysadmin** task (Firefox extension, ZFS, Spring, numpy) |
| 02–03 | Lazada **pull-up bar SEO** — one product |
| 20, 43–44 | **One** theme-park / sitcom **worldbuilding** thread (“hotel” is a park analogy) |
| 24, 55, 61 | Sexual / fetish **roleplay** — one story; **unsuitable** for a public demo even though long |
| 31 U11 | “tips for interviews” after Spring Boot — **same career**, not clothing/travel |
| 45–47 | Jailbreak then politics/business — switches, **no return**; toxic-adjacent |

---

## Correction / deixis (not gold)

- **Correction:** “I meant what type of outfit” (48); name-munging apology in a later code thread.  
- **Deixis:** “that hooks into a gradio app”; “list 1”; “the previous question”. Almost always **the current task**.  
- **“Forget all that”** (42) **drops** the prior thread.

None of these are `back to the JWT` after travel.

---

## Privacy / licensing

- **License:** ODC-BY (WildChat card). Cite Zhao et al., ICLR 2024.  
- **Consent:** opt-in free ChatGPT.  
- **PII:** Presidio + later journalism-PII removals. Still: do not republish full logs. This report uses **hashes prefixes** and paraphrases.  
- **Safety:** “Non-toxic” split **still contains** sexual roleplay and jailbreak. A product demo must filter those separately.  
- **1** conversation was `redacted=True`.

---

## Is this enough substrate for the next experiment?

**No.**

The next experiment you described (full history vs recency vs ContextFlow on **10–20 real heterogeneous-return sessions**) **cannot** start from this sample: **heterogeneous-return sessions = 0**.

WildChat **does** show:

- long single-task sessions (the tail is real),
- **fickle sequential** new asks (`A → B → C` with no resume),
- same-task deixis and correction.

It does **not** show, in the first 80 English 10+ turn threads in stream order, the product behavior:

coding → clothing → travel → **back to coding**.

---

## Decision gate

**0–2 genuinely useful heterogeneous-return sessions (here: 0).**

→ **Public-data route unsuitable for this phenomenon.**  
→ **STOP dataset search.**  
→ Use a **consented real conversation / product log** as the realistic substrate.

Do not manufacture more. Do not mine another 10k WildChat rows hoping the next 80 look different without a new, pre-registered filter — that would be fishing. The long tail here is **long single tasks** and **shotgun Q&A**, not working-set returns.

**Do not run ContextFlow on these 80** as if they were the target substrate.

---

## Promising-session table (required format)

**None** meet `intention A / intervening B / return turn` for a **heterogeneous return**.

Optional (switch only, **not** for the replay experiment):

| session_id (prefix) | turn range | description | A | B | return turn | why it would *not* qualify | confidence |
|---|---|---|---|---|---|---|---|
| `8ee7f70e3b1709e6` | U00–U09 | Trivia shotgun | Attic numerals | clothing, paleontology, … | **none** | no resume of A | high |
| `4972785ec61754fd` | U00–U12 | Recipe then crime/finance | food | jailbreak/forex | **none** | no resume; unsafe | high |
| `8866fa8f839d60cb` | U00–U11 | Meta then essay | ChatGPT identity | architecture essay | **none** | “forget all that” abandons A | high |
