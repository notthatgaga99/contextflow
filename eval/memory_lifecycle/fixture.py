"""Synthetic ABCD conversation for pipeline tests. Not a real user transcript.

If data/consented/session.json is present, the runner uses that substrate instead
and does not invent extract gold for it.
"""

from __future__ import annotations

NAVY_MSG = (
    "Actually, back to the dress — navy, not black. "
    "And it needs to work for the formal evening event."
)

SUBSTRATE_KIND = "synthetic_engineering_fixture"

TASKS = [
    {
        "id": "A", "title": "authentication",
        "goal": "fix JWT authentication",
        "loops": ["401 after refresh", "refresh token still expired"],
        "cues": ["jwt", "401", "authentication", "token"],
    },
    {
        "id": "B", "title": "corporate outfit",
        "goal": "choose a corporate event outfit",
        "loops": ["pick dress color"],
        "cues": ["outfit", "dress", "navy", "formal"],
    },
    {
        "id": "C", "title": "travel",
        "goal": "plan Lisbon trip",
        "loops": ["book hotel with parking"],
        "cues": ["lisbon", "hotel", "travel", "parking"],
    },
    {
        "id": "D", "title": "paper",
        "goal": "finish paper draft",
        "loops": ["write related-work section"],
        "cues": ["paper", "draft", "citation", "apa"],
    },
]

# User-only establishing + return trajectory. Assistant lines exist so FULL/RECENT
# have a transcript; they are stubs, not a real dialogue.
TURNS = [
    {"i": 0, "role": "user", "text": "JWT still returns 401 after refresh.",
     "engine_turn": 1, "extract": True},
    {"i": 1, "role": "assistant", "text": "[stub] noted the 401."},
    {"i": 2, "role": "user", "text": "Access token TTL is 15 minutes.",
     "engine_turn": 2, "extract": True},
    {"i": 3, "role": "assistant", "text": "[stub] noted TTL."},
    {"i": 4, "role": "user", "text": "I need a black dress for a corporate event.",
     "engine_turn": 3, "extract": True},
    {"i": 5, "role": "assistant", "text": "[stub] noted black dress."},
    {"i": 6, "role": "user", "text": "The event is formal and in the evening.",
     "engine_turn": 4, "extract": True},
    {"i": 7, "role": "assistant", "text": "[stub] noted formal evening."},
    {"i": 8, "role": "user", "text": "Planning a Lisbon trip; the hotel needs parking.",
     "engine_turn": 5, "extract": True},
    {"i": 9, "role": "assistant", "text": "[stub] noted Lisbon parking."},
    {"i": 10, "role": "user", "text": "The paper related-work section should use APA.",
     "engine_turn": 6, "extract": True},
    {"i": 11, "role": "assistant", "text": "[stub] noted APA."},
    {"i": 12, "role": "user", "text": "go back to the JWT 401 after refresh",
     "engine_turn": 7, "extract": False},
    {"i": 13, "role": "assistant", "text": "[stub] return A"},
    {"i": 14, "role": "user", "text": NAVY_MSG,
     "engine_turn": 8, "extract": True},
    {"i": 15, "role": "assistant", "text": "[stub] return B"},
    {"i": 16, "role": "user", "text": "back to the Lisbon hotel — still need parking?",
     "engine_turn": 9, "extract": False},
    {"i": 17, "role": "assistant", "text": "[stub] return C"},
    {"i": 18, "role": "user", "text": "the navy dress — add pockets if possible",
     "engine_turn": 10, "extract": True},
]

EXTRACT_SCRIPTS = {
    "JWT still returns 401": {
        "patches": [
            {"kind": "fact", "text": "401 after refresh", "workstream_id": "A",
             "referent_id": "A.loop1"},
        ],
    },
    "Access token TTL is 15 minutes": {
        "patches": [
            {"kind": "fact", "text": "access token TTL 15 minutes", "workstream_id": "A",
             "referent_id": "A.loop1", "slot": "ttl"},
        ],
    },
    "black dress for a corporate": {
        "patches": [
            {"kind": "decision", "text": "black", "workstream_id": "B",
             "referent_id": "B.loop1", "slot": "color"},
            {"kind": "constraint", "text": "corporate/formal", "workstream_id": "B",
             "referent_id": "B.loop1", "slot": "dress_code"},
        ],
    },
    "formal and in the evening": {
        "patches": [
            {"kind": "constraint", "text": "evening event", "workstream_id": "B",
             "referent_id": "B.loop1", "slot": "event_time"},
        ],
    },
    "Lisbon trip; the hotel needs parking": {
        "patches": [
            {"kind": "fact", "text": "Lisbon hotel needs parking", "workstream_id": "C",
             "referent_id": "C.loop1"},
        ],
    },
    "should use APA": {
        "patches": [
            {"kind": "fact", "text": "citation style APA", "workstream_id": "D",
             "referent_id": "D.loop1"},
        ],
    },
    "navy, not black": {
        "patches": [
            {"kind": "decision", "text": "navy", "workstream_id": "B",
             "referent_id": "B.loop1", "slot": "color"},
            {"kind": "constraint", "text": "corporate/formal", "workstream_id": "B",
             "referent_id": "B.loop1", "slot": "dress_code"},
            {"kind": "constraint", "text": "evening event", "workstream_id": "B",
             "referent_id": "B.loop1", "slot": "event_time"},
        ],
        "resolve_supersede_slot": True,
    },
    "add pockets if possible": {
        "patches": [
            {"kind": "preference", "text": "prefer pockets", "workstream_id": "B",
             "referent_id": "B.loop1", "slot": "pockets"},
        ],
    },
}

LLM_SCRIPTS = {
    "JWT still returns 401": {
        "task_id": "A", "is_new_task": False, "confidence": 0.4,
    },
    "Access token TTL": {
        "task_id": "A", "is_new_task": False, "confidence": 0.35,
    },
    "black dress for a corporate": {
        "task_id": "B", "is_new_task": False, "confidence": 0.4,
    },
    "formal and in the evening": {
        "task_id": "B", "is_new_task": False, "confidence": 0.35,
    },
    "Lisbon trip": {
        "task_id": "C", "is_new_task": False, "confidence": 0.4,
    },
    "should use APA": {
        "task_id": "D", "is_new_task": False, "confidence": 0.4,
    },
    "go back to the JWT": {
        "task_id": "A", "is_new_task": False, "confidence": 0.4,
    },
    "navy, not black": {
        "task_id": "B", "is_new_task": False, "confidence": 0.35,
    },
    "Lisbon hotel": {
        "task_id": "C", "is_new_task": False, "confidence": 0.4,
    },
    "navy dress — add pockets": {
        "task_id": "B", "is_new_task": False, "confidence": 0.35,
    },
    "back to the dress": {
        "task_id": "B", "is_new_task": False, "confidence": 0.35,
    },
    "navy dress for the formal": {
        "task_id": "B", "is_new_task": False, "confidence": 0.35,
    },
}

# Engine-turn ids of genuine returns (resume after other workstreams).
PROBES = [
    {
        "id": "return_A",
        "engine_turn": 7,
        "gold_task_id": "A",
        "gold_referent_id": "A.loop1",
        "gold_policy": "ACT",
        "phenomenon": "return_after_unrelated",
        "required_facts": ["401", "15 minutes"],
        "required_decisions": [],
        "required_constraints": [],
        "required_entities": [],
        "needed_state": ["401", "15 minutes"],
        "should_not_carry": ["Lisbon", "APA", "navy", "black dress"],
    },
    {
        "id": "return_B_navy",
        "engine_turn": 8,
        "gold_task_id": "B",
        "gold_referent_id": "B.loop1",
        "gold_policy": "ACT",
        "phenomenon": "correction_supersession",
        "required_facts": [],
        "required_decisions": ["navy"],
        "required_constraints": ["formal", "evening"],
        "required_entities": [],
        "needed_state": ["navy", "formal", "evening"],
        "should_not_carry": ["Lisbon", "APA", "401"],
        "stale_excluded": ["black"],
    },
    {
        "id": "return_C",
        "engine_turn": 9,
        "gold_task_id": "C",
        "gold_referent_id": "C.loop1",
        "gold_policy": "ACT",
        "phenomenon": "return_after_unrelated",
        "required_facts": ["parking", "Lisbon"],
        "required_decisions": [],
        "required_constraints": [],
        "required_entities": [],
        "needed_state": ["parking", "Lisbon"],
        "should_not_carry": ["navy", "APA", "401"],
    },
    {
        "id": "return_B_again",
        "engine_turn": 10,
        "gold_task_id": "B",
        "gold_referent_id": "B.loop1",
        "gold_policy": "ACT",
        "phenomenon": "multiple_returns_same_workstream",
        "required_facts": [],
        "required_decisions": ["navy"],
        "required_constraints": ["formal", "evening"],
        "required_entities": [],
        "needed_state": ["navy", "formal", "evening", "pockets"],
        "should_not_carry": ["Lisbon", "APA"],
    },
]


# Product-path order on the SAME ABCD utterances (not a new conversation world):
# A → B → C → D → return B → return A → correct B → return B again
PRODUCT_USER_TURNS = [
    (1, "JWT still returns 401 after refresh.", True),
    (2, "Access token TTL is 15 minutes.", True),
    (3, "I need a black dress for a corporate event.", True),
    (4, "The event is formal and in the evening.", True),
    (5, "Planning a Lisbon trip; the hotel needs parking.", True),
    (6, "The paper related-work section should use APA.", True),
    (7, "back to the dress for the corporate event", False),
    (8, "go back to the JWT 401 after refresh", False),
    (9, NAVY_MSG, True),
    (10, "the navy dress for the formal evening event", False),
]
