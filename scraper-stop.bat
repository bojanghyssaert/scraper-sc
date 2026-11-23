@echo off
setlocal
cd /d "%~dp0"
echo ========================================================
echo   SoundCloud Scraper - Noodstop
echo ========================================================
echo Controleren op actieve processen op poort 8000 en 5173...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ports = @(8000, 5173); " ^
  "$conns = Get-NetTCPConnection -LocalPort $ports -ErrorAction SilentlyContinue; " ^
  "$pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique; " ^
  "if ($pids) { " ^
  "  foreach ($procId in $pids) { " ^
  "    if ($procId -gt 0) { " ^
  "      try { " ^
  "        $pName = (Get-Process -Id $procId -ErrorAction SilentlyContinue).ProcessName; " ^
  "        Write-Host ('[STOPPEN] Proces ' + $pName + ' (PID: ' + $procId + ') wordt beeindigd...') -ForegroundColor Yellow; " ^
  "        taskkill /PID $procId /T /F | Out-Null; " ^
  "      } catch { } " ^
  "    } " ^
  "  } " ^
  "  Write-Host '[OK] Alle processen op poort 8000 en 5173 zijn succesvol beeindigd.' -ForegroundColor Green; " ^
  "} else { " ^
  "  Write-Host '[INFO] Geen actieve processen gevonden op poort 8000 of 5173. Alles is al afgesloten.' -ForegroundColor Cyan; " ^
  "}"

echo.
pause
