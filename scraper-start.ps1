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
    Write-Host "  .\venv\Scripts\pip install -r requirements-dev.txt"
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

# 2. Map 'logs/' initialiseren voor gecentraliseerde logging
$LogsDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
}
$BackendLog = Join-Path $LogsDir "backend.log"
$FrontendLog = Join-Path $LogsDir "frontend.log"

# 3. Eventuele achtergebleven processen op poort 8000 en 5173 automatisch controleren en opruimen
$staleConns = Get-NetTCPConnection -LocalPort 8000, 5173 -ErrorAction SilentlyContinue
if ($staleConns) {
    $stalePids = $staleConns | Select-Object -ExpandProperty OwningProcess -Unique
    Write-Host "Achtergebleven processen op poort 8000 of 5173 gedetecteerd. Deze worden eerst beëindigd..." -ForegroundColor Yellow
    foreach ($p in $stalePids) {
        if ($p -and $p -gt 4) {
            taskkill /PID $p /T /F 2>&1 | Out-Null
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
    # Start FastAPI-backend op de achtergrond en schrijf opstart- en foutmeldingen naar logs/backend.log
    Write-Host "[1/2] FastAPI-backend opstarten op poort 8000..." -ForegroundColor Yellow
    $backendCmd = "`"$PythonExe`" -m uvicorn backend.main:app --reload --port 8000 > `"$BackendLog`" 2>&1"
    $backendProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$backendCmd`"" -PassThru -NoNewWindow

    # Start Vue-frontend op de achtergrond en schrijf opstart- en foutmeldingen naar logs/frontend.log
    Write-Host "[2/2] Vue-frontend opstarten op poort 5173..." -ForegroundColor Yellow
    $frontendCmd = "`"$NpmCmd`" --prefix frontend run dev < nul > `"$FrontendLog`" 2>&1"
    $frontendProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$frontendCmd`"" -PassThru -NoNewWindow

    # Wacht maximaal 10 seconden tot http://127.0.0.1:8000 en http://localhost:5173 bereikbaar zijn
    Write-Host "Wachten tot backend en frontend bereikbaar zijn (max. 10s)..." -ForegroundColor Cyan
    $timeoutSeconds = 10
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $backendReady = $false
    $frontendReady = $false

    while ($stopwatch.Elapsed.TotalSeconds -lt $timeoutSeconds) {
        # Controleer of processen vroegtijdig zijn gecrasht
        if ($backendProcess.HasExited) {
            break
        }
        if ($frontendProcess.HasExited) {
            break
        }

        # Controleer backend readiness via healthcheck
        if (-not $backendReady) {
            try {
                $bResp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
                if ($bResp.StatusCode -eq 200) {
                    $backendReady = $true
                }
            } catch { }
        }

        # Controleer frontend readiness (Vite)
        if (-not $frontendReady) {
            try {
                $fResp = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
                if ($fResp.StatusCode -ge 200 -and $fResp.StatusCode -lt 400) {
                    $frontendReady = $true
                }
            } catch { }
        }

        if ($backendReady -and $frontendReady) {
            break
        }

        Start-Sleep -Milliseconds 500
    }

    $hasStartupError = $false

    if (-not $backendReady -or $backendProcess.HasExited) {
        $hasStartupError = $true
        Write-Host ""
        Write-Host "FOUT: FastAPI-backend is gecrasht of reageerde niet binnen 10 seconden op poort 8000." -ForegroundColor Red
        Write-Host "Laatste 15 regels uit '$BackendLog':" -ForegroundColor Red
        Write-Host "----------------------------------------------------------------" -ForegroundColor Red
        if (Test-Path $BackendLog) {
            Get-Content $BackendLog -Tail 15 | ForEach-Object { Write-Host $_ -ForegroundColor DarkRed }
        } else {
            Write-Host "(Geen backend logbestand gevonden op $BackendLog)" -ForegroundColor DarkRed
        }
        Write-Host "----------------------------------------------------------------" -ForegroundColor Red
    }

    if (-not $frontendReady -or $frontendProcess.HasExited) {
        $hasStartupError = $true
        Write-Host ""
        Write-Host "FOUT: Vue-frontend is gecrasht of reageerde niet binnen 10 seconden op poort 5173." -ForegroundColor Red
        Write-Host "Laatste 15 regels uit '$FrontendLog':" -ForegroundColor Red
        Write-Host "----------------------------------------------------------------" -ForegroundColor Red
        if (Test-Path $FrontendLog) {
            Get-Content $FrontendLog -Tail 15 | ForEach-Object { Write-Host $_ -ForegroundColor DarkRed }
        } else {
            Write-Host "(Geen frontend logbestand gevonden op $FrontendLog)" -ForegroundColor DarkRed
        }
        Write-Host "----------------------------------------------------------------" -ForegroundColor Red
    }

    if ($hasStartupError) {
        Write-Host ""
        Write-Host "Opstarten afgebroken wegens fouten. Bekijk bovenstaande logs voor details." -ForegroundColor Red
        Read-Host "Druk op ENTER om af te sluiten..."
        exit 1
    }

    Write-Host "Backend en frontend zijn gereed! Browser wordt geopend..." -ForegroundColor Green

    # Open automatisch in de standaardbrowser
    Start-Process "http://localhost:5173"

    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host "  SoundCloud Scraper is succesvol gestart!" -ForegroundColor Green
    Write-Host "  - Backend:  http://localhost:8000 (API Docs: /docs)" -ForegroundColor Gray
    Write-Host "  - Frontend: http://localhost:5173" -ForegroundColor Gray
    Write-Host "  - Logs:     $LogsDir" -ForegroundColor Gray
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host ""

    Read-Host "Druk op ENTER (of Ctrl+C) om de SoundCloud Scraper volledig af te sluiten"
}
finally {
    Write-Host ""
    Write-Host "SoundCloud Scraper wordt afgesloten..." -ForegroundColor Yellow

    if ($backendProcess -and -not $backendProcess.HasExited) {
        Write-Host "FastAPI-backend beëindigen (PID $($backendProcess.Id))..."
        taskkill /PID $backendProcess.Id /T /F 2>&1 | Out-Null
    }

    if ($frontendProcess -and -not $frontendProcess.HasExited) {
        Write-Host "Vue-frontend beëindigen (PID $($frontendProcess.Id))..."
        taskkill /PID $frontendProcess.Id /T /F 2>&1 | Out-Null
    }

    # Naloop om eventuele overgebleven child-processen op poort 8000 en 5173 definitief te stoppen
    $remainingPids = Get-NetTCPConnection -LocalPort 8000, 5173 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    if ($remainingPids) {
        foreach ($rPid in $remainingPids) {
            if ($rPid -and $rPid -gt 4) {
                taskkill /PID $rPid /T /F 2>&1 | Out-Null
            }
        }
    }

    Write-Host "Alle SoundCloud Scraper processen zijn netjes afgesloten." -ForegroundColor Green
}
