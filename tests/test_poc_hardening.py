"""POC hardening invariants — fail closed, no eval gold in runtime."""

from __future__ import annotations

import ast
from pathlib import Path

from app.context.working_set import WorkingContextBuilder
from app.memory.extractor import ExtractRequest, LlmMemoryExtractor
from app.memory.registry import InMemoryRegistry
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryItem, MemoryPatch
from tests.conftest import make_task


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def test_sibling_loop_state_excluded_from_working_set():
    reg = InMemoryRegistry()
    a = make_task("A", "auth", "fix JWT", ["401 after refresh", "TTL tune"], ["jwt"])
    reg.add(a)
    store = InMemoryMemoryStore(conversation_id="sib")
    w = MemoryWriter(store, reg)
    w.commit([
        MemoryPatch(kind="fact", text="401 after refresh", source_turn=1,
                    workstream_id="A", referent_id="A.loop1", conversation_id="sib"),
        MemoryPatch(kind="fact", text="TTL was 60 then 15", source_turn=2,
                    workstream_id="A", referent_id="A.loop2", conversation_id="sib"),
    ], turn=2)
    proj = WorkingContextBuilder().project(a, "A.loop1", store, reg.open_tasks())
    blob = " ".join(proj.facts).lower()
    assert "401" in blob
    assert "ttl" not in blob


def test_uncertain_asserted_item_excluded_from_working_set():
    """Even if an uncertain item were present, WC must not project it."""
    reg = InMemoryRegistry()
    b = make_task("B", "outfit", "outfit", ["color"], ["dress"])
    reg.add(b)
    store = InMemoryMemoryStore(conversation_id="unc-wc")
    store._items["ghost"] = MemoryItem(  # noqa: SLF001 — intentional edge inject
        id="ghost", kind="decision", text="maybe navy", source_turn=1,
        workstream_id="B", referent_id="B.loop1", status="asserted",
        conversation_id="unc-wc", uncertain=True, version=1,
    )
    proj = WorkingContextBuilder().project(b, "B.loop1", store)
    assert proj.decisions == []


def test_extractor_drops_uncertain_row_before_writer():
    class _LLM:
        def generate(self, prompt: str) -> str:
            return (
                '[{"kind":"decision","text":"navy","workstream_id":"B",'
                '"referent_id":"B.loop1","uncertain":true}]'
            )

    reg = InMemoryRegistry()
    reg.add(make_task("B", "outfit", "outfit", ["color"], ["dress"]))
    ext = LlmMemoryExtractor(_LLM())
    out = ext.extract(ExtractRequest(
        message="Use navy for the corporate evening dress.", source_turn=1,
        conversation_id="u", open_workstreams=reg.open_tasks(),
    ))
    assert out.patches == []
    assert any("uncertain" in n for n in out.notes)


def test_thin_context_is_detectable_not_invented():
    reg = InMemoryRegistry()
    b = make_task("B", "outfit", "outfit", ["color"], ["dress"])
    reg.add(b)
    store = InMemoryMemoryStore()
    MemoryWriter(store, reg).commit([
        MemoryPatch(kind="decision", text="navy", source_turn=1, workstream_id="B",
                    slot="color"),
    ], turn=1)
    builder = WorkingContextBuilder()
    proj = builder.project(b, "B.loop1", store)
    assert not builder.insufficient(proj, ["navy"])
    assert builder.insufficient(proj, ["navy", "formal", "evening"])
    assert "formal" in builder.missing_required(proj, ["navy", "formal", "evening"])


def test_runtime_app_does_not_import_eval_gold():
    forbidden = ("eval.ten_workstream.probes", "probes.json", "gold_task_id",
                 "eval.memory_lifecycle.fixture")
    offenders = []
    for path in APP_ROOT.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        if "demo_smoke" in path.name:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
                if mod.startswith("eval.") or mod == "eval":
                    offenders.append(f"{path.relative_to(APP_ROOT.parent)}:{mod}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "eval" or alias.name.startswith("eval."):
                        offenders.append(
                            f"{path.relative_to(APP_ROOT.parent)}:{alias.name}"
                        )
        for token in forbidden:
            if token in src and "demo_smoke" not in path.name:
                # Comment-only mentions of probes are OK; import paths are not.
                if f"import {token}" in src or f"from {token}" in src:
                    offenders.append(f"{path.relative_to(APP_ROOT.parent)}:{token}")
    assert offenders == [], offenders


def test_demo_smoke_scripts_are_app_local():
    from app.memory.demo_smoke import EXTRACT_SCRIPTS, LLM_SCRIPTS
    assert "navy, not black" in EXTRACT_SCRIPTS
    assert "JWT still returns 401" in LLM_SCRIPTS
