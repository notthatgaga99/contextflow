"""One-window product demo reliability. Mock only. Frozen routing. No GCP."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from eval.product_demo.build import OUT, UI, build, public_demo_payload
from eval.product_demo.scenario import (
    DEMO_BOUNDARY,
    DEMO_LABEL,
    EXPECTED_BEAT_LABELS,
    MESSAGE_OVERRIDES,
    NARRATIVE,
    REVIEWER_SENTENCE,
    THESIS,
)
from eval.ten_workstream.load import load_fixture
from eval.ten_workstream.run import make_registry

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
DEMO_ROOT = Path(__file__).resolve().parents[1] / "eval" / "product_demo"
CHECKPOINT = "8cc553983b45702ff16c071678f9bdc5b9d26fe3"


def test_deterministic_replay_identical_semantic_state():
    a = build()
    b = build()
    assert a["demo_ok"] is True
    assert a["semantic_fingerprint"] == b["semantic_fingerprint"]
    assert [f["turn"] for f in a["frames"]] == [f["turn"] for f in b["frames"]]
    assert [f["transition"] for f in a["frames"]] == [f["transition"] for f in b["frames"]]
    assert [f["message"] for f in a["frames"]] == [f["message"] for f in b["frames"]]


def test_exact_fifteen_beat_order():
    p = build()
    assert len(p["frames"]) == 15
    assert len(EXPECTED_BEAT_LABELS) == 15
    assert [f["turn"] for f in p["frames"]] == [n["turn"] for n in NARRATIVE]
    assert [c["label"] for c in p["canonical_sequence"]] == EXPECTED_BEAT_LABELS
    caps = [f["caption"].lower() for f in p["frames"]]
    assert "dinner" in caps[3]
    assert "docker" in caps[4]
    assert "lisbon" in caps[5]
    assert "checkout" in caps[6]


def test_canonical_hero_and_clarify_beats():
    p = build()
    assert p["thesis"] == THESIS
    assert p["reviewer_sentence"] == REVIEWER_SENTENCE
    assert p["demo_label"] == DEMO_LABEL
    assert p["demo_boundary"] == DEMO_BOUNDARY
    assert p["demo_ok"] is True and p["demo_error"] is None
    hero = next(f for f in p["frames"] if f.get("hero") or f["beat"] == "return")
    assert hero["message"] == MESSAGE_OVERRIDES[38]
    assert "outfit" in hero["message"].lower()
    assert hero["transition"] == "RETURN"
    assert hero["task_id"] == "E"
    assert hero["working"]
    blob = " ".join(
        hero["working"]["included"]["decisions"]
        + hero["working"]["included"]["constraints"]
    ).lower()
    assert "navy" in blob
    assert "formal" in blob or "evening" in blob or "corporate" in blob
    excl = " ".join(e["workstream"].lower() for e in hero["working"]["excluded"])
    for needle in ("authentication", "deployment", "lisbon", "trivia", "orders"):
        assert needle in excl
    life = hero["lifecycle"]
    assert any(s["text"] == "black" for s in life["superseded"])
    assert "navy" in life["current"]
    clarify = next(f for f in p["frames"] if f["beat"] == "clarify")
    assert clarify["transition"] == "CLARIFY"
    assert "maybe" in clarify["message"].lower()
    assert clarify["product_route"] == "NEEDS CLARIFICATION"


def test_switching_does_not_leak_unrelated_into_outfit_context():
    p = build()
    hero = next(f for f in p["frames"] if f["beat"] == "return")
    pack = " ".join(
        hero["working"]["included"]["decisions"]
        + hero["working"]["included"]["constraints"]
        + hero["working"]["included"]["facts"]
    ).lower()
    assert "parking" not in pack
    assert "celesteela" not in pack
    assert "401" not in pack
    excl_titles = " ".join(e["workstream"].lower() for e in hero["working"]["excluded"])
    assert "lisbon" in excl_titles
    assert "deployment" in excl_titles or "orders" in excl_titles


def test_superseded_inspectable_but_excluded_from_current():
    p = build()
    hero = next(f for f in p["frames"] if f["beat"] == "return")
    assert "black" not in " ".join(hero["working"]["included"]["decisions"]).lower()
    assert any(s["text"] == "black" for s in hero["lifecycle"]["superseded"])
    hist = next(i for i in hero["inspector"] if i["id"] == "E")
    assert any("black" in h.lower() for h in hist["history_lines"])


def test_uncertain_does_not_enter_current_context():
    p = build()
    clarify = next(f for f in p["frames"] if f["beat"] == "clarify")
    if clarify.get("working"):
        blob = " ".join(
            clarify["working"]["included"]["decisions"]
            + clarify["working"]["included"]["facts"]
        ).lower()
        assert "maybe" not in blob


def test_generate_cannot_mutate_memory_flag():
    p = build()
    assert all(f.get("generate_did_not_mutate_memory") for f in p["frames"])


def test_conversation_isolation_remains_intact():
    fx = load_fixture()
    a = InMemoryMemoryStore(conversation_id="demo-iso-a")
    b = InMemoryMemoryStore(conversation_id="demo-iso-b")
    ra, rb = make_registry(fx), make_registry(fx)
    MemoryWriter(a, ra).commit([
        MemoryPatch(kind="fact", text="secret-a", source_turn=1, workstream_id="A",
                    conversation_id="demo-iso-a"),
    ], turn=1)
    MemoryWriter(b, rb).commit([
        MemoryPatch(kind="decision", text="navy-b", source_turn=1, workstream_id="E",
                    conversation_id="demo-iso-b", slot="color"),
    ], turn=1)
    assert all("navy" not in (i.text or "") for i in a.all())
    assert all("secret-a" not in (i.text or "") for i in b.all())


def test_reset_clears_to_first_beat_semantics():
    p1 = build()
    first = p1["frames"][0]
    p2 = build()
    assert p2["frames"][0]["turn"] == first["turn"]
    assert p2["semantic_fingerprint"] == p1["semantic_fingerprint"]


def test_ten_workstreams_present_and_narrative_covers_domains():
    p = build()
    assert len(p["workstream_titles"]) == 10
    titles = " ".join(p["workstream_titles"]).lower()
    for needle in ("auth", "deploy", "order", "checkout", "outfit", "lisbon",
                   "dinner", "presentation", "job", "trivia"):
        assert needle in titles
    beats = {n["beat"] for n in NARRATIVE}
    assert {"open", "switch", "correct", "deictic", "return", "clarify"} <= beats


def test_no_eval_gold_in_app_runtime():
    offenders = []
    for path in APP_ROOT.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("eval"):
                offenders.append(f"{path.name}:{node.module}")
        if "probes.json" in src or "gold_policy" in src and "demo_smoke" not in path.name:
            if "from eval" in src or "import eval" in src:
                offenders.append(str(path))
    assert offenders == []


def test_routing_files_byte_identical_to_checkpoint():
    root = Path(__file__).resolve().parents[1]
    files = [
        "app/router/gate.py",
        "app/router/referent.py",
        "app/retrieval/scorer.py",
        "app/config.py",
    ]
    for rel in files:
        r = subprocess.run(
            ["git", "diff", "--quiet", CHECKPOINT, "--", rel],
            cwd=root, check=False,
        )
        assert r.returncode == 0, f"{rel} changed vs {CHECKPOINT}"


def test_demo_has_no_gcp_or_vertex_dependency():
    """Local product demo must not require Cloud / credentials / network SDKs."""
    for path in (DEMO_ROOT / "build.py", DEMO_ROOT / "scenario.py", DEMO_ROOT / "__main__.py"):
        src = path.read_text(encoding="utf-8")
        assert "from google" not in src
        assert "import google" not in src
        assert "GEMINI_API_KEY" not in src
        assert "FirestoreMemoryStore" not in src
        assert "gcloud" not in src
    ui = UI.read_text(encoding="utf-8").lower()
    assert "fonts.googleapis.com" not in ui
    assert "fonts.gstatic.com" not in ui


def test_ui_surfaces_demo_error_and_hero_sections():
    ui = UI.read_text(encoding="utf-8")
    assert "DEMO ERROR" in ui
    assert "CURRENT" in ui and "HISTORY" in ui and "EXCLUDED" in ui
    assert "NEEDS CLARIFICATION" in ui
    assert "RESET DEMO" in ui and "PLAY SCENARIO" in ui and "STEP" in ui
    assert REVIEWER_SENTENCE in ui
    assert DEMO_LABEL in ui
    assert DEMO_BOUNDARY in ui
    assert "hero-banner" in ui or "HERO" in ui
    assert "gold" not in ui.lower()
    assert "benchmark score" not in ui.lower()
    assert "probe" not in ui.lower()


def test_build_writes_artifact_with_honest_boundary():
    p = build()
    assert OUT.exists()
    hb = p["honest_boundary"]
    assert hb["vertex"] is False
    assert hb["gcp"] is False
    assert hb["network"] is False
    assert hb["production_ready"] is False


def test_public_payload_omits_evaluator_internals():
    p = build()
    pub = public_demo_payload(p)
    assert "canonical_sequence" not in pub
    assert "semantic_fingerprint" not in pub
    assert "narrative_note" not in pub
    assert pub["reviewer_sentence"] == REVIEWER_SENTENCE
    hero = next(f for f in pub["frames"] if f.get("hero"))
    assert "generate_did_not_mutate_memory" not in hero
    assert "referent" not in (hero.get("evidence") or {})
    ws0 = hero["workstreams"][0]
    assert "id" not in ws0


def _focus_history(hero: dict) -> list[str]:
    focus = next(
        (i for i in hero.get("inspector") or [] if i.get("id") == hero.get("focus_workstream_id")),
        None,
    )
    return list((focus or {}).get("history_lines") or [])


def test_served_http_path_hero_and_clarify():
    """Exercise the real FastAPI serve path (HTML + /api/demo), not only build()."""
    from eval.product_demo.__main__ import create_app

    payload = build()
    assert payload["demo_ok"] is True
    client = TestClient(create_app(payload))

    health = client.get("/health")
    assert health.status_code == 200
    h = health.json()
    assert h["network"] is False and h["vertex"] is False and h["gcp"] is False
    assert h["natural_chat_benchmark"] is False
    assert DEMO_LABEL in h["label"]

    home = client.get("/")
    assert home.status_code == 200
    html = home.text
    assert "RESET DEMO" in html and "PLAY SCENARIO" in html and "STEP" in html
    assert REVIEWER_SENTENCE in html
    assert DEMO_LABEL in html
    assert DEMO_BOUNDARY in html
    assert "fonts.googleapis.com" not in html

    api = client.get("/api/demo")
    assert api.status_code == 200
    data = api.json()
    assert data["demo_ok"] is True
    assert "canonical_sequence" not in data
    assert data["reviewer_sentence"] == REVIEWER_SENTENCE

    hero = next(f for f in data["frames"] if f.get("hero") or f["beat"] == "return")
    assert hero["message"] == "Okay, back to the outfit."
    assert hero["transition"] == "RETURN"
    decisions = " ".join(hero["working"]["included"]["decisions"]).lower()
    assert "navy" in decisions
    assert "black" not in decisions
    hist = " ".join(
        _focus_history(hero)
        + [s.get("text", "") for s in (hero.get("lifecycle") or {}).get("superseded") or []]
    ).lower()
    assert "black" in hist
    excl = " ".join(e["workstream"].lower() for e in hero["working"]["excluded"])
    assert "lisbon" in excl or "authentication" in excl

    clarify = next(f for f in data["frames"] if f["beat"] == "clarify")
    assert "maybe" in clarify["message"].lower()
    assert clarify["transition"] == "CLARIFY"
    assert clarify["product_route"] == "NEEDS CLARIFICATION"
