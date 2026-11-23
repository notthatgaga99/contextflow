# Snappy local UI — MockLLM, no Vertex pace. Usage (from contextflow/):
#   . .\scripts\env_mock_local.ps1
#   python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8080

$ErrorActionPreference = "Stop"
$env:CF_LLM_MODE = "mock"
$env:CF_USE_VERTEX = "0"
$env:CF_USE_GEMINI = "0"
$env:CF_USE_OLLAMA = "0"
$env:CF_LLM_EXTRACT = "0"
$env:CF_TOPIC_LLM = "0"
$env:CF_VERTEX_MIN_INTERVAL_S = "0"
$env:CF_DEMO_ONLY = "0"
$env:CF_SMOKE_FIXTURE = "0"
$env:CF_COLD_ENRICH = "0"
Write-Host "Mock env ready: llm_mode=mock pace=0s (no Vertex)"
