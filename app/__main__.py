from app.config import SETTINGS
from app.engine import Engine
from app.memory.registry import InMemoryRegistry
from app.models.task import Task, TaskAnchor
from app.llm.mock import MockLLM


def _seed_registry() -> InMemoryRegistry:
    r = InMemoryRegistry()
    r.add(Task(id="A", title="jwt auth",
               anchor=TaskAnchor(goal="debug jwt authentication",
                                 open_loops=["401 on protected route unresolved"]),
               retrieval_cues=["jwt", "401", "authentication", "token"]))
    r.add(Task(id="B", title="laptop",
               anchor=TaskAnchor(goal="choose a laptop",
                                 open_loops=["compare macbook vs xps"]),
               retrieval_cues=["laptop", "macbook", "xps"]))
    r.add(Task(id="C", title="slides",
               anchor=TaskAnchor(goal="prepare slide deck",
                                 open_loops=["write closing slide"]),
               retrieval_cues=["slide", "deck", "presentation"]))
    return r


def main():
    reg = _seed_registry()
    llm = MockLLM(scripted={
        "authentication": {"task_id": "A", "is_new_task": False, "confidence": 0.9},
        "macbook": {"task_id": "B", "is_new_task": False, "confidence": 0.9},
        "presentation": {"task_id": "C", "is_new_task": False, "confidence": 0.9},
        "fix that authentication thing": {"task_id": "A", "is_new_task": False, "confidence": 0.85},
    })
    eng = Engine(llm, reg, SETTINGS, mode="split")
    script = [
        ("help me with the jwt authentication", 1),
        ("actually the macbook vs xps decision", 2),
        ("now the presentation deck", 3),
        ("okay fix that authentication thing", 8),
    ]
    for msg, turn in script:
        res = eng.handle_turn(msg, turn)
        d = res.decision
        print(f'turn {turn}: "{msg}"')
        print(f'   -> {res.transition.value} task={res.task_id} '
              f'referent={res.predicted_referent_id} '
              f'(top_raw={d.candidates[0].raw:.2f} margin={d.margin:.2f})')
        if res.package:
            print(f'   decision_tokens={res.package.decision_tokens} '
                  f'answer_tokens={res.package.answer_tokens} '
                  f'total={res.package.total_context_tokens} '
                  f'mode={res.package.context_mode} '
                  f'loops={res.package.included_loop_ids}')
    print("\nExpected final: RETURN task=A  (routed by open-loop, not recency)")


if __name__ == "__main__":
    main()
