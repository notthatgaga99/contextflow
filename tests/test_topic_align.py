"""Topic alignment rail — lexical mismatch override (not a gate retune)."""

from app.domain import Transition
from app.models.task import Task, TaskAnchor
from app.router.topic_align import align_plan, overlap_score


def _task(tid: str, title: str, cues: list[str], loops: list[str] | None = None) -> Task:
    return Task(
        id=tid,
        title=title,
        retrieval_cues=cues,
        anchor=TaskAnchor(goal=title, open_loops=loops or [title]),
    )


def test_overlap_fashion_vs_iot():
    dress = "hosting gig ivory peplum corset top business casual"
    iot = "setup service principals for IoT Hub customer endpoints"
    fashion = _task("T2", "ivory peplum hosting outfit", ["ivory", "peplum", "dress", "hosting"])
    tech = _task("T3", "IoT Hub service principals", ["iothub", "service", "principals", "endpoints"])
    assert overlap_score(dress, fashion.title + " " + " ".join(fashion.retrieval_cues)) > overlap_score(
        dress, tech.title + " " + " ".join(tech.retrieval_cues)
    )


def test_force_new_when_gate_sticks_to_tech():
    dress = (
        "i have a hosting gig for my corporate event and I'm supposed to be "
        "dressed in business casuals but like an AI bot so will a structured "
        "corset like peplum top work? its in ivory?"
    )
    tech = _task(
        "T3",
        "id like to learn about how i can setup service principals to each of my endpoints",
        ["service", "principals", "endpoints", "iothub", "customers"],
        loops=["service principals for IoT Hub endpoints"],
    )
    out = align_plan(
        message=dress,
        transition=Transition.SWITCH,
        task_id="T3",
        open_tasks=[tech],
        active_id="T1",
    )
    assert out is not None
    assert out.transition == Transition.NEW
    assert out.reason == "force_new_topic_mismatch"


def test_steal_better_fashion_thread():
    dress = "what about the ivory peplum top for the hosting gig?"
    tech = _task("T1", "IoT Hub service principals", ["iothub", "principals", "endpoints"])
    fashion = _task("T2", "ivory peplum hosting outfit", ["ivory", "peplum", "hosting", "outfit", "dress"])
    out = align_plan(
        message=dress,
        transition=Transition.SWITCH,
        task_id="T1",
        open_tasks=[tech, fashion],
        active_id="T1",
    )
    assert out is not None
    assert out.task_id == "T2"
    assert out.reason == "steal_better_workstream"


def test_keep_gate_when_selected_matches():
    msg = "also grant the service principal IoT Hub Data Sender role"
    tech = _task("T3", "IoT Hub service principals", ["iothub", "service", "principal", "endpoints", "role"])
    out = align_plan(
        message=msg,
        transition=Transition.CONTINUE,
        task_id="T3",
        open_tasks=[tech],
        active_id="T3",
    )
    assert out is None
