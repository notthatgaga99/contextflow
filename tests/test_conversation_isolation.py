"""Process-local conversation_id isolation. Not a realistic dialogue substrate."""

from fastapi.testclient import TestClient

from app.api.main import app, store


def setup_function():
    store.reset()


def test_health_and_correlation_id():
    c = TestClient(app)
    r = c.get("/health", headers={"x-request-id": "corr-1"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.headers.get("x-request-id") == "corr-1"


def test_empty_conversation_id_rejected():
    c = TestClient(app)
    r = c.post("/turn", json={"conversation_id": "  ", "message": "hello", "turn": 1})
    assert r.status_code == 400


def test_two_conversations_do_not_share_registry():
    c = TestClient(app)
    a1 = c.post("/turn", json={
        "conversation_id": "conv-a",
        "message": "jwt still returns 401 after refresh",
        "turn": 1,
    })
    b1 = c.post("/turn", json={
        "conversation_id": "conv-b",
        "message": "need a dress for a rooftop venue with harsh lighting",
        "turn": 1,
    })
    assert a1.status_code == 200
    assert b1.status_code == 200
    ta = c.get("/conversations/conv-a/tasks").json()["tasks"]
    tb = c.get("/conversations/conv-b/tasks").json()["tasks"]
    a_blob = " ".join(t.get("goal", "") + " ".join(t.get("open_loops") or []) for t in ta).lower()
    b_blob = " ".join(t.get("goal", "") + " ".join(t.get("open_loops") or []) for t in tb).lower()
    assert "401" in a_blob or "jwt" in a_blob
    assert "dress" in b_blob or "rooftop" in b_blob or "lighting" in b_blob
    assert "401" not in b_blob and "jwt" not in b_blob
    assert "dress" not in a_blob and "rooftop" not in a_blob


def test_task_ids_are_local_to_conversation():
    c = TestClient(app)
    c.post("/turn", json={"conversation_id": "conv-a", "message": "jwt still returns 401", "turn": 1})
    c.post("/turn", json={"conversation_id": "conv-b", "message": "need a dress for rooftop lighting", "turn": 1})
    a = c.get("/task/T1", params={"conversation_id": "conv-a"}).json()
    b = c.get("/task/T1", params={"conversation_id": "conv-b"}).json()
    assert "error" not in a
    assert "error" not in b
    assert "401" in (a.get("anchor") or {}).get("goal", "").lower() or "jwt" in (a.get("anchor") or {}).get("goal", "").lower()
    assert "dress" in (b.get("anchor") or {}).get("goal", "").lower() or "rooftop" in (b.get("anchor") or {}).get("goal", "").lower()
    assert a["anchor"]["goal"] != b["anchor"]["goal"]


def test_memory_endpoint_is_per_conversation():
    c = TestClient(app)
    c.post("/turn", json={"conversation_id": "conv-a", "message": "jwt still returns 401", "turn": 1})
    c.post("/turn", json={"conversation_id": "conv-b", "message": "need a dress for rooftop lighting", "turn": 1})
    a = c.get("/conversations/conv-a/memory").json()
    b = c.get("/conversations/conv-b/memory").json()
    assert a["conversation_id"] == "conv-a"
    assert b["conversation_id"] == "conv-b"
    assert a["items"] == [] or all(i.get("conversation_id") in (None, "conv-a") for i in a["items"])

