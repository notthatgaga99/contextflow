import math
import re
import numpy as np

from app.config import Settings, NEW_ID
from app.domain import LLM
from app.models.task import Task
from app.models.proposal import TaskProposal, Candidate


def task_text(t: Task) -> str:
    cues = " ".join(t.retrieval_cues)
    return f"{t.anchor.goal or t.title} {cues}".strip()


def cos_sim(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
    return max(0.0, float(a @ b / denom))


def recency(last: int, now: int, lam: float) -> float:
    return math.exp(-lam * max(0, now - last))


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def open_loop_match(message: str, t: Task) -> float:
    msg = _tokens(message)
    if not msg:
        return 0.0
    for loop in t.anchor.open_loops:
        loop_terms = _tokens(loop)
        if loop_terms and (loop_terms & msg):
            return 1.0
    cues = {c.lower() for c in t.retrieval_cues}
    if cues & msg:
        return 1.0
    return 0.0


def score_candidates(llm: LLM, message: str, open_tasks: list[Task],
                     proposal: TaskProposal, turn: int,
                     settings: Settings, apply_llm: bool = True) -> list[Candidate]:
    msg_emb = llm.embed([message])[0]
    task_embs = {t.id: llm.embed([task_text(t)])[0] for t in open_tasks}

    cands: list[Candidate] = []
    for t in open_tasks:
        llm_conf = 0.0
        if apply_llm and (not proposal.is_new_task and proposal.task_id == t.id):
            llm_conf = proposal.confidence
        cos = cos_sim(msg_emb, task_embs[t.id])
        rec = recency(t.last_active_turn, turn, settings.LAMBDA)
        loop = open_loop_match(message, t)
        raw = (settings.W_LLM * llm_conf + settings.W_SIM * cos
               + settings.W_REC * rec + settings.W_LOOP * loop)
        cands.append(Candidate(task_id=t.id, raw=raw, norm=0.0,
                               components={"llm": llm_conf, "cos": cos, "rec": rec, "loop": loop}))

    new_llm = proposal.confidence if (apply_llm and proposal.is_new_task) else 0.0
    new_base = settings.BASE_NEW if proposal.is_new_task else 0.0
    new_raw = settings.W_LLM * new_llm + new_base
    cands.append(Candidate(task_id=NEW_ID, raw=new_raw, norm=0.0,
                           components={"llm": new_llm, "cos": 0.0, "rec": 0.0, "loop": 0.0}))

    total = sum(c.raw for c in cands) + settings.EPS
    for c in cands:
        c.norm = c.raw / total
    cands.sort(key=lambda c: c.norm, reverse=True)
    return cands
