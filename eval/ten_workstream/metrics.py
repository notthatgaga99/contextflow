"""Ten-workstream eval metrics. Scoring only — never fed into runtime prompts.

Frozen routing is not a consumer of these definitions.

Layers (do not collapse into one score):
  RESOLUTION — task_match, referent_match, candidate_miss
  POLICY     — policy_match, wrong_act, clarify_correct
  MEMORY     — persistence_correct, idempotency_correct, isolation_correct,
               supersession_correct
  WORKING CONTEXT — working_context_sufficient, critical_thin_context, contamination
  PACKAGE USABILITY — package evidence labels (token/string presence on context
               packs). Not answer-model quality.
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
    "NONE",
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


def clarify_correct(*, gold_policy: str | None, acted: bool) -> bool | None:
    """True only when gold expects CLARIFY and the system did not ACT."""
    if gold_policy != "CLARIFY":
        return None
    return not acted


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
    answer_usability: str | None = None,
) -> dict:
    tm = task_match(gold_task=gold_task, selected_task=selected_task, acted=acted)
    rm = referent_match(
        gold_ref=gold_ref, selected_ref=selected_ref, acted=acted, gold_task=gold_task,
    )
    pm = policy_match(gold_policy=gold_policy, acted=acted)
    cc = clarify_correct(gold_policy=gold_policy, acted=acted)
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
        answer_usability=answer_usability,
    )

    return {
        "task_match": tm,
        "referent_match": rm,
        "policy_match": pm,
        "clarify_correct": cc,
        "wrong_act": wa,
        "candidate_miss": cm,
        "working_context_sufficient": wcs,
        "critical_thin_context": ctc,
        "contamination": contam,
        "supersession_correct": supersession_ok,
        "persistence_correct": persist_ok,
        "package_absent_because_clarify": clarify_no_pkg,
        "answer_usability": answer_usability if answer_usability is not None else (
            "correct_continuation" if answer_usable else (
                None if answer_usable is None else "missing_state"
            )
        ),
        "package_usability": answer_usability if answer_usability is not None else (
            "correct_continuation" if answer_usable else (
                None if answer_usable is None else "missing_state"
            )
        ),
        "failure_layer": layer,
        "layers": {
            "RESOLUTION": {
                "task_match": tm,
                "referent_match": rm,
                "candidate_miss": cm,
            },
            "POLICY": {
                "policy_match": pm,
                "wrong_act": wa,
                "clarify_correct": cc,
            },
            "MEMORY": {
                "persistence_correct": persist_ok,
                "supersession_correct": supersession_ok,
            },
            "WORKING_CONTEXT": {
                "working_context_sufficient": wcs,
                "critical_thin_context": ctc,
                "contamination": contam,
            },
            "ANSWER_USABILITY": {
                "label": answer_usability if answer_usability is not None else (
                    "correct_continuation" if answer_usable else (
                        None if answer_usable is None else "missing_state"
                    )
                ),
                "note": "alias of PACKAGE_USABILITY — package evidence, not answer quality",
            },
            "PACKAGE_USABILITY": {
                "label": answer_usability if answer_usability is not None else (
                    "correct_continuation" if answer_usable else (
                        None if answer_usable is None else "missing_state"
                    )
                ),
                "note": "working-context / package evidence usability (not answer-model quality)",
            },
        },
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
    answer_usability: str | None = None,
) -> str:
    """Prefer the most specific layer. Never hide under OTHER when known."""
    if gold_policy == "CLARIFY":
        if not acted:
            return "NONE"  # clarify_correct — not a failure
        return "POLICY"

    if candidate_miss is True:
        return "CANDIDATE_MISS"

    if wrong_act:
        return "RESOLUTION"

    if gold_policy == "ACT" and not acted:
        return "POLICY"

    if critical_thin:
        if extract_status in ("rejected", "failed"):
            return "EXTRACTION"
        if not persist_ok:
            return "PERSISTENCE"
        return "RECONSTRUCTION"

    if contamination and acted:
        return "CONTAMINATION"

    if answer_usability in ("wrong-context", "contaminated", "stale-context", "missing_state"):
        if answer_usability == "contaminated":
            return "CONTAMINATION"
        if answer_usability == "missing_state":
            return "RECONSTRUCTION"
        return "ANSWER"

    if cf_sufficient is False and acted and task_match:
        return "RECONSTRUCTION"

    if policy_match is False:
        return "POLICY"

    if task_match is False and acted:
        return "RESOLUTION"

    # Success / no attributable failure — do not inflate OTHER.
    return "NONE"


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
    cc_ok, cc_n = _count("clarify_correct", lambda v: v is True)

    layers: dict[str, int] = {}
    for r in rows:
        layers[r["failure_layer"]] = layers.get(r["failure_layer"], 0) + 1

    failure_counts = {k: v for k, v in layers.items() if k != "NONE"}

    usability: dict[str, int] = {}
    for r in rows:
        lab = (
            r.get("package_usability")
            or r.get("answer_usability")
            or (r.get("CF") or {}).get("package_usability")
            or (r.get("CF") or {}).get("usability")
        )
        if lab:
            usability[lab] = usability.get(lab, 0) + 1

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
        "clarify_correct": f"{cc_ok}/{cc_n}" if cc_n else "n/a",
        "clarify_correct_ok": cc_ok,
        "clarify_correct_n": cc_n,
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
        "failure_counts_by_layer": failure_counts,
        "package_usability_counts": usability,
        "answer_usability_counts": usability,  # deprecated alias
        # Legacy alias — do not use as the primary quality score.
        "routing_correct_legacy": tm_ok + sum(
            1 for r in clar_rows if r.get("policy_match") is True
        ),
    }


def poc_machine_summary(
    *,
    rows: list[dict],
    number_of_workstreams: int,
    number_of_turns: int,
    trajectory_return_transitions: int,
    probe_return_count: int,
    idempotency_correct: bool,
    isolation_correct: bool,
) -> dict:
    """Machine-readable POC summary. Metrics remain separated by layer."""
    base = summarize(rows)
    base["idempotency_correct"] = idempotency_correct
    base["isolation_correct"] = isolation_correct
    failure_counts_by_layer = dict(base.get("failure_counts_by_layer") or {
        k: v for k, v in (base.get("failure_layers") or {}).items() if k != "NONE"
    })
    pkg_counts = base.get("package_usability_counts") or {}
    return {
        "fixture_label": (
            "CONTROLLED ADVERSARIAL ENGINEERING FIXTURE — NOT NATURAL HUMAN CHAT."
        ),
        "number_of_workstreams": number_of_workstreams,
        "number_of_turns": number_of_turns,
        "trajectory_return_transitions": trajectory_return_transitions,
        "probe_return_count": probe_return_count,
        "RESOLUTION": {
            "task_match": base["task_match"],
            "task_match_ok": base["task_match_ok"],
            "task_match_n": base["task_match_n"],
            "referent_match": base["referent_match"],
            "referent_match_ok": base["referent_match_ok"],
            "referent_match_n": base["referent_match_n"],
            "candidate_miss": base["candidate_miss"],
        },
        "POLICY": {
            "policy_match": base["policy_match"],
            "policy_match_ok": base["policy_match_ok"],
            "policy_match_n": base["policy_match_n"],
            "wrong_act": base["wrong_act"],
            "clarify_correct": base["clarify_correct"],
        },
        "MEMORY": {
            "persistence_correct": base["persistence_correct"],
            "idempotency_correct": idempotency_correct,
            "isolation_correct": isolation_correct,
            "supersession_correct": base["supersession_correct"],
        },
        "WORKING_CONTEXT": {
            "working_context_sufficient": base["working_context_sufficient"],
            "critical_thin_context": base["critical_thin_context"],
            "contamination": base["contamination"],
        },
        "PACKAGE_USABILITY": pkg_counts,
        "WORKING_CONTEXT_PACKAGE_USABILITY": pkg_counts,
        # Flat keys
        "task_match": base["task_match"],
        "referent_match": base["referent_match"],
        "policy_match": base["policy_match"],
        "wrong_act": base["wrong_act"],
        "candidate_miss": base["candidate_miss"],
        "working_context_sufficient": base["working_context_sufficient"],
        "critical_thin_context": base["critical_thin_context"],
        "contamination": base["contamination"],
        "supersession_correct": base["supersession_correct"],
        "persistence_correct": base["persistence_correct"],
        "idempotency_correct": idempotency_correct,
        "isolation_correct": isolation_correct,
        "failure_counts_by_layer": failure_counts_by_layer,
        "probes": base["probes"],
        "act_probes": base["act_probes"],
        "clarify_probes": base["clarify_probes"],
    }
