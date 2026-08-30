"""Score FULL / RECENT / CF working text. Eval only. No routing changes."""

from __future__ import annotations

from eval.consented_case.reconstruction import reconstruction_report


def condition_score(text: str | None, probe: dict) -> dict:
    report = reconstruction_report(text, probe)
    stale = list(probe.get("stale_excluded") or [])
    blob = (text or "").lower()
    stale_present = [s for s in stale if s and s.lower() in blob]
    # After supersession, "black" must not remain as live color. If the package
    # still lists it among decisions, that is stale. reconstruction_report does
    # not know slot status; callers pass rendered CF which should omit superseded.
    report["stale_present"] = stale_present
    report["sufficient_no_leak"] = (
        report["sufficient_for_continuation"] and not report["leaks"]
        and not stale_present
    )
    return report


def winner(full: dict, recent: dict, cf: dict) -> str:
    f, r, c = full["sufficient_no_leak"], recent["sufficient_no_leak"], cf["sufficient_no_leak"]
    if c and not f:
        return "CF_beats_FULL"
    if f and not c:
        return "FULL_beats_CF"
    if c and f:
        return "both_sufficient"
    if r and not c and not f:
        return "RECENT_only"
    return "none_sufficient"


def classify_failure(
    *,
    extract_status: str,
    persist_ok: bool,
    resolution: dict,
    recon: dict,
    gold_task: str | None,
    gold_policy: str | None,
) -> str:
    acted = resolution.get("transition") != "CLARIFY"
    task = resolution.get("task_id")
    if gold_policy == "CLARIFY" and not acted:
        return "clarify_ok"
    if acted and gold_task and task and task != gold_task:
        return "routing_wrong_ACT"
    if gold_task and acted and task == gold_task and recon.get("thin_context"):
        if extract_status in ("rejected", "uncertain", "missing", "wrong_workstream"):
            return "extraction"
        if not persist_ok:
            return "persistence"
        return "reconstruction"
    if gold_task and not acted and gold_policy == "ACT":
        return "routing_CLARIFY"
    if gold_task and acted and task == gold_task and not recon.get("sufficient_no_leak"):
        return "reconstruction"
    return "none"
