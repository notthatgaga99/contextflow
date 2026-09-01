"""In-process Fake Firestore for deterministic unit tests (no emulator required)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class _Snap:
    def __init__(self, data: dict[str, Any] | None, exists: bool):
        self._data = data
        self.exists = exists

    def to_dict(self) -> dict[str, Any] | None:
        return deepcopy(self._data) if self._data is not None else None


class _DocRef:
    def __init__(self, store: "FakeFirestoreClient", path: tuple[str, ...]):
        self._store = store
        self._path = path

    def collection(self, name: str) -> "_ColRef":
        return _ColRef(self._store, self._path + (name,))

    def get(self) -> _Snap:
        key = "/".join(self._path)
        if key in self._store._docs:
            return _Snap(self._store._docs[key], True)
        return _Snap(None, False)

    def set(self, data: dict[str, Any]) -> None:
        self._store._docs["/".join(self._path)] = deepcopy(data)


class _ColRef:
    def __init__(self, store: "FakeFirestoreClient", path: tuple[str, ...]):
        self._store = store
        self._path = path

    def document(self, doc_id: str) -> _DocRef:
        return _DocRef(self._store, self._path + (doc_id,))

    def stream(self):
        prefix = "/".join(self._path) + "/"
        for key, data in list(self._store._docs.items()):
            if key.startswith(prefix):
                rest = key[len(prefix):]
                if "/" not in rest:
                    yield _Snap(data, True)


class _Batch:
    def __init__(self, store: "FakeFirestoreClient"):
        self._store = store
        self._ops: list[tuple[str, dict[str, Any]]] = []

    def set(self, ref: _DocRef, data: dict[str, Any]) -> None:
        self._ops.append(("/".join(ref._path), deepcopy(data)))

    def commit(self) -> None:
        if getattr(self._store, "fail_commits", False):
            raise RuntimeError("simulated_firestore_failure")
        for key, data in self._ops:
            self._store._docs[key] = data


class FakeFirestoreClient:
    """Minimal Client/batch/collection surface for FirestoreMemoryStore tests."""

    def __init__(self) -> None:
        self._docs: dict[str, dict[str, Any]] = {}
        self.fail_commits = False

    def collection(self, name: str) -> _ColRef:
        return _ColRef(self, (name,))

    def batch(self) -> _Batch:
        return _Batch(self)
