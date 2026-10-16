# Start the EarthScape Flask API (backend on http://127.0.0.1:5000)
# Usage: .\scripts\start_backend.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "==> EarthScape Climate Agency - Backend" -ForegroundColor Cyan

# Generate test data + ingest only when storage is empty (first run)
if (-not (Test-Path "data\hdfs_sim\climate")) {
    Write-Host "==> First run: generating test data..." -ForegroundColor Yellow
    python -m src.ingestion.generate_test_data
    Write-Host "==> Ingesting into HDFS-partitioned storage..." -ForegroundColor Yellow
    python -m src.ingestion.pipeline
}

Write-Host "==> Starting API on http://127.0.0.1:5000 (Ctrl+C to stop)" -ForegroundColor Green
$env:EARTHSCAPE_DEBUG = "1"
python -m src.api.app
