# Interleaved pilot — adversarial human-realism review

**Corpus:** `eval/interleaved_corpus/` S01–S05 (Pilot 0, unlabeled)  
**Date:** 2026-08-27  
**Scope:** dialogue text, not metadata claims. No models, no gold labels, no accuracy.

**Hypothesis under test (not “does ContextFlow work?”):**  
AI-agent users can interleave heterogeneous intentions, switch domains abruptly, abandon topics, return later, and use references whose intended memory **cannot** be recovered safely from a single `active_task` variable.

This review asks whether these five sessions are **credible material** for that claim.

---

## 1. Overall realism assessment

The sessions are **better than numbered “Turn 1: Task A” templates**. User lines include interruptions (`wait —`), shorthand, a typo (`tokne`), `never mind`, `actually`, `nvm`, and self-corrections. Assistant lines are often **too helpful**: they enumerate open cards, split loops, and pre-ask “which 401 / which Lisbon / which draft?” That is something a careful product assistant might do, but it is also **benchmark scaffolding**. It leaks an inventory into the history so later probes are easier for any full-history reader—and harder to treat as “the user was vague in a vacuum.”

**Cross-domain switches:** S03 t9 (`black or navy` after Envoy) and S04 t7 / t17 / t25 (`hotel` / pytest / kettle) are the most believable hops. They feel like a person with a chat window open all day, not a JSON schema.

**What the corpus does *not* yet strongly show:** many turns where the user is **still executing workstream A** while a **pure** `that/this` points at B. The best “active ≠ referent” items are mostly **lexically marked** (`that dress`, `the hotel`, `continue … on the deck`), which a Jaccard/LLM baseline can also catch. Pure deixis after a mixed inventory is present (S02 t19, S03 t33, S03 t37, S04 t41) and is usually **CLARIFY-shaped**, which is scientifically useful if we do not force ACT.

**Verdict in one line:** usable as a **small inspection set** with a **YELLOW** gate: annotate a **subset**, after clarifying protocol edges (NEW / ABANDON / one-thread vs two cards). Do not treat the full probe list as ready-made gold.

---

## 2. Session-by-session assessment

### S01 — focused JWT (control)

Reads like a real debugging thread: cookie, redis, curl vs browser, silent refresh `credentials`. The **second loop** (backgrounded access token) is introduced naturally at t5 and kept alive by the assistant (t6, t20, t34), so a later “parked” contrast is earned.

**Weaknesses:** Standup at t23 is realistic, but the assistant invents “last you told me it was 9:45” — the user never said 9:45. That is an **assistant hallucination** in the transcript, not a user mess. Only one non-technical hop; this is a control, not a diversity exhibit.

**Human mess:** `wait, different code`; `whatever, I'll ping Priya` then immediately back to `kid`.

**Would this matter if ContextFlow did not exist?** Yes as a **debugging dialogue** and a **two-loop** resume. The standup blip tests “don’t keep AUTH as the only possible topic,” which any assistant eval could use.

### S02 — same-product multitask

Believable **on-call / QA week**: two 401s, checkout remount, Docker COPY, OAuth allowlist. The `wait — CI is red` interrupt is human.

**Weaknesses:** t18 is an explicit **scoreboard of five open items**, then t19 is `fix that`. That sequence is how you **build** a deixis item, not how most users talk (they rarely wait for a numbered inventory). t39 “I meant the deployment one” after “the 401” is messy in a **good** way (user conflates CI with 401) and in a **constructed** way (sets up a category error).

**Would this matter without ContextFlow?** Yes: sibling 401s and “which bug” are classic agent failures. The inventory+`fix that` pair is more **eval-shaped**.

### S03 — technical → clothing → technical

The unannounced t9 question is the strongest **cross-domain** moment in the corpus. People do this. The outfit subsequence (midi, gold sandals, less formal) is coherent.

**Weaknesses:** Metadata splits **EVENT** vs **DRESS** though the talk is **one** Friday-outfit thread. Annotators will disagree on card boundaries. t31 “the other dress / I also mentioned a black one” **overclaims**: t9 was “black or navy” as **colors**, not two specified garments. t33 stacks `nvm` + `fix that` like a trap. t21 “Okay, let’s go back to OAuth” is the **announced** return the design doc said we should not require every time—here it is used once, which is fine, but it is cleaner than life.

**Would this matter without ContextFlow?** **Yes.** Dress-in-a-debug-chat is exactly the production story. Several later probes are mechanism-shaped (stacked deixis).

### S04 — planning → travel → debug → shopping

Lisbon **on the slide** vs Lisbon **the trip** is the best **same-keyword / different memory** construction and it is still conversational (`do I even mention Lisbon?` then `I never booked the hotel`). Kettle `never mind` is good abandonment. Soccer + in-laws is a plausible extra thread.

**Weaknesses:** Density of domains in ~25 user turns is **high** (deck, trip, test, kettle, dinner, kids). Possible for a stressed afternoon; still **packed**. t45 “I meant the deployment— wait we don’t have deployment” is **author voice** (corpus-aware). Assistant t24/t30/t36/t42/t44 keep **listing the world**.

**Long return:** Deck substance is t1–t6; resume t39 is ~30 turns later — this is the only session that really **feels** like a long return. Hotel from t7–t15 to t37/t47 is also a gap.

**Would this matter without ContextFlow?** Yes (calendar+travel+work). t45 should not be treated as natural speech.

### S05 — writing / paper / receipts / tap / token / zine

Closest to **messy life+work**. Email tone, “thirsty” attachment, paper citation, expenses, tap, then a real security bug, then a zine. Typo `tokne`. `never mind I'll do it tomorrow` then the assistant objects (realistic).

**Weaknesses:** t39 “not a gift token” names a **distractor that never appeared** in the conversation. That is an author wink at “semantic token.” t33 zine arrives as a complete subject change with “totally different thing sorry” — slightly narrated. Six workstreams is a lot; still more human than S02’s scoreboard.

**Would this matter without ContextFlow?** Yes for “which draft” and “what did we decide?” Gift-token line would not.

---

## 3. Candidate-probe table

Open memories are **as a reader could list them before that user turn** (not production clocks). “Inferable?” = could a careful human uniquely bind a referent **without** inventing gold. No ACT/CLARIFY gold is assigned.

| ID | Turn | Utterance (abbrev.) | Domains | Open (approx.) | Why interesting | Unique referent inferable? | Reasonable disagreement? | CLARIFY legitimate? | Leaks expected answer? | Challenges | Task / referent | Class |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S01 | 23 | standup 10:15 or 9:45? | eng → calendar | AUTH.loop1–2 | Unannounced hop; not a resume of a prior card | No prior STANDUP card; this **creates** a topic | Unlikely (it’s a new question) | No (it’s a new explicit Q) | Assistant later invents 9:45 in t24 | Recency (would stay AUTH) | Task (NEW vs AUTH); not loop resume | **WEAK** |
| S01 | 35 | leave background one; remind me what we changed for the 401 | eng | AUTH×2, STANDUP | Distinguishes two AUTH loops | **Yes** — “the 401” vs “background one” just named | Unlikely | No | Assistant t34 already split them | Recency if someone still has standup; Jaccard both 401-ish | **Both** (AUTH + loop1) | **STRONG** |
| S01 | 37 | the other one we just parked | eng | same | Intra-task loop after t35 | **Yes** if t35’s “leave the background one” is the park | Unlikely | Only if they ignore t35 | t34–t36 telegraph the split | Recency=401 thread; this points at parked loop | **Referent** (same task) | **STRONG** |
| S02 | 19 | fix that | eng | AUTH×2, FE, CI, OAUTH | Pure deixis after **five** items | **No** | **Yes** (OAuth last detailed vs Docker they asked to draft) | **Yes — primary** | t18 **lists all five**; t20 (after probe) also lectures | Recency, CF clocks, LLM | Both unresolved | **STRONG** (setup is **WEAK**/inventory) |
| S02 | 23 | still getting the 401 | eng | same | Sibling 401 | **No** | **Yes** | **Yes** | t4 already taught “two 401s” | Jaccard/similarity (both 401); recency OAuth/Docker | Referent (task AUTH likely) | **STRONG** |
| S02 | 29 | continue where we left off on checkout. the cartId flicker | eng | same | Resume FE while AUTH just spoken | **Yes** (explicit checkout + cartId) | Unlikely | No | Lexical giveaway | Recency (AUTH); LLM may stay on 401 | **Both** | **WEAK** |
| S02 | 37 | what did we decide about the 401 | eng | same | Ellipsis + collision | **No** | **Yes** | **Yes** | t24 already asked which 401 | Recency OAuth; lexical 401 | Referent; task maybe AUTH | **STRONG** |
| S02 | 39 | I meant the deployment one | eng | same | Correction; user maps “401” → CI | CI inferable as **intended repair of t37**, but they called it a 401 | **Yes** (CI vs still a 401) | Reasonable if they refuse to bind CI to “the 401” | “Deployment” is explicit; “we don’t have k8s” isn’t here | Recency AUTH; lexical 401 vs “deployment” | **Task** (CI vs AUTH); referent CI.loop1 | **WEAK** (messy, valuable) |
| S03 | 9 | black or navy look better? | eng → fashion | AUTH×2 | Abrupt domain; no prior clothes | **N/A** — new intention, not a pointer into AUTH | Unlikely it’s JWT | N/A as resume; asking “for what?” is human (t10) | No | Recency/similarity AUTH; LLM debug mode | **Task** NEW | **STRONG** |
| S03 | 17 | Make it a little less formal | fashion | AUTH + outfit | Ellipsis on outfit | **Yes** — last content is sandals/formality | Unlikely | No | Local context | Recency already outfit; weak routing test | Referent (shoes vs dress cut) mildly | **WEAK** |
| S03 | 21 | go back to OAuth | fashion → eng | same | Announced return; OAuth not JWT | **Yes** | Unlikely vs JWT | No | Explicit | LLM/JWT recency; similarity 401 | **Task** AUTH.loop2 vs loop1 | **WEAK** |
| S03 | 29 | what about that dress we discussed? | eng + fashion | AUTH hot, DRESS | Active AUTH, **explicit** other domain | **Yes** (dress) | Unlikely | No | “dress” leaks | Recency AUTH; similarity JWT | **Both** (task DRESS, referent dress/shoes) | **STRONG** |
| S03 | 31 | not that, the other dress | fashion | same | Correction; black dress **not really built** | **No** unique garment | **Yes** | **Yes** | User **asserts** a black dress that wasn’t specified | — | Referent | **ARTIFICIAL** |
| S03 | 33 | nvm. fix that | mixed | AUTH + outfit + black mention | Deixis after abandon | **No** | **Yes** | **Yes** | Stacked nvm+fix that | Recency, LLM, CF | Both unresolved | **STRONG** (slightly trap-shaped) |
| S03 | 37 | what about that one? | mixed | after AUTH recap t35 | Deixis, many leftovers | **No** | **Yes** | **Yes** | t36 recap lists AUTH tracks | Recency AUTH | Both | **STRONG** |
| S03 | 41 | back to that. the 401 | mixed | after shoes t39 | Ellipsis + 401 | **Mostly yes** — JWT refresh not OAuth (OAuth succeeded) | Mild (OAuth vs JWT) | Optional | “the 401” | Recency shoes | **Both** | **WEAK** |
| S04 | 7 | wait I never booked the hotel | work → travel | DECK×2 | New trip loop; Lisbon already on **deck** | Hotel is **new**; not the footnote | Unlikely they mean the slide | No | “hotel” | Similarity “Lisbon” → DECK | **Task** TRIP vs DECK | **STRONG** |
| S04 | 17 | actually the pytest thing… | travel → eng | DECK, TRIP, … | Abrupt debug | New TEST | Unlikely | No | Explicit pytest | Recency trip | Task NEW | **WEAK** (switch, not resume) |
| S04 | 25 | add the blue kettle to the cart | → shopping | many | Abrupt shopping | New CART | Unlikely | No | Explicit | Recency TEST | Task NEW | **WEAK** |
| S04 | 29 | never mind the kettle actually | shopping | CART just opened | Abandon | N/A (drop, not bind) | Unlikely | Protocol: not ACT | Explicit abandon | — | Neither (ABANDON) | **WEAK** (protocol gap) |
| S04 | 35 | what did we decide on Lisbon | work+travel | DECK.loop2 + TRIP×2 | Same keyword two memories | **No** | **Yes** | **Yes** | t36 (after) splits them; t24 already listed | Jaccard Lisbon; recency kids | **Task** | **STRONG** |
| S04 | 37 | the hotel | travel | after t36 split | Partial after clarify | **Yes** (TRIP.loop1) | Unlikely | No | t36 named hotel vs footnote | Recency; was CLARIFY then unique | Referent | **STRONG** |
| S04 | 39 | continue … on the deck | work | many | Long return, explicit | Task DECK **yes**; **which loop** no | Loop-level **yes** | Loop CLARIFY possible | “deck” | Recency hotel | Task yes, referent split | **WEAK**–**STRONG** |
| S04 | 41 | fix that | work | DECK two bullets in t40 | Deixis, two deck loops | **No** | **Yes** (headcount vs Lisbon footnote) | **Yes** | t40 listed two | Recency, CF | Referent | **STRONG** |
| S04 | 43 | no, the other one | mixed | if t41 bound one deck loop | Correction; **many** others | **No** | **Yes** | **Yes** | Followed by t45 author slip | Recency | Both | **STRONG** (adjacent t45 **ARTIFICIAL**) |
| S04 | 47 | and the hotel still | travel | after TEST | Return to hotel | **Yes** | Unlikely | No | Explicit | Recency TEST | Task+referent | **WEAK** |
| S05 | 7 | the draft is still too long | writing | EMAIL only | “Draft” before collision exists | **Yes** (email) | Unlikely | No | Only one draft | — | Both | **WEAK** |
| S05 | 11 | actually … sentence from the paper | writing → research | EMAIL + new PAPER | Abrupt | New | Unlikely | No | Explicit paper | Recency email | Task NEW | **WEAK** |
| S05 | 15 | the draft is a mess | writing+research | EMAIL + PAPER | Shared “draft” | **No** | **Yes** | **Yes** | t16 asks which | Jaccard draft | Task | **STRONG** |
| S05 | 25 | leaking the access token in the share URL | home → eng | many + new BUG | Abrupt + later “token” | **Yes** (new bug) | Unlikely | No | Explicit | Recency tap | Task NEW | **WEAK** |
| S05 | 31 | what did we decide? | many | 5+ threads | Ellipsis | **No** | **Yes** | **Yes** | t32 lists them | Recency token | Both | **STRONG** |
| S05 | 35 | go back to the draft | creative+writing | after zine | “Draft” ≠ zine; two drafts | **No** which draft | **Yes** | **Yes** | t36 asks | Recency zine; lexical draft | Task EMAIL vs PAPER | **STRONG** |
| S05 | 37 | the other one | same | t36 offered two drafts; **neither chosen** | Correction without last_selected | **No** | **Yes** | **Yes** | No | Policy 4 needs a prior selection | Referent | **STRONG** as CLARIFY; **INVALID** if forced ACT |
| S05 | 41 | continue where we left off | many | t39 named token | Ellipsis | **Arguably** last specified = token | **Yes** (email? paper? token?) | **Yes** | t39 is explicit if taken as last pick | Recency | Both | **WEAK** |
| S05 | 39 | *(not a listed probe)* token thing, not a gift token | eng | — | Names unused distractor | — | — | — | **Leaks** a phantom “gift token” | Similarity | — | **ARTIFICIAL** line |

**Counts of listed `probe_candidates` (34):**

| Class | n | IDs |
|---|---|---|
| STRONG | 16 | S01:35,37; S02:19,23,37; S03:9,29,33,37; S04:7,35,37,41,43; S05:15,31,35,37 |
| WEAK | 16 | S01:23; S02:29,39; S03:17,21,41; S04:17,25,29,39,47; S05:7,11,25,41 |
| ARTIFICIAL | 1 | S03:31 (black dress retrofit) |
| INVALID (as unique ACT) | 1 | S05:37 if gold were a specific draft; as CLARIFY it is STRONG |

S02 t19 is counted STRONG for the **user behavior** (vague deixis) with a WEAK **setup** (t18 inventory). S04 t43 is STRONG; do not treat t45 as evidence.

---

## 4. Cross-domain diversity (A)

| Session | Mix | Feels like a person? |
|---|---|---|
| S01 | Almost none | Control. Standup is a **ping**, not a second life. |
| S02 | None (all software) | Valid **Type A** interleaving only. |
| S03 | Debug ↔ outfit | **Yes** at t9. Later dress/OAuth/JWT weaving is slightly tidy. |
| S04 | Deck, trip, pytest, kettle, dinner, kids | **Yes** in pieces; **compressed** as a whole. |
| S05 | Email, paper, receipts, tap, security, zine | **Yes**; gift-token aside. |

The hypothesis **needs S03+S04+S05**. S01+S02 do not support “heterogeneous intentions” by themselves.

---

## 5. Active task ≠ foreground referent (B)

**Clear, natural:**

- **S03 t29** — Just on JWT 401; `that dress` is another workstream. Lexical, so recency fails and Jaccard may succeed.
- **S04 t7** — Deck/Lisbon footnote vs **hotel** (new trip object).
- **S02 t29** — Explicit checkout while AUTH was last bug talked; too explicit to stress deixis.

**Pure deixis while A is “the work” and B is “that”:** rare. **S03 t33 / t37** and **S02 t19** / **S04 t41** are deixis with **several** leftovers, i.e. CLARIFY, not a clean A-active / B-referent pair.

Do not invent that pair in gold. It is **under-represented** as a *unique* bind.

---

## 6. Multiple loops in one task (C)

| Place | Naturally two loops? | Later reference distinguishes? |
|---|---|---|
| S01 AUTH | **Yes** (t5 + refresh 401) | t35–t37 **yes** |
| S02 AUTH | **Yes** (refresh vs /me) | t23/t37 **no** (collision); t25 later names header |
| S03 AUTH | **Yes** (JWT vs OAuth) | t21 OAuth explicit; t25 user self-separates 401 vs OAuth |
| S03 DRESS | Shoes vs dress **yes**; navy vs black garment **no** | t31 **fails** |
| S04 DECK | Headcount vs Lisbon-as-win **yes** | t41 **no**; t39 names task only |
| S04 TRIP | Hotel vs flight **yes** | t37 hotel **yes** |
| S05 EMAIL | Tone vs attach **yes** | Not probed as a pair |
| S05 PAPER | Claim vs my paragraph **yes** | “draft” collides with EMAIL instead |

---

## 7. Ambiguity (D)

CLARIFY is a **legitimate human** response on: **S02 t19, t23, t37**; **S03 t31, t33, t37**; **S04 t35, t41, t43**; **S05 t15, t31, t35, t37, t41**.

Do not force ACT because a clock policy could pick a winner.

---

## 8. Wrong LLM proposal (E)

Meaningful **without rewriting** wherever the user is explicit or the case is already CLARIFY: if an LLM says AUTH at **S03 t29**, that is a real error. If it ACT-binds a 401 at **S02 t23**, that is a real error. **Do not** add a fake “gift token” memory to justify S05 t39.

---

## 9. Semantic distraction (F)

| Collision | Notes |
|---|---|
| 401 ×2 | S02 — strongest lexical distractor |
| Lisbon slide vs Lisbon trip | S04 t35 |
| draft ×2 | S05 t15, t35 |
| token | Dialogue has **URL access token** only; “gift token” is **not** earned |
| OAuth vs JWT | Related technical, not cross-domain |

---

## 10. Long return (G)

Only **S04 t39** (deck after kettle/dinner/kids) and **S04 t37/t47** (hotel after pytest/kettle/…) qualify. S01 standup gap is a few turns. There is **no** 20+ turn desert before a **bare** `that`.

---

## 11. Human messiness (H)

Present: `wait`, `actually`, `never mind`, `nvm`, `uh. the header one I think?`, `tokne`, `god.`, `ugh`, self-correction t45 (but t45 is also authorial).  

**Do not clean these.** Do **remove or ignore** t45’s “we don’t have deployment” as a **probe-adjacent** contamination.

---

## 12. Can the 10-example annotation protocol apply unchanged?

**Mostly, with gaps.** Unique bind / deixis / collision / correction / active ≠ referent / last mention ≠ collision-break still apply.

**Must brief annotators (not a new 50-page spec):**

1. **NEW topic** (S03 t9, S04 kettle, S05 paper): gold_task may be NEW; not every user turn is a pointer into an existing card.  
2. **ABANDON** (S04 t29): not ACT on CART; protocol should allow NONE + note, or skip the item.  
3. **EVENT vs DRESS:** one human thread; do not force two task ids.  
4. **Assistant recaps are history**, not the user’s intended bind. t18/t36/t40 **do** change what a later `that` can uniquely pick.  
5. **Elliptical** (`what did we decide?`, `continue where we left off`) = treat as deixis/collision per policy 2–3.  
6. **last_selected_referent** is **not** in the JSON; for correction items, infer only from dialogue (S05 t37 has **no** prior unique selection).

Without that briefing, P03/P10-style disagreements will recur (last mention vs collision).

---

## 13. Recommended subset for human annotation

**Include (stress the hypothesis, mostly STRONG):**

- S01 t35, t37 (loop split; control)  
- S02 t19, t23, t37  
- S03 t9, t29, t33, t37  
- S04 t7, t35, t37, t41, t43  
- S05 t15, t31, t35, t37  

That is **18** probes: enough to see agreement, not the whole 34.

**Optional WEAK (only if annotators have spare time):** S02 t29, S02 t39, S03 t21, S04 t39, S01 t23 (as NEW).

---

## 14. Cases that should be removed (from the annotation set, not necessarily deleted from the file)

- **S03 t31** — black dress not established.  
- **S04 t29** — until ABANDON is in the codebook.  
- **S04 t17, t25; S05 t11, t25** — new-topic switches; weak as *referent* items (keep in the **dialogue**, skip as probes).  
- **S03 t17** — local ellipsis, no routing stress.  
- **S05 t41** — under-specified “continue”; recency theater.  
- **Do not annotate S04 t45**; if t43 is kept, stop the clip before t45 or tell annotators to ignore t45 as non-user-realistic.

---

## 15. Cases that need clarification before annotation

1. Workstream inventory: is **OAuth** a loop of AUTH or its own task (S02 vs S03 disagree in metadata)?  
2. **EVENT vs DRESS** merge rule.  
3. Gold for **NEW** vs first mention (S03 t9).  
4. **ABANDON** (S04 t29).  
5. Whether assistant **clarifying questions** (t20, t24, t36) mean the **next user line** is an answer to the bot (unique bind) vs a new probe — S04 t37 is the latter and is clean; S02 t21 is not a listed probe but is the answer to t19.  
6. S05 t39 gift-token sentence: **ignore** as evidence of a second token memory.

---

## 16. Recommendation

**YELLOW.**

Ready for **independent human annotation of the recommended subset**, after a **one-page** annotator brief (NEW / ABANDON / card merge / ignore t45 and gift-token). Not GREEN for the full 34-probe list. Not RED: S03 t9, S03 t29, S02 t23, S04 t35, S05 t15 are credible and would still be interesting if ContextFlow had never been written.

**Do not expand the corpus. Do not label in this step. Do not run models.**

If the 18-probe subset still yields mixed agreement on CLARIFY vs last-mention, **stop** (protocol), do not add sessions.
