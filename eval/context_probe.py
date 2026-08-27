"""Manual context-construction probe. Not a benchmark."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.config import SETTINGS
from app.context.compiler import ContextCompiler
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.registry import InMemoryRegistry
from app.models.task import Task, TaskAnchor
from tests.test_referent import jwt_frontend, jwt_oauth, seed_mentions, two_loops_a


def _three() -> InMemoryRegistry:
    r = InMemoryRegistry()
    r.add(Task(
        id="A", title="auth", status="paused",
        retrieval_cues=["jwt", "401", "token", "deploy"],
        anchor=TaskAnchor(
            goal="fix authentication and release",
            open_loops=[
                "JWT 401 after refresh",
                "expired access token",
                "deployment pipeline failing",
            ],
            decisions=["refresh in middleware"],
            constraints=["do not change public API"],
            entities=["JWT middleware"],
        ),
    ))
    r.add(Task(
        id="B", title="frontend", status="paused",
        retrieval_cues=["react", "render", "component"],
        anchor=TaskAnchor(goal="Frontend rendering",
                          open_loops=["component renders twice"]),
    ))
    return r


def _engine(reg: InMemoryRegistry, mode: str = "split") -> Engine:
    llm = MockLLM({
        "authentication thing": {
            "task_id": "B", "is_new_task": False, "confidence": 0.92,
            "referent": None, "rationale": "x",
        },
        "renders twice": {
            "task_id": "A", "is_new_task": False, "confidence": 0.92,
            "referent": None, "rationale": "x",
        },
        "the 401": {
            "task_id": "B", "is_new_task": False, "confidence": 0.92,
            "referent": None, "rationale": "x",
        },
        "deployment": {
            "task_id": "A", "is_new_task": False, "confidence": 0.9,
            "referent": None, "rationale": "x",
        },
        "fix that": {
            "task_id": "A", "is_new_task": False, "confidence": 0.95,
            "referent": None, "rationale": "always-A",
        },
    })
    return Engine(llm, reg, SETTINGS, mode=mode)


def row(sid: str, gold_task: str, gold_ref: str, r, mode: str) -> dict:
    pkg = r.package
    return {
        "scenario_id": sid,
        "gold_task": gold_task,
        "gold_referent": gold_ref,
        "predicted_task": r.predicted_task_id,
        "predicted_referent": r.predicted_referent_id,
        "included_loops": pkg.included_loop_ids if pkg else [],
        "decision_tokens": pkg.decision_tokens if pkg else None,
        "answer_tokens": pkg.answer_tokens if pkg else None,
        "total_context_tokens": pkg.total_context_tokens if pkg else None,
        "context_mode": pkg.context_mode if pkg else None,
        "engine_mode": mode,
        "answer_preview": ContextCompiler().render(pkg) if pkg else None,
    }


def run_scenarios() -> list[dict]:
    rows: list[dict] = []

    r = _three()
    seed_mentions(r, [("A", "A.loop1", 1)])
    res = _engine(r).handle_turn("the 401", 2)
    rows.append(row("P1_loop1", "A", "A.loop1", res, "split"))

    r = _three()
    seed_mentions(r, [("A", "A.loop2", 1)])
    res = _engine(r).handle_turn("fix that", 2)
    rows.append(row("P2_loop2", "A", "A.loop2", res, "split"))

    r = _three()
    seed_mentions(r, [("A", "A.loop3", 1)])
    res = _engine(r).handle_turn("deployment pipeline", 2)
    rows.append(row("P3_loop3", "A", "A.loop3", res, "split"))

    r = jwt_frontend()
    seed_mentions(r, [("A", "A.loop1", 1), ("A", "A.loop1", 2), ("B", "B.loop1", 3)])
    res = _engine(r).handle_turn("fix that", 4)
    rows.append(row("P4_B_while_A_history", "B", "B.loop1", res, "split"))

    r = jwt_frontend()
    seed_mentions(r, [("A", "A.loop1", 1), ("B", "B.loop1", 2), ("A", "A.loop1", 3)])
    res = _engine(r).handle_turn("the component still renders twice", 4)
    rows.append(row("P5_lexical_B", "B", "B.loop1", res, "split"))

    r = two_loops_a()
    seed_mentions(r, [("A", "A.loop1", 1), ("B", "B.loop1", 2), ("A", "A.loop2", 3)])
    res = _engine(r).handle_turn("fix that", 4)
    rows.append(row("P6_A2_style_loop2", "A", "A.loop2", res, "split"))

    r = two_loops_a()
    seed_mentions(r, [("A", "A.loop2", 1), ("A", "A.loop2", 2)])
    res = _engine(r).handle_turn("the 401", 3)
    rows.append(row("P7_lexical_overrides_fg", "A", "A.loop1", res, "split"))

    r = jwt_oauth()
    seed_mentions(r, [("JWT", "JWT.loop1", 1), ("OAuth", "OAuth.loop1", 2)])
    res = _engine(r).handle_turn("fix that", 3)
    rows.append(row("P8_oauth_deictic", "OAuth", "OAuth.loop1", res, "split"))

    r = _three()
    seed_mentions(r, [("A", "A.loop2", 1)])
    res = _engine(r, mode="full").handle_turn("fix that", 2)
    rows.append(row("P9_full_task", "A", "A.loop2", res, "full"))

    r = _three()
    seed_mentions(r, [("A", "A.loop2", 1)])
    res = _engine(r, mode="merged").handle_turn("fix that", 2)
    rows.append(row("P10_merged_compact", "A", "A.loop2", res, "merged"))

    return rows


def main() -> None:
    rows = run_scenarios()
    out_dir = os.path.join(ROOT, "eval", "out")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "context_probe.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"note": "manual construction check, not a benchmark", "rows": rows}, f, indent=2)
    print("scenario              gold            pred            loops                    mode             d/a/tot")
    for r in rows:
        loops = ",".join(r["included_loops"] or [])
        print(
            f"{r['scenario_id']:22} {r['gold_task']}/{r['gold_referent']:12} "
            f"{r['predicted_task']}/{str(r['predicted_referent']):12} "
            f"{loops:24} {str(r['context_mode']):16} "
            f"{r['decision_tokens']}/{r['answer_tokens']}/{r['total_context_tokens']}"
        )
        preview = (r["answer_preview"] or "").replace("\n", " | ")
        print(f"   {preview[:160]}")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
