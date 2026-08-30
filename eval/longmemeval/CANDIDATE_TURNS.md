# LongMemEval candidate turns (mining only)

**Not gold.** No `gold_task_id` / `gold_referent_id` / `gold_decision`.  
Source: `data/longmemeval/longmemeval_oracle.json` unless `split=S`.  
`split=S` items are listed mainly to show **unsuitable** compilation hops.

`kind` is a miner tag, not a label for annotators.

| # | split | question_id | sess_idx | turn_idx (0-based in session) | kind | user text (abbrev.) | Why it might matter | Suitable? |
|---|---|---|---|---|---|---|---|---|
| 1 | oracle | e56a43b9 | 1 | 2 | correction | I meant FreshMart, it's my local grocery store… | Names a store after a possible mix-up | **yes** (in-stream correction) |
| 2 | oracle | 0f05491a | 0 | 10 | correction | Wait, I apologize… I actually need **125 stars**… not 400 | Fact self-repair | **yes** |
| 3 | oracle | 80ec1f4f | 1 | 10 | correction | Wait, I think I might have misspoken earlier… | Explicit misspeak | **yes** |
| 4 | oracle | gpt4_2f56ae70 | 2 | 10 | uncertainty | Wait, I just thought of something. Since I started a free trial of Disney+… | Partial ID of a documentary | **maybe** (still one-topic) |
| 5 | oracle | dfde3500 | 0 | 0 | ambiguity | …meet with Juan… Tuesday or Thursday? | Two days equally plausible | **yes** (CLARIFY-shaped) |
| 6 | oracle | ba61f0b9 | 0 | 0 | resumption | Going back to my former manager Rachel's team… | Returns to a named work group | **yes** |
| 7 | oracle | c8090214 | 0 | 0 | resumption | I'll go back to the Holiday Market… jewelry… sister | Resume shopping thread | **yes** |
| 8 | oracle | c6853660 | 0 | 0 | same-domain | going back to my drip coffee maker | Object switch vs French press | **yes** (weak routing) |
| 9 | oracle | a89d7624 | 0 | 0 | resumption | going back to Denver for another concert… BBQ near Red Rocks | Travel return | **yes** |
| 10 | oracle | gpt4_76048e76 | 0 | 10 | same-domain return | Anyway, back to the Kuat Transfer… | Aside then named product | **yes** |
| 11 | oracle | gpt4_5dcc0aab | 0 | 2 | local choice | try on both pairs to see which one feels more comfortable. By the way, I wore… Converse… | “Which one” = two shoes in-prompt; BTW injects a fact | **weak** / partly **unsuitable** (BTW) |
| 12 | oracle | gpt4_2487a7cb | 1 | 10 | local choice | try out both Tableau and Power BI… see which one feels more comfortable | Assistant-listed tools, not memory bind | **unsuitable** as routing |
| 13 | oracle | a3838d2b | 2 | 2 | underspec | not sure which one to choose [local org] | New choice, not prior loop | **unsuitable** |
| 14 | oracle | c14c00dd | 0 | 0 | false deixis | I've been thinking about trying to fix that leaky faucet… | `fix that` = new DIY topic | **unsuitable** |
| 15 | oracle | 0ea62687 | 0 | 4 | not collision | check the other things you mentioned… dash cam | “Other” = assistant’s checklist | **unsuitable** |
| 16 | oracle | 6cb6f249 | 1 | 2 | not collision | some of the other books on the list | List deixis, not two open loops | **unsuitable** |
| 17 | oracle | gpt4_2655b836 | 0 | 0 | fact-inject | …detailers… By the way, I just got my car serviced… March 15th | Canonical LME injection | **unsuitable** as CF probe |
| 18 | oracle | gpt4_2655b836 | 1 | 2 | same-domain interleave | …detailer… By the way, GPS system on 3/22… dealership | Two car issues in one session | **maybe** (same domain; BTW-shaped) |
| 19 | oracle | gpt4_2655b836 | 1 | 10 | same-domain | …detailer… By the way, I recently helped Emily move… | Domain hop inside persona session | **maybe** (still one speaker) |
| 20 | oracle | gpt4_2655b836 | 2 | 0 | long-ish return | planning a road trip… silver Honda Civic… February 10th | New session, same car persona | **weak** (session boundary, not in-turn `that`) |
| 21 | LME-Q | gpt4_2655b836 | — | — | post-hoc QA | What was the first issue I had with my new car after its first service? | Official LME question | **unsuitable** as in-stream probe |
| 22 | LME-Q | gpt4_70e84552_abs | — | — | abstention QA | Which task did I complete first, fixing the fence or purchasing three cows… | Official abs | **unsuitable** as CF CLARIFY (wrong unit) |
| 23 | LME-Q | 982b5123_abs | — | — | abstention QA | When did I book the Airbnb in Sacramento? | Named place never booked | **unsuitable** as in-stream |
| 24 | LME-Q | 852ce960 | — | — | knowledge-update QA | What was the amount I was pre-approved for… Wells Fargo? | Needs later fact to override earlier | **unsuitable** as turn probe (use a **user turn** from that instance instead if annotating) |
| 25 | LME-Q | 0a995998 | — | — | multi-session QA | How many items of clothing do I need to pick up or return… | Count across sessions | **unsuitable** as routing |
| 26 | S | (inst 0) | 0 | 0 | filler | farmer / fox / chicken / grain river puzzle | ShareGPT | **unsuitable** |
| 27 | S | (inst 0) | 2 | 0 | filler | numbered topics on radiation therapy lecture | ShareGPT | **unsuitable** |
| 28 | S | (inst 0) | 3 | 0 | filler | Rewrite Heat bank heist with the Joker | ShareGPT | **unsuitable** |
| 29 | S | (inst 0) | 7 | 0 | filler | predators of mussel larvae | UltraChat | **unsuitable** |
| 30 | S | (inst 0) | 8 | 0 | filler | add mouse click on chart to set alarm… trading | ShareGPT code UI | **unsuitable** (not same user as degree/fitness facts) |
| 31 | S | (inst 0) | 10 | 0 | filler | Explain bitcoin like I'm 10 | ShareGPT | **unsuitable** |
| 32 | S | dfde3500 | 5 | 0 | compiled hop | privacy notice / leads generation company | Unrelated to Juan-meeting persona | **unsuitable** as one-user switch |
| 33 | S | 488d3006 | 8 | 0 | compiled hop | course to learn bot trading week by week | Filler | **unsuitable** |
| 34 | S | 488d3006 | 9 | 0 | compiled hop | trip to Chicago from New York flights | Filler vs previous recipe | **unsuitable** |
| 35 | oracle | gpt4_d12ceb0e | 2 | — | mixed | going back to school… grandma 75 grandpa 78 | Career vs family in one utterance | **maybe** (underspecified “back”) |
| 36 | oracle | 852ce960 | 1 | — | same-domain | move into new home… cable… owning a home | Home admin after mortgage thread | **maybe** |
| 37 | oracle | 45dc21b6 | 0 | — | same-domain | tech review videos… Unbox Therapy… as I mentioned | Resumes named channel | **weak** |
| 38 | oracle | a3838d2b | 1 | — | same-domain | looking for something that combines arts and fitness | After a race story | **weak** |
| 39 | oracle | gpt4_2d58bcd6 | 1 | — | same-domain | finished three fiction novels last weekend… [titles] | Multiple books; later “which” would collide | **maybe** if a later turn is vague (inspect before annotating) |
| 40 | oracle | b9cfe692 | 0 | 6 | local choice | samples of both [narrators] to see which one I like | Two audiobook narrators in-session | **weak** / usually **unsuitable** |

Session/turn indices for rows 35–38 should be re-checked in the JSON before any annotation packet (miner used regex hits; some turns are first-user in session 0).

**Human subset (from the review doc):** items **1–10** plus one knowledge-update **user turn** and one multi-session **underspecified user turn** after manual read — **12 total**, oracle only.
