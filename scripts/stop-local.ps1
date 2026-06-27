$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$RuntimeDir = Join-Path $Root ".runtime"
$PidDir = Join-Path $RuntimeDir "pids"

function Write-Step {
    param([string]$Message)
    Write-Host "[MPU] $Message"
}

if (-not (Test-Path $PidDir)) {
    Write-Step "No running services found."
    exit 0
}

$pidFiles = Get-ChildItem -Path $PidDir -Filter "*.pid" -ErrorAction SilentlyContinue
if (-not $pidFiles) {
    Write-Step "No running services found."
    exit 0
}

foreach ($pidFile in $pidFiles) {
    $name = [System.IO.Path]::GetFileNameWithoutExtension($pidFile.Name)
    $rawPid = Get-Content $pidFile.FullName -Raw
    $processId = 0

    if (-not [int]::TryParse($rawPid.Trim(), [ref]$processId)) {
        Remove-Item $pidFile.FullName -Force -ErrorAction SilentlyContinue
        continue
    }

    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        Write-Step "Stopping $name"
        Stop-Process -Id $processId -Force
    } else {
        Write-Step "$name was not running"
    }

    Remove-Item $pidFile.FullName -Force -ErrorAction SilentlyContinue
}

Write-Step "Stopped Mordhau Prediction Unit."

