"""Ten-workstream eval metrics. Scoring only — never fed into runtime prompts.

Frozen routing is not a consumer of these definitions.
"""

from __future__ import annotations


FAILURE_LAYERS = (
    "CANDIDATE_MISS",
    "RESOLUTION",
    "POLICY",
    "EXTRACTION",
    "PERSISTENCE",
    "RECONSTRUCTION",
    "CONTAMINATION",
    "ANSWER",
    "AMBIGUITY",
    "OTHER",
)


def task_match(*, gold_task: str | None, selected_task: str | None, acted: bool) -> bool | None:
    """None when gold has no task (e.g. pure CLARIFY)."""
    if gold_task is None:
        return None
    if not acted:
        return False
    return selected_task == gold_task


def referent_match(
    *, gold_ref: str | None, selected_ref: str | None, acted: bool, gold_task: str | None,
) -> bool | None:
    if gold_ref is None:
        return None
    if not acted:
        return False
    return selected_ref == gold_ref


def policy_match(*, gold_policy: str | None, acted: bool) -> bool | None:
    if gold_policy is None:
        return None
    if gold_policy == "CLARIFY":
        return not acted
    if gold_policy == "ACT":
        return acted
    return None


def wrong_act(
    *, gold_task: str | None, selected_task: str | None, acted: bool, gold_policy: str | None,
) -> bool:
    """ACT to a non-gold task. CLARIFY gold + ACT is policy disagreement, not wrong-ACT."""
    if not acted:
        return False
    if gold_policy == "CLARIFY" or gold_task is None:
        return False
    return bool(selected_task and selected_task != gold_task)


def candidate_miss(*, gold_task: str | None, open_task_ids: set[str] | list[str]) -> bool | None:
    if gold_task is None:
        return None
    return gold_task not in set(open_task_ids)


def working_context_sufficient(
    *,
    acted: bool,
    gold_policy: str | None,
    cf_sufficient_no_leak: bool | None,
) -> bool | None:
    """None = not applicable (CLARIFY / no ACT package expected)."""
    if gold_policy == "CLARIFY" or not acted:
        return None
    if cf_sufficient_no_leak is None:
        return None
    return bool(cf_sufficient_no_leak)


def critical_thin_context(
    *,
    acted: bool,
    gold_task: str | None,
    selected_task: str | None,
    thin_context: bool,
    gold_policy: str | None,
) -> bool:
    """Correct workstream selected but package missing required state."""
    if gold_policy == "CLARIFY" or not acted or not gold_task:
        return False
    return selected_task == gold_task and bool(thin_context)


def package_absent_because_clarify(*, acted: bool, has_package: bool) -> bool:
    return (not acted) and (not has_package)


def score_probe_row(
    *,
    gold_task: str | None,
    gold_ref: str | None,
    gold_policy: str | None,
    selected_task: str | None,
    selected_ref: str | None,
    acted: bool,
    open_task_ids: list[str] | set[str],
    cf_sufficient_no_leak: bool | None,
    thin_context: bool,
    has_package: bool,
    contamination: list | None,
    supersession_ok: bool,
    persist_ok: bool,
    extract_status: str | None = None,
    answer_usable: bool | None = None,
) -> dict:
    tm = task_match(gold_task=gold_task, selected_task=selected_task, acted=acted)
    rm = referent_match(
        gold_ref=gold_ref, selected_ref=selected_ref, acted=acted, gold_task=gold_task,
    )
    pm = policy_match(gold_policy=gold_policy, acted=acted)
    wa = wrong_act(
        gold_task=gold_task, selected_task=selected_task, acted=acted, gold_policy=gold_policy,
    )
    cm = candidate_miss(gold_task=gold_task, open_task_ids=open_task_ids)
    wcs = working_context_sufficient(
        acted=acted, gold_policy=gold_policy, cf_sufficient_no_leak=cf_sufficient_no_leak,
    )
    ctc = critical_thin_context(
        acted=acted, gold_task=gold_task, selected_task=selected_task,
        thin_context=thin_context, gold_policy=gold_policy,
    )
    contam = bool(contamination) if acted else False
    clarify_no_pkg = package_absent_because_clarify(acted=acted, has_package=has_package)

    layer = attribute_failure(
        gold_policy=gold_policy,
        acted=acted,
        task_match=tm,
        wrong_act=wa,
        candidate_miss=cm,
        critical_thin=ctc,
        contamination=contam,
        persist_ok=persist_ok,
        extract_status=extract_status,
        cf_sufficient=wcs,
        policy_match=pm,
    )

    return {
        "task_match": tm,
        "referent_match": rm,
        "policy_match": pm,
        "wrong_act": wa,
        "candidate_miss": cm,
        "working_context_sufficient": wcs,
        "critical_thin_context": ctc,
        "contamination": contam,
        "supersession_correct": supersession_ok,
        "persistence_correct": persist_ok,
        "package_absent_because_clarify": clarify_no_pkg,
        "answer_usability": answer_usable,
        "failure_layer": layer,
    }


def attribute_failure(
    *,
    gold_policy: str | None,
    acted: bool,
    task_match: bool | None,
    wrong_act: bool,
    candidate_miss: bool | None,
    critical_thin: bool,
    contamination: bool,
    persist_ok: bool,
    extract_status: str | None,
    cf_sufficient: bool | None,
    policy_match: bool | None,
) -> str:
    """Prefer OTHER when layers cannot be distinguished honestly."""
    if gold_policy == "CLARIFY":
        if not acted:
            return "AMBIGUITY"
        return "POLICY"

    if candidate_miss is True:
        return "CANDIDATE_MISS"

    if wrong_act:
        return "RESOLUTION"

    if gold_policy == "ACT" and not acted:
        return "POLICY"

    if critical_thin:
        if extract_status in ("rejected", "uncertain", "empty", "failed"):
            # empty extract on a return turn is often not the cause of thin
            # historical memory; only blame EXTRACTION when something failed loudly.
            if extract_status in ("rejected", "failed"):
                return "EXTRACTION"
        if not persist_ok:
            return "PERSISTENCE"
        return "RECONSTRUCTION"

    if contamination and acted:
        return "CONTAMINATION"

    if cf_sufficient is False and acted and task_match:
        return "RECONSTRUCTION"

    if policy_match is False:
        return "POLICY"

    return "OTHER"


def summarize(rows: list[dict]) -> dict:
    def _count(key, pred):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return sum(1 for v in vals if pred(v)), len(vals)

    act_rows = [r for r in rows if r.get("gold_policy") == "ACT"]
    clar_rows = [r for r in rows if r.get("gold_policy") == "CLARIFY"]

    tm_ok, tm_n = _count("task_match", lambda v: v is True)
    rm_ok, rm_n = _count("referent_match", lambda v: v is True)
    pm_ok, pm_n = _count("policy_match", lambda v: v is True)
    wcs_ok, wcs_n = _count("working_context_sufficient", lambda v: v is True)

    layers: dict[str, int] = {}
    for r in rows:
        layers[r["failure_layer"]] = layers.get(r["failure_layer"], 0) + 1

    return {
        "probes": len(rows),
        "act_probes": len(act_rows),
        "clarify_probes": len(clar_rows),
        "task_match": f"{tm_ok}/{tm_n}" if tm_n else "n/a",
        "task_match_ok": tm_ok,
        "task_match_n": tm_n,
        "referent_match": f"{rm_ok}/{rm_n}" if rm_n else "n/a",
        "referent_match_ok": rm_ok,
        "referent_match_n": rm_n,
        "policy_match": f"{pm_ok}/{pm_n}" if pm_n else "n/a",
        "policy_match_ok": pm_ok,
        "policy_match_n": pm_n,
        "wrong_act": sum(1 for r in rows if r.get("wrong_act")),
        "candidate_miss": sum(1 for r in rows if r.get("candidate_miss") is True),
        "working_context_sufficient": f"{wcs_ok}/{wcs_n}" if wcs_n else "n/a",
        "working_context_sufficient_ok": wcs_ok,
        "working_context_sufficient_n": wcs_n,
        "critical_thin_context": sum(1 for r in rows if r.get("critical_thin_context")),
        "contamination": sum(1 for r in rows if r.get("contamination")),
        "supersession_correct": sum(1 for r in rows if r.get("supersession_correct")),
        "persistence_correct": sum(1 for r in rows if r.get("persistence_correct")),
        "idempotency_correct": None,  # filled by harness smoke
        "isolation_correct": None,
        "failure_layers": layers,
        # Legacy alias — do not use as the primary quality score.
        "routing_correct_legacy": tm_ok + sum(
            1 for r in clar_rows if r.get("policy_match") is True
        ),
    }
