param(
  [string]$VenvDir = "venv311"
)

$ErrorActionPreference = "Stop"

Write-Host "Checking Python 3.11..."
py -3.11 -V | Out-Host

$venvPath = Join-Path $PSScriptRoot "..\$VenvDir"
if (-Not (Test-Path $venvPath)) {
  Write-Host "Creating venv at $venvPath"
  py -3.11 -m venv $venvPath
} else {
  Write-Host "Venv already exists at $venvPath"
}

$pip = Join-Path $venvPath "Scripts\pip.exe"
$python = Join-Path $venvPath "Scripts\python.exe"

Write-Host "Upgrading pip..."
& $python -m pip install --upgrade pip wheel setuptools | Out-Host

Write-Host "Installing dependencies..."
& $pip install -r (Join-Path $PSScriptRoot "..\requirements.txt") | Out-Host

Write-Host "Done."
Write-Host "Activate with: `"$venvPath\\Scripts\\Activate.ps1`""
Write-Host "Run API with: `"$venvPath\\Scripts\\uvicorn.exe app.main:app --reload`" from the backend/ directory"

