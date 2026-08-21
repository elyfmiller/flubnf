# FluBNF on Windows

Native Windows support is in active bring-up. The console, the analogue
engine, data fetching, scoring, and reports are expected to work; the PF
fitting engine has additional requirements listed under Limitations.

## Supported path (lab laptops)

Install once:

1. Python 3.11 or newer from https://www.python.org/downloads/
   (tick "Add python.exe to PATH" in the installer).
2. Git from https://git-scm.com/download/win (defaults are fine).

Then get the code and launch:

```
git clone https://github.com/elyfmiller/flubnf %USERPROFILE%\Documents\GitHub\flubnf
```

Double-click `FluBNF.bat` in that folder. The first run creates the
virtual environment and installs dependencies (a few minutes); every later
run self-updates with a fast-forward `git pull` and starts the console.

For the full first-time setup, including the sparse FluSight hub data
clone (about 150 MB) and the environment variables, run once from the
repository folder:

```
powershell -ExecutionPolicy Bypass -File setup.ps1
```

`setup.ps1` is idempotent; re-running it fixes whatever is missing.

## WSL2 alternative

FluBNF runs unmodified under WSL2 (Ubuntu): install WSL, then follow the
standard `setup.sh` instructions inside the Linux environment.

## Limitations (current)

- **Fit scheduling priority.** On macOS and Linux, fitting subprocesses
  start under `nice` so the console stays responsive during long runs. The
  Windows equivalent (`BELOW_NORMAL_PRIORITY_CLASS`, provided by
  `app/core/proc.py:low_priority_popen_kwargs`) is not yet wired into the
  engine call sites, so fits run at normal priority and the console may
  feel sluggish during a run.
- **PF engine.** The particle-filter engine needs three externals on
  Windows:
  - the private PyBNF fork (pure Python; clones and installs normally),
  - `bngsim` (official Windows wheels exist on PyPI for Python 3.10-3.13,
    so `pip install bngsim` works without a compiler),
  - Perl, for the one-time BNG2.pl network-generation step at fit prep.
    The `bionetgen` pip package ships the Windows BNG binaries
    (`bng-win`, including `run_network.exe`), but not a Perl interpreter;
    install Strawberry Perl from https://strawberryperl.com.
  The PF engine has not yet been validated end to end on native Windows;
  until it is, machines without the engine automatically run the analogue
  engine only, exactly as on a Tier-A Mac.
- **Windows CI is experimental.** The `test-windows (experimental)` job in
  `.github/workflows/tests.yml` runs the suite on `windows-latest` with
  `continue-on-error`, so a red Windows run does not fail the checks while
  the port stabilizes. It will be promoted to a required check once it has
  been green for a few consecutive weeks.
