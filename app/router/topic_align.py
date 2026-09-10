"""Post-gate topic alignment — does not change gate/scorer thresholds.

When frozen routing binds CONTINUE/SWITCH/RETURN to a workstream whose
lexical cues barely match the user message, override:
  - to a better-matching open workstream, or
  - to NEW when nothing open matches (e.g. first fashion turn after tech).

This is a fail-closed demo safety rail, not a retune of gate.py / scorer.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain import Transition
from app.models.task import Task

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
# Deictic / underspecified continues — prefer stick to active, do not force NEW.
_CONTINUE_CUES = frozenset({
    "yes", "yeah", "yep", "ok", "okay", "sure", "same", "also", "and", "then",
    "those", "these", "them", "that", "this", "again", "still", "continue",
    "more", "please", "right", "exactly", "correct", "yaml", "yml", "json",
    "file", "files", "config", "configs", "manifest", "manifests",
})


def _tokens(text: str) -> set[str]:
    return {
        t for t in _TOKEN.findall((text or "").lower())
        if len(t) >= 3 and t not in _STOP
    }


def is_underspecified(message: str) -> bool:
    """Short or deictic follow-ups should not open a new workstream."""
    raw = (message or "").strip()
    if len(raw) < 24:
        return True
    toks = _tokens(raw)
    if len(toks) <= 3:
        return True
    # Mostly continuation glue + tiny content.
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
    inter = mt & bt
    return len(inter) / max(len(mt), 1)


@dataclass
class AlignmentOutcome:
    transition: Transition
    task_id: str | None
    reason: str
    selected_score: float
    best_other_id: str | None
    best_other_score: float


def align_plan(
    *,
    message: str,
    transition: Transition,
    task_id: str | None,
    open_tasks: list[Task],
    active_id: str | None,
    memory_texts_by_task: dict[str, list[str]] | None = None,
    # Selected task must clear this to keep the gate choice.
    keep_min: float = 0.12,
    # Challenger must beat selected by this margin to steal the bind.
    steal_margin: float = 0.08,
    # Absolute floor to accept a challenger / keep from forcing NEW.
    accept_min: float = 0.10,
) -> AlignmentOutcome | None:
    """Return an override, or None to keep the frozen gate decision."""
    # Spurious NEW on tiny follow-ups ("yml", "ok?", "yes") after CLARIFY/tech.
    if transition == Transition.NEW and active_id and is_underspecified(message):
        return AlignmentOutcome(
            transition=Transition.CONTINUE,
            task_id=active_id,
            reason="stick_underspecified_new",
            selected_score=0.0,
            best_other_id=None,
            best_other_score=0.0,
        )

    if transition in (Transition.CLARIFY, Transition.NEW):
        return None
    if not task_id or not open_tasks:
        return None

    mem = memory_texts_by_task or {}
    scores: dict[str, float] = {}
    for t in open_tasks:
        scores[t.id] = overlap_score(message, task_blob(t, mem.get(t.id)))

    selected = scores.get(task_id, 0.0)
    others = [(tid, sc) for tid, sc in scores.items() if tid != task_id]
    best_other_id, best_other = (None, 0.0)
    if others:
        best_other_id, best_other = max(others, key=lambda x: x[1])

    # Gate choice is good enough.
    if selected >= keep_min:
        return None

    # A different open thread clearly matches the message better.
    if (
        best_other_id
        and best_other >= accept_min
        and best_other >= selected + steal_margin
        and not is_underspecified(message)
    ):
        if active_id == best_other_id:
            tr = Transition.CONTINUE
        elif active_id and active_id != best_other_id:
            tr = Transition.RETURN
        else:
            tr = Transition.SWITCH
        return AlignmentOutcome(
            transition=tr,
            task_id=best_other_id,
            reason="steal_better_workstream",
            selected_score=selected,
            best_other_id=best_other_id,
            best_other_score=best_other,
        )

    # Substantial mismatched topic (e.g. fashion after IoT) → NEW.
    # Vague / short YAML-style continues must NOT open a new thread.
    if selected < accept_min and not is_underspecified(message):
        return AlignmentOutcome(
            transition=Transition.NEW,
            task_id=None,
            reason="force_new_topic_mismatch",
            selected_score=selected,
            best_other_id=best_other_id,
            best_other_score=best_other,
        )

    return None