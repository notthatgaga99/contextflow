import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.config import SETTINGS
from app.context.working_set import WorkingContextBuilder
from app.memory.catalog import catalog_backend, create_catalog
from app.memory.extractor import LlmMemoryExtractor, MockMemoryExtractor
from app.memory.import_rollup import import_rollup_workstreams
from app.memory.rollup import build_conversation_rollup
from app.memory.sessions import ConversationStore
from app.obs import correlation_id, decision_event, emit_decision
from app.kernel.bind_api import bind_and_expose, resolve_llm_mode
from app.kernel.session import run_kernel_turn

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("contextflow")
app = FastAPI(
    title="ContextFlow Agent",
    description=(
        "Agent workspace: frozen binder + ContextFlow memory planes + tool harness. "
        "UI at GET /. Agent turn at POST /agent/turn. Tools at GET/POST /agent/tools. "
        "DEMO/RESEARCH shape — not a production readiness claim."
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
# H2 catalog: file by default; Firestore when CF_CATALOG_BACKEND=firestore
# (or when CF_MEMORY_BACKEND=firestore and backend unset).
catalog = create_catalog()
CATALOG_BACKEND = catalog_backend()


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


class ImportRollupIn(BaseModel):
    """Opt-in only: seed rollup workstreams into this conversation as paused cards."""
    source_conversation_id: str | None = Field(default=None, max_length=128)
    rollup: dict | None = None
    workstream_ids: list[str] | None = None
    user_key: str = Field(default="local", max_length=128)
    turn: int = Field(default=0, ge=0, le=1_000_000)


def _touch_catalog(conversation_id: str, *, user_key: str = "local") -> None:
    """Best-effort H2 index update; never fails the turn."""
    try:
        eng = store.engine(conversation_id)
        mem = store.memory_store(conversation_id)
        catalog.touch_from_live(
            eng.reg, mem, conversation_id=conversation_id, user_key=user_key,
        )
    except Exception:
        log.exception("catalog_touch_failed conversation_id=%s", conversation_id)


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
    # Host contract (bind_and_expose)
    interrupt: bool | None = None
    l1_expose: str | None = None
    discrimination: dict | None = None
    latency_ms: float | None = None
    llm_mode: str | None = None


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


_STATIC = Path(__file__).resolve().parent / "static" / "index.html"


@app.get("/")
def live_demo_ui():
    """Public reviewer UI — clean chat over POST /turn (Gemini when enabled)."""
    if not _STATIC.is_file():
        raise HTTPException(status_code=404, detail="ui_missing")
    return FileResponse(_STATIC)


@app.get("/health")
@app.get("/healthz")
def health():
    cfg = _config_ok()
    mode = resolve_llm_mode()
    vertex_on = mode == "vertex" or os.getenv("CF_USE_VERTEX") == "1"
    return {
        "status": "ok" if cfg["ok"] else "degraded",
        "service": "contextflow",
        "ready": cfg["ok"],
        "demo_only": DEMO_ONLY,
        "memory_backend": MEMORY_BACKEND,
        "memory_durable": MEMORY_DURABLE,
        "catalog_backend": CATALOG_BACKEND,
        "registry_durable": MEMORY_DURABLE,
        "multi_instance_safe": MEMORY_DURABLE,
        "config_ok": cfg["ok"],
        "config_issues": cfg["issues"],
        "llm_mode": mode,
        "llm": mode,
        "extract": "llm" if os.getenv("CF_LLM_EXTRACT") == "1" else "mock",
        "vertex_enabled": vertex_on,
        "vertex_pace_s": (
            float(os.getenv("CF_VERTEX_MIN_INTERVAL_S") or "0")
            if mode == "vertex" else 0.0
        ),
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
    """HTTP door → same ``bind_and_expose`` contract as in-process hosts."""
    corr = getattr(request.state, "correlation_id", correlation_id())
    try:
        bound = bind_and_expose(
            store, extractor,
            conversation_id=t.conversation_id.strip(),
            message=t.message,
            turn=t.turn,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        log.exception("turn_failed correlation_id=%s", corr)
        raise HTTPException(
            status_code=500,
            detail={"error": "turn_failed", "correlation_id": corr},
        ) from None

    eng = store.engine(bound.conversation_id)
    mem = store.memory_store(bound.conversation_id)
    package_status = (
        "clarify" if bound.interrupt
        else "ok" if bound.package_summary else "none"
    )
    answer_status = (
        "clarify" if bound.interrupt
        else "ok" if bound.answer else "none"
    )
    mem_stats = mem.stats() if hasattr(mem, "stats") else {}
    reg_stats = eng.reg.stats() if hasattr(eng.reg, "stats") else {}
    hist = mem.historical()
    emit_decision(decision_event(
        correlation_id=corr,
        conversation_id=bound.conversation_id,
        turn=t.turn,
        transition=bound.transition,
        task_id=bound.task_id,
        referent_id=bound.predicted_referent_id,
        extract_ok=bound.extract_ok,
        extract_status="ok" if bound.extract_ok else "rejected",
        extract_committed=bound.extract_committed,
        message_chars=len(t.message or ""),
        latency_ms=bound.latency_ms,
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
        context_mode=bound.context_mode,
        demo_only=DEMO_ONLY,
        answer_status=answer_status,
    ))
    _touch_catalog(bound.conversation_id)
    return TurnOut(
        conversation_id=bound.conversation_id,
        transition=bound.transition,
        task_id=bound.task_id,
        answer=bound.answer,
        workstream_title=bound.workstream_title,
        selected_loop=bound.selected_loop,
        clarify_question=bound.clarify_question,
        decision_tokens=bound.decision_tokens,
        answer_tokens=bound.answer_tokens,
        predicted_task_id=bound.predicted_task_id,
        predicted_referent_id=bound.predicted_referent_id,
        context_mode=bound.context_mode,
        included_loop_ids=bound.included_loop_ids,
        total_context_tokens=bound.total_context_tokens,
        correlation_id=corr,
        extract_ok=bound.extract_ok,
        extract_committed=bound.extract_committed,
        demo_only=DEMO_ONLY,
        memory_backend=MEMORY_BACKEND,
        interrupt=bound.interrupt,
        l1_expose=bound.l1_expose,
        discrimination=bound.discrimination or None,
        latency_ms=bound.latency_ms,
        llm_mode=bound.llm_mode,
    )


@app.post("/bind")
def bind_only(t: TurnIn, request: Request):
    """Host door: full ``bind_and_expose`` JSON (interrupt + L1 + discrimination).

    Same kernel as ``/turn``. Prefer this when the shell owns generate and must
    pause on ``interrupt=true`` (LangGraph-shaped hosts).
    """
    corr = getattr(request.state, "correlation_id", correlation_id())
    try:
        bound = bind_and_expose(
            store, extractor,
            conversation_id=t.conversation_id.strip(),
            message=t.message,
            turn=t.turn,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        log.exception("bind_failed correlation_id=%s", corr)
        raise HTTPException(
            status_code=500,
            detail={"error": "bind_failed", "correlation_id": corr},
        ) from None
    _touch_catalog(bound.conversation_id)
    payload = bound.to_dict()
    payload["correlation_id"] = corr
    payload["demo_only"] = DEMO_ONLY
    payload["memory_backend"] = MEMORY_BACKEND
    return payload


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
            "procedures": [i.text for i in asserted if i.kind == "procedure"],
            "planes": {
                "long_term": [i.text for i in asserted if i.kind != "procedure"],
                "procedural": [i.text for i in asserted if i.kind == "procedure"],
            },
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


@app.get("/conversations/{conversation_id}/rollup")
def conversation_rollup(conversation_id: str):
    """Structured condensation of open workstreams from asserted memory (not chat summary)."""
    try:
        eng = store.engine(conversation_id)
        mem = store.memory_store(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    roll = build_conversation_rollup(eng.reg, mem, conversation_id=conversation_id)
    out = roll.to_dict()
    out["demo_only"] = DEMO_ONLY
    out["memory_backend"] = MEMORY_BACKEND
    return out


@app.post("/conversations/{conversation_id}/archive")
def archive_conversation(
    conversation_id: str,
    user_key: str = Query(default="local", max_length=128),
):
    """Snapshot structured rollup into the last-N catalog (does not delete the live chat)."""
    try:
        eng = store.engine(conversation_id)
        mem = store.memory_store(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    entry = catalog.touch_from_live(
        eng.reg, mem, conversation_id=conversation_id.strip(), user_key=user_key,
    )
    return {
        "ok": True,
        "entry": entry.summary(),
        "catalog_limit": catalog.max_entries,
        "demo_only": DEMO_ONLY,
    }


@app.get("/catalog")
def list_catalog(
    user_key: str = Query(default="local", max_length=128),
    limit: int | None = Query(default=None, ge=1, le=50),
):
    """Last-N conversation index. Summaries only — not injected into generate()."""
    entries = catalog.list(user_key=user_key, limit=limit)
    return {
        "user_key": user_key,
        "catalog_limit": catalog.max_entries,
        "catalog_backend": CATALOG_BACKEND,
        "count": len(entries),
        "conversations": [e.summary() for e in entries],
        "demo_only": DEMO_ONLY,
        "note": "Opt-in import via POST /conversations/{id}/import-rollup. Never auto-merged.",
    }


@app.get("/catalog/match")
def match_catalog(
    q: str = Query(..., min_length=1, max_length=500),
    user_key: str = Query(default="local", max_length=128),
    limit: int = Query(default=3, ge=1, le=10),
):
    """Tier C soft suggest: lexical match over rollup blurbs/titles.

    Returns summaries only. Does **not** import or touch generate/L1.
    Host/UI must call POST …/import-rollup after explicit consent.
    """
    hits = catalog.match(q, user_key=user_key, limit=limit)
    return {
        "query": q,
        "user_key": user_key,
        "catalog_backend": CATALOG_BACKEND,
        "count": len(hits),
        "matches": [
            {**ent.summary(), "score": round(score, 4)}
            for ent, score in hits
        ],
        "demo_only": DEMO_ONLY,
        "note": "Suggest only — never auto-merged. Import via POST /conversations/{id}/import-rollup.",
    }


@app.get("/catalog/{conversation_id}")
def get_catalog_entry(
    conversation_id: str,
    user_key: str = Query(default="local", max_length=128),
):
    entry = catalog.get(conversation_id, user_key=user_key)
    if entry is None:
        raise HTTPException(status_code=404, detail="catalog_entry_not_found")
    return {
        "entry": entry.summary(),
        "rollup": entry.rollup,
        "demo_only": DEMO_ONLY,
        "catalog_backend": CATALOG_BACKEND,
    }


@app.post("/conversations/{conversation_id}/import-rollup")
def import_rollup(conversation_id: str, body: ImportRollupIn):
    """Explicitly seed paused workstreams from a catalog entry or inline rollup."""
    try:
        eng = store.engine(conversation_id)
        writer = store.writer(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rollup = body.rollup
    if rollup is None:
        src = (body.source_conversation_id or "").strip()
        if not src:
            raise HTTPException(
                status_code=400,
                detail="source_conversation_id_or_rollup_required",
            )
        entry = catalog.get(src, user_key=body.user_key)
        if entry is None:
            # Fall back to live conversation rollup if still in process memory.
            try:
                src_eng = store.engine(src)
                src_mem = store.memory_store(src)
                rollup = build_conversation_rollup(
                    src_eng.reg, src_mem, conversation_id=src,
                ).to_dict()
            except ValueError as exc:
                raise HTTPException(
                    status_code=404, detail="source_not_found",
                ) from exc
        else:
            rollup = entry.rollup

    result = import_rollup_workstreams(
        eng.reg,
        writer,
        rollup,
        workstream_ids=body.workstream_ids,
        turn=body.turn,
        as_paused=True,
    )
    if not result.ok:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "import_failed",
                "errors": result.errors,
                "skipped": result.skipped,
                "imported": result.imported,
            },
        )
    _touch_catalog(conversation_id.strip(), user_key=body.user_key)
    return {
        "ok": True,
        "conversation_id": conversation_id,
        "imported": result.imported,
        "skipped": result.skipped,
        "demo_only": DEMO_ONLY,
        "note": "Imported as paused. Gate must SELECT before answer package uses them.",
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
            "procedures": list(getattr(proj, "procedures", []) or []),
        },
        "excluded_workstreams": list(proj.excluded_workstreams),
        "demo_only": DEMO_ONLY,
    }


@app.get("/conversations/{conversation_id}/compact-notation")
def compact_notation(
    conversation_id: str,
    task_id: str = Query(..., min_length=1),
    referent_id: str | None = None,
    query: str | None = None,
):
    """SHORT_TERM (L1) compact notation + plane diagnostics for a bound thread."""
    from app.context.working_memory_switch import assemble_bound_memory
    from app.memory.planes import plane_catalog

    try:
        eng = store.engine(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    task = eng.reg.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    if eng.memory_port is None:
        raise HTTPException(status_code=404, detail="memory_port_unavailable")
    ref = referent_id or (f"{task_id}.loop1" if task.anchor.open_loops else task_id)
    loop = task.anchor.open_loops[0] if task.anchor.open_loops else None
    bundle = assemble_bound_memory(
        eng.memory_port,
        workstream_id=task_id,
        referent_id=ref,
        selected_loop=loop,
        builder=eng.working_context_builder,
        open_tasks=eng.reg.open_tasks(),
        query=query,
    )
    if bundle is None or bundle.short_term is None:
        raise HTTPException(status_code=404, detail="notation_unavailable")
    notation = bundle.short_term
    return {
        "conversation_id": conversation_id,
        "notation": notation.to_dict(),
        "expose_text": notation.to_expose_text(),
        "planes": {
            "short_term": notation.to_dict(),
            "long_term": bundle.long_term.to_dict(),
            "procedural": bundle.procedural.to_dict(),
            "relevant": bundle.relevant.to_dict(),
            "index": bundle.index.to_dict(),
        },
        "diagnostics": bundle.diagnostics,
        "plane_catalog": plane_catalog(),
        "design": bundle.to_dict().get("design"),
        "demo_only": DEMO_ONLY,
        "note": (
            "ContextFlow RB-WSR: generate() reads SHORT_TERM (L1) only. "
            "LONG_TERM / PROCEDURAL feed it; RELEVANT is bound cold; "
            "INDEX/ARCHIVE never dump into generate."
        ),
    }


@app.get("/memory/planes")
def memory_planes():
    """Describe ContextFlow memory planes (our model; learn-from, not clone)."""
    from app.memory.planes import design_notes, plane_catalog

    return {
        "planes": plane_catalog(),
        "design": design_notes(),
        "demo_only": DEMO_ONLY,
    }


class AgentTurnIn(BaseModel):
    conversation_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=8000)
    turn: int = Field(..., ge=0, le=1_000_000)
    auto_tools: bool = True


class ToolInvokeIn(BaseModel):
    conversation_id: str = Field(..., min_length=1, max_length=128)
    arguments: dict = Field(default_factory=dict)


@app.get("/agent/tools")
def agent_tools():
    """List tool harness entries for the agent shell."""
    from app.agent.tools import list_tools

    return {
        "tools": list_tools(),
        "note": "Tools use MemoryPort/Writer. Binder stays frozen authority.",
        "demo_only": DEMO_ONLY,
    }


@app.post("/agent/tools/{tool_name}")
def agent_tool_invoke(tool_name: str, body: ToolInvokeIn):
    """Manual tool invoke. Write/search tools should pass the bound workstream_id.

    Does not re-bind. Prefer POST /agent/turn for the fail-closed loop.
    """
    from app.agent.tools import TOOL_REGISTRY, invoke_tool

    args = dict(body.arguments or {})
    args.setdefault("conversation_id", body.conversation_id)
    # Fail-closed for write tools: workstream must exist (no invent).
    entry = TOOL_REGISTRY.get(tool_name)
    if entry and entry[0].category == "write":
        wid = str(args.get("workstream_id") or "").strip()
        if not wid:
            raise HTTPException(status_code=400, detail="workstream_id_required")
        try:
            eng = store.engine(body.conversation_id.strip())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if eng.reg.get(wid) is None:
            raise HTTPException(status_code=404, detail=f"unknown_workstream:{wid}")
    result = invoke_tool(store, tool_name, args)
    if not result.ok and result.error and result.error.startswith("unknown_tool"):
        raise HTTPException(status_code=404, detail=result.error)
    if not result.ok and result.error and result.error.startswith("workstream_not_bound"):
        raise HTTPException(status_code=400, detail=result.error)
    return {**result.to_dict(), "demo_only": DEMO_ONLY}


@app.post("/agent/turn")
def agent_turn(body: AgentTurnIn, request: Request):
    """Agentic turn: bind → L1/answer → optional bound tools (never re-bind)."""
    from app.agent.turn import run_agent_turn

    corr = getattr(request.state, "correlation_id", correlation_id())
    try:
        payload = run_agent_turn(
            store, extractor,
            conversation_id=body.conversation_id.strip(),
            message=body.message,
            turn=body.turn,
            auto_tools=body.auto_tools,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        log.exception("agent_turn_failed correlation_id=%s", corr)
        raise HTTPException(
            status_code=500,
            detail={"error": "agent_turn_failed", "correlation_id": corr},
        ) from None
    _touch_catalog(body.conversation_id.strip())
    payload["correlation_id"] = corr
    payload["demo_only"] = DEMO_ONLY
    mode = resolve_llm_mode()
    payload["llm"] = mode
    payload["llm_mode"] = mode
    return payload


@app.get("/agent/snapshot")
def agent_snapshot(conversation_id: str = Query(..., min_length=1)):
    """Full shell snapshot: threads + planes catalog + tool list."""
    from app.agent.tools import invoke_tool, list_tools
    from app.memory.planes import design_notes, plane_catalog

    threads = invoke_tool(
        store, "list_threads", {"conversation_id": conversation_id},
    )
    health = invoke_tool(
        store, "session_health", {"conversation_id": conversation_id},
    )
    return {
        "conversation_id": conversation_id,
        "threads": threads.data if threads.ok else {},
        "health": health.data if health.ok else {},
        "planes": plane_catalog(),
        "design": design_notes(),
        "tools": list_tools(),
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
