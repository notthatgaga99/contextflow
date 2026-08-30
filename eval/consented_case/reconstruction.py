"""Score whether reconstructed context carries required working state. Eval only."""

from __future__ import annotations


def _missing(haystack: str, items: list[str]) -> list[str]:
    blob = (haystack or "").lower()
    return [x for x in items if x and x.lower() not in blob]


def reconstruction_report(rendered: str | None, probe: dict) -> dict:
    text = rendered or ""
    facts = list(probe.get("required_facts") or [])
    decisions = list(probe.get("required_decisions") or [])
    constraints = list(probe.get("required_constraints") or [])
    entities = list(probe.get("required_entities") or [])
    needed = list(probe.get("needed_state") or [])
    forbid = list(probe.get("should_not_carry") or probe.get("contamination_cues") or [])
    missing = {
        "facts": _missing(text, facts),
        "decisions": _missing(text, decisions),
        "constraints": _missing(text, constraints),
        "entities": _missing(text, entities),
        "needed_state": _missing(text, needed),
    }
    leaks = [x for x in forbid if x and x.lower() in text.lower()]
    thin = any(missing.values())
    return {
        "missing": missing,
        "leaks": leaks,
        "thin_context": thin,
        "sufficient_for_continuation": (not thin) and bool(text),
    }
