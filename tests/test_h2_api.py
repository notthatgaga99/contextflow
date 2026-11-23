"""HTTP H2: rollup → archive → catalog → match → import (opt-in, paused).

Never auto-merge; catalog never lands in L1/generate without bind.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.memory.catalog import ConversationCatalog
from app.models.memory import MemoryPatch
from tests.conftest import make_task

pytestmark = [pytest.mark.integration, pytest.mark.h2]


@pytest.fixture()
def h2_client(monkeypatch):
    from app.api import main as api_main

    cat = ConversationCatalog(max_entries=5, persist=False)
    monkeypatch.setattr(api_main, "catalog", cat)
    monkeypatch.setattr(api_main, "CATALOG_BACKEND", "file")
    return TestClient(api_main.app), api_main, cat


def _seed_chat(api_main, cid: str) -> None:
    eng = api_main.store.engine(cid)
    eng.reg.add(make_task("B", "outfit", "corporate outfit", ["choose color"], ["outfit", "navy"]))
    eng.reg.add(make_task("C", "travel", "plan trip", ["book hotel"], ["travel", "lisbon"]))
    eng.reg.mark_active("C", 3)
    api_main.store.writer(cid).commit(
        [
            MemoryPatch(
                kind="decision", text="navy", source_turn=2,
                workstream_id="B", slot="color",
            ),
            MemoryPatch(
                kind="fact", text="Lisbon hotel", source_turn=3, workstream_id="C",
            ),
        ],
        turn=3,
    )


def test_http_archive_list_match_import_paused(h2_client):
    client, api_main, cat = h2_client
    src = "h2-src-1"
    dst = "h2-dst-1"
    _seed_chat(api_main, src)

    r = client.get(f"/conversations/{src}/rollup")
    assert r.status_code == 200
    assert r.json()["open_count"] == 2

    r = client.post(f"/conversations/{src}/archive?user_key=u1")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["entry"]["conversation_id"] == src

    r = client.get("/catalog?user_key=u1")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["conversations"][0]["conversation_id"] == src
    assert "catalog_backend" in body

    r = client.get("/catalog/match", params={"q": "navy outfit", "user_key": "u1"})
    assert r.status_code == 200
    matches = r.json()["matches"]
    assert matches
    assert matches[0]["conversation_id"] == src

    r = client.post(
        f"/conversations/{dst}/import-rollup",
        json={
            "source_conversation_id": src,
            "user_key": "u1",
            "workstream_ids": ["B"],
            "turn": 0,
        },
    )
    assert r.status_code == 200
    imported = r.json()["imported"]
    assert len(imported) == 1
    new_id = imported[0]["new_workstream_id"]
    assert new_id != "B"

    eng = api_main.store.engine(dst)
    task = eng.reg.get(new_id)
    assert task is not None
    assert task.status == "paused"

    # Without bind SELECT, bind_and_expose must not ACT on paused-only import.
    r = client.post(
        "/bind",
        json={"conversation_id": dst, "message": "hello", "turn": 1},
    )
    assert r.status_code == 200
    bound = r.json()
    # Catalog match payload never appears as l1 package from catalog alone.
    assert bound.get("l1_expose") is None or "catalog" not in str(bound.get("l1_expose")).lower()
    assert cat.get(src, user_key="u1") is not None


def test_catalog_match_never_auto_imports(h2_client):
    client, api_main, _cat = h2_client
    src = "h2-src-match"
    _seed_chat(api_main, src)
    client.post(f"/conversations/{src}/archive?user_key=local")
    before = len(api_main.store.engine("fresh-x").reg.open_tasks())
    r = client.get("/catalog/match", params={"q": "lisbon travel"})
    assert r.status_code == 200
    assert r.json()["count"] >= 1
    after = len(api_main.store.engine("fresh-x").reg.open_tasks())
    assert after == before
