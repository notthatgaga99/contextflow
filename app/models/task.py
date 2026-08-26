from dataclasses import dataclass, field, asdict


@dataclass
class TaskAnchor:
    goal: str = ""
    current_state: str = ""
    decisions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    open_loops: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)


@dataclass
class Task:
    id: str
    title: str
    status: str = "active"  # active | paused | resolved
    retrieval_cues: list[str] = field(default_factory=list)
    anchor: TaskAnchor = field(default_factory=TaskAnchor)
    last_active_turn: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0

    def card(self) -> str:
        loops = "; ".join(self.anchor.open_loops) or "none"
        goal = self.anchor.goal or self.title
        return f"[{self.id}] goal: {goal}; open_loops: {loops}; last_active_turn: {self.last_active_turn}"

    def to_dict(self) -> dict:
        return asdict(self)
