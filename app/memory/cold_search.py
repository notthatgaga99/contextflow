"""Real cold recall over memory items (lexical + optional hash embedding).

Used after bind, scoped to one workstream. Not a stub: scores every candidate
item and returns ranked ColdHits. Does not write memory or route.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from app.models.memory import MemoryItem

_TOKEN = re.compile(r"[a-z0-9]{2,}")


@dataclass
class ColdHit:
    """Ranked cold-enrich candidate for the bound workstream."""

    text: str
    workstream_id: str | None = None
    score: float = 0.0
    source: str = "cold"
    item_id: str | None = None
    kind: str | None = None
    status: str | None = None
    slot: str | None = None


def tokenize(text: str) -> set[str]:
    return set(_TOKEN.findall((text or "").lower()))


def lexical_score(query: str, text: str) -> float:
    q = tokenize(query)
    t = tokenize(text)
    if not q or not t:
        return 0.0
    overlap = len(q & t)
    if overlap == 0:
        return 0.0
    # Jaccard-like with slight preference for denser overlap on short facts
    return overlap / len(q | t) + 0.15 * (overlap / len(q))


def _hash_embed(text: str, dim: int = 64) -> np.ndarray:
    """Deterministic bag-of-tokens hash embed (same family as MockLLM)."""
    v = np.zeros(dim, dtype=np.float32)
    for tok in tokenize(text):
        h = hash(tok) % dim
        v[h] += 1.0
    n = float(np.linalg.norm(v))
    if n > 1e-9:
        v /= n
    return v


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(max(0.0, a @ b))


@dataclass
class RankedItem:
    item: MemoryItem
    score: float


def rank_memory_items(
    query: str,
    items: list[MemoryItem],
    *,
    use_embed: bool = True,
    asserted_boost: float = 0.08,
    superseded_scale: float = 0.45,
) -> list[RankedItem]:
    """Rank items for cold recall. Asserted outrank superseded at equal lexical hit."""
    q = (query or "").strip()
    if not q or not items:
        return []
    q_emb = _hash_embed(q) if use_embed else None
    ranked: list[RankedItem] = []
    for item in items:
        text = (item.text or "").strip()
        if not text:
            continue
        lex = lexical_score(q, text)
        emb = cosine(q_emb, _hash_embed(text)) if q_emb is not None else 0.0
        score = 0.7 * lex + 0.3 * emb
        if item.status == "asserted":
            score += asserted_boost
        elif item.status == "superseded":
            score *= superseded_scale
        elif item.status == "retracted":
            continue
        if score <= 1e-9:
            continue
        ranked.append(RankedItem(item=item, score=score))
    ranked.sort(key=lambda r: (r.score, r.item.source_turn, r.item.id), reverse=True)
    return ranked


def hits_from_items(
    query: str,
    items: list[MemoryItem],
    *,
    limit: int = 5,
    workstream_id: str | None = None,
    use_embed: bool = True,
) -> list[ColdHit]:
    pool = items
    if workstream_id:
        wid = workstream_id.strip()
        pool = [i for i in items if (i.workstream_id or "") == wid]
    ranked = rank_memory_items(query, pool, use_embed=use_embed)
    out: list[ColdHit] = []
    seen: set[str] = set()
    for r in ranked:
        key = r.item.text.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            ColdHit(
                text=r.item.text.strip(),
                workstream_id=r.item.workstream_id,
                score=round(r.score, 4),
                source=f"cold:{r.item.status}:{r.item.kind}",
                item_id=r.item.id,
                kind=r.item.kind,
                status=r.item.status,
                slot=r.item.slot,
            )
        )
        if len(out) >= max(0, limit):
            break
    return out


def filter_hits_for_l1(
    hits: list[ColdHit],
    *,
    asserted_slots: set[str] | None = None,
    prefer_asserted_over_superseded: bool = True,
) -> list[ColdHit]:
    """Drop stale superseded hits when CURRENT already owns the slot."""
    slots = {s.strip().lower() for s in (asserted_slots or set()) if s and s.strip()}
    out: list[ColdHit] = []
    for h in hits:
        st = (h.status or "").strip().lower()
        if st == "retracted":
            continue
        if prefer_asserted_over_superseded and st == "superseded":
            slot = (h.slot or "").strip().lower()
            # If slot is known and CURRENT has it, skip stale. Unslotted superseded
            # still allowed as weak recall (lower score already applied upstream).
            if slot and slot in slots:
                continue
        out.append(h)
    return out


def merge_hits_into_facts(
    facts: list[str],
    hits: list[ColdHit],
    *,
    max_facts: int,
    bound_workstream_id: str,
) -> list[str]:
    """Promote query-relevant cold hits into L1 facts; never other workstreams."""
    bound = (bound_workstream_id or "").strip()
    # Re-order: hits that already exist move toward front
    hit_texts = []
    for h in hits:
        if h.workstream_id and (h.workstream_id or "").strip() != bound:
            continue
        t = (h.text or "").strip()
        if not t:
            continue
        hit_texts.append(t)
    ordered: list[str] = []
    seen: set[str] = set()
    for t in hit_texts + list(facts):
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        ordered.append(t)
        if max_facts > 0 and len(ordered) >= max_facts:
            break
    if max_facts <= 0:
        return ordered
    return ordered[:max_facts]


def hit_item_ids(hits: list[ColdHit], merged_facts: list[str]) -> list[str]:
    """Provenance ids for cold texts that actually landed in L1 facts."""
    want = {f.strip().lower() for f in merged_facts}
    ids: list[str] = []
    seen: set[str] = set()
    for h in hits:
        t = (h.text or "").strip().lower()
        iid = (h.item_id or "").strip()
        if not iid or t not in want or iid in seen:
            continue
        seen.add(iid)
        ids.append(iid)
    return ids
