"""Smoke/demo MockLLM + MockMemoryExtractor scripts.

Used when CF_SMOKE_FIXTURE=1. Lives in app/ so the HTTP runtime never imports
eval gold/probes. Synthetic ABCD engineering fixture — not organic chat.
"""

from __future__ import annotations

# Soft task proposals for MockLLM.propose — not ACT/CLARIFY decisions.
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
    "CI is failing on the Docker step": {
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
    # Ten-workstream resurrection (CF_SEED_TEN=1): outfit=E, docker=B
    "outfit black dress for corporate event": {
        "task_id": "E", "is_new_task": False, "confidence": 0.4,
    },
    "evening formal constraint outfit": {
        "task_id": "E", "is_new_task": False, "confidence": 0.35,
    },
    "navy not black outfit": {
        "task_id": "E", "is_new_task": False, "confidence": 0.35,
    },
    "back to the outfit thread": {
        "task_id": "E", "is_new_task": False, "confidence": 0.4,
    },
    "Docker CI step failing": {
        "task_id": "B", "is_new_task": False, "confidence": 0.4,
    },
    "orders API is slow": {
        "task_id": "C", "is_new_task": False, "confidence": 0.4,
    },
    "checkout renders twice": {
        "task_id": "D", "is_new_task": False, "confidence": 0.4,
    },
    "JWT auth 401 issue": {
        "task_id": "A", "is_new_task": False, "confidence": 0.4,
    },
    "Lisbon travel hotel": {
        "task_id": "F", "is_new_task": False, "confidence": 0.4,
    },
    "vegetarian dinner restaurant": {
        "task_id": "G", "is_new_task": False, "confidence": 0.4,
    },
    "closing slide deck": {
        "task_id": "H", "is_new_task": False, "confidence": 0.4,
    },
    "update job resume": {
        "task_id": "I", "is_new_task": False, "confidence": 0.4,
    },
    "trivia capital Portugal": {
        "task_id": "J", "is_new_task": False, "confidence": 0.4,
    },
    "return to orders API": {
        "task_id": "C", "is_new_task": False, "confidence": 0.4,
    },
}

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
    "CI is failing on the Docker step": {
        "patches": [
            {"kind": "fact", "text": "CI failing on Docker step", "workstream_id": "C",
             "referent_id": "C.loop1", "slot": "deploy"},
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
    # Ten-workstream resurrection (workstream E = outfit)
    "outfit black dress for corporate event": {
        "patches": [
            {"kind": "decision", "text": "black", "workstream_id": "E",
             "referent_id": "E.loop1", "slot": "color"},
            {"kind": "constraint", "text": "corporate/formal", "workstream_id": "E",
             "referent_id": "E.loop1", "slot": "dress_code"},
        ],
    },
    "evening formal constraint outfit": {
        "patches": [
            {"kind": "constraint", "text": "evening event", "workstream_id": "E",
             "referent_id": "E.loop1", "slot": "event_time"},
        ],
    },
    "navy not black outfit": {
        "patches": [
            {"kind": "decision", "text": "navy", "workstream_id": "E",
             "referent_id": "E.loop1", "slot": "color"},
        ],
    },
    "Docker CI step failing": {
        "patches": [
            {"kind": "fact", "text": "CI failing on Docker step", "workstream_id": "B",
             "referent_id": "B.loop1", "slot": "deploy"},
        ],
    },
    "JWT auth 401 issue": {
        "patches": [
            {"kind": "fact", "text": "401 after refresh", "workstream_id": "A",
             "referent_id": "A.loop1"},
        ],
    },
    "orders API is slow": {
        "patches": [
            {"kind": "fact", "text": "orders endpoint slow", "workstream_id": "C",
             "referent_id": "C.loop1"},
        ],
    },
}
