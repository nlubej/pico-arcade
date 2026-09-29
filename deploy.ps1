# Copy the game onto the Pico and restart it.
#   .\deploy.ps1              auto-detect the board
#   .\deploy.ps1 -Port COM7   use a specific port
# Every .py file in this folder is copied, plus players.txt; mpremote skips files
# that are already up to date. Saved scores/settings on the board are left alone.
param([string]$Port = "auto")

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$files = @(Get-ChildItem -File -Filter *.py | ForEach-Object { $_.Name }) + "players.txt"

py -m mpremote connect $Port fs cp @files : + reset
if ($LASTEXITCODE -ne 0) {
    Write-Host "Deploy failed. If the port is busy, disconnect MicroPico in VS Code and try again." -ForegroundColor Red
    exit $LASTEXITCODE
}
