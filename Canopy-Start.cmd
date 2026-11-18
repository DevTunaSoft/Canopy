@echo off
setlocal
rem Single-click test-lab preflight. No destructive installer actions.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Canopy-Setup.ps1"
set "CANOPY_EXIT=%ERRORLEVEL%"
if not "%CANOPY_EXIT%"=="0" (
  echo Setup preflight failed. Collecting diagnostic ZIP...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Canopy-Diagnostics.ps1"
  echo Diagnostic files are under %LOCALAPPDATA%\CanopyTestLab\diagnostics
  pause
  exit /b %CANOPY_EXIT%
)
echo Canopy preflight passed. Mint unattended installation is not yet enabled.
pause
exit /b 0
