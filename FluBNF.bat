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
rem (the Anaconda python probe used to live here; it now runs at the very
rem top, before the first-run gate, so that EVERY launch has it: the engine
rem venv fallback needs it on the reopen-after-saving-the-file path, which
rem is exactly the staged flow the install doc prescribes)
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
rem The timeout answers YES, and that is a deliberate change (2026-08-31).
rem The requirement this launcher is written to is "double click one file and
rem setup happens", and a question that answers ITSELF with "no" after 20 s is
rem the one thing that guarantees setup does not happen: a student who
rem double-clicks and goes to get coffee came back to a console reporting
rem "Latest vintage: none", which is the state this whole block exists to
rem prevent. The console is unusable without this data, the download is a
rem one-time 150 MB, and N is still one keystroke away for anyone on a
rem metered connection who is actually watching.
choice /c YN /n /t 20 /d Y /m "Fetch it now? [Y/N, Y by itself in 20s] "
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
rem (20 s, defaults to Y), and a double-click must never end at a prompt
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
rem ===== the particle filter engine =========================================
rem This section is the Windows twin of the block in FluBNF.command, and it
rem exists for one reason: cloning the PyBNF fork is the ONLY step of a FluBNF
rem install that needs a GitHub account, because that repository is private.
rem Everything else - this repo, the FluSight hub, BioNetGen, both venvs - is
rem public and automatic. The console runs without the engine (analogue member
rem only), so nothing here may block the launch or ask a question.
rem
rem An OFFLINE ENGINE BUNDLE removes the account entirely. Someone who has the
rem fork runs, once:
rem   git bundle create pybnf.bundle feature/particle-filter
rem and that single file clones like a repository, with no network and no
rem credentials:
rem   git clone -b feature/particle-filter pybnf.bundle <destination>
rem So this block looks for such a file where a student would leave it, and
rem installs the engine from it if it is there. What it deliberately does NOT
rem do is probe github.com: that costs a network round trip on every launch of
rem every machine that never gets the engine, and setup.ps1 already does it
rem once, with a timeout and a real diagnosis. Run setup.ps1 for that.
rem
rem The checkout locations below mirror setup.ps1's Resolve-Checkout, in ITS
rem order, name by name: FLUBNF_PYBNF wins; then PyBNF-pf at the old
rem Documents default, used where it stands and never moved; then PyBNF-pf
rem under %LOCALAPPDATA%; then the same two for PyBNF-Private, which is what
rem the fork clones as on every machine but the development host. If the
rem launcher and setup.ps1 ever disagreed, one of them would install an
rem engine the other cannot find.
rem
rem Each location is accepted for either of two shapes: a git checkout
rem ("\.git") or an UNPACKED ARCHIVE, recognised by pybnf\pf.py. The archive
rem is what the lab actually hands students (scripts/cut_engine_archive.sh, a
rem ~130 KB pybnf-pf-<sha>.tar.gz that unzips to PyBNF-Private), and the
rem install below is a plain pip install from a directory, so .git was never
rem the real requirement. Testing pf.py rather than the bare directory keeps
rem the property the old "\.git" test was defending: an empty folder is not
rem an engine source, and the bundle clone below still needs an empty
rem destination.
set "PYBNFDIR=%FLUBNF_PYBNF%"
if not defined PYBNFDIR goto :pybnfprobe
rem Honour the pin only if an engine is actually there. setup.ps1 records
rem FLUBNF_PYBNF at its DEFAULT before anything exists at that path (first
rem run answers the data question before the archive is unpacked), so a
rem dangling pin is the NORMAL first-run state, not an error, and treating
rem it as authoritative would send every later launch to a folder that will
rem never contain an engine.
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
set "ENGINEVENV=%FLUBNF_ENGINE_VENV%"
if not defined ENGINEVENV set "ENGINEVENV=%USERPROFILE%\.venvs\flubnf-engine"
set "ENGINEPY=%ENGINEVENV%\Scripts\python.exe"

rem Is it already installed? Two cheap file tests first, so a machine with no
rem engine never pays for starting Python, and only then the import probe -
rem which is the same one setup.ps1 uses, and it loads pybnf the way the
rem generated runners do (the checkout on sys.path), because the editable
rem install is known to fail on Windows while fits run perfectly anyway.
if not exist "%ENGINEPY%" goto :engineabsent
rem pf.py, not .git: the import probe on the next line loads pybnf off the
rem checkout via sys.path, and an unpacked archive satisfies that exactly as
rem a clone does. Testing .git here declared a working archive-based engine
rem absent on every open.
if not exist "%PYBNFDIR%\pybnf\pf.py" goto :engineabsent
"%ENGINEPY%" -c "import sys; sys.path.insert(0, r'%PYBNFDIR%'); import bngsim; from pybnf.pf import ParticleFilter" >nul 2>&1
if errorlevel 1 goto :engineabsent
set "FLUBNF_PY_ENGINE=%ENGINEPY%"
set "FLUBNF_PYBNF=%PYBNFDIR%"
goto :startconsole

:engineabsent
rem Look for the bundle where a student actually saves a downloaded file: the
rem FluBNF folder itself, beside it, Downloads, Desktop, Documents. The
rem wildcard catches "pybnf (1).bundle", which is what a second download is
rem called. `if not defined` inside the loop is evaluated per iteration, so
rem the first match wins without needing delayed expansion.
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
for %%F in ("%USERPROFILE%\Downloads\pybnf*.bundle") do if not defined BUNDLE set "BUNDLE=%%~fF"
for %%F in ("%USERPROFILE%\Desktop\pybnf*.bundle") do if not defined BUNDLE set "BUNDLE=%%~fF"
for %%F in ("%USERPROFILE%\Documents\pybnf*.bundle") do if not defined BUNDLE set "BUNDLE=%%~fF"
rem The other artifact shape: the ~130 KB pybnf-pf-<sha>.tar.gz that
rem scripts/cut_engine_archive.sh cuts. Same folders, same rule: whatever
rem the student saved is the engine, and they should never have to know
rem which shape they were given or where it belongs.
set "ARCHIVE="
for %%F in ("%~dp0pybnf*.tar.gz") do if not defined ARCHIVE set "ARCHIVE=%%~fF"
for %%F in ("%~dp0..\pybnf*.tar.gz") do if not defined ARCHIVE set "ARCHIVE=%%~fF"
for %%F in ("%USERPROFILE%\Downloads\pybnf*.tar.gz") do if not defined ARCHIVE set "ARCHIVE=%%~fF"
for %%F in ("%USERPROFILE%\Desktop\pybnf*.tar.gz") do if not defined ARCHIVE set "ARCHIVE=%%~fF"
for %%F in ("%USERPROFILE%\Documents\pybnf*.tar.gz") do if not defined ARCHIVE set "ARCHIVE=%%~fF"
:bundleresolved

rem Extract an archive HERE, not somewhere in the install flow: tar.exe has
rem shipped with Windows since 10 1803, the extraction is about a second,
rem and once it lands the ordinary pf.py gates below see a normal unpacked
rem copy. The destination is chosen by this launcher (LOCALAPPDATA, because
rem Controlled Folder Access protects Documents), which is exactly the
rem detail a student should never be asked to know.
if not defined ARCHIVE goto :archivedone
if exist "%PYBNFDIR%\.git" goto :archivedone
if exist "%PYBNFDIR%\pybnf\pf.py" goto :archivedone
where tar >nul 2>&1
if errorlevel 1 goto :archivedone
if not exist "%LOCALAPPDATA%\FluBNF" mkdir "%LOCALAPPDATA%\FluBNF"
echo   unpacking the engine from "%ARCHIVE%" - no GitHub account needed
tar -xzf "%ARCHIVE%" -C "%LOCALAPPDATA%\FluBNF"
if exist "%LOCALAPPDATA%\FluBNF\PyBNF-Private\pybnf\pf.py" set "PYBNFDIR=%LOCALAPPDATA%\FluBNF\PyBNF-Private"
if not exist "%PYBNFDIR%\pybnf\pf.py" echo   unpack failed or wrong file; continuing without it
rem the stamp is the answer to "which build am I running" when two people's
rem forecasts disagree; macOS prints it on every setup, so Windows does too
if exist "%PYBNFDIR%\VERSION" set /p FLUVER=<"%PYBNFDIR%\VERSION"
if defined FLUVER echo   version stamp: %FLUVER%
:archivedone

rem Neither a checkout nor a bundle: say so in two lines and open the console.
rem This is a normal state, not a failure - the analogue member is a whole
rem working forecast - so it gets no banner and no question.
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
rem Do not repeat a failed build on every open. The fingerprint is the
rem checkout and the bundle, so a NEW bundle (or a checkout that has since
rem appeared) retries by itself, which is exactly the sequence a student
rem hits: first open fails for want of access, someone hands them the file,
rem second open installs. "?" is the separator because no Windows path may
rem contain one.
rem
rem The bundle's SIZE is part of it, not just its path. The failure this file
rem says is the realistic one - a copy from a shared drive that did not finish
rem - is repaired by writing the whole file over the broken one, under the
rem same name, in the same folder. A fingerprint made of the path alone does
rem not move when that happens, so the stamp would suppress exactly the retry
rem the message asked for. %%~zF is the size of the file the loop names, and
rem the file is known to exist by now, so it is never empty here. Measured on
rem the POSIX twin in FluBNF.command, where the same defect was reproduced.
set "BUNDLESZ="
if defined BUNDLE for %%F in ("%BUNDLE%") do set "BUNDLESZ=%%~zF"
set "ENGINEFP=%PYBNFDIR%?%BUNDLE%?%BUNDLESZ%"
set "ATTEMPT=.venv\engine-attempt.txt"
set "LAST="
if not exist "%ATTEMPT%" goto :engineinstall
for /f "usebackq delims=" %%L in ("%ATTEMPT%") do set "LAST=%%~L"
if "%LAST%"=="%ENGINEFP%" goto :engineskipped
:engineinstall
echo.
echo Installing the particle filter engine. One time, a few minutes.
where git >nul 2>&1
if errorlevel 1 goto :enginenogit
if exist "%PYBNFDIR%\.git" goto :enginevenv
if exist "%PYBNFDIR%\pybnf\pf.py" goto :enginevenv
echo   cloning from the offline bundle, no GitHub account needed:
echo     "%BUNDLE%"
rem Verify first, but do not expect much of it. MEASURED on git 2.39.5:
rem `git bundle verify` ACCEPTS a bundle truncated to half its bytes, because
rem it reads the header and the prerequisites and not the pack. So verify
rem catches only a file that is not a bundle at all (a browser that saved an
rem error page under this name), and the truncated copy - the one that
rem actually happens, from a shared drive that went away mid-copy - has to be
rem reported by the clone. The two remedies differ: one needs a different
rem file, the other needs the same file copied again.
git bundle verify "%BUNDLE%" >nul 2>&1
if errorlevel 1 goto :enginebadbundle
git clone -b feature/particle-filter "%BUNDLE%" "%PYBNFDIR%"
if not exist "%PYBNFDIR%\.git" goto :enginebadclone
rem git records the bundle FILE as origin, and that file is often on a stick
rem about to be unplugged. Name the fork instead, so a later pull fails with
rem something a person can act on. Nothing in FluBNF pulls this checkout.
git -C "%PYBNFDIR%" remote set-url origin https://github.com/elyfmiller/PyBNF-Private.git >nul 2>&1

:enginevenv
rem THE ENGINE VENV NEEDS PYTHON 3.11 OR 3.12, and nothing newer, even
rem though the console runs happily on the latest. The engine pins numpy<2
rem (the PyBNF fork predates NumPy 2), and numpy 1.26 ships wheels only up
rem to cp312; on anything newer pip falls back to building numpy from
rem source and dies unpacking a vendored-meson test path that blows past
rem Windows' 260-character MAX_PATH. MEASURED on the first real Windows
rem run (Sandbox, 2026-09-01): Anaconda's base is Python 3.14 and the
rem engine install failed exactly that way. So: check an existing venv's
rem version and rebuild a too-new one (first-attempt debris), prefer the
rem py launcher's 3.12/3.11, accept plain python only if it IS 3.11/3.12,
rem and otherwise have conda MAKE a 3.12 interpreter, which any Anaconda
rem can do regardless of its base version.
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
rem CONDAPY is the base interpreter, which may be 3.14; do not venv from it
rem blindly. If it happens to be 3.11/3.12 use it; otherwise ask conda to
rem create a real 3.12 interpreter next to the engine venv and venv from
rem that, so everything downstream (Scripts\python.exe, pip) is unchanged.
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
rem The pins, and the reason for each, are documented at length in setup.ps1
rem and setup_engine.sh; this is the same list. numpy<2 because the fork
rem predates NumPy 2. bngsim 0.15.1 because it was measured bit-identical to
rem the build every published FluBNF number came from. The runtime set is
rem installed explicitly so the fork can go in with --no-deps: PyBNF's own
rem setup.py pins msgpack==0.6.2, a 2019 release with no Windows wheel for
rem any modern Python, which pip would then try to compile.
"%ENGINEPY%" -m pip install -q --upgrade pip
"%ENGINEVENV%\Scripts\pip" install -q "numpy<2" scipy pandas "bngsim==0.15.1" "dask==2022.12.1" "distributed==2022.12.1" msgpack pyparsing tornado libroadrunner python-libsbml
if errorlevel 1 goto :enginefailed
rem A failed editable install is a warning, not an error: every generated
rem runner puts the checkout on sys.path and imports from there, so the
rem probe below is the real gate. This install is known to fail on Windows.
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
rem Quoted on the way out and unquoted on the way back in (%%~L above): a
rem profile path may contain & or a trailing digit, either of which cmd would
rem read as an operator or a redirect handle on a bare echo.
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
