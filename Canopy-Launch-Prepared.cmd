@echo off
setlocal
rem Launch a PREPARED Canopy ISO only, with an explicit user confirmation.
set "CANOPY_LOG_DIR=%LOCALAPPDATA%\CanopyTestLab\diagnostics"
if not exist "%CANOPY_LOG_DIR%" mkdir "%CANOPY_LOG_DIR%"
set "CANOPY_LOG=%CANOPY_LOG_DIR%\last-prepared-launch.log"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Canopy-Launch-Prepared.ps1" >"%CANOPY_LOG%" 2>&1
set "CANOPY_EXIT=%ERRORLEVEL%"
type "%CANOPY_LOG%"
if not "%CANOPY_EXIT%"=="0" (
  echo Prepared VM launch failed. Collecting diagnostic ZIP...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Canopy-Diagnostics.ps1"
  echo Diagnostic files are under %CANOPY_LOG_DIR%
)
pause
exit /b %CANOPY_EXIT%
