"""MemoryPort — pluggable persistence behind the working-memory switch.

Binder (frozen ContextFlow) selects a thread. Ports serve:
  list_open_threads / read_asserted / get_task / search_cold (real local ranker).

Cold hits enrich the *bound* thread only via expose_bound_thread — never a
multi-thread dump into generate(). Frozen gate/scorer/referent untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.memory.cold_search import ColdHit, hits_from_items
from app.models.memory import MemoryItem
from app.models.task import Task

# Re-export for callers that import ColdHit from port.
__all__ = [
    "ThreadCard",
    "ColdHit",
    "MemoryPort",
    "InProcessMemoryPort",
    "DictMemoryPort",
]


@dataclass
class ThreadCard:
    """Thin L4 index row for routing — not L1 body."""

    workstream_id: str
    title: str = ""
    goal: str = ""
    status: str = "paused"
    open_loops: list[str] = field(default_factory=list)
    retrieval_cues: list[str] = field(default_factory=list)
    last_active_turn: int = 0
    mention_turn: int = 0

    @classmethod
    def from_task(cls, t: Task) -> "ThreadCard":
        return cls(
            workstream_id=t.id,
            title=t.title or t.id,
            goal=t.anchor.goal or t.title or "",
            status=t.status,
            open_loops=list(t.anchor.open_loops or []),
            retrieval_cues=list(t.retrieval_cues or []),
            last_active_turn=t.last_active_turn,
            mention_turn=t.mention_turn,
        )


@runtime_checkable
class MemoryPort(Protocol):
    def list_open_threads(self) -> list[ThreadCard]: ...

    def get_task(self, workstream_id: str) -> Task | None: ...

    def read_asserted(self, workstream_id: str) -> list[MemoryItem]: ...

    def search_cold(
        self,
        query: str,
        *,
        limit: int = 5,
        workstream_id: str | None = None,
    ) -> list[ColdHit]: ...


class InProcessMemoryPort:
    """Adapter over registry + MemoryStore with real lexical/hash cold search."""

    def __init__(self, registry, store):
        self.registry = registry
        self.store = store

    def list_open_threads(self) -> list[ThreadCard]:
        return [ThreadCard.from_task(t) for t in self.registry.open_tasks()]

    def get_task(self, workstream_id: str) -> Task | None:
        return self.registry.get(workstream_id)

    def read_asserted(self, workstream_id: str) -> list[MemoryItem]:
        return list(self.store.asserted(workstream_id))

    def search_cold(
        self,
        query: str,
        *,
        limit: int = 5,
        workstream_id: str | None = None,
    ) -> list[ColdHit]:
        # Prefer historical(workstream) so capped / referent-filtered asserts can resurface.
        if workstream_id and hasattr(self.store, "historical"):
            items = list(self.store.historical(workstream_id))
        elif workstream_id:
            items = list(self.store.asserted(workstream_id))
        else:
            items = list(self.store.all()) if hasattr(self.store, "all") else list(
                self.store.asserted()
            )
        return hits_from_items(
            query, items, limit=limit, workstream_id=workstream_id, use_embed=True,
        )


class DictMemoryPort:
    """In-memory port with the same cold-search implementation (no empty stub)."""

    def __init__(
        self,
        tasks: dict[str, Task],
        asserted: dict[str, list[MemoryItem]],
        *,
        historical: dict[str, list[MemoryItem]] | None = None,
    ):
        self._tasks = dict(tasks)
        self._asserted = {k: list(v) for k, v in asserted.items()}
        self._historical = {
            k: list(v) for k, v in (historical or {}).items()
        }

    def list_open_threads(self) -> list[ThreadCard]:
        return [
            ThreadCard.from_task(t)
            for t in self._tasks.values()
            if t.status in ("active", "paused")
        ]

    def get_task(self, workstream_id: str) -> Task | None:
        return self._tasks.get(workstream_id)

    def read_asserted(self, workstream_id: str) -> list[MemoryItem]:
        return list(self._asserted.get(workstream_id, []))

    def search_cold(
        self,
        query: str,
        *,
        limit: int = 5,
        workstream_id: str | None = None,
    ) -> list[ColdHit]:
        if workstream_id:
            items = list(self._historical.get(workstream_id, []))
            if not items:
                items = list(self._asserted.get(workstream_id, []))
            # Always include asserted for ranking even if historical set
            seen = {i.id for i in items}
            for i in self._asserted.get(workstream_id, []):
                if i.id not in seen:
                    items.append(i)
        else:
            items = []
            for wid, rows in self._asserted.items():
                items.extend(rows)
            for wid, rows in self._historical.items():
                items.extend(rows)
        return hits_from_items(
            query, items, limit=limit, workstream_id=workstream_id, use_embed=True,
        )
