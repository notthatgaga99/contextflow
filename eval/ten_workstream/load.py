"""Load ten-workstream fixture. Control-plane cards vs extracted content."""

from __future__ import annotations

import json
from pathlib import Path

DIR = Path(__file__).resolve().parent
FIXTURE_PATH = DIR / "fixture.json"
PROBES_PATH = DIR / "probes.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def load_probes() -> list[dict]:
    return json.loads(PROBES_PATH.read_text(encoding="utf-8"))["probes"]


def extract_scripts(fx: dict | None = None) -> dict:
    return dict((fx or load_fixture())["extract_scripts"])


def llm_scripts(fx: dict | None = None) -> dict:
    return dict((fx or load_fixture())["llm_scripts"])
