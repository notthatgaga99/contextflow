"""Phase 13 structured correction tests."""

from app.memory.correction import try_parse_color_correction
from app.memory.extractor import (
    ExtractRequest,
    LlmMemoryExtractor,
    MockMemoryExtractor,
    apply_extraction,
    message_looks_recall_only,
    try_parse_initial_color_decision,
)
from app.memory.registry import InMemoryRegistry
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from app.models.task import Task, TaskAnchor
from tests.test_memory_extractor import NAVY_MSG, abcd_black, _navy_script


def _outfit_reg():
    reg = InMemoryRegistry()
    reg.add(Task(
        id="B", title="corporate outfit", status="paused",
        retrieval_cues=["outfit", "dress"],
        anchor=TaskAnchor(goal="choose outfit", open_loops=["pick dress color"]),
    ))
    return reg


class _BoomLLM:
    def generate(self, prompt):
        raise AssertionError("should use deterministic path")

    def propose(self, prompt, schema):
        raise AssertionError("should use deterministic path")

    def embed(self, texts):
        return []


def test_explicit_old_to_new_correction():
    reg = _outfit_reg()
    store = InMemoryMemoryStore()
    writer = MemoryWriter(store, reg)
    writer.commit([
        MemoryPatch(kind="decision", text="black", source_turn=1, workstream_id="B",
                    slot="color", proposer="extractor"),
    ], turn=1)
    row = try_parse_color_correction(
        "Change the dress from black to navy.",
        asserted=store.asserted(),
        tasks=reg.open_tasks(),
    )
    assert row and row["text"] == "navy" and row["slot"] == "color"
    r = apply_extraction(
        LlmMemoryExtractor(_BoomLLM()),
        writer,
        ExtractRequest(message="Change the dress from black to navy.", source_turn=2,
                       open_workstreams=reg.open_tasks(), asserted_items=store.asserted()),
    )
    assert r.ok
    assert store.asserted("B")[0].text == "navy"
    assert any(i.status == "superseded" for i in store.all())


def test_instead_correction():
    reg, store, _writer = abcd_black()
    row = try_parse_color_correction(
        "Actually, make it navy instead.",
        asserted=store.asserted(),
        tasks=reg.open_tasks(),
    )
    assert row and row["text"] == "navy"


def test_initial_black_dress():
    reg = _outfit_reg()
    row = try_parse_initial_color_decision(
        "Pick the black dress.",
        tasks=reg.open_tasks(),
        asserted=[],
    )
    assert row and row["text"] == "black" and row["slot"] == "color"


def test_maybe_navy_abstains():
    assert try_parse_color_correction(
        "Maybe navy?",
        asserted=[],
        tasks=_outfit_reg().open_tasks(),
    ) is None


def test_recall_abstains():
    assert message_looks_recall_only("What did we decide about the color?")


def test_unrelated_favorite_color():
    assert try_parse_color_correction(
        "Blue is my favorite color.",
        asserted=[],
        tasks=_outfit_reg().open_tasks(),
    ) is None


def test_same_value_correction_rejected():
    reg, store, _writer = abcd_black()
    row = try_parse_color_correction(
        "Actually, make it black instead.",
        asserted=store.asserted(),
        tasks=reg.open_tasks(),
    )
    assert row is None


def test_navy_script_still_supersedes():
    reg, store, writer = abcd_black()
    ext = MockMemoryExtractor(_navy_script())
    r = apply_extraction(ext, writer, ExtractRequest(
        message=NAVY_MSG, source_turn=12, open_workstreams=reg.open_tasks(),
        asserted_items=store.asserted(),
    ))
    assert r.ok
    assert next(i for i in store.asserted("B") if i.slot == "color").text == "navy"
