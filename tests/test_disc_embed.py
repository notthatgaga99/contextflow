"""Embed mix on distinctive (I) channel — never genre-only cosine winners."""

from __future__ import annotations

import os

import pytest

from app.domain import Transition
from app.router.thread_discriminate import (
    decide_discrimination,
    score_threads,
)
from tests.conftest import make_task

pytestmark = pytest.mark.trust


@pytest.fixture(autouse=True)
def _embed_on(monkeypatch):
    monkeypatch.setenv("CF_DISC_EMBED", "1")
    monkeypatch.setenv("CF_DISC_EMBED_W", "0.35")
    monkeypatch.setenv("CF_DISC_EMBED_USE_LLM", "0")


def test_embed_boosts_distinctive_over_shared_genre():
    auth = make_task(
        "A", "JWT auth refresh", "fix auth",
        ["session refresh path"], ["jwt", "auth", "session", "refresh", "token"],
    )
    orders = make_task(
        "C", "orders checkout", "fix checkout",
        ["checkout path"], ["orders", "cart", "checkout", "error", "service"],
    )
    msg = "session refresh still failing on the auth path"
    off = score_threads(msg, [auth, orders])
    # Force embed contrast visible
    os.environ["CF_DISC_EMBED_W"] = "0.5"
    on = score_threads(msg, [auth, orders])
    assert on["A"].distinctive_emb >= 0.0
    assert on["A"].distinctive >= off["A"].distinctive_raw * 0.0  # smoke
    assert on["A"].distinctive > on["C"].distinctive


def test_embed_never_binds_shared_genre_alone():
    """Shared error/service must CLARIFY — cosine must not silently pick."""
    auth = make_task(
        "A", "JWT auth", "fix JWT",
        ["JWT error"], ["jwt", "auth", "401", "error", "service"],
    )
    orders = make_task(
        "C", "orders", "fix orders",
        ["orders error"], ["orders", "cart", "401", "error", "service"],
    )
    decided = decide_discrimination(
        message="error again from the service",
        gate_transition=Transition.CONTINUE,
        gate_task_id="A",
        open_tasks=[auth, orders],
        active_id="A",
        underspecified=False,
    )
    assert decided is not None
    assert decided.transition == Transition.CLARIFY
    assert decided.task_id is None


def test_embed_off_leaves_lex_only(monkeypatch):
    monkeypatch.setenv("CF_DISC_EMBED", "0")
    auth = make_task("A", "JWT", "g", ["loop"], ["jwt", "refresh"])
    orders = make_task("C", "orders", "g", ["loop"], ["orders", "cart"])
    scores = score_threads("jwt refresh", [auth, orders])
    assert scores["A"].distinctive_emb == 0.0
