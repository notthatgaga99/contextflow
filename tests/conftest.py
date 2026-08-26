try:
    import pytest
except ImportError:  # sandbox fallback
    class _P:
        @staticmethod
        def fixture(fn=None, **k):
            def deco(f): return f
            return deco(fn) if fn else deco
    pytest = _P()

from app.models.task import Task, TaskAnchor
from app.memory.registry import InMemoryRegistry
from app.llm.mock import MockLLM


def make_task(tid, title, goal, loops, cues):
    return Task(id=tid, title=title,
                anchor=TaskAnchor(goal=goal, open_loops=loops),
                retrieval_cues=cues)


@pytest.fixture
def registry():
    r = InMemoryRegistry()
    r.add(make_task("A", "jwt auth", "debug jwt authentication",
                    ["401 on protected route unresolved"], ["jwt", "401", "authentication", "token"]))
    r.add(make_task("B", "laptop", "choose a laptop",
                    ["compare macbook vs xps"], ["laptop", "macbook", "xps"]))
    r.add(make_task("C", "slides", "prepare slide deck",
                    ["write closing slide"], ["slide", "deck", "presentation"]))
    return r


@pytest.fixture
def mock():
    return MockLLM()


def scripted(**mapping):
    return MockLLM(scripted=mapping)
