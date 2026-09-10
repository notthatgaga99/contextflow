"""Lite-LLM topic discern unit tests (no Vertex)."""

from app.domain import Transition
from app.models.task import Task, TaskAnchor
from app.router.topic_discern import _parse, build_discern_prompt, discern_topic


def _task(tid: str, title: str, cues: list[str]) -> Task:
    return Task(
        id=tid,
        title=title,
        retrieval_cues=cues,
        anchor=TaskAnchor(goal=title, open_loops=[title]),
    )


class _FakeLLM:
    def __init__(self, raw: dict | None = None, boom: bool = False):
        self.raw = raw or {}
        self.boom = boom
        self.last_prompt = ""

    def propose(self, prompt: str, schema: dict) -> dict:
        self.last_prompt = prompt
        if self.boom:
            raise RuntimeError("nope")
        return self.raw

    def generate(self, prompt: str) -> str:
        return ""

    def embed(self, texts: list[str]):
        return []


def test_parse_continue_defaults_to_active():
    out = _parse(
        {"decision": "CONTINUE", "task_id": None, "confidence": 0.9, "rationale": "same yamls"},
        {"T1"},
        "T1",
    )
    assert out is not None
    assert out.transition == Transition.CONTINUE
    assert out.task_id == "T1"


def test_parse_switch_to_open_card():
    out = _parse(
        {"decision": "SWITCH", "task_id": "T2", "confidence": 0.8, "rationale": "dress"},
        {"T1", "T2"},
        "T1",
    )
    assert out is not None
    assert out.transition == Transition.RETURN
    assert out.task_id == "T2"


def test_parse_rejects_low_confidence():
    assert _parse(
        {"decision": "NEW", "task_id": None, "confidence": 0.2, "rationale": "guess"},
        {"T1"},
        "T1",
    ) is None


def test_discern_yaml_vague_continue():
    llm = _FakeLLM({
        "decision": "CONTINUE",
        "task_id": "T1",
        "confidence": 0.91,
        "rationale": "still about yamls",
    })
    tech = _task("T1", "helm values yaml", ["helm", "yaml", "values"])
    out = discern_topic(llm, "those yamls?", [tech], "T1")
    assert out is not None
    assert out.transition == Transition.CONTINUE
    assert "ACTIVE_ID: T1" in llm.last_prompt
    assert "those yamls" in llm.last_prompt


def test_discern_fashion_new():
    llm = _FakeLLM({
        "decision": "NEW",
        "task_id": None,
        "confidence": 0.88,
        "rationale": "outfit domain",
    })
    tech = _task("T1", "IoT Hub principals", ["iothub", "principals"])
    out = discern_topic(
        llm,
        "hosting gig ivory peplum corset top business casual",
        [tech],
        "T1",
    )
    assert out is not None
    assert out.transition == Transition.NEW


def test_discern_fail_closed_on_error():
    llm = _FakeLLM(boom=True)
    tech = _task("T1", "yaml", ["yaml"])
    assert discern_topic(llm, "yml", [tech], "T1") is None


def test_prompt_lists_open_cards():
    t1 = _task("T1", "yaml", ["yaml"])
    t2 = _task("T2", "ivory dress", ["ivory", "dress"])
    p = build_discern_prompt("back to ivory", [t1, t2], "T1")
    assert "id=T1" in p and "id=T2" in p
    assert "ACTIVE_ID: T1" in p


def test_veto_underspecified_new_sticks_active():
    from app.router.topic_discern import DiscernResult, refine_discern
    tech = _task("T3", "Meghalaya solo trip guide", ["meghalaya", "trip", "guide", "solo"])
    raw = DiscernResult(Transition.NEW, None, 0.9, "new", reason="llm")
    out = refine_discern(raw, "hikes or cafes?", [tech], "T3")
    assert out.transition == Transition.CONTINUE
    assert out.task_id == "T3"
    assert out.reason == "veto_underspecified_stick"


def test_veto_switch_to_peplum_when_asking_pipelines():
    from app.router.topic_discern import DiscernResult, refine_discern
    azure = _task(
        "T1",
        "azure pipeline bash exit 127 yaml",
        ["azure", "pipeline", "bash", "yaml", "agent", "tests"],
    )
    peplum = _task(
        "T2",
        "peplum hosting corporate event",
        ["peplum", "hosting", "corporate", "dress", "outfit"],
    )
    raw = DiscernResult(Transition.SWITCH, "T2", 0.85, "oops", reason="llm")
    msg = (
        "if i were to consider that i want to create 10 pipelines on same repo "
        "unit test module test end to end azure"
    )
    out = refine_discern(raw, msg, [azure, peplum], "T2")
    assert out.task_id == "T1"
    assert out.reason == "veto_better_lexical"


def test_veto_new_when_bash_matches_azure_card():
    from app.router.topic_discern import DiscernResult, refine_discern
    azure = _task(
        "T1",
        "azure pipeline bash exit 127 self hosted agent",
        ["azure", "pipeline", "bash", "exit", "agent"],
    )
    trip = _task("T3", "Meghalaya solo trip", ["meghalaya", "trip", "solo"])
    raw = DiscernResult(Transition.NEW, None, 0.9, "new", reason="llm")
    out = refine_discern(raw, "when would i see bash exit 4? is it pretty common", [azure, trip], "T3")
    assert out.task_id == "T1"
    assert out.reason == "veto_new_has_match"
