@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Canopy-Diagnostics.ps1"
if errorlevel 1 (
  echo Canopy diagnostics failed. No VM changes were made.
  pause
  exit /b 1
)
echo Upload the Canopy-Diagnostics ZIP from %LOCALAPPDATA%\CanopyTestLab\diagnostics.
pause
