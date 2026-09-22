# PC Parts Desk — Windows PowerShell launcher
# Usage: right-click → Run with PowerShell, or:
#   powershell -ExecutionPolicy Bypass -File .\start.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Ensure-Command($Name, $Hint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Error "$Name not found. $Hint"
    }
}

Ensure-Command "python" "Install Python 3.11+ from https://www.python.org and tick 'Add to PATH'."
Ensure-Command "npm" "Install Node.js 20+ from https://nodejs.org"

$VenvPython = Join-Path $Root "backend\.venv\Scripts\python.exe"
$VenvUvicorn = Join-Path $Root "backend\.venv\Scripts\uvicorn.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating Python venv…"
    python -m venv (Join-Path $Root "backend\.venv")
    & $VenvPython -m pip install -r (Join-Path $Root "backend\requirements.txt")
}

if (-not (Test-Path (Join-Path $Root "frontend\node_modules"))) {
    Write-Host "Installing frontend dependencies…"
    Push-Location (Join-Path $Root "frontend")
    npm install
    Pop-Location
}

$EnvFile = Join-Path $Root ".env"
$EnvExample = Join-Path $Root ".env.example"
if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
    Copy-Item $EnvExample $EnvFile
    Write-Host "Created .env from .env.example — edit OLLAMA_URL if needed."
}

$env:PYTHONPATH = (Join-Path $Root "backend")

Write-Host "Starting API on http://127.0.0.1:8765 …"
$Backend = Start-Process -FilePath $VenvUvicorn -ArgumentList @(
    "app.main:app",
    "--app-dir", (Join-Path $Root "backend"),
    "--host", "127.0.0.1",
    "--port", "8765"
) -PassThru -NoNewWindow -WorkingDirectory $Root

Write-Host "Starting UI on http://127.0.0.1:5173 …"
Push-Location (Join-Path $Root "frontend")
try {
    npm run dev -- --host 127.0.0.1 --port 5173
}
finally {
    Pop-Location
    if ($Backend -and -not $Backend.HasExited) {
        Stop-Process -Id $Backend.Id -Force -ErrorAction SilentlyContinue
    }
}
