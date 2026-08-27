from app.models.task import Task


class FirestoreRegistry:
    """Seam only. Same Protocol as InMemoryRegistry. Implement later."""

    def add(self, t: Task) -> None: raise NotImplementedError
    def get(self, id: str): raise NotImplementedError
    def all(self) -> list: raise NotImplementedError
    def open_tasks(self) -> list: raise NotImplementedError
    def active(self): raise NotImplementedError
    def mark_active(self, id: str, turn: int) -> None: raise NotImplementedError
    def record_mention(self, task_id: str, turn: int, loop_id: str | None = None) -> None: raise NotImplementedError
    def last_selected_referent(self): raise NotImplementedError
    def set_last_selected_referent(self, referent_id: str | None) -> None: raise NotImplementedError
    def apply_update(self, id: str, delta: dict) -> None: raise NotImplementedError
