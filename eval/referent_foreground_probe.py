"""Diagnostic: referent foregrounding vs task similarity.

Not a published benchmark. Does not modify scorer/gate/compiler.
Task cards are frozen (no last_active_turn). Only FOREGROUNDING HISTORY
and registry recency (current engine) change between paired cases.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from app.config import SETTINGS, NEW_ID
from app.engine import Engine
from app.llm.ollama import OllamaLLM
from app.llm.base import validate_proposal
from app.memory.registry import InMemoryRegistry
from app.models.task import Task, TaskAnchor
from app.retrieval.scorer import _tokens
from app.router.proposal import PROPOSAL_SCHEMA


FROZEN_CARDS = (
    "[A] goal: JWT authentication; open_loops: HTTP 401 after token refresh\n"
    "[B] goal: Frontend rendering; open_loops: component renders twice"
)

FROZEN_CARDS_LOOPS = (
    "[A] goal: fix authentication; open_loops: 401 after refresh; expired access token\n"
    "[B] goal: Frontend rendering; open_loops: component renders twice"
)


def _base_tasks(two_loops: bool = False) -> list[Task]:
    if two_loops:
        a = TaskAnchor(goal="fix authentication",
                       open_loops=["401 after refresh", "expired access token"],
                       entities=["JWT"])
        cues_a = ["jwt", "401", "authentication", "token"]
    else:
        a = TaskAnchor(goal="JWT authentication",
                       open_loops=["HTTP 401 after token refresh"],
                       entities=["JWT"])
        cues_a = ["jwt", "401", "authentication", "token"]
    b = TaskAnchor(goal="Frontend rendering",
                   open_loops=["component renders twice"],
                   entities=["React"])
    return [
        Task(id="A", title="jwt auth", status="paused", retrieval_cues=cues_a, anchor=a),
        Task(id="B", title="frontend", status="paused", retrieval_cues=["react", "render"],
             anchor=b),
    ]


def frozen_prompt(message: str, history: list[str], cards: str) -> str:
    hist = "\n".join(f"{i+1}. {h}" for i, h in enumerate(history))
    return (
        "You route a user message to one of the user's open tasks.\n"
        "Task cards are identical across histories. Use FOREGROUNDING HISTORY\n"
        "(most recent last) plus open loops to decide what 'that' refers to.\n"
        "task_id must be exactly A or B, or null. confidence is uncalibrated.\n"
        "referent should name the task or open loop being pointed at.\n\n"
        f"OPEN TASK CARDS:\n{cards}\n\n"
        f"FOREGROUNDING HISTORY (most recent last):\n{hist}\n\n"
        f'MESSAGE: "{message}"\n\n'
        "Return JSON: {task_id, is_new_task, confidence, referent, rationale}"
    )


class ProbeLLM:
    """Delegates to Ollama or injects a fixed proposal. generate is stubbed."""

    def __init__(self, inner: OllamaLLM, prompt: str | None = None,
                 injected: dict | None = None):
        self.inner = inner
        self.prompt = prompt
        self.injected = injected
        self.last_proposal: dict | None = None
        self.last_propose_latency_s = 0.0

    def propose(self, prompt: str, schema: dict) -> dict:
        if self.injected is not None:
            self.last_proposal = dict(self.injected)
            self.last_propose_latency_s = 0.0
            return self.last_proposal
        raw = self.inner.propose(self.prompt if self.prompt is not None else prompt, schema)
        self.last_proposal = raw
        self.last_propose_latency_s = self.inner.last_propose_latency_s
        return raw

    def generate(self, prompt: str) -> str:
        return "[diagnostic: answer skipped]"

    def embed(self, texts: list[str]):
        return self.inner.embed(texts)


def apply_foreground(reg: InMemoryRegistry, order: list[str]) -> None:
    """order is task ids discussed, most recent last. Does not change goals/loops."""
    for i, tid in enumerate(order, start=1):
        reg.mark_active(tid, i)


def infer_referent(message: str, task: Task | None) -> str | None:
    """Diagnostic only — not a product resolver. Token overlap with open loops."""
    if task is None:
        return None
    loops = task.anchor.open_loops
    if not loops:
        return task.id
    msg = _tokens(message)
    best_i, best_n = 0, -1
    for i, loop in enumerate(loops):
        n = len(_tokens(loop) & msg)
        if n > best_n:
            best_n, best_i = n, i
    if best_n <= 0:
        return task.id
    return f"{task.id}:loop{best_i + 1}"


def registry_from(tasks: list[Task], order: list[str]) -> InMemoryRegistry:
    r = InMemoryRegistry()
    for t in tasks:
        r.add(Task(id=t.id, title=t.title, status="paused",
                   retrieval_cues=list(t.retrieval_cues),
                   anchor=TaskAnchor(goal=t.anchor.goal,
                                     open_loops=list(t.anchor.open_loops),
                                     entities=list(t.anchor.entities))))
    apply_foreground(r, order)
    return r


@dataclass
class Case:
    name: str
    message: str
    history: list[str]
    order: list[str]
    gold_task_id: str
    gold_referent_id: str
    cards: str
    two_loops: bool = False
    injected: dict | None = None


def run_case(inner: OllamaLLM, case: Case, turn: int) -> dict:
    tasks = _base_tasks(two_loops=case.two_loops)
    prompt = frozen_prompt(case.message, case.history, case.cards)
    llm = ProbeLLM(inner, prompt=prompt, injected=case.injected)
    reg = registry_from(tasks, case.order)
    eng = Engine(llm, reg, SETTINGS, mode="split")
    t0 = time.perf_counter()
    res = eng.handle_turn(case.message, turn)
    proposal = validate_proposal(llm.last_proposal or {})
    cf_task = res.task_id
    cf_task_obj = reg.get(cf_task) if cf_task else None
    llm_task = proposal.task_id
    llm_wrong = (llm_task != case.gold_task_id)
    acted = res.transition.value != "CLARIFY"
    cf_ok = acted and cf_task == case.gold_task_id
    invalid = llm_task not in (None, "A", "B")
    missing = llm_task is None
    recovered = False
    if llm_wrong:
        if invalid or missing:
            recovered = not acted  # safe reject
        else:
            recovered = cf_ok
    d = res.decision
    return {
        "provider": "ollama" if case.injected is None else "injected",
        "model": inner.model,
        "case": case.name,
        "message": case.message,
        "gold_task_id": case.gold_task_id,
        "gold_referent_id": case.gold_referent_id,
        "llm_task_id": llm_task,
        "llm_confidence": proposal.confidence,
        "llm_referent": proposal.referent,
        "llm_rationale": proposal.rationale,
        "contextflow_task_id": cf_task,
        "contextflow_referent_id": infer_referent(case.message, cf_task_obj),
        "gate_decision": d.transition.value,
        "raw_top": round(d.top_raw, 4),
        "raw_margin": round(d.raw_margin, 4),
        "open_task_count": d.open_task_count,
        "whether_llm_was_wrong": llm_wrong,
        "whether_contextflow_recovered": recovered,
        "acted": acted,
        "cf_correct": cf_ok,
        "latency_s": round(time.perf_counter() - t0, 3),
        "propose_latency_s": round(llm.last_propose_latency_s, 3),
        "injected": case.injected is not None,
        "invalid_llm_id": invalid,
        "history": case.history,
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    llm_acc = sum(not r["whether_llm_was_wrong"] for r in rows) / n
    cf_acc = sum(r["cf_correct"] for r in rows) / n
    wrong = [r for r in rows if r["whether_llm_was_wrong"]]
    rec = (sum(r["whether_contextflow_recovered"] for r in wrong) / len(wrong)
           if wrong else None)
    acted = [r for r in rows if r["acted"]]
    wrong_act = (sum(not r["cf_correct"] for r in acted) / len(acted)
                 if acted else None)
    clarify = sum(not r["acted"] for r in rows) / n
    return {
        "n": n,
        "llm_proposal_accuracy": round(llm_acc, 3),
        "contextflow_final_accuracy": round(cf_acc, 3),
        "llm_to_contextflow_recovery_rate": None if rec is None else round(rec, 3),
        "wrong_confident_action_rate": None if wrong_act is None else round(wrong_act, 3),
        "clarification_rate": round(clarify, 3),
        "note": (
            "Diagnostic only. contextflow_referent_id is token-overlap with "
            "open loops, not a product resolver. Cards frozen; engine recency "
            "still uses last_active_turn internally."
        ),
    }


def cases() -> list[Case]:
    h_b = [
        "discussed task A (JWT authentication / 401 after refresh)",
        "discussed task A (JWT authentication / 401 after refresh)",
        "discussed task B (frontend rendering / component renders twice)",
    ]
    h_a = [
        "discussed task A (JWT authentication / 401 after refresh)",
        "discussed task B (frontend rendering / component renders twice)",
        "discussed task A (JWT authentication / 401 after refresh)",
    ]
    h_loop2 = [
        "discussed task A open loop: 401 after refresh",
        "discussed task B (frontend rendering)",
        "discussed task A open loop: expired access token",
    ]
    out = [
        Case("pair_fix_that_foreground_B", "fix that", h_b, ["A", "A", "B"],
             "B", "B:loop1", FROZEN_CARDS),
        Case("pair_fix_that_foreground_A", "fix that", h_a, ["A", "B", "A"],
             "A", "A:loop1", FROZEN_CARDS),
        Case("explicit_auth_after_B", "fix that authentication thing", h_b, ["A", "A", "B"],
             "A", "A:loop1", FROZEN_CARDS),
        Case("explicit_component_after_A", "the component still renders twice", h_a,
             ["A", "B", "A"], "B", "B:loop1", FROZEN_CARDS),
        Case("vague_after_B", "fix that", h_b, ["A", "A", "B"], "B", "B:loop1", FROZEN_CARDS),
        Case("vague_after_A", "fix that", h_a, ["A", "B", "A"], "A", "A:loop1", FROZEN_CARDS),
        Case("competing_loops_fix_that", "fix that", h_loop2, ["A", "B", "A"],
             "A", "A:loop2", FROZEN_CARDS_LOOPS, two_loops=True),
        Case("competing_loops_401", "still getting 401 after refresh", h_loop2, ["A", "B", "A"],
             "A", "A:loop1", FROZEN_CARDS_LOOPS, two_loops=True),
        Case("competing_loops_expired", "the access token is expired", h_loop2, ["A", "B", "A"],
             "A", "A:loop2", FROZEN_CARDS_LOOPS, two_loops=True),
        Case("fail_invalid_id", "fix that", h_a, ["A", "B", "A"], "A", "A:loop1",
             FROZEN_CARDS, injected={"task_id": "NOT_A_TASK", "is_new_task": False,
                                     "confidence": 0.99, "referent": "x", "rationale": "inject"}),
        Case("fail_missing_id", "fix that", h_a, ["A", "B", "A"], "A", "A:loop1",
             FROZEN_CARDS, injected={"task_id": None, "is_new_task": False,
                                     "confidence": 0.0, "referent": None, "rationale": "inject"}),
        Case("fail_wrong_id_high_conf", "fix that", h_a, ["A", "B", "A"], "A", "A:loop1",
             FROZEN_CARDS, injected={"task_id": "B", "is_new_task": False,
                                     "confidence": 0.95, "referent": "frontend",
                                     "rationale": "inject"}),
        Case("fail_wrong_id_auth_msg", "fix that authentication thing", h_b, ["A", "A", "B"],
             "A", "A:loop1", FROZEN_CARDS,
             injected={"task_id": "B", "is_new_task": False, "confidence": 0.97,
                       "referent": "frontend", "rationale": "inject"}),
    ]
    return out


def main():
    inner = OllamaLLM()
    rows = []
    for i, case in enumerate(cases(), start=10):
        rec = run_case(inner, case, turn=i)
        rows.append(rec)
        print(json.dumps(rec, indent=2))
    live = [r for r in rows if not r["injected"]]
    injected = [r for r in rows if r["injected"]]
    print("\n=== SUMMARY LIVE OLLAMA ===")
    print(json.dumps(summarize(live), indent=2))
    print("\n=== SUMMARY INJECTED FAILURES ===")
    print(json.dumps(summarize(injected), indent=2))
    print("\n=== SUMMARY ALL ===")
    print(json.dumps(summarize(rows), indent=2))
    return rows


if __name__ == "__main__":
    main()
