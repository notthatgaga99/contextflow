from app.llm.ollama import parse_proposal_content, safe_proposal


def test_malformed_json_does_not_guess_task():
    p = parse_proposal_content("not json at all")
    assert p["task_id"] is None
    assert p["is_new_task"] is False
    assert p["confidence"] == 0.0
    assert p["rationale"].startswith("invalid_provider_output")


def test_empty_content_is_safe():
    p = parse_proposal_content("")
    assert p == safe_proposal("empty_content")


def test_valid_json_passthrough():
    p = parse_proposal_content(
        '{"task_id": "A", "is_new_task": false, "confidence": 0.7, "referent": null, "rationale": "auth"}'
    )
    assert p["task_id"] == "A" and p["is_new_task"] is False
    assert p["confidence"] == 0.7


def test_fenced_json():
    p = parse_proposal_content('```json\n{"task_id": "B", "is_new_task": false, "confidence": 0.4}\n```')
    assert p["task_id"] == "B"


def test_importing_ollama_adapter_does_not_need_daemon():
    from app.llm.ollama import OllamaLLM
    llm = OllamaLLM(base_url="http://127.0.0.1:9", model="unused")
    p = llm.propose("MESSAGE: \"hi\"", {"type": "object"})
    assert p["task_id"] is None and p["confidence"] == 0.0
