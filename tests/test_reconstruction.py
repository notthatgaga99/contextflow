from eval.consented_case.reconstruction import reconstruction_report


def test_thin_context_when_decision_omitted():
    probe = {
        "required_decisions": ["rejected black because of venue lighting"],
        "required_facts": [],
        "required_constraints": [],
        "required_entities": [],
        "needed_state": [],
        "should_not_carry": ["Lisbon flight"],
    }
    rendered = "TASK: corporate event outfit\nSELECTED LOOP: pick a dress"
    r = reconstruction_report(rendered, probe)
    assert r["thin_context"] is True
    assert r["missing"]["decisions"]
    assert r["sufficient_for_continuation"] is False


def test_leak_detected():
    probe = {"should_not_carry": ["Lisbon"], "needed_state": ["navy"]}
    r = reconstruction_report("TASK: outfit\nFACTS: navy; Lisbon hotel", probe)
    assert "Lisbon" in r["leaks"]
