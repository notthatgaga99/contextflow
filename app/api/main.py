import logging
import os
import time
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import SETTINGS
from app.context.working_set import WorkingContextBuilder
from app.memory.extractor import LlmMemoryExtractor, MockMemoryExtractor
from app.memory.sessions import ConversationStore
from app.obs import correlation_id, decision_event, emit_decision
from app.turn_pipeline import run_turn

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("contextflow")
app = FastAPI(
    title="ContextFlow",
    description=(
        "Working-memory layer for context-switching assistants. "
        "DEMO/RESEARCH presentation shape — not a production readiness claim. "
        "Public unauthenticated deployments are a demo boundary unless invoker IAM is set."
    ),
)


DEMO_ONLY = os.getenv("CF_DEMO_ONLY", "1" if os.getenv("CF_SMOKE_FIXTURE") == "1" else "0") == "1"
MEMORY_BACKEND = os.getenv("CF_MEMORY_BACKEND", "memory").strip().lower() or "memory"
MEMORY_DURABLE = MEMORY_BACKEND == "firestore"


def _make_llm():
    # Vertex / Gemini: proposer (extract) + answer only — never ACT/CLARIFY authority.
    if os.getenv("CF_USE_GEMINI") == "1" or os.getenv("CF_USE_VERTEX") == "1":
        from app.llm.gemini import GeminiClient
        return GeminiClient()
    if os.getenv("CF_USE_OLLAMA") == "1":
        from app.llm.ollama import OllamaLLM
        return OllamaLLM()
    from app.llm.mock import MockLLM
    # Smoke-only: scripted proposals for ABCD fixture. Does not change gate/resolver.
    # Scripts live in app/ — runtime must not import eval gold/probes.
    if os.getenv("CF_SMOKE_FIXTURE") == "1":
        from app.memory.demo_smoke import LLM_SCRIPTS
        return MockLLM(LLM_SCRIPTS)
    return MockLLM()


store = ConversationStore(_make_llm(), SETTINGS, mode=os.getenv("CF_MODE", "split"))


def _make_extractor():
    # CF_LLM_EXTRACT=1 → LLM proposes MemoryPatches only; never ACT/CLARIFY.
    if os.getenv("CF_LLM_EXTRACT") == "1":
        return LlmMemoryExtractor(store.llm)
    if os.getenv("CF_SMOKE_FIXTURE") == "1":
        from app.memory.demo_smoke import EXTRACT_SCRIPTS
        return MockMemoryExtractor(EXTRACT_SCRIPTS)
    return MockMemoryExtractor()


extractor = _make_extractor()


class TurnIn(BaseModel):
    conversation_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=8000)
    turn: int = Field(..., ge=0, le=1_000_000)


class TurnOut(BaseModel):
    conversation_id: str
    transition: str
    task_id: str | None
    workstream_title: str | None = None
    selected_loop: str | None = None
    answer: str | None
    clarify_question: str | None
    decision_tokens: int | None
    answer_tokens: int | None
    predicted_task_id: str | None = None
    predicted_referent_id: str | None = None
    context_mode: str | None = None
    included_loop_ids: list[str] | None = None
    total_context_tokens: int | None = None
    correlation_id: str | None = None
    extract_ok: bool | None = None
    extract_committed: bool | None = None
    demo_only: bool | None = None
    memory_backend: str | None = None


def _title_and_loop(r) -> tuple[str | None, str | None]:
    if r.package is None:
        return None, None
    return r.package.task_summary, r.package.selected_open_loop


def _config_ok() -> dict:
    issues = []
    if (
        (os.getenv("CF_USE_GEMINI") == "1" or os.getenv("CF_USE_VERTEX") == "1")
        and not (os.getenv("GEMINI_API_KEY") or os.getenv("CF_USE_VERTEX") == "1")
    ):
        issues.append("gemini_enabled_without_credentials")
    if SETTINGS.TAU < 0 or SETTINGS.DELTA < 0:
        issues.append("invalid_gate_thresholds")
    if MEMORY_BACKEND not in ("memory", "firestore"):
        issues.append(f"unsupported_memory_backend:{MEMORY_BACKEND}")
    if MEMORY_BACKEND == "firestore" and not (
        os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    ):
        # ADC may still resolve project; warn as degraded, not hard-fail local inject.
        issues.append("firestore_project_unset")
    return {"ok": not issues or issues == ["firestore_project_unset"], "issues": issues}


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    cid = correlation_id(request.headers.get("x-request-id") or request.headers.get("x-correlation-id"))
    request.state.correlation_id = cid
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled correlation_id=%s", cid)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "correlation_id": cid},
        )
    response.headers["x-request-id"] = cid
    if DEMO_ONLY:
        response.headers["x-contextflow-demo-only"] = "1"
    return response


@app.get("/health")
@app.get("/healthz")
def health():
    cfg = _config_ok()
    vertex_on = os.getenv("CF_USE_VERTEX") == "1" or os.getenv("CF_USE_GEMINI") == "1"
    return {
        "status": "ok" if cfg["ok"] else "degraded",
        "service": "contextflow",
        "ready": cfg["ok"],
        "demo_only": DEMO_ONLY,
        "memory_backend": MEMORY_BACKEND,
        "memory_durable": MEMORY_DURABLE,
        "registry_durable": MEMORY_DURABLE,
        "multi_instance_safe": MEMORY_DURABLE,
        "config_ok": cfg["ok"],
        "config_issues": cfg["issues"],
        "llm": (
            "vertex" if os.getenv("CF_USE_VERTEX") == "1"
            else "gemini" if os.getenv("CF_USE_GEMINI") == "1"
            else "ollama" if os.getenv("CF_USE_OLLAMA") == "1"
            else "mock"
        ),
        "extract": "llm" if os.getenv("CF_LLM_EXTRACT") == "1" else "mock",
        "vertex_enabled": vertex_on,
        "boundary": (
            "Authenticated Cloud Run + Firestore is the durable POC path. "
            "Public unauthenticated access remains a demo-only boundary. "
            + (
                "Firestore-backed memory survives restart when CF_MEMORY_BACKEND=firestore."
                if MEMORY_DURABLE
                else "In-memory state is process-local."
            )
        ),
    }


@app.post("/turn", response_model=TurnOut)
def turn(t: TurnIn, request: Request):
    corr = getattr(request.state, "correlation_id", correlation_id())
    t0 = time.perf_counter()
    try:
        eng = store.engine(t.conversation_id)
        writer = store.writer(t.conversation_id)
        mem = store.memory_store(t.conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        pipe = run_turn(
            eng, writer, extractor,
            conversation_id=t.conversation_id.strip(),
            message=t.message, turn=t.turn,
        )
    except Exception as exc:
        log.exception("turn_failed correlation_id=%s", corr)
        raise HTTPException(
            status_code=500,
            detail={"error": "turn_failed", "correlation_id": corr},
        ) from exc
    r = pipe.turn
    title, loop = _title_and_loop(r)
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    package_status = "ok" if r.package is not None else (
        "clarify" if r.transition and r.transition.value == "CLARIFY" else "none"
    )
    answer_status = (
        "clarify" if r.transition and r.transition.value == "CLARIFY"
        else "ok" if r.answer else "none"
    )
    mem_stats = mem.stats() if hasattr(mem, "stats") else {}
    reg_stats = eng.reg.stats() if hasattr(eng.reg, "stats") else {}
    hist = mem.historical()
    emit_decision(decision_event(
        correlation_id=corr,
        conversation_id=t.conversation_id.strip(),
        turn=t.turn,
        transition=r.transition.value,
        task_id=r.task_id,
        referent_id=r.predicted_referent_id,
        extract_ok=pipe.extract.ok,
        extract_status="ok" if pipe.extract.ok else "rejected",
        extract_committed=bool(pipe.extract.items) or bool(pipe.extract.idempotent_retry),
        message_chars=len(t.message or ""),
        latency_ms=latency_ms,
        memory_asserted=len(mem.asserted()),
        memory_total=len(mem.all()),
        memory_backend=MEMORY_BACKEND,
        memory_reads=mem_stats.get("memory_reads"),
        memory_writes=mem_stats.get("memory_writes"),
        memory_current_count=len(mem.asserted()),
        memory_history_count=len([i for i in hist if i.status in ("superseded", "retracted")]),
        workstream_count=reg_stats.get("workstream_count") or len(eng.reg.open_tasks()),
        registry_reads=reg_stats.get("registry_reads"),
        registry_writes=reg_stats.get("registry_writes"),
        package_status=package_status,
        context_mode=r.package.context_mode if r.package else None,
        demo_only=DEMO_ONLY,
        answer_status=answer_status,
    ))
    return TurnOut(
        conversation_id=t.conversation_id,
        transition=r.transition.value, task_id=r.task_id, answer=r.answer,
        workstream_title=title,
        selected_loop=loop,
        clarify_question=r.clarify_question,
        decision_tokens=r.package.decision_tokens if r.package else None,
        answer_tokens=r.package.answer_tokens if r.package else None,
        predicted_task_id=r.predicted_task_id,
        predicted_referent_id=r.predicted_referent_id,
        context_mode=r.package.context_mode if r.package else None,
        included_loop_ids=r.package.included_loop_ids if r.package else None,
        total_context_tokens=r.package.total_context_tokens if r.package else None,
        correlation_id=corr,
        extract_ok=pipe.extract.ok,
        extract_committed=bool(pipe.extract.items) or bool(pipe.extract.idempotent_retry),
        demo_only=DEMO_ONLY,
        memory_backend=MEMORY_BACKEND,
    )


@app.get("/conversations/{conversation_id}/tasks")
def list_tasks(conversation_id: str):
    try:
        eng = store.engine(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    out = []
    for t in eng.reg.all():
        out.append({
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "goal": t.anchor.goal,
            "open_loops": list(t.anchor.open_loops),
            "last_active_turn": t.last_active_turn,
        })
    return {"conversation_id": conversation_id, "tasks": out, "demo_only": DEMO_ONLY}


@app.get("/conversations/{conversation_id}/memory")
def list_memory(conversation_id: str):
    """Working-memory inspector (not a raw dump of chat history)."""
    try:
        eng = store.engine(conversation_id)
        mem = store.memory_store(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    by_ws = []
    for t in eng.reg.all():
        asserted = mem.asserted(t.id)
        hist = mem.historical(t.id)
        by_ws.append({
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "goal": t.anchor.goal,
            "open_loops": list(t.anchor.open_loops),
            "last_active_turn": t.last_active_turn,
            "decisions": [i.text for i in asserted if i.kind == "decision"],
            "corrections": [i.text for i in asserted if i.kind == "correction"],
            "constraints": [i.text for i in asserted if i.kind == "constraint"],
            "facts": [i.text for i in asserted if i.kind in ("fact", "preference", "event")],
            "history": [
                {
                    "text": i.text, "slot": i.slot, "status": i.status,
                    "superseded_by": i.superseded_by, "source_turn": i.source_turn,
                }
                for i in hist if i.status == "superseded"
            ],
            "superseded": [
                {
                    "id": i.id, "text": i.text, "slot": i.slot,
                    "superseded_by": i.superseded_by, "source_turn": i.source_turn,
                    "provenance": i.provenance,
                }
                for i in hist if i.status == "superseded"
            ],
        })
    items = []
    for i in mem.all():
        items.append({
            "id": i.id,
            "kind": i.kind,
            "text": i.text,
            "status": i.status,
            "workstream_id": i.workstream_id,
            "referent_id": i.referent_id,
            "slot": i.slot,
            "source_turn": i.source_turn,
            "provenance": i.provenance,
            "superseded_by": i.superseded_by,
        })
    return {
        "conversation_id": conversation_id,
        "workstreams": by_ws,
        "items": items,
        # Product-facing inspector shape (not a debug dump).
        "views": {
            "CURRENT": [
                {
                    "workstream": w["title"],
                    "decisions": w["decisions"],
                    "constraints": w["constraints"],
                    "facts": w["facts"],
                }
                for w in by_ws if w["decisions"] or w["constraints"] or w["facts"]
            ],
            "HISTORY": [
                {
                    "workstream": w["title"],
                    "lines": [
                        f"{h['text']} → superseded"
                        + (f" by {h['superseded_by']}" if h.get("superseded_by") else "")
                        for h in w["history"]
                    ],
                }
                for w in by_ws if w["history"]
            ],
        },
        "demo_only": DEMO_ONLY,
        "memory_backend": MEMORY_BACKEND,
        "memory_durable": MEMORY_DURABLE,
    }


@app.get("/conversations/{conversation_id}/working-context")
def working_context(
    conversation_id: str,
    task_id: str = Query(..., min_length=1),
    referent_id: str | None = None,
):
    try:
        eng = store.engine(conversation_id)
        mem = store.memory_store(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    task = eng.reg.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    ref = referent_id or (f"{task_id}.loop1" if task.anchor.open_loops else task_id)
    proj = WorkingContextBuilder().project(task, ref, mem, eng.reg.open_tasks())
    return {
        "conversation_id": conversation_id,
        "task_id": task_id,
        "referent_id": ref,
        "included": {
            "decisions": list(proj.decisions),
            "constraints": list(proj.constraints),
            "facts": list(proj.facts),
            "entities": list(proj.entities),
        },
        "excluded_workstreams": list(proj.excluded_workstreams),
        "demo_only": DEMO_ONLY,
    }


@app.get("/task/{task_id}")
def get_task(task_id: str, conversation_id: str = Query(..., min_length=1)):
    try:
        eng = store.engine(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    t = eng.reg.get(task_id)
    return t.to_dict() if t else {"error": "not found"}
