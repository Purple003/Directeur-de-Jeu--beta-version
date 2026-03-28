param(
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

Push-Location (Join-Path $PSScriptRoot "..")
try {
  # Works even if uvicorn.exe is not on PATH.
  python -m uvicorn main:app --reload --port $Port
} finally {
  Pop-Location
}

