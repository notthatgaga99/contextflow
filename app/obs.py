"""Structured, redacted decision logs. Do not log raw message text or prompts."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid

log = logging.getLogger("contextflow")


def correlation_id(incoming: str | None = None) -> str:
    if incoming and incoming.strip():
        return incoming.strip()[:128]
    return str(uuid.uuid4())


def conversation_id_hash(conversation_id: str) -> str:
    """Redacted conversation identifier for logs (not reversible to raw id)."""
    raw = (conversation_id or "").strip().encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


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
    memory_backend: str | None = None,
    memory_reads: int | None = None,
    memory_writes: int | None = None,
    memory_current_count: int | None = None,
    memory_history_count: int | None = None,
    workstream_count: int | None = None,
    registry_reads: int | None = None,
    registry_writes: int | None = None,
    package_status: str | None = None,
    context_mode: str | None = None,
    demo_only: bool | None = None,
    answer_status: str | None = None,
    extract_committed: bool | None = None,
) -> dict:
    """Redacted turn event for Cloud Logging / local structured logs.

    Never includes: message text, prompts, secrets, answers, memory content,
    or private transcript bodies.
    """
    return {
        "event": "turn_decision",
        "subsystem": "contextflow",
        "correlation_id": correlation_id,
        "request_id": correlation_id,
        "conversation_id_hash": conversation_id_hash(conversation_id),
        "turn": turn,
        "transition": transition,
        "task_id": task_id,
        "selected_task": task_id,
        "referent_id": referent_id,
        "selected_referent": referent_id,
        "extract_ok": extract_ok,
        "extract_status": extract_status,
        "extract_committed": extract_committed,
        "message_chars": message_chars,
        "latency_ms": latency_ms,
        "memory_asserted": memory_asserted,
        "memory_total": memory_total,
        "memory_backend": memory_backend,
        "memory_reads": memory_reads,
        "memory_writes": memory_writes,
        "memory_current_count": memory_current_count if memory_current_count is not None else memory_asserted,
        "memory_history_count": memory_history_count,
        "workstream_count": workstream_count,
        "registry_reads": registry_reads,
        "registry_writes": registry_writes,
        "package_status": package_status,
        "context_mode": context_mode,
        "demo_only": demo_only,
        "answer_status": answer_status,
    }


def emit_decision(payload: dict) -> None:
    # Single-line JSON → Cloud Logging friendly; no raw user content.
    log.info("%s", json.dumps(payload, sort_keys=True, default=str))


FORBIDDEN_LOG_KEYS = frozenset({
    "message", "prompt", "answer", "text", "raw", "content",
    "GEMINI_API_KEY", "password", "credential", "secret",
})
