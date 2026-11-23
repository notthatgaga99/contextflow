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
_TTL_FROM_TO_RE = re.compile(
    r"(?is)\bttl\b.{0,24}\bfrom\s+(\d+)\s*(?:m|min|mins|minutes)?"
    r".{0,16}\bto\s+(\d+)\s*(?:m|min|mins|minutes)?\b"
)
_TTL_SET_RE = re.compile(
    r"(?is)\b(?:set|use|make)\b.{0,24}\bttl\b(?:\s*(?:to|=|:)\s*|\s+)(\d+)\s*(?:m|min|mins|minutes)?\b"
)
_AUD_SET_RE = re.compile(
    r"(?is)\baud(?:ience)?\b(?:\s*(?:claim)?\s*)?(?:must\s+be|to|=|:)\s*"
    r"([a-z0-9][a-z0-9._-]*)"
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


def _slot_predecessor(
    asserted: list[MemoryItem],
    workstream_id: str,
    slot: str,
) -> MemoryItem | None:
    return next(
        (
            i for i in asserted
            if i.status == "asserted"
            and i.workstream_id == workstream_id
            and i.slot == slot
            and i.kind in ("decision", "correction", "fact", "constraint")
        ),
        None,
    )


def try_parse_slot_correction(
    message: str,
    *,
    asserted: list[MemoryItem],
    tasks: list[Task],
    focus_workstream_id: str | None = None,
) -> dict | None:
    """Non-color slot correction (docker base_image, ttl, aud)."""
    msg = (message or "").strip()
    if not msg or message_looks_recall_only(msg):
        return None

    slot: str | None = None
    new_val: str | None = None
    old_val: str | None = None
    cue_tasks: tuple[str, ...] = ()

    m = _DOCKER_FROM_TO_RE.search(msg)
    if m:
        slot, old_val, new_val = "base_image", m.group(1), m.group(2)
        cue_tasks = ("docker", "ci", "builder")
    if not slot:
        m = _TTL_FROM_TO_RE.search(msg)
        if m:
            slot, old_val, new_val = "ttl", m.group(1), f"{m.group(2)} minutes"
            cue_tasks = ("jwt", "auth", "ttl", "refresh")
    if not slot:
        m = _TTL_SET_RE.search(msg)
        if m:
            slot, new_val = "ttl", f"{m.group(1)} minutes"
            cue_tasks = ("jwt", "auth", "ttl", "refresh")
    if not slot:
        m = _AUD_SET_RE.search(msg)
        if m:
            slot, new_val = "aud", m.group(1)
            cue_tasks = ("jwt", "auth", "aud", "token")

    if not slot or not new_val:
        return None
    if old_val and old_val == new_val:
        return None

    ws = focus_workstream_id
    if not ws:
        for task in tasks:
            blob = " ".join(
                [task.title or "", " ".join(task.retrieval_cues or [])]
            ).lower()
            if any(c in blob for c in cue_tasks):
                ws = task.id
                break
    if not ws:
        return None

    predecessor = _slot_predecessor(asserted, ws, slot)
    if old_val and slot == "base_image" and not predecessor:
        return None
    body = {
        "kind": "decision",
        "text": new_val,
        "workstream_id": ws,
        "slot": slot,
        "action": "assert",
    }
    if predecessor:
        if predecessor.text.strip().lower() == new_val.strip().lower():
            return None
        body["supersedes_id"] = predecessor.id
    if any(_assertion_equivalent(body, item) for item in asserted):
        return None
    return body
