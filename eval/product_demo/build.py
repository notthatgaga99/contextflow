"""Build a deterministic product-demo snapshot from the ten-workstream fixture.

CONTROLLED ADVERSARIAL ENGINEERING FIXTURE — demo mechanisms, not production accuracy.
MockLLM + MockMemoryExtractor. $0. No Vertex. No network.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import SETTINGS
from app.context.working_set import WorkingContextBuilder
from app.engine import Engine
from app.llm.mock import MockLLM
from app.llm.tokens import count
from app.memory.extractor import MockMemoryExtractor
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.turn_pipeline import run_turn
from eval.consented_case.contexts import (
    RECENT_K,
    contextflow_answer_prompt,
    full_history_prompt,
    recent_prompt,
)
from eval.ten_workstream.load import extract_scripts, llm_scripts, load_fixture
from eval.ten_workstream.run import make_registry

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "out" / "product_demo.json"
UI = Path(__file__).resolve().parent / "ui.html"

# Ordered ~60–120s pitch. Every listed turn becomes a UI beat.
# Transitions/clarify come from frozen ContextFlow + Mock scripts — not forced.
NARRATIVE = [
    {"turn": 1, "beat": "open", "caption": "Open an authentication thread"},
    {"turn": 3, "beat": "open", "caption": "Open the outfit thread (black)"},
    {"turn": 5, "beat": "switch", "caption": "Similar technical thread - orders API"},
    {"turn": 10, "beat": "switch", "caption": "Jump to Docker / CI"},
    {"turn": 11, "beat": "switch", "caption": "Unrelated travel - Lisbon"},
    {"turn": 20, "beat": "switch", "caption": "Trivia noise - many threads still alive"},
    {"turn": 28, "beat": "switch", "caption": "Another distraction - Stripe deadline"},
    {"turn": 32, "beat": "correct", "caption": "Correction: black -> navy (history kept)"},
    {"turn": 35, "beat": "distract", "caption": "Leave the outfit again"},
    {"turn": 37, "beat": "deictic", "caption": "Deictic 'fix that' amid open work"},
    {"turn": 38, "beat": "return", "caption": "Return - reconstruct navy / formal / evening"},
    {"turn": 46, "beat": "clarify", "caption": "Underspecified - refuse to guess"},
]


def _status_label(task, selected_id: str | None, transition: str | None) -> str:
    if selected_id and task.id == selected_id:
        if transition == "RETURN":
            return "Returned"
        if transition == "CLARIFY":
            return "Ambiguous"
        return "Active"
    if task.status == "resolved":
        return "Resolved"
    return "Paused"


def _inspector(reg, store, selected_id: str | None, transition: str | None) -> list[dict]:
    rows = []
    for t in reg.all():
        asserted = store.asserted(t.id)
        hist = store.historical(t.id)
        superseded = [i for i in hist if i.status == "superseded"]
        decisions = [i.text for i in asserted if i.kind in ("decision", "correction")]
        constraints = [i.text for i in asserted if i.kind == "constraint"]
        facts = [i.text for i in asserted if i.kind in ("fact", "preference", "event")]
        history_lines = []
        for i in superseded:
            nxt = next((x.text for x in asserted if x.id == i.superseded_by), None)
            if nxt:
                history_lines.append(f"{i.text} -> superseded by {nxt}")
            else:
                history_lines.append(f"{i.text} -> superseded")
        rows.append({
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "status_label": _status_label(t, selected_id, transition),
            "goal": t.anchor.goal,
            "open_loops": list(t.anchor.open_loops),
            "last_active_turn": t.last_active_turn,
            "decisions": decisions,
            "constraints": constraints,
            "facts": facts,
            "history_lines": history_lines,
            "superseded": [
                {
                    "text": i.text, "slot": i.slot, "superseded_by": i.superseded_by,
                    "source_turn": i.source_turn, "provenance": i.provenance,
                }
                for i in superseded
            ],
            "asserted_count": len(asserted),
        })
    return rows


def _working_view(task, store, reg) -> dict:
    proj = WorkingContextBuilder().project(
        task, f"{task.id}.loop1", store, reg.open_tasks(),
    )
    included = {
        "decisions": list(proj.decisions),
        "constraints": list(proj.constraints),
        "facts": list(proj.facts),
    }
    excluded = []
    for t in reg.all():
        if t.id == task.id:
            continue
        items = store.asserted(t.id)
        if not items:
            continue
        excluded.append({
            "workstream": t.title,
            "samples": [i.text for i in items[:3]],
        })
    return {
        "included": included,
        "excluded": excluded,
        "excluded_titles": list(proj.excluded_workstreams),
    }


def _compare(history: list[dict], message: str, task, store, reg) -> dict:
    proj = WorkingContextBuilder().project(
        task, f"{task.id}.loop1", store, reg.open_tasks(),
    )
    rendered = "\n".join([
        f"WORKSTREAM: {task.title}",
        f"GOAL: {task.anchor.goal}",
        "DECISIONS: " + (", ".join(proj.decisions) or "—"),
        "CONSTRAINTS: " + (", ".join(proj.constraints) or "—"),
        "FACTS: " + (", ".join(proj.facts) or "—"),
    ])
    full = full_history_prompt(history, message)
    recent = recent_prompt(history, message, RECENT_K)
    cf = contextflow_answer_prompt(rendered, message)
    return {
        "full": {
            "preview": full[:900], "tokens": count(full),
            "label": "FULL HISTORY",
            "blurb": "Has the facts, but carries unrelated material.",
        },
        "recent": {
            "preview": recent[:900], "tokens": count(recent),
            "label": f"RECENT (last {RECENT_K})",
            "blurb": "May miss older decisions.",
        },
        "contextflow": {
            "preview": cf[:900], "tokens": count(cf),
            "label": "CONTEXTFLOW WORKING SET",
            "blurb": (
                "Selected workstream + current decisions/constraints; "
                "unrelated state excluded."
            ),
        },
        "qualitative": {
            "full": "Has the facts, but carries unrelated material.",
            "recent": "May miss older decisions.",
            "contextflow": (
                "Selected workstream + current decisions/constraints; "
                "unrelated state excluded."
            ),
        },
    }


def _lifecycle_e(store) -> dict:
    asserted = store.asserted("E")
    hist = store.historical("E")
    color_now = [i.text for i in asserted if i.slot == "color"]
    superseded = [
        {"text": i.text, "status": i.status, "superseded_by": i.superseded_by,
         "provenance": i.provenance, "source_turn": i.source_turn}
        for i in hist if i.status == "superseded" and i.slot == "color"
    ]
    return {"current": color_now, "superseded": superseded}


def build() -> dict:
    fx = load_fixture()
    turn_by = {t["turn"]: t for t in fx["turns"]}
    narrative_turns = {n["turn"] for n in NARRATIVE}
    max_turn = max(narrative_turns)

    scripts = extract_scripts(fx)
    llm_s = llm_scripts(fx)
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="product-demo")
    writer = MemoryWriter(store, reg)
    eng = Engine(
        MockLLM(llm_s), reg, SETTINGS, memory_store=store,
        working_context_builder=WorkingContextBuilder(),
    )
    ext = MockMemoryExtractor(scripts)

    history: list[dict] = []
    frames: list[dict] = []
    caption_by = {n["turn"]: n for n in NARRATIVE}

    for t in fx["turns"]:
        turn = t["turn"]
        if turn > max_turn:
            break
        msg = t["message"]
        pipe = run_turn(
            eng, writer, ext,
            conversation_id="product-demo",
            message=msg, turn=turn,
        )
        r = pipe.turn
        history.append({"role": "user", "text": msg, "turn": turn})
        if r.answer:
            history.append({"role": "assistant", "text": r.answer, "turn": turn})

        if turn not in narrative_turns:
            continue

        meta = caption_by[turn]
        task = reg.get(r.task_id) if r.task_id else None
        # On CLARIFY, still show outfit inspector if that is the story beat.
        focus = task
        if meta["beat"] in ("return", "correct", "clarify") and reg.get("E"):
            focus = reg.get("E") if meta["beat"] != "clarify" or not task else task
        if meta["beat"] == "return":
            focus = reg.get("E")
        if meta["beat"] == "correct":
            focus = reg.get("E")

        working = _working_view(focus, store, reg) if focus else None
        compare = _compare(history, msg, focus, store, reg) if focus else None
        transition = r.transition.value if r.transition else None
        frames.append({
            "beat": meta["beat"],
            "caption": meta["caption"],
            "turn": turn,
            "message": msg,
            "transition": transition,
            "task_id": r.task_id,
            "workstream_title": task.title if task else None,
            "clarify": r.clarify_question,
            "answer_preview": (r.answer or "")[:180],
            "workstreams": [
                {
                    "id": x.id, "title": x.title, "status": x.status,
                    "status_label": _status_label(x, r.task_id, transition),
                    "last_active": x.last_active_turn,
                    "active_now": x.id == r.task_id,
                }
                for x in reg.all()
            ],
            "inspector": _inspector(reg, store, r.task_id, transition),
            "focus_workstream_id": focus.id if focus else None,
            "working": working,
            "compare": compare,
            "lifecycle": _lifecycle_e(store),
            "memory_counts": {
                "asserted": len(store.asserted()),
                "all": len(store.all()),
            },
        })

    payload = {
        "label": "CONTROLLED ADVERSARIAL ENGINEERING FIXTURE — product demo",
        "checkpoint": "DEMO-READY / RESEARCH-PRODUCT CHECKPOINT",
        "tagline": (
            "ContextFlow doesn't try to remember everything equally. "
            "It maintains multiple open workstreams and reconstructs the "
            "working state that matters when you return."
        ),
        "disclaimer": (
            "Demo-only · MockLLM · CONTROLLED ADVERSARIAL ENGINEERING FIXTURE · "
            "not organic chat · not production-ready · $0 · no network"
        ),
        "paths": {
            "mock": "default (this demo)",
            "ollama": "CF_USE_OLLAMA=1 (optional local)",
            "vertex": "explicit eval harnesses only — not this demo",
        },
        "pitch_questions": [
            "What does ContextFlow remember?",
            "What does it deliberately exclude from the current context?",
            "Can it keep many tasks alive simultaneously?",
            "Can it return after unrelated activity?",
            "Can it preserve decisions and constraints?",
            "Can it handle corrections?",
            "Can it CLARIFY instead of guessing?",
            "Why isn't this just a longer context window?",
        ],
        "frames": frames,
        "workstream_titles": [w["title"] for w in fx["workstreams"]],
        "narrative_note": (
            "Beat order is curated for the pitch; routing outcomes are produced by "
            "frozen ContextFlow + MockLLM scripts on the synthetic fixture."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def main() -> int:
    p = build()
    print(json.dumps({
        "status": "ok",
        "checkpoint": p["checkpoint"],
        "frames": len(p["frames"]),
        "out": str(OUT),
        "ui": str(UI),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
