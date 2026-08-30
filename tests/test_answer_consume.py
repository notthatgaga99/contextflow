"""Ollama consume is optional. Pytest must not wait on 9 live generates."""

import os

from eval.answer_consume import ollama_available, run


def test_answer_consume_skips_or_runs():
    if os.getenv("CF_OLLAMA_CONSUME") != "1":
        assert ollama_available() in (True, False)
        return
    payload = run()
    assert payload["status"] in ("ran", "skipped")
    if payload["status"] == "ran":
        assert len(payload["probes"]) == 3
