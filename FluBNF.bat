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
rem Anaconda, found once and here, for the first run and the engine alike.
rem CONDAPY and CONDABAT come from one root, and a folder counts as one only
rem with both python.exe and condabin\conda.bat in it (an environment made
rem with conda create has the first and never the second). Lines 25-29 know
rem four folders and are frozen; what they found is replaced here. In order:
rem CONDA_EXE, which Anaconda Prompt sets, so FluBNF.bat run from there
rem finds conda wherever it is; then %USERPROFILE%\.conda\environments.txt,
rem where conda's installer records the folder it installed to; then the
rem usual folders. Those are the installers' defaults for Just Me, a domain
rem account and All Users, for Miniconda and Miniforge too, and
rem %SystemDrive%\anaconda3 and \anaconda: with a space in the profile
rem folder's name the installer refuses its default, and Anaconda's FAQ
rem suggests those two.
set "CONDAROOT="
if defined CONDA_EXE for %%R in ("%CONDA_EXE%\..\..") do if exist "%%~fR\python.exe" if exist "%%~fR\condabin\conda.bat" set "CONDAROOT=%%~fR"
if not defined CONDAROOT if exist "%USERPROFILE%\.conda\environments.txt" for /f "usebackq delims=" %%E in ("%USERPROFILE%\.conda\environments.txt") do if not defined CONDAROOT if exist "%%E\python.exe" if exist "%%E\condabin\conda.bat" set "CONDAROOT=%%E"
for %%R in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%LOCALAPPDATA%\anaconda3" "%ProgramData%\anaconda3" "%LOCALAPPDATA%\miniconda3" "%ProgramData%\miniconda3" "%USERPROFILE%\miniforge3" "%SystemDrive%\anaconda3" "%SystemDrive%\anaconda") do if not defined CONDAROOT if exist "%%~R\python.exe" if exist "%%~R\condabin\conda.bat" set "CONDAROOT=%%~R"
set "CONDAPY="
set "CONDABAT="
if defined CONDAROOT set "CONDAPY=%CONDAROOT%\python.exe"
if defined CONDAROOT set "CONDABAT=%CONDAROOT%\condabin\conda.bat"
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
rem Refresh deps only when pyproject.toml changed (the package is editable),
rem or when BioNetGen is missing. :firstrun installs it in the same pip call
rem as flubnf, and pip puts flubnf.exe in before the Jupyter stack bionetgen
rem brings: a first run closed in its last minutes left a .venv that skipped
rem :firstrun from then on, with no BNG2.pl for Check or the Sandbox.
rem Never reinstall on every open otherwise: an interrupted one left no
rem launcher.
if not exist ".venv\Lib\site-packages\bionetgen\bng-win\BNG2.pl" goto :syncbng
fc /b pyproject.toml ".venv\pyproject.stamp" >nul 2>&1
if not errorlevel 1 goto :data
echo   project dependencies changed, refreshing, about a minute
goto :syncpip
:syncbng
echo   BioNetGen (BNG2.pl) is missing from .venv; installing it, a few minutes
:syncpip
".venv\Scripts\pip" install -q -e ".[app,dev]" bionetgen
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
rem double-click must never park at a prompt (:perlblock, at the end of this
rem file, asks about Perl with a bounded question).
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
rem A trailing backslash (typed in the Environment Variables dialog, or set
rem from PowerShell) would escape the closing quote of every "%PYBNFDIR%"
rem handed to a program.
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
rem Cleaned as FLUBNF_PYBNF is above. A trailing backslash reached venv as
rem D:\venvs\flubnf-engine" (it escapes the closing quote), so the venv was
rem never made, on every open. A stray quote, which setx in Command Prompt
rem stores for "D:\venvs\flubnf-engine\", made the IFs below a syntax error
rem that closed this window.
set "ENGINEVENV=%ENGINEVENV:"=%"
if "%ENGINEVENV:~-1%"=="\" set "ENGINEVENV=%ENGINEVENV:~0,-1%"
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
rem (twin of setup_engine.sh; glob order is arbitrary). That name only: PyPI's
rem pybnf-<version>.tar.gz and GitHub's PyBNF-<version>.tar.gz are not the
rem engine, and either one saved after the lab's file used to win.
for %%F in ("%~dp0pybnf-pf-*.tar.gz") do call :newerarchive "%%~fF"
for %%F in ("%~dp0..\pybnf-pf-*.tar.gz") do call :newerarchive "%%~fF"
for %%F in ("%USERPROFILE%\Downloads\pybnf-pf-*.tar.gz") do call :newerarchive "%%~fF"
if defined OneDrive for %%F in ("%OneDrive%\Downloads\pybnf-pf-*.tar.gz") do call :newerarchive "%%~fF"
for %%F in ("%USERPROFILE%\Desktop\pybnf-pf-*.tar.gz") do call :newerarchive "%%~fF"
if defined OneDrive for %%F in ("%OneDrive%\Desktop\pybnf-pf-*.tar.gz") do call :newerarchive "%%~fF"
for %%F in ("%USERPROFILE%\Documents\pybnf-pf-*.tar.gz") do call :newerarchive "%%~fF"
if defined OneDrive for %%F in ("%OneDrive%\Documents\pybnf-pf-*.tar.gz") do call :newerarchive "%%~fF"
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
set "NEWVER="
set "OLDVER="
rem Both stamps are read with for /f, never set /p. VERSION is cut on a Mac
rem with LF line ends: set /p took all three lines, and the line breaks it
rem kept cut the IF below short, a syntax error that closed the window
rem before the console started, on every open with the file in Downloads.
rem for /f splits on LF. The archive's is read by name: the unpack above
rem accepts only PyBNF-Private, and a literal name works in bsdtar and GNU
rem tar alike.
for /f "usebackq delims=" %%V in (`tar -xzOf "%ARCHIVE%" PyBNF-Private/VERSION 2^>nul`) do if not defined NEWVER set "NEWVER=%%V"
if not defined NEWVER goto :archivedone
if exist "%PYBNFDIR%\VERSION" for /f "usebackq delims=" %%V in ("%PYBNFDIR%\VERSION") do if not defined OLDVER set "OLDVER=%%V"
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
rem ENGINEOK came from probing the copy just set aside, so the new one is
rem probed the same way. If it imports, ENGINEOK stays: the packages are this
rem file's pins and are already in the venv, and the editable install points
rem at this same folder. Sending it through pip told a network without PyPI
rem the engine was missing while the console ran it. If it does not import,
rem it goes through pip and the probe below. Compared with 0, as at the gate:
rem a crash exits negative, which `if errorlevel 1` reads as success.
if not defined ENGINEOK goto :archiveunpacked
"%ENGINEPY%" -c "import sys; sys.path.insert(0, sys.argv[1]); import bngsim; from pybnf.pf import ParticleFilter" "%PYBNFDIR%" <nul >nul 2>&1
if not "%ERRORLEVEL%"=="0" set "ENGINEOK="
:archiveunpacked
rem Print the stamp ("which build"), as macOS does: its first line, read
rem with for /f as in :archivestale.
set "FLUVER="
if exist "%PYBNFDIR%\VERSION" for /f "usebackq delims=" %%V in ("%PYBNFDIR%\VERSION") do if not defined FLUVER set "FLUVER=%%V"
if defined FLUVER echo   version stamp: %FLUVER%
:archivedone
rem A working engine goes straight to the console, Perl checked on the way:
rem an engine that imports says nothing about the Perl BNG2.pl needs.
if defined ENGINEOK call :perlblock
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
call :enginelookedin "%~dp0."
rem Perl all the same: the Sandbox's Check runs BNG2.pl with no engine.
call :perlblock
goto :startconsole

:engineinstall
rem An archive that did not unpack is all there is: say why. Perl is
rem checked there as well (:enginebadarchive).
if not exist "%PYBNFDIR%\.git" if not exist "%PYBNFDIR%\pybnf\pf.py" if not defined BUNDLE goto :enginebadarchive
echo.
if exist "%ATTEMPT%" (
  echo Trying the particle filter engine install again, a few minutes.
) else (
  echo Installing the particle filter engine. One time, a few minutes.
)
rem Perl before the install, while whoever opened this is more likely to be
rem watching: the install takes minutes, and Perl's permission prompt wants
rem a click. setup.ps1 cannot ask here (-NoPrompt).
call :perlblock
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
rem The engine venv needs 64-bit (x64) Python 3.11 or 3.12: numpy<2 wheels
rem stop at cp312 and a source build of numpy hits MAX_PATH, and numpy<2,
rem bngsim and libroadrunner have Windows wheels for x64 only, so with an
rem ARM64 or 32-bit Python pip ended in a compiler error, on every open.
rem Every Python below passes one gate, ENGINEGATE, before it is used: py
rem 3.12, py 3.11, python if it is one, conda's base, else conda makes a
rem 3.12. The gate prints what it found, one line each, so a miss says why.
rem It exits 0 for usable, 2 for another version, 3 for 3.11 or 3.12 built
rem for another processor. Any other code means the program did not start:
rem 9009 not found, 103 a venv whose base Python is gone, a negative number
rem for a crash, which `if errorlevel 1` read as success.
set "ENGINEGATE=import sys, sysconfig; v = sys.version_info; p = sysconfig.get_platform(); ok = v[:2] in ((3,11),(3,12)); x = p == 'win-amd64'; print('    ' + sys.argv[1] + ': Python ' + '.'.join(map(str, v[:3])) + ' (' + p + ')' + ('' if ok and x else ', not the x64 build the engine needs' if ok else ', the engine needs 3.12 or 3.11')); raise SystemExit(0 if ok and x else 3 if ok else 2)"
if not exist "%ENGINEPY%" goto :enginevenvmake
"%ENGINEPY%" -c "%ENGINEGATE%" "the engine venv" <nul 2>nul
set "GATE=%ERRORLEVEL%"
if "%GATE%"=="2" goto :enginevenvrebuild
if "%GATE%"=="3" goto :enginevenvrebuild
if not "%GATE%"=="0" goto :enginevenvgone
rem pip too: a venv whose ensurepip never finished (the window closed during
rem it, antivirus) has python.exe and no pip, and every open ended at "No
rem module named pip".
"%ENGINEPY%" -m pip --version <nul >nul 2>&1
if "%ERRORLEVEL%"=="0" goto :enginedeps
echo   the engine venv has no pip: an install closed part way, or antivirus
echo   removed it
goto :enginevenvrebuild
:enginevenvgone
rem Not "too new": the venv points at a Python that is no longer there.
echo   the engine venv's Python does not start: the Python it was made from
echo   was removed or moved
:enginevenvrebuild
echo   rebuilding the engine venv: "%ENGINEVENV%"
rd /s /q "%ENGINEVENV%" >nul 2>&1
if not exist "%ENGINEPY%" goto :enginevenvmake
echo   It could not be deleted: a program still has a file in it open. Close
echo   every other FluBNF window, or restart Windows, then open FluBNF again.
goto :enginefailed
:enginevenvmake
rem The chosen Python is a program and its argument, kept apart: a path is
rem quoted where it is used, and a profile name may hold & or brackets.
echo   looking for a Python for the engine, 64-bit (x64) 3.12 or 3.11:
set "MAKEEXE="
set "MAKEARG="
where py >nul 2>&1
if errorlevel 1 goto :enginevenvnopy
py -3.12 -c "%ENGINEGATE%" "py -3.12" <nul 2>nul
set "GATE=%ERRORLEVEL%"
if "%GATE%"=="0" set "MAKEEXE=py"
if "%GATE%"=="0" set "MAKEARG=-3.12"
if defined MAKEEXE goto :enginevenvcreate
if not "%GATE%"=="2" if not "%GATE%"=="3" echo     py -3.12: not installed
py -3.11 -c "%ENGINEGATE%" "py -3.11" <nul 2>nul
set "GATE=%ERRORLEVEL%"
if "%GATE%"=="0" set "MAKEEXE=py"
if "%GATE%"=="0" set "MAKEARG=-3.11"
if defined MAKEEXE goto :enginevenvcreate
if not "%GATE%"=="2" if not "%GATE%"=="3" echo     py -3.11: not installed
goto :enginevenvpython
:enginevenvnopy
echo     py, the Python launcher: not installed
:enginevenvpython
where python >nul 2>&1
if errorlevel 1 goto :enginevenvnopython
python -c "%ENGINEGATE%" "python" <nul 2>nul
set "GATE=%ERRORLEVEL%"
if "%GATE%"=="0" set "MAKEEXE=python"
if defined MAKEEXE goto :enginevenvcreate
rem The Microsoft Store's python.exe stand-in is on PATH with no Python
rem installed: it exits 9009.
if not "%GATE%"=="2" if not "%GATE%"=="3" echo     python: on PATH, but it does not run
goto :enginevenvconda
:enginevenvnopython
echo     python: not on PATH
:enginevenvconda
if not defined CONDAPY goto :enginevenvnoconda
"%CONDAPY%" -c "%ENGINEGATE%" "Anaconda at %CONDAROOT%" <nul 2>nul
set "GATE=%ERRORLEVEL%"
if "%GATE%"=="0" set "MAKEEXE=%CONDAPY%"
if defined MAKEEXE goto :enginevenvcreate
if not "%GATE%"=="2" if not "%GATE%"=="3" echo     Anaconda in "%CONDAROOT%": its python.exe does not run
rem Anaconda's own Python is usually newer (3.14 in Anaconda 2026.07), so
rem conda makes a 3.12 beside the engine venv. CONDA_SUBDIR=win-64 asks for
rem the x64 build whatever conda takes this PC to be: on an ARM laptop,
rem conda 26.3 to 26.6, itself x64 under emulation, said win-arm64 and made
rem an ARM64 Python that no engine wheel exists for. Set for this call only,
rem so the console does not inherit it. conda's output shows: when this
rem fails, its own words are the cause. It reads from nul: a question of
rem conda's (Anaconda's Terms of Service) ends unanswered instead of
rem waiting for someone who is not there.
set "CONDAENV=%USERPROFILE%\.venvs\flubnf-engine-py312"
echo   asking conda for a 64-bit (x64) Python 3.12, one time, a few minutes
setlocal
set "CONDA_SUBDIR=win-64"
call "%CONDABAT%" create -y -p "%CONDAENV%" python=3.12 <nul
endlocal
if not exist "%CONDAENV%\python.exe" goto :enginecondafailed
"%CONDAENV%\python.exe" -c "%ENGINEGATE%" "conda's new Python" <nul 2>nul
if "%ERRORLEVEL%"=="0" set "MAKEEXE=%CONDAENV%\python.exe"
if defined MAKEEXE goto :enginevenvcreate
:enginecondafailed
echo   conda did not make a Python the engine can use; its own messages are
echo   above. When they name a command to run (conda tos accept ...), run it
echo   in Anaconda Prompt, then open FluBNF again.
goto :enginefailed
:enginevenvnoconda
echo     Anaconda: not found (FluBNF looks in its installer's usual folders,
echo     and where CONDA_EXE points when it runs from Anaconda Prompt)
rem Nothing usable, so the cause and one step that works here. py install
rem only with the Python install manager: the older py.exe takes "install"
rem for a script to run. On an ARM laptop, Anaconda: its installer is x64,
rem the conda route above asks for x64, and Windows runs both under
rem emulation, while py install there may pick the ARM64 build.
echo   No Python on this PC can run the engine: it needs 64-bit (x64) Python
echo   3.12 or 3.11.
set "ARMPC="
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ARMPC=1"
if /i "%PROCESSOR_ARCHITEW6432%"=="ARM64" set "ARMPC=1"
if defined ARMPC goto :enginevenvarm
where pymanager >nul 2>&1
if errorlevel 1 goto :enginevenvanaconda
echo   To add one, run this in Command Prompt, then open FluBNF again:
echo       py install 3.12
goto :enginefailed
:enginevenvarm
echo   This PC has an ARM processor: the engine runs on the x64 build, which
echo   Windows runs under emulation.
:enginevenvanaconda
echo   To add one, install Anaconda (anaconda.com/download; the defaults are
echo   fine) and open FluBNF again. If Anaconda is installed already, open
echo   Anaconda Prompt from the Start menu and run FluBNF.bat from there:
echo       "%~f0"
goto :enginefailed
:enginevenvcreate
rem venv's own output shows: nothing when all goes well, the cause when not.
"%MAKEEXE%" %MAKEARG% -m venv "%ENGINEVENV%"
if exist "%ENGINEPY%" goto :enginevenvmade
echo   Python could not make the engine venv in "%ENGINEVENV%"; its error is
echo   above. Most often the disk is full: free about 1 GB, then open FluBNF
echo   again.
goto :enginefailed
:enginevenvmade
"%ENGINEPY%" -m pip --version <nul >nul 2>&1
if "%ERRORLEVEL%"=="0" goto :enginedeps
rem venv ran ensurepip and it failed, out of sight: again, for its reason.
echo   the new engine venv has no pip; asking Python for it once more:
"%ENGINEPY%" -m ensurepip --upgrade --default-pip <nul
"%ENGINEPY%" -m pip --version <nul >nul 2>&1
if "%ERRORLEVEL%"=="0" goto :enginedeps
echo   pip would not go into the engine venv; Python's message is above.
echo   Antivirus holding pip's files and a full disk are the usual causes:
echo   allow "%ENGINEVENV%" in the antivirus, or free some space, then open
echo   FluBNF again.
goto :enginefailed

:enginedeps
rem Same pins as setup_engine.sh (reasons there); runtime set explicit so the
rem fork goes in --no-deps (its msgpack==0.6.2 pin has no Windows wheel).
rem pip through python -m, never Scripts\pip.exe: that is a launcher
rem antivirus can take, and a venv without one read "not recognized".
rem First five seconds at the package index, through pip so pip.ini's index
rem and proxy count. On a network that drops PyPI's traffic pip's retries
rem took minutes, twice an open, then said "no matching distribution",
rem which does not say "network".
"%ENGINEPY%" -m pip index versions numpy --retries 0 --timeout 5 --disable-pip-version-check <nul >nul 2>&1
if "%ERRORLEVEL%"=="0" goto :engineindex
echo   This network does not reach the Python package index (pypi.org), and
echo   the engine needs it once, for its packages. Open FluBNF again on
echo   another network: home Wi-Fi, or a phone's hotspot.
goto :enginefailed
:engineindex
rem Without -q pip shows what it fetches: minutes of a window that did not
rem change invited closing it. Not upgraded first: the pip a venv comes with
rem installs every wheel here.
echo   downloading about 100 MB of packages and installing them, usually 2 to
echo   5 minutes; leave this window open
"%ENGINEPY%" -m pip install --disable-pip-version-check "numpy<2" scipy pandas "bngsim==0.15.1" "dask==2022.12.1" "distributed==2022.12.1" msgpack pyparsing tornado libroadrunner python-libsbml
if "%ERRORLEVEL%"=="0" goto :enginepip
echo   pip could not install the engine's packages; its error is above. If
echo   the connection dropped, open FluBNF again: pip reuses what it already
echo   downloaded.
goto :enginefailed
:enginepip
rem The editable install is known to fail on Windows; the probe is the gate.
"%ENGINEPY%" -m pip install -q --disable-pip-version-check -e "%PYBNFDIR%" --no-deps
rem Compiled first, warnings off: the probe is the first import of a fresh
rem unpack, and the fork's "\d" regexes printed about 25 SyntaxWarnings
rem right above "engine ready".
"%ENGINEPY%" -W ignore -m compileall -q "%PYBNFDIR%\pybnf" <nul >nul 2>&1
"%ENGINEPY%" -c "import sys; sys.path.insert(0, sys.argv[1]); import bngsim; from pybnf.pf import ParticleFilter; print('  PF engine ready, bngsim ' + bngsim.__version__ + ' -- engine ready')" "%PYBNFDIR%"
if not "%ERRORLEVEL%"=="0" goto :engineprobefailed
del "%ATTEMPT%" >nul 2>&1
set "FLUBNF_PY_ENGINE=%ENGINEPY%"
set "FLUBNF_PYBNF=%PYBNFDIR%"
call :recordengine
goto :startconsole

:engineprobefailed
echo   The engine's packages are installed, but the engine does not load;
echo   Python's error is above.
rem libroadrunner's _roadrunner.pyd imports MSVCP140.dll and ships none: a
rem conda Python brings one, python.org's does not. Keyed on the file, not
rem the error text, which antivirus or a damaged wheel can give as well.
if not exist "%SystemRoot%\System32\msvcp140.dll" goto :enginevcruntime
for %%V in ("%ENGINEVENV%") do set "VENVLEAF=%%~nxV"
echo   For a fresh install, rename the engine venv, then open FluBNF again:
echo       ren "%ENGINEVENV%" "%VENVLEAF%-old"
echo   If it happens again, send the lines above to the lab.
goto :enginefailed
:enginevcruntime
echo   This PC lacks the Microsoft Visual C++ runtime (msvcp140.dll is not
echo   in Windows\System32), which the engine's simulator needs. Install the
echo   Visual C++ Redistributable for x64 from
echo   https://aka.ms/vc14/vc_redist.x64.exe (it asks an administrator), then
echo   open FluBNF again.
goto :enginefailed

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
rem Perl as on every open; then what went wrong with the engine file.
call :perlblock
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
call :enginelookedin "%~dp0."
call :perlblock

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
rem The record is written here, by cmd, so it reads back in the code page
rem cmd uses (an accented profile name would never match one PowerShell wrote).
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\FluBNF.lnk" cd >"%LOCALAPPDATA%\FluBNF\start-menu.txt"
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
echo Anaconda installed in a folder this launcher does not know? Open
echo Anaconda Prompt from the Start menu and run FluBNF.bat from there.
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

:enginelookedin
rem Every folder the engine-file search looks in, spelled out: a Downloads
rem folder moved elsewhere (Properties, Location) or a file saved one folder
rem down was a miss with nothing on screen to say where the file should go.
rem The argument is this file's folder, passed in from the main body.
echo   Looked for pybnf-pf-*.tar.gz and pybnf*.bundle in:
for %%D in ("%~1" "%~1\.." "%USERPROFILE%\Downloads" "%USERPROFILE%\Desktop" "%USERPROFILE%\Documents") do echo     %%~fD
if defined OneDrive for %%D in ("%OneDrive%\Downloads" "%OneDrive%\Desktop" "%OneDrive%\Documents") do echo     %%~fD
echo   (each folder itself, not the folders inside it)
goto :eof

:newerarchive
rem Keep the NEWEST pybnf-pf-*.tar.gz (twin of setup_engine.sh): glob order is arbitrary.
set /a ARCHIVES+=1
if defined ARCHIVE goto :newerarchivecmp
set "ARCHIVE=%~f1"
goto :eof
:newerarchivecmp
set "CAND=%~f1"
powershell -NoProfile -NonInteractive -Command "if ((Get-Item -LiteralPath $env:CAND).LastWriteTimeUtc -gt (Get-Item -LiteralPath $env:ARCHIVE).LastWriteTimeUtc) { exit 0 } else { exit 1 }" <nul >nul 2>&1
if not errorlevel 1 set "ARCHIVE=%CAND%"
goto :eof

:perlblock
rem Perl, for BNG2.pl: the Sandbox's Check and contact map run it with no
rem engine, and every fit runs it. Called on every open: from the engine
rem install, the ENGINEOK jump and the paths with no engine. The offer used
rem to live inside the engine install alone, so once the engine imported, or
rem after an engine file that did not unpack, no open said a word about
rem Perl while the console said FluBNF.bat would offer it. One subroutine,
rem so another way to get Perl drops in here and nowhere else.
rem Only a Windows perl counts: Git's Unix tools, MSYS2 and Cygwin bring a
rem perl whose $^O is msys or cygwin, and BNG2.pl cannot load its own modules
rem under it. perl.exe, not perl: the console and the engine start perl.exe,
rem and a perl.bat run without call would never hand this file back.
rem FluBNF's own Perl first, once an earlier open unpacked it: the console
rem looks there first too (flubnf/settings.py), so both run the same perl.
set "PERLPKG=perl-5.32.1.1-2_h57928b3_strawberry.tar.bz2"
set "OWNPERL=%LOCALAPPDATA%\FluBNF\perl"
call :perlownok
if not errorlevel 1 goto :perlownpath
perl.exe -e "exit($^O eq q(MSWin32) ? 0 : 1)" <nul >nul 2>&1 && goto :eof
rem Installed but not on this window's PATH (a Command Prompt opened before
rem the install, a machine PATH cut short), or behind a Unix-style perl:
rem nothing to offer, only its folders to add.
if exist "%SystemDrive%\Strawberry\perl\bin\perl.exe" goto :perloffpath
set "PERLAT="
for /f "delims=" %%P in ('where perl.exe 2^>nul') do if not defined PERLAT set "PERLAT=%%P"
if defined PERLAT echo   The perl on PATH is not a Windows Perl, and BNG2.pl needs one:
if defined PERLAT echo     "%PERLAT%"
rem No Windows Perl here, so FluBNF installs its own: conda-forge's repack of
rem Strawberry Perl, unpacked under %LOCALAPPDATA%. No administrator, no
rem installer and no question, so it is tried on every open until it works
rem (a network that was down, a full disk). winget's Strawberry Perl, a
rem machine-wide install that needs an administrator, is the fallback.
call :perlown
if not errorlevel 1 goto :perlownpath
rem Offered once, in a record of its own. engine-attempt.txt also stamps an
rem engine file that did not unpack, and a retry then skipped an offer that
rem was never made. Once is enough: an unattended Y on every open would
rem raise Windows' permission prompt every time. The reminder follows.
set "PERLOFFER=%CD%\.venv\perl-offer.txt"
if exist "%PERLOFFER%" goto :perlreminder
where winget >nul 2>&1
if errorlevel 1 goto :perlnowinget
rem Asked like the data question: 20 s, default Y. An unattended N would
rem never be asked again.
where choice >nul 2>&1
if errorlevel 1 goto :perlwinget
choice /c YN /n /t 20 /d Y /m "Install Strawberry Perl via winget (fits and Check need it)? [Y/N, Y in 20s] "
if errorlevel 2 goto :perlskipped
:perlwinget
rem A machine-wide MSI, so Windows asks for permission. Behind another
rem window that prompt is only a flashing button on the taskbar, and winget
rem waits on it with nothing new on screen.
echo   installing Strawberry Perl with winget, a few minutes...
echo   Windows will ask permission to install Strawberry Perl (about 210 MB).
echo   Click Yes. If nothing appears, click the flashing shield on the taskbar.
echo   An account that is not an administrator needs an administrator's password.
rem --source winget: without it winget searches the msstore source too, and
rem when that cannot be reached (a network that inspects TLS) the install
rem stops although the package was found.
winget install -e --id StrawberryPerl.StrawberryPerl --source winget --accept-source-agreements --accept-package-agreements
set "WG=%ERRORLEVEL%"
rem Judged by what is on disk, not by the code: winget's failure codes are
rem negative (0x8A15xxxx), and the errorlevel test this replaced (1 or more)
rem never caught one, so a declined prompt was reported as "Perl installed".
if exist "%SystemDrive%\Strawberry\perl\bin\perl.exe" goto :perlinstalled
echo   winget did not install Strawberry Perl (code %WG%).
set "PERLSAID=winget %WG%"
if "%WG%"=="-1978334974" goto :perlbusy
if "%WG%"=="-1978334964" goto :perlrefused
if "%WG%"=="-1978334961" goto :perlpolicy
if "%WG%"=="-1978335174" goto :perlpolicy
goto :perlasked
:perlbusy
rem 0x8A150102, another install in progress: left unrecorded, so the next
rem open asks again.
echo   Another install is running, often Windows Update. Close FluBNF and open
echo   it again in a few minutes; it asks once more.
goto :eof
:perlrefused
rem 0x8A15010C, cancelled: the MSI's 1602.
echo   Windows' permission prompt was declined or not answered in time, or
echo   this account is not an administrator.
goto :perlasked
:perlpolicy
rem 0x8A15010F and 0x8A15003A: blocked by an organisation's policy.
echo   A policy on this PC blocks the install, as on a school or work laptop:
echo   ask whoever manages it to install Strawberry Perl.
goto :perlasked
:perlskipped
set "PERLSAID=declined"
echo   skipped.
:perlasked
rem Quoted on write: the code ends in a digit, and a digit just before >
rem names a handle to redirect.
echo "%PERLSAID%">"%PERLOFFER%"
echo   FluBNF asks only once; every open repeats this until Perl is installed:
goto :perlreminder
:perlnowinget
echo "no winget">"%PERLOFFER%"
echo   winget is not on this PC, so FluBNF cannot install Perl for you.
:perlreminder
echo   Perl is still missing, and fits and the Sandbox's Check need it:
echo   https://strawberryperl.com (not an administrator here? ask one to install it)
goto :eof
:perlinstalled
echo "installed">"%PERLOFFER%"
echo   Strawberry Perl installed and ready.
goto :perlpath
:perloffpath
echo   using Strawberry Perl from "%SystemDrive%\Strawberry" (not first on this window's PATH)
:perlpath
rem Strawberry's three folders, in the order its installer adds them. That
rem change reaches windows opened after it, not this one, and the console
rem starts from this one. First, not last: a Unix-style perl earlier on PATH
rem would win otherwise.
set "PATH=%SystemDrive%\Strawberry\c\bin;%SystemDrive%\Strawberry\perl\site\bin;%SystemDrive%\Strawberry\perl\bin;%PATH%"
goto :eof
:perlownok
rem 0 when FluBNF's own Perl is complete and starts: the marker, written
rem last, names the pinned package, and perl.exe loads strict, which a
rem missing DLL or an @INC it cannot read stops.
if not defined LOCALAPPDATA exit /b 1
if not exist "%OWNPERL%\flubnf-perl.ok" exit /b 1
set "OWNHAVE="
set /p OWNHAVE=<"%OWNPERL%\flubnf-perl.ok"
if not "%OWNHAVE%"=="%PERLPKG%" exit /b 1
if not exist "%OWNPERL%\Library\bin\perl.exe" exit /b 1
"%OWNPERL%\Library\bin\perl.exe" -Mstrict -e "exit($^O eq q(MSWin32) ? 0 : 1)" <nul >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0
:perlown
rem Unpacks FluBNF's own Perl; 0 once it is complete and starts. The
rem console's Python downloads the package into memory (the proxy and
rem certificates pip used) and checks its size and SHA-256 before a byte goes
rem on, then hands Windows' tar.exe a plain tar: Windows 10's tar has no
rem bzip2. tar writes the files, not Python: a Microsoft Store Python's writes
rem under AppData land in a private copy. Every file is then checked against
rem the package's own list, and the marker is written last, so a marker
rem always means a whole Perl. No parenthesised blocks: a profile folder's
rem name can hold a ")".
if not defined LOCALAPPDATA exit /b 1
if not exist ".venv\Scripts\python.exe" exit /b 1
if not exist "scripts\windows\get_perl.py" exit /b 1
if not exist "%SystemRoot%\System32\tar.exe" exit /b 1
echo   installing Perl for FluBNF: a 31 MB download, no administrator needed...
if exist "%OWNPERL%" rmdir /s /q "%OWNPERL%" >nul 2>&1
if exist "%OWNPERL%" echo   "%OWNPERL%" could not be cleared: close other FluBNF windows and open FluBNF again.
if exist "%OWNPERL%" exit /b 1
mkdir "%OWNPERL%" >nul 2>&1
if not exist "%OWNPERL%\" exit /b 1
rem tar's exit code is not trusted either way: verify is the only gate.
".venv\Scripts\python.exe" -I "%CD%\scripts\windows\get_perl.py" fetch <nul | "%SystemRoot%\System32\tar.exe" -xf - -C "%OWNPERL%"
".venv\Scripts\python.exe" -I "%CD%\scripts\windows\get_perl.py" verify "%OWNPERL%" <nul
if errorlevel 1 goto :perlownundo
"%OWNPERL%\Library\bin\perl.exe" -Mstrict -MPOSIX -MIPC::Open3 -e "exit($^O eq q(MSWin32) ? 0 : 1)" <nul >nul 2>&1
if errorlevel 1 goto :perlownundo
>"%OWNPERL%\flubnf-perl.ok" echo %PERLPKG%
echo   Perl for FluBNF is ready.
exit /b 0
:perlownundo
rmdir /s /q "%OWNPERL%" >nul 2>&1
echo   FluBNF could not install its own Perl; the next open tries again.
exit /b 1
:perlownpath
rem Its bin folder first, as Strawberry's above. PERL5LIB, PERLLIB and
rem PERL5OPT would put another Perl's modules or options in front.
set "PATH=%OWNPERL%\Library\bin;%PATH%"
set "PERL5LIB="
set "PERLLIB="
set "PERL5OPT="
goto :eof
