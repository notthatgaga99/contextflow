"""MemoryExtractor: conversation → MemoryPatch proposals. Never writes MemoryStore.

Does not select the current working context. That is ContextFlow (resolver/gate).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.memory.writer import MemoryWriter, WriterResult
from app.models.memory import ITEM_KINDS, MemoryItem, MemoryPatch, patch_from_dict
from app.models.task import Task


@dataclass
class ExtractRequest:
    message: str
    source_turn: int
    conversation_id: str = ""
    history: list[dict] = field(default_factory=list)
    open_workstreams: list[Task] = field(default_factory=list)
    asserted_items: list[MemoryItem] = field(default_factory=list)


@dataclass
class ExtractResult:
    patches: list[MemoryPatch]
    notes: list[str] = field(default_factory=list)
    uncertain: bool = False


@runtime_checkable
class MemoryExtractor(Protocol):
    def extract(self, req: ExtractRequest) -> ExtractResult: ...


def apply_extraction(extractor: MemoryExtractor, writer: MemoryWriter,
                     req: ExtractRequest) -> WriterResult:
    """Extractor → writer.propose → validate → commit. Extractor never sees store.commit."""
    extracted = extractor.extract(req)
    if extracted.uncertain or not extracted.patches:
        return WriterResult(ok=True, errors=list(extracted.notes), items=[])
    for p in extracted.patches:
        if req.conversation_id and not p.conversation_id:
            p.conversation_id = req.conversation_id
        if p.source_turn < 0:
            p.source_turn = req.source_turn
    patches = writer.propose(extracted.patches)
    return writer.commit(patches, turn=req.source_turn)


def parse_patch_list(raw: str) -> tuple[list | None, str | None]:
    """Fail-closed JSON list parse. Does not interpret routing fields."""
    if not raw or not str(raw).strip():
        return None, "empty"
    text = str(raw).strip()
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end <= start:
            return None, "not_list"
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None, "not_json"
    if not isinstance(data, list):
        return None, "not_list"
    return data, None


class MockMemoryExtractor:
    """Deterministic scripts. Not empirical evidence. Never writes the store."""

    def __init__(self, scripts: dict[str, dict] | None = None):
        self.scripts = scripts or {}
        self.extract_calls = 0

    def extract(self, req: ExtractRequest) -> ExtractResult:
        self.extract_calls += 1
        # Longest key first so "navy, not black" is not stolen by a shorter "black".
        for key in sorted(self.scripts, key=len, reverse=True):
            spec = self.scripts[key]
            if key not in req.message:
                continue
            if spec.get("uncertain"):
                return ExtractResult(patches=[], notes=list(spec.get("notes") or ["uncertain"]),
                                    uncertain=True)
            patches: list[MemoryPatch] = []
            for raw in spec.get("patches") or []:
                body = dict(raw)
                body.setdefault("source_turn", req.source_turn)
                body.setdefault("proposer", "extractor")
                if req.conversation_id:
                    body.setdefault("conversation_id", req.conversation_id)
                if spec.get("omit_workstream"):
                    body.pop("workstream_id", None)
                    body.pop("referent_id", None)
                if spec.get("omit_referent"):
                    body.pop("referent_id", None)
                if spec.get("resolve_supersede_slot"):
                    slot = body.get("slot")
                    for item in req.asserted_items:
                        if (
                            item.status == "asserted"
                            and item.slot == slot
                            and item.kind == body.get("kind")
                            and item.workstream_id == body.get("workstream_id")
                        ):
                            body["supersedes_id"] = item.id
                            break
                patches.append(patch_from_dict(body))
            return ExtractResult(patches=patches, notes=list(spec.get("notes") or []))
        return ExtractResult(patches=[], notes=["no_script"], uncertain=True)


def _workstream_cards(tasks: list[Task]) -> str:
    lines = []
    for t in tasks:
        loops = "; ".join(t.anchor.open_loops) or "none"
        lines.append(f"[{t.id}] {t.title}: {t.anchor.goal}; loops: {loops}")
    return "\n".join(lines) or "(none)"


class LlmMemoryExtractor:
    """Fail-closed JSON extractor. Never chooses ACT/CLARIFY or mutates the store.

    Pytest must not call Vertex. Local exploratory runs may use Ollama.generate.
    """

    def __init__(self, llm):
        self.llm = llm

    def extract(self, req: ExtractRequest) -> ExtractResult:
        cards = _workstream_cards(req.open_workstreams)
        asserted = "; ".join(
            f"{i.id}:{i.kind}:{i.slot or '-'}:{i.text[:40]}"
            for i in req.asserted_items[:12]
        ) or "(none)"
        prompt = (
            "Return ONLY a JSON list of memory patches. No markdown.\n"
            "Each object keys: kind, text, workstream_id, referent_id, slot, action.\n"
            "kind is one of: fact, decision, constraint, entity, preference, event, correction.\n"
            "action is assert or retract. If uncertain, return [].\n"
            "Do not invent workstream ids. If the workstream or referent is ambiguous, omit it.\n"
            "Do not choose ACT, CLARIFY, SWITCH, or the current task. That is not your job.\n"
            f"KNOWN WORKSTREAMS:\n{cards}\n"
            f"ALREADY ASSERTED: {asserted}\n"
            f"MESSAGE: {req.message}\nTURN: {req.source_turn}\n"
        )
        try:
            raw = self.llm.generate(prompt)
        except Exception:
            return ExtractResult(patches=[], notes=["llm_extract_generate_failed"], uncertain=True)
        data, err = parse_patch_list(raw)
        if data is None:
            return ExtractResult(patches=[], notes=[f"llm_extract_{err}"], uncertain=True)
        patches = []
        notes = []
        known = {t.id for t in req.open_workstreams}
        for row in data:
            if not isinstance(row, dict):
                notes.append("skipped_non_object")
                continue
            row.pop("transition", None)
            row.pop("task_id", None)
            row.pop("is_new_task", None)
            kind = str(row.get("kind") or "")
            if kind not in ITEM_KINDS:
                notes.append(f"dropped_invalid_kind:{kind}")
                continue
            ws = row.get("workstream_id")
            if ws and ws not in known:
                notes.append(f"dropped_unknown_workstream:{ws}")
                continue
            if not ws and not row.get("allow_global"):
                notes.append("dropped_unanchored")
                continue
            ref = row.get("referent_id")
            if ref and ws:
                ok_ref = ref == ws or str(ref).startswith(f"{ws}.loop")
                if not ok_ref:
                    notes.append(f"dropped_invalid_referent:{ref}")
                    row["referent_id"] = None
            row.setdefault("source_turn", req.source_turn)
            row.setdefault("proposer", "extractor")
            if req.conversation_id:
                row.setdefault("conversation_id", req.conversation_id)
            patches.append(patch_from_dict(row))
        return ExtractResult(patches=patches, notes=notes, uncertain=not patches)
