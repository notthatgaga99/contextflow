"""Context sufficiency experiment. Not a benchmark. Does not change production routing."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from app.config import SETTINGS
from app.context.compiler import ContextCompiler
from app.domain import Transition
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.registry import InMemoryRegistry
from app.models.context import FULL_TASK, MERGED_COMPACT, REFERENT_COMPACT
from app.models.task import Task, TaskAnchor
from app.router.referent import loop_index_from_id


MODES = (
    ("full", FULL_TASK),
    ("split", REFERENT_COMPACT),
    ("merged", MERGED_COMPACT),
)


@dataclass
class SufficiencyScenario:
    scenario_id: str
    tasks: list[Task]
    mentions: list[tuple[str, str, int]]
    message: str
    gold_task: str
    gold_referent: str
    probe: str
    expect_any: list[str]
    wrong_loop_any: list[str] = field(default_factory=list)
    wrong_task_any: list[str] = field(default_factory=list)


def _task(
    tid: str,
    title: str,
    goal: str,
    loops: list[str],
    cues: list[str],
    decisions: list[str] | None = None,
    constraints: list[str] | None = None,
    entities: list[str] | None = None,
) -> Task:
    a = TaskAnchor(goal=goal, open_loops=list(loops))
    if decisions:
        a.decisions = list(decisions)
    if constraints:
        a.constraints = list(constraints)
    if entities:
        a.entities = list(entities)
    return Task(id=tid, title=title, status="paused", retrieval_cues=list(cues), anchor=a)


def _three_loop_a() -> Task:
    return _task(
        "A", "auth", "fix authentication and release",
        [
            "JWT 401 after page refresh",
            "expired access token",
            "deployment pipeline failing",
        ],
        ["jwt", "401", "token", "deploy"],
        decisions=["token refresh lives in middleware"],
        constraints=["do not change the public API"],
        entities=["JWT middleware"],
    )


def _frontend_b() -> Task:
    return _task(
        "B", "frontend", "Frontend rendering",
        ["React component renders twice"],
        ["react", "render", "component"],
        entities=["React StrictMode"],
    )


def scenarios() -> list[SufficiencyScenario]:
    a3, b = _three_loop_a(), _frontend_b()
    return [
        SufficiencyScenario(
            "S1_resume_loop1", [a3, b],
            [("A", "A.loop1", 1), ("B", "B.loop1", 2), ("A", "A.loop1", 3)],
            "fix that", "A", "A.loop1",
            "What symptom is being investigated?",
            ["401", "refresh"],
            wrong_loop_any=["expired access", "deployment"],
            wrong_task_any=["renders twice", "strictmode"],
        ),
        SufficiencyScenario(
            "S2_resume_loop2", [a3, b],
            [("A", "A.loop1", 1), ("B", "B.loop1", 2), ("A", "A.loop2", 3)],
            "fix that", "A", "A.loop2",
            "What should be investigated first?",
            ["expired", "access token", "middleware"],
            wrong_loop_any=["401", "deployment"],
            wrong_task_any=["renders twice"],
        ),
        SufficiencyScenario(
            "S3_resume_loop3", [a3, b],
            [("A", "A.loop1", 1), ("B", "B.loop1", 2), ("A", "A.loop3", 3)],
            "fix that", "A", "A.loop3",
            "What is failing?",
            ["deployment", "pipeline"],
            wrong_loop_any=["401", "expired access"],
            wrong_task_any=["renders twice"],
        ),
        SufficiencyScenario(
            "S4_b_while_a_active", [a3, b],
            [("A", "A.loop1", 1), ("A", "A.loop1", 2), ("B", "B.loop1", 3)],
            "fix that", "B", "B.loop1",
            "What UI issue is being investigated?",
            ["renders twice", "component", "react"],
            wrong_loop_any=[],
            wrong_task_any=["401", "expired", "deployment", "jwt"],
        ),
        SufficiencyScenario(
            "S5_similar_oauth_loops",
            [_task(
                "A", "oauth", "fix OAuth authentication",
                ["OAuth redirect URI mismatch", "OAuth refresh token rotation"],
                ["oauth", "redirect", "refresh"],
                entities=["authorization server"],
            ), b],
            [("A", "A.loop1", 1), ("B", "B.loop1", 2), ("A", "A.loop2", 3)],
            "fix that", "A", "A.loop2",
            "Which OAuth issue is in focus?",
            ["refresh token", "rotation"],
            wrong_loop_any=["redirect", "uri mismatch"],
            wrong_task_any=["renders twice"],
        ),
        SufficiencyScenario(
            "S6_different_entities",
            [_task(
                "A", "infra", "stabilize checkout path",
                ["Stripe webhook signature rejected", "Redis cache stampede on catalog"],
                ["stripe", "redis", "cache"],
                entities=["checkout service"],
            ), b],
            [("A", "A.loop1", 1), ("B", "B.loop1", 2), ("A", "A.loop2", 3)],
            "fix that", "A", "A.loop2",
            "Which component is in focus?",
            ["redis", "cache", "stampede"],
            wrong_loop_any=["stripe", "webhook"],
            wrong_task_any=["renders twice"],
        ),
        SufficiencyScenario(
            "S7_deictic_fix_that", [a3, b],
            [("A", "A.loop1", 1), ("B", "B.loop1", 2), ("A", "A.loop2", 3)],
            "fix that", "A", "A.loop2",
            "What token problem is in focus?",
            ["expired", "access token"],
            wrong_loop_any=["401", "deployment"],
            wrong_task_any=["renders twice"],
        ),
        SufficiencyScenario(
            "S8_explicit_401", [a3, b],
            [("A", "A.loop2", 1), ("B", "B.loop1", 2), ("A", "A.loop2", 3)],
            "the 401", "A", "A.loop1",
            "What HTTP status is the issue?",
            ["401"],
            wrong_loop_any=["expired access", "deployment"],
            wrong_task_any=["renders twice"],
        ),
        SufficiencyScenario(
            "S9_single_loop",
            [_task(
                "A", "slides", "prepare slide deck",
                ["write closing slide"],
                ["slide", "deck"],
                entities=["architecture diagram"],
            )],
            [("A", "A.loop1", 1)],
            "fix that", "A", "A.loop1",
            "Which slide is unfinished?",
            ["closing slide", "closing"],
            wrong_loop_any=[],
            wrong_task_any=[],
        ),
        SufficiencyScenario(
            "S10_tempting_keywords",
            [_task(
                "A", "session", "fix browser session handling",
                [
                    "session cookie SameSite not set",
                    "JWT 401 authentication token refresh",
                    "OAuth login button missing",
                ],
                ["cookie", "samesite", "session"],
                entities=["browser cookie jar"],
            ), b],
            [("A", "A.loop1", 1), ("B", "B.loop1", 2), ("A", "A.loop1", 3)],
            "fix that", "A", "A.loop1",
            "What cookie setting is being investigated?",
            ["samesite", "cookie", "session"],
            wrong_loop_any=["401", "jwt", "oauth", "login button"],
            wrong_task_any=["renders twice"],
        ),
    ]


def router_llm() -> MockLLM:
    """Deterministic routing only. Same scripts as the referent tests."""
    return MockLLM({
        "the 401": {
            "task_id": "B", "is_new_task": False, "confidence": 0.92,
            "referent": None, "rationale": "wrong-lexical",
        },
        "fix that": {
            "task_id": "A", "is_new_task": False, "confidence": 0.95,
            "referent": None, "rationale": "always-A",
        },
    })


def seed(reg: InMemoryRegistry, sc: SufficiencyScenario) -> None:
    for t in sc.tasks:
        # fresh copies so scenario list can be reused
        reg.add(_task(
            t.id, t.title, t.anchor.goal, list(t.anchor.open_loops),
            list(t.retrieval_cues), list(t.anchor.decisions),
            list(t.anchor.constraints), list(t.anchor.entities),
        ))
    for task_id, loop_id, turn in sc.mentions:
        reg.record_mention(task_id, turn, loop_id)
        reg.mark_active(task_id, turn)


def build_registry(sc: SufficiencyScenario) -> InMemoryRegistry:
    r = InMemoryRegistry()
    seed(r, sc)
    return r


def loop_text(task: Task, referent_id: Optional[str]) -> Optional[str]:
    if not referent_id:
        return None
    idx = loop_index_from_id(task.id, referent_id)
    if idx is None or idx >= len(task.anchor.open_loops):
        return None
    return task.anchor.open_loops[idx]


def _hit(text: str, needles: list[str]) -> bool:
    if not needles:
        return False
    low = text.lower()
    return any(n.lower() in low for n in needles)


def score_answer(answer: str, sc: SufficiencyScenario) -> dict:
    hit = _hit(answer, sc.expect_any)
    wrong_loop = _hit(answer, sc.wrong_loop_any)
    wrong_task = _hit(answer, sc.wrong_task_any)
    correct = hit and not wrong_loop and not wrong_task
    if correct:
        score = 1.0
    elif hit:
        score = 0.5
    else:
        score = 0.0
    return {
        "answer_correct": correct,
        "answer_score": score,
        "wrong_loop": wrong_loop,
        "wrong_task": wrong_task,
        "checkable_probe_result": "pass" if correct else ("partial" if hit else "fail"),
    }


def classify_compact_failure(
    sc: SufficiencyScenario,
    pred_task: Optional[str],
    pred_ref: Optional[str],
    compact_pkg,
    full_pkg,
    compact_correct: bool,
    full_correct: bool,
    compact_answer: str,
) -> Optional[str]:
    """Return A–G or None if compact did not fail."""
    if compact_correct:
        return None
    if pred_task != sc.gold_task or pred_ref != sc.gold_referent:
        return "F"
    gold_task_obj = next((t for t in sc.tasks if t.id == sc.gold_task), None)
    gold_loop = loop_text(gold_task_obj, sc.gold_referent) if gold_task_obj else None
    compact_txt = ContextCompiler().render(compact_pkg)
    full_txt = ContextCompiler().render(full_pkg)
    if gold_loop and gold_loop not in compact_txt:
        if gold_loop in full_txt:
            return "G"
        return "B"
    need_missing = [k for k in sc.expect_any if k.lower() not in compact_txt.lower()]
    if need_missing and full_correct and not compact_correct:
        task_level = " ".join([
            gold_task_obj.anchor.goal if gold_task_obj else "",
            " ".join(gold_task_obj.anchor.decisions) if gold_task_obj else "",
            " ".join(gold_task_obj.anchor.entities) if gold_task_obj else "",
        ]).lower()
        in_other_loops = any(k.lower() not in task_level and k.lower() in full_txt.lower() for k in need_missing)
        if in_other_loops:
            return "C"
        if any(k.lower() not in compact_txt.lower() for k in need_missing):
            return "A"
    if not any(k.lower() in compact_txt.lower() for k in sc.expect_any):
        return "E"
    if full_correct and not compact_correct:
        return "D"
    if not full_correct and not compact_correct:
        if not any(k.lower() in compact_txt.lower() for k in sc.expect_any):
            return "E"
        return "D"
    return "D"


class EchoSelectedMock(MockLLM):
    """Answers from SELECTED LOOP / OPEN LOOPS. Checks construction, not model skill."""

    def generate(self, prompt: str) -> str:
        m = re.search(r"SELECTED LOOP:\s*(.+)", prompt)
        if m:
            return m.group(1).strip().split("\n")[0]
        m = re.search(r"OPEN LOOPS:\s*(.+)", prompt)
        if m:
            return m.group(1).strip().split(";")[0].strip()
        return "[mock answer] no loop"


def probe_prompt(rendered: str, question: str) -> str:
    return (
        f"{rendered}\n\n"
        f"QUESTION: {question}\n"
        "Answer in one short sentence using only the supplied context."
    )


def route(sc: SufficiencyScenario):
    reg = build_registry(sc)
    turn = max(t for _, _, t in sc.mentions) + 1
    res = Engine(router_llm(), reg, SETTINGS, mode="split").handle_turn(sc.message, turn)
    cards = build_registry(sc)
    return res, cards


def compile_mode(cards: InMemoryRegistry, sc: SufficiencyScenario,
                 pred_task: Optional[str], pred_ref: Optional[str],
                 engine_mode: str):
    if not pred_task:
        return None
    task = cards.get(pred_task)
    if task is None:
        return None
    return ContextCompiler().build(
        task, engine_mode,
        selected_referent_id=pred_ref,
        selected_open_loop=loop_text(task, pred_ref),
        message=sc.message,
        open_tasks=cards.open_tasks(),
    )


def generate_answer(llm, pkg, question: str) -> tuple[str, Optional[float]]:
    prompt = probe_prompt(ContextCompiler().render(pkg), question)
    t0 = time.perf_counter()
    text = llm.generate(prompt)
    elapsed = time.perf_counter() - t0
    lat = getattr(llm, "last_latency_s", None)
    return text, (lat if lat else elapsed)


def run_provider(name: str, answer_llm) -> list[dict]:
    rows: list[dict] = []
    compiler_cache: dict[str, dict] = {}
    for sc in scenarios():
        res, cards = route(sc)
        clarified = res.transition == Transition.CLARIFY
        pred_task, pred_ref = res.predicted_task_id, res.predicted_referent_id
        pkgs = {}
        for engine_mode, _label in MODES:
            pkgs[engine_mode] = compile_mode(cards, sc, pred_task, pred_ref, engine_mode)
        compiler_cache[sc.scenario_id] = pkgs
        for engine_mode, label in MODES:
            pkg = pkgs[engine_mode]
            row = {
                "provider": name,
                "scenario_id": sc.scenario_id,
                "gold_task": sc.gold_task,
                "gold_referent": sc.gold_referent,
                "pred_task": pred_task,
                "pred_referent": pred_ref,
                "context_mode": pkg.context_mode if pkg else None,
                "engine_mode": engine_mode,
                "included_loop_ids": pkg.included_loop_ids if pkg else [],
                "decision_context_tokens": pkg.decision_tokens if pkg else None,
                "answer_context_tokens": pkg.answer_tokens if pkg else None,
                "total_context_tokens": pkg.total_context_tokens if pkg else None,
                "clarified": clarified,
                "probe": sc.probe,
                "answer": None,
                "latency_s": None,
                "failure_class": None,
            }
            if clarified or pkg is None:
                row.update({
                    "answer_correct": False,
                    "answer_score": 0.0,
                    "wrong_loop": False,
                    "wrong_task": False,
                    "checkable_probe_result": "clarify" if clarified else "no_package",
                })
                rows.append(row)
                continue
            answer, lat = generate_answer(answer_llm, pkg, sc.probe)
            scored = score_answer(answer, sc)
            row["answer"] = answer
            row["latency_s"] = round(lat, 3) if lat is not None else None
            row.update(scored)
            rows.append(row)
        # classify compact vs full after both exist
        by_mode = {r["context_mode"]: r for r in rows[-3:]}
        compact = by_mode.get(REFERENT_COMPACT)
        full = by_mode.get(FULL_TASK)
        if compact and full:
            compact["failure_class"] = classify_compact_failure(
                sc, pred_task, pred_ref,
                pkgs["split"], pkgs["full"],
                compact["answer_correct"], full["answer_correct"],
                compact.get("answer") or "",
            )
    return rows


def summarize(rows: list[dict], provider: str) -> dict:
    rs = [r for r in rows if r["provider"] == provider]
    out = {"provider": provider, "by_mode": {}}
    for mode in (FULL_TASK, REFERENT_COMPACT, MERGED_COMPACT):
        ms = [r for r in rs if r["context_mode"] == mode]
        n = len(ms) or 1
        out["by_mode"][mode] = {
            "n": len(ms),
            "probe_accuracy": round(sum(1 for r in ms if r["answer_correct"]) / n, 3),
            "mean_answer_score": round(sum(r["answer_score"] for r in ms) / n, 3),
            "wrong_loop_rate": round(sum(1 for r in ms if r.get("wrong_loop")) / n, 3),
            "wrong_task_rate": round(sum(1 for r in ms if r.get("wrong_task")) / n, 3),
            "clarification_rate": round(sum(1 for r in ms if r.get("clarified")) / n, 3),
            "mean_answer_tokens": round(
                sum(r["answer_context_tokens"] or 0 for r in ms) / n, 1
            ),
            "mean_total_tokens": round(
                sum(r["total_context_tokens"] or 0 for r in ms) / n, 1
            ),
        }
    return out


def print_report(rows: list[dict], summaries: list[dict]) -> None:
    print("\n=== CONTEXT SUFFICIENCY (mechanism check, not a benchmark) ===\n")
    for provider in sorted({r["provider"] for r in rows}):
        print(f"-- {provider} --")
        print(f"{'scenario':24} {'mode':18} pred            loops                    ok  score loops?")
        for r in rows:
            if r["provider"] != provider:
                continue
            loops = ",".join(r["included_loop_ids"] or [])
            print(
                f"{r['scenario_id']:24} {str(r['context_mode']):18} "
                f"{str(r['pred_task'])}/{str(r['pred_referent']):12} "
                f"{loops:24} {str(r['answer_correct']):5} {r['answer_score']:.1f}  "
                f"{r.get('checkable_probe_result')}"
            )
        print()
    print("summaries:", json.dumps(summaries, indent=2))
    print("\nfailure_class key: A task-level missing, B selected-loop missing, "
          "C cross-loop required, D model weakness, E bad card, F resolver, G compiler")


def main() -> None:
    mock_rows = run_provider("mock", EchoSelectedMock())
    all_rows = list(mock_rows)
    try:
        from app.llm.ollama import OllamaLLM
        ollama = OllamaLLM()
        all_rows.extend(run_provider("ollama", ollama))
    except Exception as exc:
        print(f"ollama skipped: {exc}")

    summaries = []
    for p in sorted({r["provider"] for r in all_rows}):
        summaries.append(summarize(all_rows, p))

    out_dir = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "context_sufficiency.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "note": "mechanism validation, not a benchmark",
                "rows": all_rows,
                "summary": summaries,
            },
            f,
            indent=2,
        )
    print_report(all_rows, summaries)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
