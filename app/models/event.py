from dataclasses import dataclass, field, asdict
from enum import Enum


class EventType(str, Enum):
    MESSAGE = "message"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    STATE_CHANGE = "state_change"
    TASK_SWITCH = "task_switch"
    TASK_RETURN = "task_return"


@dataclass
class TaskEvent:
    id: str
    task_id: str
    event_type: EventType
    content: str
    turn: int
    created_at: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
