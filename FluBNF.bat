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

rem The lab's Windows machines run the ANACONDA distribution, whose installer
rem has no "add to PATH" checkbox and deliberately leaves PATH alone, so on a
rem defaults-accepted Anaconda machine a plain Command Prompt has no `py` and
rem no `python` even though Python is right there. Probe the folders Anaconda
rem and Miniconda actually install into, ABOVE every gate: the first-run venv
rem needs this, and so does the engine-venv fallback on a LATER launch (save
rem the engine file, "open FluBNF again"), which skips the first-run block
rem entirely. PATH launchers are still tried first wherever this is used, so
rem a python.org install keeps working exactly as before.
set "CONDAPY="
if exist "%USERPROFILE%\anaconda3\python.exe"    set "CONDAPY=%USERPROFILE%\anaconda3\python.exe"
if not defined CONDAPY if exist "%USERPROFILE%\miniconda3\python.exe" set "CONDAPY=%USERPROFILE%\miniconda3\python.exe"
if not defined CONDAPY if exist "%LOCALAPPDATA%\anaconda3\python.exe" set "CONDAPY=%LOCALAPPDATA%\anaconda3\python.exe"
if not defined CONDAPY if exist "C:\ProgramData\anaconda3\python.exe" set "CONDAPY=C:\ProgramData\anaconda3\python.exe"

rem Stay current (lab-share mode). Fast-forward only, so a real edit is never
rem silently overwritten. This is the Windows twin of the block in
rem FluBNF.command, and the reasoning is written out there: "offline or local
rem changes" named two causes with opposite remedies and said which one it was
rem not, so a machine could sit on a month old console with nothing on screen
rem to say so. A stray edit is stashed, never destroyed; a local commit is
rem left alone and the recovery command is printed.
rem   set FLUBNF_UPDATE=off     skip this entirely
rem   set FLUBNF_UPDATE=force   take origin's copy whatever is here
if not exist ".git" goto :deps
where git >nul 2>&1
if errorlevel 1 goto :deps
if /I "%FLUBNF_UPDATE%"=="off" goto :deps
set "BRANCH="
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%b"
if not defined BRANCH goto :deps
if "%BRANCH%"=="HEAD" (
  echo   not on a branch - running the copy on disk
  goto :deps
)
git fetch -q origin >nul 2>&1
if errorlevel 1 (
  echo   offline ^(origin unreachable^) - running the copy on disk
  goto :deps
)
if /I "%FLUBNF_UPDATE%"=="force" (
  git reset --hard -q origin/%BRANCH% >nul 2>&1
  if errorlevel 1 (
    echo   could not reset to origin/%BRANCH% - running the copy on disk
  ) else (
    echo   forced to origin/%BRANCH% - local edits and commits discarded
  )
  goto :deps
)
git merge --ff-only -q origin/%BRANCH% >nul 2>&1
if not errorlevel 1 (
  echo   up to date with origin
  goto :deps
)
set "AHEAD=0"
for /f "delims=" %%n in ('git rev-list --count origin/%BRANCH%..HEAD 2^>nul') do set "AHEAD=%%n"
if not "%AHEAD%"=="0" (
  echo   this clone has %AHEAD% commit^(s^) origin does not, so it cannot
  echo   fast-forward. Nothing here will discard them. Running as-is. To take
  echo   origin's copy and throw this clone's work away:
  echo       git fetch origin ^&^& git reset --hard origin/%BRANCH%
  goto :deps
)
echo   local edits are blocking the update:
git status --porcelain --untracked-files=no
git stash push -q -m "FluBNF update" >nul 2>&1
if errorlevel 1 goto :updatestuck
git merge --ff-only -q origin/%BRANCH% >nul 2>&1
if errorlevel 1 (
  git stash pop -q >nul 2>&1
  goto :updatestuck
)
echo   updated anyway - those edits were set aside, not lost. In this folder,
echo   git stash list shows them and git stash pop puts them back.
goto :deps
:updatestuck
echo   could not update around them - running the copy on disk. To take
echo   origin's copy and discard the edits above:
echo       git fetch origin ^&^& git reset --hard origin/%BRANCH%

:deps
if exist ".venv\Scripts\flubnf.exe" goto :sync
echo First run - setting up, a few minutes...
rem venv output goes to a log, not nul, so the failure text shows the real cause.
set "SETUPLOG=%TEMP%\flubnf-firstrun.log"
if exist "%SETUPLOG%" del "%SETUPLOG%" >nul 2>&1
where py >nul 2>&1 && py -3 -m venv .venv >>"%SETUPLOG%" 2>&1
if not exist ".venv\Scripts\python.exe" (
  where python >nul 2>&1 && python -m venv .venv >>"%SETUPLOG%" 2>&1
)
if not exist ".venv\Scripts\python.exe" if defined CONDAPY (
  echo   using Anaconda's Python: "%CONDAPY%"
  "%CONDAPY%" -m venv .venv >>"%SETUPLOG%" 2>&1
)
if not exist ".venv\Scripts\python.exe" goto :failvenv
".venv\Scripts\python" -m pip install -q --upgrade pip
".venv\Scripts\pip" install -q -e ".[app,dev]" bionetgen
if errorlevel 1 goto :fail
copy /y pyproject.toml ".venv\pyproject.stamp" >nul 2>&1
goto :data

:sync
rem Refresh deps only when pyproject.toml changed (the package is editable).
rem Never reinstall on every open: an interrupted one left no launcher.
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
rem .flubnf.env.cmd (setup.ps1's twin of .flubnf.env) is read on EVERY launch:
rem User env vars reach only processes started after setup ran.
if exist ".flubnf.env.cmd" call ".flubnf.env.cmd"

rem Hub order = setup.ps1's: FLUBNF_HUB, an existing clone at the old
rem %USERPROFILE%\Documents default (reused in place), else %LOCALAPPDATA%.
rem Controlled Folder Access, when switched on, blocks git.exe in Documents
rem (docs\WINDOWS.md). %USERPROFILE% anchors setup.ps1 and settings.py too.
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "HUBDIR=%FLUBNF_HUB%"
if defined HUBDIR goto :hubresolved
set "HUBDIR=%USERPROFILE%\Documents\GitHub\FluSight-forecast-hub"
if exist "%HUBDIR%\." goto :hubresolved
set "HUBDIR=%LOCALAPPDATA%\FluBNF\FluSight-forecast-hub"
:hubresolved
rem Test for DATA (the file settings.py reads), not .git: a --sparse clone
rem holds only the repository root.
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
rem The timeout answers Y: an unattended double-click must end with data.
choice /c YN /n /t 20 /d Y /m "Fetch it now? [Y/N, Y by itself in 20s] "
if errorlevel 2 (
  echo   skipped. Run this whenever you are ready:
  echo   powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
  echo.
  goto :launch
)
echo.
rem -NoProfile: a profile's $ErrorActionPreference would make git stderr fatal.
rem (A Group Policy execution policy can still refuse; the console starts.)
rem -NoPrompt is required: setup.ps1's Perl question has no timeout, and a
rem double-click must never park at a prompt (the engine section below offers
rem Perl with a bounded question).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" -NoPrompt
if errorlevel 1 echo   setup.ps1 reported a problem, see above - starting the console anyway
rem setup.ps1 rewrote .flubnf.env.cmd: re-read it.
if exist ".flubnf.env.cmd" call ".flubnf.env.cmd"

:launch
rem ===== the particle filter engine =========================================
rem Twin of FluBNF.command's engine block. The fork is private, so this never
rem blocks the launch or asks an unbounded question, and never probes
rem github.com (setup.ps1 does, once, with a diagnosis). It installs from an
rem offline file saved where students save files: a git bundle
rem (git bundle create pybnf.bundle feature/particle-filter) or the
rem pybnf-pf-<sha>.tar.gz from scripts/cut_engine_archive.sh.
rem Checkout order mirrors setup.ps1's Resolve-Checkout exactly (a mismatch
rem installs an engine the other cannot find). A location counts if it has
rem \.git or pybnf\pf.py, never if merely present: the bundle clone needs an
rem empty destination.
set "PYBNFDIR=%FLUBNF_PYBNF%"
if not defined PYBNFDIR goto :pybnfprobe
rem Honour the pin only if an engine is there: setup.ps1 records its DEFAULT
rem before anything exists, so a dangling pin is the normal first-run state.
if exist "%PYBNFDIR%\.git" goto :pybnfresolved
if exist "%PYBNFDIR%\pybnf\pf.py" goto :pybnfresolved
:pybnfprobe
set "PYBNFDIR=%USERPROFILE%\Documents\GitHub\PyBNF-pf"
if exist "%PYBNFDIR%\.git" goto :pybnfresolved
if exist "%PYBNFDIR%\pybnf\pf.py" goto :pybnfresolved
set "PYBNFDIR=%LOCALAPPDATA%\FluBNF\PyBNF-pf"
if exist "%PYBNFDIR%\.git" goto :pybnfresolved
if exist "%PYBNFDIR%\pybnf\pf.py" goto :pybnfresolved
set "PYBNFDIR=%USERPROFILE%\Documents\GitHub\PyBNF-Private"
if exist "%PYBNFDIR%\.git" goto :pybnfresolved
if exist "%PYBNFDIR%\pybnf\pf.py" goto :pybnfresolved
set "PYBNFDIR=%LOCALAPPDATA%\FluBNF\PyBNF-Private"
if exist "%PYBNFDIR%\.git" goto :pybnfresolved
if exist "%PYBNFDIR%\pybnf\pf.py" goto :pybnfresolved
rem nothing on disk yet: the default is where setup.ps1 would clone
set "PYBNFDIR=%LOCALAPPDATA%\FluBNF\PyBNF-pf"
:pybnfresolved
set "ENGINEOK="
set "ENGINEVENV=%FLUBNF_ENGINE_VENV%"
if not defined ENGINEVENV set "ENGINEVENV=%USERPROFILE%\.venvs\flubnf-engine"
set "ENGINEPY=%ENGINEVENV%\Scripts\python.exe"

rem Installed? Cheap file tests first, then setup.ps1's import probe, which
rem loads pybnf off the checkout as runners do (the editable install can fail).
if not exist "%ENGINEPY%" goto :engineabsent
rem pf.py, not .git: an unpacked archive satisfies the probe like a clone.
if not exist "%PYBNFDIR%\pybnf\pf.py" goto :engineabsent
"%ENGINEPY%" -c "import sys; sys.path.insert(0, r'%PYBNFDIR%'); import bngsim; from pybnf.pf import ParticleFilter" >nul 2>&1
if errorlevel 1 goto :engineabsent
set "FLUBNF_PY_ENGINE=%ENGINEPY%"
set "FLUBNF_PYBNF=%PYBNFDIR%"
set "ENGINEOK=1"

:engineabsent
rem Search the FluBNF folder, beside it, Downloads, Desktop, Documents. The
rem wildcard catches "pybnf (1).bundle". `if not defined` is evaluated per
rem iteration, so the first match wins.
set "BUNDLE="
if not defined FLUBNF_PYBNF_BUNDLE goto :bundlesearch
if exist "%FLUBNF_PYBNF_BUNDLE%" set "BUNDLE=%FLUBNF_PYBNF_BUNDLE%"
if defined BUNDLE goto :bundleresolved
echo   FLUBNF_PYBNF_BUNDLE names a file that is not there:
echo     "%FLUBNF_PYBNF_BUNDLE%"
echo   looking in the usual places instead
:bundlesearch
for %%F in ("%~dp0pybnf*.bundle") do if not defined BUNDLE set "BUNDLE=%%~fF"
for %%F in ("%~dp0..\pybnf*.bundle") do if not defined BUNDLE set "BUNDLE=%%~fF"
rem OneDrive Known Folder Move relocates these folders: probe both spellings,
rem profile first. Guard each OneDrive probe: an undefined %OneDrive% would
rem match a bare "\Downloads" at the drive root.
for %%F in ("%USERPROFILE%\Downloads\pybnf*.bundle") do if not defined BUNDLE set "BUNDLE=%%~fF"
if defined OneDrive for %%F in ("%OneDrive%\Downloads\pybnf*.bundle") do if not defined BUNDLE set "BUNDLE=%%~fF"
for %%F in ("%USERPROFILE%\Desktop\pybnf*.bundle") do if not defined BUNDLE set "BUNDLE=%%~fF"
if defined OneDrive for %%F in ("%OneDrive%\Desktop\pybnf*.bundle") do if not defined BUNDLE set "BUNDLE=%%~fF"
for %%F in ("%USERPROFILE%\Documents\pybnf*.bundle") do if not defined BUNDLE set "BUNDLE=%%~fF"
if defined OneDrive for %%F in ("%OneDrive%\Documents\pybnf*.bundle") do if not defined BUNDLE set "BUNDLE=%%~fF"
rem The other shape, pybnf-pf-<sha>.tar.gz: same folders, but the NEWEST wins
rem (twin of setup_engine.sh; glob order is arbitrary).
set "ARCHIVE="
set "ARCHIVES=0"
for %%F in ("%~dp0pybnf*.tar.gz") do call :newerarchive "%%~fF"
for %%F in ("%~dp0..\pybnf*.tar.gz") do call :newerarchive "%%~fF"
for %%F in ("%USERPROFILE%\Downloads\pybnf*.tar.gz") do call :newerarchive "%%~fF"
if defined OneDrive for %%F in ("%OneDrive%\Downloads\pybnf*.tar.gz") do call :newerarchive "%%~fF"
for %%F in ("%USERPROFILE%\Desktop\pybnf*.tar.gz") do call :newerarchive "%%~fF"
if defined OneDrive for %%F in ("%OneDrive%\Desktop\pybnf*.tar.gz") do call :newerarchive "%%~fF"
for %%F in ("%USERPROFILE%\Documents\pybnf*.tar.gz") do call :newerarchive "%%~fF"
if defined OneDrive for %%F in ("%OneDrive%\Documents\pybnf*.tar.gz") do call :newerarchive "%%~fF"
:bundleresolved
if %ARCHIVES% GTR 1 echo   %ARCHIVES% engine archives found; using the newest: "%ARCHIVE%"

rem Extract here with Windows' tar (since 10 1803) into LOCALAPPDATA (Controlled
rem Folder Access protects Documents); the pf.py gates below then see a copy.
if not defined ARCHIVE goto :archivedone
if exist "%PYBNFDIR%\.git" goto :archivedone
where tar >nul 2>&1
if errorlevel 1 goto :archivedone
if exist "%PYBNFDIR%\pybnf\pf.py" goto :archivestale
if not exist "%LOCALAPPDATA%\FluBNF" mkdir "%LOCALAPPDATA%\FluBNF"
echo   unpacking the engine from "%ARCHIVE%" - no GitHub account needed
tar -xzf "%ARCHIVE%" -C "%LOCALAPPDATA%\FluBNF"
if exist "%LOCALAPPDATA%\FluBNF\PyBNF-Private\pybnf\pf.py" set "PYBNFDIR=%LOCALAPPDATA%\FluBNF\PyBNF-Private"
if not exist "%PYBNFDIR%\pybnf\pf.py" echo   unpack failed or wrong file; continuing without it
goto :archiveunpacked
:archivestale
rem A newer archive replaces an unpacked copy this launcher made, only if the
rem stamps differ and it is newer than the installed VERSION (no downgrades).
rem The old copy is renamed, never deleted, and put back if the unpack fails.
if /i not "%PYBNFDIR%"=="%LOCALAPPDATA%\FluBNF\PyBNF-Private" goto :archivedone
set "VMEMBER="
set "NEWVER="
set "OLDVER="
for /f "delims=" %%M in ('tar -tzf "%ARCHIVE%" 2^>nul ^| findstr /e /c:"/VERSION"') do if not defined VMEMBER set "VMEMBER=%%M"
if not defined VMEMBER goto :archivedone
for /f "usebackq delims=" %%V in (`tar -xzOf "%ARCHIVE%" "%VMEMBER%" 2^>nul`) do if not defined NEWVER set "NEWVER=%%V"
if not defined NEWVER goto :archivedone
if exist "%PYBNFDIR%\VERSION" set /p OLDVER=<"%PYBNFDIR%\VERSION"
if "%NEWVER%"=="%OLDVER%" goto :archivedone
if not exist "%PYBNFDIR%\VERSION" goto :archivereplace
set "VERFILE=%PYBNFDIR%\VERSION"
powershell -NoProfile -Command "if ((Get-Item -LiteralPath $env:ARCHIVE).LastWriteTimeUtc -gt (Get-Item -LiteralPath $env:VERFILE).LastWriteTimeUtc) { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 goto :archivedone
:archivereplace
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMddHHmmss"') do set "TS=%%T"
set "KEPT=PyBNF-Private.replaced-%TS%"
echo   a different engine archive has arrived: on disk %OLDVER%, archive %NEWVER%
ren "%PYBNFDIR%" "%KEPT%" || goto :archivedone
tar -xzf "%ARCHIVE%" -C "%LOCALAPPDATA%\FluBNF"
if exist "%PYBNFDIR%\pybnf\pf.py" goto :archivereplaced
if exist "%PYBNFDIR%" rd /s /q "%PYBNFDIR%"
ren "%LOCALAPPDATA%\FluBNF\%KEPT%" PyBNF-Private
echo   could not install "%ARCHIVE%"; the copy already on disk is unchanged
goto :archivedone
:archivereplaced
echo   the previous copy is at "%LOCALAPPDATA%\FluBNF\%KEPT%"; delete it once you are happy
:archiveunpacked
rem Print the stamp ("which build"), as macOS does.
if exist "%PYBNFDIR%\VERSION" set /p FLUVER=<"%PYBNFDIR%\VERSION"
if defined FLUVER echo   version stamp: %FLUVER%
:archivedone
if defined ENGINEOK goto :startconsole

rem Nothing to install from: a normal state (analogue works), so no question.
if exist "%PYBNFDIR%\.git" goto :enginestamp
if exist "%PYBNFDIR%\pybnf\pf.py" goto :enginestamp
if defined BUNDLE goto :enginestamp
echo   PF engine not installed (the console runs analogue forecasts only).
echo   The shortcut needs no GitHub account: ask the lab for the engine file
echo   (pybnf-pf-XXXX.tar.gz or pybnf.bundle), save it in your Downloads
echo   folder, and open this again. That is the whole step.
echo   Otherwise run setup.ps1, which explains how to reach the private fork.
goto :startconsole

:enginestamp
rem Do not repeat a failed build every open. Fingerprint = checkout, bundle
rem path + SIZE (a truncated file re-copied under the same name must retry),
rem and this file's and setup.ps1's size+mtime (a pulled fix must retry; the
rem POSIX twin hashes setup_engine.sh). "?" separates: no Windows path has one.
set "BUNDLESZ="
if defined BUNDLE for %%F in ("%BUNDLE%") do set "BUNDLESZ=%%~zF"
set "BATFP="
for %%F in ("%~f0") do set "BATFP=%%~zF-%%~tF"
set "PS1FP="
if exist setup.ps1 for %%F in (setup.ps1) do set "PS1FP=%%~zF-%%~tF"
set "ENGINEFP=%PYBNFDIR%?%BUNDLE%?%BUNDLESZ%?%BATFP%?%PS1FP%"
set "ATTEMPT=.venv\engine-attempt.txt"
set "LAST="
if not exist "%ATTEMPT%" goto :engineinstall
for /f "usebackq delims=" %%L in ("%ATTEMPT%") do set "LAST=%%~L"
if "%LAST%"=="%ENGINEFP%" goto :engineskipped
:engineinstall
echo.
echo Installing the particle filter engine. One time, a few minutes.
rem Perl (BNG2.pl, engine fits only), offered like the data question: 20 s,
rem default Y; without winget, name the link. setup.ps1 cannot ask here (-NoPrompt).
where perl >nul 2>&1
if not errorlevel 1 goto :perldone
where winget >nul 2>&1
if errorlevel 1 (
  echo   perl not found and winget unavailable: the engine installs fine but
  echo   cannot FIT until Perl exists. Install Strawberry Perl by hand from
  echo   https://strawberryperl.com and reopen; nothing else waits on it.
  goto :perldone
)
where choice >nul 2>&1
if errorlevel 1 goto :perlwinget
choice /c YN /n /t 20 /d Y /m "Install Strawberry Perl via winget (engine fits need it)? [Y/N, Y in 20s] "
if errorlevel 2 (
  echo   skipped. Install later from https://strawberryperl.com or rerun setup.ps1.
  goto :perldone
)
:perlwinget
echo   installing Strawberry Perl via winget (one time, a few minutes)...
winget install -e --id StrawberryPerl.StrawberryPerl --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
  echo   winget could not install it; get it from https://strawberryperl.com.
) else (
  echo   Perl installed. NOTE: already-open windows cannot see the new PATH;
  echo   this launcher keeps going, and the first fit picks it up on the next
  echo   open if this one cannot find it.
)
:perldone
where git >nul 2>&1
if errorlevel 1 goto :enginenogit
if exist "%PYBNFDIR%\.git" goto :enginevenv
if exist "%PYBNFDIR%\pybnf\pf.py" goto :enginevenv
echo   cloning from the offline bundle, no GitHub account needed:
echo     "%BUNDLE%"
rem bundle verify reads only the header, so it accepts a truncated copy
rem (git 2.39.5); the clone reports truncation. Different remedies, two labels.
git bundle verify "%BUNDLE%" >nul 2>&1
if errorlevel 1 goto :enginebadbundle
git clone -b feature/particle-filter "%BUNDLE%" "%PYBNFDIR%"
if not exist "%PYBNFDIR%\.git" goto :enginebadclone
rem origin = the bundle file (often removable media): name the fork instead.
git -C "%PYBNFDIR%" remote set-url origin https://github.com/elyfmiller/PyBNF-Private.git >nul 2>&1

:enginevenv
rem Engine venv must be Python 3.11/3.12: numpy<2 wheels stop at cp312, and a
rem source build of numpy hits MAX_PATH. Rebuild a too-new venv; try py 3.12/3.11,
rem then python if it IS 3.11/3.12, else have conda make a 3.12.
if not exist "%ENGINEPY%" goto :enginevenvmake
"%ENGINEPY%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,11),(3,12)) else 1)" >nul 2>&1
if not errorlevel 1 goto :enginedeps
echo   engine venv exists but its Python is too new for the engine's numpy
echo   pin; rebuilding it with Python 3.12
rd /s /q "%ENGINEVENV%" >nul 2>&1
:enginevenvmake
where py >nul 2>&1
if errorlevel 1 goto :enginevenvpython
py -3.12 -m venv "%ENGINEVENV%" >nul 2>&1
if exist "%ENGINEPY%" goto :enginevenvcheck
py -3.11 -m venv "%ENGINEVENV%" >nul 2>&1
if exist "%ENGINEPY%" goto :enginevenvcheck
:enginevenvpython
where python >nul 2>&1
if errorlevel 1 goto :enginevenvconda
python -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,11),(3,12)) else 1)" >nul 2>&1
if errorlevel 1 goto :enginevenvconda
python -m venv "%ENGINEVENV%"
goto :enginevenvcheck
:enginevenvconda
rem CONDAPY is conda's base (maybe too new): use it only if 3.11/3.12.
if not defined CONDAPY goto :enginefailed
"%CONDAPY%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,11),(3,12)) else 1)" >nul 2>&1
if errorlevel 1 goto :enginevenvcondamake
"%CONDAPY%" -m venv "%ENGINEVENV%"
goto :enginevenvcheck
:enginevenvcondamake
set "CONDABAT="
if exist "%USERPROFILE%\anaconda3\condabin\conda.bat"    set "CONDABAT=%USERPROFILE%\anaconda3\condabin\conda.bat"
if not defined CONDABAT if exist "%USERPROFILE%\miniconda3\condabin\conda.bat" set "CONDABAT=%USERPROFILE%\miniconda3\condabin\conda.bat"
if not defined CONDABAT if exist "%LOCALAPPDATA%\anaconda3\condabin\conda.bat" set "CONDABAT=%LOCALAPPDATA%\anaconda3\condabin\conda.bat"
if not defined CONDABAT if exist "C:\ProgramData\anaconda3\condabin\conda.bat" set "CONDABAT=C:\ProgramData\anaconda3\condabin\conda.bat"
if not defined CONDABAT goto :enginefailed
echo   Anaconda's Python is newer than the engine supports; asking conda for
echo   a Python 3.12 (one time, a few minutes)
call "%CONDABAT%" create -y -p "%USERPROFILE%\.venvs\flubnf-engine-py312" python=3.12 >nul
if not exist "%USERPROFILE%\.venvs\flubnf-engine-py312\python.exe" goto :enginefailed
"%USERPROFILE%\.venvs\flubnf-engine-py312\python.exe" -m venv "%ENGINEVENV%"
:enginevenvcheck
if not exist "%ENGINEPY%" goto :enginefailed

:enginedeps
rem Same pins as setup_engine.sh (reasons there); runtime set explicit so the
rem fork goes in --no-deps (its msgpack==0.6.2 pin has no Windows wheel).
"%ENGINEPY%" -m pip install -q --upgrade pip
"%ENGINEVENV%\Scripts\pip" install -q "numpy<2" scipy pandas "bngsim==0.15.1" "dask==2022.12.1" "distributed==2022.12.1" msgpack pyparsing tornado libroadrunner python-libsbml
if errorlevel 1 goto :enginefailed
rem The editable install is known to fail on Windows; the probe is the gate.
"%ENGINEVENV%\Scripts\pip" install -q -e "%PYBNFDIR%" --no-deps
"%ENGINEPY%" -c "import sys; sys.path.insert(0, r'%PYBNFDIR%'); import bngsim; from pybnf.pf import ParticleFilter; print('  PF engine ready, bngsim ' + bngsim.__version__ + ' -- engine ready')"
if errorlevel 1 goto :enginefailed
del "%ATTEMPT%" >nul 2>&1
set "FLUBNF_PY_ENGINE=%ENGINEPY%"
set "FLUBNF_PYBNF=%PYBNFDIR%"
goto :startconsole

:enginebadbundle
echo   That file is not a git bundle at all. git said:
git bundle verify "%BUNDLE%"
echo   A browser that saved an error page under this name does exactly that.
echo   Ask for the file again, or move it out of the way. The console starts
echo   either way.
goto :enginefailed

:enginebadclone
echo   The clone from that bundle failed (git's own output is above).
echo   The usual cause is a copy that did not finish: git reports that as
echo   "early EOF" or "index-pack died", which reads like a broken install
echo   and is really a broken file. Compare its size with the copy you were
echo   given and fetch it again. The other cause is a bundle made from the
echo   wrong branch, which needs a new bundle.
goto :enginefailed

:enginenogit
echo   git is not on PATH, so the engine cannot be installed from here.
echo   Install Git for Windows, then open this again.
goto :enginefailed

:enginefailed
echo   Engine setup did not finish (see above). The console still runs,
echo   analogue forecasts only. It will not retry on every open; a new
echo   bundle, or setup.ps1, starts it again.
rem Quoted on write, %%~L on read: a path may hold & or a trailing digit.
echo "%ENGINEFP%">"%ATTEMPT%"
goto :startconsole

:engineskipped
echo   PF engine still not installed - the last attempt failed and is not
echo   retried on every open. Run setup.ps1 to see why, or delete
echo   "%ATTEMPT%" to try again here. Analogue forecasts work meanwhile.

:startconsole
echo FluBNF console starting - a window (or browser tab) will open. Ctrl-C here to stop.
".venv\Scripts\flubnf" app
set STATUS=%errorlevel%
if "%STATUS%"=="0" exit /b 0
rem 15 = takeover by a newer launch (FluBNF.command treats 143 the same).
if "%STATUS%"=="15" exit /b 0
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
echo Usual causes: no Python found. Install Anaconda (anaconda.com/download,
echo defaults are fine - this launcher finds it with nothing added to PATH),
echo or Python 3.11 or newer - get it from
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

:newerarchive
rem Keep the NEWEST pybnf*.tar.gz (twin of setup_engine.sh): glob order is arbitrary.
set /a ARCHIVES+=1
if defined ARCHIVE goto :newerarchivecmp
set "ARCHIVE=%~f1"
goto :eof
:newerarchivecmp
set "CAND=%~f1"
powershell -NoProfile -Command "if ((Get-Item -LiteralPath $env:CAND).LastWriteTimeUtc -gt (Get-Item -LiteralPath $env:ARCHIVE).LastWriteTimeUtc) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 set "ARCHIVE=%CAND%"
goto :eof
