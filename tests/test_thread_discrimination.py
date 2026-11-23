"""Thread discrimination: near-miss ≠ same; surface-shift / extension = continue.

Marked trust — these are switch-mastery laws, Mock-only.
"""

from __future__ import annotations

import pytest

from app.domain import Transition
from app.models.task import Task, TaskAnchor
from app.router.thread_discriminate import (
    _tokens,
    prefer_distinctive,
    score_threads,
    stick_active_extension,
)
from app.router.topic_align import align_plan

pytestmark = pytest.mark.trust


def _task(tid: str, title: str, cues: list[str], loops: list[str] | None = None) -> Task:
    return Task(
        id=tid,
        title=title,
        retrieval_cues=cues,
        anchor=TaskAnchor(goal=title, open_loops=loops or [title]),
    )


def test_three_letter_identity_token_stems_symmetrically():
    """jwt (3) must not lose to cart (4) via plural-fold asymmetry."""
    jwt_toks = _tokens("jwt")
    cart_toks = _tokens("cart")
    assert "jwts" in jwt_toks
    assert "carts" in cart_toks
    assert len(jwt_toks) == len(cart_toks)


def test_named_pair_jwt_or_cart_clarifies():
    """User names both identities — do not silently pick a winner."""
    auth = _task("A", "JWT auth", ["jwt", "auth", "401", "refresh"])
    orders = _task("C", "orders checkout", ["orders", "cart", "401", "checkout"])
    out = align_plan(
        message="401 again, maybe jwt or cart?",
        transition=Transition.CONTINUE,
        task_id="A",
        open_tasks=[auth, orders],
        active_id="A",
        memory_texts_by_task={"A": ["refresh fails"], "C": ["checkout 401"]},
    )
    assert out is not None
    assert out.transition == Transition.CLARIFY
    assert out.discrimination.get("high_confusion") is True
    assert out.discrimination.get("region") == "near_miss_clarify"


def test_near_miss_jwt_vs_orders_distinctive_wins():
    """Seemingly close (both 401) but different threads — JWT wins on distinctive."""
    auth = _task(
        "A",
        "JWT auth refresh 401",
        ["jwt", "auth", "refresh", "ttl", "401", "cookie"],
        loops=["JWT 401 after refresh"],
    )
    orders = _task(
        "C",
        "orders API 401",
        ["orders", "cart", "checkout", "401", "sku"],
        loops=["orders 401 on checkout"],
    )
    msg = "JWT refresh still returns 401 — check TTL and cookie"
    scores = score_threads(msg, [auth, orders])
    assert scores["A"].distinctive > scores["C"].distinctive
    pick = prefer_distinctive(scores, "C")  # gate wrongly picked orders
    assert pick == "A"

    out = align_plan(
        message=msg,
        transition=Transition.CONTINUE,
        task_id="C",
        open_tasks=[auth, orders],
        active_id="C",
        memory_texts_by_task={
            "A": ["JWT refresh cookie", "TTL 5 minutes"],
            "C": ["checkout cart 401"],
        },
    )
    assert out is not None
    assert out.task_id == "A"
    assert "discriminate" in out.reason or "steal" in out.reason
    assert out.discrimination.get("high_confusion") is True
    assert out.discrimination.get("winner_id") == "A"
    assert out.discrimination.get("delta_I", 0) >= 0


def test_surface_shift_continue_same_thread():
    """Seemingly different wording — still CONTINUE on auth."""
    auth = _task(
        "A",
        "JWT auth refresh",
        ["jwt", "auth", "refresh", "ttl", "aud"],
        loops=["JWT 401 after refresh"],
    )
    orders = _task(
        "C",
        "orders checkout",
        ["orders", "cart", "checkout", "sku"],
        loops=["orders flaky checkout"],
    )
    msg = "also set aud to api.internal on the auth service"
    out = align_plan(
        message=msg,
        transition=Transition.CONTINUE,
        task_id="A",
        open_tasks=[auth, orders],
        active_id="A",
        memory_texts_by_task={"A": ["JWT refresh", "TTL 5 minutes"]},
    )
    # Keep gate CONTINUE on A (None) or explicit stick — not NEW, not orders.
    if out is not None:
        assert out.transition != Transition.NEW
        assert out.task_id in (None, "A") or out.reason.startswith("stick")
    scores = score_threads(msg, [auth, orders], {"A": ["JWT refresh"]})
    assert stick_active_extension(msg, "A", scores) or scores["A"].distinctive >= scores["C"].distinctive


def test_extension_needs_more_context_stays_active():
    """Extension of same thread needing more context — not NEW."""
    trip = _task(
        "F",
        "Lisbon trip parking hotel",
        ["lisbon", "hotel", "parking", "alfama"],
        loops=["hotel needs parking near center"],
    )
    outfit = _task(
        "E",
        "navy formal dress",
        ["navy", "dress", "formal", "hosting"],
        loops=["color for corporate event"],
    )
    msg = "can we also check if the hotel allows late checkout?"
    out = align_plan(
        message=msg,
        transition=Transition.NEW,  # spurious NEW from gate
        task_id=None,
        open_tasks=[trip, outfit],
        active_id="F",
        memory_texts_by_task={"F": ["Lisbon hotel parking Alfama"]},
    )
    # Underspecified NEW sticks via stick_underspecified_new, or extension stick.
    assert out is not None
    assert out.transition == Transition.CONTINUE
    assert out.task_id == "F"


def test_common_concepts_removed_still_auth():
    """Drop shared '401' — distinctive jwt/refresh still means auth thread."""
    auth = _task(
        "A",
        "JWT auth service",
        ["jwt", "auth", "refresh", "ttl", "cookie", "401"],
        loops=["fix refresh path"],
    )
    orders = _task(
        "C",
        "orders service",
        ["orders", "cart", "401", "checkout"],
        loops=["checkout failures"],
    )
    msg = "the refresh cookie path still fails after rotating keys"
    scores = score_threads(
        msg, [auth, orders],
        {"A": ["JWT refresh cookie", "TTL"], "C": ["orders checkout"]},
    )
    assert scores["A"].distinctive > scores["C"].distinctive
    out = align_plan(
        message=msg,
        transition=Transition.SWITCH,
        task_id="C",
        open_tasks=[auth, orders],
        active_id="C",
        memory_texts_by_task={
            "A": ["JWT refresh cookie", "TTL"],
            "C": ["orders checkout cart"],
        },
    )
    assert out is not None
    assert out.task_id == "A"


def test_high_confusion_never_binds_by_overlap_alone():
    """Hard invariant: under high C_S, final bind follows argmax d (identity), not o."""
    from app.router.thread_discriminate import decide_discrimination

    auth = _task(
        "A", "JWT auth", ["jwt", "refresh", "ttl", "401", "cookie"],
        loops=["JWT 401"],
    )
    orders = _task(
        "C", "orders 401", ["orders", "cart", "401", "checkout"],
        loops=["orders 401"],
    )
    # Message heavy on shared 401 + distinctive jwt — gate wrongly prefers C
    msg = "401 on JWT refresh — ttl and cookie"
    dec = decide_discrimination(
        message=msg,
        gate_transition=Transition.CONTINUE,
        gate_task_id="C",
        open_tasks=[auth, orders],
        active_id="C",
        memory_texts_by_task={
            "A": ["JWT refresh cookie"],
            "C": ["orders checkout 401"],
        },
        underspecified=False,
    )
    assert dec is not None
    assert dec.evidence.high_confusion
    assert dec.task_id == dec.evidence.winner_id == "A"
    assert dec.transition != Transition.NEW


def test_kernel_clarify_near_miss_asks_about_confused_threads():
    """E2E: weak identity + high confusion → CLARIFY with both thread labels."""
    from app.config import SETTINGS
    from app.engine import Engine
    from app.kernel.session import run_kernel_turn
    from app.llm.mock import MockLLM
    from app.memory.extractor import MockMemoryExtractor
    from app.memory.registry import InMemoryRegistry
    from app.memory.store import InMemoryMemoryStore
    from app.memory.writer import MemoryWriter
    from app.models.memory import MemoryPatch

    reg = InMemoryRegistry()
    auth = _task("A", "JWT auth refresh", ["jwt", "auth", "401", "refresh"])
    orders = _task("C", "orders checkout", ["orders", "cart", "401", "checkout"])
    reg.add(auth)
    reg.add(orders)
    reg.mark_active("A", 1)
    store = InMemoryMemoryStore(conversation_id="clar-e2e")
    w = MemoryWriter(store, reg)
    w.commit([
        MemoryPatch(kind="fact", text="refresh fails", source_turn=1, workstream_id="A"),
        MemoryPatch(kind="fact", text="checkout 401", source_turn=1, workstream_id="C"),
    ], turn=1)
    # Gate may stick to A; discrimination should force CLARIFY on bare 401
    llm = MockLLM({
        "401": {"task_id": "A", "is_new_task": False, "confidence": 0.9},
        "still": {"task_id": "A", "is_new_task": False, "confidence": 0.9},
    })
    eng = Engine(llm, reg, SETTINGS, memory_store=store)
    k = run_kernel_turn(
        eng, w, MockMemoryExtractor(),
        conversation_id="clar-e2e",
        message="still getting 401",
        turn=2,
    )
    assert k.result.transition == Transition.CLARIFY
    assert k.result.clarify_question
    q = k.result.clarify_question.lower()
    assert "jwt" in q or "auth" in q or "refresh" in q
    assert "order" in q or "checkout" in q or "cart" in q
    disc = (k.result.resolution_evidence or {}).get("discrimination") or {}
    assert disc.get("high_confusion") is True
    assert disc.get("region") == "near_miss_clarify"


def test_new_turn_extract_before_answer_sees_fact():
    """Honesty fix: NEW generates after extract so same-turn fact can land in L1."""
    from app.engine import Engine
    from app.llm.mock import MockLLM
    from app.memory.extractor import LlmMemoryExtractor, apply_extraction
    from app.memory.registry import InMemoryRegistry
    from app.memory.store import InMemoryMemoryStore
    from app.memory.writer import MemoryWriter
    from app.turn_pipeline import run_turn
    import json
    import re

    class _Ext:
        def generate(self, prompt: str) -> str:
            ws = "T1"
            if "FOCUS WORKSTREAM" in prompt:
                m = re.search(r"FOCUS WORKSTREAM.*?:\s*(\S+)", prompt)
                if m:
                    ws = m.group(1)
            if "leaking" not in prompt.lower() and "espresso" not in prompt.lower():
                return json.dumps([])
            return json.dumps([{
                "kind": "fact",
                "text": "espresso machine keeps leaking",
                "workstream_id": ws,
            }])

        def embed(self, texts):
            return MockLLM().embed(texts)

    reg = InMemoryRegistry()
    store = InMemoryMemoryStore(conversation_id="disc-new")
    writer = MemoryWriter(store, reg)
    llm = MockLLM({
        "espresso": {"task_id": None, "is_new_task": True, "confidence": 0.95},
    })
    eng = Engine(llm, reg, memory_store=store)
    pipe = run_turn(
        eng, writer, LlmMemoryExtractor(_Ext()),
        conversation_id="disc-new",
        message="I need to figure out why my espresso machine keeps leaking.",
        turn=1,
    )
    assert pipe.turn.transition == Transition.NEW
    assert pipe.turn.answer is not None
    assert any("leaking" in i.text for i in store.asserted(pipe.turn.task_id))
    # Generate snapshot should exist after complete_answer
    assert pipe.turn.l1_expose is not None
    assert "leaking" in pipe.turn.l1_expose.lower()
