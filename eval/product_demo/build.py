"""Build a deterministic one-window product-demo snapshot.

CONTROLLED ADVERSARIAL ENGINEERING FIXTURE — demo mechanisms, not production accuracy.
MockLLM + MockMemoryExtractor. $0. No Vertex. No network.
"""

from __future__ import annotations

import hashlib
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
from eval.product_demo.scenario import (
    DEMO_BOUNDARY,
    DEMO_LABEL,
    EXPECTED_BEAT_LABELS,
    MESSAGE_OVERRIDES,
    NARRATIVE,
    PRODUCT_LLM_EXTRA,
    REVIEWER_SENTENCE,
    TAGLINE,
    THESIS,
)
from eval.ten_workstream.load import extract_scripts, llm_scripts, load_fixture
from eval.ten_workstream.run import make_registry

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "out" / "product_demo.json"
UI = Path(__file__).resolve().parent / "ui.html"


def _status_label(task, selected_id: str | None, transition: str | None) -> str:
    if selected_id and task.id == selected_id:
        if transition == "RETURN":
            return "RETURNING TO"
        if transition == "CLARIFY":
            return "NEEDS CLARIFICATION"
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
        decisions = [i.text for i in asserted if i.kind == "decision"]
        corrections = [i.text for i in asserted if i.kind == "correction"]
        constraints = [i.text for i in asserted if i.kind == "constraint"]
        facts = [i.text for i in asserted if i.kind in ("fact", "preference", "event")]
        history_lines = []
        for i in superseded:
            nxt = next((x.text for x in asserted if x.id == i.superseded_by), None)
            if nxt:
                history_lines.append(f"{i.text} → superseded by {nxt}")
            else:
                history_lines.append(f"{i.text} → superseded")
        rows.append({
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "status_label": _status_label(t, selected_id, transition),
            "goal": t.anchor.goal,
            "open_loops": list(t.anchor.open_loops),
            "last_active_turn": t.last_active_turn,
            "decisions": decisions,
            "corrections": corrections,
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
        f"Thread: {task.title}",
        f"Goal: {task.anchor.goal}",
        "CURRENT decisions: " + (", ".join(proj.decisions) or "—"),
        "CURRENT constraints: " + (", ".join(proj.constraints) or "—"),
        "CURRENT facts: " + (", ".join(proj.facts) or "—"),
    ])
    full = full_history_prompt(history, message)
    recent = recent_prompt(history, message, RECENT_K)
    cf = contextflow_answer_prompt(rendered, message)
    return {
        "full": {
            "preview": full[:900], "tokens": count(full),
            "label": "FULL history",
            "blurb": "Everything is available — including unrelated threads.",
        },
        "recent": {
            "preview": recent[:900], "tokens": count(recent),
            "label": f"RECENT (last {RECENT_K})",
            "blurb": "Recent turns can miss older working state.",
        },
        "contextflow": {
            "preview": cf[:900], "tokens": count(cf),
            "label": "ContextFlow working context",
            "blurb": "Only the resumed thread’s current working state.",
        },
        "qualitative": {
            "full": "Everything is available — including unrelated threads.",
            "recent": "Recent turns can miss older working state.",
            "contextflow": "Only the resumed thread’s current working state.",
        },
    }


def _lifecycle_e(store) -> dict:
    asserted = store.asserted("E")
    hist = store.historical("E")
    color_now = [i.text for i in asserted if i.slot == "color"]
    constraints = [
        i.text for i in asserted if i.kind == "constraint"
    ]
    superseded = [
        {"text": i.text, "status": i.status, "superseded_by": i.superseded_by,
         "provenance": i.provenance, "source_turn": i.source_turn}
        for i in hist if i.status == "superseded" and i.slot == "color"
    ]
    return {
        "current": color_now,
        "constraints": constraints,
        "superseded": superseded,
    }


def _evidence(r, focus, store, working) -> dict:
    """Technical drawer — secondary to the product story."""
    items = []
    if focus:
        for i in store.asserted(focus.id):
            items.append({
                "text": i.text, "kind": i.kind, "slot": i.slot,
                "status": i.status, "source_turn": i.source_turn,
                "provenance": i.provenance, "referent_id": i.referent_id,
            })
        for i in store.historical(focus.id):
            if i.status == "superseded":
                items.append({
                    "text": i.text, "kind": i.kind, "slot": i.slot,
                    "status": i.status, "source_turn": i.source_turn,
                    "provenance": i.provenance,
                    "superseded_by": i.superseded_by,
                    "why_excluded_from_current": "superseded",
                })
    excluded_why = []
    if working:
        for e in working.get("excluded") or []:
            excluded_why.append({
                "workstream": e["workstream"],
                "why": "unrelated_to_selected_thread",
                "samples": e.get("samples") or [],
            })
    return {
        "selected_workstream": r.task_id,
        "referent": r.predicted_referent_id,
        "transition": r.transition.value if r.transition else None,
        "package_present": r.package is not None,
        "clarify": r.clarify_question,
        "focus_items": items,
        "excluded": excluded_why,
    }


def _semantic_fingerprint(store, reg, frames: list[dict]) -> str:
    """Stable hash of demo-relevant semantic state (not wall-clock)."""
    blob = {
        "asserted": sorted(
            (i.workstream_id, i.kind, i.slot or "", i.text, i.status)
            for i in store.all()
        ),
        "frames": [
            {
                "turn": f["turn"], "beat": f["beat"],
                "transition": f["transition"], "task_id": f["task_id"],
                "message": f["message"],
                "current": (f.get("working") or {}).get("included"),
                "clarify": bool(f.get("clarify")),
            }
            for f in frames
        ],
        "open": sorted(t.id for t in reg.open_tasks()),
    }
    raw = json.dumps(blob, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _validate_demo(frames: list[dict], store, reg) -> list[str]:
    """Fail-closed product invariants. Empty list = demo healthy."""
    errors: list[str] = []
    if len(frames) != 15:
        errors.append(f"expected_15_beats_got_{len(frames)}")
    if len(NARRATIVE) != 15 or len(EXPECTED_BEAT_LABELS) != 15:
        errors.append("narrative_length_mismatch")
    if len(reg.all()) != 10:
        errors.append(f"expected_10_workstreams_got_{len(reg.all())}")

    turns = [f["turn"] for f in frames]
    if turns != [n["turn"] for n in NARRATIVE]:
        errors.append("beat_turn_order_mismatch")

    hero = next((f for f in frames if f.get("hero") or f["beat"] == "return"), None)
    if hero is None:
        errors.append("missing_hero_return_beat")
    else:
        if hero["message"] != MESSAGE_OVERRIDES[38]:
            errors.append("hero_message_mismatch")
        if hero.get("transition") != "RETURN" or hero.get("task_id") != "E":
            errors.append("hero_not_return_to_outfit")
        working = hero.get("working") or {}
        inc = working.get("included") or {}
        blob = " ".join(
            (inc.get("decisions") or []) + (inc.get("constraints") or [])
        ).lower()
        if "navy" not in blob:
            errors.append("hero_missing_navy_current")
        if "black" in " ".join(inc.get("decisions") or []).lower():
            errors.append("hero_projects_superseded_black_as_current")
        life = hero.get("lifecycle") or {}
        if not any(s.get("text") == "black" for s in life.get("superseded") or []):
            errors.append("hero_missing_black_history")
        excl = " ".join(
            e.get("workstream", "").lower() for e in (working.get("excluded") or [])
        )
        for needle in ("authentication", "lisbon", "trivia"):
            if needle not in excl:
                errors.append(f"hero_missing_excluded_{needle}")

    clarify = next((f for f in frames if f["beat"] == "clarify"), None)
    if clarify is None:
        errors.append("missing_clarify_beat")
    elif clarify.get("transition") != "CLARIFY":
        errors.append("clarify_beat_not_clarify")
    elif "maybe" not in (clarify.get("message") or "").lower():
        errors.append("clarify_message_mismatch")

    if any(not f.get("generate_did_not_mutate_memory") for f in frames):
        errors.append("generate_mutated_memory")

    # Supersession: black historical, navy asserted on E
    asserted_e = store.asserted("E")
    hist_e = store.historical("E")
    if not any(i.text == "navy" and i.status == "asserted" for i in asserted_e):
        errors.append("navy_not_asserted_on_outfit")
    if not any(i.text == "black" and i.status == "superseded" for i in hist_e):
        errors.append("black_not_superseded_on_outfit")

    return errors


def public_demo_payload(payload: dict) -> dict:
    """Browser-facing snapshot: product story only — no evaluator internals."""
    frames = []
    for f in payload.get("frames") or []:
        frames.append({
            "beat": f.get("beat"),
            "hero": f.get("hero"),
            "caption": f.get("caption"),
            "turn": f.get("turn"),
            "message": f.get("message"),
            "transition": f.get("transition"),
            "product_route": f.get("product_route"),
            "task_id": f.get("task_id"),
            "workstream_title": f.get("workstream_title"),
            "clarify": f.get("clarify"),
            "answer_preview": f.get("answer_preview"),
            "workstreams": [
                {
                    "title": w.get("title"),
                    "status": w.get("status"),
                    "status_label": w.get("status_label"),
                    "active_now": w.get("active_now"),
                }
                for w in (f.get("workstreams") or [])
            ],
            "inspector": [
                {
                    "id": i.get("id"),
                    "title": i.get("title"),
                    "status_label": i.get("status_label"),
                    "decisions": i.get("decisions"),
                    "constraints": i.get("constraints"),
                    "facts": i.get("facts"),
                    "history_lines": i.get("history_lines"),
                }
                for i in (f.get("inspector") or [])
            ],
            "focus_workstream_id": f.get("focus_workstream_id"),
            "working": f.get("working"),
            "compare": f.get("compare"),
            "lifecycle": f.get("lifecycle"),
            "evidence": {
                "selected_workstream": (f.get("evidence") or {}).get("selected_workstream"),
                "transition": (f.get("evidence") or {}).get("transition"),
                "clarify": (f.get("evidence") or {}).get("clarify"),
                "excluded": (f.get("evidence") or {}).get("excluded"),
                "focus_items": (f.get("evidence") or {}).get("focus_items"),
            },
        })
    return {
        "label": payload.get("label"),
        "demo_label": payload.get("demo_label"),
        "demo_boundary": payload.get("demo_boundary"),
        "checkpoint": payload.get("checkpoint"),
        "thesis": payload.get("thesis"),
        "reviewer_sentence": payload.get("reviewer_sentence"),
        "tagline": payload.get("tagline"),
        "demo_ok": payload.get("demo_ok"),
        "demo_error": payload.get("demo_error"),
        "disclaimer": payload.get("disclaimer"),
        "honest_boundary": payload.get("honest_boundary"),
        "controls": payload.get("controls"),
        "paths": payload.get("paths"),
        "frames": frames,
        "workstream_titles": payload.get("workstream_titles"),
    }


def build() -> dict:
    fx = load_fixture()
    narrative_turns = {n["turn"] for n in NARRATIVE}
    max_turn = max(narrative_turns)

    scripts = extract_scripts(fx)
    llm_s = {**llm_scripts(fx), **PRODUCT_LLM_EXTRA}
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
        msg = MESSAGE_OVERRIDES.get(turn, t["message"])
        ids_before = {i.id for i in store.all()}
        pipe = run_turn(
            eng, writer, ext,
            conversation_id="product-demo",
            message=msg, turn=turn,
        )
        r = pipe.turn
        # generate must not invent memory ids beyond extractor commits
        new_ids = {i.id for i in store.all()} - ids_before
        extract_ids = {i.id for i in pipe.extract.items}
        generate_mutated = bool(new_ids - extract_ids)

        history.append({"role": "user", "text": msg, "turn": turn})
        if r.answer:
            history.append({"role": "assistant", "text": r.answer, "turn": turn})

        if turn not in narrative_turns:
            continue

        meta = caption_by[turn]
        task = reg.get(r.task_id) if r.task_id else None
        focus = task
        if meta["beat"] in ("return", "correct", "clarify"):
            focus = reg.get("E")

        working = _working_view(focus, store, reg) if focus else None
        compare = _compare(history, msg, focus, store, reg) if focus else None
        transition = r.transition.value if r.transition else None
        product_route = (
            "NEEDS CLARIFICATION" if transition == "CLARIFY" or r.clarify_question
            else ("RETURNING TO" if transition == "RETURN" else (transition or "—"))
        )
        frames.append({
            "beat": meta["beat"],
            "hero": bool(meta.get("hero")),
            "caption": meta["caption"],
            "turn": turn,
            "message": msg,
            "transition": transition,
            "product_route": product_route,
            "task_id": r.task_id,
            "referent_id": r.predicted_referent_id,
            "workstream_title": (focus or task).title if (focus or task) else None,
            "clarify": r.clarify_question,
            "answer_preview": (r.answer or "")[:180],
            "generate_did_not_mutate_memory": not generate_mutated,
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
            "evidence": _evidence(r, focus, store, working),
            "memory_counts": {
                "asserted": len(store.asserted()),
                "all": len(store.all()),
            },
        })

    demo_errors = _validate_demo(frames, store, reg)
    fingerprint = _semantic_fingerprint(store, reg, frames)
    payload = {
        "label": f"{DEMO_LABEL} — product demo",
        "demo_label": DEMO_LABEL,
        "demo_boundary": DEMO_BOUNDARY,
        "checkpoint": "DEMO-READY / RESEARCH-PRODUCT CHECKPOINT",
        "thesis": THESIS,
        "reviewer_sentence": REVIEWER_SENTENCE,
        "tagline": TAGLINE,
        "demo_ok": not demo_errors,
        "demo_error": None if not demo_errors else {
            "message": "DEMO ERROR — product invariants failed",
            "errors": demo_errors,
        },
        "disclaimer": (
            f"{DEMO_LABEL} · {DEMO_BOUNDARY} · MockLLM · offline · "
            "$0 · no Vertex · no credentials · no network · not production-ready"
        ),
        "honest_boundary": {
            "fixture": "controlled synthetic engineering demo",
            "deterministic": True,
            "memory": "in-memory (process-local)",
            "auth": False,
            "natural_chat_benchmark": False,
            "production_ready": False,
            "vertex": False,
            "gcp": False,
            "network": False,
        },
        "controls": [
            "RESET DEMO", "PLAY SCENARIO", "STEP", "RETURN TO THREAD", "INSPECT MEMORY",
        ],
        "paths": {
            "mock": "default (this demo)",
            "command": "python -m eval.product_demo --serve",
        },
        "canonical_sequence": [
            {"turn": n["turn"], "beat": n["beat"], "caption": n["caption"],
             "label": EXPECTED_BEAT_LABELS[i]}
            for i, n in enumerate(NARRATIVE)
        ],
        "frames": frames,
        "workstream_titles": [w["title"] for w in fx["workstreams"]],
        "semantic_fingerprint": fingerprint,
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
        "thesis": p["thesis"],
        "frames": len(p["frames"]),
        "fingerprint": p["semantic_fingerprint"],
        "out": str(OUT),
        "ui": str(UI),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
