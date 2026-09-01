"""Firestore-backed workstream registry. Persistence only — not a router.

Path: conversations/{conversation_id}/workstreams/{workstream_id}
Meta: conversations/{conversation_id}/meta/registry
"""

from __future__ import annotations

import time
from typing import Any, Optional

from app.memory.firestore_store import StorageError
from app.models.task import Task, TaskAnchor
from app.router.referent import ensure_loop_clocks, loop_index_from_id


VALID_STATUSES = frozenset({"active", "paused", "resolved", "abandoned"})


def _anchor_to_doc(anchor: TaskAnchor) -> dict[str, Any]:
    return {
        "goal": anchor.goal,
        "current_state": anchor.current_state,
        "decisions": list(anchor.decisions),
        "constraints": list(anchor.constraints),
        "open_loops": list(anchor.open_loops),
        "entities": list(anchor.entities),
    }


def _anchor_from_doc(data: dict[str, Any] | None) -> TaskAnchor:
    if not data:
        return TaskAnchor()
    return TaskAnchor(
        goal=str(data.get("goal") or ""),
        current_state=str(data.get("current_state") or ""),
        decisions=list(data.get("decisions") or []),
        constraints=list(data.get("constraints") or []),
        open_loops=list(data.get("open_loops") or []),
        entities=list(data.get("entities") or []),
    )


def _task_to_doc(task: Task, *, conversation_id: str, version: int) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "retrieval_cues": list(task.retrieval_cues),
        "item_ids": list(task.item_ids),
        "anchor": _anchor_to_doc(task.anchor),
        "last_active_turn": int(task.last_active_turn),
        "mention_turn": int(task.mention_turn),
        "loop_mention_turns": list(task.loop_mention_turns),
        "created_at": float(task.created_at or 0.0),
        "updated_at": float(task.updated_at or 0.0),
        "conversation_id": conversation_id,
        "version": int(version),
    }


def _doc_to_task(data: dict[str, Any] | None, *, conversation_id: str) -> Task:
    if not data or not isinstance(data, dict):
        raise StorageError("malformed_workstream_document")
    try:
        wid = str(data.get("id") or "")
        if not wid:
            raise StorageError("missing_workstream_id")
        cid = (data.get("conversation_id") or "").strip()
        if cid and cid != conversation_id:
            raise StorageError("conversation_id_mismatch")
        status = str(data.get("status") or "active")
        if status not in VALID_STATUSES:
            raise StorageError(f"invalid_workstream_status:{status}")
        task = Task(
            id=wid,
            title=str(data.get("title") or ""),
            status=status,
            retrieval_cues=list(data.get("retrieval_cues") or []),
            item_ids=list(data.get("item_ids") or []),
            anchor=_anchor_from_doc(data.get("anchor")),
            last_active_turn=int(data.get("last_active_turn") or 0),
            mention_turn=int(data.get("mention_turn") or 0),
            loop_mention_turns=list(data.get("loop_mention_turns") or []),
            created_at=float(data.get("created_at") or 0.0),
            updated_at=float(data.get("updated_at") or 0.0),
        )
        ensure_loop_clocks(task)
        return task
    except StorageError:
        raise
    except Exception as exc:
        raise StorageError(f"malformed_workstream_document:{exc}") from exc


class FirestoreRegistry:
    """Conversation-scoped durable workstream registry."""

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
        self._tasks: dict[str, Task] = {}
        self._versions: dict[str, int] = {}
        self._last_selected_referent: Optional[str] = None
        self._reads = 0
        self._writes = 0
        self._load_all()

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

    def _ws_col(self) -> Any:
        return self._conv_ref().collection("workstreams")

    def _meta_ref(self) -> Any:
        return self._conv_ref().collection("meta").document("registry")

    def _load_all(self) -> None:
        try:
            self._reads += 1
            for snap in self._ws_col().stream():
                task = _doc_to_task(snap.to_dict(), conversation_id=self.conversation_id)
                self._tasks[task.id] = task
                ver = int((snap.to_dict() or {}).get("version") or 1)
                self._versions[task.id] = ver
            self._reads += 1
            meta = self._meta_ref().get()
            if meta.exists:
                data = meta.to_dict() or {}
                self._last_selected_referent = data.get("last_selected_referent")
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"firestore_registry_load_failed:{exc}") from exc

    def _persist_task(self, task: Task) -> None:
        ver = self._versions.get(task.id, 1)
        try:
            self._writes += 1
            self._ws_col().document(task.id).set(
                _task_to_doc(task, conversation_id=self.conversation_id, version=ver)
            )
            self._persist_meta()
        except Exception as exc:
            raise StorageError(f"firestore_registry_write_failed:{exc}") from exc

    def _persist_meta(self) -> None:
        try:
            self._writes += 1
            self._meta_ref().set({
                "conversation_id": self.conversation_id,
                "last_selected_referent": self._last_selected_referent,
                "workstream_count": len(self._tasks),
            })
        except Exception as exc:
            raise StorageError(f"firestore_registry_meta_write_failed:{exc}") from exc

    def stats(self) -> dict[str, int]:
        return {
            "registry_reads": self._reads,
            "registry_writes": self._writes,
            "workstream_count": len(self._tasks),
        }

    def add(self, t: Task, *, idempotency_key: str | None = None) -> None:
        existing = self._tasks.get(t.id)
        if existing is not None:
            if (
                existing.title == t.title
                and existing.status == t.status
                and existing.anchor.goal == t.anchor.goal
            ):
                return  # idempotent create
            raise StorageError(f"workstream_exists:{t.id}")
        now = time.time()
        if not t.created_at:
            t.created_at = now
        t.updated_at = now
        self._tasks[t.id] = t
        self._versions.setdefault(t.id, 1)
        ensure_loop_clocks(t)
        self._persist_task(t)

    def get(self, id: str) -> Task | None:
        return self._tasks.get(id)

    def all(self) -> list[Task]:
        return list(self._tasks.values())

    def open_tasks(self) -> list[Task]:
        return [t for t in self._tasks.values() if t.status in ("active", "paused")]

    def mark_abandoned(self, task_id: str) -> None:
        t = self._tasks.get(task_id)
        if t is not None:
            t.status = "abandoned"
            t.updated_at = time.time()
            self._versions[task_id] = self._versions.get(task_id, 1) + 1
            self._persist_task(t)

    def active(self) -> Task | None:
        for t in self._tasks.values():
            if t.status == "active":
                return t
        return None

    def mark_active(self, id: str, turn: int) -> None:
        changed: list[Task] = []
        for t in self._tasks.values():
            if t.status == "active" and t.id != id:
                t.status = "paused"
                t.updated_at = time.time()
                self._versions[t.id] = self._versions.get(t.id, 1) + 1
                changed.append(t)
        t = self._tasks[id]
        t.status = "active"
        t.last_active_turn = turn
        t.updated_at = time.time()
        self._versions[id] = self._versions.get(id, 1) + 1
        changed.append(t)
        for task in changed:
            self._persist_task(task)

    def record_mention(self, task_id: str, turn: int, loop_id: Optional[str] = None) -> None:
        t = self._tasks[task_id]
        ensure_loop_clocks(t)
        t.mention_turn = turn
        if loop_id is not None:
            idx = loop_index_from_id(task_id, loop_id)
            if idx is not None and 0 <= idx < len(t.loop_mention_turns):
                t.loop_mention_turns[idx] = turn
        t.updated_at = time.time()
        self._versions[task_id] = self._versions.get(task_id, 1) + 1
        self._persist_task(t)

    def last_selected_referent(self) -> Optional[str]:
        return self._last_selected_referent

    def set_last_selected_referent(self, referent_id: Optional[str]) -> None:
        self._last_selected_referent = referent_id
        self._persist_meta()

    def apply_update(self, id: str, delta: dict) -> None:
        t = self._tasks[id]
        a = t.anchor
        for k in ("decisions", "constraints", "open_loops", "entities"):
            for item in delta.get(k, []):
                if item not in getattr(a, k):
                    getattr(a, k).append(item)
        for loop in delta.get("resolved_loops", []):
            if loop in a.open_loops:
                idx = a.open_loops.index(loop)
                a.open_loops.remove(loop)
                if idx < len(t.loop_mention_turns):
                    t.loop_mention_turns.pop(idx)
        if "goal" in delta:
            a.goal = delta["goal"]
        if "current_state" in delta:
            a.current_state = delta["current_state"]
        added = len(a.open_loops) - len(t.loop_mention_turns)
        if added > 0:
            t.loop_mention_turns.extend([0] * added)
        ensure_loop_clocks(t)
        t.updated_at = time.time()
        self._versions[id] = self._versions.get(id, 1) + 1
        self._persist_task(t)

    def version(self, id: str) -> int:
        return self._versions.get(id, 0)
