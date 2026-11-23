from dataclasses import dataclass, field
from typing import Callable, Optional
import os

from app.config import SETTINGS, NEW_ID
from app.domain import LLM, Registry, Transition
from app.models.context import ContextPackage
from app.models.proposal import GateDecision, TaskProposal
from app.models.task import Task, TaskAnchor
from app.router.proposal import propose
from app.router.references import parse_reference, detect_conflict
from app.router.gate import (
    decide,
    bind_task,
    clarify_question,
    clarify_question_from_ids,
)
from app.router.referent import (
    loop_index_from_id,
    loop_referent_id,
    resolve_referent,
)
from app.retrieval.scorer import score_candidates
from app.context.compiler import ContextCompiler
from app.context.working_memory_switch import expose_bound_thread
from app.context.working_set import WorkingContextBuilder
from app.memory.port import InProcessMemoryPort, MemoryPort
from app.memory.retriever import OpenWorkstreamRetriever, Retriever
from app.memory.store import MemoryStore
from app.router.thread_discriminate import (
    build_evidence,
    identity_cues_from_items,
    score_threads,
)
from app.router.topic_align import align_plan
from app.router.topic_discern import discern_topic

NewTaskFactory = Callable[[str, int], Optional[Task]]


@dataclass
class TurnPlan:
    """Routing outcome without registry mutations or answer generation."""
    transition: Transition
    task_id: str | None
    pred_task: str | None
    pred_ref: str | None
    evidence: dict
    decision: GateDecision
    open_tasks: list
    candidates: list = field(default_factory=list)


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
    # Exact L1 expose text fed to generate (single snapshot; kernel must not re-invent).
    l1_expose: Optional[str] = None


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
                 working_context_builder: WorkingContextBuilder | None = None,
                 memory_port: MemoryPort | None = None):
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
        # Bind → read → expose uses MemoryPort; default wraps in-process store.
        if memory_port is not None:
            self.memory_port = memory_port
        elif memory_store is not None:
            self.memory_port = InProcessMemoryPort(registry, memory_store)
        else:
            self.memory_port = None

    def _make_package(self, task, pred_ref, loop_text, message, open_tasks):
        """Assemble answer package from L1 compact notation for the bound task only.

        Returns (package, l1_expose_text). Callers must pass that expose through
        TurnResult so diagnostics match what generate saw.
        """
        extra = {}
        notation = None
        expose = None
        if self.memory_port is not None:
            notation = expose_bound_thread(
                self.memory_port,
                workstream_id=task.id,
                referent_id=pred_ref,
                selected_loop=loop_text,
                builder=self.working_context_builder,
                open_tasks=list(open_tasks),
                query=message,
            )
            if notation is not None:
                expose = notation.to_expose_text()
                if (
                    notation.decisions or notation.constraints
                    or notation.facts or notation.entities
                    or notation.procedures or notation.memory_item_ids
                ):
                    extra = notation.compiler_extras()
        pkg = self.compiler.build(
            task, self.mode,
            selected_referent_id=pred_ref,
            selected_open_loop=loop_text,
            message=message,
            open_tasks=list(open_tasks),
            **extra,
        )
        # Attach L1 notation for inspectors / API (non-routing).
        if notation is not None:
            pkg.source_event_ids = list(notation.memory_item_ids or pkg.source_event_ids)
        return pkg, expose

    def plan_turn(self, message: str, turn: int) -> TurnPlan:
        """Frozen routing plan only — no registry writes, no answer generation."""
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
            plan = TurnPlan(
                Transition.CLARIFY, None, pred_task, pred_ref, evidence, decision, open_tasks, cands,
            )
            return self._maybe_align(plan, message, open_tasks, active_id)

        if resolution.use_referent_route:
            if resolution.ambiguous or not pred_task:
                decision = decide(cands, None, active_id, self.settings, self.platt,
                                  statuses=statuses, turns_since=turns_since)
                plan = TurnPlan(
                    Transition.CLARIFY, None, pred_task, pred_ref, evidence, decision, open_tasks, cands,
                )
                return self._maybe_align(plan, message, open_tasks, active_id)
            decision = bind_task(
                cands, None, active_id, self.settings, statuses, turns_since, pred_task,
            )
            plan = TurnPlan(
                decision.transition, pred_task, pred_task, pred_ref, evidence, decision, open_tasks, cands,
            )
            return self._maybe_align(plan, message, open_tasks, active_id)

        decision = decide(cands, None, active_id, self.settings, self.platt,
                          statuses=statuses, turns_since=turns_since)
        if decision.transition == Transition.CLARIFY:
            plan = TurnPlan(
                Transition.CLARIFY, None, pred_task, pred_ref, evidence, decision, open_tasks, cands,
            )
            # Frozen gate CLARIFY is embedding-near; I-channel may still resolve.
            return self._maybe_align(plan, message, open_tasks, active_id)
        if decision.transition == Transition.NEW:
            plan = TurnPlan(
                Transition.NEW, None, pred_task, pred_ref, evidence, decision, open_tasks, cands,
            )
            return self._maybe_align(plan, message, open_tasks, active_id)

        plan = TurnPlan(
            decision.transition, decision.task_id, pred_task, pred_ref, evidence, decision, open_tasks, cands,
        )
        return self._maybe_align(plan, message, open_tasks, active_id)

    @staticmethod
    def _referent_owner(referent_id: str | None) -> str | None:
        if not referent_id:
            return None
        return referent_id.split(".", 1)[0]

    @staticmethod
    def _default_referent(task_id: str, open_tasks: list) -> str:
        for t in open_tasks:
            if t.id == task_id:
                if t.anchor.open_loops:
                    return loop_referent_id(task_id, 0)
                return task_id
        return task_id

    def _maybe_align(self, plan: TurnPlan, message: str, open_tasks: list, active_id: str | None) -> TurnPlan:
        """Post-gate topic alignment; frozen gate thresholds unchanged.

        Topic-LLM (CF_TOPIC_LLM) is a soft prior only. Discrimination always runs
        afterward so Vertex demos cannot skip the I-channel or desync task/referent.
        """
        mem_texts: dict[str, list[str]] = {}
        id_cues = {}
        if self.memory_store is not None:
            for t in open_tasks:
                items = self.memory_store.asserted(t.id)
                cues = identity_cues_from_items(items)
                id_cues[t.id] = cues
                texts = [i.text for i in items if getattr(i, "text", "")]
                # Slot names must reach lexical overlap (discern veto) and I-channel.
                texts.extend(cues.extra_texts())
                mem_texts[t.id] = texts

        topic_llm = os.getenv("CF_TOPIC_LLM", "").strip()
        if topic_llm == "":
            # Default on for Vertex-hosted demos; off for local mock pytest.
            topic_llm = "1" if os.getenv("CF_USE_VERTEX") == "1" else "0"

        evidence = dict(plan.evidence)
        if topic_llm == "1" and plan.transition != Transition.CLARIFY:
            discerned = discern_topic(
                self.llm, message, open_tasks, active_id, mem_texts,
            )
            if discerned is not None:
                evidence.update({
                    "topic_discern": discerned.reason,
                    "topic_discern_decision": discerned.transition.value,
                    "topic_discern_task": discerned.task_id,
                    "topic_discern_confidence": discerned.confidence,
                    "topic_discern_rationale": discerned.rationale,
                    "topic_align_gate_transition": plan.transition.value,
                    "topic_align_gate_task": plan.task_id,
                })
                # Soft prior only — discrimination below is authoritative.
                if discerned.transition == Transition.CLARIFY:
                    plan = TurnPlan(
                        Transition.CLARIFY, None, plan.pred_task, plan.pred_ref, evidence,
                        plan.decision, plan.open_tasks, plan.candidates,
                    )
                elif discerned.transition == Transition.NEW:
                    plan = TurnPlan(
                        Transition.NEW, None, plan.pred_task, plan.pred_ref, evidence,
                        plan.decision, plan.open_tasks, plan.candidates,
                    )
                else:
                    plan = TurnPlan(
                        discerned.transition, discerned.task_id, plan.pred_task, plan.pred_ref,
                        evidence, plan.decision, plan.open_tasks, plan.candidates,
                    )

        # Always compute two-channel snapshot (genre S vs identity I) for audit + bind.
        disc_scores = (
            score_threads(message, open_tasks, mem_texts, id_cues) if open_tasks else {}
        )
        disc_ev = build_evidence(disc_scores).to_dict()

        aligned = align_plan(
            message=message,
            transition=plan.transition,
            task_id=plan.task_id,
            open_tasks=open_tasks,
            active_id=active_id,
            memory_texts_by_task=mem_texts,
            identity_cues_by_task=id_cues,
        )
        if aligned is None:
            out = TurnPlan(
                plan.transition, plan.task_id, plan.pred_task, plan.pred_ref,
                {**plan.evidence, **evidence, "discrimination": disc_ev},
                plan.decision, plan.open_tasks, plan.candidates,
            )
            return self._reconcile_task_ref(out, disc_ev, active_id)
        evidence = {
            **plan.evidence,
            **evidence,
            "topic_align": aligned.reason,
            "topic_align_selected_score": aligned.selected_score,
            "topic_align_best_other": aligned.best_other_id,
            "topic_align_best_other_score": aligned.best_other_score,
            "topic_align_gate_transition": plan.transition.value,
            "topic_align_gate_task": plan.task_id,
            "discrimination": aligned.discrimination or disc_ev,
        }
        if aligned.transition == Transition.CLARIFY:
            return TurnPlan(
                Transition.CLARIFY, None, plan.pred_task, plan.pred_ref, evidence,
                plan.decision, plan.open_tasks, plan.candidates,
            )
        if aligned.transition == Transition.NEW:
            return TurnPlan(
                Transition.NEW, None, plan.pred_task, plan.pred_ref, evidence,
                plan.decision, plan.open_tasks, plan.candidates,
            )
        out = TurnPlan(
            aligned.transition, aligned.task_id, plan.pred_task, plan.pred_ref, evidence,
            plan.decision, plan.open_tasks, plan.candidates,
        )
        return self._reconcile_task_ref(out, evidence.get("discrimination") or disc_ev, active_id)

    def _reconcile_task_ref(
        self, plan: TurnPlan, disc_ev: dict, active_id: str | None,
    ) -> TurnPlan:
        """Fix task_id / pred_ref desync after topic-LLM soft prior.

        Observed Vertex failure mode: referent clock correct (A.loop1) while
        task_id stayed on a rival (C). Prefer referent owner when it matches the
        I-channel winner or when discrimination kept the gate (winner None/absent
        conflict); otherwise retarget referent onto the bound task.
        """
        if plan.transition in (Transition.CLARIFY, Transition.NEW) or not plan.task_id:
            return plan
        owner = self._referent_owner(plan.pred_ref)
        if not owner or owner == plan.task_id:
            return plan
        open_ids = {t.id for t in plan.open_tasks}
        if owner not in open_ids:
            new_tid = plan.task_id
            new_ref = self._default_referent(plan.task_id, plan.open_tasks)
            reason = "sync_referent_to_task"
        else:
            winner = (disc_ev or {}).get("winner_id")
            if winner in (owner, None):
                new_tid, new_ref, reason = owner, plan.pred_ref, "sync_task_to_referent_owner"
            elif winner == plan.task_id:
                new_tid = plan.task_id
                new_ref = self._default_referent(plan.task_id, plan.open_tasks)
                reason = "sync_referent_to_task"
            else:
                # Discrimination picked a third task — trust task_id, retarget ref.
                new_tid = plan.task_id
                new_ref = self._default_referent(plan.task_id, plan.open_tasks)
                reason = "sync_referent_to_task"

        if new_tid == plan.task_id and new_ref == plan.pred_ref:
            return plan
        if new_tid == active_id:
            tr = Transition.CONTINUE
        elif active_id and new_tid != active_id:
            tr = Transition.RETURN if plan.transition == Transition.RETURN else Transition.SWITCH
        else:
            tr = plan.transition
        return TurnPlan(
            tr, new_tid, plan.pred_task, new_ref,
            {**plan.evidence, "task_ref_sync": reason,
             "task_ref_sync_from": {"task_id": plan.task_id, "pred_ref": plan.pred_ref}},
            plan.decision, plan.open_tasks, plan.candidates,
        )

    def execute_plan(
        self,
        plan: TurnPlan,
        message: str,
        turn: int,
        *,
        generate_answer: bool = True,
    ) -> TurnResult:
        """Apply a routing plan: registry mutations + optional answer generation."""
        if plan.transition == Transition.CLARIFY:
            return self._clarify(
                plan.decision, plan.candidates, plan.pred_task, plan.pred_ref, plan.evidence,
                open_tasks=plan.open_tasks,
            )
        if plan.transition == Transition.NEW:
            return self._new(
                plan.decision, plan.evidence, turn, message,
                generate_answer=generate_answer,
            )
        return self._act(
            plan.decision, plan.task_id, plan.pred_ref, plan.evidence, turn, message,
            plan.open_tasks, generate_answer=generate_answer,
        )

    def complete_answer(self, partial: TurnResult, message: str, turn: int) -> TurnResult:
        """Generate answer+L1 after extract (NEW path: card exists, memory may be fresh)."""
        if partial.transition == Transition.CLARIFY or not partial.task_id:
            return partial
        task = self.reg.get(partial.task_id)
        if task is None:
            return partial
        pred_ref = partial.predicted_referent_id
        loop_text = _loop_text(task, pred_ref)
        open_tasks = self.reg.open_tasks()
        pkg, expose = self._make_package(task, pred_ref, loop_text, message, open_tasks)
        answer = self.llm.generate(self.compiler.render(pkg, message=message))
        return TurnResult(
            partial.transition, partial.task_id, answer, None, pkg, partial.decision,
            partial.predicted_task_id, pred_ref, partial.resolution_evidence,
            l1_expose=expose,
        )

    def handle_turn(self, message: str, turn: int) -> TurnResult:
        plan = self.plan_turn(message, turn)
        return self.execute_plan(plan, message, turn)

    def _clarify(
        self, decision: GateDecision, cands, pred_task, pred_ref, evidence,
        open_tasks: list | None = None,
    ) -> TurnResult:
        # Prefer near-miss pair from discrimination evidence when present.
        disc = (evidence or {}).get("discrimination") or {}
        ids = [disc.get("winner_id"), disc.get("second_id")]
        ids = [i for i in ids if i]
        if len(ids) >= 2:
            q = clarify_question_from_ids(ids, self.reg)
        else:
            q = clarify_question(cands, self.reg)
            if q == "Which task did you mean?" and open_tasks:
                # Fall back to top open cards by last activity
                ranked = sorted(
                    open_tasks,
                    key=lambda t: getattr(t, "last_active_turn", 0),
                    reverse=True,
                )
                q = clarify_question_from_ids([t.id for t in ranked[:2]], self.reg)
        return TurnResult(
            Transition.CLARIFY, None, None,
            q, None, decision,
            pred_task, pred_ref, evidence,
        )

    def _act(self, decision: GateDecision, task_id: Optional[str],
             pred_ref: Optional[str], evidence: dict, turn: int,
             message: str, open_tasks: list, *, generate_answer: bool = True) -> TurnResult:
        if not task_id:
            return TurnResult(
                decision.transition, None, None, None, None, decision,
                task_id, pred_ref, evidence,
            )
        self.reg.mark_active(task_id, turn)
        self.reg.record_mention(task_id, turn, pred_ref)
        self.reg.set_last_selected_referent(pred_ref)
        if not generate_answer:
            return TurnResult(
                decision.transition, task_id, None, None, None, decision,
                task_id, pred_ref, evidence,
            )
        task = self.reg.get(task_id)
        loop_text = _loop_text(task, pred_ref)
        pkg, expose = self._make_package(task, pred_ref, loop_text, message, open_tasks)
        answer = self.llm.generate(self.compiler.render(pkg, message=message))
        self.reg.apply_update(task_id, {})  # legacy no-op; MemoryWriter is the production path
        return TurnResult(
            decision.transition, task_id, answer, None, pkg, decision,
            task_id, pred_ref, evidence, l1_expose=expose,
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

    def _new(
        self,
        decision: GateDecision,
        evidence: dict,
        turn: int,
        message: str,
        *,
        generate_answer: bool = True,
    ) -> TurnResult:
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
        if not generate_answer:
            return TurnResult(
                Transition.NEW, task.id, None, None, None, decision,
                task.id, ref_id, evidence,
            )
        loop_text = _loop_text(task, ref_id)
        pkg, expose = self._make_package(
            task, ref_id, loop_text, message, self.reg.open_tasks(),
        )
        answer = self.llm.generate(self.compiler.render(pkg, message=message))
        return TurnResult(
            Transition.NEW, task.id, answer, None, pkg, decision,
            task.id, ref_id, evidence, l1_expose=expose,
        )
