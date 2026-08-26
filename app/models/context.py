from dataclasses import dataclass, field, asdict
from typing import Optional, Union


@dataclass
class Reference:
    kind: str = "none"  # ordinal | entity | pronoun | none
    value: Optional[Union[str, int]] = None
    raw_span: str = ""


@dataclass
class Conflict:
    kind: str
    explicit_ref: Reference
    evidence_task_id: str
    reason: str


@dataclass
class ContextPackage:
    task_id: str
    task_summary: str = ""
    relevant_facts: list[str] = field(default_factory=list)
    active_decisions: list[str] = field(default_factory=list)
    active_constraints: list[str] = field(default_factory=list)
    open_loops: list[str] = field(default_factory=list)
    source_event_ids: list[str] = field(default_factory=list)
    decision_tokens: int = 0
    answer_tokens: int = 0

    def to_dict(self) -> dict:
        return asdict(self)
