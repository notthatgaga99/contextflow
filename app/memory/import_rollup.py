"""Opt-in import of catalog/rollup workstreams into a live conversation.

Best practices:
- Explicit call only — never auto-merge on NEW CHAT.
- Imported cards start paused (fail-closed; user/gate must select).
- Seed asserted memory via MemoryWriter (same validate/commit path).
- Remap workstream ids so imports never collide with live ids.
- Does not call the gate or answer model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.memory.rollup import WorkstreamRollup
from app.memory.writer import MemoryWriter, WriterResult
from app.models.memory import MemoryPatch
from app.models.task import Task, TaskAnchor
from app.router.referent import ensure_loop_clocks


@dataclass
class ImportResult:
    ok: bool
    imported: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    writer: WriterResult | None = None


def _cues_from_text(*parts: str, limit: int = 8) -> list[str]:
    blob = " ".join(p for p in parts if p).lower()
    words = re.findall(r"[a-z0-9]{3,}", blob)
    out: list[str] = []
    seen: set[str] = set()
    for w in words:
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= limit:
            break
    return out


def _next_task_id(registry) -> str:
    n = 1
    while registry.get(f"T{n}") is not None:
        n += 1
    return f"T{n}"


def _workstreams_from_payload(rollup: dict) -> list[WorkstreamRollup]:
    rows = rollup.get("workstreams") or []
    out: list[WorkstreamRollup] = []
    for r in rows:
        if isinstance(r, WorkstreamRollup):
            out.append(r)
            continue
        out.append(
            WorkstreamRollup(
                workstream_id=str(r.get("workstream_id") or r.get("id") or ""),
                title=str(r.get("title") or ""),
                goal=str(r.get("goal") or ""),
                status=str(r.get("status") or "paused"),
                open_loops=list(r.get("open_loops") or []),
                decisions=list(r.get("decisions") or []),
                constraints=list(r.get("constraints") or []),
                facts=list(r.get("facts") or []),
                entities=list(r.get("entities") or []),
                last_active_turn=int(r.get("last_active_turn") or 0),
                mention_turn=int(r.get("mention_turn") or 0),
                item_count=int(r.get("item_count") or 0),
            )
        )
    return out


def import_rollup_workstreams(
    registry,
    writer: MemoryWriter,
    rollup: dict,
    *,
    workstream_ids: list[str] | None = None,
    turn: int = 0,
    as_paused: bool = True,
) -> ImportResult:
    """Seed selected rollup workstreams into registry + asserted memory.

    ``workstream_ids`` None → import all workstreams in the rollup.
    """
    wanted = None
    if workstream_ids is not None:
        wanted = {str(x).strip() for x in workstream_ids if str(x).strip()}
        if not wanted:
            return ImportResult(ok=False, errors=["workstream_ids_empty"])

    rows = _workstreams_from_payload(rollup)
    if not rows:
        return ImportResult(ok=False, errors=["rollup_empty"])

    imported: list[dict] = []
    skipped: list[str] = []
    patches: list[MemoryPatch] = []
    src_turn = max(0, int(turn))

    for ws in rows:
        src_id = (ws.workstream_id or "").strip()
        if not src_id:
            skipped.append("(missing_id)")
            continue
        if wanted is not None and src_id not in wanted:
            continue

        new_id = _next_task_id(registry)
        loops = list(ws.open_loops)[:5] or ([ws.goal[:200]] if ws.goal else [])
        title = (ws.title or ws.goal or new_id)[:48]
        goal = (ws.goal or ws.title or "")[:160]
        task = Task(
            id=new_id,
            title=title,
            status="paused" if as_paused else "active",
            retrieval_cues=_cues_from_text(title, goal, " ".join(loops)),
            anchor=TaskAnchor(
                goal=goal,
                open_loops=loops,
                decisions=list(ws.decisions)[:6],
                constraints=list(ws.constraints)[:6],
                entities=list(ws.entities)[:8],
            ),
            last_active_turn=0,
            mention_turn=0,
        )
        ensure_loop_clocks(task)
        registry.add(task)

        def _patch(kind: str, text: str, slot: str | None = None) -> MemoryPatch:
            return MemoryPatch(
                kind=kind,
                text=text,
                source_turn=src_turn,
                workstream_id=new_id,
                slot=slot,
                proposer="system",
                action="assert",
            )

        for i, text in enumerate(ws.decisions):
            if (text or "").strip():
                patches.append(_patch("decision", text.strip(), slot=f"import_decision_{i}"))
        for i, text in enumerate(ws.constraints):
            if (text or "").strip():
                patches.append(_patch("constraint", text.strip(), slot=f"import_constraint_{i}"))
        for i, text in enumerate(ws.facts):
            if (text or "").strip():
                patches.append(_patch("fact", text.strip(), slot=f"import_fact_{i}"))
        for i, text in enumerate(ws.entities):
            if (text or "").strip():
                patches.append(_patch("entity", text.strip(), slot=f"import_entity_{i}"))

        imported.append({
            "source_workstream_id": src_id,
            "new_workstream_id": new_id,
            "title": title,
            "status": task.status,
            "seeded_items": (
                len(ws.decisions) + len(ws.constraints) + len(ws.facts) + len(ws.entities)
            ),
        })

    if wanted is not None:
        have = {row["source_workstream_id"] for row in imported}
        for wid in wanted:
            if wid not in have:
                skipped.append(wid)

    if not imported:
        return ImportResult(
            ok=False,
            imported=[],
            skipped=skipped,
            errors=["nothing_imported"],
        )

    writer_result = None
    if patches:
        proposed = writer.propose(patches)
        writer_result = writer.validate(proposed)
        if not writer_result.ok:
            return ImportResult(
                ok=False,
                imported=imported,
                skipped=skipped,
                errors=list(writer_result.errors),
                writer=writer_result,
            )
        writer_result = writer.commit(proposed, turn=src_turn)
        if not writer_result.ok:
            return ImportResult(
                ok=False,
                imported=imported,
                skipped=skipped,
                errors=list(writer_result.errors) or ["commit_failed"],
                writer=writer_result,
            )

    return ImportResult(
        ok=True,
        imported=imported,
        skipped=skipped,
        errors=[],
        writer=writer_result,
    )
