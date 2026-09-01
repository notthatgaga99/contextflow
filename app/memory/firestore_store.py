"""Firestore-backed MemoryStore. Persistence only — not a router.

Uses Application Default Credentials. Optional dependency:
`google-cloud-firestore`. Local tests inject FakeFirestoreClient.
"""

from __future__ import annotations

from typing import Any, Optional

from app.models.memory import ITEM_KINDS, ITEM_PROPOSERS, ITEM_STATUSES, MemoryItem
from app.memory.store import DuplicateTurnError, StaleNamespaceError


class StorageError(RuntimeError):
    """Explicit Firestore / storage failure. Never silent."""


def _item_to_doc(item: MemoryItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "kind": item.kind,
        "text": item.text,
        "source_turn": int(item.source_turn),
        "workstream_id": item.workstream_id,
        "referent_id": item.referent_id,
        "status": item.status,
        "valid_from_turn": item.valid_from_turn,
        "valid_to_turn": item.valid_to_turn,
        "superseded_by": item.superseded_by,
        "proposer": item.proposer,
        "proposal_confidence": float(item.proposal_confidence or 0.0),
        "version": int(item.version or 1),
        "slot": item.slot,
        "conversation_id": item.conversation_id,
        "provenance": item.provenance,
        "uncertain": bool(item.uncertain),
        "idempotency_key": item.idempotency_key,
    }


def _doc_to_item(data: dict[str, Any] | None, *, conversation_id: str) -> MemoryItem:
    if not data or not isinstance(data, dict):
        raise StorageError("malformed_memory_document")
    try:
        kind = str(data.get("kind") or "")
        status = str(data.get("status") or "asserted")
        proposer = str(data.get("proposer") or "system")
        if kind not in ITEM_KINDS:
            raise StorageError(f"invalid_kind:{kind}")
        if status not in ITEM_STATUSES:
            raise StorageError(f"invalid_status:{status}")
        if proposer not in ITEM_PROPOSERS:
            raise StorageError(f"invalid_proposer:{proposer}")
        cid = (data.get("conversation_id") or "").strip()
        if cid and cid != conversation_id:
            raise StorageError("conversation_id_mismatch")
        item_id = str(data.get("id") or "")
        if not item_id:
            raise StorageError("missing_item_id")
        return MemoryItem(
            id=item_id,
            kind=kind,
            text=str(data.get("text") or ""),
            source_turn=int(data["source_turn"]),
            workstream_id=data.get("workstream_id"),
            referent_id=data.get("referent_id"),
            status=status,
            valid_from_turn=data.get("valid_from_turn"),
            valid_to_turn=data.get("valid_to_turn"),
            superseded_by=data.get("superseded_by"),
            proposer=proposer,
            proposal_confidence=float(data.get("proposal_confidence") or 0.0),
            version=int(data.get("version") or 1),
            slot=data.get("slot"),
            conversation_id=conversation_id,
            provenance=data.get("provenance"),
            uncertain=bool(data.get("uncertain") or False),
            idempotency_key=data.get("idempotency_key"),
        )
    except StorageError:
        raise
    except Exception as exc:
        raise StorageError(f"malformed_memory_document:{exc}") from exc


class FirestoreMemoryStore:
    """Conversation-scoped durable MemoryStore.

    Path: conversations/{conversation_id}/memory/{item_id}
    Meta: conversations/{conversation_id}/meta/namespace
    Keys: conversations/{conversation_id}/idempotency/{key}
    """

    def __init__(
        self,
        conversation_id: str,
        *,
        client: Any | None = None,
        project: str | None = None,
        database: str | None = None,
    ) -> None:
        cid = (conversation_id or "").strip()
        if not cid:
            raise ValueError("conversation_id_required")
        self.conversation_id = cid
        self._client = client
        self._project = project
        self._database = database or "(default)"
        if self._client is None:
            self._client = self._make_client()
        self._reads = 0
        self._writes = 0

    def _make_client(self) -> Any:
        try:
            from google.cloud import firestore  # type: ignore
        except ImportError as exc:
            raise StorageError(
                "google-cloud-firestore not installed; pip install google-cloud-firestore"
            ) from exc
        try:
            if self._project:
                return firestore.Client(project=self._project, database=self._database)
            return firestore.Client(database=self._database)
        except Exception as exc:
            raise StorageError(f"firestore_client_init_failed:{exc}") from exc

    def _conv_ref(self) -> Any:
        return self._client.collection("conversations").document(self.conversation_id)

    def _meta_ref(self) -> Any:
        return self._conv_ref().collection("meta").document("namespace")

    def _mem_col(self) -> Any:
        return self._conv_ref().collection("memory")

    def _key_col(self) -> Any:
        return self._conv_ref().collection("idempotency")

    def _load_meta(self) -> dict[str, Any]:
        try:
            self._reads += 1
            snap = self._meta_ref().get()
            if not snap.exists:
                return {
                    "version": 0,
                    "last_turn": None,
                    "last_item_ids": [],
                    "last_keys": [],
                }
            data = snap.to_dict() or {}
            return {
                "version": int(data.get("version") or 0),
                "last_turn": data.get("last_turn"),
                "last_item_ids": list(data.get("last_item_ids") or []),
                "last_keys": list(data.get("last_keys") or []),
            }
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"firestore_meta_read_failed:{exc}") from exc

    def namespace_version(self) -> int:
        return int(self._load_meta()["version"])

    def last_committed_turn(self) -> Optional[int]:
        lt = self._load_meta().get("last_turn")
        return int(lt) if lt is not None else None

    def get(self, item_id: str) -> MemoryItem | None:
        try:
            self._reads += 1
            snap = self._mem_col().document(item_id).get()
            if not snap.exists:
                return None
            return _doc_to_item(snap.to_dict(), conversation_id=self.conversation_id)
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"firestore_get_failed:{exc}") from exc

    def get_by_idempotency_key(self, key: str) -> MemoryItem | None:
        if not key:
            return None
        try:
            self._reads += 1
            snap = self._key_col().document(key).get()
            if not snap.exists:
                return None
            data = snap.to_dict() or {}
            iid = data.get("item_id")
            if not iid:
                raise StorageError("malformed_idempotency_document")
            return self.get(str(iid))
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"firestore_idempotency_lookup_failed:{exc}") from exc

    def all(self) -> list[MemoryItem]:
        try:
            self._reads += 1
            out = []
            for snap in self._mem_col().stream():
                out.append(
                    _doc_to_item(snap.to_dict(), conversation_id=self.conversation_id)
                )
            return out
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"firestore_list_failed:{exc}") from exc

    def asserted(self, workstream_id: str | None = None) -> list[MemoryItem]:
        out = [i for i in self.all() if i.status == "asserted"]
        if workstream_id is None:
            return out
        return [i for i in out if i.workstream_id == workstream_id]

    def historical(self, workstream_id: str | None = None) -> list[MemoryItem]:
        out = self.all()
        if workstream_id is None:
            return out
        return [i for i in out if i.workstream_id == workstream_id]

    def commit(
        self,
        items: list[MemoryItem],
        expected_version: int,
        turn: int,
    ) -> int:
        for item in items:
            if item.conversation_id and item.conversation_id.strip() != self.conversation_id:
                raise ValueError("conversation_id_mismatch")
            if not item.conversation_id:
                item.conversation_id = self.conversation_id

        meta = self._load_meta()
        version = int(meta["version"])
        if expected_version != version:
            raise StaleNamespaceError(
                f"expected_version={expected_version} actual={version}"
            )

        new_ids = [i.id for i in items]
        new_keys = [i.idempotency_key or i.id for i in items]
        last_turn = meta.get("last_turn")
        if last_turn is not None and int(last_turn) == int(turn):
            if (
                new_ids == list(meta.get("last_item_ids") or [])
                or new_keys == list(meta.get("last_keys") or [])
            ):
                return version
            raise DuplicateTurnError(f"turn {turn} already committed")

        try:
            # Batch write: items + idempotency + meta. Fail closed on any error.
            batch = self._client.batch()
            for item in items:
                batch.set(self._mem_col().document(item.id), _item_to_doc(item))
                self._writes += 1
                if item.idempotency_key:
                    batch.set(
                        self._key_col().document(item.idempotency_key),
                        {"item_id": item.id, "conversation_id": self.conversation_id},
                    )
                    self._writes += 1
            new_version = version + 1
            batch.set(
                self._meta_ref(),
                {
                    "version": new_version,
                    "last_turn": int(turn),
                    "last_item_ids": new_ids,
                    "last_keys": new_keys,
                    "conversation_id": self.conversation_id,
                },
            )
            self._writes += 1
            batch.commit()
            return new_version
        except (StaleNamespaceError, DuplicateTurnError, ValueError):
            raise
        except Exception as exc:
            raise StorageError(f"firestore_commit_failed:{exc}") from exc

    def stats(self) -> dict[str, int]:
        return {"memory_reads": self._reads, "memory_writes": self._writes}
