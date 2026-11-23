"""Framework-agnostic bind door: industry shell shape + ContextFlow hop law.

Hosts (Cursor custom agents, Claude-style coordinators, LangGraph nodes) call
``bind_and_expose`` then:
- if ``interrupt``: pause for user (CLARIFY) — do not generate
- else: generate / tool-loop using ``l1_expose`` only; never re-bind

No LangGraph/Crew dependency. Binder stays authority.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from app.kernel.session import KernelResult, run_kernel_turn
from app.memory.extractor import MemoryExtractor
from app.memory.sessions import ConversationStore


def resolve_llm_mode() -> str:
    """Latency / provider mode for hosts and /health.

    Explicit ``CF_LLM_MODE=mock|vertex|gemini|ollama`` wins.
    Otherwise derived from existing flags (Vertex pacing only when vertex).
    """
    raw = (os.getenv("CF_LLM_MODE") or "").strip().lower()
    if raw in ("mock", "vertex", "gemini", "ollama"):
        return raw
    if os.getenv("CF_USE_VERTEX") == "1":
        return "vertex"
    if os.getenv("CF_USE_GEMINI") == "1":
        return "gemini"
    if os.getenv("CF_USE_OLLAMA") == "1":
        return "ollama"
    return "mock"


def apply_llm_mode(mode: str | None = None) -> str:
    """Normalize env for the chosen mode. Mock clears Vertex pace."""
    m = (mode or resolve_llm_mode()).strip().lower()
    if m == "mock":
        os.environ["CF_USE_VERTEX"] = "0"
        os.environ["CF_USE_GEMINI"] = "0"
        os.environ["CF_USE_OLLAMA"] = "0"
        os.environ["CF_LLM_EXTRACT"] = "0"
        os.environ["CF_TOPIC_LLM"] = "0"
        os.environ["CF_VERTEX_MIN_INTERVAL_S"] = "0"
        os.environ["CF_LLM_MODE"] = "mock"
    elif m == "vertex":
        os.environ["CF_USE_VERTEX"] = "1"
        os.environ["CF_USE_GEMINI"] = "0"
        os.environ.setdefault("CF_VERTEX_MIN_INTERVAL_S", "6.5")
        os.environ["CF_LLM_MODE"] = "vertex"
    elif m == "gemini":
        os.environ["CF_USE_GEMINI"] = "1"
        os.environ["CF_USE_VERTEX"] = "0"
        os.environ["CF_LLM_MODE"] = "gemini"
    elif m == "ollama":
        os.environ["CF_USE_OLLAMA"] = "1"
        os.environ["CF_USE_VERTEX"] = "0"
        os.environ["CF_USE_GEMINI"] = "0"
        os.environ["CF_LLM_MODE"] = "ollama"
    return resolve_llm_mode()


@dataclass
class BindExposeResult:
    """Stable host contract — same shape for HTTP and in-process."""

    conversation_id: str
    turn: int
    transition: str
    task_id: str | None
    l1_expose: str | None
    clarify_question: str | None
    discrimination: dict[str, Any] = field(default_factory=dict)
    interrupt: bool = False
    latency_ms: float = 0.0
    answer: str | None = None
    workstream_title: str | None = None
    selected_loop: str | None = None
    predicted_task_id: str | None = None
    predicted_referent_id: str | None = None
    context_mode: str | None = None
    included_loop_ids: list[str] | None = None
    total_context_tokens: int | None = None
    decision_tokens: int | None = None
    answer_tokens: int | None = None
    extract_ok: bool = True
    extract_committed: bool = False
    llm_mode: str = "mock"
    package_summary: dict[str, Any] | None = None
    timeline: list[dict[str, Any]] = field(default_factory=list)
    # Advanced: full kernel (tools / diagnostics). Hosts should prefer fields above.
    kernel: KernelResult | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("kernel", None)
        return d


def bind_and_expose(
    store: ConversationStore,
    extractor: MemoryExtractor,
    *,
    conversation_id: str,
    message: str,
    turn: int,
    history: list[dict] | None = None,
) -> BindExposeResult:
    """Bind one hop, assemble L1, return interrupt-or-expose for the host.

    Product laws:
    - Binder owns ``task_id``; host must not re-bind.
    - ``interrupt=True`` on CLARIFY → shell pauses; no generate from L1.
    - ``l1_expose`` is the only working context for generate on ACT/NEW/…
    """
    t0 = time.perf_counter()
    cid = (conversation_id or "").strip()
    if not cid:
        raise ValueError("conversation_id_required")
    eng = store.engine(cid)
    writer = store.writer(cid)
    kernel = run_kernel_turn(
        eng,
        writer,
        extractor,
        conversation_id=cid,
        message=message,
        turn=turn,
        history=history,
    )
    r = kernel.result
    tr = r.transition.value
    interrupt = tr == "CLARIFY"
    disc = (r.resolution_evidence or {}).get("discrimination") or {}
    if not isinstance(disc, dict):
        disc = {}

    l1 = kernel.expose_text or r.l1_expose
    answer = r.answer
    clarify = r.clarify_question
    if interrupt:
        # Interrupt contract: no answer payload, no L1 for generate.
        answer = None
        l1 = None
        if not clarify:
            clarify = "Which task did you mean?"

    pkg = r.package
    package_summary = None
    if pkg is not None and not interrupt:
        package_summary = {
            "task_id": pkg.task_id,
            "task_summary": pkg.task_summary,
            "context_mode": pkg.context_mode,
            "selected_referent_id": pkg.selected_referent_id,
            "total_context_tokens": pkg.total_context_tokens,
        }

    return BindExposeResult(
        conversation_id=cid,
        turn=turn,
        transition=tr,
        task_id=None if interrupt else r.task_id,
        l1_expose=l1,
        clarify_question=clarify if interrupt else None,
        discrimination=disc,
        interrupt=interrupt,
        latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        answer=answer,
        workstream_title=None if interrupt else kernel.workstream_title,
        selected_loop=None if interrupt else kernel.selected_loop,
        predicted_task_id=r.predicted_task_id,
        predicted_referent_id=None if interrupt else r.predicted_referent_id,
        context_mode=None if interrupt or not pkg else pkg.context_mode,
        included_loop_ids=None if interrupt or not pkg else list(pkg.included_loop_ids or []),
        total_context_tokens=None if interrupt or not pkg else pkg.total_context_tokens,
        decision_tokens=None if interrupt or not pkg else pkg.decision_tokens,
        answer_tokens=None if interrupt or not pkg else pkg.answer_tokens,
        extract_ok=kernel.extract.ok,
        extract_committed=bool(kernel.extract.items) or bool(
            kernel.extract.idempotent_retry
        ),
        llm_mode=resolve_llm_mode(),
        package_summary=package_summary,
        timeline=list(kernel.timeline),
        kernel=kernel,
    )
