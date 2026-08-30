from dataclasses import dataclass, field
from typing import Callable, Optional

from app.config import SETTINGS, NEW_ID
from app.domain import LLM, Registry, Transition
from app.models.context import ContextPackage
from app.models.proposal import GateDecision, TaskProposal
from app.models.task import Task, TaskAnchor
from app.router.proposal import propose
from app.router.references import parse_reference, detect_conflict
from app.router.gate import decide, bind_task, clarify_question
from app.router.referent import (
    loop_index_from_id,
    loop_referent_id,
    resolve_referent,
)
from app.retrieval.scorer import score_candidates
from app.context.compiler import ContextCompiler
from app.context.working_set import WorkingContextBuilder
from app.memory.retriever import OpenWorkstreamRetriever, Retriever
from app.memory.store import MemoryStore

NewTaskFactory = Callable[[str, int], Optional[Task]]


@dataclass
class TurnResult:
    transition: Transition
    task_id: Optional[str]
    answer: Optional[str]
    clarify_question: Optional[str]
    package: Optional[ContextPackage]
    decision: GateDecision
    predicted_task_id: Optional[str] = None
    predicted_referent_id: Optional[str] = None
    resolution_evidence: dict = field(default_factory=dict)


def _sanitize_proposal(proposal: TaskProposal, open_ids: set[str]) -> TaskProposal:
    """Unknown task ids are not evidence. Fail closed."""
    if proposal.task_id is None:
        return proposal
    if proposal.task_id in open_ids:
        return proposal
    return TaskProposal(
        task_id=None,
        is_new_task=False,
        confidence=0.0,
        referent=None,
        rationale="invalid_task_id",
    )


def _loop_text(task, referent_id: Optional[str]) -> Optional[str]:
    if not referent_id:
        return None
    idx = loop_index_from_id(task.id, referent_id)
    if idx is None or idx >= len(task.anchor.open_loops):
        return None
    return task.anchor.open_loops[idx]


class Engine:
    """Single composition root. Wiring only — no algorithm lives here."""

    def __init__(self, llm: LLM, registry: Registry, settings=SETTINGS,
                 mode: str = "split", platt: tuple[float, float] | None = None,
                 new_task_factory: NewTaskFactory | None = None,
                 retriever: Retriever | None = None,
                 memory_store: MemoryStore | None = None,
                 working_context_builder: WorkingContextBuilder | None = None):
        self.llm = llm
        self.reg = registry
        self.settings = settings
        self.mode = mode
        self.platt = platt
        self.compiler = ContextCompiler()
        self.new_task_factory = new_task_factory
        self.retriever = retriever or OpenWorkstreamRetriever()
        self.memory_store = memory_store
        self.working_context_builder = working_context_builder or WorkingContextBuilder()

    def _make_package(self, task, pred_ref, loop_text, message, open_tasks):
        extra = {}
        if self.memory_store is not None and self.memory_store.asserted(task.id):
            proj = self.working_context_builder.project(
                task, pred_ref, self.memory_store, open_tasks,
            )
            extra = {
                "active_decisions": proj.decisions,
                "active_constraints": proj.constraints,
                "relevant_facts": proj.facts,
                "relevant_entities": proj.entities,
                "excluded_workstreams": proj.excluded_workstreams,
                "memory_item_ids": proj.item_ids,
                "recent_changes": proj.recent_changes,
            }
        pkg = self.compiler.build(
            task, self.mode,
            selected_referent_id=pred_ref,
            selected_open_loop=loop_text,
            message=message,
            open_tasks=list(open_tasks),
            **extra,
        )
        return pkg

    def handle_turn(self, message: str, turn: int) -> TurnResult:
        open_tasks = self.retriever.candidates(message, self.reg)
        active = self.reg.active()
        active_id = active.id if active else None
        open_ids = {t.id for t in open_tasks}

        proposal = _sanitize_proposal(propose(self.llm, message, open_tasks), open_ids)
        resolution = resolve_referent(
            message, open_tasks, proposal.task_id,
            prior_referent_id=self.reg.last_selected_referent(),
        )
        apply_llm = resolution.kind not in ("deictic", "correction")
        cands = score_candidates(
            self.llm, message, open_tasks, proposal, turn, self.settings,
            apply_llm=apply_llm,
        )

        pred_task = resolution.predicted_task_id
        pred_ref = resolution.predicted_referent_id
        evidence = dict(resolution.evidence)

        top = cands[0]
        conflict_task_id = pred_task if (resolution.use_referent_route and pred_task) else (
            top.task_id if top.task_id != NEW_ID else None
        )
        top_task = self.reg.get(conflict_task_id) if conflict_task_id else None
        ref = parse_reference(message)
        conflict = detect_conflict(ref, top, top_task, self.settings)

        statuses = {t.id: t.status for t in open_tasks}
        turns_since = {t.id: turn - t.last_active_turn for t in open_tasks}

        if conflict is not None:
            decision = decide(cands, conflict, active_id, self.settings, self.platt,
                              statuses=statuses, turns_since=turns_since)
            return self._clarify(decision, cands, pred_task, pred_ref, evidence)

        if resolution.use_referent_route:
            if resolution.ambiguous or not pred_task:
                decision = decide(cands, None, active_id, self.settings, self.platt,
                                  statuses=statuses, turns_since=turns_since)
                # Resolver is uncertain: policy CLARIFY even if scorer would act.
                return self._clarify(decision, cands, pred_task, pred_ref, evidence)
            decision = bind_task(
                cands, None, active_id, self.settings, statuses, turns_since, pred_task,
            )
            return self._act(decision, pred_task, pred_ref, evidence, turn, message, open_tasks)

        decision = decide(cands, None, active_id, self.settings, self.platt,
                          statuses=statuses, turns_since=turns_since)
        if decision.transition == Transition.CLARIFY:
            return self._clarify(decision, cands, pred_task, pred_ref, evidence)
        if decision.transition == Transition.NEW:
            return self._new(decision, evidence, turn, message)
        return self._act(decision, decision.task_id, pred_ref, evidence, turn, message, open_tasks)

    def _clarify(self, decision: GateDecision, cands, pred_task, pred_ref, evidence) -> TurnResult:
        return TurnResult(
            Transition.CLARIFY, None, None,
            clarify_question(cands, self.reg), None, decision,
            pred_task, pred_ref, evidence,
        )

    def _act(self, decision: GateDecision, task_id: Optional[str],
             pred_ref: Optional[str], evidence: dict, turn: int,
             message: str, open_tasks: list) -> TurnResult:
        if not task_id:
            return TurnResult(
                decision.transition, None, None, None, None, decision,
                task_id, pred_ref, evidence,
            )
        self.reg.mark_active(task_id, turn)
        self.reg.record_mention(task_id, turn, pred_ref)
        self.reg.set_last_selected_referent(pred_ref)
        task = self.reg.get(task_id)
        loop_text = _loop_text(task, pred_ref)
        pkg = self._make_package(task, pred_ref, loop_text, message, open_tasks)
        answer = self.llm.generate(self.compiler.render(pkg))
        self.reg.apply_update(task_id, {})  # legacy no-op; MemoryWriter is the production path
        return TurnResult(
            decision.transition, task_id, answer, None, pkg, decision,
            task_id, pred_ref, evidence,
        )

    def _next_task_id(self) -> str:
        n = 1
        while self.reg.get(f"T{n}") is not None:
            n += 1
        return f"T{n}"

    def _default_new_task(self, message: str) -> Task:
        text = " ".join(message.strip().split())
        title = text[:48] or "untitled"
        cues = [w for w in text.lower().replace("'", "").split() if w.isalpha() and len(w) >= 3][:8]
        return Task(
            id=self._next_task_id(),
            title=title,
            retrieval_cues=cues,
            anchor=TaskAnchor(goal=text[:160], open_loops=[text[:200]] if text else []),
        )

    def _new(self, decision: GateDecision, evidence: dict, turn: int, message: str) -> TurnResult:
        """Persist a card after the gate accepts NEW. Does not change scoring or thresholds."""
        task = None
        if self.new_task_factory is not None:
            task = self.new_task_factory(message, turn)
        if task is None:
            task = self._default_new_task(message)
        if self.reg.get(task.id) is not None:
            task = self._default_new_task(message)
            task.id = self._next_task_id()
        self.reg.add(task)
        ref_id = loop_referent_id(task.id, 0) if task.anchor.open_loops else task.id
        self.reg.mark_active(task.id, turn)
        self.reg.record_mention(task.id, turn, ref_id)
        self.reg.set_last_selected_referent(ref_id)
        loop_text = _loop_text(task, ref_id)
        pkg = self._make_package(task, ref_id, loop_text, message, self.reg.open_tasks())
        answer = self.llm.generate(self.compiler.render(pkg))
        return TurnResult(
            Transition.NEW, task.id, answer, None, pkg, decision,
            task.id, ref_id, evidence,
        )
