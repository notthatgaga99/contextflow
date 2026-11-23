"""Contrastive thread discrimination — application of two-channel math to bind.

Novelty is not IDF/margins themselves; it is wiring genre (S) vs identity (I)
into ContextFlow's post-gate switch so near-miss ≠ same and extend ≠ NEW.

See docs/THREAD_DISCRIMINATION_MODEL.md.

Product-locked: weak identity + high genre confusion → CLARIFY
  (context mgmt still binds silently when identity is recoverable;
   clarify is the least harm on bad/thin prompts).
  Escape hatch only: CF_NEAR_MISS_WEAK=stick_active
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.domain import Transition
from app.models.task import Task
from app.router.referent import classify_utterance

_TOKEN = re.compile(r"[a-z0-9]+")
# Strip return framing so "go back to the JWT" scores on JWT, not on "back".
_RETURN_PREFIX = re.compile(
    r"^(?:(?:please\s+)?(?:let'?s\s+)?(?:go\s+)?back\s+to\s+(?:the\s+)?"
    r"|return\s+to\s+(?:the\s+)?)",
    re.I,
)
_STOP = frozenset({
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "am", "i", "me", "my", "we", "our",
    "you", "your", "it", "its", "this", "that", "these", "those", "at", "by",
    "from", "as", "into", "about", "like", "so", "if", "then", "than", "too",
    "can", "will", "just", "have", "has", "had", "do", "does", "did", "not",
    "what", "when", "where", "how", "why", "which", "who", "whom", "there",
    "here", "also", "very", "really", "should", "would", "could", "need",
    "want", "get", "got", "make", "made", "using", "use", "used",
    "fix", "please", "check", "back", "again",
})

Region = Literal[
    "underspecified_continue",
    "near_miss_clarify",
    "near_miss_resolve",
    "extend_continue",
    "true_new",
    "keep_gate",
    "overlap_steal",
]

# Policy thresholds (documented in THREAD_DISCRIMINATION_MODEL.md §5).
TAU_S = 0.06          # shared-hit floor for confusion counting (raw s)
EPS_DELTA = 0.06      # identity margin below → clarify under confusion
TAU_ID_ABS = 0.15     # best d must clear this to *resolve* under confusion
TAU_EXT = 0.06        # ACTIVE distinctive floor for extension stick
DELTA_RIVAL = 0.10    # rival must beat ACTIVE by this on d to unstick
TAU_NEW_D = 0.06
TAU_NEW_O = 0.10
KEEP_MIN_O = 0.12
STEAL_MARGIN_O = 0.08
ACCEPT_MIN_O = 0.10
CONFUSION_MIN_PAIR = 0.05  # c_S on raw shared hits (genre glue)


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for t in _TOKEN.findall((text or "").lower()):
        if len(t) < 3 or t in _STOP:
            continue
        out.add(t)
        # Symmetric stem: 3-letter identity tokens (jwt) must not lose to
        # 4-letter ones (cart) just because only the latter grew a plural.
        if t.endswith("s") and len(t) >= 4 and not t.endswith("ss"):
            out.add(t[:-1])
        if len(t) >= 3 and not t.endswith("s"):
            out.add(t + "s")
    return out


def _norm_slot(slot: str) -> str:
    return (slot or "").strip().replace("_", " ").replace("-", " ")


@dataclass(frozen=True)
class IdentityCues:
    """Structured I-channel material already stored on MemoryItems.

    Slot *names* identify a thread when unique in the open set (`ttl` vs
    `sku`). Shared slot names (`window` on two cards) are genre, not identity.
    """

    slots: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()

    def extra_texts(self) -> list[str]:
        parts: list[str] = []
        names = [_norm_slot(s) for s in self.slots if s and s.strip()]
        if names:
            parts.append(" ".join(names))
        parts.extend(e for e in self.entities if e and str(e).strip())
        return parts


_GENERIC_SLOTS = frozenset({"entity", "fact", "item", "memory", "note", "kind"})


def identity_cues_from_items(items: list[Any] | None) -> IdentityCues:
    """Read slot + kind=entity from asserted items. Does not invent cues."""
    slots: list[str] = []
    entities: list[str] = []
    seen_slots: set[str] = set()
    for item in items or []:
        slot = _norm_slot(getattr(item, "slot", None) or "")
        if slot and slot.lower() not in _GENERIC_SLOTS and slot not in seen_slots:
            seen_slots.add(slot)
            slots.append(slot)
        kind = (getattr(item, "kind", None) or "").strip().lower()
        text = (getattr(item, "text", None) or "").strip()
        if kind == "entity" and text:
            entities.append(text)
    return IdentityCues(slots=tuple(slots), entities=tuple(entities))


def _task_blob(task: Task, extra_texts: list[str] | None = None) -> str:
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


def idf_weights(tok_sets: dict[str, set[str]]) -> dict[str, float]:
    """w(t) = log((1+N)/(1+df(t))) over open threads."""
    n = max(len(tok_sets), 1)
    df: dict[str, int] = {}
    for toks in tok_sets.values():
        for t in toks:
            df[t] = df.get(t, 0) + 1
    return {t: math.log((1.0 + n) / (1.0 + c)) for t, c in df.items()}


def _weighted_frac(hit: set[str], universe: set[str], w: dict[str, float]) -> float:
    denom = sum(w.get(t, 0.0) for t in universe) + 1e-9
    num = sum(w.get(t, 0.0) for t in hit)
    return num / denom


@dataclass(frozen=True)
class ThreadScores:
    task_id: str
    overlap: float          # o_i (unweighted; debug / legacy)
    distinctive: float      # d_i^w identity
    shared_hit: float       # s_i^w genre
    overlap_w: float = 0.0  # o_i^w
    distinctive_raw: float = 0.0
    shared_hit_raw: float = 0.0
    slot_hits: tuple[str, ...] = ()


@dataclass
class DiscriminationEvidence:
    """Auditable two-channel snapshot for one message vs open set."""

    scores: dict[str, ThreadScores] = field(default_factory=dict)
    c_S: float = 0.0                 # pair-form shared confusion
    C_S_count: int = 0               # #threads with s_i >= TAU_S
    delta_I: float = 0.0             # d_(1) - d_(2)
    winner_id: str | None = None     # argmax d_i
    second_id: str | None = None
    region: Region | None = None
    high_confusion: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "c_S": round(self.c_S, 4),
            "C_S_count": self.C_S_count,
            "delta_I": round(self.delta_I, 4),
            "winner_id": self.winner_id,
            "second_id": self.second_id,
            "region": self.region,
            "high_confusion": self.high_confusion,
            "slot_hits": {
                tid: list(s.slot_hits)
                for tid, s in self.scores.items()
                if s.slot_hits
            },
            "scores": {
                tid: {
                    "o": round(s.overlap, 4),
                    "o_w": round(s.overlap_w, 4),
                    "d": round(s.distinctive, 4),
                    "d_raw": round(s.distinctive_raw, 4),
                    "s": round(s.shared_hit, 4),
                    "s_raw": round(s.shared_hit_raw, 4),
                    "slot_hits": list(s.slot_hits),
                }
                for tid, s in self.scores.items()
            },
        }


@dataclass
class DiscriminationDecision:
    transition: Transition
    task_id: str | None
    reason: str
    evidence: DiscriminationEvidence
    # For AlignmentOutcome compat
    selected_score: float = 0.0
    best_other_id: str | None = None
    best_other_score: float = 0.0


def _message_for_score(message: str) -> str:
    """Drop return/deictic framing so identity tokens dominate."""
    m = (message or "").strip()
    stripped = _RETURN_PREFIX.sub("", m).strip()
    return stripped or m


def score_threads(
    message: str,
    open_tasks: list[Task],
    memory_texts_by_task: dict[str, list[str]] | None = None,
    identity_cues_by_task: dict[str, IdentityCues] | None = None,
) -> dict[str, ThreadScores]:
    """Per-thread o/d/s with IDF-weighted d and s (identity / genre channels)."""
    mem = memory_texts_by_task or {}
    cues = identity_cues_by_task or {}
    blobs: dict[str, str] = {}
    for t in open_tasks:
        extra = list(mem.get(t.id) or [])
        ic = cues.get(t.id)
        if ic:
            extra.extend(ic.extra_texts())
        blobs[t.id] = _task_blob(t, extra)
    tok_sets = {tid: _tokens(blob) for tid, blob in blobs.items()}
    msg_toks = _tokens(_message_for_score(message))
    weights = idf_weights(tok_sets)
    n_msg = max(len(msg_toks), 1)
    out: dict[str, ThreadScores] = {}
    for t in open_tasks:
        own = tok_sets[t.id]
        rivals: set[str] = set()
        for oid, ots in tok_sets.items():
            if oid != t.id:
                rivals |= ots
        distinctive = own - rivals
        shared = own & rivals
        inter_own = msg_toks & own
        inter_dist = msg_toks & distinctive
        inter_shared = msg_toks & shared
        ic = cues.get(t.id)
        slot_toks = _tokens(" ".join(ic.slots)) if ic and ic.slots else set()
        slot_hits = tuple(sorted(msg_toks & slot_toks & distinctive))
        out[t.id] = ThreadScores(
            task_id=t.id,
            overlap=len(inter_own) / n_msg,
            distinctive=_weighted_frac(inter_dist, msg_toks, weights) if msg_toks else 0.0,
            shared_hit=_weighted_frac(inter_shared, msg_toks, weights) if msg_toks else 0.0,
            overlap_w=_weighted_frac(inter_own, msg_toks, weights) if msg_toks else 0.0,
            distinctive_raw=len(inter_dist) / n_msg,
            shared_hit_raw=len(inter_shared) / n_msg,
            slot_hits=slot_hits,
        )
    return out


def build_evidence(scores: dict[str, ThreadScores]) -> DiscriminationEvidence:
    if not scores:
        return DiscriminationEvidence()
    # Identity ranking uses IDF-weighted d (rare tokens dominate).
    ranked = sorted(scores.values(), key=lambda s: (s.distinctive, s.overlap_w), reverse=True)
    d1 = ranked[0].distinctive
    d2 = ranked[1].distinctive if len(ranked) > 1 else 0.0
    # Genre confusion must use RAW shared hits — IDF suppresses glue tokens like 401,
    # which would hide the near-miss regime we care about.
    c_s = 0.0
    ids = list(scores.keys())
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            c_s = max(
                c_s,
                min(scores[a].shared_hit_raw, scores[b].shared_hit_raw),
            )
    c_count = sum(1 for s in scores.values() if s.shared_hit_raw >= TAU_S)
    # Also: two threads both reasonably overlapping the message → confusingly close.
    by_o = sorted(scores.values(), key=lambda s: s.overlap, reverse=True)
    close_pair = (
        len(by_o) >= 2
        and by_o[0].overlap >= 0.12
        and by_o[1].overlap >= 0.12
        and abs(by_o[0].overlap - by_o[1].overlap) <= 0.10
    )
    high = c_s >= CONFUSION_MIN_PAIR or c_count >= 2 or close_pair
    return DiscriminationEvidence(
        scores=scores,
        c_S=c_s,
        C_S_count=c_count,
        delta_I=d1 - d2,
        winner_id=ranked[0].task_id,
        second_id=ranked[1].task_id if len(ranked) > 1 else None,
        high_confusion=high,
    )


def _bind_transition(active_id: str | None, task_id: str) -> Transition:
    if active_id == task_id:
        return Transition.CONTINUE
    if active_id and active_id != task_id:
        return Transition.RETURN
    return Transition.SWITCH


def near_miss_pair(
    scores: dict[str, ThreadScores],
    *,
    close_margin: float = 0.06,
    both_min_overlap: float = 0.12,
) -> tuple[str, str] | None:
    """Legacy helper — prefer evidence.high_confusion + delta_I."""
    if len(scores) < 2:
        return None
    ranked = sorted(scores.values(), key=lambda s: s.overlap, reverse=True)
    a, b = ranked[0], ranked[1]
    if a.overlap < both_min_overlap or b.overlap < both_min_overlap:
        return None
    if abs(a.overlap - b.overlap) > close_margin:
        return None
    return a.task_id, b.task_id


def prefer_distinctive(
    scores: dict[str, ThreadScores],
    selected_id: str | None,
    *,
    steal_margin: float = 0.08,
    min_distinctive: float = 0.08,
) -> str | None:
    if not scores:
        return None
    best = max(scores.values(), key=lambda s: (s.distinctive, s.overlap_w))
    if best.distinctive < min_distinctive:
        return None
    if not selected_id:
        return best.task_id
    sel = scores.get(selected_id)
    sel_d = sel.distinctive if sel else 0.0
    if best.task_id != selected_id and best.distinctive >= sel_d + steal_margin:
        return best.task_id
    return None


def stick_active_extension(
    message: str,
    active_id: str | None,
    scores: dict[str, ThreadScores],
    *,
    min_distinctive: float = TAU_EXT,
    max_rival_distinctive_lead: float = DELTA_RIVAL,
) -> bool:
    if not active_id or active_id not in scores:
        return False
    active = scores[active_id]
    rivals = [s for tid, s in scores.items() if tid != active_id]
    best_rival_d = max((s.distinctive for s in rivals), default=0.0)
    if best_rival_d >= active.distinctive + max_rival_distinctive_lead:
        return False
    if active.distinctive >= min_distinctive:
        return True
    if active.overlap_w > 0 and active.overlap_w >= best_rival_d:
        return True
    if active.overlap >= 0.10 and best_rival_d < active.overlap:
        return True
    return False


def decide_discrimination(
    *,
    message: str,
    gate_transition: Transition,
    gate_task_id: str | None,
    open_tasks: list[Task],
    active_id: str | None,
    memory_texts_by_task: dict[str, list[str]] | None = None,
    identity_cues_by_task: dict[str, IdentityCues] | None = None,
    underspecified: bool = False,
) -> DiscriminationDecision | None:
    """Single policy table (§5). None = keep frozen gate decision."""
    if not open_tasks and gate_transition != Transition.NEW:
        return None

    scores = score_threads(
        message, open_tasks, memory_texts_by_task, identity_cues_by_task,
    ) if open_tasks else {}
    ev = build_evidence(scores)

    # Deixis / correction belong to the referent clock, not I-channel.
    # "fix that" shares the verb `fix` across cards — that is not near-miss.
    utterance = classify_utterance(message)
    if utterance in ("deictic", "correction"):
        ev.region = "keep_gate"
        return None

    def _out(
        tr: Transition,
        tid: str | None,
        reason: str,
        region: Region,
    ) -> DiscriminationDecision:
        ev.region = region
        sel_o = scores[gate_task_id].overlap if gate_task_id and gate_task_id in scores else 0.0
        other = ev.second_id if ev.winner_id == gate_task_id else ev.winner_id
        other_o = scores[other].overlap if other and other in scores else 0.0
        return DiscriminationDecision(
            transition=tr,
            task_id=tid,
            reason=reason,
            evidence=ev,
            selected_score=sel_o,
            best_other_id=other,
            best_other_score=other_o,
        )

    if not scores:
        # Underspecified with no open cards — nothing to do
        return None

    # --- 1. Near-miss BEFORE underspecified stick ---
    # Short "still getting 401" is underspecified *and* high confusion; genre
    # glue must CLARIFY/resolve, not silently CONTINUE ACTIVE.
    # Product fork: CF_NEAR_MISS_WEAK=stick_active → CONTINUE ACTIVE instead.
    weak_policy = (os.getenv("CF_NEAR_MISS_WEAK", "clarify") or "clarify").strip().lower()
    if ev.high_confusion:
        best_d = scores[ev.winner_id].distinctive if ev.winner_id in scores else 0.0
        if ev.delta_I < EPS_DELTA or best_d < TAU_ID_ABS:
            if weak_policy in ("stick_active", "stick", "active") and active_id:
                return _out(
                    Transition.CONTINUE, active_id,
                    "stick_active_weak_near_miss", "extend_continue",
                )
            return _out(
                Transition.CLARIFY, None,
                "clarify_near_miss_threads", "near_miss_clarify",
            )
        if ev.winner_id and (
            gate_task_id != ev.winner_id
            or gate_transition in (Transition.NEW, Transition.CLARIFY)
        ):
            return _out(
                _bind_transition(active_id, ev.winner_id),
                ev.winner_id,
                "discriminate_near_miss_resolve",
                "near_miss_resolve",
            )
        ev.region = "near_miss_resolve"
        return None

    # Gate CLARIFY without high-confusion still hops if identity is recoverable
    # (entity/slot unique). Otherwise keep the ask.
    if gate_transition == Transition.CLARIFY and ev.winner_id:
        best_d = scores[ev.winner_id].distinctive if ev.winner_id in scores else 0.0
        if ev.delta_I >= EPS_DELTA and best_d >= TAU_ID_ABS:
            return _out(
                _bind_transition(active_id, ev.winner_id),
                ev.winner_id,
                "discriminate_resolve_gate_clarify",
                "near_miss_resolve",
            )
        ev.region = "near_miss_clarify"
        return None

    # --- 2. Underspecified → CONTINUE ACTIVE unless identity is recoverable ---
    # Thin "what's the TTL?" / "confirm the color" must hop when a unique
    # slot/entity is on a rival. Blind ACTIVE stick is wrong L1.
    if underspecified and active_id:
        # "no, the other one" is a referent correction — do not undo the hop.
        if classify_utterance(message) == "correction":
            ev.region = "keep_gate"
            return None
        best_d = scores[ev.winner_id].distinctive if ev.winner_id in scores else 0.0
        if (
            ev.winner_id
            and ev.winner_id != active_id
            and ev.delta_I >= EPS_DELTA
            and best_d >= TAU_ID_ABS
        ):
            return _out(
                _bind_transition(active_id, ev.winner_id),
                ev.winner_id,
                "discriminate_underspecified_identity",
                "near_miss_resolve",
            )
        if gate_transition in (Transition.NEW, Transition.CLARIFY) or (
            gate_task_id and gate_task_id != active_id
        ):
            return _out(
                Transition.CONTINUE, active_id,
                "stick_underspecified_new", "underspecified_continue",
            )
        if gate_transition != Transition.NEW:
            ev.region = "underspecified_continue"
            return None

    # --- 3. Extension / same-saga stick (incl. spurious NEW) ---
    if active_id and stick_active_extension(message, active_id, scores):
        if gate_transition == Transition.NEW or (
            gate_task_id and gate_task_id != active_id
            and prefer_distinctive(scores, gate_task_id) == active_id
        ):
            return _out(
                Transition.CONTINUE, active_id,
                "stick_active_extension", "extend_continue",
            )
        if gate_task_id == active_id:
            ev.region = "extend_continue"
            return None

    # Distinctive steal outside explicit confusion (still identity-first)
    dist_steal = prefer_distinctive(scores, gate_task_id)
    if (
        dist_steal
        and gate_task_id
        and dist_steal != gate_task_id
        and not underspecified
        and scores[dist_steal].distinctive >= 0.10
        and gate_transition not in (Transition.CLARIFY,)
    ):
        return _out(
            _bind_transition(active_id, dist_steal),
            dist_steal,
            "discriminate_steal_distinctive",
            "near_miss_resolve",
        )

    # NEW with distinctive ACTIVE
    if gate_transition == Transition.NEW and active_id:
        pick = prefer_distinctive(scores, None)
        if pick == active_id and scores[active_id].distinctive >= 0.08:
            return _out(
                Transition.CONTINUE, active_id,
                "stick_distinctive_new", "extend_continue",
            )
        return None  # allow true NEW from gate

    if gate_transition in (Transition.CLARIFY, Transition.NEW):
        return None
    if not gate_task_id:
        return None

    selected = scores[gate_task_id].overlap if gate_task_id in scores else 0.0
    others = [(tid, s.overlap) for tid, s in scores.items() if tid != gate_task_id]
    best_other_id, best_other = (None, 0.0)
    if others:
        best_other_id, best_other = max(others, key=lambda x: x[1])

    # --- 4. True NEW: weak identity and overlap ---
    max_d = max(s.distinctive for s in scores.values())
    max_o = max(s.overlap for s in scores.values())
    if (
        selected < ACCEPT_MIN_O
        and not underspecified
        and max_d < TAU_NEW_D
        and max_o < TAU_NEW_O
    ):
        return _out(Transition.NEW, None, "force_new_topic_mismatch", "true_new")

    if selected < ACCEPT_MIN_O and not underspecified:
        # Genre mismatch but some identity somewhere → prefer steal/overlap
        if (
            best_other_id
            and best_other >= ACCEPT_MIN_O
            and best_other >= selected + STEAL_MARGIN_O
        ):
            return _out(
                _bind_transition(active_id, best_other_id),
                best_other_id,
                "steal_better_workstream",
                "overlap_steal",
            )
        return _out(Transition.NEW, None, "force_new_topic_mismatch", "true_new")

    # Overlap steal when selected weak
    if selected < KEEP_MIN_O and best_other_id and best_other >= ACCEPT_MIN_O:
        if best_other >= selected + STEAL_MARGIN_O and not underspecified:
            return _out(
                _bind_transition(active_id, best_other_id),
                best_other_id,
                "steal_better_workstream",
                "overlap_steal",
            )

    # --- 5. Keep gate ---
    ev.region = "keep_gate"
    return None
