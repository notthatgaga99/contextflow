from dataclasses import dataclass, field
from typing import Optional
from pydantic import BaseModel

from app.domain import Transition
from app.models.context import Conflict


class TaskProposal(BaseModel):
    task_id: Optional[str] = None
    is_new_task: bool = True
    confidence: float = 0.0
    referent: Optional[str] = None
    rationale: str = ""


@dataclass
class Candidate:
    task_id: str
    raw: float
    norm: float
    components: dict = field(default_factory=dict)  # {llm,cos,rec,loop}


@dataclass
class GateDecision:
    transition: Transition
    task_id: Optional[str]
    top: float
    margin: float
    gating_quantity: float
    conflict: Optional[Conflict] = None
    candidates: list = field(default_factory=list)
