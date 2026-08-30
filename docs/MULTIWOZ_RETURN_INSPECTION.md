# MultiWOZ return/interleaving inspection (design only)

**Date:** 2026-08-28  
**Status:** inspection + experiment design. **No ContextFlow run. No Ollama. No Vertex.**  
**Freeze:** production routing/gate/scorer/compiler untouched. No commit/push. No `feat/submission-polish` edits.  
**Data:** MultiWOZ 2.2 test shard only — `data/multiwoz/dialogues_001.json` (512 dialogues, MIT). Gitignored. No full corpus download.

**Research question:** Can ContextFlow take an existing human conversation as raw history, build its **own** working memory (not DST labels), and reconstruct the right working context when the user returns after other work?

**Product claim this is meant to support later:** ContextFlow does not replace the agent’s memory. It manages the **working set** of that memory after intention switches.

---

## Candidate selection procedure (locked before ranking)

This procedure was fixed from the research brief and from reading the shard. It is **not** “keep the cases ContextFlow would win.”

1. **Substrate.** Use the already-audited MultiWOZ 2.2 test file only. Do not invent dialogues. Do not stitch sessions.
2. **Scope.** Restrict to multi-service (`MUL*` / `PMUL*`) dialogues. Multi-domain **labels** are not enough.
3. **Search aid only.** A naive DST active-intent A→B→A scan (excluding thanks/goodbye and “I also need a train/restaurant/…”) is a **finder**, not gold. On this shard it flagged **193/409** multi-service dialogues; most of those are leftover DST on closings or sequential “next domain” turns.
4. **Inclusion (utterance-level, after dump).** Keep a target user turn if at least one holds:
   - **Interrupt return:** a newer workstream has started, and the user **pauses it** to resume earlier entity/slot work.
   - **Recover:** the target is not interpretable without earlier named entities or booking constraints (deixis, “same day as the hotel,” “you mentioned earlier”).
   - **Correction:** the wizard mixed two workstreams; the user re-asserts the earlier one.
5. **Exclusion.** Sequential domain starts (“I’m also looking for a hotel”), taxi as a **new** booking that merely **names** prior venues, and closings. `hotel → taxi → attraction` is not automatically a return.
6. **DST/intent/slot frames are never ContextFlow memory.** They may be cited as **auxiliary** evidence after the utterance judgment.
7. **Cherry-pick rule.** Rank by how clearly the target needs **non-recent** working context, not by expected CF vs recency win. If the first 5–10 are lexically easy, say so.

Hand-read this step: PMUL0079, MUL0810, PMUL4186, MUL2053, MUL2423, PMUL2882, MUL0789, MUL0088, PMUL2746, PMUL4842, MUL0089, PMUL0204 (plus scan dumps of other DST A-B-A IDs). Scripts: `eval/multiwoz_inspect/scan_returns.py`, `eval/multiwoz_inspect/dump_ids.py`.

---

## Verdict: does the audited dataset contain useful natural returns?

**Yes, sparsely.** This shard is **not** a dense A→B→C→A corpus. Typical MUL is **concatenated tourist goals**: finish or pause domain 1, then “I also need a restaurant/train.” Those are **sequential domain transitions**. They do **not** test “the user moved on, then came back.”

What **does** exist, in small numbers, is:

- mid-dialogue **interrupt** of a new domain to finish earlier lodging/attraction facts;
- explicit **“you mentioned earlier”** recover;
- wizard **wrong-domain** answers that the user corrects;
- **constraint copy** (“same day as the hotel,” “the same as the hotel”) that needs prior slots without returning to that domain as the **current** task.

That is enough for a **5–10 turn local experiment**. It is **not** enough to claim MultiWOZ “has interleaving” in the ShareGPT/agent-chat sense. WOZ users follow sampled goals; they are human, not organic production logs.

**Do not manufacture extra returns.** If we later need more, inspect further shards with the same procedure — do not write synthetic A-B-C-A.

**Difficulty warning:** several strongest cases are **lexically easy** (entity name in the target turn). Recency and Jaccard may already succeed. The experiment is still worth running **because** the substrate is not ours — but we must not treat a CF win on named-entity recover as the killer demo.

---

## Rejected (sequential / not a return)

| Dialogue | Why rejected as a return probe |
|---|---|
| **PMUL4842** | Restaurant booked, then “I’d like to find a guesthouse…”. New workstream. |
| **MUL0089 t8** | “I'm also looking for a hotel” after restaurant booking. Sequential. **t12** (“close to our restaurant”) is **constraint copy**, optional secondary probe, not A→B→A. |
| **PMUL0204 t10** | “I do need a place to stay in the same area” after restaurant. New hotel search with copied **area**, not return to restaurant work. |
| **Typical taxi MUL** | “Taxi from the restaurant to the hotel” **consumes** earlier names as a **new** taxi task. User brief: not automatically a return. |
| **DST A-B-A on goodbye** | Active-intent often stays on the first domain while the user is closing. Discard. |
| **PMUL4247-style** | DST said hotel while the user asked **train times**. DST is leaky; do not use as CF memory or as inclusion gold. |

---

## Strongest candidates (8)

Turn IDs are MultiWOZ `turn_id`. **Target = that USER turn.** Replay history = all USER+SYSTEM turns with `turn_id` **strictly less than** the target. Hold out the target wizard reply and everything after.

### 1. PMUL0079 — user t8 (strongest interrupt)

- **History:** 4-star hotel north → cheap guesthouse phone/price (wizard never clearly named it) → user starts **expensive restaurant in the same area as the hotel**.
- **Target:** *“Before we do that, what is the name of the guesthouse? And also, do they have free parking?”*
- **Earlier workstream:** hotel / Worth House (unnamed in user text until wizard t9).
- **Intervening:** restaurant food-type question (t7).
- **Genuine return?** **Yes.** Explicit *before we do that* interrupt of restaurant to resume hotel.
- **Needs previous context?** **Yes.** Name + parking were not in the user’s last restaurant turns; parking was never asked.
- **Form:** **explicit interrupt** + missing slot (parking); name recover.
- **DST auxiliary:** hotel `find_hotel` + parking request while restaurant slots persist. Useful as “not restaurant.” Not CF memory.
- **CF must reconstruct:** hotel/guesthouse card (cheap, north, phone 01223316074, parking unknown) as **active working set**; restaurant as paused, not discarded.
- **Too easy?** Medium. No hotel name in the target string; recency is the restaurant question.

### 2. MUL0810 — user t12

- **History:** east attractions (Camboats, Cambridge Museum of Technology) → unusual then Italian restaurant → Pizza Hut Fen Ditton postcode/phone → user says that’s all.
- **Target:** *“I forgot to ask; what is the postcode for the Cambridge Museum of Technology that you mentioned earlier?”*
- **Earlier:** attraction. **Intervening:** full restaurant booking-ish info.
- **Genuine return?** **Yes.** Explicit recover after a closing-ish turn.
- **Needs previous context?** **Yes** for a compact working set; the name is in the target so **full history / Jaccard / LLM-select all likely work**.
- **Form:** **explicit** named recover.
- **DST:** attraction `find_attraction` + `attraction-postcode`; restaurant `NONE`. Auxiliary domain switch.
- **CF reconstruct:** attraction mention (museum) vs restaurant (Pizza Hut). Killer product story is **not** “remember a museum string in the query.”
- **Too easy?** **Yes** for answer quality if the name is in the prompt. Still valid as **routing**: did CF attach to attraction not restaurant?

### 3. PMUL4186 — user t8

- **History:** Nando’s two addresses → user also asks **Cambridge Belfry** hotel → user asks **Belfry postcode + free parking**.
- **Wizard t7 (in history):** *“The postcode for the nandos is cb17dy”* — **wrong workstream**.
- **Target:** *“You didn’t answer my question. I need the postcode for The Cambridge Belfry and I need to know if they have free parking or not.”*
- **Genuine return?** **Yes** (correction / re-assert hotel after restaurant leak). Not A→B→C→A spanning many domains, but **return to the intended hotel ask**.
- **Needs previous context?** **Yes:** Belfry already introduced; parking unanswered; Nando’s postcode is a distractor.
- **Form:** **correction** + **explicit** hotel name.
- **DST:** mixed restaurant requested_slots + hotel parking/postcode. Shows why DST ≠ memory.
- **CF reconstruct:** hotel Belfry working set; do not treat Nando’s postcode as the answer context.
- **Too easy?** Name is in the target. The **failure mode** to preserve: models that answer Nando’s again.

### 4. MUL2423 — user t12

- **History:** Indian restaurant Panahar (centre) → theatres → taxi leave by 1:00.
- **Target:** *“I need the taxi to pick me up at the theatre. But I suppose we should figure out exactly which theatre that is. You mentioned one in the centre?”*
- **Earlier:** attraction/theatre (wizard had asked centre, **had not listed names yet** — “you mentioned” is slightly mismatched).
- **Intervening:** taxi time.
- **Genuine return?** **Yes** — taxi started; user **goes back** to pin the attraction before taxi can be booked.
- **Needs previous context?** **Yes** (centre constraint, restaurant vs theatre collision). Theatre names appear only **after** the target in the wizard reply — **must not leak t13+**.
- **Form:** **partial / deictic** (“the theatre”, “one in the centre”).
- **DST:** noisy (restaurant `find_restaurant` still on this turn). **Do not treat DST as gold referent.**
- **CF reconstruct:** attraction workstream + taxi leaveat; restaurant Panahar as **other** mention. CLARIFY is **legal** if CF cannot uniquely bind a theatre (wizard never named one yet).
- **Too easy?** **No** — underspecified; CLARIFY vs listing centre theatres is the interesting behavior.

### 5. MUL2053 — user t14

- **History:** 2-star hotel → book Ashley → user needs **east** → rebook Express Holiday Inn **Tuesday, 3 people, 4 nights** → train Peterborough→Cambridge arrive 11:45.
- **Wizard t13:** *“Which day would you be traveling?”*
- **Target:** *“On the same day as the hotel stay.”*
- **Genuine return?** **Partial.** This is **constraint copy** into **train**, not returning to hotel as the current task. Still the phenomenon: later turn **requires** earlier workstream slots.
- **Needs previous context?** **Yes** (`hotel-bookday` = Tuesday). Recency window that drops hotel booking **fails**.
- **Form:** **deictic / partial**.
- **DST:** `copy`/hotel slots + `book_train` day. Auxiliary for “day should be Tuesday,” not CF memory.
- **CF reconstruct:** train task with **day bound from hotel booking**, not a hotel ACT.
- **Too easy?** Medium. Jaccard may miss “Tuesday” if the window is train-only.

### 6. PMUL2746 — user t10

- **History:** south moderate hotel, Aylesbray booked Fri / 3 / 5 nights, parking confirmed → user asks attractions.
- **Target:** *“The same as the hotel please”* (area, after wizard asked attraction type/area).
- **Genuine return?** **No as hotel-return.** **Yes as copy-from.** Same class as MUL2053.
- **Needs previous context?** **Yes** (south).
- **Form:** **deictic**.
- **DST:** attraction-area copied from hotel. Auxiliary.
- **CF reconstruct:** attraction find with **area = hotel area**; hotel card stays in memory but is not the answer task.
- **Too easy?** Easy if “south” is still in a medium window.

### 7. PMUL2882 — user t16 (and optional t18)

- **History:** A and B Guest House booked Monday / 1 / 4 nights, east, wifi → attractions same area → user confusion restaurant vs attraction → Cambridge Artworks museum.
- **Target t16:** *“I want to book a taxi so that I can travel from the guest house to the museum.”*
- **Genuine return?** **Borderline.** New taxi workstream **grounded in two prior names**. Not A→B→A to hotel Q&A. Include as **referent resolution across paused streams**, labeled as such — not as “returned to hotel.”
- **t18:** *“leave the museum by 23:15 to head back to the guesthouse”* — direction flip; still taxi.
- **Needs previous context?** **Yes** (A and B Guest House, Cambridge Artworks).
- **Form:** **explicit** category nouns, not names.
- **DST:** `copy_from` hotel-name on taxi. Auxiliary entity link.
- **CF reconstruct:** taxi departure/destination from hotel + attraction mentions.
- **Too easy?** Names not in t16; recency has “museum” and “guest house” as types.

### 8. MUL0088 — user t10 (interrupt) and t18 (taxi consume)

- **t10:** After user also asked Cow Pizza Kitchen, wizard pushes **Hamilton Lodge**. Target: *“Does it have internet?”*
  - **Return?** **Yes, weak interrupt:** restaurant name was introduced; user answers the **hotel** offer. “It” is **deictic** (lodge, not restaurant).
  - Needs context: last offered lodging vs restaurant name in the previous user turn.
- **t18:** *“taxi for the hotel by 13:45 to get to the restaurant”* — **new taxi**, exclude as primary return; optional copy-from control.
- **DST t10:** hotel internet request, restaurant NONE. Auxiliary.
- **Too easy?** t10 is a classic last-mention vs collision case (PoC-like).

### Optional 9. MUL0789 — user t24 (after t20)

- **t20:** *“No on the hotel. What is the train id…”* — **rejects** hotel, stays on train. Not a return.
- **t24:** *“No, if you're sure there are no 3-star moderately priced hotels with free parking then there's nothing else…”* — **returns to hotel constraints** after a train stretch. Wizard then offers Hamilton Lodge.
- **Genuine return?** **Yes**, delayed. Messy (user also sounds done). Use only if we want a harder, less clean case.
- **Do not** use t20 as a “return to hotel.”

**Not in the top 8:** MUL0089 t12 (copy area from restaurant into hotel) — sequential + copy, keep as optional if we need a ninth.

---

## What ContextFlow would have to reconstruct (mechanism, not DST dump)

From **utterances only**, incrementally:

- **Tasks / workstreams:** hotel search-or-book, restaurant, attraction, train, taxi — as CF’s own cards, not `services[]`.
- **Loops / mentions:** named venues (Panahar, Belfry, museum of technology), unnamed (“the guesthouse”), constraints (Tuesday, east, cheap, 3-star).
- **Active vs paused:** restaurant can be **active** in the dialogue manager’s last wizard question while the **user** returns to hotel (PMUL0079, PMUL4186).
- **At the target:** referent resolution → selected working context for the **answer model**. Gold for routing is **human inspection** of the cases above, not `active_intent`.

If CF only classifies domain like DST, the experiment has already failed the research question.

---

## Replay protocol (no answer leak)

1. Parse MultiWOZ turns into a linear USER/SYSTEM transcript. **Strip** `frames`, `slot_values`, `active_intent`, dialogue acts from anything CF or the answer model sees.
2. For target turn *T*: **memory input** = turns `0 … T-1` only. **Never** include user turn *T* in the **history** used to **build** memory **after** scoring?  
   **Correct split:**  
   - **Incremental replay:** feed turns in order through CF **up to and including user turn T** as the **query** (the thing to resolve), with memory state from **0 … T-1**.  
   - **Answer model:** CF-selected (or control) context **plus user turn T**. **No** wizard *T+1* or later.
3. Wizard **T+1** is **held-out gold for answer quality only** (what the WOZ agent said). It is **not** gold for referent IDs. It **leaks** DB facts (postcodes) — use it as a **reference reply**, not as a required string match.
4. Do not give CF the MultiWOZ database. Answer quality on phone/postcode may fail for **all** conditions if the fact was only in a dropped wizard turn — that is a **context-size** result, not a DST fail.
5. Same **answer model** for A–E: local **`llama3.1:8b`**. No Gemini.

---

## Proposed controls (small local)

Fixed answer model. Vary **only** the context string.

| | Context given to `llama3.1:8b` with user turn T |
|---|---|
| **A FULL HISTORY** | Entire transcript `0 … T-1`. |
| **B RECENCY** | Last *k* turns (propose *k* ∈ {4, 8} user+system pairs; freeze *k* before scoring). |
| **C JACCARD** | Rank earlier turns by lexical overlap with T; take top *m* (freeze *m*). |
| **D LLM-ONLY** | Same 8b (or a separate select prompt on 8b) picks excerpts from `0 … T-1`; then answer. |
| **E CONTEXTFLOW** | Incremental CF memory from `0 … T-1`; resolve T; **compiler working context** only. |

Do **not** retune TAU/DELTA/HYST for MultiWOZ. Frozen PoC constants.

---

## Proposed metrics (separate)

1. **Memory / routing (primary for the research question).** Did the selected working set correspond to the workstream in the inspection notes (hotel vs restaurant vs attraction vs train-day copy)? Binary + short error tag. **DST domain is auxiliary**, reported in a side column, **not** the official score unless it agrees with the utterance judgment (it often does not: MUL2423 t12).
2. **Answer quality.** Rubric vs held-out wizard **and** vs inspection: correct entity, correct copied slot (Tuesday, south), or **appropriate CLARIFY**. Do not require matching wizard wording. Do not score “wrong” if the original history does not uniquely bind (MUL2423 t12).
3. **Context size.** Tokens / turns supplied to the answer model.
4. **Failure mode.** `wrong_context` | `insufficient_context` | `legitimate_ambiguity_or_clarify` | `answer_model_error_given_good_context`.

**CLARIFY is not automatically wrong.**

Preserve **all** CF failures. Do not drop cases after seeing scores.

---

## Methodological risks

- **WOZ ≠ production chat.** Goals are sampled; switches are often polite concatenations.
- **Wizard text is in the substrate.** CF “memory” includes agent utterances (names, postcodes). That matches “agent history as memory,” not “user-only memory.”
- **Lexical overlap.** Named recover (MUL0810, PMUL4186) inflates Jaccard/LLM-select. State that in the writeup.
- **Taxi-as-glue.** Easy to over-count as returns.
- **DST leak** if any pipeline accidentally passes frames.
- **No Cambridge DB** in the answer model → postcode questions measure **whether context contained the fact**, not tourism QA skill.
- **CF ontology mismatch.** PoC tasks/loops may not map cleanly onto hotel/restaurant/train; the experiment tests whether the **mechanism** still selects a useful working set.
- **n = 8.** Directional evidence only. No claim of MultiWOZ SOTA.
- **Cherry-picking after the fact.** Mitigated by this document; do not add “CF-friendly” IDs after the first Ollama run without labeling them **post-hoc**.

---

## Should we proceed to the small local experiment?

**Yes — after you review this candidate list.** Recommended first run: **cases 1–6** (PMUL0079, MUL0810, PMUL4186, MUL2423, MUL2053, PMUL2746). Add 7–8 if you want copy-from / deixis. Skip expanding the shard until that run is classified.

**Stop here.** No engine, no Ollama, until you confirm or drop IDs.
