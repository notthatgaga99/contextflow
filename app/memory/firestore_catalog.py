"""Firestore-backed last-N conversation catalog (H2 durable).

Path: cf_catalog/{user_key}/entries/{conversation_id}

Same product laws as file catalog:
- Structured rollups only (not transcripts).
- Cap hot set (CF_CATALOG_LIMIT).
- Never inject into generate() — list/match/import are opt-in.
- No auto-merge across chats.
"""

from __future__ import annotations

import os
import time
from typing import Any

from app.memory.catalog import CatalogEntry, catalog_limit, score_catalog_match
from app.memory.rollup import ConversationRollup, build_conversation_rollup


def _client(client=None, *, project: str | None = None, database: str | None = None):
    if client is not None:
        return client
    from google.cloud import firestore

    kwargs: dict[str, Any] = {}
    if project:
        kwargs["project"] = project
    db = database or os.getenv("CF_FIRESTORE_DATABASE") or "(default)"
    if db and db != "(default)":
        kwargs["database"] = db
    return firestore.Client(**kwargs)


class FirestoreConversationCatalog:
    """User-scoped durable hot index of conversation rollups."""

    def __init__(
        self,
        *,
        max_entries: int | None = None,
        client=None,
        project: str | None = None,
        database: str | None = None,
        root_collection: str = "cf_catalog",
    ):
        self.max_entries = max_entries if max_entries is not None else catalog_limit()
        self._db = _client(
            client,
            project=project or os.getenv("GCP_PROJECT") or None,
            database=database,
        )
        self._root = root_collection

    def reset(self) -> None:
        """Test helper: wipe catalog docs (FakeFirestore) or best-effort delete."""
        docs = getattr(self._db, "_docs", None)
        if isinstance(docs, dict):
            prefix = f"{self._root}/"
            for key in list(docs.keys()):
                if key.startswith(prefix):
                    docs.pop(key, None)
            return
        # Real client: delete entry docs found under each user (rare outside tests).
        for user_key in ("local",):
            for ent in self._load_user(user_key):
                self._entry_ref(user_key, ent.conversation_id).delete()

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
        self._entry_ref(uk, cid).set(entry.to_dict())
        self._trim(uk)
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
        items = self._load_user(uk)
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
        snap = self._entry_ref(uk, (conversation_id or "").strip()).get()
        if not snap.exists:
            return None
        raw = snap.to_dict() or {}
        ent = CatalogEntry.from_dict(raw)
        return ent if ent.conversation_id else None

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

    def _entry_ref(self, user_key: str, conversation_id: str):
        return (
            self._db.collection(self._root)
            .document(user_key)
            .collection("entries")
            .document(conversation_id)
        )

    def _load_user(self, user_key: str) -> list[CatalogEntry]:
        out: list[CatalogEntry] = []
        for snap in (
            self._db.collection(self._root)
            .document(user_key)
            .collection("entries")
            .stream()
        ):
            raw = snap.to_dict() or {}
            ent = CatalogEntry.from_dict(raw)
            if ent.conversation_id:
                out.append(ent)
        return out

    def _trim(self, user_key: str) -> None:
        items = self._load_user(user_key)
        if len(items) <= self.max_entries:
            return
        items.sort(key=lambda e: e.updated_at, reverse=True)
        drop = items[self.max_entries :]
        batch = self._db.batch()
        for ent in drop:
            batch.delete(self._entry_ref(user_key, ent.conversation_id))
        batch.commit()
