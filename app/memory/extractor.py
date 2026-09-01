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
    focus_workstream_id: str | None = None


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

# Pure recall / deixis — no new asserted memory (return-turn behavior).
_RECALL_ONLY_RE = re.compile(
    r"(?is)\b(?:"
    r"what did we decide|what was the|what were the|what is the|"
    r"remind me(?:\s+about|\s+of)?|tell me again|"
    r"back to .{0,48}\bwhat\b|"
    r"what\b.{0,32}\b(?:again|requirement|decision|color)\b"
    r")\b"
)

_COLOR_WORDS = frozenset({
    "black", "navy", "white", "red", "blue", "green", "gray", "grey",
    "brown", "beige", "pink", "purple", "gold", "silver", "maroon",
})

_CORRECTION_SIGNAL_RE = re.compile(
    r"(?i)\b(?:not|instead|changed my mind|rather than|switch to|correction)\b"
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


def message_looks_recall_only(message: str) -> bool:
    """True when the utterance asks to recall state, not assert new facts."""
    msg = (message or "").strip()
    if not msg:
        return False
    return bool(_RECALL_ONLY_RE.search(msg))


def _normalize_memory_text(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    t = re.sub(r"[.!?]+$", "", t)
    t = re.sub(r"^(pick a |choose a |get a |the )", "", t)
    return t


def _extract_color_token(text: str) -> str | None:
    for token in re.findall(r"[a-z]+", (text or "").lower()):
        if token in _COLOR_WORDS:
            return token
    return None


def _kind_peers(kind: str) -> set[str]:
    if kind in ("decision", "correction"):
        return {"decision", "correction"}
    return {kind}


def _patch_redundant_with_asserted(patch: MemoryPatch, asserted: list[MemoryItem]) -> bool:
    """Drop assert patches that restate equivalent current memory."""
    if patch.action != "assert" or patch.supersedes_id:
        return False
    ws = patch.workstream_id
    norm = _normalize_memory_text(patch.text)
    if not norm:
        return False
    patch_color = _extract_color_token(patch.text)
    for item in asserted:
        if item.status != "asserted" or item.workstream_id != ws:
            continue
        if patch.kind not in _kind_peers(item.kind):
            continue
        if patch.slot and item.slot and patch.slot != item.slot:
            continue
        if patch.slot and item.slot == patch.slot:
            if _normalize_memory_text(item.text) == norm:
                return True
            item_color = _extract_color_token(item.text)
            if patch_color and patch_color == item_color:
                return True
            continue
        if _normalize_memory_text(item.text) == norm:
            return True
        item_color = _extract_color_token(item.text)
        if patch_color and patch_color == item_color and patch.slot == item.slot == "color":
            return True
    return False


def filter_redundant_patches(
    patches: list[MemoryPatch],
    asserted: list[MemoryItem],
) -> tuple[list[MemoryPatch], list[str]]:
    kept: list[MemoryPatch] = []
    notes: list[str] = []
    for patch in patches:
        if _patch_redundant_with_asserted(patch, asserted):
            notes.append(f"dropped_redundant_assert:{patch.text[:32]}")
            continue
        kept.append(patch)
    return kept, notes


def _task_has_color_loop(task: Task | None) -> bool:
    if not task:
        return False
    return any("color" in loop.lower() for loop in task.anchor.open_loops)


def _infer_color_correction(
    row: dict,
    *,
    message: str,
    asserted: list[MemoryItem],
    tasks: list[Task],
) -> None:
    """Normalize outfit color corrections to slot=color with compact color text."""
    if row.get("slot"):
        return
    kind = row.get("kind")
    if kind not in ("decision", "correction"):
        return
    ws = row.get("workstream_id")
    if not ws:
        return
    msg = message.lower()
    color_new = _extract_color_token(str(row.get("text") or "")) or _extract_color_token(msg)
    has_correction = bool(_CORRECTION_SIGNAL_RE.search(msg))
    task = next((t for t in tasks if t.id == ws), None)
    color_asserted = [
        i for i in asserted
        if i.status == "asserted"
        and i.workstream_id == ws
        and i.kind in ("decision", "correction")
        and (_extract_color_token(i.text) or i.slot == "color")
    ]
    if not color_new and not has_correction:
        return
    if not (has_correction or color_asserted or _task_has_color_loop(task)):
        return
    row["slot"] = "color"
    if color_new:
        row["text"] = color_new
    if kind == "correction":
        row["kind"] = "decision"


_PICK_COLOR_DRESS_RE = re.compile(
    r"(?is)\b(?:pick|choose|get)\s+(?:(?:a|the)\s+)?(" + "|".join(_COLOR_WORDS) + r")\s+dress\b"
)


def try_parse_initial_color_decision(
    message: str,
    *,
    tasks: list[Task],
    asserted: list[MemoryItem],
    focus_workstream_id: str | None = None,
) -> dict | None:
    """Initial outfit color assertion without correction signal."""
    if _CORRECTION_SIGNAL_RE.search(message or ""):
        return None
    m = _PICK_COLOR_DRESS_RE.search(message or "")
    if not m:
        return None
    color = m.group(1).lower()
    ws = focus_workstream_id
    if not ws:
        for task in tasks:
            if any("color" in loop.lower() or "dress" in loop.lower() for loop in task.anchor.open_loops):
                ws = task.id
                break
    if not ws:
        return None
    body = {
        "kind": "decision",
        "text": color,
        "workstream_id": ws,
        "slot": "color",
        "action": "assert",
    }
    if any(_assertion_equivalent(body, item) for item in asserted):
        return None
    return body


# NEW-only focus path: unambiguous problem/goal intro after gate already created the card.
_NEW_FOCUS_PROBLEM_RE = re.compile(
    r"(?is)\b(?:"
    r"i\s+need\s+to|need\s+to\s+(?:figure|plan|fix|fix|debug|investigate)|"
    r"figure\s+out|keeps?\s+\w+ing|leaking|failing|"
    r"deadline|plan\s+a|separate\s+issue|also\s+i\s+need|"
    r"why\s+.{0,60}\b(?:keep|leak|fail)"
    r")\b"
)


def try_parse_new_focus_fact(
    message: str,
    *,
    focus_workstream_id: str | None,
    asserted: list[MemoryItem],
) -> dict | None:
    """Propose a workstream-anchored fact only when NEW pipeline set focus_workstream_id.

    Does not invent ids. Does not run without focus (non-NEW turns unchanged).
    Abstains on recall / underspecified / non-problem utterances.
    """
    if not focus_workstream_id:
        return None
    msg = (message or "").strip()
    if not msg or message_looks_recall_only(msg) or message_looks_underspecified(msg):
        return None
    if not _NEW_FOCUS_PROBLEM_RE.search(msg):
        return None
    text = re.sub(r"\s+", " ", msg)[:160]
    if len(text) < 12:
        return None
    body = {
        "kind": "fact",
        "text": text,
        "workstream_id": focus_workstream_id,
        "action": "assert",
    }
    if any(_assertion_equivalent(body, item) for item in asserted):
        return None
    return body


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


def _assertion_equivalent(body: dict, item: MemoryItem) -> bool:
    """True when a proposed patch would restate the same asserted value."""
    if item.status != "asserted":
        return False
    if body.get("workstream_id") != item.workstream_id:
        return False
    kind = body.get("kind")
    if kind not in _kind_peers(item.kind):
        return False
    slot = body.get("slot")
    if slot and item.slot and slot != item.slot:
        return False
    text = str(body.get("text") or "")
    if _normalize_memory_text(text) == _normalize_memory_text(item.text):
        return True
    new_color = _extract_color_token(text)
    old_color = _extract_color_token(item.text)
    if new_color and new_color == old_color and (slot == "color" or item.slot == "color"):
        return True
    return False


def _fill_supersedes(body: dict, asserted: list[MemoryItem]) -> None:
    """Attach supersedes_id for slotted decision/correction without inventing ids."""
    if body.get("supersedes_id"):
        return
    kind = body.get("kind")
    if kind not in ("decision", "correction"):
        return
    ws = body.get("workstream_id")
    slot = body.get("slot")
    if slot:
        for item in asserted:
            if (
                item.status == "asserted"
                and item.slot == slot
                and item.workstream_id == ws
                and item.kind in ("decision", "correction")
            ):
                if _assertion_equivalent(body, item):
                    return
                body["supersedes_id"] = item.id
                return
    if body.get("slot") == "color":
        new_color = _extract_color_token(str(body.get("text") or ""))
        if not new_color:
            return
        for item in asserted:
            if (
                item.status == "asserted"
                and item.workstream_id == ws
                and item.kind in ("decision", "correction")
            ):
                old_color = _extract_color_token(item.text)
                if old_color and old_color == new_color:
                    return
                if old_color and old_color != new_color:
                    body["supersedes_id"] = item.id
                    return


class LlmMemoryExtractor:
    """Fail-closed JSON extractor. Never chooses ACT/CLARIFY or mutates the store.

    Pytest must not call Vertex. Local exploratory runs may use Ollama.generate.
    """

    def __init__(self, llm):
        self.llm = llm

    def extract(self, req: ExtractRequest) -> ExtractResult:
        from app.memory.correction import try_parse_color_correction, try_parse_slot_correction

        if message_looks_underspecified(req.message):
            return ExtractResult(
                patches=[],
                notes=["underspecified_message_no_assert"],
                uncertain=True,
            )
        if message_looks_recall_only(req.message):
            return ExtractResult(
                patches=[],
                notes=["recall_only_no_new_assert"],
                uncertain=True,
            )

        notes: list[str] = []
        deterministic: list[MemoryPatch] = []
        for label, parser in (
            (
                "deterministic_correction",
                lambda: try_parse_color_correction(
                    req.message,
                    asserted=req.asserted_items,
                    tasks=req.open_workstreams,
                    focus_workstream_id=req.focus_workstream_id,
                ),
            ),
            (
                "deterministic_correction",
                lambda: try_parse_initial_color_decision(
                    req.message,
                    tasks=req.open_workstreams,
                    asserted=req.asserted_items,
                    focus_workstream_id=req.focus_workstream_id,
                ),
            ),
            (
                "deterministic_correction",
                lambda: try_parse_slot_correction(
                    req.message,
                    asserted=req.asserted_items,
                    tasks=req.open_workstreams,
                    focus_workstream_id=req.focus_workstream_id,
                ),
            ),
            (
                "deterministic_new_focus_fact",
                lambda: try_parse_new_focus_fact(
                    req.message,
                    focus_workstream_id=req.focus_workstream_id,
                    asserted=req.asserted_items,
                ),
            ),
        ):
            row = parser()
            if row is None:
                continue
            if req.focus_workstream_id:
                row["workstream_id"] = req.focus_workstream_id
            row.setdefault("source_turn", req.source_turn)
            row.setdefault("proposer", "extractor")
            if req.conversation_id:
                row.setdefault("conversation_id", req.conversation_id)
            _fill_supersedes(row, req.asserted_items)
            deterministic.append(patch_from_dict(row))
            notes.append(label)
            break

        if deterministic:
            patches, dedup_notes = filter_redundant_patches(deterministic, req.asserted_items)
            notes.extend(dedup_notes)
            return ExtractResult(patches=patches, notes=notes, uncertain=not patches)

        cards = _workstream_cards(req.open_workstreams)
        known_refs = _known_referent_ids(req.open_workstreams)
        asserted = "; ".join(
            f"{i.id}:{i.kind}:{i.slot or '-'}:{i.text[:40]}"
            for i in req.asserted_items[:12]
        ) or "(none)"
        focus = (
            f"FOCUS WORKSTREAM (prefer this id for new facts): {req.focus_workstream_id}\n"
            if req.focus_workstream_id
            else ""
        )
        prompt = (
            "Extract memory patches from the user message.\n"
            "Return JSON: {\"patches\": [...], \"abstain\": false}.\n"
            "Each patch keys: kind, text, workstream_id, referent_id, slot, action, "
            "supersedes_id, uncertain.\n"
            "kind: fact, decision, constraint, entity, preference, event, correction.\n"
            "action: assert or retract. If uncertain or recall-only, set abstain=true "
            "and patches=[].\n"
            "workstream_id MUST be one known id from KNOWN WORKSTREAMS.\n"
            "referent_id MUST be a known_referent or omitted.\n"
            "Color decisions: kind=decision, slot=color, text=color word only "
            "(black, navy, etc).\n"
            "Color corrections: slot=color, text=new color, supersedes_id=asserted item id.\n"
            "Do not invent ids. Do not copy ALREADY ASSERTED items.\n"
            "Do not route or choose ACT/CLARIFY/SWITCH.\n"
            f"{focus}"
            f"KNOWN WORKSTREAMS:\n{cards}\n"
            f"ALREADY ASSERTED: {asserted}\n"
            f"MESSAGE: {req.message}\nTURN: {req.source_turn}\n"
        )
        data = None
        try:
            from app.llm.gemini import GeminiClient
            if isinstance(self.llm, GeminiClient):
                from app.memory.extract_schema import MEMORY_EXTRACT_SCHEMA
                raw = self.llm.propose(prompt, MEMORY_EXTRACT_SCHEMA)
                if isinstance(raw, dict):
                    if raw.get("abstain"):
                        return ExtractResult(patches=[], notes=["structured_abstain"], uncertain=True)
                    data = raw.get("patches") or []
                elif isinstance(raw, list):
                    data = raw
            if data is None:
                raw_text = self.llm.generate(prompt)
                data, err = parse_patch_list(raw_text)
                if data is None:
                    return ExtractResult(patches=[], notes=[f"llm_extract_{err}"], uncertain=True)
        except Exception:
            return ExtractResult(patches=[], notes=["llm_extract_generate_failed"], uncertain=True)
        patches = []
        notes = []
        known = {t.id for t in req.open_workstreams}
        known_refs = _known_referent_ids(req.open_workstreams)
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
            if req.focus_workstream_id and not ws:
                ws = req.focus_workstream_id
                row["workstream_id"] = ws
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
            _infer_color_correction(
                row,
                message=req.message,
                asserted=req.asserted_items,
                tasks=req.open_workstreams,
            )
            if any(_assertion_equivalent(row, item) for item in req.asserted_items):
                notes.append("dropped_redundant_row")
                continue
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
        patches, dedup_notes = filter_redundant_patches(patches, req.asserted_items)
        notes.extend(dedup_notes)
        return ExtractResult(patches=patches, notes=notes, uncertain=not patches)
