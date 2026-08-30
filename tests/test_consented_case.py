"""Loader smoke tests. Fixture is not the Sep 7 case study."""

from eval.consented_case.contexts import diagnostic_size, full_history_prompt, recent_prompt
from eval.consented_case.load import registry_for_probe, turns_before, user_text


def test_turns_before_and_user_text():
    session = {
        "turns": [
            {"i": 0, "role": "user", "text": "a"},
            {"i": 1, "role": "assistant", "text": "b"},
            {"i": 2, "role": "user", "text": "back to a"},
        ]
    }
    assert user_text(session, 2) == "back to a"
    hist = turns_before(session, 2)
    assert [t["i"] for t in hist] == [0, 1]


def test_recent_is_smaller_than_full():
    hist = [{"i": i, "role": "user" if i % 2 == 0 else "assistant", "text": "x" * 40} for i in range(20)]
    full = full_history_prompt(hist, "now")
    rec = recent_prompt(hist, "now", 4)
    assert diagnostic_size(full) > diagnostic_size(rec)


def test_registry_skips_non_tasks():
    interp = {
        "workstreams": [
            {"id": "A", "title": "code", "unresolved_objective": "fix jwt",
             "open_loops": ["401 after refresh"], "retrieval_cues": ["jwt"],
             "is_task": True, "status": "paused"},
            {"id": "CHAT", "title": "smalltalk", "is_task": False},
        ]
    }
    probe = {
        "user_turn_index": 9,
        "active_task_id": "A",
        "last_selected_referent": "A.loop1",
        "clocks": {"A": {"last_active_turn": 3, "mention_turn": 3, "loop_mention_turns": [3]}},
    }
    reg = registry_for_probe(interp, probe)
    assert reg.get("A") is not None
    assert reg.get("CHAT") is None
    assert reg.active() is not None
    assert reg.active().id == "A"
    assert reg.last_selected_referent() == "A.loop1"
