"""Security / boundary checks for the Cloud POC shape."""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from app.obs import FORBIDDEN_LOG_KEYS, decision_event, emit_decision

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def test_app_does_not_import_eval():
    offenders = []
    for path in APP.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "eval" or alias.name.startswith("eval."):
                        offenders.append(f"{path.relative_to(ROOT)}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "eval" or mod.startswith("eval."):
                    offenders.append(f"{path.relative_to(ROOT)}: from {mod}")
    assert offenders == [], "app/ must not import eval:\n" + "\n".join(offenders)


def test_no_service_account_json_in_tracked_tree():
    patterns = ("*credentials*.json", "*service-account*.json", "*-key.json")
    found = []
    for pat in patterns:
        for p in ROOT.rglob(pat):
            if any(part in {".git", ".venv", "venv", "node_modules", "__pycache__"} for part in p.parts):
                continue
            # Allow nothing that looks like a GCP key blob
            text = p.read_text(encoding="utf-8", errors="ignore")[:2000]
            if '"private_key"' in text or "BEGIN PRIVATE KEY" in text:
                found.append(str(p.relative_to(ROOT)))
    assert found == []


def test_no_private_transcript_in_tracked_data():
    """Private consented transcripts must not be committed under data/private."""
    private = ROOT / "data" / "private"
    if not private.exists():
        return
    for p in private.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".jsonl", ".txt", ".md"}:
            # Presence of private raw transcript files in git is a fail;
            # allow empty dirs / README placeholders only.
            if p.name.lower() in {"readme.md", ".gitkeep"}:
                continue
            pytest.fail(f"private transcript-like file present: {p.relative_to(ROOT)}")


def test_structured_logs_omit_raw_text_keys():
    payload = decision_event(
        correlation_id="r1",
        conversation_id="secret-conversation-id-xyz",
        turn=1,
        transition="ACT",
        task_id="B",
        referent_id="B.loop1",
        extract_ok=True,
        extract_status="ok",
        message_chars=12,
        latency_ms=1.0,
        memory_backend="firestore",
        memory_reads=2,
        memory_writes=1,
        memory_current_count=1,
        memory_history_count=0,
        package_status="ok",
        answer_status="ok",
    )
    assert "message" not in payload
    assert "prompt" not in payload
    assert "answer" not in payload
    assert "conversation_id" not in payload
    blob = str(payload)
    assert "secret-conversation" not in blob
    assert "conversation_id_hash" in payload
    assert FORBIDDEN_LOG_KEYS.isdisjoint(payload.keys())
    emit_decision(payload)


def test_durable_cloudrun_not_public_by_default():
    yaml_path = ROOT / "deploy" / "cloudrun-durable.yaml"
    text = yaml_path.read_text(encoding="utf-8")
    # Strip comments — warning text may mention the flag; config must not enable it.
    code = "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "allow-unauthenticated" not in code.lower()
    assert "allUsers" not in code
    assert "allAuthenticatedUsers" not in code
    assert "CF_MEMORY_BACKEND" in text and "firestore" in text
    assert "contextflow.dev/tier: durable-poc" in text
    demo = (ROOT / "deploy" / "cloudrun.yaml").read_text(encoding="utf-8")
    assert "demo" in demo.lower()
    assert "value: memory" in demo


def test_default_memory_backend_is_memory(monkeypatch):
    monkeypatch.delenv("CF_MEMORY_BACKEND", raising=False)
    from app.memory.factory import memory_backend
    assert memory_backend() == "memory"
