"""Judge-mode interleaved-work demo. $0 MockLLM. No Vertex, no Ollama.

NEW cards are created by the engine after the gate accepts NEW.
The optional factory only supplies card *content* (ids, loops) for the story;
it does not override the routing decision.
"""

from __future__ import annotations

import argparse
import json
from typing import Optional

from app.config import SETTINGS
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.registry import InMemoryRegistry
from app.models.task import Task, TaskAnchor
from app.router.referent import loop_referent_id

# First matching substring wins. "fix that" is a deliberate Authentication lure.
SCRIPTED = {
    "authentication problem first": {
        "task_id": None, "is_new_task": True, "confidence": 0.91,
        "referent": None, "rationale": "new: authentication",
    },
    "checkout page is rendering twice": {
        "task_id": None, "is_new_task": True, "confidence": 0.90,
        "referent": None, "rationale": "new: frontend",
    },
    "deployment is failing in CI": {
        "task_id": None, "is_new_task": True, "confidence": 0.89,
        "referent": None, "rationale": "new: deployment",
    },
    "OAuth redirect URI is wrong too": {
        "task_id": None, "is_new_task": True, "confidence": 0.88,
        "referent": None, "rationale": "new: oauth",
    },
    "expired access token on this auth": {
        "task_id": "A", "is_new_task": False, "confidence": 0.87,
        "referent": None, "rationale": "auth loop 2",
    },
    "go back to the JWT 401": {
        "task_id": "A", "is_new_task": False, "confidence": 0.86,
        "referent": None, "rationale": "lexical JWT 401",
    },
    "JWT still returns 401": {
        "task_id": "A", "is_new_task": False, "confidence": 0.93,
        "referent": "A.loop1", "rationale": "JWT 401 loop",
    },
    "checkout component issue is actually more urgent": {
        "task_id": "B", "is_new_task": False, "confidence": 0.84,
        "referent": None, "rationale": "frontend",
    },
    "component still renders twice": {
        "task_id": "B", "is_new_task": False, "confidence": 0.92,
        "referent": "B.loop1", "rationale": "render loop",
    },
    "check the deployment quickly": {
        "task_id": "C", "is_new_task": False, "confidence": 0.80,
        "referent": None, "rationale": "deployment",
    },
    "failing on the Docker step": {
        "task_id": "C", "is_new_task": False, "confidence": 0.91,
        "referent": "C.loop1", "rationale": "docker ci",
    },
    "OAuth redirect URI is still broken": {
        "task_id": "D", "is_new_task": False, "confidence": 0.83,
        "referent": None, "rationale": "oauth resume",
    },
    "back to the JWT 401": {
        "task_id": "A", "is_new_task": False, "confidence": 0.85,
        "referent": None, "rationale": "auth resume",
    },
    "no, the other one": {
        "task_id": "A", "is_new_task": False, "confidence": 0.96,
        "referent": "A.loop1", "rationale": "llm lure: correction still guesses auth",
    },
    "fix that": {
        "task_id": "A", "is_new_task": False, "confidence": 0.97,
        "referent": "A.loop1", "rationale": "llm lure: salient auth prior",
    },
}

NEW_CARDS = [
    ("authentication problem first", Task(
        id="A", title="Authentication",
        retrieval_cues=["jwt", "401", "authentication", "refresh", "token"],
        anchor=TaskAnchor(
            goal="fix JWT authentication",
            open_loops=["JWT still returns 401 after refresh", "expired access token"],
        ),
    )),
    ("checkout page is rendering twice", Task(
        id="B", title="Frontend rendering",
        retrieval_cues=["checkout", "render", "frontend", "component"],
        anchor=TaskAnchor(
            goal="stop double render on checkout",
            open_loops=["component still renders twice"],
        ),
    )),
    ("deployment is failing in CI", Task(
        id="C", title="Deployment",
        retrieval_cues=["deploy", "ci", "docker", "pipeline"],
        anchor=TaskAnchor(
            goal="fix CI deployment",
            open_loops=["CI is failing on the Docker step"],
        ),
    )),
    ("OAuth redirect URI is wrong too", Task(
        id="D", title="OAuth",
        retrieval_cues=["oauth", "redirect", "uri"],
        anchor=TaskAnchor(
            goal="fix OAuth redirect URI",
            open_loops=["OAuth redirect URI mismatch"],
        ),
    )),
]

# Canonical judge conversation (~20 turns).
TURNS: list[str] = [
    "Let's fix the authentication problem first.",
    "The JWT still returns 401 after refresh.",
    "There's also an expired access token on this auth work.",
    "Actually before that, the checkout page is rendering twice.",
    "Also deployment is failing in CI.",
    "The OAuth redirect URI is wrong too.",
    "Let's go back to the JWT 401 after refresh.",
    "Wait, the checkout component issue is actually more urgent.",
    "The component still renders twice.",
    "Let's check the deployment quickly.",
    "CI is failing on the Docker step.",
    "fix that",
    "no, the other one",
    "Now back to the JWT 401 after refresh.",
    "fix that",
    "The expired access token on this auth work is still a problem.",
    "The OAuth redirect URI is still broken.",
    "The component still renders twice, can you look?",
    "CI is failing on the Docker step again.",
]


class RecordingLLM:
    def __init__(self, inner: MockLLM):
        self.inner = inner
        self.last_proposal: Optional[dict] = None

    def propose(self, prompt: str, schema: dict) -> dict:
        self.last_proposal = self.inner.propose(prompt, schema)
        return self.last_proposal

    def generate(self, prompt: str) -> str:
        return self.inner.generate(prompt)

    def embed(self, texts: list[str]):
        return self.inner.embed(texts)


def _clone_task(t: Task) -> Task:
    return Task(
        id=t.id, title=t.title, status="paused",
        retrieval_cues=list(t.retrieval_cues),
        anchor=TaskAnchor(
            goal=t.anchor.goal,
            open_loops=list(t.anchor.open_loops),
        ),
    )


def new_task_factory(message: str, turn: int) -> Optional[Task]:
    """Card body only. Called by Engine after gate NEW. Does not choose the transition."""
    del turn
    for key, template in NEW_CARDS:
        if key in message:
            return _clone_task(template)
    return None


def naive_history(reg: InMemoryRegistry) -> list[dict]:
    rows = []
    for t in reg.open_tasks():
        rows.append({
            "id": t.id,
            "title": t.title,
            "goal": t.anchor.goal,
            "loops": list(t.anchor.open_loops),
            "loop_ids": [loop_referent_id(t.id, i) for i in range(len(t.anchor.open_loops))],
        })
    return rows


def loop_label(task: Optional[Task], referent_id: Optional[str]) -> Optional[str]:
    if not task or not referent_id:
        return None
    for i, text in enumerate(task.anchor.open_loops):
        if loop_referent_id(task.id, i) == referent_id:
            return text
    return None


def snapshot(reg: InMemoryRegistry, llm: RecordingLLM, res, message: str, turn: int) -> dict:
    active = reg.active()
    pred_t = res.predicted_task_id
    pred_r = res.predicted_referent_id
    task = reg.get(pred_t) if pred_t else active
    pkg = res.package
    proposal = llm.last_proposal or {}
    llm_task = proposal.get("task_id")
    mismatch = (
        message == "fix that"
        and llm_task
        and pred_t
        and llm_task != pred_t
    )
    return {
        "turn": turn,
        "message": message,
        "highlight": mismatch,
        "llm_proposal": {
            "task_id": llm_task,
            "is_new_task": proposal.get("is_new_task"),
            "confidence": proposal.get("confidence"),
            "referent": proposal.get("referent"),
            "rationale": proposal.get("rationale"),
            "note": "Diagnostic only. Not P(correct). Not the final decision.",
        },
        "resolution": {
            "kind": (res.resolution_evidence or {}).get("kind"),
            "rule": (res.resolution_evidence or {}).get("rule"),
            "predicted_task_id": pred_t,
            "predicted_referent_id": pred_r,
            "evidence": dict(res.resolution_evidence or {}),
        },
        "gate": {
            "transition": res.transition.value,
            "task_id": res.task_id,
            "top_raw": res.decision.top_raw,
            "raw_margin": res.decision.raw_margin,
            "clarify_question": res.clarify_question,
        },
        "final_decision": res.transition.value,
        "engine_created_task": (
            {"id": res.task_id, "title": (reg.get(res.task_id).title if res.task_id and reg.get(res.task_id) else None)}
            if res.transition.value == "NEW" else None
        ),
        "state": {
            "active_task_id": active.id if active else None,
            "active_title": active.title if active else None,
            "foreground_referent": pred_r or reg.last_selected_referent(),
            "foreground_loop": loop_label(task, pred_r) if task else None,
            "open_tasks": [
                {
                    "id": t.id, "title": t.title, "status": t.status,
                    "mention_turn": t.mention_turn,
                    "last_active_turn": t.last_active_turn,
                    "open_loops": list(t.anchor.open_loops),
                    "loop_mention_turns": list(t.loop_mention_turns),
                }
                for t in reg.open_tasks()
            ],
        },
        "answer_context": {
            "mode": pkg.context_mode if pkg else None,
            "task_id": pkg.task_id if pkg else None,
            "task_summary": pkg.task_summary if pkg else None,
            "included_loop_ids": list(pkg.included_loop_ids) if pkg else [],
            "open_loops": list(pkg.open_loops) if pkg else [],
            "answer_tokens": pkg.answer_tokens if pkg else 0,
            "decision_tokens": pkg.decision_tokens if pkg else 0,
            "mock_generate": res.answer,
            "note": "Selected task + selected loop. Decision tokens still include open cards. Not savings.",
        },
        "naive_full_history": naive_history(reg),
        "provider": "MockLLM",
        "network": False,
    }


def run_script() -> list[dict]:
    reg = InMemoryRegistry()
    llm = RecordingLLM(MockLLM(scripted=SCRIPTED))
    eng = Engine(llm, reg, SETTINGS, mode="split", new_task_factory=new_task_factory)
    return [snapshot(reg, llm, eng.handle_turn(msg, i), msg, i) for i, msg in enumerate(TURNS, start=1)]


def _box(title: str, lines: list[str]) -> str:
    width = max(len(title) + 2, max((len(x) for x in lines), default=0), 40)
    top = "+- " + title + " " + "-" * max(1, width - len(title) - 3) + "+"
    body = [f"| {row.ljust(width)} |" for row in lines]
    bot = "+" + "-" * (width + 2) + "+"
    return "\n".join([top, *body, bot])


def _tree_naive(rows: list[dict]) -> str:
    lines = ["TRADITIONAL / FULL HISTORY (all open cards; diagnostic, not a savings claim)"]
    for t in rows:
        lines.append(f"+-- [{t['id']}] {t['title']}")
        loops = t["loops"] or ["(none)"]
        for i, loop in enumerate(loops):
            branch = "`--" if i == len(loops) - 1 else "+--"
            lid = t["loop_ids"][i] if t["loop_ids"] else "?"
            lines.append(f"|   {branch} {lid} - {loop}")
    return "\n".join(lines)


def _tree_answer(frame: dict) -> str:
    ac = frame["answer_context"]
    st = frame["state"]
    if not ac.get("task_id"):
        return "CONTEXTFLOW ANSWER CONTEXT\n`-- (none - CLARIFY)"
    loop_ids = ", ".join(ac.get("included_loop_ids") or [])
    loop_txt = (ac.get("open_loops") or ["-"])[0]
    return "\n".join([
        "CONTEXTFLOW",
        f"ACTIVE WORKSTREAM  [{st.get('active_task_id')}] {st.get('active_title')}",
        f"CURRENT REFERENT   {st.get('foreground_referent')} - {st.get('foreground_loop')}",
        f"ANSWER CONTEXT     {ac.get('task_id')} + {loop_ids}",
        f"                   {loop_txt}",
    ])


def format_frame(frame: dict) -> str:
    st = frame["state"]
    prop = frame["llm_proposal"]
    reso = frame["resolution"]
    gate = frame["gate"]
    created = frame.get("engine_created_task")
    banner = ""
    if frame.get("highlight"):
        banner = (
            "*** KILLER TURN: LLM proposes Authentication; "
            "ContextFlow follows deictic clocks ***\n"
        )
    arrow = "               |\n               v"
    parts = [
        "=" * 72,
        f"TURN {frame['turn']}   MockLLM  $0  no network",
        f'USER  "{frame["message"]}"',
        "",
        banner,
        _box("LLM PROPOSAL", [
            f"task={prop.get('task_id')!r}   is_new_task={prop.get('is_new_task')}",
            f"confidence={prop.get('confidence')}   (not P(correct))",
            f"rationale={prop.get('rationale')}",
        ]),
        arrow,
        _box("REFERENT RESOLUTION", [
            f'utterance = "{frame["message"]}"',
            f"mode = {reso.get('kind')}   rule = {reso.get('rule')}",
            f"resolved task = {reso.get('predicted_task_id')}",
            f"foreground = {reso.get('predicted_referent_id')}",
        ]),
        arrow,
        _box("DETERMINISTIC GATE", [
            f"top_raw = {gate.get('top_raw'):.2f}   raw_margin = {gate.get('raw_margin'):.2f}",
            f"decision = {gate['transition']} {gate.get('task_id') or ''}".rstrip(),
        ]),
        arrow,
        "",
        _tree_naive(frame["naive_full_history"]),
        "",
        _tree_answer(frame),
        "",
        f"diagnostic tokens  decision={frame['answer_context']['decision_tokens']}  "
        f"answer={frame['answer_context']['answer_tokens']}  (not savings)",
    ]
    if created:
        parts.insert(5, f"ENGINE NEW persisted task [{created['id']}] {created['title']}\n")
    clocks = [
        f"  [{t['id']}] {t['title']}  mention={t['mention_turn']}  "
        f"last_active={t['last_active_turn']}  loops={t['open_loops']}"
        for t in st["open_tasks"]
    ]
    parts.extend(["", "OPEN TASK STATE", *clocks])
    return "\n".join(p for p in parts if p is not None)


def _workboard(rows: list[dict]) -> str:
    lines = ["FOUR UNFINISHED PROBLEMS"]
    for t in rows:
        lines.append(f"  {t['title'].upper()}")
        loops = t["loops"] or ["(none)"]
        for i, loop in enumerate(loops):
            mark = "`-" if i == len(loops) - 1 else "+-"
            lines.append(f"    {mark} {loop}")
    return "\n".join(lines)


def _compact_line(frame: dict) -> str:
    g = frame["gate"]["transition"]
    tid = frame["resolution"]["predicted_task_id"] or "-"
    rid = frame["resolution"]["predicted_referent_id"] or "-"
    mark = "  <== LOOK" if frame.get("highlight") else ""
    return f"  {frame['turn']:2} {g:8} {tid}/{rid:10}  {frame['message'][:52]}{mark}"


def format_killer(frame: dict) -> str:
    prop = frame["llm_proposal"]
    reso = frame["resolution"]
    gate = frame["gate"]
    ac = frame["answer_context"]
    loop_txt = (ac.get("open_loops") or ["-"])[0]
    title = frame["state"].get("active_title") or ac.get("task_summary") or "-"
    return "\n".join([
        "--------------------------------------------------------------",
        "THE MOMENT",
        'USER              "fix that"',
        "",
        f"LLM PROPOSAL      Authentication  (confidence {prop.get('confidence')})",
        "                  [soft guess; not the decision; not P(correct)]",
        "",
        f"CONTEXTFLOW       mode={reso.get('kind')}  {reso.get('predicted_task_id')} / {reso.get('predicted_referent_id')}",
        "  REFERENT         mention clocks, not the LLM lure",
        "",
        f"GATE              {gate['transition']} {gate.get('task_id')}",
        f"                  top_raw={gate.get('top_raw'):.2f}  raw_margin={gate.get('raw_margin'):.2f}",
        "",
        f"ANSWER CONTEXT    {title} + {loop_txt}",
        "                  (selected task/loop only)",
        "",
        "FULL HISTORY = everything on the card dump.",
        "CONTEXTFLOW  = what matters now.",
        "--------------------------------------------------------------",
    ])


def format_report(frames: list[dict], verbose: bool = False) -> str:
    if verbose:
        header = "\n".join([
            "ContextFlow judge-mode demo (verbose)",
            "The LLM proposes. ContextFlow owns referent state and the act/clarify gate.",
            "",
        ])
        return header + "\n\n".join(format_frame(f) for f in frames) + "\n"

    last = frames[-1]
    killer = next((f for f in frames if f.get("highlight")), frames[11] if len(frames) > 11 else last)
    corr = next((f for f in frames if f["message"] == "no, the other one"), None)
    lines = [
        "ContextFlow  |  60-second judge demo  |  MockLLM  $0  no network",
        "",
        "Long conversations fail when the system does not know which piece of",
        "unfinished work the user is pointing at. Watch four open problems,",
        "then the user says \"fix that\".",
        "",
        _workboard(last["naive_full_history"]),
        "",
        format_killer(killer),
        "",
        _tree_naive(killer["naive_full_history"]),
        "",
        _tree_answer(killer),
        "",
        "TURN LOG  (decision / resolved task.loop / utterance)",
        *[_compact_line(f) for f in frames],
        "",
        "The LLM proposes. ContextFlow keeps task/loop clocks and decides ACT vs CLARIFY.",
        "PoC evidence is controlled, not a production benchmark. See docs/POC_FREEZE.md.",
    ]
    if corr:
        lines.extend([
            "",
            "Also: \"no, the other one\" (correction). LLM still guesses Authentication;",
            f"ContextFlow resolves {corr['resolution']['predicted_task_id']}/"
            f"{corr['resolution']['predicted_referent_id']} and "
            f"{corr['gate']['transition']}s.",
        ])
    return "\n".join(lines) + "\n"


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    from pathlib import Path
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, JSONResponse
    import uvicorn

    ui = Path(__file__).with_name("demo_ui.html")
    api = FastAPI(title="ContextFlow demo")

    @api.get("/")
    def index():
        return FileResponse(ui)

    @api.get("/api/replay")
    def replay():
        return JSONResponse(run_script())

    print(f"ContextFlow demo  http://{host}:{port}  (local only, MockLLM, $0)")
    uvicorn.run(api, host=host, port=port, log_level="warning")


def main() -> None:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser(description="ContextFlow $0 interleaved demo")
    p.add_argument("--verbose", action="store_true", help="print every turn in full")
    p.add_argument("--json", action="store_true")
    p.add_argument("--serve", action="store_true", help="local browser UI; still MockLLM, no Vertex")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    if args.serve:
        serve(args.host, args.port)
        return
    frames = run_script()
    if args.json:
        print(json.dumps(frames, indent=2))
    else:
        print(format_report(frames, verbose=args.verbose))


if __name__ == "__main__":
    main()
