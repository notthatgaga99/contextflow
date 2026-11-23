"""Last-N conversation catalog (horizon H2) with real file persistence.

Best practices:
- Store structured rollups, not full transcripts.
- Cap hot set (default 5).
- Never inject catalog into generate() — UI / opt-in import only.
- Persist to JSON when CF_CATALOG_PATH is set (default: .data/catalog.json).
- Backend: CF_CATALOG_BACKEND=file|firestore (default: follow CF_MEMORY_BACKEND).

Frozen routing / MemoryWriter contracts untouched.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.memory.rollup import ConversationRollup, build_conversation_rollup


def catalog_limit() -> int:
    raw = os.getenv("CF_CATALOG_LIMIT", "5").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 5
    return max(1, min(n, 50))


def catalog_backend() -> str:
    """Resolve catalog storage: file (default) or firestore."""
    raw = (os.getenv("CF_CATALOG_BACKEND", "") or "").strip().lower()
    if raw in ("file", "json", "memory", "firestore"):
        if raw in ("json", "memory"):
            return "file"
        return raw
    mem = (os.getenv("CF_MEMORY_BACKEND", "memory") or "memory").strip().lower()
    return "firestore" if mem == "firestore" else "file"


def create_catalog(*, client=None, **kwargs: Any):
    """Factory: file ConversationCatalog or FirestoreConversationCatalog."""
    kind = catalog_backend()
    if kind == "firestore":
        from app.memory.firestore_catalog import FirestoreConversationCatalog

        return FirestoreConversationCatalog(client=client, **{
            k: v for k, v in kwargs.items()
            if k in ("max_entries", "project", "database", "root_collection")
        })
    # Drop firestore-only kwargs for file catalog.
    file_kwargs = {
        k: v for k, v in kwargs.items()
        if k in ("max_entries", "path", "persist")
    }
    return ConversationCatalog(**file_kwargs)


def default_catalog_path() -> Path:
    raw = os.getenv("CF_CATALOG_PATH", "").strip()
    if raw:
        return Path(raw)
    return Path(os.getenv("CF_DATA_DIR", ".data")).expanduser() / "catalog.json"


def score_catalog_match(entry: "CatalogEntry", query: str) -> float:
    """Lexical soft-match score for Tier C suggest (no import side effects)."""
    q_toks = set(re.findall(r"[a-z0-9]{3,}", (query or "").lower()))
    if not q_toks:
        return 0.0
    parts = [entry.blurb or ""]
    roll = entry.rollup or {}
    for ws in roll.get("workstreams") or []:
        if not isinstance(ws, dict):
            continue
        parts.extend([
            str(ws.get("title") or ""),
            str(ws.get("goal") or ""),
            " ".join(str(x) for x in (ws.get("open_loops") or [])[:4]),
            " ".join(str(x) for x in (ws.get("decisions") or [])[:4]),
            " ".join(str(x) for x in (ws.get("facts") or [])[:4]),
        ])
    blob = " ".join(parts).lower()
    hits = sum(1 for t in q_toks if t in blob)
    return hits / max(len(q_toks), 1)


@dataclass
class CatalogEntry:
    conversation_id: str
    updated_at: float
    blurb: str = ""
    open_count: int = 0
    rollup: dict[str, Any] = field(default_factory=dict)
    user_key: str = "local"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CatalogEntry":
        return cls(
            conversation_id=str(raw.get("conversation_id") or ""),
            updated_at=float(raw.get("updated_at") or 0.0),
            blurb=str(raw.get("blurb") or ""),
            open_count=int(raw.get("open_count") or 0),
            rollup=dict(raw.get("rollup") or {}),
            user_key=str(raw.get("user_key") or "local"),
        )

    def summary(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "updated_at": self.updated_at,
            "blurb": self.blurb,
            "open_count": self.open_count,
            "user_key": self.user_key,
        }


class ConversationCatalog:
    """Hot index of recent conversations; optionally durable on disk."""

    def __init__(
        self,
        *,
        max_entries: int | None = None,
        path: Path | str | None = None,
        persist: bool | None = None,
    ):
        self.max_entries = max_entries if max_entries is not None else catalog_limit()
        self._path = Path(path) if path is not None else default_catalog_path()
        if persist is None:
            persist = os.getenv("CF_CATALOG_PERSIST", "1").strip() != "0"
        self._persist = persist
        self._by_user: dict[str, dict[str, CatalogEntry]] = {}
        if self._persist:
            self._load()

    def reset(self) -> None:
        self._by_user.clear()
        if self._persist and self._path.is_file():
            try:
                self._path.unlink()
            except OSError:
                pass

    def upsert_rollup(
        self,
        rollup: ConversationRollup | dict[str, Any],
        *,
        user_key: str = "local",
        updated_at: float | None = None,
    ) -> CatalogEntry:
        data = rollup.to_dict() if isinstance(rollup, ConversationRollup) else dict(rollup)
        cid = (data.get("conversation_id") or "").strip()
        if not cid:
            raise ValueError("conversation_id_required")
        uk = (user_key or "local").strip() or "local"
        entry = CatalogEntry(
            conversation_id=cid,
            updated_at=float(updated_at if updated_at is not None else time.time()),
            blurb=str(data.get("blurb") or ""),
            open_count=int(data.get("open_count") or 0),
            rollup=data,
            user_key=uk,
        )
        bucket = self._by_user.setdefault(uk, {})
        bucket[cid] = entry
        self._trim(uk)
        self._save()
        return entry

    def touch_from_live(
        self,
        registry,
        store,
        *,
        conversation_id: str,
        user_key: str = "local",
    ) -> CatalogEntry:
        roll = build_conversation_rollup(
            registry, store, conversation_id=conversation_id,
        )
        return self.upsert_rollup(roll, user_key=user_key)

    def list(
        self,
        *,
        user_key: str = "local",
        limit: int | None = None,
    ) -> list[CatalogEntry]:
        uk = (user_key or "local").strip() or "local"
        items = list(self._by_user.get(uk, {}).values())
        items.sort(key=lambda e: e.updated_at, reverse=True)
        n = self.max_entries if limit is None else max(1, limit)
        return items[:n]

    def get(
        self,
        conversation_id: str,
        *,
        user_key: str = "local",
    ) -> CatalogEntry | None:
        uk = (user_key or "local").strip() or "local"
        return self._by_user.get(uk, {}).get((conversation_id or "").strip())

    def match(
        self,
        query: str,
        *,
        user_key: str = "local",
        limit: int = 3,
    ) -> list[tuple[CatalogEntry, float]]:
        """Lexical soft match over blurb + rollup titles — summaries only, no import."""
        q = (query or "").strip()
        if not q:
            return []
        scored: list[tuple[CatalogEntry, float]] = []
        for ent in self.list(user_key=user_key, limit=self.max_entries):
            sc = score_catalog_match(ent, q)
            if sc > 0:
                scored.append((ent, sc))
        scored.sort(key=lambda t: (t[1], t[0].updated_at), reverse=True)
        return scored[: max(1, limit)]

    def _trim(self, user_key: str) -> None:
        bucket = self._by_user.get(user_key) or {}
        if len(bucket) <= self.max_entries:
            return
        ordered = sorted(bucket.values(), key=lambda e: e.updated_at, reverse=True)
        keep = {e.conversation_id for e in ordered[: self.max_entries]}
        self._by_user[user_key] = {k: v for k, v in bucket.items() if k in keep}

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        users = raw.get("users") if isinstance(raw, dict) else None
        if not isinstance(users, dict):
            return
        loaded: dict[str, dict[str, CatalogEntry]] = {}
        for uk, entries in users.items():
            if not isinstance(entries, dict):
                continue
            bucket: dict[str, CatalogEntry] = {}
            for cid, eraw in entries.items():
                if not isinstance(eraw, dict):
                    continue
                ent = CatalogEntry.from_dict(eraw)
                if ent.conversation_id:
                    bucket[ent.conversation_id] = ent
            if bucket:
                loaded[str(uk)] = bucket
                self._trim(str(uk))
        self._by_user = loaded

    def _save(self) -> None:
        if not self._persist:
            return
        payload = {
            "version": 1,
            "users": {
                uk: {cid: e.to_dict() for cid, e in bucket.items()}
                for uk, bucket in self._by_user.items()
            },
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix="catalog_", suffix=".json", dir=str(self._path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            os.replace(tmp_name, self._path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
