# Consented conversation — human interpretation sheet

**This is an audit sheet, not ContextFlow gold for threshold tuning.**  
**Do not label turns “correct/incorrect ContextFlow” here.**

Fill **after** `data/consented/session.json` exists. Keep private facts out of git. A paraphrased public copy may stay in this file; the machine snapshot `eval/consented_case/interpretation.json` is gitignored.

Copy the JSON shape from `eval/consented_case/interpretation.example.json`.

---

## Rules

- Do not assume every topic is a task (smalltalk, jailbreak play, one-shot trivia may be non-tasks).
- Do not assume every keyword repeat is a return.
- A return requires a **paused** workstream with an **unresolved** objective, then a later utterance that continues **that** objective after unrelated material.
- Abandoned = user explicitly dropped it or it was completed. Paused = still open.
- A correct `task_id` is **not** enough. Record required facts, decisions, constraints, entities, and what must **not** carry over. If those are missing from the reconstructed package, tag **critical failure** (extraction, not routing).
- Tag phenomenon only if it is in the transcript: `aba`, `abc_a`, `abc_b`, `multi_return`, `multi_loop`, `correction`, `ambiguous`, `abandoned`, `simultaneous`. Do not invent turns.

---

## Workstreams

| id | is_task? | short title | unresolved objective | open loops | decisions already made | constraints | entities/facts | last relevant mention (turn i) | abandoned or paused |
|---|---|---|---|---|---|---|---|---|---|
| A | | | | | | | | | |
| B | | | | | | | | | |
| C | | | | | | | | | |

---

## Selected demonstration turns (probes)

For each probe:

| field | |
|---|---|
| probe_id | P1 … |
| user_turn_index | `i` of the user message |
| turn range of prior A | |
| short neutral description | |
| intention A | |
| intervening intention B (and C if any) | |
| return turn | same as user_turn_index |
| why it qualifies | A → unrelated B → return to A, not keyword echo |
| confidence | high / medium / low |
| gold_task_id | |
| gold_referent_id | `{id}.loopk` or task id |
| gold_policy | ACT or CLARIFY |
| human_workstream | Judge-facing name, e.g. JWT debugging / event outfit / Lisbon trip |
| human_open_loop | Judge-facing loop, not `A.loop1` |
| phenomenon | `aba` / `abc_a` / … only if present |
| gold_policy | ACT or CLARIFY |
| clarify_appropriate | true if the return is genuinely ambiguous |
| required_facts / required_decisions / required_constraints / required_entities | what continuation needs |
| needed_state | extra must-see strings |
| should_not_carry | other workstreams that must not leak |
| clocks | mention / last_active / loop clocks **before** this utterance |
| active_task_id before probe | |
| last_selected_referent before probe | |

---

## Probe table (empty until transcript)

| probe_id | turn | A | intervening | return? | gold task/ref | policy | needed_state | confidence |
|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | — |

---

## Machine snapshot fields (`interpretation.json`)

```json
{
  "session_id": "",
  "workstreams": [
    {
      "id": "A",
      "is_task": true,
      "title": "",
      "unresolved_objective": "",
      "open_loops": [],
      "decisions": [],
      "constraints": [],
      "entities": [],
      "retrieval_cues": [],
      "status": "paused"
    }
  ],
  "probes": [
    {
      "id": "P1",
      "user_turn_index": 0,
      "short_description": "",
      "why_it_qualifies": "",
      "confidence": "high",
      "gold_task_id": "A",
      "gold_referent_id": "A.loop1",
      "gold_policy": "ACT",
      "required_facts": [],
      "required_decisions": [],
      "required_constraints": [],
      "required_entities": [],
      "needed_state": [],
      "should_not_carry": [],
      "contamination_cues": [],
      "active_task_id": "B",
      "last_selected_referent": "B.loop1",
      "clocks": {
        "A": {
          "status": "paused",
          "last_active_turn": 4,
          "mention_turn": 4,
          "loop_mention_turns": [4]
        }
      }
    }
  ]
}
```

Clocks must reflect **history**, not the desired CF output.
