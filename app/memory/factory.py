"""MemoryStore and WorkstreamRegistry factories. Default remains in-memory."""

from __future__ import annotations

import os

from app.memory.registry import InMemoryRegistry
from app.memory.store import InMemoryMemoryStore, MemoryStore


def memory_backend() -> str:
    return (os.getenv("CF_MEMORY_BACKEND", "memory") or "memory").strip().lower()


def create_memory_store(
    conversation_id: str,
    *,
    backend: str | None = None,
    client=None,
) -> MemoryStore:
    """Create a conversation-scoped MemoryStore.

    backend:
      memory    — InMemoryMemoryStore (default)
      firestore — FirestoreMemoryStore (ADC / injected client)
    """
    kind = (backend or memory_backend()).strip().lower()
    if kind in ("memory", "inmemory", "in-memory"):
        return InMemoryMemoryStore(conversation_id=conversation_id)
    if kind == "firestore":
        from app.memory.firestore_store import FirestoreMemoryStore
        return FirestoreMemoryStore(
            conversation_id,
            client=client,
            project=os.getenv("GCP_PROJECT") or None,
            database=os.getenv("CF_FIRESTORE_DATABASE") or "(default)",
        )
    raise ValueError(f"unsupported_memory_backend:{kind}")


def create_registry(
    conversation_id: str,
    *,
    backend: str | None = None,
    client=None,
):
    """Create a conversation-scoped workstream registry.

    When CF_MEMORY_BACKEND=firestore, registry is also Firestore-backed.
    """
    kind = (backend or memory_backend()).strip().lower()
    if kind in ("memory", "inmemory", "in-memory"):
        return InMemoryRegistry()
    if kind == "firestore":
        from app.memory.firestore_registry import FirestoreRegistry
        return FirestoreRegistry(
            conversation_id,
            client=client,
            project=os.getenv("GCP_PROJECT") or None,
            database=os.getenv("CF_FIRESTORE_DATABASE") or "(default)",
        )
    raise ValueError(f"unsupported_memory_backend:{kind}")
