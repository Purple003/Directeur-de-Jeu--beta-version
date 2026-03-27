param(
    [string]$VenvPath = ".venv310"
)

$ErrorActionPreference = "Stop"

Write-Host "== DeepFace setup (Python 3.10) ==" -ForegroundColor Cyan

# 1) Ensure Python 3.10 exists (Windows launcher).
try {
    $pyExe = (py -3.10 -c "import sys; print(sys.executable)" 2>$null).Trim()
} catch {
    $pyExe = ""
}
if (-not $pyExe) {
    Write-Error "Python 3.10 not found. Install it first (e.g. `winget install -e --id Python.Python.3.10`) and ensure `py -3.10 -V` works."
    exit 1
}
Write-Host "Python 3.10: $pyExe"

# 2) Create venv.
if (-not (Test-Path $VenvPath)) {
    py -3.10 -m venv $VenvPath
    Write-Host "Created venv: $VenvPath"
} else {
    Write-Host "Using existing venv: $VenvPath"
}

$python = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Venv python not found at $python"
    exit 1
}

# 3) Install compatible versions (avoid source builds / resolver loops).
& $python -m pip install --upgrade pip setuptools wheel

# TensorFlow 2.14 works best with numpy<2 + protobuf<5 and Keras 2.x (avoid Keras 3 conflicts).
& $python -m pip install "numpy<2" "protobuf<5" "keras<3"

# Prefer wheels only to prevent long native builds.
& $python -m pip install --only-binary=:all: tensorflow==2.14.0
& $python -m pip install --only-binary=:all: opencv-python

# DeepFace (pure python) + optional compatibility shim used by some stacks.
& $python -m pip install deepface
& $python -m pip install tf-keras

Write-Host "== Installed versions ==" -ForegroundColor Cyan
& $python -c "import sys; print('python', sys.version)"
& $python -c "import tensorflow as tf; print('tensorflow', tf.__version__)"
& $python -c "from deepface import DeepFace; print('deepface ok')"

Write-Host ""
Write-Host "Run test:" -ForegroundColor Cyan
Write-Host "  $python scripts/test_deepface.py --webcam"

