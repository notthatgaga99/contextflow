"""Structured, redacted decision logs. Do not log raw message text or prompts."""

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
    latency_ms: float | None = None,
    memory_asserted: int | None = None,
    memory_total: int | None = None,
    package_status: str | None = None,
    context_mode: str | None = None,
    demo_only: bool | None = None,
) -> dict:
    """Redacted turn event for Cloud Logging / local structured logs.

    Never includes: message text, prompts, secrets, answers, or private content.
    """
    return {
        "event": "turn_decision",
        "severity": "contextflow",
        "correlation_id": correlation_id,
        "conversation_id": conversation_id,
        "turn": turn,
        "transition": transition,
        "task_id": task_id,
        "referent_id": referent_id,
        "extract_ok": extract_ok,
        "extract_status": extract_status,
        "message_chars": message_chars,
        "latency_ms": latency_ms,
        "memory_asserted": memory_asserted,
        "memory_total": memory_total,
        "package_status": package_status,
        "context_mode": context_mode,
        "demo_only": demo_only,
    }


def emit_decision(payload: dict) -> None:
    # Single-line JSON → Cloud Logging friendly; no raw user content.
    log.info("%s", json.dumps(payload, sort_keys=True, default=str))
