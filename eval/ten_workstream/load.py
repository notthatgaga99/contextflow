"""Load ten-workstream fixture. Control-plane cards vs extracted content.

Probe gold lives ONLY here (evaluator). Runtime never imports this module's
probe paths — app code must not read probes.json /
evaluator_isolated_probes.json.
"""

from __future__ import annotations

import json
from pathlib import Path

DIR = Path(__file__).resolve().parent
FIXTURE_PATH = DIR / "fixture.json"
PROBES_PATH = DIR / "probes.json"
# Runtime-blind evaluator probe set (NOT a statistical/generalization holdout).
EVALUATOR_ISOLATED_PROBES_PATH = DIR / "evaluator_isolated_probes.json"
# Deprecated alias name kept for older call sites / docs redirects.
HELD_OUT_PROBES_PATH = EVALUATOR_ISOLATED_PROBES_PATH

# Declarative fields every probe should expose to the evaluator.
PROBE_REQUIRED_KEYS = (
    "id",
    "turn",
    "gold_policy",
    "needed_state",
    "should_not_carry",
    "competing_similar",
    "category",
    "expected_open_workstream_count",
)


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def normalize_probe(raw: dict) -> dict:
    """Fill alias fields so scoring sees one declarative shape. Eval-only."""
    p = dict(raw)
    if p.get("expected_task") is None and p.get("gold_task_id") is not None:
        p["expected_task"] = p["gold_task_id"]
    if p.get("gold_task_id") is None and p.get("expected_task") is not None:
        p["gold_task_id"] = p["expected_task"]
    if p.get("expected_referent") is None and p.get("gold_referent_id") is not None:
        p["expected_referent"] = p["gold_referent_id"]
    if p.get("gold_referent_id") is None and p.get("expected_referent") is not None:
        p["gold_referent_id"] = p["expected_referent"]
    if p.get("expected_policy") is None and p.get("gold_policy") is not None:
        p["expected_policy"] = p["gold_policy"]
    if p.get("gold_policy") is None and p.get("expected_policy") is not None:
        p["gold_policy"] = p["expected_policy"]
    needed = list(p.get("needed_state") or p.get("required_working_state") or [])
    p["needed_state"] = needed
    p["required_working_state"] = list(p.get("required_working_state") or needed)
    forbid = list(p.get("forbidden_state") or p.get("should_not_carry") or [])
    p["should_not_carry"] = list(p.get("should_not_carry") or forbid)
    p["forbidden_state"] = forbid
    p.setdefault("competing_similar", [])
    p.setdefault("stale_excluded", [])
    p.setdefault("required_facts", [])
    p.setdefault("required_decisions", [])
    p.setdefault("required_constraints", [])
    p.setdefault("utterance_kind", "unspecified")
    p.setdefault("category", "unspecified")
    p["gap_category"] = p.get("gap_category") or p.get("expected_gap") or p.get("category")
    p.setdefault("expected_open_workstream_count", None)
    return p


def validate_probe(p: dict) -> list[str]:
    errs = []
    for k in PROBE_REQUIRED_KEYS:
        if k not in p:
            errs.append(f"{p.get('id', '?')}: missing {k}")
    if p.get("gold_policy") not in ("ACT", "CLARIFY", None):
        errs.append(f"{p.get('id')}: bad gold_policy")
    return errs


def _load_probe_file(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    probes = [normalize_probe(p) for p in data["probes"]]
    errs = [e for p in probes for e in validate_probe(p)]
    if errs:
        raise ValueError("probe metadata incomplete: " + "; ".join(errs[:8]))
    return probes


def load_probes(
    *,
    path: Path | str | None = None,
    evaluator_isolated: bool = False,
    held_out: bool = False,
) -> list[dict]:
    """Load scoring probes. Never call from app runtime.

    ``evaluator_isolated=True`` loads the runtime-blind evaluator probe set
    (derived from the controlled fixture). This is **not** an unseen
    statistical/generalization holdout — it exists so gold never enters
    runtime. ``held_out`` is a deprecated alias for ``evaluator_isolated``.
    """
    if path is not None:
        return _load_probe_file(Path(path))
    if held_out:
        evaluator_isolated = True
    if evaluator_isolated:
        return _load_probe_file(EVALUATOR_ISOLATED_PROBES_PATH)
    return _load_probe_file(PROBES_PATH)


def extract_scripts(fx: dict | None = None) -> dict:
    return dict((fx or load_fixture())["extract_scripts"])


def llm_scripts(fx: dict | None = None) -> dict:
    return dict((fx or load_fixture())["llm_scripts"])
