"""Deterministic correction parsing for MemoryExtractor (no routing, no store writes)."""

from __future__ import annotations

import re

from app.memory.extractor import (
    _COLOR_WORDS,
    _CORRECTION_SIGNAL_RE,
    _assertion_equivalent,
    _extract_color_token,
    message_looks_recall_only,
    message_looks_underspecified,
)
from app.models.memory import MemoryItem
from app.models.task import Task

_MAYBE_UNCERTAIN_RE = re.compile(r"(?is)\b(?:maybe|perhaps|might)\b.*\?")
_INSTEAD_RE = re.compile(
    r"(?is)\b(?:instead\s+of|rather\s+than|changed\s+my\s+mind|make\s+it|switch\s+to|"
    r"change\s+(?:the\s+)?(?:\w+\s+)?from)\b"
)
_FROM_TO_RE = re.compile(
    r"(?is)\bfrom\s+(" + "|".join(_COLOR_WORDS) + r")\s+to\s+(" + "|".join(_COLOR_WORDS) + r")\b"
)
_NOT_COLOR_RE = re.compile(
    r"(?is)\b(" + "|".join(_COLOR_WORDS) + r")\s*,\s*not\s+(" + "|".join(_COLOR_WORDS) + r")\b"
)
_NOT_ONLY_RE = re.compile(
    r"(?is)\bnot\s+(" + "|".join(_COLOR_WORDS) + r")\b"
)
_MAKE_IT_COLOR_RE = re.compile(
    r"(?is)\b(?:make\s+it|change\s+it\s+to)\s+(" + "|".join(_COLOR_WORDS) + r")\b"
)
_FAVORITE_COLOR_RE = re.compile(r"(?is)\b(?:favorite|favourite)\s+color\b")
_DOCKER_FROM_TO_RE = re.compile(
    r"(?is)\b(?:docker|image|base)\b.*\bfrom\s+(\w+)\s+to\s+(\w+)\b"
)


def _outfit_workstream_id(
    tasks: list[Task],
    asserted: list[MemoryItem],
    focus: str | None,
) -> str | None:
    if focus:
        return focus
    for item in asserted:
        if item.status == "asserted" and (item.slot == "color" or _extract_color_token(item.text)):
            return item.workstream_id
    for task in tasks:
        if any("color" in loop.lower() or "dress" in loop.lower() for loop in task.anchor.open_loops):
            return task.id
        if any(c in (task.title or "").lower() for c in ("outfit", "dress")):
            return task.id
    return None


def _color_predecessor(
    asserted: list[MemoryItem],
    workstream_id: str,
    old_color: str | None = None,
) -> MemoryItem | None:
    candidates = [
        i for i in asserted
        if i.status == "asserted"
        and i.workstream_id == workstream_id
        and i.kind in ("decision", "correction")
        and (i.slot == "color" or _extract_color_token(i.text))
    ]
    if old_color:
        for item in candidates:
            if _extract_color_token(item.text) == old_color:
                return item
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        slotted = [i for i in candidates if i.slot == "color"]
        if len(slotted) == 1:
            return slotted[0]
    return None


def try_parse_color_correction(
    message: str,
    *,
    asserted: list[MemoryItem],
    tasks: list[Task],
    focus_workstream_id: str | None = None,
) -> dict | None:
    """Return a MemoryPatch-shaped dict or None when abstaining."""
    msg = (message or "").strip()
    if not msg or message_looks_recall_only(msg) or message_looks_underspecified(msg):
        return None
    if _MAYBE_UNCERTAIN_RE.search(msg):
        return None
    if _FAVORITE_COLOR_RE.search(msg) and not _CORRECTION_SIGNAL_RE.search(msg):
        return None

    new_color: str | None = None
    old_color: str | None = None

    m = _FROM_TO_RE.search(msg)
    if m:
        old_color, new_color = m.group(1), m.group(2)
    m = _NOT_COLOR_RE.search(msg)
    if m:
        new_color, old_color = m.group(1), m.group(2)
    m = _MAKE_IT_COLOR_RE.search(msg)
    if m and not new_color:
        new_color = m.group(1)
    if not new_color and _INSTEAD_RE.search(msg):
        new_color = _extract_color_token(msg)
        m = _NOT_ONLY_RE.search(msg)
        if m:
            old_color = m.group(1)

    if not new_color:
        return None
    if not (_CORRECTION_SIGNAL_RE.search(msg) or old_color or _INSTEAD_RE.search(msg)):
        return None

    ws = _outfit_workstream_id(tasks, asserted, focus_workstream_id)
    if not ws:
        return None

    predecessor = _color_predecessor(asserted, ws, old_color)
    if old_color and not predecessor:
        return None
    if predecessor and _extract_color_token(predecessor.text) == new_color:
        return None

    body = {
        "kind": "decision",
        "text": new_color,
        "workstream_id": ws,
        "slot": "color",
        "action": "assert",
    }
    if predecessor:
        body["supersedes_id"] = predecessor.id
    if any(_assertion_equivalent(body, item) for item in asserted):
        return None
    return body


def try_parse_slot_correction(
    message: str,
    *,
    asserted: list[MemoryItem],
    tasks: list[Task],
    focus_workstream_id: str | None = None,
) -> dict | None:
    """Non-color slot correction (e.g. docker base image)."""
    msg = (message or "").strip()
    if not msg or message_looks_recall_only(msg):
        return None
    m = _DOCKER_FROM_TO_RE.search(msg)
    if not m:
        return None
    old_val, new_val = m.group(1), m.group(2)
    if old_val == new_val:
        return None
    ws = focus_workstream_id
    if not ws:
        for task in tasks:
            if any("docker" in c for c in task.retrieval_cues):
                ws = task.id
                break
    if not ws:
        return None
    predecessor = next(
        (
            i for i in asserted
            if i.status == "asserted"
            and i.workstream_id == ws
            and i.slot == "base_image"
        ),
        None,
    )
    if not predecessor and old_val:
        return None
    body = {
        "kind": "decision",
        "text": new_val,
        "workstream_id": ws,
        "slot": "base_image",
        "action": "assert",
    }
    if predecessor:
        body["supersedes_id"] = predecessor.id
    return body
