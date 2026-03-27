param(
  [string]$VenvDir = "venv311",
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$venvPath = Join-Path $PSScriptRoot "..\$VenvDir"
$uvicorn = Join-Path $venvPath "Scripts\uvicorn.exe"
if (-Not (Test-Path $uvicorn)) {
  throw "uvicorn not found at $uvicorn. Run scripts/setup_py311.ps1 first."
}

Push-Location (Join-Path $PSScriptRoot "..")
try {
  & $uvicorn app.main:app --reload --port $Port
} finally {
  Pop-Location
}

