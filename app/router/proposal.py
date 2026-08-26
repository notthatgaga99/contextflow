from app.domain import LLM
from app.models.task import Task
from app.models.proposal import TaskProposal
from app.llm.base import validate_proposal

PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "nullable": True},
        "is_new_task": {"type": "boolean"},
        "confidence": {"type": "number"},
        "referent": {"type": "string", "nullable": True},
        "rationale": {"type": "string"},
    },
    "required": ["is_new_task", "confidence"],
}


def build_prompt(message: str, open_tasks: list[Task]) -> str:
    cards = "\n".join(t.card() for t in open_tasks) or "none"
    return (
        "You route a user message to one of the user's open tasks, or say it's new.\n"
        "You see the message and short cards for each open task (goal, open loops, recency).\n"
        "Pick the single task the user is most likely acting on. If none fit, set is_new_task=true.\n\n"
        f'MESSAGE: "{message}"\n\nOPEN TASKS:\n{cards}\n\n'
        'Return JSON: {task_id|null, is_new_task, confidence 0..1, referent, rationale}'
    )


def propose(llm: LLM, message: str, open_tasks: list[Task]) -> TaskProposal:
    raw = llm.propose(build_prompt(message, open_tasks), PROPOSAL_SCHEMA)
    return validate_proposal(raw)
