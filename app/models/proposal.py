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
    """Deterministic routing record. No field here is a calibrated probability."""

    transition: Transition
    task_id: Optional[str]
    top: float  # top_norm (diagnostic only; does not gate)
    margin: float  # raw_margin (decision quantity; not a probability)
    gating_quantity: float  # = raw_margin, for risk-coverage sweeps
    conflict: Optional[Conflict] = None
    candidates: list = field(default_factory=list)
    top_raw: float = 0.0
    runner_raw: float = 0.0
    raw_margin: float = 0.0
    top_norm: float = 0.0
    runner_norm: float = 0.0
    norm_margin: float = 0.0
    open_task_count: int = 0
    plausible_candidate_count: int = 0
    active_task: Optional[str] = None
    active_raw: float = 0.0
    active_gap: float = 0.0  # top_raw - active_raw; 0 if no active task
