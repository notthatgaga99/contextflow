from dataclasses import dataclass, field
import random

from app.models.task import Task, TaskAnchor

# Domain pools: low-interference (distant) and high-interference (sibling) families.
DISTANT = [
    ("A", "jwt auth", "debug jwt authentication", ["401 on protected route unresolved"],
     ["jwt", "401", "authentication", "token"]),
    ("B", "laptop", "choose a laptop", ["compare macbook vs xps"], ["laptop", "macbook", "xps"]),
    ("C", "slides", "prepare slide deck", ["write closing slide"], ["slide", "deck", "presentation"]),
    ("D", "recipe", "plan a dinner menu", ["pick a dessert"], ["dinner", "menu", "dessert"]),
]
SIBLINGS = [
    ("A", "jwt auth", "fix jwt authentication", ["jwt token not verified"], ["jwt", "token"]),
    ("B", "oauth auth", "fix oauth authentication", ["oauth redirect fails"], ["oauth", "redirect"]),
    ("C", "api auth", "fix api key authentication", ["api key rejected"], ["api", "key"]),
    ("D", "frontend auth", "fix frontend auth guard", ["route guard leaks"], ["frontend", "guard"]),
]

RESUME = {
    "explicit": {"A": "fix the jwt authentication token issue",
                 "B": "fix the oauth redirect", "C": "fix the api key",
                 "D": "fix the frontend guard"},
    "partial": {"A": "fix the authentication token", "B": "fix the oauth thing",
                "C": "fix the api thing", "D": "fix the frontend thing"},
    "referential": {"A": "fix that", "B": "fix that", "C": "fix that", "D": "fix that"},
}


@dataclass
class Scenario:
    scenario_id: str
    seed: int
    open_count: int
    underspec: str
    interference: str
    tasks: list = field(default_factory=list)      # (id,title,goal,loops,cues)
    turns: list = field(default_factory=list)      # (message, turn, gold_task or None)
    gold_task: str = ""
    gold_referent: str = ""


def build_scenarios(seed: int, open_counts=(1, 2, 4), underspecs=("explicit", "partial", "referential"),
                    interferences=("low", "high"), per_cell: int = 30) -> list[Scenario]:
    rng = random.Random(seed)
    out = []
    for oc in open_counts:
        for us in underspecs:
            for itf in interferences:
                for k in range(per_cell):
                    pool = SIBLINGS if itf == "high" else DISTANT
                    chosen = pool[:oc]
                    gold = chosen[0][0]  # return to the first-introduced task
                    turns = []
                    t = 1
                    for spec in chosen:                       # introduce each task
                        turns.append((f"let's work on {spec[2]}", t, spec[0]))
                        t += 1
                    for spec in chosen[1:]:                    # revisit distractors (interleave)
                        turns.append((f"more on {spec[2]}", t, spec[0]))
                        t += 1
                    resume_msg = RESUME[us][gold]
                    turns.append((resume_msg, t + 2, gold))    # the probe (gap before return)
                    out.append(Scenario(
                        scenario_id=f"{itf}_{us}_oc{oc}_{k}", seed=seed, open_count=oc,
                        underspec=us, interference=itf, tasks=list(chosen), turns=turns,
                        gold_task=gold, gold_referent=chosen[0][3][0]))
    return out


def registry_for(scn: Scenario):
    from app.memory.registry import InMemoryRegistry
    r = InMemoryRegistry()
    for (tid, title, goal, loops, cues) in scn.tasks:
        r.add(Task(id=tid, title=title, anchor=TaskAnchor(goal=goal, open_loops=list(loops)),
                   retrieval_cues=list(cues)))
    return r


def scripted_llm(scn: Scenario):
    """Simulate a competent proposal model deterministically from gold labels."""
    from app.llm.mock import MockLLM
    script = {}
    for (msg, turn, gold) in scn.turns:
        if gold:
            script[msg] = {"task_id": gold, "is_new_task": False, "confidence": 0.9}
    return MockLLM(scripted=script)
