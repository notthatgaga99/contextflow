"""Agent tool harness — binder stays authority; tools use MemoryPort/Writer."""

from app.agent.tools import invoke_tool, list_tools
from app.agent.turn import run_agent_turn
from app.llm.mock import MockLLM
from app.memory.extractor import MockMemoryExtractor
from app.memory.sessions import ConversationStore
from app.models.memory import MemoryPatch
from tests.conftest import make_task


def test_list_tools_has_core_harness():
    names = {t["name"] for t in list_tools()}
    assert "list_threads" in names
    assert "assemble_short_term" in names
    assert "search_bound" in names
    assert "assert_procedure" in names


def test_invoke_list_threads_and_procedure():
    store = ConversationStore(MockLLM())
    eng = store.engine("c1")
    eng.reg.add(make_task("B", "outfit", "corporate outfit", ["color"], ["dress"]))
    w = store.writer("c1")
    w.commit([
        MemoryPatch(kind="fact", text="navy peplum", source_turn=1, workstream_id="B"),
    ], turn=1)

    listed = invoke_tool(store, "list_threads", {"conversation_id": "c1"})
    assert listed.ok
    assert listed.data["n_open"] >= 1

    proc = invoke_tool(store, "assert_procedure", {
        "conversation_id": "c1",
        "workstream_id": "B",
        "text": "try jacket then shoes",
        "turn": 2,
    })
    assert proc.ok, proc.error

    assembled = invoke_tool(store, "assemble_short_term", {
        "conversation_id": "c1",
        "workstream_id": "B",
        "query": "navy",
    })
    assert assembled.ok, assembled.error
    assert "SHORT_TERM" in assembled.data["expose_text"] or "PLANE" in assembled.data["expose_text"]
    assert any("jacket" in p for p in (assembled.data.get("short_term") or {}).get("procedures") or [])


def test_agent_turn_timeline():
    store = ConversationStore(MockLLM())
    out = run_agent_turn(
        store, MockMemoryExtractor(),
        conversation_id="c-agent",
        message="I need a navy outfit for a formal evening",
        turn=1,
        auto_tools=True,
    )
    assert out["timeline"]
    steps = [s["step"] for s in out["timeline"]]
    assert "bind" in steps
    assert "answer" in steps
    # ACT/NEW with task_id may run search_bound; CLARIFY would skip.
    if not out.get("interrupt") and out.get("task_id"):
        assert out.get("tools")
        assert out.get("tool_loop", {}).get("l1_unchanged") is True
    else:
        assert out.get("tools") == []
