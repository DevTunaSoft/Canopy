@echo off
setlocal
rem One-click read-only preflight; preserves failure output for diagnostics.
set "CANOPY_LOG_DIR=%LOCALAPPDATA%\CanopyTestLab\diagnostics"
if not exist "%CANOPY_LOG_DIR%" mkdir "%CANOPY_LOG_DIR%"
set "CANOPY_LOG=%CANOPY_LOG_DIR%\last-setup-preflight.log"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Canopy-Setup.ps1" >"%CANOPY_LOG%" 2>&1
set "CANOPY_EXIT=%ERRORLEVEL%"
type "%CANOPY_LOG%"
if not "%CANOPY_EXIT%"=="0" (
  echo Setup preflight failed with exit code %CANOPY_EXIT%. Collecting diagnostic ZIP...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Canopy-Diagnostics.ps1"
  echo Diagnostic files are under %CANOPY_LOG_DIR%
  pause
  exit /b %CANOPY_EXIT%
)
echo Canopy preflight passed. Mint unattended installation is not yet enabled.
pause
exit /b 0
