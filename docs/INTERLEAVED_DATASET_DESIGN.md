# Interleaved interaction dataset — design

**Status:** local research planning. Not an experiment result.  
**Freeze:** `feat/submission-polish` @ `4b1b4e9`  
**This document does not authorize production changes, Vertex, or dataset downloads.**

**Pilot corpus:** `eval/interleaved_corpus/` (5 unlabeled synthetic sessions).  
**Inspection tool:** `eval/interleaved_probe.py` (schema + stats only; does **not** call ContextFlow or any LLM).

---

## 1. Why same-project interleaving is insufficient

The PoC family (auth / frontend / deploy / sibling 401) tests **semantic interference inside one product**. That is necessary and still too narrow.

A real agent conversation is a **stream of heterogeneous intentions**. The user can:

- debug JWT,
- ask what to wear to a corporate event,
- book a hotel,
- return to OAuth with no recap,
- then ask “what about that dress?”

If every open memory is assumed to live in one project, routing collapses to “which bug in this repo?” That is **task classification among cousins**, not memory reconstruction under mixed life-and-work context.

The hypothesis to test is:

**USER INTENT → which prior object/loop is pointed at → which workstream owns that referent → what context to reconstruct → ACT or CLARIFY**

`active_task` and `referent_task` are allowed to differ (e.g. active AUTH, foreground DRESS.loop1).

---

## 2. Two kinds of interleaving

| Kind | What it stresses | Example mix |
|---|---|---|
| **A. Same-domain / same-project** | High lexical/semantic overlap among related workstreams | JWT 401, expired token, OAuth redirect, frontend double-render, Docker CI |
| **B. Cross-domain** | Abrupt, unrelated memories; similarity baselines should **fail** or **confabulate** | Coding → clothing → travel → shopping → writing |

Both are required. B is not decoration. If ContextFlow only wins on A, we have not tested the claim that matters for production agent traffic.

Sessions **must not** all contain every category. Realistic mixtures, for example:

- 2 technical + 2 personal
- 1 technical + 3 lifestyle
- 3 work + 1 shopping
- 2 unrelated personal threads
- 5+ heterogeneous threads (chaotic archetype)

Domain switches may have **no** transition phrase (“Anyway, back to…”). That is intentional.

---

## 3. What we are not evaluating

- Not “is this utterance about authentication?” as a standalone classifier.
- Not RAG over the web.
- Not whether Gemini is a better chat model.
- Not token savings as a primary claim.
- Not private/personal logs.

---

## 4. Session archetypes

| Id | Archetype | Role |
|---|---|---|
| 1 | **Focused** | Mostly one domain. Control. Recency and full-history should look strong. |
| 2 | **Multi-task** | Several related technical workstreams. Semantic distractors. |
| 3 | **Cross-domain** | Technical + lifestyle + planning. Abrupt switches. |
| 4 | **Chaotic** | Frequent unannounced switches. Many open memories. |
| 5 | **Long-return** | Resume a loop after many unrelated turns (including 20+). |
| 6 | **Ambiguous** | Genuine CLARIFY probes. |
| 7 | **Adversarial** | Shared keywords, sibling loops, wrong-LLM injection slots. |
| 8 | **Human-like** | Messier, less “benchmark-shaped”; typos, abandon, “wait”, “never mind”. |

A single session may mix archetypes (e.g. chaotic + long-return). The label is the **dominant** construction intent.

---

## 5. Thread structure

Each workstream (memory card) may have **multiple unresolved loops**.

```
AUTH:   loop1 = JWT 401 after refresh;  loop2 = expired access token
DRESS:  loop1 = navy dress for Friday event;  loop2 = shoes
TRAVEL: loop1 = hotel;  loop2 = flight timing
```

Gold (when later annotated) is **referent-first**: bind the object, then the owning task. Do not set `gold_task = AUTH` merely because AUTH is active.

---

## 6. Reference kinds (probes)

| Kind | Examples |
|---|---|
| Explicit | “the JWT issue”, “the navy dress” |
| Partial | “the 401”, “the shoes”, “the hotel” |
| Deictic | “fix that”, “change this”, “what about that one?” |
| Elliptical | “back to that”, “what did we decide?”, “continue where we left off” |
| Correction | “no, the other one”, “not that, the other dress”, “I meant the deployment one” |

Cross-domain deixis after AUTH → DRESS → AUTH is a **designed** stress: “fix that” must not default to the semantically nearest *technical* card.

Annotation policy for gold (when labeling starts) is the pilot policy in `docs/annotation_pilot/ANNOTATION_BLANKS.md`: unique bind vs foreground deixis vs collision vs correction; active ≠ automatic referent; last mention ≠ automatic resolution of lexical collision.

---

## 7. Adversarial inventory (must appear across the corpus, not every session)

1. Last-mentioned memory is correct.  
2. Last-mentioned memory is **not** the intended referent.  
3. Active task correct, foreground referent owned by another task.  
4. Same keyword in unrelated domains.  
5. Similar phrasing across unrelated domains.  
6. Same task, multiple loops.  
7. Two tasks, nearly identical loops.  
8. Slot for a **wrong high-confidence LLM proposal** (injected later; **not** gold).  
9. Explicit lexical evidence vs recency conflict.  
10. Deixis with one unique foreground candidate.  
11. Deixis with multiple plausible candidates.  
12. Correction reverses previous selection.  
13. Ambiguous reference → CLARIFY.  
14. Domain change with no announcement.  
15. Return to an old domain after many unrelated turns.  
16. Resume a loop after 20+ unrelated turns.  
17. Several domains concurrently open.  
18. Distractor with highly similar vocabulary.  
19. Distractor semantically unrelated.  
20. Task identifiable, **loop** not (CLARIFY or loop-level miss).

**Not every hard case is a success case.** The corpus should be able to **falsify** ContextFlow, recency, similarity, and LLM-only proposal.

---

## 8. Real vs synthetic vs annotated vs predictions

| Layer | What it is | What it is not |
|---|---|---|
| Public real interaction data | Licensed/public dialogues used as **structure** (topic shifts, length, messiness) | Drop-in gold for task/referent/ACT |
| Synthetic conversations | Author-written sessions in this repo (pilot) | Human behavior; not “users did this” |
| Human-annotated conversations | Independent labels on probe turns using the written policy | Model outputs |
| ContextFlow (or baseline) predictions | System under test | Gold |

**Do not pretend synthetic gold is human behavior.** The 5-session pilot is **unlabeled** on purpose: inspect dialogue quality first.

### Public datasets (survey only — nothing downloaded)

None of the following supply **our** gold (task + loop referent + ACT/CLARIFY under heterogeneous open memories).

| Dataset | Why people cite it | Why it is not drop-in gold |
|---|---|---|
| **MultiWOZ** | Multi-domain TOD (hotel/restaurant/train/…) | Booking domains in one itinerary, not coding+fashion+admin; DST slots ≠ workstream/loop routing; not coding-agent traffic |
| **LoCoMo** | Very long persona dialogues; QA / summarization | Memory **QA**, not “which open loop to bind”; largely LLM-generated then edited; no ACT/CLARIFY gate |
| **LongMemEval** | Long-horizon memory questions over session haystacks | Evidence-session retrieval / answer strings; not interleaved **referent** cards or fail-closed CLARIFY |
| **LMSYS / ShareGPT-style dumps** | Messy real-ish chat | License/PII/quality uneven; **no** workstream gold; do not ingest privately collected logs |
| **ATOD / similar TOD** | Agent/task-oriented labels (if used later) | Typically in-domain tasks, not cross-life interleaving + loop deixis |

**Legitimate later use of public data:** sample dialogues for **turn-taking and topic-shift statistics**, then **human-annotate a small subset** with our schema. Provenance and license must be recorded. No private Ericsson/user chats.

---

## 9. Annotation schema (for a later labeling pass)

Unit = **one probe turn**, not one session.

Required on each labeled probe:

| Field | Role |
|---|---|
| `session_id`, `turn_id` | Identity |
| `user_message` | Probe |
| `active_task_id` | Workstream clock **before** the probe (analysis + state) |
| `gold_task_id`, `gold_referent_id`, `gold_decision` | Human gold (`ACT` / `CLARIFY`; ids or `NONE`) |
| `reference_kind` | explicit / partial / deictic / elliptical / correction |
| `domain` | Domain of the **intended** referent if ACT; else `mixed` / `unknown` |
| `rationale`, `ambiguity_level` | Audit |

Analysis fields (not production state):

| Field | Role |
|---|---|
| `last_mentioned_task`, `last_mentioned_referent` | Discourse clocks |
| `turns_since_referent` | Distance to last mention of gold referent (if known) |
| `number_of_open_tasks`, `number_of_open_loops` | Interference load |

Candidates (open tasks/loops **before** the probe) must be listed so retrieval miss ≠ resolver miss.

**LLM proposals are never gold.** Wrong-proposal items are a **later experimental injection**.

Do not reverse-engineer gold from ContextFlow output.

---

## 10. Scale (staged)

| Stage | Size | Rule |
|---|---|---|
| **Pilot 0 (now)** | 5 sessions, unlabeled | Inspect realism only |
| **Pilot 1** | Same 5 + human gold on marked probes | After 10-example annotation protocol is GREEN |
| **v1 corpus** | 8–12 sessions, ~30–60 turns/session, 4–8 workstreams, 8–15 probes/session | Target ~100–150 eval turns **eventually** |
| **v2** | Expand only if v1 labeling is defensible | Still no production rewrite from scores alone |

Distribution **targets** (document actuals; do not force if it wrecks naturalness):

- ≥40% of **target** turns: reference or resumption  
- ≥25%: cross-domain switch in the recent history  
- ≥15%: genuine CLARIFY  

Pilot 0 does not claim these percentages.

---

## 11. Baselines (later; not run now)

| Id | System |
|---|---|
| A | Full conversation / history in the prompt |
| B | Last-active / recency |
| C | Lexical / Jaccard |
| D | Semantic similarity (hash or embeddings — declare which) |
| E | LLM-only proposal |
| F | ContextFlow |

Metrics (later):

- task accuracy, referent accuracy, **joint** accuracy  
- ACT accuracy, **wrong-ACT** rate, clarification rate, **correct-clarification** rate  
- recovery from wrong LLM proposal  
- vs open-memory count, domain diversity, turns since referent, context size  

### Primary scientific plots (not just “did F beat B?”)

1. Performance vs **number of concurrent memories**  
2. vs **number of domains**  
3. vs **turns since last mention** of the intended referent  
4. vs **semantic similarity of distractors**  
5. vs **active_task ≠ referent_task**

Question: **under what interference does memory routing break?**

---

## 12. Falsification

The idea is in trouble if, on a **human-labeled** cross-domain set:

- Joint resolution is indistinguishable from recency **and** from Jaccard on the cases that were supposed to separate them.  
- Wrong-ACT on designed CLARIFY items is high.  
- Cross-domain deixis is systematically resolved to the **nearest technical** card.  
- Annotators cannot agree on gold (protocol failure — stop expanding the corpus).  

Beating same-project PoC scenarios is **not** sufficient.

---

## 13. Privacy

- Pilot 0: **synthetic only**.  
- No private or employee conversation logs.  
- If public data is used later: license, URL, date, and transformation steps in this document.

---

## 14. What this pilot is for

A credible bridge from the **controlled PoC** to a future evaluation that looks more like **real agent traffic**: mixed intentions, vague resumes, and fail-closed clarification — without claiming we already have production memory.

**Next gates (not this deliverable):** (1) 10-example human annotation GREEN; (2) label these 5 sessions; (3) then ~8–12 session v1; (4) baseline grid; (5) only then discuss Cloud Run / a real MemoryProvider.
