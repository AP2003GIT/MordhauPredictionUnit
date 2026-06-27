param(
    [switch]$SkipInstall,
    [switch]$SkipIngest,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$RuntimeDir = Join-Path $Root ".runtime"
$LogDir = Join-Path $RuntimeDir "logs"
$PidDir = Join-Path $RuntimeDir "pids"

New-Item -ItemType Directory -Force -Path $RuntimeDir, $LogDir, $PidDir | Out-Null

function Write-Step {
    param([string]$Message)
    Write-Host "[MPU] $Message"
}

function Find-BasePython {
    $codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

    $candidates = @(
        @{ Exe = "python"; Args = @() },
        @{ Exe = "py"; Args = @("-3") },
        @{ Exe = $codexPython; Args = @() }
    )

    foreach ($candidate in $candidates) {
        if ($candidate.Exe -like "*\*" -and -not (Test-Path $candidate.Exe)) {
            continue
        }

        try {
            $version = & $candidate.Exe @($candidate.Args) --version 2>$null
            if ($LASTEXITCODE -eq 0 -and $version) {
                return $candidate
            }
        } catch {
            continue
        }
    }

    throw "Python 3.12+ was not found. Install Python and enable the PATH option, then run this launcher again."
}

function Invoke-BasePython {
    param(
        [hashtable]$Python,
        [string[]]$Arguments,
        [string]$WorkingDirectory = $Root
    )

    Push-Location $WorkingDirectory
    try {
        & $Python.Exe @($Python.Args) @Arguments 2>&1 | ForEach-Object { Write-Host $_ }
        if ($LASTEXITCODE -ne 0) {
            throw "Python command failed: $($Arguments -join ' ')"
        }
    } finally {
        Pop-Location
    }
}

function Ensure-PythonService {
    param(
        [string]$Name,
        [string]$Path,
        [hashtable]$BasePython
    )

    $venvPython = Join-Path $Path ".venv\Scripts\python.exe"
    $requirements = Join-Path $Path "requirements.txt"
    $stamp = Join-Path $Path ".venv\.requirements-installed"

    if (-not (Test-Path $venvPython)) {
        Write-Step "Creating Python environment for $Name"
        Invoke-BasePython -Python $BasePython -Arguments @("-m", "venv", ".venv") -WorkingDirectory $Path
    }

    if (-not $SkipInstall) {
        $needsInstall = -not (Test-Path $stamp)
        if (-not $needsInstall -and (Test-Path $requirements)) {
            $needsInstall = (Get-Item $requirements).LastWriteTimeUtc -gt (Get-Item $stamp).LastWriteTimeUtc
        }

        if ($needsInstall) {
            Write-Step "Installing Python dependencies for $Name"
            & $venvPython -m pip install -r $requirements 2>&1 | ForEach-Object { Write-Host $_ }
            if ($LASTEXITCODE -ne 0) {
                throw "Could not install Python dependencies for $Name."
            }
            New-Item -ItemType File -Force -Path $stamp | Out-Null
        }
    }

    return $venvPython
}

function Ensure-Dashboard {
    $dashboardPath = Join-Path $Root "apps\dashboard"
    $nodeModules = Join-Path $dashboardPath "node_modules"

    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        throw "npm was not found. Install Node.js 20+ and run this launcher again."
    }

    Push-Location $dashboardPath
    try {
        if (-not $SkipInstall -and -not (Test-Path $nodeModules)) {
            Write-Step "Installing dashboard dependencies"
            npm install
            if ($LASTEXITCODE -ne 0) {
                throw "Could not install dashboard dependencies."
            }
        }

        Write-Step "Building dashboard"
        npm run build
        if ($LASTEXITCODE -ne 0) {
            throw "Could not build dashboard."
        }
    } finally {
        Pop-Location
    }
}

function Stop-PidFile {
    param([string]$Name)

    $pidPath = Join-Path $PidDir "$Name.pid"
    if (-not (Test-Path $pidPath)) {
        return
    }

    $processId = [int](Get-Content $pidPath -Raw)
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        Write-Step "Stopping previous $Name process"
        Stop-Process -Id $processId -Force
    }
    Remove-Item $pidPath -Force -ErrorAction SilentlyContinue
}

function Test-PortFree {
    param([int]$Port)

    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($connection) {
        $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
        $name = if ($process) { $process.ProcessName } else { "unknown" }
        throw "Port $Port is already in use by process $($connection.OwningProcess) ($name). Run Stop-MordhauPredictionUnit.bat or close that process, then start again."
    }
}

function Start-ServiceProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )

    $stdout = Join-Path $LogDir "$Name.out.log"
    $stderr = Join-Path $LogDir "$Name.err.log"

    Write-Step "Starting $Name"
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -WindowStyle Hidden `
        -PassThru

    Set-Content -Path (Join-Path $PidDir "$Name.pid") -Value $process.Id
}

function Wait-Http {
    param(
        [string]$Url,
        [int]$Seconds = 30
    )

    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }

    throw "Timed out waiting for $Url"
}

Write-Step "Preparing local stack"

$basePython = Find-BasePython
$dataPath = Join-Path $Root "services\data-service"
$predictionPath = Join-Path $Root "services\prediction-service"
$dashboardDist = Join-Path $Root "apps\dashboard\dist"

$dataPython = Ensure-PythonService -Name "data-service" -Path $dataPath -BasePython $basePython
$predictionPython = Ensure-PythonService -Name "prediction-service" -Path $predictionPath -BasePython $basePython
Ensure-Dashboard

Stop-PidFile "dashboard"
Stop-PidFile "prediction-service"
Stop-PidFile "data-service"

Test-PortFree 8001
Test-PortFree 8002
Test-PortFree 5173

Start-ServiceProcess `
    -Name "data-service" `
    -FilePath $dataPython `
    -Arguments @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001") `
    -WorkingDirectory $dataPath

Wait-Http "http://127.0.0.1:8001/health" 30

Start-ServiceProcess `
    -Name "prediction-service" `
    -FilePath $predictionPython `
    -Arguments @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8002") `
    -WorkingDirectory $predictionPath

Wait-Http "http://127.0.0.1:8002/health" 30

if (-not $SkipIngest) {
    try {
        Write-Step "Syncing match and player data"
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8002/ingest/history?limit=9999" -TimeoutSec 60 | Out-Null
    } catch {
        Write-Warning "Data sync failed. The app will still start with cached data. $($_.Exception.Message)"
    }
}

Start-ServiceProcess `
    -Name "dashboard" `
    -FilePath $dataPython `
    -Arguments @("-m", "http.server", "5173", "--bind", "127.0.0.1", "-d", $dashboardDist) `
    -WorkingDirectory $Root

Wait-Http "http://127.0.0.1:5173/" 30

if (-not $NoBrowser) {
    Write-Step "Opening dashboard"
    Start-Process "http://127.0.0.1:5173/"
}

Write-Step "Ready"
Write-Host "Dashboard:          http://127.0.0.1:5173/"
Write-Host "Data service:       http://127.0.0.1:8001/health"
Write-Host "Prediction service: http://127.0.0.1:8002/health"
Write-Host "Logs:               $LogDir"
