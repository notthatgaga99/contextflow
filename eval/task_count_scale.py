"""Open-task-count stress experiment. $0. Does not change production code.

Mechanism check, not a benchmark.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from app.config import SETTINGS
from app.context.compiler import ContextCompiler
from app.domain import Transition
from app.engine import Engine
from app.llm import tokens as token_lib
from app.llm.mock import MockLLM
from app.memory.registry import InMemoryRegistry
from app.models.task import Task, TaskAnchor
from app.retrieval.scorer import _tokens
from app.router.referent import loop_index_from_id, loop_referent_id

N_VALUES = (1, 2, 3, 5, 8, 10)
FAMILIES = ("LOW", "HIGH")
UNDERSPEC = ("EXPLICIT", "PARTIAL", "DEICTIC", "CORRECTION")
FOREGROUND = ("target_last", "distractor_last", "target_active_distractor_fg")
SYSTEMS = ("contextflow", "recency", "similarity", "full_history")
TARGET_ID = "T"


def _mk(
    tid: str,
    title: str,
    goal: str,
    loops: list[str],
    cues: list[str],
) -> Task:
    return Task(
        id=tid, title=title, status="paused",
        retrieval_cues=list(cues),
        anchor=TaskAnchor(goal=goal, open_loops=list(loops)),
    )


def target_task() -> Task:
    return _mk(
        TARGET_ID, "jwt auth", "fix JWT authentication",
        ["JWT 401 after refresh", "expired access token"],
        ["jwt", "401", "authentication", "refresh", "token"],
    )


HIGH_DISTRACTORS = [
    _mk("H1", "oauth", "fix OAuth authentication",
        ["OAuth redirect URI mismatch"], ["oauth", "redirect", "authentication"]),
    _mk("H2", "session", "fix session cookies",
        ["session cookie SameSite unset"], ["session", "cookie", "samesite"]),
    _mk("H3", "apikey", "rotate API keys",
        ["API key rejected on /v2"], ["api", "key", "authorization"]),
    _mk("H4", "refresh", "token refresh middleware",
        ["refresh token rotation fails"], ["token", "refresh", "jwt"]),
    _mk("H5", "authz", "authorization header missing",
        ["401 from missing Authorization"], ["authorization", "401", "header"]),
    _mk("H6", "loginui", "login form",
        ["login button does not submit"], ["login", "frontend", "auth"]),
    _mk("H7", "csrf", "CSRF token",
        ["CSRF token rejected after POST"], ["csrf", "token", "auth"]),
    _mk("H8", "reset", "password reset JWT",
        ["password reset JWT expired"], ["jwt", "password", "reset"]),
    _mk("H9", "oidc", "OpenID Connect",
        ["OIDC nonce mismatch"], ["oidc", "openid", "token"]),
]

LOW_DISTRACTORS = [
    _mk("L1", "laptop", "choose a laptop",
        ["compare macbook vs xps"], ["laptop", "macbook"]),
    _mk("L2", "slides", "prepare slide deck",
        ["write closing slide"], ["slide", "deck"]),
    _mk("L3", "garden", "water the garden",
        ["fix drip irrigation timer"], ["garden", "irrigation"]),
    _mk("L4", "taxes", "file taxes",
        ["gather 1099 forms"], ["tax", "1099"]),
    _mk("L5", "pasta", "cook pasta",
        ["salt the pasta water"], ["pasta", "recipe"]),
    _mk("L6", "bike", "repair the bike",
        ["replace rear inner tube"], ["bike", "tube"]),
    _mk("L7", "piano", "piano practice",
        ["learn bach invention"], ["piano", "bach"]),
    _mk("L8", "visa", "travel visa",
        ["scan passport photos"], ["visa", "passport"]),
    _mk("L9", "vet", "dog vet visit",
        ["book annual vaccines"], ["vet", "dog"]),
]


def distractors(family: str) -> list[Task]:
    return HIGH_DISTRACTORS if family == "HIGH" else LOW_DISTRACTORS


def clone_task(t: Task) -> Task:
    return _mk(t.id, t.title, t.anchor.goal, list(t.anchor.open_loops), list(t.retrieval_cues))


def task_set(n: int, family: str) -> list[Task]:
    extra = [clone_task(t) for t in distractors(family)[: max(0, n - 1)]]
    return [clone_task(target_task())] + extra


def message_for(underspec: str) -> str:
    return {
        "EXPLICIT": "fix the JWT 401 after refresh",
        "PARTIAL": "still getting the 401",
        "DEICTIC": "fix that",
        "CORRECTION": "no, the other one",
    }[underspec]


def apply_foreground(reg: InMemoryRegistry, tasks: list[Task], fg: str) -> list[tuple[str, str, int]]:
    """Return mention events. last_active follows mark_active only."""
    ids = [t.id for t in tasks]
    others = ids[1:]
    mentions: list[tuple[str, str, int]] = []
    turn = 1
    if fg == "target_last":
        for tid in others:
            mentions.append((tid, f"{tid}.loop1", turn))
            reg.record_mention(tid, turn, f"{tid}.loop1")
            reg.mark_active(tid, turn)
            turn += 1
        mentions.append((TARGET_ID, f"{TARGET_ID}.loop1", turn))
        reg.record_mention(TARGET_ID, turn, f"{TARGET_ID}.loop1")
        reg.mark_active(TARGET_ID, turn)
    elif fg == "distractor_last":
        mentions.append((TARGET_ID, f"{TARGET_ID}.loop1", turn))
        reg.record_mention(TARGET_ID, turn, f"{TARGET_ID}.loop1")
        reg.mark_active(TARGET_ID, turn)
        turn += 1
        for tid in others:
            mentions.append((tid, f"{tid}.loop1", turn))
            reg.record_mention(tid, turn, f"{tid}.loop1")
            reg.mark_active(tid, turn)
            turn += 1
        if not others:
            # n=1: same as target_last
            pass
    else:  # target_active_distractor_fg
        mentions.append((TARGET_ID, f"{TARGET_ID}.loop1", turn))
        reg.record_mention(TARGET_ID, turn, f"{TARGET_ID}.loop1")
        reg.mark_active(TARGET_ID, turn)
        turn += 1
        if others:
            last = others[-1]
            mentions.append((last, f"{last}.loop1", turn))
            reg.record_mention(last, turn, f"{last}.loop1")
            # do not mark_active: task recency stays on T, referent recency on distractor
        else:
            reg.mark_active(TARGET_ID, turn)
    return mentions


def gold_for(underspec: str, fg: str, tasks: list[Task], mentions: list[tuple[str, str, int]]) -> tuple[str, str]:
    last_ref = mentions[-1][1] if mentions else f"{TARGET_ID}.loop1"
    last_task = mentions[-1][0] if mentions else TARGET_ID
    if underspec in ("EXPLICIT", "PARTIAL"):
        return TARGET_ID, f"{TARGET_ID}.loop1"
    if underspec == "DEICTIC":
        return last_task, last_ref
    # CORRECTION: exclude last selected (set to last mention); expect remaining highest clock = previous mention
    if len(mentions) >= 2:
        prev = mentions[-2]
        return prev[0], prev[1]
    return TARGET_ID, f"{TARGET_ID}.loop2"


def build_registry(tasks: list[Task], fg: str, underspec: str) -> tuple[InMemoryRegistry, list[tuple[str, str, int]]]:
    reg = InMemoryRegistry()
    for t in tasks:
        reg.add(clone_task(t))
    mentions = apply_foreground(reg, tasks, fg)
    if underspec == "CORRECTION" and mentions:
        reg.set_last_selected_referent(mentions[-1][1])
    return reg, mentions


def wrong_llm(tasks: list[Task]) -> MockLLM:
    lure = tasks[1].id if len(tasks) > 1 else "Z"
    return MockLLM({
        "401": {"task_id": lure, "is_new_task": False, "confidence": 0.92,
                "referent": None, "rationale": "lure"},
        "JWT": {"task_id": lure, "is_new_task": False, "confidence": 0.92,
                "referent": None, "rationale": "lure"},
        "other one": {"task_id": lure, "is_new_task": False, "confidence": 0.92,
                "referent": None, "rationale": "lure"},
        "fix that": {"task_id": lure, "is_new_task": False, "confidence": 0.95,
                "referent": None, "rationale": "lure"},
    })


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def pred_recency(reg: InMemoryRegistry) -> tuple[Optional[str], Optional[str]]:
    tasks = reg.open_tasks()
    if not tasks:
        return None, None
    t = max(tasks, key=lambda x: (x.last_active_turn, x.mention_turn))
    if t.anchor.open_loops:
        ensure = list(range(len(t.anchor.open_loops)))
        idx = max(ensure, key=lambda i: t.loop_mention_turns[i] if i < len(t.loop_mention_turns) else 0)
        # if all loop clocks 0, first loop
        if max(t.loop_mention_turns or [0]) == 0:
            idx = 0
        return t.id, loop_referent_id(t.id, idx)
    return t.id, t.id


def pred_similarity(message: str, reg: InMemoryRegistry) -> tuple[Optional[str], Optional[str]]:
    msg = _tokens(message)
    best = (-1.0, None, None)
    for t in reg.open_tasks():
        for i, loop in enumerate(t.anchor.open_loops or [""]):
            blob = _tokens(f"{t.anchor.goal} {loop} {' '.join(t.retrieval_cues)}")
            s = _jaccard(msg, blob)
            cand = (s, t.id, loop_referent_id(t.id, i) if t.anchor.open_loops else t.id)
            if cand[0] > best[0]:
                best = cand
    if best[1] is None:
        return pred_recency(reg)
    if best[0] == 0.0:
        return pred_recency(reg)
    return best[1], best[2]


def pred_full_history(message: str, reg: InMemoryRegistry) -> tuple[Optional[str], Optional[str]]:
    # Same lexical scorer over the full card dump; deictic falls back to recency.
    if not _tokens(message) - {"fix", "that", "the", "no", "other", "one", "still", "getting"}:
        return pred_recency(reg)
    return pred_similarity(message, reg)


def compile_for(reg: InMemoryRegistry, pred_task: Optional[str], pred_ref: Optional[str],
                message: str, mode: str = "split"):
    if not pred_task or not reg.get(pred_task):
        return None
    task = reg.get(pred_task)
    idx = loop_index_from_id(pred_task, pred_ref or "")
    loop = task.anchor.open_loops[idx] if idx is not None and idx < len(task.anchor.open_loops) else None
    return ContextCompiler().build(
        task, mode,
        selected_referent_id=pred_ref,
        selected_open_loop=loop,
        message=message,
        open_tasks=reg.open_tasks(),
    )


def full_history_tokens(reg: InMemoryRegistry) -> tuple[int, int]:
    blob = "\n".join(t.card() for t in reg.open_tasks())
    n = token_lib.count(blob)
    return n, n


def classify_failure(row: dict) -> Optional[str]:
    if row["joint_accuracy"]:
        return None
    if row["clarified"]:
        return "clarify"
    if row["pred_task"] != row["gold_task"] and row["pred_referent"] == row["gold_referent"]:
        return "task_mismatch_same_referent"
    if row["pred_task"] == row["gold_task"] and row["pred_referent"] != row["gold_referent"]:
        return "referent_neq_task"
    if row["pred_task"] and str(row["pred_task"]).startswith("H"):
        return "similar_lure"
    if row["pred_task"] and str(row["pred_task"]).startswith("L"):
        return "unrelated_lure"
    return "other"


def run_contextflow(reg: InMemoryRegistry, message: str, turn: int):
    eng = Engine(wrong_llm(reg.open_tasks()), reg, SETTINGS, mode="split")
    res = eng.handle_turn(message, turn)
    clarified = res.transition == Transition.CLARIFY
    pkg = res.package
    return {
        "pred_task": res.predicted_task_id,
        "pred_referent": res.predicted_referent_id,
        "clarified": clarified,
        "acted": not clarified and res.transition != Transition.NEW,
        "decision_context_tokens": pkg.decision_tokens if pkg else 0,
        "answer_context_tokens": pkg.answer_tokens if pkg else 0,
        "total_context_tokens": pkg.total_context_tokens if pkg else 0,
        "context_mode": pkg.context_mode if pkg else None,
    }


def run_baseline(kind: str, reg: InMemoryRegistry, message: str):
    if kind == "recency":
        pt, pr = pred_recency(reg)
    elif kind == "similarity":
        pt, pr = pred_similarity(message, reg)
    else:
        pt, pr = pred_full_history(message, reg)
    if kind == "full_history":
        d, a = full_history_tokens(reg)
        pkg_mode = "FULL_HISTORY"
        total = d
        ans = a
        dec = d
    else:
        pkg = compile_for(reg, pt, pr, message, "split")
        dec = pkg.decision_tokens if pkg else 0
        ans = pkg.answer_tokens if pkg else 0
        total = pkg.total_context_tokens if pkg else 0
        pkg_mode = pkg.context_mode if pkg else None
    return {
        "pred_task": pt,
        "pred_referent": pr,
        "clarified": False,
        "acted": True,
        "decision_context_tokens": dec,
        "answer_context_tokens": ans,
        "total_context_tokens": total,
        "context_mode": pkg_mode,
    }


def iter_cells():
    for n in N_VALUES:
        for family in FAMILIES:
            fgs = FOREGROUND if n > 1 else ("target_last",)
            for underspec in UNDERSPEC:
                for fg in fgs:
                    yield n, family, underspec, fg


def run_grid() -> list[dict]:
    rows: list[dict] = []
    for n, family, underspec, fg in iter_cells():
        tasks = task_set(n, family)
        message = message_for(underspec)
        for system in SYSTEMS:
            reg, mentions = build_registry(tasks, fg, underspec)
            gold_task, gold_ref = gold_for(underspec, fg, tasks, mentions)
            turn = max(m[2] for m in mentions) + 1
            if system == "contextflow":
                out = run_contextflow(reg, message, turn)
            else:
                out = run_baseline(system, reg, message)
            pred_t, pred_r = out["pred_task"], out["pred_referent"]
            task_ok = pred_t == gold_task
            ref_ok = pred_r == gold_ref
            joint = task_ok and ref_ok
            acted = out["acted"]
            row = {
                "open_task_count": n,
                "interference_family": family,
                "underspecification": underspec,
                "foreground": fg,
                "system": system,
                "gold_task": gold_task,
                "gold_referent": gold_ref,
                "pred_task": pred_t,
                "pred_referent": pred_r,
                "task_accuracy": task_ok,
                "referent_accuracy": ref_ok,
                "joint_accuracy": joint,
                "clarified": out["clarified"],
                "wrong_action": bool(acted and not joint),
                "decision_context_tokens": out["decision_context_tokens"],
                "answer_context_tokens": out["answer_context_tokens"],
                "total_context_tokens": out["total_context_tokens"],
                "context_mode": out["context_mode"],
            }
            row["failure_class"] = classify_failure(row)
            rows.append(row)
    return rows


def _agg(rows: list[dict], n: int, family: str, system: str, subset=None) -> dict:
    xs = [r for r in rows if r["open_task_count"] == n and r["system"] == system
          and r["interference_family"] == family]
    if subset:
        xs = [r for r in xs if subset(r)]
    k = len(xs) or 1
    acted = [r for r in xs if not r["clarified"]]
    return {
        "n": n,
        "family": family,
        "system": system,
        "cells": len(xs),
        "task_accuracy": round(sum(r["task_accuracy"] for r in xs) / k, 3),
        "referent_accuracy": round(sum(r["referent_accuracy"] for r in xs) / k, 3),
        "joint_accuracy": round(sum(r["joint_accuracy"] for r in xs) / k, 3),
        "wrong_action_rate": round(sum(r["wrong_action"] for r in acted) / len(acted), 3) if acted else None,
        "clarification_rate": round(sum(r["clarified"] for r in xs) / k, 3),
        "mean_decision_tokens": round(sum(r["decision_context_tokens"] for r in xs) / k, 1),
        "mean_answer_tokens": round(sum(r["answer_context_tokens"] for r in xs) / k, 1),
        "mean_total_tokens": round(sum(r["total_context_tokens"] for r in xs) / k, 1),
    }


def curves(rows: list[dict]) -> list[dict]:
    out = []
    families = sorted({r["interference_family"] for r in rows})
    for family in families:
        ns = sorted({r["open_task_count"] for r in rows if r["interference_family"] == family})
        for system in SYSTEMS:
            for n in ns:
                out.append(_agg(rows, n, family, system))
    return out


def print_report(rows: list[dict], curve: list[dict]) -> None:
    print("\n=== TASK-COUNT SCALE (mechanism stress, not a benchmark) ===\n")
    print(f"cells={len(rows)}  (n, family, underspec, foreground, system)\n")
    for family in ("LOW", "HIGH"):
        print(f"-- {family} joint accuracy vs n --")
        ns = sorted({c["n"] for c in curve if c["family"] == family})
        header = f"{'system':16} " + " ".join(f"{n:>6}" for n in ns)
        print(header)
        for system in SYSTEMS:
            vals = []
            for n in ns:
                hit = next((c for c in curve if c["family"] == family and c["system"] == system and c["n"] == n), None)
                vals.append(f"{hit['joint_accuracy']:.3f}" if hit else "  n/a")
            print(f"{system:16} " + " ".join(f"{v:>6}" for v in vals))
        print()
    cf_high = [c for c in curve if c["family"] == "HIGH" and c["system"] == "contextflow"]
    print("ContextFlow HIGH decision tokens by n:")
    for c in cf_high:
        print(f"  n={c['n']:2}  joint={c['joint_accuracy']:.3f}  "
              f"task={c['task_accuracy']:.3f}  ref={c['referent_accuracy']:.3f}  "
              f"wrong_act={c['wrong_action_rate']}  clarify={c['clarification_rate']:.3f}  "
              f"dec_tok={c['mean_decision_tokens']}")


def write_plots(curve: list[dict], out_dir: str) -> list[str]:
    paths = []
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return paths

    def _series(family, metric):
        fig, ax = plt.subplots(figsize=(7, 4))
        for system in SYSTEMS:
            pts = sorted([c for c in curve if c["family"] == family and c["system"] == system], key=lambda c: c["n"])
            if not pts:
                continue
            ax.plot([c["n"] for c in pts], [c[metric] for c in pts], marker="o", label=system)
        ax.set_xlabel("open task count")
        ax.set_ylabel(metric.replace("_", " "))
        ax.set_title(f"{family} interference: {metric.replace('_', ' ')} vs open-task count")
        ax.legend()
        ax.set_xticks(list(N_VALUES))
        fig.tight_layout()
        path = os.path.join(out_dir, f"{family.lower()}_{metric}.png")
        fig.savefig(path, dpi=120)
        plt.close(fig)
        paths.append(path)

    for family in ("LOW", "HIGH"):
        for metric in (
            "task_accuracy", "referent_accuracy", "joint_accuracy",
            "wrong_action_rate", "mean_decision_tokens",
        ):
            _series(family, metric)
    return paths


def main() -> None:
    rows = run_grid()
    curve = curves(rows)
    out_dir = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out_dir, exist_ok=True)
    payload = {
        "note": "open-task-count mechanism stress; not a benchmark",
        "n_values": list(N_VALUES),
        "systems": list(SYSTEMS),
        "rows": rows,
        "curves": curve,
    }
    path = os.path.join(out_dir, "task_count_scale.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    pngs = write_plots(curve, out_dir)
    print_report(rows, curve)
    print("plots:", pngs)
    print("wrote", path)


if __name__ == "__main__":
    main()
