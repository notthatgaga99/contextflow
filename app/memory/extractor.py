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
from app.router.referent import loop_referent_id


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


# Underspecified deixis / hedges: prefer no asserted memory over invention.
# Structural patterns — not fixture-string overfitting.
_UNDERSPECIFIED_RE = re.compile(
    r"(?is)^\s*(?:no[,.]?\s+)?"
    r"("
    r"(?:maybe|perhaps|might be|not sure|i think\??)\b.{0,40}\?|"
    r"(?:the other one|that one|this one|same one)\b.*|"
    r"(?:fix that|do that|same again)\b.*"
    r")\s*$"
)


def message_looks_underspecified(message: str) -> bool:
    """True when the utterance lacks enough substance for safe asserted memory."""
    msg = (message or "").strip()
    if not msg:
        return True
    if _UNDERSPECIFIED_RE.match(msg):
        return True
    # Very short + only deixis/hedge tokens
    tokens = re.findall(r"[a-z0-9']+", msg.lower())
    if len(tokens) <= 5:
        deixis = {"that", "this", "it", "one", "other", "maybe", "fix", "the", "a", "an"}
        if tokens and all(t in deixis for t in tokens):
            return True
    return False


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
                    _fill_supersedes(body, req.asserted_items)
                patches.append(patch_from_dict(body))
            return ExtractResult(patches=patches, notes=list(spec.get("notes") or []))
        return ExtractResult(patches=[], notes=["no_script"], uncertain=True)


def _workstream_cards(tasks: list[Task]) -> str:
    lines = []
    for t in tasks:
        loops = "; ".join(t.anchor.open_loops) or "none"
        refs = ", ".join(
            loop_referent_id(t.id, i) for i in range(len(t.anchor.open_loops))
        ) or "(none)"
        lines.append(
            f"[{t.id}] {t.title}: {t.anchor.goal}; loops: {loops}; "
            f"known_referents: {refs}"
        )
    return "\n".join(lines) or "(none)"


def _known_referent_ids(tasks: list[Task]) -> set[str]:
    known: set[str] = set()
    for t in tasks:
        known.add(t.id)
        for i in range(len(t.anchor.open_loops)):
            known.add(loop_referent_id(t.id, i))
    return known


def _normalize_workstream_id(raw) -> str | None:
    """Strip accidental [brackets] / whitespace from model ids. Does not invent ids."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if len(s) >= 2 and s[0] == "[" and s[-1] == "]":
        s = s[1:-1].strip()
    return s or None


def _normalize_referent_id(raw, workstream_id: str | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if len(s) >= 2 and s[0] == "[" and s[-1] == "]":
        s = s[1:-1].strip()
    if s.startswith("[") and "]" in s:
        inner, rest = s[1:].split("]", 1)
        s = inner.strip() + rest
    if workstream_id and s.startswith(f"[{workstream_id}]"):
        s = workstream_id + s[len(workstream_id) + 2 :]
    return s or None


def _fill_supersedes(body: dict, asserted: list[MemoryItem]) -> None:
    """Attach supersedes_id for slotted decision/correction without inventing ids."""
    if body.get("supersedes_id") or not body.get("slot"):
        return
    kind = body.get("kind")
    if kind not in ("decision", "correction"):
        return
    ws = body.get("workstream_id")
    slot = body.get("slot")
    for item in asserted:
        if (
            item.status == "asserted"
            and item.slot == slot
            and item.workstream_id == ws
            and item.kind in ("decision", "correction")
        ):
            body["supersedes_id"] = item.id
            break


class LlmMemoryExtractor:
    """Fail-closed JSON extractor. Never chooses ACT/CLARIFY or mutates the store.

    Pytest must not call Vertex. Local exploratory runs may use Ollama.generate.
    """

    def __init__(self, llm):
        self.llm = llm

    def extract(self, req: ExtractRequest) -> ExtractResult:
        if message_looks_underspecified(req.message):
            return ExtractResult(
                patches=[],
                notes=["underspecified_message_no_assert"],
                uncertain=True,
            )
        cards = _workstream_cards(req.open_workstreams)
        known_refs = _known_referent_ids(req.open_workstreams)
        asserted = "; ".join(
            f"{i.id}:{i.kind}:{i.slot or '-'}:{i.text[:40]}"
            for i in req.asserted_items[:12]
        ) or "(none)"
        prompt = (
            "Return ONLY a JSON list of memory patches. No markdown.\n"
            "Each object keys: kind, text, workstream_id, referent_id, slot, action, "
            "supersedes_id.\n"
            "kind is one of: fact, decision, constraint, entity, preference, event, correction.\n"
            "action is assert or retract. If uncertain or underspecified, return [].\n"
            "workstream_id MUST be exactly one known id (A, B, C, …) — the token inside "
            "[brackets] in KNOWN WORKSTREAMS, without brackets.\n"
            "referent_id if present MUST be exactly one of known_referents for that "
            "workstream (e.g. E.loop1). Never invent E.loop2/E.loop3/etc.\n"
            "If unsure of the loop, omit referent_id rather than inventing one.\n"
            "For corrections that replace a slotted decision, set slot and optionally "
            "supersedes_id to the asserted item id being replaced.\n"
            "Do not invent workstream ids. If the workstream is ambiguous, return [].\n"
            "Do not choose ACT, CLARIFY, SWITCH, or the current task. That is not your job.\n"
            "Do not copy ALREADY ASSERTED items back as new patches.\n"
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
            ws = _normalize_workstream_id(row.get("workstream_id"))
            if ws:
                row["workstream_id"] = ws
            if ws and ws not in known:
                notes.append(f"dropped_unknown_workstream:{ws}")
                continue
            if not ws and not row.get("allow_global"):
                notes.append("dropped_unanchored")
                continue
            ref = _normalize_referent_id(row.get("referent_id"), ws)
            if ref:
                # Only keep referents that exist on open workstreams — never invent.
                if ref not in known_refs:
                    notes.append(f"omitted_unknown_referent:{ref}")
                    row["referent_id"] = None
                else:
                    row["referent_id"] = ref
            elif "referent_id" in row:
                row["referent_id"] = None
            _fill_supersedes(row, req.asserted_items)
            row.setdefault("source_turn", req.source_turn)
            row.setdefault("proposer", "extractor")
            if req.conversation_id:
                row.setdefault("conversation_id", req.conversation_id)
            # Model may mark a row uncertain — never promote to asserted memory.
            if bool(row.get("uncertain")):
                notes.append("dropped_uncertain_row")
                continue
            patches.append(patch_from_dict(row))
        return ExtractResult(patches=patches, notes=notes, uncertain=not patches)
