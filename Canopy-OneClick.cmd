@echo off
setlocal
set "CANOPY_LOG_DIR=%LOCALAPPDATA%\CanopyTestLab\diagnostics"
if not exist "%CANOPY_LOG_DIR%" mkdir "%CANOPY_LOG_DIR%"
set "CANOPY_LOG=%CANOPY_LOG_DIR%\last-oneclick.log"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Canopy-OneClick.ps1" %* >"%CANOPY_LOG%" 2>&1
set "CANOPY_EXIT=%ERRORLEVEL%"
type "%CANOPY_LOG%"
if not "%CANOPY_EXIT%"=="0" (
  echo Canopy installation was BLOCKED or failed. Collecting diagnostics...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Canopy-Diagnostics.ps1"
  echo Diagnostic files are under %CANOPY_LOG_DIR%
)
pause
exit /b %CANOPY_EXIT%
