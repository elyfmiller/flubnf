@echo off
rem UTF-8 mode: Windows' cp1252 default breaks reads of UTF-8 assets
set PYTHONUTF8=1
rem Double-click me. Self-updates, sets up on first run, launches the console.
rem Windows twin of FluBNF.command.
rem
rem setup.ps1 is the FULL first-time setup: the sparse FluSight data clone,
rem the environment variables, the Perl and engine checks. This launcher used
rem to mention that only in a rem comment no user ever sees, so a first run
rem ended at a console reporting "Latest vintage: none" with no explanation.
rem The :data section below now says so out loud and offers to run it, once,
rem and only while the data is actually missing.
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
echo First run - setting up, a few minutes...
rem venv creation output goes to a log rather than to nul: the old "2>nul"
rem hid access-denied and broken-ensurepip failures, and the failure text
rem below then blamed a missing Python, which sent people the wrong way.
set "SETUPLOG=%TEMP%\flubnf-firstrun.log"
if exist "%SETUPLOG%" del "%SETUPLOG%" >nul 2>&1
where py >nul 2>&1 && py -3 -m venv .venv >>"%SETUPLOG%" 2>&1
if not exist ".venv\Scripts\python.exe" (
  where python >nul 2>&1 && python -m venv .venv >>"%SETUPLOG%" 2>&1
)
if not exist ".venv\Scripts\python.exe" goto :failvenv
".venv\Scripts\python" -m pip install -q --upgrade pip
".venv\Scripts\pip" install -q -e ".[app,dev]" bionetgen
if errorlevel 1 goto :fail
copy /y pyproject.toml ".venv\pyproject.stamp" >nul 2>&1
goto :data

:sync
rem Refresh dependencies only when the project metadata changed (the
rem package is editable, so pulled code changes are live without pip).
rem The old always-reinstall briefly uninstalled the launcher on every
rem open and hid its errors: an interrupted open left the app broken
rem until the next open re-ran full setup.
fc /b pyproject.toml ".venv\pyproject.stamp" >nul 2>&1
if not errorlevel 1 goto :data
echo   project dependencies changed, refreshing, about a minute
".venv\Scripts\pip" install -q -e ".[app,dev]"
if errorlevel 1 (
  echo   dependency refresh failed - running with what is installed
) else (
  copy /y pyproject.toml ".venv\pyproject.stamp" >nul 2>&1
)
if not exist ".venv\Scripts\flubnf.exe" goto :fail

:data
rem Configuration written by setup.ps1: the Windows twin of .flubnf.env, which
rem FluBNF.command sources on macOS. Read it on EVERY launch. setup.ps1 also
rem records User-scope environment variables, but those reach only processes
rem started after it ran, so without this file a console opened from a window
rem that was already open would still see nothing.
if exist ".flubnf.env.cmd" call ".flubnf.env.cmd"

rem Resolved in the same order setup.ps1 uses, so the launcher and the setup
rem script can never disagree about where the data is: FLUBNF_HUB wins; then
rem an existing clone at the old %USERPROFILE%\Documents default, which is
rem reused where it stands and never moved; then the current default under
rem %LOCALAPPDATA%. Documents is one of the folders Controlled Folder Access
rem protects whenever it is switched on, which blocks git.exe from writing
rem there; %LOCALAPPDATA% is never in that set. Microsoft ships the
rem protection off, but it was on for this project's corresponding author,
rem so the default must not rely on it. See docs\WINDOWS.md.
rem
rem %USERPROFILE% is the anchor here, in setup.ps1 and in flubnf\settings.py
rem alike, so the three can never disagree about where the old default was.
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "HUBDIR=%FLUBNF_HUB%"
if defined HUBDIR goto :hubresolved
set "HUBDIR=%USERPROFILE%\Documents\GitHub\FluSight-forecast-hub"
if exist "%HUBDIR%\." goto :hubresolved
set "HUBDIR=%LOCALAPPDATA%\FluBNF\FluSight-forecast-hub"
:hubresolved
rem Test for DATA, not for ".git". A clone made by hand with --sparse is a
rem healthy git checkout that contains only the repository root, so the old
rem ".git exists" gate declared such a machine finished and never offered
rem setup again - on the one machine that most needs the offer. locations.csv
rem is the file flubnf/settings.py reads, so this is the same question the
rem console will ask a moment later.
if exist "%HUBDIR%\auxiliary-data\locations.csv" goto :launch

echo.
echo The FluSight data files are not on this machine yet, so the console will
echo open with "Latest vintage: none" and no archived truth vintages.
echo   looked for: "%HUBDIR%\auxiliary-data\locations.csv"
if exist "%HUBDIR%\.git" echo   The folder is there but holds no data directories, which is what a
if exist "%HUBDIR%\.git" echo   clone made with --sparse leaves behind. setup.ps1 repairs that.
echo Fetching it is a one-time sparse download of about 150 MB. setup.ps1
echo does that, and records the settings FluBNF needs.
where choice >nul 2>&1
if errorlevel 1 (
  echo Run this once, then double-click me again:
  echo   powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
  echo.
  goto :launch
)
choice /c YN /n /t 20 /d N /m "Fetch it now? [Y/N, N by itself in 20s] "
if errorlevel 2 (
  echo   skipped. Run this whenever you are ready:
  echo   powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
  echo.
  goto :launch
)
echo.
rem -NoProfile so a user profile that sets $ErrorActionPreference cannot turn
rem git's ordinary stderr output into a setup-ending error. A Group Policy
rem execution policy overrides -ExecutionPolicy Bypass and PowerShell will
rem refuse to run; that is reported and the console still starts.
rem
rem -NoPrompt is not optional on THIS path. The question above is bounded
rem (20 s, defaults to N), and a double-click must never end at a prompt
rem nobody is watching. Without the switch setup.ps1 detects an interactive
rem session and asks, with no timeout and no default, whether to let winget
rem install Strawberry Perl - so a user who answered Y and walked away would
rem come back to a blocked window and no console. Perl is needed only by the
rem PF engine, never by the console this launcher is opening, and setup.ps1
rem still prints the winget command for anyone who wants it later. A user who
rem does want to be asked runs setup.ps1 by hand, where the offer still fires.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" -NoPrompt
if errorlevel 1 echo   setup.ps1 reported a problem, see above - starting the console anyway
rem setup.ps1 rewrites .flubnf.env.cmd, so re-read it and let THIS process see
rem what it just wrote.
if exist ".flubnf.env.cmd" call ".flubnf.env.cmd"

:launch
echo FluBNF console starting - a window (or browser tab) will open. Ctrl-C here to stop.
".venv\Scripts\flubnf" app
set STATUS=%errorlevel%
if "%STATUS%"=="0" exit /b 0
echo.
echo FluBNF exited with an error (code %STATUS%). Press any key to close.
pause >nul
exit /b %STATUS%

:failvenv
echo.
echo Could not create the Python virtual environment in .venv
if exist "%SETUPLOG%" (
  echo The setup output was:
  type "%SETUPLOG%"
)
echo.
echo Usual causes: Python 3.11 or newer is not installed - get it from
echo https://www.python.org/downloads/ and tick "Add python.exe to PATH" -
echo or a policy on this machine blocks writing into this folder.
echo Press any key to close.
pause >nul
exit /b 1

:fail
echo.
echo Setup hit a problem (see above). If Python is missing, install 3.11 or
echo newer from https://www.python.org/downloads/ and tick "Add to PATH".
echo Press any key to close.
pause >nul
exit /b 1
