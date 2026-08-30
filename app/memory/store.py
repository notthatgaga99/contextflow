"""In-memory MemoryStore. Not Firestore. Optimistic namespace versioning only.

Namespaced by conversation_id on the store instance (one store per conversation).
Idempotent retry: same turn + same idempotency keys does not duplicate items.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from app.models.memory import MemoryItem


class StaleNamespaceError(ValueError):
    pass


class DuplicateTurnError(ValueError):
    """Same turn already committed with different content; identical retry is idempotent."""


@runtime_checkable
class MemoryStore(Protocol):
    conversation_id: str
    def namespace_version(self) -> int: ...
    def get(self, item_id: str) -> MemoryItem | None: ...
    def get_by_idempotency_key(self, key: str) -> MemoryItem | None: ...
    def all(self) -> list[MemoryItem]: ...
    def asserted(self, workstream_id: str | None = None) -> list[MemoryItem]: ...
    def historical(self, workstream_id: str | None = None) -> list[MemoryItem]: ...
    def commit(
        self,
        items: list[MemoryItem],
        expected_version: int,
        turn: int,
    ) -> int: ...


class InMemoryMemoryStore:
    def __init__(self, conversation_id: str = "") -> None:
        self.conversation_id = (conversation_id or "").strip()
        self._items: dict[str, MemoryItem] = {}
        self._by_key: dict[str, str] = {}
        self._version = 0
        self._last_turn: Optional[int] = None
        self._last_item_ids: tuple[str, ...] = ()
        self._last_keys: tuple[str, ...] = ()

    def namespace_version(self) -> int:
        return self._version

    def last_committed_turn(self) -> Optional[int]:
        return self._last_turn

    def get(self, item_id: str) -> MemoryItem | None:
        return self._items.get(item_id)

    def get_by_idempotency_key(self, key: str) -> MemoryItem | None:
        iid = self._by_key.get(key)
        return self._items.get(iid) if iid else None

    def all(self) -> list[MemoryItem]:
        return list(self._items.values())

    def asserted(self, workstream_id: str | None = None) -> list[MemoryItem]:
        out = [i for i in self._items.values() if i.status == "asserted"]
        if workstream_id is None:
            return out
        return [i for i in out if i.workstream_id == workstream_id]

    def historical(self, workstream_id: str | None = None) -> list[MemoryItem]:
        """All statuses, including superseded/retracted. Working set must not use this."""
        out = list(self._items.values())
        if workstream_id is None:
            return out
        return [i for i in out if i.workstream_id == workstream_id]

    def commit(self, items: list[MemoryItem], expected_version: int, turn: int) -> int:
        if expected_version != self._version:
            raise StaleNamespaceError(
                f"expected_version={expected_version} actual={self._version}"
            )
        for item in items:
            if self.conversation_id and item.conversation_id and (
                item.conversation_id.strip() != self.conversation_id
            ):
                raise ValueError("conversation_id_mismatch")
            if self.conversation_id and not item.conversation_id:
                item.conversation_id = self.conversation_id
        new_ids = tuple(i.id for i in items)
        new_keys = tuple(i.idempotency_key or i.id for i in items)
        if self._last_turn == turn:
            if new_ids == self._last_item_ids or new_keys == self._last_keys:
                return self._version
            raise DuplicateTurnError(f"turn {turn} already committed")
        for item in items:
            self._items[item.id] = item
            if item.idempotency_key:
                self._by_key[item.idempotency_key] = item.id
        self._version += 1
        self._last_turn = turn
        self._last_item_ids = new_ids
        self._last_keys = new_keys
        return self._version
