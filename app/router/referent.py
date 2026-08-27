"""Deterministic referent resolution. Pure: no registry writes, no gate, no LLM calls."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.models.task import Task
from app.retrieval.scorer import _tokens


_GENERIC = frozenset({
    "help", "write", "about", "still", "with", "from", "that", "this", "have",
    "been", "make", "just", "like", "them", "they", "your", "please", "actually",
    "okay", "need", "want", "does", "doing", "also", "more", "some", "than",
    "the", "and", "for", "are", "was", "can", "not",
})


def _content_tokens(text: str) -> set[str]:
    """Content tokens for lexical overlap. Tiny/generic words cannot unique-match a card."""
    out: set[str] = set()
    for t in _tokens(text):
        if t.isdigit() or (len(t) >= 3 and t not in _GENERIC):
            out.add(t)
    return out


def loop_referent_id(task_id: str, index: int) -> str:
    return f"{task_id}.loop{index + 1}"


def loop_index_from_id(task_id: str, referent_id: str) -> Optional[int]:
    prefix = f"{task_id}.loop"
    if not referent_id.startswith(prefix):
        return None
    rest = referent_id[len(prefix):]
    if not rest.isdigit():
        return None
    idx = int(rest) - 1
    return idx if idx >= 0 else None


def ensure_loop_clocks(task: Task) -> None:
    n = len(task.anchor.open_loops)
    if len(task.loop_mention_turns) < n:
        task.loop_mention_turns.extend([0] * (n - len(task.loop_mention_turns)))
    elif len(task.loop_mention_turns) > n:
        del task.loop_mention_turns[n:]


@dataclass
class ReferentCandidate:
    task_id: str
    referent_id: str
    text: str
    loop_mention: int
    task_mention: int


@dataclass
class ReferentResolution:
    kind: str
    predicted_task_id: Optional[str]
    predicted_referent_id: Optional[str]
    evidence: dict = field(default_factory=dict)
    ambiguous: bool = False
    use_referent_route: bool = False


_DEICTIC_ONLY = re.compile(
    r"^(?:please\s+)?(?:fix|change|try|do)\s+(?:that|it|this)[\.\!]*$"
    r"|^(?:that|it|this)[\.\!]*$",
)


def classify_utterance(message: str) -> str:
    m = message.strip().lower()
    if re.search(r"\b(other one|the other)\b", m) or re.match(r"^no[, ]", m):
        return "correction"
    if _DEICTIC_ONLY.fullmatch(m):
        return "deictic"
    if re.search(r"\b(that|it|this)\b", m):
        # Pronoun plus extra tokens: lexical if the extra content can match a card.
        return "explicit"
    return "explicit"


def collect_referents(tasks: list[Task]) -> list[ReferentCandidate]:
    rows: list[ReferentCandidate] = []
    for t in tasks:
        ensure_loop_clocks(t)
        goal = t.anchor.goal or t.title
        if not t.anchor.open_loops:
            rows.append(ReferentCandidate(
                task_id=t.id, referent_id=t.id, text=goal,
                loop_mention=t.mention_turn, task_mention=t.mention_turn,
            ))
            continue
        for i, text in enumerate(t.anchor.open_loops):
            rows.append(ReferentCandidate(
                task_id=t.id,
                referent_id=loop_referent_id(t.id, i),
                text=f"{text} {goal}",
                loop_mention=t.loop_mention_turns[i],
                task_mention=t.mention_turn,
            ))
    return rows


def resolve_referent(
    message: str,
    tasks: list[Task],
    llm_task_id: Optional[str],
    prior_referent_id: Optional[str] = None,
) -> ReferentResolution:
    kind = classify_utterance(message)
    refs = collect_referents(tasks)
    evidence: dict = {
        "kind": kind,
        "llm_task_soft": llm_task_id,
        "prior_referent": prior_referent_id,
    }
    if not refs:
        return ReferentResolution(kind, None, None, evidence, ambiguous=True, use_referent_route=False)

    if kind == "correction":
        return _resolve_correction(refs, prior_referent_id, evidence)

    msg_t = _content_tokens(message)
    scored: list[tuple[int, int, int, str, str]] = []
    for r in refs:
        overlap = len(msg_t & _content_tokens(r.text))
        scored.append((overlap, r.loop_mention, r.task_mention, r.task_id, r.referent_id))

    if kind == "explicit":
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        best = scored[0]
        evidence["lexical"] = [(s[4], s[0], s[1]) for s in scored]
        if best[0] > 0:
            if len(scored) > 1 and scored[1][0] == best[0]:
                return ReferentResolution(
                    kind, best[3], best[4], {**evidence, "rule": "lexical_tie"},
                    ambiguous=True, use_referent_route=True,
                )
            return ReferentResolution(
                kind, best[3], best[4], {**evidence, "rule": "lexical"},
                ambiguous=False, use_referent_route=True,
            )
        evidence["lexical_miss"] = True
        return ReferentResolution(
            kind, None, None, evidence, ambiguous=False, use_referent_route=False,
        )

    return _resolve_deictic(scored, llm_task_id, evidence)


def _resolve_correction(
    refs: list[ReferentCandidate],
    prior: Optional[str],
    evidence: dict,
) -> ReferentResolution:
    alts = [r for r in refs if r.referent_id != prior]
    if len(alts) == 1:
        a = alts[0]
        return ReferentResolution(
            "correction", a.task_id, a.referent_id, {**evidence, "rule": "correction_unique"},
            ambiguous=False, use_referent_route=True,
        )
    if prior:
        ranked = sorted(alts, key=lambda r: (r.loop_mention, r.task_mention), reverse=True)
        if ranked:
            a = ranked[0]
            return ReferentResolution(
                "correction", a.task_id, a.referent_id, {**evidence, "rule": "correction_exclude_prior"},
                ambiguous=False, use_referent_route=True,
            )
    return ReferentResolution(
        "correction", None, None, {**evidence, "rule": "correction_ambiguous"},
        ambiguous=True, use_referent_route=True,
    )


def _resolve_deictic(
    scored: list[tuple[int, int, int, str, str]],
    llm_task_id: Optional[str],
    evidence: dict,
) -> ReferentResolution:
    scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
    best = scored[0]
    runner = scored[1] if len(scored) > 1 else scored[0]
    evidence["ranked_clocks"] = [(s[4], s[1]) for s in scored]
    if best[1] == 0 and runner[1] == 0:
        return ReferentResolution(
            "deictic", None, None, {**evidence, "rule": "deictic_no_mention"},
            ambiguous=True, use_referent_route=True,
        )
    if best[1] == runner[1] and best[4] != runner[4]:
        if llm_task_id:
            for s in scored:
                if s[3] == llm_task_id and s[1] == best[1]:
                    return ReferentResolution(
                        "deictic", s[3], s[4], {**evidence, "rule": "deictic_llm_tiebreak"},
                        ambiguous=True, use_referent_route=True,
                    )
        return ReferentResolution(
            "deictic", best[3], best[4], {**evidence, "rule": "deictic_tie"},
            ambiguous=True, use_referent_route=True,
        )
    return ReferentResolution(
        "deictic", best[3], best[4], {**evidence, "rule": "deictic_clock"},
        ambiguous=False, use_referent_route=True,
    )


def resolution_metrics(
    gold_task_id: str,
    gold_referent_id: str,
    predicted_task_id: Optional[str],
    predicted_referent_id: Optional[str],
    decision: str,
    llm_task_id: Optional[str],
) -> dict:
    """Diagnostic fields. Not a benchmark claim."""
    task_ok = predicted_task_id == gold_task_id
    ref_ok = predicted_referent_id == gold_referent_id
    joint = task_ok and ref_ok
    acted = decision != "CLARIFY"
    llm_error = llm_task_id != gold_task_id
    return {
        "gold_task_id": gold_task_id,
        "gold_referent_id": gold_referent_id,
        "predicted_task_id": predicted_task_id,
        "predicted_referent_id": predicted_referent_id,
        "task_resolution_correct": task_ok,
        "referent_resolution_correct": ref_ok,
        "joint_resolution_correct": joint,
        "decision": decision,
        "wrong_action": acted and not joint,
        "llm_error": llm_error,
        "llm_error_recovered": bool(llm_error and joint),
    }
