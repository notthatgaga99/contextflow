"""Kernel E2E probe for discrimination cases: bind + L1 + generate prompt.

Used by trust tests (Mock) and optional Vertex smoke. Sibling tokens listed
on a case as forbid_in_l1 must not appear in l1_expose or the generate prompt.
"""

from __future__ import annotations

from app.config import SETTINGS
from app.context.compiler import ContextCompiler
from app.engine import Engine
from app.kernel.session import run_kernel_turn
from app.llm.mock import MockLLM
from app.memory.extractor import MockMemoryExtractor
from app.memory.registry import InMemoryRegistry
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from app.models.task import Task
from eval.discrimination.run_cases import _task


class CaptureLLM(MockLLM):
    """Records the exact prompt generate() received."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_generate_prompt: str | None = None

    def generate(self, prompt: str) -> str:
        self.last_generate_prompt = prompt
        return super().generate(prompt)


def _script_for_gate(case: dict) -> dict:
    """Steer frozen propose toward the case's (often wrong) gate pick."""
    msg = case.get("message") or ""
    gate_tid = case.get("gate_task_id")
    is_new = str(case.get("gate_transition") or "").upper() == "NEW"
    scripts: dict[str, dict] = {}
    payload = {
        "task_id": None if is_new else gate_tid,
        "is_new_task": is_new,
        "confidence": 0.92,
        "referent": None,
        "rationale": "kernel-probe-gate",
    }
    for tok in msg.lower().replace("—", " ").replace("-", " ").split():
        clean = "".join(ch for ch in tok if ch.isalnum())
        if len(clean) >= 3:
            scripts[clean] = payload
    if not scripts:
        scripts[msg[:12] or "probe"] = payload
    return scripts


def run_kernel_probe(case: dict, *, llm=None) -> dict:
    """Seed open cards + memory, run one kernel turn, score bind and L1 hygiene."""
    cid = f"probe-{case.get('id') or 'x'}"
    reg = InMemoryRegistry()
    tasks: list[Task] = []
    for row in case.get("open") or []:
        t = _task(row)
        reg.add(t)
        tasks.append(t)
    active = case.get("active")
    if active and reg.get(active):
        reg.mark_active(active, 1)

    store = InMemoryMemoryStore(conversation_id=cid)
    writer = MemoryWriter(store, reg)
    patches: list[MemoryPatch] = []
    for row in case.get("open") or []:
        slots = [s for s in (row.get("slots") or []) if s]
        texts = list(row.get("memory") or [])
        for i, text in enumerate(texts):
            slot = slots[i] if i < len(slots) else (slots[0] if len(slots) == 1 else None)
            patches.append(MemoryPatch(
                kind="decision" if slot else "fact",
                text=text,
                source_turn=1,
                workstream_id=row["id"],
                conversation_id=cid,
                slot=slot,
            ))
        extra_slots = slots[len(texts):]
        for slot in extra_slots:
            patches.append(MemoryPatch(
                kind="fact",
                text=slot,
                source_turn=1,
                workstream_id=row["id"],
                conversation_id=cid,
                slot=slot,
            ))
        for ent in row.get("entities") or []:
            patches.append(MemoryPatch(
                kind="entity",
                text=ent,
                source_turn=1,
                workstream_id=row["id"],
                conversation_id=cid,
            ))
    if patches:
        writer.commit(patches, turn=1)

    capture = llm
    if capture is None:
        capture = CaptureLLM(_script_for_gate(case))
    eng = Engine(capture, reg, SETTINGS, memory_store=store)
    k = run_kernel_turn(
        eng, writer, MockMemoryExtractor(),
        conversation_id=cid,
        message=case["message"],
        turn=2,
    )
    r = k.result
    generate_prompt = getattr(capture, "last_generate_prompt", None)
    if generate_prompt is None and r.package is not None:
        generate_prompt = ContextCompiler().render(r.package, message=case["message"])

    gold_tid = case.get("gold_task_id")
    gold_tr = case.get("gold_transition") or []
    if isinstance(gold_tr, str):
        gold_tr = [gold_tr]
    gold_tr = [t for t in gold_tr if t not in (None, "null")]

    tr = r.transition.value
    tid = r.task_id
    if gold_tid is None and "CLARIFY" in gold_tr:
        bind_ok = tr == "CLARIFY"
    elif gold_tid is None and "NEW" in gold_tr:
        # Kernel creates a card; gold_task_id stays null. Bind is the verb NEW.
        bind_ok = tr == "NEW"
    else:
        bind_ok = tid == gold_tid and (not gold_tr or tr in gold_tr or tr == "CONTINUE")

    l1 = (k.expose_text or r.l1_expose or "").lower()
    prompt = (generate_prompt or "").lower()
    surfaces = l1 + "\n" + prompt
    forbid = [w.lower() for w in (case.get("forbid_in_l1") or [])]
    require = [w.lower() for w in (case.get("require_in_l1") or [])]
    # CLARIFY / NEW with no package: L1 checks only apply when we generated.
    l1_ok = True
    if tr not in ("CLARIFY",) and (l1 or prompt):
        l1_ok = all(w not in surfaces for w in forbid)
        if require and l1:
            l1_ok = l1_ok and all(w in l1 for w in require)

    return {
        "id": case.get("id"),
        "ok": bool(bind_ok and l1_ok),
        "bind_ok": bind_ok,
        "l1_ok": l1_ok,
        "transition": tr,
        "task_id": tid,
        "clarify_question": r.clarify_question,
        "l1_expose": k.expose_text or r.l1_expose,
        "generate_prompt": generate_prompt,
        "discrimination": (r.resolution_evidence or {}).get("discrimination"),
        "forbid_hits": [w for w in forbid if w in surfaces],
    }
