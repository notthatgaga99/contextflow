# Switch-mastery bar: trust suite + discrimination casefile.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "== pytest -m trust ==" -ForegroundColor Cyan
python -m pytest -m trust -q --tb=line
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "== discrimination casefile ==" -ForegroundColor Cyan
python -m eval.discrimination.run_cases --json eval/out/discrimination_cases.json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "== slot/entity I-channel insights ==" -ForegroundColor Cyan
python -m eval.discrimination.insights
exit $LASTEXITCODE
