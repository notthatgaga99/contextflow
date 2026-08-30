"""Structured, redacted decision logs. Do not log raw message text."""

from __future__ import annotations

import json
import logging
import uuid

log = logging.getLogger("contextflow")


def correlation_id(incoming: str | None = None) -> str:
    if incoming and incoming.strip():
        return incoming.strip()[:128]
    return str(uuid.uuid4())


def decision_event(
    *,
    correlation_id: str,
    conversation_id: str,
    turn: int,
    transition: str,
    task_id: str | None,
    referent_id: str | None,
    extract_ok: bool,
    extract_status: str,
    message_chars: int,
) -> dict:
    return {
        "event": "turn_decision",
        "correlation_id": correlation_id,
        "conversation_id": conversation_id,
        "turn": turn,
        "transition": transition,
        "task_id": task_id,
        "referent_id": referent_id,
        "extract_ok": extract_ok,
        "extract_status": extract_status,
        "message_chars": message_chars,
    }


def emit_decision(payload: dict) -> None:
    log.info("%s", json.dumps(payload, sort_keys=True))
