"""FirestoreConversationCatalog via FakeFirestore — durable last-N, user isolation."""

from __future__ import annotations

import pytest

from app.memory.fake_firestore import FakeFirestoreClient
from app.memory.firestore_catalog import FirestoreConversationCatalog

pytestmark = [pytest.mark.integration, pytest.mark.h2]


def test_firestore_catalog_persists_across_instances():
    client = FakeFirestoreClient()
    a = FirestoreConversationCatalog(max_entries=5, client=client)
    a.upsert_rollup(
        {
            "conversation_id": "chat-1",
            "blurb": "JWT auth + orders",
            "open_count": 2,
            "workstreams": [
                {"title": "JWT auth", "goal": "fix refresh", "facts": ["ttl=15m"]},
            ],
        },
        user_key="u1",
        updated_at=10.0,
    )
    # Simulate process drop: new catalog object, same FakeFirestore.
    b = FirestoreConversationCatalog(max_entries=5, client=client)
    got = b.get("chat-1", user_key="u1")
    assert got is not None
    assert got.blurb.startswith("JWT")
    assert len(b.list(user_key="u1")) == 1


def test_firestore_catalog_trims_last_n_and_isolates_users():
    client = FakeFirestoreClient()
    cat = FirestoreConversationCatalog(max_entries=2, client=client)
    for i in range(4):
        cat.upsert_rollup(
            {
                "conversation_id": f"c{i}",
                "blurb": f"chat {i}",
                "open_count": 1,
                "workstreams": [],
            },
            user_key="alice",
            updated_at=float(i),
        )
    listed = cat.list(user_key="alice")
    assert [e.conversation_id for e in listed] == ["c3", "c2"]
    assert cat.get("c0", user_key="alice") is None

    cat.upsert_rollup(
        {
            "conversation_id": "other",
            "blurb": "bob only",
            "open_count": 1,
            "workstreams": [],
        },
        user_key="bob",
        updated_at=99.0,
    )
    assert cat.get("other", user_key="alice") is None
    assert cat.get("other", user_key="bob") is not None
    assert cat.get("c3", user_key="bob") is None


def test_firestore_catalog_match_suggests_without_import():
    client = FakeFirestoreClient()
    cat = FirestoreConversationCatalog(max_entries=5, client=client)
    cat.upsert_rollup(
        {
            "conversation_id": "azure-ci",
            "blurb": "Azure pipeline + peplum",
            "open_count": 1,
            "workstreams": [
                {"title": "Azure CI", "goal": "fix pipeline", "facts": ["exit 4"]},
            ],
        },
        user_key="local",
        updated_at=1.0,
    )
    cat.upsert_rollup(
        {
            "conversation_id": "travel",
            "blurb": "Lisbon trip",
            "open_count": 1,
            "workstreams": [{"title": "travel", "goal": "book hotel"}],
        },
        user_key="local",
        updated_at=2.0,
    )
    hits = cat.match("azure pipeline exit", user_key="local", limit=2)
    assert hits
    assert hits[0][0].conversation_id == "azure-ci"
    assert hits[0][1] > 0
