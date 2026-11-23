# Local Vertex recipe for ContextFlow Free Trial project (no secrets in git).
# Usage (from contextflow/):
#   . .\scripts\env_vertex_local.ps1
# Requires: .data/cf-vertex.json (gitignored SA key) created once via gcloud.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$keyPath = Join-Path $root ".data\cf-vertex.json"
if (-not (Test-Path $keyPath)) {
    Write-Error "Missing $keyPath - create SA key before sourcing."
}
$env:GOOGLE_APPLICATION_CREDENTIALS = (Resolve-Path $keyPath).Path
$env:GCP_PROJECT = "contextflow-gagan-20261019"
$env:GOOGLE_CLOUD_PROJECT = $env:GCP_PROJECT
$env:GCP_REGION = "us-central1"
$env:CF_VERTEX_LOCATION = "us-central1"
$env:CF_USE_VERTEX = "1"
$env:CF_LITE_MODEL = "gemini-2.5-flash-lite"
$env:CF_GEN_MODEL = "gemini-2.5-flash-lite"
$env:CF_EMBED_LOCAL = "1"
# Free Trial / express Gemini ~10 RPM — space generate calls (~9 RPM headroom).
$env:CF_VERTEX_MIN_INTERVAL_S = "6.5"
Write-Host ("Vertex env ready: project={0} model={1} pace={2}s" -f $env:GCP_PROJECT, $env:CF_LITE_MODEL, $env:CF_VERTEX_MIN_INTERVAL_S)
