"""Manual Ollama provider probe. Not part of pytest. $0 cloud."""

from __future__ import annotations

import json
import time

from app.config import SETTINGS
from app.engine import Engine
from app.llm.ollama import OllamaLLM
from app.llm.tokens import count
from app.memory.registry import InMemoryRegistry
from app.models.task import Task, TaskAnchor
from app.router.proposal import PROPOSAL_SCHEMA, build_prompt


def _task(tid, title, goal, loops, entities, cues, status="paused", last=0, decision=""):
    a = TaskAnchor(goal=goal, open_loops=list(loops), entities=list(entities))
    if decision:
        a.decisions = [decision]
    return Task(id=tid, title=title, status=status, retrieval_cues=list(cues),
                anchor=a, last_active_turn=last)


def experiment_registry() -> InMemoryRegistry:
    r = InMemoryRegistry()
    r.add(_task("A", "api auth", "fix API authentication",
                ["API returns HTTP 401 after token refresh"],
                ["JWT", "refresh token"],
                ["jwt", "401", "authentication", "token"],
                status="paused", last=1,
                decision="token refresh moved to middleware"))
    r.add(_task("B", "frontend", "fix frontend rendering",
                ["React component renders twice"],
                ["React", "useEffect"],
                ["react", "render", "useeffect"],
                status="active", last=5))
    r.add(_task("C", "slides", "prepare architecture presentation",
                ["explain context-management diagram"],
                ["slides", "architecture"],
                ["slide", "architecture", "presentation"],
                status="paused", last=3))
    return r


FULL_TRANSCRIPT = """
User: The login API started returning 401 after we moved token refresh into middleware.
Assistant: I'll inspect the JWT refresh path and the 401 on protected routes.
User: Also the dashboard React component mounts twice; I think useEffect is the cause.
Assistant: I'll look at StrictMode and the effect dependencies.
User: Tomorrow I need slides explaining the context-management diagram.
Assistant: I'll draft the architecture presentation outline.
User: fix that
"""


def compact_prompt(message: str, tasks: list[Task]) -> str:
    return build_prompt(message, tasks)


def full_prompt(message: str) -> str:
    return (
        "You route a user message to one of the user's open tasks, or say it's new.\n"
        "You see a full transcript plus the latest message.\n"
        "Pick the single task the user is most likely acting on. "
        "Task ids: A=API authentication, B=frontend rendering, C=architecture presentation.\n\n"
        f"TRANSCRIPT:\n{FULL_TRANSCRIPT}\n"
        f'MESSAGE: "{message}"\n\n'
        'Return JSON: {task_id|null, is_new_task, confidence 0..1, referent, rationale}'
    )


def row(provider, model, message, proposal, result, llm: OllamaLLM, kind: str):
    d = result.decision
    pkg = result.package
    if isinstance(proposal, dict):
        p_task, p_new, p_conf, p_rat = (
            proposal.get("task_id"), proposal.get("is_new_task"),
            proposal.get("confidence"), proposal.get("rationale"),
        )
    else:
        p_task, p_new, p_conf, p_rat = (
            proposal.task_id, proposal.is_new_task, proposal.confidence, proposal.rationale,
        )
    return {
        "kind": kind,
        "provider": provider,
        "model": model,
        "user_message": message,
        "proposal_task": p_task,
        "proposal_is_new": p_new,
        "proposal_confidence": p_conf,
        "proposal_rationale": p_rat,
        "ContextFlow_top_task": d.candidates[0].task_id if d.candidates else None,
        "top_raw": round(d.top_raw, 4),
        "runner_raw": round(d.runner_raw, 4),
        "raw_margin": round(d.raw_margin, 4),
        "open_task_count": d.open_task_count,
        "plausible_candidate_count": d.plausible_candidate_count,
        "gate_decision": d.transition.value,
        "transition": result.transition.value,
        "clarification": result.clarify_question,
        "latency_s": round(llm.last_propose_latency_s, 3),
        "input_tokens_heuristic": count(message),
        "provider_prompt_eval_count": llm.last_prompt_eval_count,
        "decision_context_tokens": pkg.decision_tokens if pkg else None,
        "answer_context_tokens": pkg.answer_tokens if pkg else None,
    }


def run_engine_script(llm: OllamaLLM):
    reg = experiment_registry()
    eng = Engine(llm, reg, SETTINGS, mode="split")
    script = [
        ("fix that authentication thing", 6),
        ("fix that", 7),
        ("still getting HTTP 401", 8),
        ("the component still renders twice", 9),
        ("fix that", 10),
    ]
    rows = []
    for msg, turn in script:
        t0 = time.perf_counter()
        res = eng.handle_turn(msg, turn)
        proposal = llm.last_proposal or {}
        rec = row("ollama", llm.model, msg, proposal, res, llm, "engine_turn")
        rec["wall_s"] = round(time.perf_counter() - t0, 3)
        rec["answer_preview"] = (res.answer or "")[:160]
        rec["generate_latency_s"] = round(llm.last_latency_s, 3)
        rows.append(rec)
        print(json.dumps(rec, indent=2))
    return rows


def run_compact_vs_full(llm: OllamaLLM):
    reg = experiment_registry()
    tasks = reg.open_tasks()
    message = "fix that"
    out = []
    for kind, prompt in (
        ("compact_task_cards", compact_prompt(message, tasks)),
        ("full_transcript", full_prompt(message)),
    ):
        raw = llm.propose(prompt, PROPOSAL_SCHEMA)
        rec = {
            "kind": kind,
            "provider": "ollama",
            "model": llm.model,
            "user_message": message,
            "proposal": raw,
            "latency_s": round(llm.last_latency_s, 3),
            "provider_prompt_eval_count": llm.last_prompt_eval_count,
            "prompt_chars": len(prompt),
            "prompt_tokens_heuristic": count(prompt),
        }
        out.append(rec)
        print(json.dumps(rec, indent=2))
    return out


def run_interference(llm: OllamaLLM):
    distant = [
        ("A", "jwt auth", "debug jwt authentication", ["401 on protected route"], ["jwt", "401"]),
        ("B", "laptop", "choose a laptop", ["compare macbook vs xps"], ["laptop"]),
        ("C", "slides", "prepare slide deck", ["write closing slide"], ["slide"]),
        ("D", "travel", "book a flight", ["pick a date"], ["flight"]),
        ("E", "recipe", "plan dinner", ["pick dessert"], ["dinner"]),
        ("F", "garden", "plant tomatoes", ["buy soil"], ["tomato"]),
        ("G", "budget", "review expenses", ["categorize receipts"], ["budget"]),
        ("H", "music", "make a playlist", ["choose opener"], ["playlist"]),
    ]
    siblings = [
        ("A", "jwt auth", "fix jwt authentication", ["jwt token not verified"], ["jwt", "token"]),
        ("B", "oauth auth", "fix oauth authentication", ["oauth redirect fails"], ["oauth"]),
        ("C", "api auth", "fix api key authentication", ["api key rejected"], ["api", "key"]),
        ("D", "frontend auth", "fix frontend auth guard", ["route guard leaks"], ["frontend", "guard"]),
        ("E", "session auth", "fix session cookies", ["cookie not set"], ["session"]),
        ("F", "saml auth", "fix saml sso", ["assertion invalid"], ["saml"]),
        ("G", "mfa auth", "fix mfa challenge", ["totp rejected"], ["mfa"]),
        ("H", "password auth", "fix password reset", ["reset token expired"], ["password"]),
    ]
    rows = []
    for label, pool in (("low", distant), ("high", siblings)):
        for n in (1, 2, 4, 8):
            r = InMemoryRegistry()
            for spec in pool[:n]:
                tid, title, goal, loops, cues = spec
                r.add(Task(id=tid, title=title,
                           anchor=TaskAnchor(goal=goal, open_loops=list(loops)),
                           retrieval_cues=list(cues), status="paused"))
            r.mark_active(pool[min(n - 1, len(pool) - 1)][0], 10)
            eng = Engine(llm, r, SETTINGS, mode="split")
            msg = "fix that"
            res = eng.handle_turn(msg, 12)
            rec = row("ollama", llm.model, msg, llm.last_proposal or {}, res, llm,
                      f"interference_{label}_n{n}")
            rec["interference"] = label
            rec["n_open"] = n
            rows.append(rec)
            print(json.dumps(rec, indent=2))
    return rows


def main():
    llm = OllamaLLM()
    print("=== ENGINE SCRIPT ===")
    engine_rows = run_engine_script(llm)
    print("=== COMPACT VS FULL ===")
    cmp_rows = run_compact_vs_full(llm)
    print("=== INTERFERENCE (exploratory) ===")
    int_rows = run_interference(llm)
    return {"engine": engine_rows, "compare": cmp_rows, "interference": int_rows}


if __name__ == "__main__":
    main()
