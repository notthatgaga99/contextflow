from __future__ import annotations

from app.models.task import Task
from app.models.context import (
    ContextPackage,
    FULL_TASK,
    MERGED_COMPACT,
    REFERENT_COMPACT,
)
from app.llm import tokens
from app.router.referent import loop_index_from_id, loop_referent_id


def normalize_context_mode(mode: str | None) -> str:
    m = (mode or "split").strip().upper().replace("-", "_")
    if m in ("MERGED", "MERGED_COMPACT"):
        return MERGED_COMPACT
    if m in ("FULL", "FULL_TASK"):
        return FULL_TASK
    return REFERENT_COMPACT  # split / referent / default


class ContextCompiler:
    """Builds split or merged context packages with separate token accounting."""

    def build(
        self,
        task: Task,
        mode: str = "split",
        selected_referent_id: str | None = None,
        selected_open_loop: str | None = None,
        message: str | None = None,
        open_tasks: list[Task] | None = None,
        active_decisions: list[str] | None = None,
        active_constraints: list[str] | None = None,
        relevant_facts: list[str] | None = None,
        relevant_entities: list[str] | None = None,
        excluded_workstreams: list[str] | None = None,
        memory_item_ids: list[str] | None = None,
        recent_changes: list[str] | None = None,
    ) -> ContextPackage:
        requested = normalize_context_mode(mode)
        included_texts, included_ids, used_mode = self._select_loops(
            task, selected_referent_id, requested,
        )
        if selected_open_loop is None and included_texts:
            if used_mode == REFERENT_COMPACT and selected_referent_id:
                selected_open_loop = included_texts[0]
        a = task.anchor
        summary = a.goal or task.title
        pkg = ContextPackage(
            task_id=task.id,
            task_summary=summary,
            open_loops=list(included_texts),
            selected_referent_id=selected_referent_id,
            selected_open_loop=selected_open_loop,
            context_mode=used_mode,
            included_loop_ids=list(included_ids),
            active_decisions=list(active_decisions if active_decisions is not None else a.decisions),
            active_constraints=list(active_constraints if active_constraints is not None else a.constraints),
            relevant_facts=list(relevant_facts if relevant_facts is not None else a.entities),
            relevant_entities=list(relevant_entities or []),
            excluded_workstreams=list(excluded_workstreams or []),
            memory_item_ids=list(memory_item_ids or []),
            recent_changes=list(recent_changes or []),
            source_event_ids=list(memory_item_ids or []),
        )
        pkg.decision_text = self._decision_text(pkg, task, message, open_tasks)
        pkg.answer_text = self._answer_text(pkg)
        d, ans = tokens.count(pkg.decision_text), tokens.count(pkg.answer_text)
        if used_mode == MERGED_COMPACT:
            merged = self._merged_text(pkg)
            pkg.decision_text = ""
            pkg.answer_text = merged
            pkg.decision_tokens = 0
            pkg.answer_tokens = tokens.count(merged)
            pkg.total_context_tokens = pkg.answer_tokens
        else:
            pkg.decision_tokens = d
            pkg.answer_tokens = ans
            pkg.total_context_tokens = d + ans
        return pkg

    def _select_loops(
        self,
        task: Task,
        selected_referent_id: str | None,
        requested: str,
    ) -> tuple[list[str], list[str], str]:
        all_texts = list(task.anchor.open_loops)
        all_ids = [loop_referent_id(task.id, i) for i in range(len(all_texts))]
        if requested == FULL_TASK:
            return all_texts, all_ids, FULL_TASK
        if requested == MERGED_COMPACT:
            texts, ids, _compact = self._compact_or_fallback(
                task, selected_referent_id, all_texts, all_ids,
            )
            return texts, ids, MERGED_COMPACT
        return self._compact_or_fallback(task, selected_referent_id, all_texts, all_ids)

    def _compact_or_fallback(
        self,
        task: Task,
        selected_referent_id: str | None,
        all_texts: list[str],
        all_ids: list[str],
    ) -> tuple[list[str], list[str], str]:
        if not selected_referent_id:
            return all_texts, all_ids, FULL_TASK
        idx = loop_index_from_id(task.id, selected_referent_id)
        if idx is None or idx < 0 or idx >= len(all_texts):
            return all_texts, all_ids, FULL_TASK
        return [all_texts[idx]], [all_ids[idx]], REFERENT_COMPACT

    def _decision_text(
        self,
        pkg: ContextPackage,
        task: Task,
        message: str | None,
        open_tasks: list[Task] | None,
    ) -> str:
        if message or open_tasks:
            lines: list[str] = []
            if message:
                lines.append(f'MESSAGE: "{message}"')
            cards = open_tasks if open_tasks is not None else [task]
            lines.append("CARDS:")
            for t in cards:
                lines.append(
                    f"[{t.id}] goal: {t.anchor.goal or t.title}; "
                    f"mention_turn: {t.mention_turn}; last_active_turn: {t.last_active_turn}"
                )
            lines.append(f"SELECTED: task={pkg.task_id} referent={pkg.selected_referent_id}")
            return "\n".join(lines)
        parts = [pkg.task_summary] + list(pkg.open_loops)
        return " ".join(p for p in parts if p)

    def _answer_text(self, pkg: ContextPackage) -> str:
        parts = [pkg.task_summary]
        if pkg.selected_referent_id:
            parts.append(pkg.selected_referent_id)
        parts.extend(pkg.open_loops)
        parts.extend(pkg.active_decisions)
        parts.extend(pkg.active_constraints)
        parts.extend(pkg.relevant_facts)
        parts.extend(pkg.relevant_entities)
        return " ".join(p for p in parts if p)

    def _merged_text(self, pkg: ContextPackage) -> str:
        chunks = [pkg.decision_text, pkg.answer_text]
        return "\n".join(c for c in chunks if c)

    def render(self, pkg: ContextPackage, message: str | None = None) -> str:
        """Render answer prompt.

        When ``message`` is set (production generate path), include it so SWITCH
        to the wrong thread cannot answer that thread while dismissing the user.
        Without ``message``, preserve the legacy package-only shape for tests/eval.
        """
        if not (message and message.strip()):
            if pkg.context_mode == MERGED_COMPACT and pkg.answer_text:
                return pkg.answer_text
            lines = [f"TASK: {pkg.task_summary}"]
            if pkg.selected_referent_id:
                lines.append(f"REFERENT: {pkg.selected_referent_id}")
            if pkg.selected_open_loop:
                lines.append(f"SELECTED LOOP: {pkg.selected_open_loop}")
            if pkg.open_loops:
                lines.append("OPEN LOOPS: " + "; ".join(pkg.open_loops))
            if pkg.active_decisions:
                lines.append("DECISIONS: " + "; ".join(pkg.active_decisions))
            if pkg.active_constraints:
                lines.append("CONSTRAINTS: " + "; ".join(pkg.active_constraints))
            if pkg.relevant_facts:
                lines.append("FACTS: " + "; ".join(pkg.relevant_facts))
            if pkg.relevant_entities:
                lines.append("ENTITIES: " + "; ".join(pkg.relevant_entities))
            return "\n".join(lines)

        lines = [
            "Answer the USER message below.",
            "Use WORKING CONTEXT only as supporting memory for the selected thread.",
            "Never call the USER message unrelated or off-topic.",
            "If working context is about a different subject than the USER message, "
            "say briefly that the wrong thread may be selected, then still address "
            "the USER message (or ask which thread to use) — do not dump the wrong topic.",
            "",
            "WORKING CONTEXT:",
        ]
        if pkg.context_mode == MERGED_COMPACT and pkg.answer_text:
            lines.append(pkg.answer_text)
        else:
            lines.append(f"TASK: {pkg.task_summary}")
            if pkg.selected_referent_id:
                lines.append(f"REFERENT: {pkg.selected_referent_id}")
            if pkg.selected_open_loop:
                lines.append(f"SELECTED LOOP: {pkg.selected_open_loop}")
            if pkg.open_loops:
                lines.append("OPEN LOOPS: " + "; ".join(pkg.open_loops))
            if pkg.active_decisions:
                lines.append("DECISIONS: " + "; ".join(pkg.active_decisions))
            if pkg.active_constraints:
                lines.append("CONSTRAINTS: " + "; ".join(pkg.active_constraints))
            if pkg.relevant_facts:
                lines.append("FACTS: " + "; ".join(pkg.relevant_facts))
            if pkg.relevant_entities:
                lines.append("ENTITIES: " + "; ".join(pkg.relevant_entities))
        lines.append("")
        lines.append(f"USER: {message.strip()}")
        return "\n".join(lines)
