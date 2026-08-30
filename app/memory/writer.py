"""MemoryWriter: propose → validate → commit. Never called from LLM.generate()."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.memory.store import DuplicateTurnError, MemoryStore, StaleNamespaceError
from app.models.memory import (
    ITEM_KINDS,
    ITEM_PROPOSERS,
    MemoryItem,
    MemoryPatch,
    patch_from_dict,
)
from app.router.referent import loop_index_from_id


@dataclass
class WriterResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    items: list[MemoryItem] = field(default_factory=list)
    namespace_version: int | None = None
    idempotent_retry: bool = False


def _referent_ok(registry, workstream_id: str, referent_id: str) -> bool:
    task = registry.get(workstream_id)
    if task is None:
        return False
    if referent_id == workstream_id:
        return True
    idx = loop_index_from_id(workstream_id, referent_id)
    if idx is None:
        return False
    return 0 <= idx < len(task.anchor.open_loops)


class MemoryWriter:
    def __init__(self, store: MemoryStore, registry):
        self.store = store
        self.registry = registry
        self._seq = 0

    def propose(self, patches: list[dict] | list[MemoryPatch] | None = None) -> list[MemoryPatch]:
        """Soft proposals only. Does not write."""
        if not patches:
            return []
        out: list[MemoryPatch] = []
        for p in patches:
            out.append(p if isinstance(p, MemoryPatch) else patch_from_dict(p))
        return out

    def validate(self, patches: list[MemoryPatch]) -> WriterResult:
        errors: list[str] = []
        for i, p in enumerate(patches):
            prefix = f"patch[{i}]"
            if p.source_turn < 0:
                errors.append(f"{prefix}: missing provenance source_turn")
            if p.kind not in ITEM_KINDS:
                errors.append(f"{prefix}: invalid kind {p.kind!r}")
            if p.proposer not in ITEM_PROPOSERS:
                errors.append(f"{prefix}: invalid proposer {p.proposer!r}")
            if p.action not in ("assert", "retract", "abandon"):
                errors.append(f"{prefix}: invalid action {p.action!r}")
            if p.uncertain:
                errors.append(f"{prefix}: uncertain patch rejected (not active memory)")
            if p.action == "assert" and not (p.text or "").strip():
                errors.append(f"{prefix}: empty text")
            if p.action == "abandon":
                if not p.workstream_id:
                    errors.append(f"{prefix}: abandon requires workstream_id")
                continue
            if p.workstream_id:
                if self.registry.get(p.workstream_id) is None:
                    errors.append(f"{prefix}: unknown workstream {p.workstream_id}")
            if p.referent_id:
                if not p.workstream_id:
                    errors.append(f"{prefix}: referent without workstream")
                elif p.workstream_id and self.registry.get(p.workstream_id) is not None:
                    if not _referent_ok(self.registry, p.workstream_id, p.referent_id):
                        errors.append(f"{prefix}: unknown referent {p.referent_id}")
            if p.action == "retract":
                rid = p.retract_id
                if not rid or self.store.get(rid) is None:
                    errors.append(f"{prefix}: retract unknown id")
            if p.supersedes_id and self.store.get(p.supersedes_id) is None:
                errors.append(f"{prefix}: unknown supersedes_id")
        return WriterResult(ok=not errors, errors=errors)

    def _next_id(self) -> str:
        self._seq += 1
        return f"M{self._seq}"

    def _slot_peer_kinds(self, kind: str) -> frozenset[str]:
        if kind in ("decision", "correction"):
            return frozenset({"decision", "correction"})
        return frozenset({kind})

    def _supersede_target(self, p: MemoryPatch) -> MemoryItem | None:
        if p.supersedes_id:
            return self.store.get(p.supersedes_id)
        if p.slot and p.action == "assert":
            peers = self._slot_peer_kinds(p.kind)
            for item in self.store.asserted(p.workstream_id):
                if (
                    item.kind in peers
                    and item.slot == p.slot
                    and item.workstream_id == p.workstream_id
                    and item.referent_id == p.referent_id
                    and item.status == "asserted"
                ):
                    return item
        return None

    def commit(
        self,
        patches: list[MemoryPatch],
        expected_version: int | None = None,
        turn: int | None = None,
    ) -> WriterResult:
        checked = self.validate(patches)
        if not checked.ok:
            return checked
        exp = self.store.namespace_version() if expected_version is None else expected_version
        turn_n = patches[0].source_turn if patches else (turn or 0)
        if turn is not None:
            turn_n = turn
        if getattr(self.store, "last_committed_turn", lambda: None)() == turn_n:
            found = []
            for p in patches:
                key = p.idempotency_key or p.identity_key()
                hit = self.store.get_by_idempotency_key(key)
                if hit is None:
                    found = []
                    break
                found.append(hit)
            if found and len(found) == len(patches):
                return WriterResult(
                    ok=True,
                    items=found,
                    namespace_version=self.store.namespace_version(),
                    idempotent_retry=True,
                )
        batch: list[MemoryItem] = []
        for p in patches:
            if p.action == "abandon":
                task = self.registry.get(p.workstream_id)
                if task is None:
                    return WriterResult(ok=False, errors=["abandon unknown workstream"])
                self.registry.mark_abandoned(p.workstream_id)
                continue
            if p.action == "retract":
                old = self.store.get(p.retract_id)
                if old is None:
                    return WriterResult(ok=False, errors=["retract vanished"])
                updated = MemoryItem(**{**old.to_dict(), "status": "retracted",
                                        "valid_to_turn": p.source_turn,
                                        "version": old.version + 1})
                batch.append(updated)
                continue
            target = self._supersede_target(p)
            if (
                p.action == "assert"
                and not p.slot
                and not p.supersedes_id
                and p.kind == "decision"
            ):
                # Unkeyed decision contradiction: do not invent a winner.
                pass
            new_id = p.id or self._next_id()
            key = p.idempotency_key or p.identity_key()
            p.idempotency_key = key
            prior = self.store.get_by_idempotency_key(key)
            if prior is not None:
                new_id = prior.id
            cid = p.conversation_id or getattr(self.store, "conversation_id", "") or None
            provenance = p.provenance or (
                f"conversation:{cid or ''}:turn:{p.source_turn}:proposer:{p.proposer}"
            )
            new = MemoryItem(
                id=new_id,
                kind=p.kind,
                text=p.text.strip(),
                source_turn=p.source_turn,
                workstream_id=p.workstream_id,
                referent_id=p.referent_id,
                status="asserted",
                valid_from_turn=p.source_turn,
                proposer=p.proposer,
                proposal_confidence=p.proposal_confidence,
                slot=p.slot,
                conversation_id=cid,
                provenance=provenance,
                uncertain=p.uncertain,
                idempotency_key=key,
            )
            if target is not None:
                if p.supersedes_id and target.kind not in self._slot_peer_kinds(p.kind):
                    return WriterResult(ok=False, errors=["supersede kind mismatch"])
                batch.append(MemoryItem(**{**target.to_dict(),
                                           "status": "superseded",
                                           "superseded_by": new_id,
                                           "valid_to_turn": p.source_turn,
                                           "version": target.version + 1}))
            elif p.kind == "decision" and not p.slot and not p.supersedes_id:
                rivals = [
                    i for i in self.store.asserted(p.workstream_id)
                    if i.kind == "decision" and i.referent_id == p.referent_id and not i.slot
                ]
                if rivals:
                    return WriterResult(
                        ok=False,
                        errors=["unresolved_decision_conflict: no slot or supersedes_id"],
                        namespace_version=self.store.namespace_version(),
                    )
            batch.append(new)
        try:
            ver = self.store.commit(batch, expected_version=exp, turn=turn_n)
        except StaleNamespaceError as exc:
            return WriterResult(ok=False, errors=[str(exc)])
        except DuplicateTurnError as exc:
            return WriterResult(ok=False, errors=[str(exc)])
        retried = (
            getattr(self.store, "last_committed_turn", lambda: None)() == turn_n
            and ver == exp
        )
        if not retried:
            for item in batch:
                if item.workstream_id and item.status == "asserted":
                    task = self.registry.get(item.workstream_id)
                    if task is not None and item.id not in task.item_ids:
                        task.item_ids.append(item.id)
        return WriterResult(
            ok=True, items=batch, namespace_version=ver, idempotent_retry=retried,
        )
