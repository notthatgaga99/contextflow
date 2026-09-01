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
    {"turn": 1, "beat": "open", "caption": "Authentication thread opens"},
    {"turn": 3, "beat": "open", "caption": "Outfit thread opens (black)"},
    {"turn": 5, "beat": "switch", "caption": "Orders API — similar 401 vocabulary"},
    {"turn": 8, "beat": "switch", "caption": "Dinner / food"},
    {"turn": 10, "beat": "switch", "caption": "Docker / CI"},
    {"turn": 11, "beat": "switch", "caption": "Lisbon travel"},
    {"turn": 14, "beat": "switch", "caption": "Checkout frontend — another 401"},
    {"turn": 17, "beat": "switch", "caption": "Presentation deck"},
    {"turn": 20, "beat": "switch", "caption": "Trivia distraction"},
    {"turn": 28, "beat": "switch", "caption": "Stripe application deadline"},
    {"turn": 32, "beat": "correct", "caption": "Correction: black → navy (history kept)"},
    {"turn": 35, "beat": "distract", "caption": "Leave the outfit again"},
    {"turn": 37, "beat": "deictic", "caption": "Deictic “fix that”"},
    {
        "turn": 38, "beat": "return", "hero": True,
        "caption": "RETURNING TO outfit — reconstruct working context",
    },
    {"turn": 46, "beat": "clarify", "caption": "NEEDS CLARIFICATION — refuse to guess"},
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
