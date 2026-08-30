"""Build FULL / RECENT / ContextFlow answer strings. Same token heuristic as production."""

from __future__ import annotations

from app.context.compiler import ContextCompiler
from app.llm.tokens import count
from app.models.task import Task

RECENT_K = 8

CONTINUE_INSTRUCTION = (
    "Continue the conversation. Use only the supplied context. "
    "If the context is insufficient, say what is missing instead of guessing."
)


def format_history(turns: list[dict]) -> str:
    lines = []
    for t in turns:
        role = str(t.get("role", "")).upper()
        lines.append(f"{role}: {t.get('text', '')}")
    return "\n".join(lines)


def full_history_prompt(history: list[dict], message: str) -> str:
    return (
        f"{CONTINUE_INSTRUCTION}\n\n"
        f"FULL CONVERSATION HISTORY:\n{format_history(history)}\n\n"
        f"USER: {message}"
    )


def recent_prompt(history: list[dict], message: str, k: int = RECENT_K) -> str:
    window = history[-k:] if k > 0 else []
    return (
        f"{CONTINUE_INSTRUCTION}\n\n"
        f"RECENT WINDOW (last {k} messages):\n{format_history(window)}\n\n"
        f"USER: {message}"
    )


def contextflow_answer_prompt(rendered: str, message: str) -> str:
    return (
        f"{CONTINUE_INSTRUCTION}\n\n"
        f"WORKING CONTEXT:\n{rendered}\n\n"
        f"USER: {message}"
    )


def diagnostic_size(text: str) -> int:
    return count(text)


def compile_cf_package(task: Task, mode: str, referent_id: str | None, loop_text: str | None,
                       message: str, open_tasks: list[Task]):
    return ContextCompiler().build(
        task, mode,
        selected_referent_id=referent_id,
        selected_open_loop=loop_text,
        message=message,
        open_tasks=open_tasks,
    )
