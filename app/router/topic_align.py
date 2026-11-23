"""Post-gate topic alignment — thin adapter over discrimination policy table.

Frozen gate thresholds unchanged. Math/application lives in
`thread_discriminate.decide_discrimination` (see THREAD_DISCRIMINATION_MODEL.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.domain import Transition
from app.models.task import Task
from app.router.thread_discriminate import IdentityCues, decide_discrimination

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset({
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "am", "i", "me", "my", "we", "our",
    "you", "your", "it", "its", "this", "that", "these", "those", "at", "by",
    "from", "as", "into", "about", "like", "so", "if", "then", "than", "too",
    "can", "will", "just", "have", "has", "had", "do", "does", "did", "not",
    "what", "when", "where", "how", "why", "which", "who", "whom", "there",
    "here", "also", "very", "really", "should", "would", "could", "need",
    "want", "get", "got", "make", "made", "using", "use", "used",
})
_CONTINUE_CUES = frozenset({
    "yes", "yeah", "yep", "ok", "okay", "sure", "same", "also", "and", "then",
    "those", "these", "them", "that", "this", "again", "still", "continue",
    "more", "please", "right", "exactly", "correct", "yaml", "yml", "json",
    "file", "files", "config", "configs", "manifest", "manifests",
    "hikes", "hike", "cafes", "cafe", "guide", "trip", "solo", "bash", "exit",
    "pipeline", "pipelines", "azure", "agent", "tests", "test", "merge",
})


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for t in _TOKEN.findall((text or "").lower()):
        if len(t) < 3 or t in _STOP:
            continue
        out.add(t)
        if t.endswith("s") and len(t) >= 4 and not t.endswith("ss"):
            out.add(t[:-1])
        if len(t) >= 3 and not t.endswith("s"):
            out.add(t + "s")
    return out


def is_underspecified(message: str) -> bool:
    """Short or deictic follow-ups should not open a new workstream."""
    raw = (message or "").strip()
    if len(raw) < 24:
        return True
    toks = _tokens(raw)
    if len(toks) <= 3:
        return True
    content = {t for t in toks if t not in _CONTINUE_CUES}
    if len(content) <= 1 and len(raw) < 80:
        return True
    return False


def task_blob(task: Task, extra_texts: list[str] | None = None) -> str:
    parts = [
        task.title or "",
        task.anchor.goal or "",
        " ".join(task.anchor.open_loops or []),
        " ".join(task.retrieval_cues or []),
        " ".join(task.anchor.decisions or []),
        " ".join(task.anchor.constraints or []),
        " ".join(task.anchor.entities or []),
    ]
    if extra_texts:
        parts.extend(extra_texts)
    return " ".join(parts)


def overlap_score(message: str, blob: str) -> float:
    mt, bt = _tokens(message), _tokens(blob)
    if not mt or not bt:
        return 0.0
    return len(mt & bt) / max(len(mt), 1)


@dataclass
class AlignmentOutcome:
    transition: Transition
    task_id: str | None
    reason: str
    selected_score: float
    best_other_id: str | None
    best_other_score: float
    # Two-channel math snapshot (application point of the model).
    discrimination: dict[str, Any] = field(default_factory=dict)


def align_plan(
    *,
    message: str,
    transition: Transition,
    task_id: str | None,
    open_tasks: list[Task],
    active_id: str | None,
    memory_texts_by_task: dict[str, list[str]] | None = None,
    identity_cues_by_task: dict[str, IdentityCues] | None = None,
    llm: Any | None = None,
    keep_min: float = 0.12,  # retained for call-site compat; policy owns thresholds
    steal_margin: float = 0.08,
    accept_min: float = 0.10,
) -> AlignmentOutcome | None:
    """Return an override, or None to keep the frozen gate decision."""
    del keep_min, steal_margin, accept_min  # policy table owns constants
    decided = decide_discrimination(
        message=message,
        gate_transition=transition,
        gate_task_id=task_id,
        open_tasks=open_tasks,
        active_id=active_id,
        memory_texts_by_task=memory_texts_by_task,
        identity_cues_by_task=identity_cues_by_task,
        underspecified=is_underspecified(message),
        llm=llm,
    )
    if decided is None:
        return None
    return AlignmentOutcome(
        transition=decided.transition,
        task_id=decided.task_id,
        reason=decided.reason,
        selected_score=decided.selected_score,
        best_other_id=decided.best_other_id,
        best_other_score=decided.best_other_score,
        discrimination=decided.evidence.to_dict(),
    )
