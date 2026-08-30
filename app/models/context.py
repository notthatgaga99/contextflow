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


FULL_TASK = "FULL_TASK"
REFERENT_COMPACT = "REFERENT_COMPACT"
MERGED_COMPACT = "MERGED_COMPACT"


@dataclass
class ContextPackage:
    task_id: str
    task_summary: str = ""
    relevant_facts: list[str] = field(default_factory=list)
    active_decisions: list[str] = field(default_factory=list)
    active_constraints: list[str] = field(default_factory=list)
    open_loops: list[str] = field(default_factory=list)
    selected_referent_id: Optional[str] = None
    selected_open_loop: Optional[str] = None
    context_mode: str = REFERENT_COMPACT
    included_loop_ids: list[str] = field(default_factory=list)
    decision_text: str = ""
    answer_text: str = ""
    source_event_ids: list[str] = field(default_factory=list)
    excluded_workstreams: list[str] = field(default_factory=list)
    memory_item_ids: list[str] = field(default_factory=list)
    recent_changes: list[str] = field(default_factory=list)
    relevant_entities: list[str] = field(default_factory=list)
    insufficient_working_set: bool = False
    decision_tokens: int = 0
    answer_tokens: int = 0
    total_context_tokens: int = 0

    @property
    def decision_context_tokens(self) -> int:
        return self.decision_tokens

    @property
    def answer_context_tokens(self) -> int:
        return self.answer_tokens

    def to_dict(self) -> dict:
        d = asdict(self)
        d["decision_context_tokens"] = self.decision_tokens
        d["answer_context_tokens"] = self.answer_tokens
        return d
