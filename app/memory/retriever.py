"""Open-workstream Retriever. Candidates only — does not choose a referent."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.task import Task


@runtime_checkable
class Retriever(Protocol):
    def candidates(self, message: str, registry) -> list[Task]: ...


class OpenWorkstreamRetriever:
    def candidates(self, message: str, registry) -> list[Task]:
        return list(registry.open_tasks())
