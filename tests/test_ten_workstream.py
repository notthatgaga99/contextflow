"""Ten-workstream stress tests. Mock only. Frozen routing."""

from app.config import SETTINGS
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.extractor import ExtractRequest, MockMemoryExtractor
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from app.turn_pipeline import run_turn
from eval.ten_workstream.load import extract_scripts, llm_scripts, load_fixture
from eval.ten_workstream.run import make_registry, replay


def test_fixture_has_ten_workstreams_and_fifty_turns():
    fx = load_fixture()
    assert len(fx["workstreams"]) == 10
    assert len(fx["turns"]) == 52
    assert {w["id"] for w in fx["workstreams"]} == set("ABCDEFGHIJ")


def test_ten_workstream_replay_persists_all_streams():
    payload, store, _ = replay()
    ws = {i.workstream_id for i in store.asserted()}
    assert set("ABCDEFGHIJ") <= ws
    assert payload["summary"]["workstreams_open"] == 10


def test_similar_technical_a_vs_c_not_mixed_in_working_set():
    payload, store, _ = replay()
    p = next(x for x in payload["probes"] if x["probe_id"] == "p02_return_a_amid_bcd_401")
    rendered = " ".join(
        i.text for i in store.asserted("A")
    )
    assert "401 after refresh" in rendered
    assert "gateway strips" not in " ".join(i.text for i in store.asserted("A"))
    if p["task_match"]:
        assert "gateway strips" not in (p.get("contamination_state") or [])


def test_supersession_navy_ttl_builder_trivia():
    _, store, _ = replay()
    color = next(i for i in store.asserted("E") if i.slot == "color")
    assert color.text == "navy"
    black = next(i for i in store.historical("E") if i.slot == "color" and i.text == "black")
    assert black.status == "superseded"
    ttl = next(i for i in store.asserted("A") if i.slot == "ttl")
    assert "5 minutes" in ttl.text
    builder = next(i for i in store.asserted("B") if i.slot == "builder")
    assert builder.text == "debian slim"
    alpine = next(i for i in store.historical("B") if i.slot == "builder" and i.text == "alpine")
    assert alpine.status == "superseded"
    ans = next(i for i in store.asserted("J") if i.slot == "answer")
    assert ans.text == "Celesteela"


def test_uncertain_does_not_enter_working_set():
    payload, store, fx = replay()
    p = next(x for x in payload["probes"] if x["probe_id"] == "p18_uncertain_navy_probe")
    assert p["extract_status"] in ("uncertain", "empty")
    maybe = [i for i in store.all() if "maybe" in (i.text or "").lower()]
    assert maybe == []


def test_duplicate_turn_does_not_duplicate_memory():
    fx = load_fixture()
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="dup")
    writer = MemoryWriter(store, reg)
    llm = MockLLM(llm_scripts(fx))
    eng = Engine(llm, reg, SETTINGS, memory_store=store)
    ext = MockMemoryExtractor(extract_scripts(fx))
    msg = "JWT still returns 401 after refresh on the auth service."
    run_turn(eng, writer, ext, conversation_id="dup", message=msg, turn=1)
    n = len(store.all())
    ver = store.namespace_version()
    run_turn(eng, writer, ext, conversation_id="dup", message=msg, turn=1)
    assert len(store.all()) == n
    assert store.namespace_version() == ver


def test_working_set_excludes_contamination_on_fashion_return():
    payload, _, _ = replay()
    p = next(x for x in payload["probes"] if x["probe_id"] == "p06_return_e_after_navy_correction")
    e = [t for t in payload["store_snapshot"] if t["workstream_id"] == "E" and t["status"] == "asserted"]
    texts = " ".join(i["text"] for i in e).lower()
    assert "navy" in texts
    assert "lisbon hotel" not in texts
    if p["selected_task"] == "E":
        leaks = " ".join(p.get("contamination_state") or []).lower()
        assert "401" not in leaks


def test_p09_clarify_gold_frozen_disagreement_documented():
    payload, _, _ = replay()
    p = next(x for x in payload["probes"] if x["probe_id"] == "p09_the_other_one")
    assert p["gold_policy"] == "CLARIFY"
    # Frozen resolver may ACT; POLICY if ACT-on-CLARIFY-gold, NONE if correctly CLARIFY
    assert p["failure_layer"] in ("NONE", "POLICY", "AMBIGUITY")
    assert p["wrong_act"] is False


def test_repeated_return_same_workstream():
    payload, _, _ = replay()
    e_returns = [p for p in payload["probes"] if p["intended_workstream"] == "E"]
    assert len(e_returns) >= 2


def test_conversation_isolation_two_stores():
    from app.models.memory import MemoryPatch
    fx = load_fixture()
    a = InMemoryMemoryStore(conversation_id="ten-a")
    b = InMemoryMemoryStore(conversation_id="ten-b")
    ra, rb = make_registry(fx), make_registry(fx)
    MemoryWriter(a, ra).commit([
        MemoryPatch(kind="fact", text="secret-a", source_turn=1, workstream_id="A",
                    conversation_id="ten-a"),
    ], turn=1)
    MemoryWriter(b, rb).commit([
        MemoryPatch(kind="decision", text="navy-b", source_turn=1, workstream_id="E",
                    conversation_id="ten-b", slot="color"),
    ], turn=1)
    assert all("navy" not in (i.text or "") for i in a.all())
    assert all("secret-a" not in (i.text or "") for i in b.all())


def test_extractor_does_not_choose_routing():
    fx = load_fixture()
    ext = MockMemoryExtractor(extract_scripts(fx))
    out = ext.extract(ExtractRequest(message="JWT still returns 401 after refresh on the auth service.", source_turn=1))
    assert not hasattr(out, "task_id")
    assert not hasattr(out, "transition")
