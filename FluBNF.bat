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
if errorlevel 1 (set "MERGED=") else set "MERGED=1"
goto :updatecheck
rem Lines 1-65 are frozen, byte for byte. cmd.exe reads a batch file as it
rem runs it, and when the merge on line 65 replaces this file it carries on
rem at the same byte offset in the new copy, so an edit up there makes the
rem first open after an update start in the middle of a line. The goto
rem below is pinned too: it starts at byte 4049, where an older copy of
rem this file carries on after it set local edits aside and merged (its
rem line 83). tests\test_windows_launcher.py checks both.
rem Whatever is edited between line 66 and here, the goto below must stay at
rem byte 4049: lengthen or shorten this comment to make up the difference.
goto :updatedaround
rem Every later git call that can replace this file ends its own line with
rem a goto, which looks its label up afresh in the copy on disk. Copies that
rem ran before an update jump to :deps, :uptodate and :updatedaround, so
rem those labels stay.
:updatecheck
rem A branch deleted or renamed upstream keeps its last remote-tracking copy
rem through a plain fetch, and a clone on it read "up to date" for ever.
rem Off main, which is never deleted, fetch again with --prune to find out.
if /I not "%BRANCH%"=="main" git fetch -q --prune origin >nul 2>&1
git rev-parse -q --verify "refs/remotes/origin/%BRANCH%" >nul 2>&1
if errorlevel 1 goto :upstreamgone
if not defined MERGED goto :updateblocked
:uptodate
echo   up to date with origin
goto :deps
:upstreamgone
echo   origin/%BRANCH% no longer exists (the branch was deleted or renamed
echo   upstream), so this copy cannot update - running the copy on disk.
echo   FluBNF ships from main; to follow it:
echo       git -C "%CD%" checkout main
goto :deps
:updateblocked
rem What blocks the fast-forward decides the message, as in FluBNF.command:
rem commits of this clone's own, commits origin rewrote under new ids,
rem tracked edits, or none of those. Commands are printed with this folder
rem in them, one per line: they are pasted into another window (the console
rem holds this one), Command Prompt or PowerShell, and PowerShell 5.1 has
rem no &&.
set "DIRTY="
for /f %%s in ('git status --porcelain -uno 2^>nul') do set "DIRTY=1"
set "AHEAD=0"
for /f "delims=" %%n in ('git rev-list --count origin/%BRANCH%..HEAD 2^>nul') do set "AHEAD=%%n"
if "%AHEAD%"=="0" goto :updatenotahead
set "UNIQUE=%AHEAD%"
for /f "delims=" %%n in ('git rev-list --left-only --cherry-pick --count HEAD...origin/%BRANCH% 2^>nul') do set "UNIQUE=%%n"
if "%UNIQUE%"=="0" goto :updaterewritten
echo   this clone has %AHEAD% commit(s) origin does not, so it cannot
echo   fast-forward. Nothing here will discard them. Running as-is. To take
echo   origin's copy and throw this clone's work away:
echo       git -C "%CD%" fetch origin
echo       git -C "%CD%" reset --hard origin/%BRANCH%
goto :deps
:updaterewritten
rem Every commit here has an equal one upstream: origin rewrote its history,
rem as main's was in September 2026, and this clone has no work of its own.
echo   origin rewrote its history: the %AHEAD% commit(s) here are all upstream
echo   already under new ids, so nothing unique would be lost. Running as-is.
echo   To take origin's copy:
if defined DIRTY echo       git -C "%CD%" stash push -m "FluBNF update"
echo       git -C "%CD%" fetch origin
echo       git -C "%CD%" reset --hard origin/%BRANCH%
goto :deps
:updatenotahead
if defined DIRTY goto :updatedirty
rem A clean tree that still cannot fast-forward: an untracked file upstream
rem now tracks, or a file another program holds open. A stash would save
rem nothing, and the pop after it applied someone's older stash instead, so
rem show git's own reason and the way out.
echo   could not update, running the copy on disk. git says:
git merge --ff-only -q origin/%BRANCH% && goto :uptodate
echo   To take origin's copy whatever is in the way:
echo       git -C "%CD%" fetch origin
echo       git -C "%CD%" reset --hard origin/%BRANCH%
goto :deps
:updatedirty
echo   local edits are blocking the update:
git status --porcelain -uno
rem Put back only a stash this run made, told by refs/stash before and
rem after the push: a push that saved nothing still succeeds, and a pop
rem then applies an older stash of someone's.
set "STASHWAS="
for /f %%s in ('git rev-parse -q --verify refs/stash 2^>nul') do set "STASHWAS=%%s"
git stash push -q -m "FluBNF update" >nul 2>&1 && goto :updatestashed
goto :updatestuck
:updatestashed
set "STASHNOW="
for /f %%s in ('git rev-parse -q --verify refs/stash 2^>nul') do set "STASHNOW=%%s"
git merge --ff-only -q origin/%BRANCH% >nul 2>&1 && goto :updatedaround
if "%STASHNOW%"=="%STASHWAS%" goto :updatestuck
git stash pop -q >nul 2>&1 & goto :updatestuck
:updatedaround
echo   updated anyway - those edits were set aside, not lost. To see them,
echo   and to put them back:
echo       git -C "%CD%" stash list
echo       git -C "%CD%" stash pop
goto :deps
:updatestuck
echo   could not update around them - running the copy on disk. To take
echo   origin's copy and discard the edits above:
echo       git -C "%CD%" fetch origin
echo       git -C "%CD%" reset --hard origin/%BRANCH%

:deps
rem Line 42 goes on without a word when git is missing, and it is one of
rem the frozen lines. A clone made with GitHub Desktop, whose own git is not
rem on PATH, then stayed on its clone-day console with nothing on screen.
if not exist ".git" goto :gitchecked
if /I "%FLUBNF_UPDATE%"=="off" goto :gitchecked
where git >nul 2>&1
if errorlevel 1 echo   FluBNF cannot update itself or the engine without Git for Windows: https://git-scm.com/download/win
:gitchecked
if not exist ".venv\Scripts\flubnf.exe" goto :firstrun
rem A folder moved by hand (setup.ps1 advises it when Controlled Folder
rem Access blocks Documents) keeps a .venv whose .exe launchers name the old
rem python.exe, so flubnf.exe and pip.exe no longer start. pip.exe is the
rem test, run once per folder: a pass is noted in folder.stamp. It and every
rem PowerShell here read from nul: PowerShell waits for input that never
rem comes when it inherits a pipe instead of a console.
set "VENVAT="
if exist ".venv\folder.stamp" set /p VENVAT=<".venv\folder.stamp"
if /I "%VENVAT%"=="%CD%" goto :sync
".venv\Scripts\pip.exe" --version <nul >nul 2>&1
if errorlevel 1 goto :venvmoved
cd >".venv\folder.stamp"
goto :sync
:venvmoved
set "TS="
for /f %%T in ('powershell -NoProfile -NonInteractive -Command "Get-Date -Format yyyyMMddHHmmss" ^<nul') do set "TS=%%T"
if not defined TS set "TS=%RANDOM%"
echo   .venv was built before this folder moved and no longer starts: it is now .venv.moved-%TS%, and setup runs again
ren ".venv" ".venv.moved-%TS%" >nul 2>&1
if not exist ".venv\Scripts\flubnf.exe" goto :firstrun
echo   .venv could not be renamed; a program may have a file in it open. Close it, or delete the .venv folder, and open this again.
goto :fail
:firstrun
echo First run - setting up, a few minutes...
rem venv output goes to a log, not nul, so the failure text shows the real cause.
set "SETUPLOG=%TEMP%\flubnf-firstrun.log"
if exist "%SETUPLOG%" del "%SETUPLOG%" >nul 2>&1
rem 3.12, then 3.11, before whatever is newest: the versions Windows CI tests
rem and setup.ps1 prefers (flubnf doctor calls anything newer untested).
where py >nul 2>&1 && py -3.12 -m venv .venv >>"%SETUPLOG%" 2>&1
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>&1 && py -3.11 -m venv .venv >>"%SETUPLOG%" 2>&1
)
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>&1 && py -3 -m venv .venv >>"%SETUPLOG%" 2>&1
)
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
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" -NoPrompt <nul
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
rem Checkout order mirrors setup.ps1's Resolve-PyBnf and flubnf\settings.py
rem exactly (a mismatch installs an engine the others cannot find). A
rem location counts if it has \.git or pybnf\pf.py, never if merely present:
rem the bundle clone needs an empty destination.
rem What .flubnf.env.cmd or the User environment recorded, kept before this
rem block sets its own: :recordengine writes a verified engine back.
set "PYBNFREC=%FLUBNF_PYBNF%"
set "ENGINEREC=%FLUBNF_PY_ENGINE%"
set "PYBNFDIR=%FLUBNF_PYBNF%"
if not defined PYBNFDIR goto :pybnfprobe
rem A trailing backslash (setx FLUBNF_PYBNF "D:\engines\PyBNF-pf\") would
rem escape the closing quote of every "%PYBNFDIR%" handed to a program.
if "%PYBNFDIR:~-1%"=="\" set "PYBNFDIR=%PYBNFDIR:~0,-1%"
rem Honour the pin only if an engine is there: setup.ps1 from before this
rem check recorded its DEFAULT before anything existed, so a dangling pin is
rem still common on machines set up then.
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
rem Stay current, engine too: FluBNF updates itself above, and this brings a
rem clean engine checkout on the production branch up to the production build
rem (fast-forward only; another branch, local edits or newer commits are left
rem and the reason printed). Twin of FluBNF.command's; FLUBNF_UPDATE=off skips
rem both. The console's build warning repeats the reason.
if /I "%FLUBNF_UPDATE%"=="off" goto :engineupdated
if not exist "%PYBNFDIR%\.git" goto :engineupdated
if not exist ".venv\Scripts\flubnf.exe" goto :engineupdated
where git >nul 2>&1
if errorlevel 1 goto :engineupdated
".venv\Scripts\flubnf.exe" engine-update --quiet --path "%PYBNFDIR%"
:engineupdated
set "ENGINEOK="
set "ENGINEVENV=%FLUBNF_ENGINE_VENV%"
if not defined ENGINEVENV set "ENGINEVENV=%USERPROFILE%\.venvs\flubnf-engine"
set "ENGINEPY=%ENGINEVENV%\Scripts\python.exe"

rem Installed? Cheap file tests first, then setup.ps1's import probe, which
rem loads pybnf off the checkout as runners do (the editable install can fail).
rem The folder goes in as an argument, as setup_engine.sh passes it: spliced
rem into r'...', an apostrophe in a profile name (O'Neil) was a SyntaxError
rem that read as "not installed".
if not exist "%ENGINEPY%" goto :engineabsent
rem pf.py, not .git: an unpacked archive satisfies the probe like a clone.
if not exist "%PYBNFDIR%\pybnf\pf.py" goto :engineabsent
"%ENGINEPY%" -c "import sys; sys.path.insert(0, sys.argv[1]); import bngsim; from pybnf.pf import ParticleFilter" "%PYBNFDIR%" >nul 2>&1
if errorlevel 1 goto :engineabsent
set "FLUBNF_PY_ENGINE=%ENGINEPY%"
set "FLUBNF_PYBNF=%PYBNFDIR%"
set "ENGINEOK=1"
call :recordengine

:engineabsent
rem Search the FluBNF folder, beside it, Downloads, Desktop, Documents. The
rem wildcard catches "pybnf (1).bundle". `if not defined` is evaluated per
rem iteration, so the first match wins.
rem All three are set before the FLUBNF_PYBNF_BUNDLE shortcut: skipping them
rem left ARCHIVES unset, and `if %ARCHIVES% GTR 1` below is then an IF syntax
rem error that ends the launcher before the console starts, on every open.
set "BUNDLE="
set "ARCHIVE="
set "ARCHIVES=0"
if not defined FLUBNF_PYBNF_BUNDLE goto :bundlesearch
if not exist "%FLUBNF_PYBNF_BUNDLE%" goto :bundlenamedmissing
rem Either shape can be named; a .tar.gz is an archive, as in setup_engine.sh.
if /I "%FLUBNF_PYBNF_BUNDLE:~-7%"==".tar.gz" goto :bundlenamedarchive
set "BUNDLE=%FLUBNF_PYBNF_BUNDLE%"
goto :bundleresolved
:bundlenamedarchive
set "ARCHIVE=%FLUBNF_PYBNF_BUNDLE%"
set "ARCHIVES=1"
goto :bundleresolved
:bundlenamedmissing
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
powershell -NoProfile -NonInteractive -Command "if ((Get-Item -LiteralPath $env:ARCHIVE).LastWriteTimeUtc -gt (Get-Item -LiteralPath $env:VERFILE).LastWriteTimeUtc) { exit 0 } else { exit 1 }" <nul >nul 2>&1
if errorlevel 1 goto :archivedone
:archivereplace
for /f %%T in ('powershell -NoProfile -NonInteractive -Command "Get-Date -Format yyyyMMddHHmmss" ^<nul') do set "TS=%%T"
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

rem Anything here to install from: a checkout, an unpacked copy, a bundle, or
rem an archive (one that did not unpack is still the file to retry with).
set "ENGINELOCAL="
if exist "%PYBNFDIR%\.git" set "ENGINELOCAL=1"
if exist "%PYBNFDIR%\pybnf\pf.py" set "ENGINELOCAL=1"
if defined BUNDLE set "ENGINELOCAL=1"
if defined ARCHIVE set "ENGINELOCAL=1"
rem A failed attempt is stamped with a fingerprint: checkout, bundle and
rem archive path + SIZE (a truncated file re-copied under the same name must
rem retry), and this file's and setup.ps1's size+mtime (a pulled fix must
rem retry; the POSIX twin hashes setup_engine.sh). "?" separates: no Windows
rem path has one.
set "BUNDLESZ="
if defined BUNDLE for %%F in ("%BUNDLE%") do set "BUNDLESZ=%%~zF"
set "ARCHIVESZ="
if defined ARCHIVE for %%F in ("%ARCHIVE%") do set "ARCHIVESZ=%%~zF"
set "BATFP="
for %%F in ("%~f0") do set "BATFP=%%~zF-%%~tF"
set "PS1FP="
if exist setup.ps1 for %%F in (setup.ps1) do set "PS1FP=%%~zF-%%~tF"
set "ENGINEFP=%PYBNFDIR%?%BUNDLE%?%BUNDLESZ%?%ARCHIVE%?%ARCHIVESZ%?%BATFP%?%PS1FP%"
set "ATTEMPT=%CD%\.venv\engine-attempt.txt"
rem The stamp is honoured only when nothing local exists, as in
rem FluBNF.command: with an engine file or checkout here, a failure may have
rem been the network (pip on lab Wi-Fi), and a stamp kept such a machine on
rem analogue forecasts until someone found the file and deleted it.
if defined ENGINELOCAL goto :engineinstall
set "LAST="
if exist "%ATTEMPT%" for /f "usebackq delims=" %%L in ("%ATTEMPT%") do set "LAST=%%~L"
if "%LAST%"=="%ENGINEFP%" goto :engineskipped
rem Nothing to install from: a normal state (analogue works), so no question.
echo   PF engine not installed (the console runs analogue forecasts only).
echo   The shortcut needs no GitHub account: ask the lab for the engine file
echo   (pybnf-pf-XXXX.tar.gz or pybnf.bundle), save it in your Downloads
echo   folder, and open this again. That is the whole step.
echo   Otherwise run setup.ps1, which explains how to reach the private fork.
goto :startconsole

:engineinstall
rem An archive that did not unpack is all there is: say why, and skip the
rem Perl question, which nothing here would use.
if not exist "%PYBNFDIR%\.git" if not exist "%PYBNFDIR%\pybnf\pf.py" if not defined BUNDLE goto :enginebadarchive
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
if exist "%PYBNFDIR%\.git" goto :enginevenv
if exist "%PYBNFDIR%\pybnf\pf.py" goto :enginevenv
rem Only the bundle clone needs git: an archive unpacks with Windows' tar.
where git >nul 2>&1
if errorlevel 1 goto :enginenogit
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
"%ENGINEPY%" -c "import sys; sys.path.insert(0, sys.argv[1]); import bngsim; from pybnf.pf import ParticleFilter; print('  PF engine ready, bngsim ' + bngsim.__version__ + ' -- engine ready')" "%PYBNFDIR%"
if errorlevel 1 goto :enginefailed
del "%ATTEMPT%" >nul 2>&1
set "FLUBNF_PY_ENGINE=%ENGINEPY%"
set "FLUBNF_PYBNF=%PYBNFDIR%"
call :recordengine
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

:enginebadarchive
echo   The engine archive did not unpack:
echo     "%ARCHIVE%"
where tar >nul 2>&1
if errorlevel 1 goto :enginenotar
echo   A copy that did not finish downloading does this: compare its size
echo   with the one you were given, and fetch it again.
goto :enginefailed

:enginenotar
echo   This Windows has no tar.exe, which Windows 10 has from version 1803
echo   on. Update Windows, or ask the lab for pybnf.bundle instead.
goto :enginefailed

:enginenogit
echo   git is not on PATH, so the engine cannot be cloned from the bundle.
echo   Install Git for Windows (https://git-scm.com/download/win), or ask the
echo   lab for pybnf-pf-XXXX.tar.gz, which needs no git; then open this again.
goto :enginefailed

:enginefailed
echo   Engine setup did not finish (see above). The console still runs,
echo   analogue forecasts only. With the engine file still in your Downloads
echo   folder, or the engine folder still in place, the next open tries again.
rem Quoted on write, %%~L on read: a path may hold & or a trailing digit.
echo "%ENGINEFP%">"%ATTEMPT%"
goto :startconsole

:engineskipped
echo   PF engine still not installed: the last attempt failed, and nothing to
echo   install from is here now. Save the engine file (pybnf-pf-XXXX.tar.gz or
echo   pybnf.bundle) in your Downloads folder and open this again; it tries
echo   again by itself. Analogue forecasts work meanwhile. That attempt is
echo   recorded in "%ATTEMPT%"

:startconsole
rem Findable without the path: this folder sits in hidden AppData, so
rem scripts\windows\shortcuts.ps1 puts FluBNF in the Start menu (type FluBNF
rem in the Windows search box; right-click to pin it) and, once per account,
rem on the Desktop. It runs only when the Start menu shortcut is missing or
rem opens another folder, so a normal open costs two file tests.
rem FLUBNF_SHORTCUTS=off skips it.
if /I "%FLUBNF_SHORTCUTS%"=="off" goto :shortcutsdone
set "SHORTCUTFOR="
if exist "%LOCALAPPDATA%\FluBNF\start-menu.txt" set /p SHORTCUTFOR=<"%LOCALAPPDATA%\FluBNF\start-menu.txt"
if not exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\FluBNF.lnk" goto :shortcutsmake
if /I "%SHORTCUTFOR%"=="%CD%" goto :shortcutsdone
:shortcutsmake
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%CD%\scripts\windows\shortcuts.ps1" <nul
:shortcutsdone
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

:recordengine
rem A verified engine is written back where the record says otherwise.
rem setup.ps1 records its default before any engine exists, and flubnf
rem doctor, the CLI and setup.ps1 in another window follow the record, not
rem this launcher (the console started here is told directly). Nothing
rem recorded stays unrecorded: the folder then came from the search above,
rem which settings.py repeats by the same names in the same order, so a
rem normal machine gets no setx and no message. In .flubnf.env.cmd a later
rem set wins, so lines are appended rather than rewritten.
set "RECPYBNF="
set "RECENGINE="
if defined PYBNFREC if /I not "%PYBNFREC%"=="%PYBNFDIR%" set "RECPYBNF=1"
if defined ENGINEREC if /I not "%ENGINEREC%"=="%ENGINEPY%" set "RECENGINE=1"
if not defined RECPYBNF if not defined RECENGINE goto :eof
if not exist ".flubnf.env.cmd" goto :recordenginesetx
echo rem FluBNF.bat verified the engine below; a later set wins.>>".flubnf.env.cmd"
if defined RECPYBNF echo set "FLUBNF_PYBNF=%PYBNFDIR%">>".flubnf.env.cmd"
if defined RECENGINE echo set "FLUBNF_PY_ENGINE=%ENGINEPY%">>".flubnf.env.cmd"
:recordenginesetx
if defined RECPYBNF setx FLUBNF_PYBNF "%PYBNFDIR%" >nul 2>&1
if defined RECENGINE setx FLUBNF_PY_ENGINE "%ENGINEPY%" >nul 2>&1
if defined RECPYBNF echo   recorded for flubnf doctor and new windows: FLUBNF_PYBNF="%PYBNFDIR%"
if defined RECENGINE echo   recorded for flubnf doctor and new windows: FLUBNF_PY_ENGINE="%ENGINEPY%"
goto :eof

:newerarchive
rem Keep the NEWEST pybnf*.tar.gz (twin of setup_engine.sh): glob order is arbitrary.
set /a ARCHIVES+=1
if defined ARCHIVE goto :newerarchivecmp
set "ARCHIVE=%~f1"
goto :eof
:newerarchivecmp
set "CAND=%~f1"
powershell -NoProfile -NonInteractive -Command "if ((Get-Item -LiteralPath $env:CAND).LastWriteTimeUtc -gt (Get-Item -LiteralPath $env:ARCHIVE).LastWriteTimeUtc) { exit 0 } else { exit 1 }" <nul >nul 2>&1
if not errorlevel 1 set "ARCHIVE=%CAND%"
goto :eof
