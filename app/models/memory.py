from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Optional

ITEM_KINDS = frozenset({
    "fact", "decision", "constraint", "entity", "preference", "event", "correction",
})
ITEM_STATUSES = frozenset({"asserted", "superseded", "retracted"})
ITEM_PROPOSERS = frozenset({"user", "extractor", "system"})


def patch_idempotency_key(
    conversation_id: str | None,
    source_turn: int,
    kind: str,
    action: str,
    text: str,
    *,
    slot: str | None = None,
    workstream_id: str | None = None,
    referent_id: str | None = None,
    retract_id: str | None = None,
    supersedes_id: str | None = None,
) -> str:
    """Stable identity for retry: conversation + turn + patch identity. Not a routing key."""
    raw = "|".join([
        (conversation_id or "").strip(),
        str(int(source_turn)),
        kind or "",
        action or "assert",
        (slot or ""),
        (workstream_id or ""),
        (referent_id or ""),
        (text or "").strip().lower(),
        retract_id or "",
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


@dataclass
class MemoryItem:
    """Canonical remembered assertion. `text` is the content.

    Answers: what was established, for which workstream, when, and whether
    it has since been superseded or retracted.
    """
    id: str
    kind: str
    text: str
    source_turn: int
    workstream_id: Optional[str] = None
    referent_id: Optional[str] = None
    status: str = "asserted"
    valid_from_turn: Optional[int] = None
    valid_to_turn: Optional[int] = None
    superseded_by: Optional[str] = None
    proposer: str = "system"
    proposal_confidence: float = 0.0
    version: int = 1
    slot: Optional[str] = None
    conversation_id: Optional[str] = None
    provenance: Optional[str] = None
    uncertain: bool = False
    idempotency_key: Optional[str] = None

    @property
    def content(self) -> str:
        return self.text

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MemoryPatch:
    """Writer proposal. Not canonical until validate + commit."""
    kind: str
    text: str
    source_turn: int
    workstream_id: Optional[str] = None
    referent_id: Optional[str] = None
    slot: Optional[str] = None
    supersedes_id: Optional[str] = None
    retract_id: Optional[str] = None
    action: str = "assert"  # assert | retract
    proposer: str = "extractor"
    proposal_confidence: float = 0.0
    id: Optional[str] = None
    conversation_id: Optional[str] = None
    provenance: Optional[str] = None
    uncertain: bool = False
    idempotency_key: Optional[str] = None

    @property
    def content(self) -> str:
        return self.text

    def identity_key(self) -> str:
        return patch_idempotency_key(
            self.conversation_id, self.source_turn, self.kind, self.action, self.text,
            slot=self.slot, workstream_id=self.workstream_id, referent_id=self.referent_id,
            retract_id=self.retract_id,
        )

    def to_dict(self) -> dict:
        return asdict(self)


def patch_from_dict(raw: dict) -> MemoryPatch:
    text = str(raw.get("text") or raw.get("content") or "")
    return MemoryPatch(
        kind=str(raw.get("kind") or ""),
        text=text,
        source_turn=int(raw["source_turn"]) if raw.get("source_turn") is not None else -1,
        workstream_id=raw.get("workstream_id"),
        referent_id=raw.get("referent_id"),
        slot=raw.get("slot"),
        supersedes_id=raw.get("supersedes_id"),
        retract_id=raw.get("retract_id"),
        action=str(raw.get("action") or "assert"),
        proposer=str(raw.get("proposer") or "extractor"),
        proposal_confidence=float(raw.get("proposal_confidence") or 0.0),
        id=raw.get("id"),
        conversation_id=raw.get("conversation_id"),
        provenance=raw.get("provenance"),
        uncertain=bool(raw.get("uncertain") or False),
        idempotency_key=raw.get("idempotency_key"),
    )
