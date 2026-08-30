# Human conversation substrates for ContextFlow (audit only)

**Date:** 2026-08-28  
**Constraint:** no download, no Vertex, no `app/` edits, no new synthetic corpus.  
**Question:** Can we evaluate ContextFlow on **existing human conversations as the memory substrate**, without requiring CF-native `task_id` / `referent_id` / ACT-CLARIFY gold on the dataset?

**Verdict:** Yes for a **small MultiWOZ-2.2 MUL** probe. No dataset is a drop-in CF benchmark. MultiDoGO is the wrong “multi-domain” (corpus-level, not in-dialogue). MUDiC is real but a **group scheduling** setting. SGD is partly simulated. Do **not** scale to 50+ until a 10–15 dialogue dry inspect confirms in-dialogue returns and underspecification.

---

## Shared mapping (all candidates)

We do **not** need the dataset to contain ContextFlow labels.

| Dataset signal | Possible CF analogue (reconstructed, not invented as truth) |
|---|---|
| Dialogue / session | One memory substrate |
| Domain / service / intent schema | Candidate **workstream** (task) |
| Active DST domains or slots mentioned | Open **loops** (referents) |
| User turn after ≥N turns of history | **Target** |
| DST domain that **changes** this turn | Auxiliary **task-resolution** signal |
| Slot value updated / requested entity | Auxiliary **referent** signal |
| No unique domain/entity from history | **CLARIFY** remains legal |

Official DST/intent labels are **auxiliary**, not CF gold. Wizard replies after the target must be **held out** (they leak the system’s bind).

---

## 1. MultiWOZ 2.2 (preferred) / 2.4

| | |
|---|---|
| **Provenance** | Cambridge WOZ, MTurk user + wizard; 2.2 Google annotation cleanup; 2.4 DST fixes on val/test of 2.1 |
| **License** | **MIT** (`budzianowski/multiwoz`; 2.4 `smartyfh/MultiWOZ2.4`) |
| **Human vs synthetic** | **Human–human** WOZ following **sampled tourist goals**. Not organic chat logs; still genuine people, not LLM roleplay. |
| **Scale** | ~10.4k dialogues; ~3.4k single-domain, **~7.0k multi-domain (2–5 domains)**; val/test 1k each (successful only) |
| **Interleave vs concatenate** | **In one dialogue.** Example: find hotel → attractions → taxi between them. Sequential **related** tasks, not ShareGPT glue, not coding↔fashion. Goal changes were **encouraged**. |
| **Annotations** | Per-turn dialogue acts; belief/DST (hotel/restaurant/train/attraction/taxi/hospital/police); goals; DBs |
| **Reconstruct memory without inventing CF labels?** | **Yes as a working representation:** one card per **active domain**; loops = open slot-bundles / booked entities. Do not claim those IDs are human gold. |
| **Target turns** | User turns in **MUL** dialogs where (a) metadata `active_domains` changes vs previous user turn, (b) user act is `request`/`inform` after another domain was last, (c) underspecified NP (`that one`, `the cheap one`, `change the time`) with **two** plausible entities in history |
| **Eval without new humans** | Match predicted domain to **DST active domain**; match slot-value updates; recency vs DST when they **disagree** |
| **Still needs humans** | ACT vs **CLARIFY**; which entity when two hotels; whether “book it” is hotel or restaurant |
| **Task / referent / return / CLARIFY** | Task ≈ domain: **supported**. Referent ≈ entity/slots: **partially** (DST is slot-state, not loop cards). Return-to-previous-domain: **supported** in MUL. CLARIFY: **only if we allow it** when DST is noisy or the user is vague — DST never says CLARIFY. |

**Limit:** Cambridge tourist ontology only. WOZ is more structured than production agent chat. Still the **least wrong** public substrate for “history → working context” with **in-dialogue** domain returns.

---

## 2. MultiDoGO (AWS)

| | |
|---|---|
| **Provenance** | Peskov et al., EMNLP 2019; crowd customer + **trained** agent; GitHub `awslabs/multi-domain-goal-oriented-dialogues-dataset` |
| **License** | **CDLA-Permissive 1.0** (use/publish allowed with notice) |
| **Human vs synthetic** | **Human–human** WOZ; collection **biased** toward intent/slot change, multi-intent (“No wait, chicken sandwich”) |
| **Scale** | Paper: **>81k–86k** raw dialogues; **~54.8k** turn-annotated; six domains |
| **Interleave vs concatenate** | **Corpus is multi-domain; conversations are stored *per domain*.** README: unannotated TSVs **split by** airline / fastfood / finance / insurance / media / software. This is **not** one chat spanning airline then insurance. |
| **Annotations** | Customer **intent** + **slots**; agent **dialogue acts** (shared across domains); turn vs sentence splits |
| **Reconstruct memory?** | Within **one** domain: intents/slots as loops. **Cannot** test cross-domain return from the released layout without stitching files (that would **invent** a session). |
| **Targets** | Same-domain corrections (`No wait…`); multi-intent turns (`<div>` in paper splits) |
| **Without humans** | Intent/slot of the customer turn vs CF card (weak: that’s NLU, not routing among open memories) |
| **Humans** | Whether vague “do this” continues the last order vs a new intent |
| **Task / referent / return / CLARIFY** | Same-domain referent/correction: **possible**. Cross-domain return: **no**. CLARIFY: possible on multi-intent/vague turns. |

**Limit:** Name is misleading for our hypothesis. Strong for **correction** inside one vertical, not heterogeneous memory.

---

## 3. MUDiC (Wagner et al., LREC 2026)

| | |
|---|---|
| **Provenance** | Two humans + Rasa chatbot on Telegram; appointment negotiation; Zenodo 10.5281/zenodo.19037937 |
| **License** | **CC BY 4.0** (Zenodo `cc-by-4.0`) |
| **Human vs synthetic** | **Human–agent** (and human–human in-group); consent + anonymisation; English + a little German |
| **Scale** | **~37–38** dialogues; **1,689** utterances (919 user, 690 system, 80 admin); ~12 user turns / dialogue (paper Table 1) |
| **Interleave vs concatenate** | **One task** (meet: date/time/location). **Off-topic / out-of-scope / gif / bot_challenge** intents are first-class. Not multi-industry. **Two users** share one bot — extra speaker identity problem. |
| **Annotations** | `intent_name`, `action_name`, slots in `data`, `party`, timestamps, policy id |
| **Reconstruct memory?** | Group vs per-user calendars as cards; off-topic as a **non-task** stream. Mapping is plausible but **not** CF’s single-user agent. |
| **Targets** | Turns tagged `off_topic` then return; `nlu_fallback`; `move` (reschedule); underspecified “that time” |
| **Without humans** | Intent tag vs whether CF stays on scheduling vs treats as new |
| **Humans** | Who is referred to; whether off-topic should CLARIFY vs ignore |
| **Task / referent / return / CLARIFY** | Return-from-off-topic: **interesting**. Task resolution among **heterogeneous workstreams**: **weak**. Two-user deixis can confound the experiment. |

**Limit:** Real interruptions, tiny N, wrong social setting (group + bot policies). Keep as a **second** substrate later, not the first.

---

## 4. Schema-Guided Dialogue (SGD / DSTC8)

| | |
|---|---|
| **Provenance** | Google; simulator + **crowd paraphrase**; 20 domains / many APIs |
| **License** | **CC BY-SA 4.0** (share-alike on derivatives) |
| **Human vs synthetic** | **Hybrid.** Flows simulated; utterances rewritten by people. Closer to SGD than to organic logs. |
| **Scale** | **~18–22k** dialogues |
| **Interleave vs concatenate** | **In-dialogue multi-service** (calendar + events, travel + weather, overlapping APIs) — **not** concatenated strangers. |
| **Annotations** | Schema, intents, slots, state, service frames |
| **Reconstruct memory?** | One card per **service/API**; good analogue of overlapping loops (two “events” APIs). |
| **Targets** | Service-frame switches; slot transfers across services |
| **Without humans** | Active service / intent vs CF task |
| **Humans** | CLARIFY when two APIs overlap |
| **Task / referent / return / CLARIFY** | Task/service: **supported**. Human-ness: **weaker than MultiWOZ**. CC-BY-SA may constrain how we publish enhanced logs. |

**Limit:** Survives “not authored by us” only loosely (simulator skeleton). Prefer MultiWOZ first.

---

## 5. STAR (Mosig et al., 2020) — runner-up

| | |
|---|---|
| **Provenance** | RasaHQ/STAR; WOZ MTurk; **MIT** |
| **Human vs synthetic** | **Human–human**; 5,820 dialogs, 13 domains, 24 tasks, schemas + KB queries |
| **Interleave** | Built for **task/domain transfer**; typical item is **one schema**. Multi-task-in-one-chat is **not** the headline property (unlike MultiWOZ MUL). |
| **Use** | Same-domain schema as cards; corrections if present in events. **Secondary** to MultiWOZ for returns. |

---

## Explicit rejects (for this direction)

| Dataset | Why not first |
|---|---|
| **LongMemEval-S** | Compiled ShareGPT haystack ≠ one user (already audited) |
| **LMSYS / ShareGPT dumps** | License/PII; no session-level workstream structure |
| **Ubuntu IRC** | Tech-only; noisy; weak domain tags |
| **Stitching MultiDoGO domains** | Would **author** a fake interleaved session |

---

## Smallest credible experiment (one dataset)

**Dataset:** MultiWOZ **2.2** (or 2.4 test/val only), **MUL** dialogues only.

**Size (do not exceed until dry inspect succeeds):**

- **8–12** dialogues from the **test** list  
- **20–30** target **user** turns total  
- History = all turns **before** the target (include wizard up to t−1; **exclude** wizard at t)

**Procedure:**

1. Replay the dialogue incrementally.  
2. **Memory representation (not gold):** open domains in DST so far → candidate tasks; mentioned venues/trains → candidate referents. If a domain has no entity yet, task-level referent.  
3. At the target user utterance, run (later, not now): recency (last active domain), Jaccard/lexical, full-history prompt, LLM-only proposal, ContextFlow.  
4. **Primary scores without new labels:** (i) predicted task vs **DST active domain(s)** this turn; (ii) if exactly one domain in DST, that is a weak task signal; (iii) **disagreement cases** (recency ≠ DST) are the scientific ones.  
5. **CLARIFY:** if DST has **two** active domains **or** the utterance has no unique slot/entity, the **legitimate** CF outcome is CLARIFY. Do **not** score CLARIFY as error against DST. Flag for **optional** 2-person human pass (same 18-probe policy: unique bind vs collision).  
6. **Do not** use wizard language after the target.  
7. **Do not** call this MultiWOZ DST accuracy. Call it: *does routing on unrehearsed WOZ history produce a working context that tracks domain/entity, and does it refuse when the user is underspecified?*

**What this can show:** the mechanism on **conversations we did not write**, with **in-dialogue** hotel↔restaurant↔taxi returns.

**What it cannot show:** production coding-agent traffic; cross-life domains; that CF “wins MultiWOZ.”

**Go / no-go after this:** if targets are almost all “now book a restaurant” with explicit domain words, the substrate is too easy → **stop**, do not scale. If we see returns, deixis, and DST/recency conflicts, **then** consider a larger MUL slice or a MUDiC off-topic add-on.

---

## Recommendation

Start with **MultiWOZ 2.2 MUL, 8–12 dialogues, 20–30 turns**. Not MultiDoGO (wrong multi-domain). Not MUDiC first (group + single task). Not SGD first (simulator). Not 50/100/1000.
