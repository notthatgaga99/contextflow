def test_mark_active_pauses_others(registry):
    registry.mark_active("A", 1)
    registry.mark_active("B", 2)
    assert registry.get("A").status == "paused"
    assert registry.get("B").status == "active"


def test_apply_update_versions_and_resolves(registry):
    v0 = registry.version("A")
    registry.apply_update("A", {"decisions": ["use RS256"],
                                "resolved_loops": ["401 on protected route unresolved"]})
    assert registry.version("A") == v0 + 1
    assert "use RS256" in registry.get("A").anchor.decisions
    assert "401 on protected route unresolved" not in registry.get("A").anchor.open_loops


def test_mention_independent_of_active(registry):
    registry.mark_active("A", 5)
    registry.record_mention("B", 6, "B.loop1")
    assert registry.active().id == "A"
    assert registry.get("A").last_active_turn == 5
    assert registry.get("A").mention_turn == 0
    assert registry.get("B").mention_turn == 6
    assert registry.get("B").status == "paused"


def test_open_tasks_filters_resolved(registry):
    registry.get("C").status = "resolved"
    ids = {t.id for t in registry.open_tasks()}
    assert ids == {"A", "B"}
