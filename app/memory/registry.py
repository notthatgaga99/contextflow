from typing import Optional

from app.models.task import Task
from app.router.referent import ensure_loop_clocks, loop_index_from_id


class InMemoryRegistry:
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._versions: dict[str, int] = {}
        self._last_selected_referent: Optional[str] = None

    def add(self, t: Task) -> None:
        self._tasks[t.id] = t
        self._versions.setdefault(t.id, 1)

    def get(self, id: str) -> Task | None:
        return self._tasks.get(id)

    def all(self) -> list[Task]:
        return list(self._tasks.values())

    def open_tasks(self) -> list[Task]:
        return [t for t in self._tasks.values() if t.status in ("active", "paused")]

    def mark_abandoned(self, task_id: str) -> None:
        """Close a workstream for routing/retrieval. Memory items remain for audit."""
        t = self._tasks.get(task_id)
        if t is not None:
            t.status = "abandoned"

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

    def record_mention(self, task_id: str, turn: int, loop_id: Optional[str] = None) -> None:
        """User-mention clocks. Not written from LLM answers."""
        t = self._tasks[task_id]
        ensure_loop_clocks(t)
        t.mention_turn = turn
        if loop_id is None:
            return
        idx = loop_index_from_id(task_id, loop_id)
        if idx is not None and 0 <= idx < len(t.loop_mention_turns):
            t.loop_mention_turns[idx] = turn

    def last_selected_referent(self) -> Optional[str]:
        return self._last_selected_referent

    def set_last_selected_referent(self, referent_id: Optional[str]) -> None:
        self._last_selected_referent = referent_id

    def apply_update(self, id: str, delta: dict) -> None:
        t = self._tasks[id]
        a = t.anchor
        for k in ("decisions", "constraints", "open_loops", "entities"):
            for item in delta.get(k, []):
                if item not in getattr(a, k):
                    getattr(a, k).append(item)
        for loop in delta.get("resolved_loops", []):
            if loop in a.open_loops:
                idx = a.open_loops.index(loop)
                a.open_loops.remove(loop)
                if idx < len(t.loop_mention_turns):
                    t.loop_mention_turns.pop(idx)
        if "goal" in delta:
            a.goal = delta["goal"]
        if "current_state" in delta:
            a.current_state = delta["current_state"]
        added = len(a.open_loops) - len(t.loop_mention_turns)
        if added > 0:
            t.loop_mention_turns.extend([0] * added)
        ensure_loop_clocks(t)
        self._versions[id] = self._versions.get(id, 1) + 1

    def version(self, id: str) -> int:
        return self._versions.get(id, 0)
