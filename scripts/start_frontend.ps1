# Start the React dashboard (dev server on http://localhost:5173)
# Usage: .\scripts\start_frontend.ps1
# NOTE: start the backend first (scripts\start_backend.ps1)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\frontend")

Write-Host "==> EarthScape Climate Agency - Frontend" -ForegroundColor Cyan

if (-not (Test-Path "node_modules")) {
    Write-Host "==> Installing npm dependencies (first run)..." -ForegroundColor Yellow
    # npm.ps1 may be blocked by execution policy -> use npm.cmd
    cmd /c "npm install --no-fund --no-audit"
}

Write-Host "==> Starting Vite dev server on http://localhost:5173" -ForegroundColor Green
cmd /c "npm run dev"
