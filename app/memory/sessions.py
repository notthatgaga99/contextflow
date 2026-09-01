"""Conversation isolation. Memory + workstream registry may be in-memory or Firestore.

On CF_MEMORY_BACKEND=firestore, both MemoryStore and registry survive instance
replacement. Routing remains frozen.
"""

from __future__ import annotations

import os

from app.config import SETTINGS
from app.context.working_set import WorkingContextBuilder
from app.engine import Engine
from app.memory.factory import create_memory_store, create_registry, memory_backend
from app.memory.retriever import OpenWorkstreamRetriever
from app.memory.store import MemoryStore
from app.memory.writer import MemoryWriter


class ConversationStore:
    """One Engine + registry + MemoryStore per conversation_id."""

    def __init__(self, llm, settings=SETTINGS, mode: str = "split", *, store_client=None):
        self.llm = llm
        self.settings = settings
        self.mode = mode
        self._store_client = store_client  # optional injected Firestore/fake client
        self._engines: dict[str, Engine] = {}
        self._stores: dict[str, MemoryStore] = {}
        self._writers: dict[str, MemoryWriter] = {}

    def reset(self) -> None:
        self._engines.clear()
        self._stores.clear()
        self._writers.clear()

    def memory_store(self, conversation_id: str) -> MemoryStore:
        self.engine(conversation_id)
        return self._stores[conversation_id.strip()]

    def registry(self, conversation_id: str):
        return self.engine(conversation_id).reg

    def writer(self, conversation_id: str) -> MemoryWriter:
        self.engine(conversation_id)
        return self._writers[conversation_id.strip()]

    def engine(self, conversation_id: str) -> Engine:
        cid = (conversation_id or "").strip()
        if not cid:
            raise ValueError("conversation_id_required")
        if cid not in self._engines:
            backend = memory_backend()
            kwargs = {}
            if backend == "firestore" and self._store_client is not None:
                kwargs["client"] = self._store_client
            mem = create_memory_store(cid, backend=backend, **kwargs)
            reg_kwargs = dict(kwargs)
            if backend == "firestore" and hasattr(mem, "_client"):
                reg_kwargs["client"] = mem._client
            reg = create_registry(cid, backend=backend, **reg_kwargs)
            self._stores[cid] = mem
            self._engines[cid] = Engine(
                self.llm, reg, self.settings, mode=self.mode,
                retriever=OpenWorkstreamRetriever(),
                memory_store=mem,
                working_context_builder=WorkingContextBuilder(),
            )
            self._writers[cid] = MemoryWriter(mem, reg)
            if os.getenv("CF_SEED_E2E") == "1":
                from app.memory.demo_cards import seed_e2e_four
                seed_e2e_four(reg)
            elif os.getenv("CF_SEED_TEN") == "1":
                from app.memory.demo_cards import seed_ten
                seed_ten(reg)
            elif os.getenv("CF_SEED_ABCD") == "1" or os.getenv("CF_SMOKE_FIXTURE") == "1":
                from app.memory.demo_cards import seed_abcd
                seed_abcd(reg)
        return self._engines[cid]

    def ids(self) -> list[str]:
        return list(self._engines.keys())
