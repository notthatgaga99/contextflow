"""Load consented session + human interpretation. Eval only. No routing changes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.memory.registry import InMemoryRegistry
from app.models.task import Task, TaskAnchor
from app.router.referent import ensure_loop_clocks

ROOT = Path(__file__).resolve().parents[2]
SESSION_PATH = ROOT / "data" / "consented" / "session.json"
INTERPRETATION_PATH = ROOT / "eval" / "consented_case" / "interpretation.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def session_ready(path: Path = SESSION_PATH) -> bool:
    return path.is_file()


def interpretation_ready(path: Path = INTERPRETATION_PATH) -> bool:
    return path.is_file()


def user_turns(session: dict) -> list[dict]:
    return [t for t in session["turns"] if t.get("role") == "user"]


def turns_before(session: dict, user_turn_index: int) -> list[dict]:
    """All messages strictly before the user turn with field i == user_turn_index."""
    return [t for t in session["turns"] if int(t["i"]) < int(user_turn_index)]


def user_text(session: dict, user_turn_index: int) -> str:
    for t in session["turns"]:
        if int(t["i"]) == int(user_turn_index) and t.get("role") == "user":
            return str(t["text"])
    raise KeyError(f"no user turn i={user_turn_index}")


def _task_from_card(card: dict) -> Task:
    a = TaskAnchor(
        goal=str(card.get("unresolved_objective") or card.get("goal") or card.get("title") or ""),
        current_state=str(card.get("current_state") or ""),
        decisions=list(card.get("decisions") or []),
        constraints=list(card.get("constraints") or []),
        open_loops=list(card.get("open_loops") or []),
        entities=list(card.get("entities") or []),
    )
    t = Task(
        id=str(card["id"]),
        title=str(card.get("title") or card["id"]),
        status=str(card.get("status") or "paused"),
        retrieval_cues=list(card.get("retrieval_cues") or []),
        anchor=a,
        last_active_turn=int(card.get("last_active_turn") or 0),
        mention_turn=int(card.get("mention_turn") or 0),
        loop_mention_turns=list(card.get("loop_mention_turns") or []),
    )
    ensure_loop_clocks(t)
    return t


def registry_for_probe(interp: dict, probe: dict) -> InMemoryRegistry:
    """Human working-memory snapshot *before* the probe utterance. Not engine-inferred."""
    clocks = probe.get("clocks") or {}
    by_id = {str(w["id"]): dict(w) for w in interp.get("workstreams") or []}
    for tid, patch in clocks.items():
        if tid in by_id:
            by_id[tid].update(patch)
        else:
            by_id[tid] = {"id": tid, **patch}
    reg = InMemoryRegistry()
    active_id = probe.get("active_task_id")
    for card in by_id.values():
        if card.get("is_task") is False:
            continue
        t = _task_from_card(card)
        if active_id and t.id == active_id:
            t.status = "active"
        elif t.status == "active" and t.id != active_id:
            t.status = "paused"
        reg.add(t)
    if active_id and reg.get(active_id):
        turn = int((clocks.get(active_id) or {}).get("last_active_turn") or probe.get("user_turn_index") or 0)
        if turn:
            reg.mark_active(active_id, turn)
    last_ref = probe.get("last_selected_referent")
    if last_ref:
        reg.set_last_selected_referent(str(last_ref))
    return reg
