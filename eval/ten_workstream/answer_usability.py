"""Package / working-context evidence usability for FULL / RECENT / CONTEXTFLOW.

Eval-only. Builds the same continuation prompt shells for three context packs,
then scores each **context package** with token/string presence via
``condition_score`` / reconstruction (required vs forbidden cues).

This is **working-context / package usability** (package evidence usability).

It is NOT:
- an answer-quality benchmark
- a judged assessment of generated model replies
- a claim of answer-model accuracy

Labels describe whether the packed context evidence looks sufficient and
uncontaminated for continuation — not whether a model answered well.
"""

from __future__ import annotations

from eval.consented_case.contexts import (
    RECENT_K,
    contextflow_answer_prompt,
    full_history_prompt,
    recent_prompt,
)
from eval.memory_lifecycle.score import condition_score

# Package-evidence usability labels (not answer-model grades).
PACKAGE_USABILITY_LABELS = (
    "correct_continuation",
    "partial",
    "missing_state",
    "wrong-context",
    "stale-context",
    "contaminated",
)
# Back-compat alias for imports; same meaning as PACKAGE_USABILITY_LABELS.
USABILITY_LABELS = PACKAGE_USABILITY_LABELS

# Display names for context-package winners (winner() legacy codes unchanged).
CONTEXT_PACKAGE_WINNER_LABELS = {
    "CF_beats_FULL": "cf_package_beats_full_on_context_criteria",
    "FULL_beats_CF": "full_package_beats_cf_on_context_criteria",
    "both_sufficient": "both_packages_sufficient_on_context_criteria",
    "RECENT_only": "recent_package_only_on_context_criteria",
    "none_sufficient": "none_sufficient_on_context_criteria",
    "n/a_clarify": "n/a_clarify",
}


def context_package_winner_label(winner_code: str | None) -> str:
    """Map legacy winner codes to explicit package-criteria labels."""
    if not winner_code:
        return "none_sufficient_on_context_criteria"
    return CONTEXT_PACKAGE_WINNER_LABELS.get(
        winner_code, f"package_criteria:{winner_code}",
    )


def classify_usability(
    score: dict | None,
    *,
    acted: bool,
    gold_policy: str | None,
    needed_total: int | None = None,
) -> str | None:
    """Classify package evidence usability from a condition_score dict.

    Returns a package-usability label, or None when N/A (CLARIFY / no ACT).
    Uses only reconstruction/token-presence signals — does not judge replies.
    """
    if gold_policy == "CLARIFY" or not acted:
        return None
    if not score:
        return "missing_state"
    leaks = list(score.get("leaks") or [])
    stale = list(score.get("stale_present") or [])
    miss = score.get("missing") or {}
    needed_miss = list(miss.get("needed_state") or [])
    typed_miss = (
        list(miss.get("facts") or [])
        + list(miss.get("decisions") or [])
        + list(miss.get("constraints") or [])
        + list(miss.get("entities") or [])
    )
    any_miss = bool(needed_miss or typed_miss)
    n_needed = needed_total if needed_total is not None else None

    if leaks and any_miss:
        return "wrong-context"
    if leaks:
        return "contaminated"
    if stale:
        return "stale-context"
    if score.get("sufficient_no_leak"):
        return "correct_continuation"
    if n_needed and needed_miss and 0 < len(needed_miss) < n_needed:
        return "partial"
    if any_miss:
        return "missing_state"
    if score.get("thin_context"):
        return "partial"
    return "missing_state"


def build_condition_prompts(
    *,
    history: list[dict],
    message: str,
    cf_rendered: str,
) -> dict[str, str]:
    """Same prompt shell for FULL / RECENT / CONTEXTFLOW context packs.

    These strings are scoring substrates for package evidence, not graded answers.
    """
    return {
        "FULL": full_history_prompt(history, message),
        "RECENT": recent_prompt(history, message, RECENT_K),
        "CONTEXTFLOW": contextflow_answer_prompt(cf_rendered, message),
    }


def score_three_conditions(
    *,
    history: list[dict],
    message: str,
    cf_rendered: str,
    probe: dict,
    acted: bool,
) -> dict:
    """Score FULL / RECENT / CONTEXTFLOW packages for the same continuation.

    Package evidence only (token/string presence). Not answer-model quality.
    """
    gold_policy = probe.get("gold_policy")
    prompts = build_condition_prompts(
        history=history, message=message, cf_rendered=cf_rendered or "",
    )
    out = {}
    for name, text in prompts.items():
        if name == "CONTEXTFLOW" and (not acted or not cf_rendered):
            sc = {
                "missing": {"needed_state": list(probe.get("needed_state") or [])},
                "leaks": [],
                "thin_context": True,
                "sufficient_for_continuation": False,
                "stale_present": [],
                "sufficient_no_leak": False,
                "note": "no_package_clarify",
            }
        else:
            body = text
            if name == "CONTEXTFLOW":
                body = cf_rendered
            sc = condition_score(body, probe)
        needed_n = len(list(probe.get("needed_state") or []))
        label = classify_usability(
            sc, acted=acted, gold_policy=gold_policy, needed_total=needed_n,
        )
        out[name] = {
            **sc,
            "usability": label,  # package evidence usability
            "package_usability": label,
            "prompt_chars": len(text),
        }
    return out
