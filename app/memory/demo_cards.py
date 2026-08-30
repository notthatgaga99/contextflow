"""Optional ABCD workstream cards for smoke/demo. Not routing. Default unused."""

from app.models.task import Task, TaskAnchor


def seed_abcd(registry) -> None:
    cards = [
        ("A", "authentication", "fix JWT authentication",
         ["401 after refresh", "refresh token still expired"],
         ["jwt", "401", "authentication", "token"]),
        ("B", "corporate outfit", "choose a corporate event outfit",
         ["pick dress color"], ["outfit", "dress", "navy", "formal"]),
        ("C", "travel", "plan Lisbon trip",
         ["book hotel with parking"], ["lisbon", "hotel", "travel", "parking"]),
        ("D", "paper", "finish paper draft",
         ["write related-work section"], ["paper", "draft", "citation", "apa"]),
    ]
    for tid, title, goal, loops, cues in cards:
        if registry.get(tid) is None:
            registry.add(Task(
                id=tid, title=title, status="paused",
                retrieval_cues=list(cues),
                anchor=TaskAnchor(goal=goal, open_loops=list(loops)),
            ))
