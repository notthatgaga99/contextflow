from dataclasses import dataclass
from typing import Optional

from app.config import SETTINGS, NEW_ID
from app.domain import LLM, Registry, Transition
from app.models.context import ContextPackage
from app.models.proposal import GateDecision
from app.router.proposal import propose
from app.router.references import parse_reference, detect_conflict
from app.router.gate import decide, clarify_question
from app.retrieval.scorer import score_candidates
from app.context.compiler import ContextCompiler


@dataclass
class TurnResult:
    transition: Transition
    task_id: Optional[str]
    answer: Optional[str]
    clarify_question: Optional[str]
    package: Optional[ContextPackage]
    decision: GateDecision


class Engine:
    """Single composition root. Wiring only — no algorithm lives here."""

    def __init__(self, llm: LLM, registry: Registry, settings=SETTINGS,
                 mode: str = "split", platt: tuple[float, float] | None = None):
        self.llm = llm
        self.reg = registry
        self.settings = settings
        self.mode = mode
        self.platt = platt
        self.compiler = ContextCompiler()

    def handle_turn(self, message: str, turn: int) -> TurnResult:
        open_tasks = self.reg.open_tasks()
        active = self.reg.active()
        active_id = active.id if active else None

        proposal = propose(self.llm, message, open_tasks)
        cands = score_candidates(self.llm, message, open_tasks, proposal, turn, self.settings)

        top = cands[0]
        top_task = self.reg.get(top.task_id) if top.task_id != NEW_ID else None
        ref = parse_reference(message)
        conflict = detect_conflict(ref, top, top_task, self.settings)

        statuses = {t.id: t.status for t in open_tasks}
        turns_since = {t.id: turn - t.last_active_turn for t in open_tasks}
        decision = decide(cands, conflict, active_id, self.settings, self.platt,
                          statuses=statuses, turns_since=turns_since)

        if decision.transition == Transition.CLARIFY:
            return TurnResult(Transition.CLARIFY, None, None,
                              clarify_question(cands, self.reg), None, decision)

        if decision.transition == Transition.NEW:
            return TurnResult(Transition.NEW, None, None, None, None, decision)

        task_id = decision.task_id
        self.reg.mark_active(task_id, turn)
        task = self.reg.get(task_id)
        pkg = self.compiler.build(task, self.mode)
        answer = self.llm.generate(self.compiler.render(pkg))
        self.reg.apply_update(task_id, {})  # no-op delta in MVP; state extraction added later
        return TurnResult(decision.transition, task_id, answer, None, pkg, decision)
