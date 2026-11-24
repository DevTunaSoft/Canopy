@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Canopy Autopilot - One Time Setup
echo.
echo ====================================================
echo   CANOPY AUTOPILOT - ONE-TIME WINDOWS INSTALLER
echo ====================================================
echo.
echo   No administrator access requested.
echo   Uses existing OpenCode credentials and task history.
echo   Does not merge PRs or replace your approved designs.
echo.

if not defined LOCALAPPDATA goto missing_home
set "AUTOPILOT=%LOCALAPPDATA%\CanopyAutopilot"
set "CHECKOUT=%AUTOPILOT%\supervisor"
set "STATE=C:\CanopySupervisor\state"
set "BRANCH=feat/windows-multi-agent-supervisor-20261121"
set "LOG=%AUTOPILOT%\setup.log"

if not exist "%STATE%\config.json" goto missing_state
if not exist "%AUTOPILOT%" mkdir "%AUTOPILOT%"
if not exist "%AUTOPILOT%" goto setup_failed
echo CANOPY_AUTOPILOT_SETUP_STARTED > "%LOG%"

where git >nul 2>&1
if errorlevel 1 goto missing_git
where py >nul 2>&1
if errorlevel 1 goto missing_python

if exist "%CHECKOUT%\.git" goto refresh
if exist "%CHECKOUT%" goto occupied_folder

echo Setting up an isolated Canopy supervisor checkout...
git clone --depth 1 --single-branch --branch "%BRANCH%" "https://github.com/DevTunaSoft/Canopy.git" "%CHECKOUT%" >>"%LOG%" 2>&1
if errorlevel 1 goto setup_failed
goto install

:refresh
set "CHANGES="
for /f "delims=" %%A in ('git -C "%CHECKOUT%" status --porcelain') do set "CHANGES=1"
if defined CHANGES goto dirty_checkout

echo Updating the isolated supervisor...
git -C "%CHECKOUT%" fetch origin "%BRANCH%" >>"%LOG%" 2>&1
if errorlevel 1 goto setup_failed
git -C "%CHECKOUT%" switch --detach "origin/%BRANCH%" >>"%LOG%" 2>&1
if errorlevel 1 goto setup_failed

:install
echo Enabling automatic recovery...
py -3 "%CHECKOUT%\tools\canopy_autopilot.py" install --state-root "%STATE%" --checkout "%CHECKOUT%" >>"%LOG%" 2>&1
if errorlevel 1 goto setup_failed

echo.
echo   CANOPY AUTOPILOT ENABLED
echo.
echo   Three OpenCode workers maximum.
echo   The queue resumes without a PowerShell window.
echo   Windows automatically retries every five minutes.
echo   Status: %STATE%\autopilot-status.json
echo.
echo   You can close this window.
echo.
exit /b 0

:missing_home
echo ERROR: Windows LOCALAPPDATA was not available.
goto failed_no_log

:missing_state
echo ERROR: Existing Canopy supervisor state not found at:
echo        %STATE%\config.json
echo Nothing was reset or installed.
goto failed_no_log

:missing_git
echo ERROR: Git is missing from PATH. Nothing was reset.
goto setup_failed

:missing_python
echo ERROR: Python launcher 'py' is missing. Nothing was reset.
goto setup_failed

:occupied_folder
echo ERROR: Target checkout folder exists but is not a Git repository.
echo        %CHECKOUT%
echo No existing files will be overwritten.
goto setup_failed

:dirty_checkout
echo ERROR: Dedicated supervisor checkout has local changes.
echo No files will be overwritten.
goto setup_failed

:setup_failed
echo.
echo   CANOPY AUTOPILOT NOT ENABLED
echo   See log: %LOG%
echo   Your current Canopy task history is preserved.
echo.
if exist "%LOG%" start "" notepad.exe "%LOG%"
:failed_no_log
echo.
echo   No PowerShell steps required.
echo.
pause
exit /b 2
