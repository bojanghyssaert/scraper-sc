# ==============================================================================
# SoundCloud Scraper - Start- en stopmechanisme voor Windows
# ==============================================================================

$ProjectRoot = $PSScriptRoot
if (-not $ProjectRoot) {
    $ProjectRoot = Get-Location
}
Set-Location $ProjectRoot

# 1. Controleer vereisten
$PythonExe = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$NodeModules = Join-Path $ProjectRoot "frontend\node_modules"

if (-not (Test-Path $PythonExe)) {
    Write-Host ""
    Write-Host "FOUT: Virtuele Python-omgeving niet gevonden in 'venv'." -ForegroundColor Red
    Write-Host ""
    Write-Host "Voer de volgende stappen eenmalig uit om de backend in te richten:" -ForegroundColor Yellow
    Write-Host "  python -m venv venv"
    Write-Host "  .\venv\Scripts\pip install -r requirements.txt"
    Write-Host ""
    Read-Host "Druk op ENTER om af te sluiten..."
    exit 1
}

if (-not (Test-Path $NodeModules)) {
    Write-Host ""
    Write-Host "FOUT: Frontend afhankelijkheden niet gevonden in 'frontend\node_modules'." -ForegroundColor Red
    Write-Host ""
    Write-Host "Voer de volgende stappen eenmalig uit om de frontend in te richten:" -ForegroundColor Yellow
    Write-Host "  cd frontend"
    Write-Host "  npm install"
    Write-Host ""
    Read-Host "Druk op ENTER om af te sluiten..."
    exit 1
}

# Zoek npm executable voor Windows
$NpmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $NpmCmd) {
    $NpmCmd = (Get-Command npm -ErrorAction SilentlyContinue).Source
}
if (-not $NpmCmd) {
    $NpmCmd = "npm.cmd"
}

# 2. Eventuele achtergebleven processen op poort 8000 en 5173 eerst opruimen
$stalePids = Get-NetTCPConnection -LocalPort 8000, 5173 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
if ($stalePids) {
    Write-Host "Oude processen op poort 8000 of 5173 gedetecteerd. Deze worden eerst beëindigd..." -ForegroundColor Yellow
    foreach ($p in $stalePids) {
        if ($p -gt 0) {
            taskkill /PID $p /T /F > $null 2>&1
        }
    }
    Start-Sleep -Seconds 1
}

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  SoundCloud Scraper wordt opgestart..." -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

$backendProcess = $null
$frontendProcess = $null

try {
    # Start FastAPI-backend op de achtergrond in hetzelfde venster
    Write-Host "[1/2] FastAPI-backend opstarten op poort 8000..." -ForegroundColor Yellow
    $backendProcess = Start-Process -FilePath $PythonExe -ArgumentList "-m uvicorn backend.main:app --reload --port 8000" -PassThru -NoNewWindow

    # Start Vue-frontend op de achtergrond in hetzelfde venster
    Write-Host "[2/2] Vue-frontend opstarten op poort 5173..." -ForegroundColor Yellow
    $frontendProcess = Start-Process -FilePath $NpmCmd -ArgumentList "--prefix frontend run dev" -PassThru -NoNewWindow

    # Wacht maximaal 10 seconden tot http://localhost:5173 bereikbaar is
    Write-Host "Wachten tot http://localhost:5173 bereikbaar is (max. 10s)..." -ForegroundColor Cyan
    $timeoutSeconds = 10
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $isReady = $false

    while ($stopwatch.Elapsed.TotalSeconds -lt $timeoutSeconds) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                $isReady = $true
                break
            }
        } catch {
            # Wachten op gereedheid van de frontend server
        }
        Start-Sleep -Milliseconds 500
    }

    if ($isReady) {
        Write-Host "Frontend is gereed! Browser wordt geopend..." -ForegroundColor Green
    } else {
        Write-Host "Frontend antwoordde nog niet binnen 10 seconden; browser wordt alsnog geopend..." -ForegroundColor Yellow
    }

    # Open automatisch in de standaardbrowser
    Start-Process "http://localhost:5173"

    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host "  SoundCloud Scraper is succesvol gestart!" -ForegroundColor Green
    Write-Host "  - Backend:  http://localhost:8000 (API Docs: /docs)" -ForegroundColor Gray
    Write-Host "  - Frontend: http://localhost:5173" -ForegroundColor Gray
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host ""

    Read-Host "Druk op ENTER (of Ctrl+C) om de SoundCloud Scraper volledig af te sluiten"
}
finally {
    Write-Host ""
    Write-Host "SoundCloud Scraper wordt afgesloten..." -ForegroundColor Yellow

    if ($backendProcess -and -not $backendProcess.HasExited) {
        Write-Host "FastAPI-backend beëindigen (PID $($backendProcess.Id))..."
        taskkill /PID $backendProcess.Id /T /F > $null 2>&1
    }

    if ($frontendProcess -and -not $frontendProcess.HasExited) {
        Write-Host "Vue-frontend beëindigen (PID $($frontendProcess.Id))..."
        taskkill /PID $frontendProcess.Id /T /F > $null 2>&1
    }

    # Naloop om eventuele overgebleven child-processen op poort 8000 en 5173 definitief te stoppen
    $remainingPids = Get-NetTCPConnection -LocalPort 8000, 5173 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    if ($remainingPids) {
        foreach ($rPid in $remainingPids) {
            if ($rPid -gt 0) {
                taskkill /PID $rPid /T /F > $null 2>&1
            }
        }
    }

    Write-Host "Alle SoundCloud Scraper processen zijn netjes afgesloten." -ForegroundColor Green
}
