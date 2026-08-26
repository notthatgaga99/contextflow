from app.models.task import Task


class InMemoryRegistry:
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._versions: dict[str, int] = {}

    def add(self, t: Task) -> None:
        self._tasks[t.id] = t
        self._versions.setdefault(t.id, 1)

    def get(self, id: str) -> Task | None:
        return self._tasks.get(id)

    def all(self) -> list[Task]:
        return list(self._tasks.values())

    def open_tasks(self) -> list[Task]:
        return [t for t in self._tasks.values() if t.status in ("active", "paused")]

    def active(self) -> Task | None:
        for t in self._tasks.values():
            if t.status == "active":
                return t
        return None

    def mark_active(self, id: str, turn: int) -> None:
        for t in self._tasks.values():
            if t.status == "active" and t.id != id:
                t.status = "paused"
        t = self._tasks[id]
        t.status = "active"
        t.last_active_turn = turn

    def apply_update(self, id: str, delta: dict) -> None:
        t = self._tasks[id]
        a = t.anchor
        for k in ("decisions", "constraints", "open_loops", "entities"):
            for item in delta.get(k, []):
                if item not in getattr(a, k):
                    getattr(a, k).append(item)
        for loop in delta.get("resolved_loops", []):
            if loop in a.open_loops:
                a.open_loops.remove(loop)
        if "goal" in delta:
            a.goal = delta["goal"]
        if "current_state" in delta:
            a.current_state = delta["current_state"]
        self._versions[id] = self._versions.get(id, 1) + 1

    def version(self, id: str) -> int:
        return self._versions.get(id, 0)
