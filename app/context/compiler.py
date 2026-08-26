from app.models.task import Task
from app.models.context import ContextPackage
from app.llm import tokens


class ContextCompiler:
    """Builds split or merged context packages with separate token accounting."""

    def build(self, task: Task, mode: str = "split") -> ContextPackage:
        a = task.anchor
        summary = a.goal or task.title
        pkg = ContextPackage(
            task_id=task.id,
            task_summary=summary,
            open_loops=list(a.open_loops),
            active_decisions=list(a.decisions),
            active_constraints=list(a.constraints),
            relevant_facts=list(a.entities),
            source_event_ids=[],
        )
        d, ans = tokens.count_package(pkg)
        if mode == "merged":
            # one representation serves both roles; count once (as answer), decision=0
            pkg.decision_tokens = 0
            pkg.answer_tokens = ans
        else:
            pkg.decision_tokens = d
            pkg.answer_tokens = ans
        return pkg

    def render(self, pkg: ContextPackage) -> str:
        lines = [f"TASK: {pkg.task_summary}"]
        if pkg.open_loops:
            lines.append("OPEN LOOPS: " + "; ".join(pkg.open_loops))
        if pkg.active_decisions:
            lines.append("DECISIONS: " + "; ".join(pkg.active_decisions))
        if pkg.active_constraints:
            lines.append("CONSTRAINTS: " + "; ".join(pkg.active_constraints))
        if pkg.relevant_facts:
            lines.append("FACTS: " + "; ".join(pkg.relevant_facts))
        return "\n".join(lines)
