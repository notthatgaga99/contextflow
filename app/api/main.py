import os
from fastapi import FastAPI
from pydantic import BaseModel

from app.config import SETTINGS
from app.engine import Engine
from app.memory.registry import InMemoryRegistry

app = FastAPI(title="ContextFlow")
_registry = InMemoryRegistry()


def _make_llm():
    if os.getenv("CF_USE_GEMINI") == "1":
        from app.llm.gemini import GeminiClient
        return GeminiClient()
    from app.llm.mock import MockLLM
    return MockLLM()


_engine = Engine(_make_llm(), _registry, SETTINGS,
                 mode=os.getenv("CF_MODE", "split"))


class TurnIn(BaseModel):
    conversation_id: str
    message: str
    turn: int


class TurnOut(BaseModel):
    transition: str
    task_id: str | None
    answer: str | None
    clarify_question: str | None
    decision_tokens: int | None
    answer_tokens: int | None


@app.post("/turn", response_model=TurnOut)
def turn(t: TurnIn):
    r = _engine.handle_turn(t.message, t.turn)
    return TurnOut(
        transition=r.transition.value, task_id=r.task_id, answer=r.answer,
        clarify_question=r.clarify_question,
        decision_tokens=r.package.decision_tokens if r.package else None,
        answer_tokens=r.package.answer_tokens if r.package else None)


@app.get("/task/{task_id}")
def get_task(task_id: str):
    t = _registry.get(task_id)
    return t.to_dict() if t else {"error": "not found"}
