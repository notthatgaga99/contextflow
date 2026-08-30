"""In-memory conversation isolation. Process-local only — not durable.

Cloud Run restart / multi-instance does not share this state. A durable
MemoryStore adapter is NOT YET; do not claim multi-instance memory semantics.
Does not change routing math.
"""

from __future__ import annotations

import os

from app.config import SETTINGS
from app.context.working_set import WorkingContextBuilder
from app.engine import Engine
from app.memory.registry import InMemoryRegistry
from app.memory.retriever import OpenWorkstreamRetriever
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter


class ConversationStore:
    """One Engine + registry + MemoryStore per conversation_id. Process lifetime only."""

    def __init__(self, llm, settings=SETTINGS, mode: str = "split"):
        self.llm = llm
        self.settings = settings
        self.mode = mode
        self._engines: dict[str, Engine] = {}
        self._stores: dict[str, InMemoryMemoryStore] = {}
        self._writers: dict[str, MemoryWriter] = {}

    def reset(self) -> None:
        self._engines.clear()
        self._stores.clear()
        self._writers.clear()

    def memory_store(self, conversation_id: str) -> InMemoryMemoryStore:
        self.engine(conversation_id)
        return self._stores[conversation_id.strip()]

    def writer(self, conversation_id: str) -> MemoryWriter:
        self.engine(conversation_id)
        return self._writers[conversation_id.strip()]

    def engine(self, conversation_id: str) -> Engine:
        cid = (conversation_id or "").strip()
        if not cid:
            raise ValueError("conversation_id_required")
        if cid not in self._engines:
            mem = InMemoryMemoryStore(conversation_id=cid)
            self._stores[cid] = mem
            reg = InMemoryRegistry()
            self._engines[cid] = Engine(
                self.llm, reg, self.settings, mode=self.mode,
                retriever=OpenWorkstreamRetriever(),
                memory_store=mem,
                working_context_builder=WorkingContextBuilder(),
            )
            self._writers[cid] = MemoryWriter(mem, reg)
            if os.getenv("CF_SEED_ABCD") == "1" or os.getenv("CF_SMOKE_FIXTURE") == "1":
                from app.memory.demo_cards import seed_abcd
                seed_abcd(reg)
        return self._engines[cid]

    def ids(self) -> list[str]:
        return list(self._engines.keys())
