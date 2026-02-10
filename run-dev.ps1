# Dev helper: open two PowerShell windows to run backend and frontend
# Usage: right-click and Run with PowerShell or execute from PowerShell: .\run-dev.ps1

$shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

Write-Host "Starting backend in new PowerShell window..."
Start-Process -FilePath $shell -ArgumentList '-NoExit','-Command', "Set-Location -Path '$backend'; if (Test-Path requirements.txt) { Write-Host 'Installing Python requirements (if needed)...'; python -m pip install -r requirements.txt } ; uvicorn main:app --reload --host 0.0.0.0 --port 8000"

Write-Host "Starting frontend in new PowerShell window..."
Start-Process -FilePath $shell -ArgumentList '-NoExit','-Command', "Set-Location -Path '$frontend'; if (-not (Test-Path node_modules)) { Write-Host 'Installing npm dependencies (if needed)...'; npm install } ; npm start"

Write-Host "Launched backend and frontend in separate windows. Close those windows to stop them."
