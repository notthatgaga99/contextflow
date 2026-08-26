from app.models.task import Task


class FirestoreRegistry:
    """Seam only. Same Protocol as InMemoryRegistry. Implement later."""

    def add(self, t: Task) -> None: raise NotImplementedError
    def get(self, id: str): raise NotImplementedError
    def all(self) -> list: raise NotImplementedError
    def open_tasks(self) -> list: raise NotImplementedError
    def active(self): raise NotImplementedError
    def mark_active(self, id: str, turn: int) -> None: raise NotImplementedError
    def apply_update(self, id: str, delta: dict) -> None: raise NotImplementedError
