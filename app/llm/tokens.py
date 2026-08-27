import math
from app.models.context import ContextPackage


def count(text: str) -> int:
    """Single source of truth. Locked heuristic: ceil(chars/4)."""
    if not text:
        return 0
    return math.ceil(len(text) / 4)


def _decision_text(pkg: ContextPackage) -> str:
    if pkg.decision_text:
        return pkg.decision_text
    parts = [pkg.task_summary] + list(pkg.open_loops)
    return " ".join(p for p in parts if p)


def _answer_text(pkg: ContextPackage) -> str:
    if pkg.answer_text:
        return pkg.answer_text
    parts = [pkg.task_summary] + list(pkg.open_loops) + list(pkg.active_decisions) \
        + list(pkg.active_constraints) + list(pkg.relevant_facts)
    return " ".join(p for p in parts if p)


def count_package(pkg: ContextPackage) -> tuple[int, int]:
    return count(_decision_text(pkg)), count(_answer_text(pkg))
