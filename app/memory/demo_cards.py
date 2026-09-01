"""Optional workstream cards for smoke/demo/cloud resurrection."""

from app.models.task import Task, TaskAnchor


def seed_e2e_four(registry) -> None:
    """Four-workstream card set for Phase 11 E2E cloud proof (identity only)."""
    cards = [
        ("A", "authentication", "fix JWT authentication",
         ["401 after refresh"], ["jwt", "401", "authentication", "token"]),
        ("B", "corporate outfit", "choose a corporate event outfit",
         ["pick dress color"], ["outfit", "dress", "formal", "evening"]),
        ("C", "Lisbon trip", "plan Lisbon trip",
         ["book hotel with parking"], ["lisbon", "hotel", "travel", "parking"]),
        ("D", "deployment", "fix CI Docker deployment",
         ["CI failing on Docker step"], ["docker", "ci", "deploy", "pipeline"]),
    ]
    for tid, title, goal, loops, cues in cards:
        if registry.get(tid) is None:
            registry.add(Task(
                id=tid, title=title, status="paused",
                retrieval_cues=list(cues),
                anchor=TaskAnchor(goal=goal, open_loops=list(loops)),
            ))


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


def seed_ten(registry) -> None:
    """Ten open workstreams for cloud resurrection engineering proof."""
    cards = [
        ("A", "authentication", "fix JWT authentication",
         ["401 after refresh"], ["jwt", "401", "authentication"]),
        ("B", "deployment", "fix CI Docker deployment",
         ["CI failing on Docker step"], ["docker", "ci", "deploy"]),
        ("C", "orders API", "debug orders API latency",
         ["orders endpoint slow"], ["orders", "api", "latency"]),
        ("D", "checkout", "fix checkout rendering",
         ["component renders twice"], ["checkout", "render"]),
        ("E", "corporate outfit", "choose corporate event outfit",
         ["pick dress color"], ["outfit", "dress", "formal", "evening"]),
        ("F", "travel", "plan Lisbon trip",
         ["book hotel with parking"], ["lisbon", "travel", "hotel"]),
        ("G", "food", "pick dinner restaurant",
         ["vegetarian options"], ["food", "dinner", "restaurant"]),
        ("H", "presentation deck", "prepare slide deck",
         ["write closing slide"], ["deck", "slides", "presentation"]),
        ("I", "job application", "apply for role",
         ["update resume"], ["job", "resume", "application"]),
        ("J", "trivia", "remember trivia fact",
         ["capital of Portugal"], ["trivia", "lisbon", "capital"]),
    ]
    for tid, title, goal, loops, cues in cards:
        if registry.get(tid) is None:
            registry.add(Task(
                id=tid, title=title, status="paused",
                retrieval_cues=list(cues),
                anchor=TaskAnchor(goal=goal, open_loops=list(loops)),
            ))
