import logging
import os
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import SETTINGS
from app.memory.extractor import LlmMemoryExtractor, MockMemoryExtractor
from app.memory.sessions import ConversationStore
from app.obs import correlation_id, decision_event, emit_decision
from app.turn_pipeline import run_turn

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="ContextFlow")


def _make_llm():
    if os.getenv("CF_USE_GEMINI") == "1":
        from app.llm.gemini import GeminiClient
        return GeminiClient()
    if os.getenv("CF_USE_OLLAMA") == "1":
        from app.llm.ollama import OllamaLLM
        return OllamaLLM()
    from app.llm.mock import MockLLM
    # Smoke-only: scripted proposals for ABCD fixture. Does not change gate/resolver.
    if os.getenv("CF_SMOKE_FIXTURE") == "1":
        from eval.memory_lifecycle.fixture import LLM_SCRIPTS
        return MockLLM(LLM_SCRIPTS)
    return MockLLM()


store = ConversationStore(_make_llm(), SETTINGS, mode=os.getenv("CF_MODE", "split"))


def _make_extractor():
    if os.getenv("CF_LLM_EXTRACT") == "1":
        return LlmMemoryExtractor(store.llm)
    if os.getenv("CF_SMOKE_FIXTURE") == "1":
        from eval.memory_lifecycle.fixture import EXTRACT_SCRIPTS
        return MockMemoryExtractor(EXTRACT_SCRIPTS)
    return MockMemoryExtractor()


extractor = _make_extractor()


class TurnIn(BaseModel):
    conversation_id: str
    message: str
    turn: int


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


def _title_and_loop(r) -> tuple[str | None, str | None]:
    if r.package is None:
        return None, None
    return r.package.task_summary, r.package.selected_open_loop


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    cid = correlation_id(request.headers.get("x-request-id") or request.headers.get("x-correlation-id"))
    request.state.correlation_id = cid
    try:
        response = await call_next(request)
    except Exception:
        logging.getLogger("contextflow").exception("unhandled")
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "correlation_id": cid},
        )
    response.headers["x-request-id"] = cid
    return response


@app.get("/health")
@app.get("/healthz")
def health():
    return {"status": "ok", "service": "contextflow"}


@app.post("/turn", response_model=TurnOut)
def turn(t: TurnIn, request: Request):
    corr = getattr(request.state, "correlation_id", correlation_id())
    try:
        eng = store.engine(t.conversation_id)
        writer = store.writer(t.conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        pipe = run_turn(
            eng, writer, extractor,
            conversation_id=t.conversation_id.strip(),
            message=t.message, turn=t.turn,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="turn_failed") from exc
    r = pipe.turn
    title, loop = _title_and_loop(r)
    emit_decision(decision_event(
        correlation_id=corr,
        conversation_id=t.conversation_id.strip(),
        turn=t.turn,
        transition=r.transition.value,
        task_id=r.task_id,
        referent_id=r.predicted_referent_id,
        extract_ok=pipe.extract.ok,
        extract_status="ok" if pipe.extract.ok else "rejected",
        message_chars=len(t.message or ""),
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
        })
    return {"conversation_id": conversation_id, "tasks": out}


@app.get("/conversations/{conversation_id}/memory")
def list_memory(conversation_id: str):
    try:
        mem = store.memory_store(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    items = []
    for i in mem.all():
        items.append({
            "id": i.id,
            "kind": i.kind,
            "text": i.text,
            "status": i.status,
            "workstream_id": i.workstream_id,
            "slot": i.slot,
            "source_turn": i.source_turn,
        })
    return {"conversation_id": conversation_id, "items": items}


@app.get("/task/{task_id}")
def get_task(task_id: str, conversation_id: str = Query(..., min_length=1)):
    try:
        eng = store.engine(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    t = eng.reg.get(task_id)
    return t.to_dict() if t else {"error": "not found"}
