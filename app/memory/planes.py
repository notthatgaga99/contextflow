"""ContextFlow memory planes — our model, informed by practice (not a port of it).

Planes are *roles* MemoryManager exposes. Storage tiers (L0–L7) are *where*
items live. The frozen binder chooses the hop; planes never bypass it.

What is ours:
  SHORT_TERM  — capped L1 working set after bind (RB-WSR); only generate() surface
  LONG_TERM   — durable asserted/historical; semantic vs episodic kinds
  PROCEDURAL  — how-to items (`procedure`) + card control (goal/loops) kept apart
  RELEVANT    — query-aware cold enrich on the *bound* hop only
  INDEX       — L4 open cards for routing, never L1 body
  ARCHIVE     — L6/L7 catalog; opt-in import only

We study market systems (working vs durable vs retrieved vs skills) so we do
not repeat their mistakes. We do **not** copy their APIs, tier names as product
identity, or “agent self-edits core memory” authority. Binder stays frozen.

Hard rule: generate() may read SHORT_TERM only (plus the user message).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Iterable


class MemoryPlane(str, Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    PROCEDURAL = "procedural"
    RELEVANT = "relevant"
    INDEX = "index"
    ARCHIVE = "archive"


class LongTermKind(str, Enum):
    """Split inside LONG_TERM by item kind (same store)."""

    SEMANTIC = "semantic"   # facts, prefs, entities, decisions, constraints
    EPISODIC = "episodic"   # events / what happened when


class StorageTier(str, Enum):
    L0 = "L0"  # ephemeral turn
    L1 = "L1"  # working set → generate
    L2 = "L2"  # hop CURRENT asserted
    L3 = "L3"  # hop HISTORY
    L4 = "L4"  # open index
    L5 = "L5"  # conversation store
    L6 = "L6"  # catalog / rollup
    L7 = "L7"  # cold market / prefs


KIND_PLANE: dict[str, MemoryPlane] = {
    "fact": MemoryPlane.LONG_TERM,
    "preference": MemoryPlane.LONG_TERM,
    "entity": MemoryPlane.LONG_TERM,
    "decision": MemoryPlane.LONG_TERM,
    "correction": MemoryPlane.LONG_TERM,
    "constraint": MemoryPlane.LONG_TERM,
    "event": MemoryPlane.LONG_TERM,
    "procedure": MemoryPlane.PROCEDURAL,
}

KIND_LONG_TERM: dict[str, LongTermKind] = {
    "fact": LongTermKind.SEMANTIC,
    "preference": LongTermKind.SEMANTIC,
    "entity": LongTermKind.SEMANTIC,
    "decision": LongTermKind.SEMANTIC,
    "correction": LongTermKind.SEMANTIC,
    "constraint": LongTermKind.SEMANTIC,
    "event": LongTermKind.EPISODIC,
}

PLANE_TIERS: dict[MemoryPlane, tuple[StorageTier, ...]] = {
    MemoryPlane.SHORT_TERM: (StorageTier.L1,),
    MemoryPlane.LONG_TERM: (StorageTier.L2, StorageTier.L3, StorageTier.L5),
    MemoryPlane.PROCEDURAL: (StorageTier.L2, StorageTier.L4),
    MemoryPlane.RELEVANT: (StorageTier.L2, StorageTier.L3),
    MemoryPlane.INDEX: (StorageTier.L4,),
    MemoryPlane.ARCHIVE: (StorageTier.L6, StorageTier.L7),
}

# Optional study notes for diagnostics — not identity, not a compatibility layer.
LEARNED_FROM: dict[str, dict[str, str]] = {
    "working_vs_durable": {
        MemoryPlane.SHORT_TERM.value: "capped in-context working set (our L1 after bind)",
        MemoryPlane.LONG_TERM.value: "durable conversation store (our L2/L3/L5)",
    },
    "retrieval_vs_binding": {
        MemoryPlane.RELEVANT.value: "retrieve after hop is chosen — never as the binder",
        MemoryPlane.INDEX.value: "thin cards for routing, not content dump",
    },
    "skills_vs_facts": {
        MemoryPlane.PROCEDURAL.value: "how-to steps separate from semantic facts",
    },
    "cross_session": {
        MemoryPlane.ARCHIVE.value: "catalog/import opt-in — never auto into generate",
    },
}

PLANE_ROLES: dict[MemoryPlane, str] = {
    MemoryPlane.SHORT_TERM: "Capped working set for the answer model this turn (RB-WSR L1)",
    MemoryPlane.LONG_TERM: "Durable semantic + episodic memory for a conversation",
    MemoryPlane.PROCEDURAL: "How-to procedures; card goal/loops stay on control fields",
    MemoryPlane.RELEVANT: "Query-aware cold enrich scoped to the bound hop",
    MemoryPlane.INDEX: "Open-thread cards for binder routing (not L1 body)",
    MemoryPlane.ARCHIVE: "Cross-chat catalog — opt-in import only",
}


@dataclass(frozen=True)
class PlanePolicy:
    """Invariants the manager enforces (docs + tests)."""

    generate_reads_only: MemoryPlane = MemoryPlane.SHORT_TERM
    relevant_must_be_bound: bool = True
    archive_never_auto_merge: bool = True
    index_not_in_generate_body: bool = True
    prefer_asserted_over_superseded: bool = True
    procedural_skills_only_in_l1: bool = True


DEFAULT_PLANE_POLICY = PlanePolicy()


def plane_for_kind(kind: str) -> MemoryPlane:
    return KIND_PLANE.get((kind or "").strip().lower(), MemoryPlane.LONG_TERM)


def long_term_kind_for(kind: str) -> LongTermKind | None:
    if plane_for_kind(kind) != MemoryPlane.LONG_TERM:
        return None
    return KIND_LONG_TERM.get((kind or "").strip().lower(), LongTermKind.SEMANTIC)


def tiers_for_plane(plane: MemoryPlane) -> tuple[StorageTier, ...]:
    return PLANE_TIERS.get(plane, ())


def plane_catalog() -> list[dict[str, Any]]:
    """Stable description for docs / API diagnostics."""
    rows = []
    for plane in MemoryPlane:
        rows.append({
            "plane": plane.value,
            "storage_tiers": [t.value for t in tiers_for_plane(plane)],
            "role": PLANE_ROLES[plane],
        })
    return rows


def design_notes() -> dict[str, Any]:
    """How we learned from the field without cloning it."""
    return {
        "product": "ContextFlow — referent-bound working-set reconstruction (RB-WSR)",
        "stance": (
            "Learn patterns (working vs durable, retrieve vs bind, skills vs facts). "
            "Own the control loop: frozen binder → bound planes → L1 only."
        ),
        "learned_from": LEARNED_FROM,
        "policy": asdict(DEFAULT_PLANE_POLICY),
        "not_a_clone_of": [
            "agent-self-edited core memory as routing authority",
            "multi-thread vector top-k as the hop selector",
            "auto-merge archival/catalog into generate()",
        ],
    }


# Back-compat alias for earlier API name
def industry_alignment() -> dict[str, Any]:
    return design_notes()


def assert_generate_surface(
    planes_present: Iterable[MemoryPlane],
    policy: PlanePolicy = DEFAULT_PLANE_POLICY,
) -> None:
    """Raise if a non-STM plane is claimed as generate surface."""
    bad = [p for p in planes_present if p != policy.generate_reads_only]
    if bad:
        raise AssertionError(
            f"generate() may only read {policy.generate_reads_only.value}; "
            f"got {[p.value for p in bad]}"
        )
