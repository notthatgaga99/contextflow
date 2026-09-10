"""Canonical one-window product-demo scenario.

CONTROLLED ADVERSARIAL ENGINEERING FIXTURE — product story on the ten-workstream
substrate. Not organic chat. Not a benchmark. Does not change frozen routing.
"""

from __future__ import annotations

# Soft MockLLM proposals for product-authored utterances (not ACT/CLARIFY decisions).
PRODUCT_LLM_EXTRA = {
    "back to the outfit": {"task_id": "E", "is_new_task": False, "confidence": 0.4},
    "Okay, back to the outfit": {"task_id": "E", "is_new_task": False, "confidence": 0.4},
}

# Fixture turn → product-facing display/routing message when the pitch needs
# exact wording. Underlying workstream cards/scripts remain the ten-ws fixture.
MESSAGE_OVERRIDES = {
    38: "Okay, back to the outfit.",
}

# Ordered ~60–120s one-window pitch. User never types a task id.
# Beat order matches docs/PRODUCT_DEMO.md (captions must match fixture turns).
NARRATIVE = [
    {
        "turn": 1, "beat": "open",
        "caption": "1) Start a tech problem — auth still returns 401",
    },
    {
        "turn": 3, "beat": "open",
        "caption": "2) New thread — outfit (we assume black for now)",
    },
    {
        "turn": 5, "beat": "switch",
        "caption": "3) Another tech 401 — easy to mix with auth",
    },
    {"turn": 8, "beat": "switch", "caption": "4) Life interrupt — dinner plans"},
    {"turn": 10, "beat": "switch", "caption": "5) Back to tech — Docker / CI"},
    {"turn": 11, "beat": "switch", "caption": "6) Life interrupt — Lisbon trip"},
    {
        "turn": 14, "beat": "switch",
        "caption": "7) Third 401 thread — checkout frontend",
    },
    {"turn": 17, "beat": "switch", "caption": "8) Work interrupt — presentation deck"},
    {"turn": 20, "beat": "switch", "caption": "9) Noise — trivia (should stay out of real work)"},
    {"turn": 28, "beat": "switch", "caption": "10) Deadline interrupt — Stripe / job"},
    {
        "turn": 32, "beat": "correct",
        "caption": "11) We were wrong — not black, NAVY (keep black as history)",
    },
    {"turn": 35, "beat": "distract", "caption": "12) Leave the outfit again — more switching"},
    {
        "turn": 37, "beat": "deictic",
        "caption": "13) Vague: “fix that” — which unfinished thread?",
    },
    {
        "turn": 38, "beat": "return", "hero": True,
        "caption": "14) HERO: back to outfit → CURRENT navy · HISTORY black · EXCLUDE the rest",
    },
    {
        "turn": 46, "beat": "clarify",
        "caption": "15) “Maybe the navy one?” → ask, don’t guess",
    },
]

# Human-readable expected pitch order (for tests / docs alignment).
EXPECTED_BEAT_LABELS = [
    "Auth",
    "Outfit black",
    "Orders",
    "Dinner",
    "Docker/CI",
    "Lisbon",
    "Checkout",
    "Deck",
    "Trivia",
    "Stripe/job",
    "Black→navy",
    "Leave outfit",
    "fix that",
    "Okay, back to the outfit.",
    "Maybe the navy one? → NEEDS CLARIFICATION",
]

THESIS = "ContextFlow lets you leave a thought without losing it."

# First-screen one-sentence explanation for human reviewers (exact wording).
REVIEWER_SENTENCE = (
    "ContextFlow keeps multiple unfinished workstreams alive and "
    "reconstructs the right working context when you return."
)

TAGLINE = REVIEWER_SENTENCE

DEMO_LABEL = "CONTROLLED SYNTHETIC ENGINEERING DEMO"
DEMO_BOUNDARY = "NOT A NATURAL-CHAT BENCHMARK"
