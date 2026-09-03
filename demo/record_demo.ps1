# demo/record_demo.ps1
# Records a real terminal demo using VHS + local mock LLM server.
#
# Usage (from repo root in PowerShell):
#   .\demo\record_demo.ps1
#
# Requirements:
#   - vhs.exe on PATH (https://github.com/charmbracelet/vhs)
#   - Python env with angrist + its deps installed

$ErrorActionPreference = "Stop"
$ROOT = (Get-Item $PSScriptRoot).Parent.FullName
Set-Location $ROOT

Write-Host "Starting mock LLM server on port 8765..." -ForegroundColor Cyan
$mockJob = Start-Process python -ArgumentList "demo/mock_server.py", "8765" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 2

try {
    # Quick health check
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:8765/" -TimeoutSec 2 -ErrorAction SilentlyContinue
    } catch {}

    Write-Host "Mock server PID $($mockJob.Id) is up." -ForegroundColor Green
    Write-Host "Recording demo with VHS..." -ForegroundColor Cyan

    # Add Git bin so bash is available (needed for VHS rendering)
    $env:PATH = "C:\Program Files\Git\bin;$env:PATH"

    vhs demo/demo.tape

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Demo saved to demo/demo.gif" -ForegroundColor Green
    } else {
        Write-Host "VHS exited with code $LASTEXITCODE" -ForegroundColor Red
    }
} finally {
    Write-Host "Stopping mock server..." -ForegroundColor Cyan
    Stop-Process -Id $mockJob.Id -Force -ErrorAction SilentlyContinue
}
