@echo off
rem UTF-8 mode: Windows' cp1252 default breaks reads of UTF-8 assets
set PYTHONUTF8=1
rem Double-click me. Self-updates, sets up on first run, launches the console.
rem Windows twin of FluBNF.command; setup.ps1 is the full first-time setup
rem (hub data, engine checks) and is worth running once.
setlocal
cd /d "%~dp0"

rem stay current (lab-share mode): fast-forward only, never clobbers local edits
if not exist ".git" goto :deps
where git >nul 2>&1
if errorlevel 1 goto :deps
git pull --ff-only -q >nul 2>&1
if errorlevel 1 (
  echo   offline or local changes - running as-is
) else (
  echo   up to date with origin
)

:deps
if exist ".venv\Scripts\flubnf.exe" goto :sync
echo First run - setting up (a few minutes)...
py -3 -m venv .venv 2>nul
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if not exist ".venv\Scripts\python.exe" goto :fail
".venv\Scripts\python" -m pip install -q --upgrade pip
".venv\Scripts\pip" install -q -e ".[app,dev]" bionetgen
if errorlevel 1 goto :fail
copy /y pyproject.toml ".venv\pyproject.stamp" >nul 2>&1
goto :launch

:sync
rem Refresh dependencies only when the project metadata changed (the
rem package is editable, so pulled code changes are live without pip).
rem The old always-reinstall briefly uninstalled the launcher on every
rem open and hid its errors: an interrupted open left the app broken
rem until the next open re-ran full setup.
fc /b pyproject.toml ".venv\pyproject.stamp" >nul 2>&1
if not errorlevel 1 goto :launch
echo   project dependencies changed, refreshing (about a minute)
".venv\Scripts\pip" install -q -e ".[app,dev]"
if errorlevel 1 (
  echo   dependency refresh failed - running with what is installed
) else (
  copy /y pyproject.toml ".venv\pyproject.stamp" >nul 2>&1
)
if not exist ".venv\Scripts\flubnf.exe" goto :fail

:launch
echo FluBNF console starting - a window (or browser tab) will open. Ctrl-C here to stop.
".venv\Scripts\flubnf" app
set STATUS=%errorlevel%
if "%STATUS%"=="0" exit /b 0
echo.
echo FluBNF exited with an error (code %STATUS%). Press any key to close.
pause >nul
exit /b %STATUS%

:fail
echo.
echo Setup hit a problem (see above). If Python is missing, install 3.11 or
echo newer from https://www.python.org/downloads/ and tick "Add to PATH".
echo Press any key to close.
pause >nul
exit /b 1
