"""Isolated CURRENT vs mention-clock referent probe. Does not modify app/ production."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Optional

from app.config import SETTINGS
from app.domain import Transition
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.registry import InMemoryRegistry
from app.models.task import Task, TaskAnchor
from app.router.proposal import propose
from app.retrieval.scorer import _tokens


@dataclass
class LoopSpec:
    loop_id: str
    text: str


@dataclass
class TaskSpec:
    task_id: str
    title: str
    goal: str
    loops: list[LoopSpec]
    cues: list[str]


@dataclass
class Mention:
    task_id: str
    loop_id: str
    turn: int


@dataclass
class Scenario:
    scenario_id: str
    tasks: list[TaskSpec]
    mentions: list[Mention]
    message: str
    gold_task: str
    gold_referent: str
    prior_pred_referent: Optional[str] = None


@dataclass
class Resolution:
    pred_task: Optional[str]
    pred_referent: Optional[str]
    evidence: dict
    decision: str  # ACT | CLARIFY


class InjectLLM:
    def __init__(self, embed_src, proposal: dict):
        self._embed_src = embed_src
        self.proposal = proposal

    def propose(self, prompt: str, schema: dict) -> dict:
        return dict(self.proposal)

    def generate(self, prompt: str) -> str:
        return "[probe: answer skipped]"

    def embed(self, texts: list[str]):
        return self._embed_src.embed(texts)


def _tok(s: str) -> set[str]:
    return _tokens(s)


def _build_tasks(specs: list[TaskSpec]) -> list[Task]:
    out = []
    for s in specs:
        out.append(Task(
            id=s.task_id, title=s.title, status="paused",
            retrieval_cues=list(s.cues),
            anchor=TaskAnchor(goal=s.goal, open_loops=[lp.text for lp in s.loops]),
        ))
    return out


def jwt_frontend() -> list[TaskSpec]:
    return [
        TaskSpec("A", "jwt auth", "JWT authentication",
                 [LoopSpec("A.loop1", "HTTP 401 after token refresh")],
                 ["jwt", "401", "authentication", "token"]),
        TaskSpec("B", "frontend", "Frontend rendering",
                 [LoopSpec("B.loop1", "component renders twice")],
                 ["react", "render", "component"]),
    ]


def two_loops_a() -> list[TaskSpec]:
    return [
        TaskSpec("A", "auth", "fix authentication",
                 [LoopSpec("A.loop1", "HTTP 401 after refresh"),
                  LoopSpec("A.loop2", "expired access token")],
                 ["jwt", "401", "authentication", "token"]),
        TaskSpec("B", "frontend", "Frontend rendering",
                 [LoopSpec("B.loop1", "component renders twice")],
                 ["react", "render"]),
    ]


def jwt_oauth() -> list[TaskSpec]:
    return [
        TaskSpec("JWT", "jwt", "fix JWT authentication",
                 [LoopSpec("JWT.loop1", "JWT token not verified")],
                 ["jwt", "token", "authentication"]),
        TaskSpec("OAuth", "oauth", "fix OAuth authentication",
                 [LoopSpec("OAuth.loop1", "OAuth redirect fails")],
                 ["oauth", "redirect", "authentication"]),
    ]


def scenarios() -> list[Scenario]:
    jf, tl, jo = jwt_frontend(), two_loops_a(), jwt_oauth()
    return [
        Scenario("A1", jf, [Mention("A", "A.loop1", 1), Mention("A", "A.loop1", 2),
                            Mention("B", "B.loop1", 3)], "fix that", "B", "B.loop1"),
        Scenario("A2", jf, [Mention("A", "A.loop1", 1), Mention("B", "B.loop1", 2),
                            Mention("A", "A.loop1", 3)], "fix that", "A", "A.loop1"),
        Scenario("B1", tl, [Mention("A", "A.loop1", 1), Mention("B", "B.loop1", 2),
                            Mention("A", "A.loop1", 3)], "fix that", "A", "A.loop1"),
        Scenario("B2", tl, [Mention("A", "A.loop1", 1), Mention("B", "B.loop1", 2),
                            Mention("A", "A.loop2", 3)], "fix that", "A", "A.loop2"),
        Scenario("C1", jf, [Mention("A", "A.loop1", 1), Mention("A", "A.loop1", 2),
                            Mention("B", "B.loop1", 3)], "fix that authentication thing",
                 "A", "A.loop1"),
        Scenario("C2", jf, [Mention("A", "A.loop1", 1), Mention("B", "B.loop1", 2),
                            Mention("A", "A.loop1", 3)], "the component still renders twice",
                 "B", "B.loop1"),
        Scenario("D1", jf, [Mention("A", "A.loop1", 1), Mention("B", "B.loop1", 2),
                            Mention("A", "A.loop1", 3)], "no, the other one",
                 "B", "B.loop1", prior_pred_referent="A.loop1"),
        Scenario("E1", jo, [Mention("JWT", "JWT.loop1", 1), Mention("OAuth", "OAuth.loop1", 2)],
                 "fix that", "OAuth", "OAuth.loop1"),
        Scenario("F1", tl, [Mention("A", "A.loop2", 1), Mention("B", "B.loop1", 2),
                            Mention("A", "A.loop2", 3)], "the 401", "A", "A.loop1"),
        Scenario("F2", tl, [Mention("A", "A.loop1", 1), Mention("B", "B.loop1", 2),
                            Mention("A", "A.loop2", 3)], "fix that", "A", "A.loop2"),
    ]


def classify_utterance(message: str) -> str:
    m = message.strip().lower()
    if re.search(r"\b(other one|the other)\b", m) or re.match(r"^no[, ]", m):
        return "correction"
    if re.fullmatch(r"(fix |do |please )?(that|it|this)[\.\!]*", m):
        return "deictic"
    lex = ("authentication", "401", "component", "renders", "oauth", "jwt",
           "expired", "refresh", "redirect")
    if any(k in m for k in lex):
        return "explicit"
    if re.search(r"\b(that|it|this)\b", m):
        return "deictic"
    return "explicit"


def all_referents(specs: list[TaskSpec]) -> list[tuple[str, str, str]]:
    """(task_id, referent_id, text)"""
    rows = []
    for s in specs:
        for lp in s.loops:
            rows.append((s.task_id, lp.loop_id, lp.text + " " + s.goal))
    return rows


def mention_clocks(mentions: list[Mention]) -> dict[str, int]:
    clocks: dict[str, int] = {}
    for m in mentions:
        clocks[m.task_id] = m.turn
        clocks[m.loop_id] = m.turn
    return clocks


def system_b_resolve(sc: Scenario, llm_task: Optional[str]) -> Resolution:
    kind = classify_utterance(sc.message)
    refs = all_referents(sc.tasks)
    clocks = mention_clocks(sc.mentions)
    msg_t = _tok(sc.message)
    evidence = {"kind": kind, "llm_task_soft": llm_task, "clocks": dict(clocks)}

    if kind == "correction":
        alts = [r[1] for r in refs if r[1] != sc.prior_pred_referent]
        if len(alts) == 1:
            tid = next(r[0] for r in refs if r[1] == alts[0])
            return Resolution(tid, alts[0], {**evidence, "rule": "correction_unique"}, "ACT")
        if sc.prior_pred_referent:
            ranked = sorted(refs, key=lambda r: clocks.get(r[1], 0), reverse=True)
            for t, rid, _ in ranked:
                if rid != sc.prior_pred_referent:
                    return Resolution(t, rid, {**evidence, "rule": "correction_exclude_prior"}, "ACT")
        return Resolution(None, None, {**evidence, "rule": "correction_ambiguous"}, "CLARIFY")

    scored = []
    for tid, rid, text in refs:
        overlap = len(msg_t & _tok(text))
        scored.append((overlap, clocks.get(rid, 0), clocks.get(tid, 0), tid, rid))

    if kind == "explicit":
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        best = scored[0]
        evidence["lexical"] = [(s[4], s[0], s[1]) for s in scored]
        if best[0] > 0:
            if len(scored) > 1 and scored[1][0] == best[0]:
                return Resolution(best[3], best[4], {**evidence, "rule": "lexical_tie"}, "CLARIFY")
            return Resolution(best[3], best[4], {**evidence, "rule": "lexical"}, "ACT")
        evidence["lexical_miss"] = True

    # deictic: mention clocks primary; LLM task is tie-break / weak
    scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
    best, runner = scored[0], scored[1] if len(scored) > 1 else scored[0]
    evidence["ranked_clocks"] = [(s[4], s[1]) for s in scored]
    if best[1] == runner[1] and best[4] != runner[4]:
        if llm_task:
            for s in scored:
                if s[3] == llm_task and s[1] == best[1]:
                    return Resolution(s[3], s[4], {**evidence, "rule": "deictic_llm_tiebreak"}, "CLARIFY")
        return Resolution(best[3], best[4], {**evidence, "rule": "deictic_tie"}, "CLARIFY")
    # unique max clock: LLM cannot override
    return Resolution(best[3], best[4], {**evidence, "rule": "deictic_clock"}, "ACT")


def registry_current(sc: Scenario) -> InMemoryRegistry:
    r = InMemoryRegistry()
    for t in _build_tasks(sc.tasks):
        r.add(t)
    for m in sc.mentions:
        r.record_mention(m.task_id, m.turn, m.loop_id)
        r.mark_active(m.task_id, m.turn)
    if sc.prior_pred_referent:
        r.set_last_selected_referent(sc.prior_pred_referent)
    return r


def system_a_resolve(sc: Scenario, llm, proposal: dict) -> Resolution:
    reg = registry_current(sc)
    wrapped = InjectLLM(llm, proposal)
    eng = Engine(wrapped, reg, SETTINGS, mode="split")
    turn = max(m.turn for m in sc.mentions) + 1
    res = eng.handle_turn(sc.message, turn)
    pred_task = res.predicted_task_id
    pred_ref = res.predicted_referent_id
    decision = "CLARIFY" if res.transition == Transition.CLARIFY else "ACT"
    return Resolution(pred_task, pred_ref, {
        "system": "A_engine",
        "gate": res.transition.value,
        "top_raw": res.decision.top_raw,
        "resolution_evidence": res.resolution_evidence,
    }, decision)


def row_for(sc: Scenario, system: str, llm_task, res: Resolution) -> dict:
    llm_error = llm_task != sc.gold_task
    joint = res.pred_task == sc.gold_task and res.pred_referent == sc.gold_referent
    task_ok = res.pred_task == sc.gold_task
    ref_ok = res.pred_referent == sc.gold_referent
    acted = res.decision == "ACT"
    wrong_action = acted and not joint
    recovered = bool(llm_error and joint)
    return {
        "scenario_id": sc.scenario_id,
        "system": system,
        "gold_task": sc.gold_task,
        "gold_referent": sc.gold_referent,
        "llm_task": llm_task,
        "pred_task": res.pred_task,
        "pred_referent": res.pred_referent,
        "resolution_correct": task_ok,
        "referent_correct": ref_ok,
        "joint_correct": joint,
        "decision": res.decision,
        "wrong_action": wrong_action,
        "llm_error": llm_error,
        "llm_error_recovered": recovered,
        "evidence": res.evidence,
    }


def summarize(rows: list[dict], system: str) -> dict:
    rs = [r for r in rows if r["system"] == system]
    n = len(rs) or 1
    acted = [r for r in rs if r["decision"] == "ACT"]
    llm_err = [r for r in rs if r["llm_error"]]
    return {
        "system": system,
        "n": len(rs),
        "task_resolution_accuracy": round(sum(r["resolution_correct"] for r in rs) / n, 3),
        "referent_resolution_accuracy": round(sum(r["referent_correct"] for r in rs) / n, 3),
        "joint_resolution_accuracy": round(sum(r["joint_correct"] for r in rs) / n, 3),
        "clarification_rate": round(sum(r["decision"] == "CLARIFY" for r in rs) / n, 3),
        "wrong_action_rate": round(sum(r["wrong_action"] for r in acted) / len(acted), 3) if acted else None,
        "llm_error_recovery_rate": round(sum(r["llm_error_recovered"] for r in llm_err) / len(llm_err), 3) if llm_err else None,
        "n_llm_errors": len(llm_err),
    }


def mock_wrong_llm() -> MockLLM:
    """Deterministic LLM that is often wrong — used to measure recovery."""
    return MockLLM({
        "authentication thing": {
            "task_id": "B", "is_new_task": False, "confidence": 0.92,
            "referent": None, "rationale": "mock-wrong-C1",
        },
        "renders twice": {
            "task_id": "A", "is_new_task": False, "confidence": 0.92,
            "referent": None, "rationale": "mock-wrong-C2",
        },
        "other one": {
            "task_id": "A", "is_new_task": False, "confidence": 0.92,
            "referent": None, "rationale": "mock-wrong-D1",
        },
        "the 401": {
            "task_id": "B", "is_new_task": False, "confidence": 0.92,
            "referent": None, "rationale": "mock-wrong-F1",
        },
        "fix that": {
            "task_id": "A", "is_new_task": False, "confidence": 0.95,
            "referent": None, "rationale": "mock-always-A",
        },
    })


def run_suite(llm, label: str) -> list[dict]:
    rows = []
    for sc in scenarios():
        reg = registry_current(sc)
        proposal = propose(llm, sc.message, reg.open_tasks())
        raw = {"task_id": proposal.task_id, "is_new_task": proposal.is_new_task,
               "confidence": proposal.confidence, "referent": proposal.referent,
               "rationale": proposal.rationale}
        llm_task = proposal.task_id
        a = system_a_resolve(sc, llm, raw)
        b = system_b_resolve(sc, llm_task)
        rows.append(row_for(sc, "A_current", llm_task, a))
        rows.append(row_for(sc, "B_referent", llm_task, b))
    return rows


CSV_FIELDS = [
    "scenario_id", "system", "gold_task", "gold_referent", "llm_task",
    "pred_task", "pred_referent", "resolution_correct", "referent_correct",
    "joint_correct", "decision", "wrong_action", "llm_error", "llm_error_recovered",
]


def paired_preds(rows: list[dict], sid: str, system: str) -> tuple:
    r = next(x for x in rows if x["scenario_id"] == sid and x["system"] == system)
    return r["pred_task"], r["pred_referent"]


def falsifiers(rows: list[dict]) -> dict:
    b = "B_referent"
    a = "A_current"
    a1t, a1r = paired_preds(rows, "A1", b)
    a2t, a2r = paired_preds(rows, "A2", b)
    b1t, b1r = paired_preds(rows, "B1", b)
    b2t, b2r = paired_preds(rows, "B2", b)
    sa, sb = summarize(rows, a), summarize(rows, b)
    return {
        "A1_A2_identical_despite_swapped_foreground": (a1t, a1r) == (a2t, a2r),
        "B1_B2_identical_despite_swapped_loop_foreground": (b1t, b1r) == (b2t, b2r),
        "task_accuracy_improves_but_referent_does_not": (
            sb["task_resolution_accuracy"] > sa["task_resolution_accuracy"]
            and sb["referent_resolution_accuracy"] <= sa["referent_resolution_accuracy"]
        ),
        "referent_improves_but_task_selection_does_not": (
            sb["referent_resolution_accuracy"] > sa["referent_resolution_accuracy"]
            and sb["task_resolution_accuracy"] <= sa["task_resolution_accuracy"]
        ),
        "llm_error_recovery_approximately_zero": (sb["llm_error_recovery_rate"] or 0) < 0.05,
        "current_system_performs_equally_well": (
            sb["joint_resolution_accuracy"] <= sa["joint_resolution_accuracy"]
        ),
        "requires_heavy_new_state": False,
        "notes": {
            "system_A_referent": "production Engine mention clocks + derived resolver",
            "system_B_state": "isolated probe resolver (same rules)",
        },
    }


def write_results(rows: list[dict], json_path: str, csv_path: str | None = None) -> None:
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    payload = {
        "rows": rows,
        "summary": [summarize(rows, "A_current"), summarize(rows, "B_referent")],
        "falsifiers": falsifiers(rows),
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    if csv_path:
        import csv
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in CSV_FIELDS})


def print_summary(rows: list[dict]) -> None:
    print("\nscenario  gold          A_task/A_ref/A_dec     B_task/B_ref/B_dec     llm")
    ids = []
    for r in rows:
        if r["scenario_id"] not in ids:
            ids.append(r["scenario_id"])
    for sid in ids:
        a = next(x for x in rows if x["scenario_id"] == sid and x["system"] == "A_current")
        b = next(x for x in rows if x["scenario_id"] == sid and x["system"] == "B_referent")
        print(f"{sid:4}  {a['gold_task']}/{a['gold_referent']:12}  "
              f"{str(a['pred_task'])}/{str(a['pred_referent']):12}/{a['decision']:7}  "
              f"{str(b['pred_task'])}/{str(b['pred_referent']):12}/{b['decision']:7}  "
              f"llm={a['llm_task']}")
    print("\n", json.dumps([summarize(rows, "A_current"), summarize(rows, "B_referent")], indent=2))
