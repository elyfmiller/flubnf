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

If the FluSight data is not on the machine yet, `FluBNF.bat` says so and
offers to run `setup.ps1` for you. Answering N, or walking away for twenty
seconds, starts the console anyway with data browsing empty; the offer
comes back on the next launch and disappears for good once the data is
there.

That offer is judged on the data, not on the folder: the launcher looks for
`auxiliary-data\locations.csv` inside the hub, and setup runs with
`-NoPrompt`, so a double-click can never end at a question with no timeout.
Nothing on the double-click path waits on input without a deadline.

## A hub cloned by hand

`git clone --sparse` is documented to check out **only the files in the
repository root**. A hub cloned by hand with

```
git clone --filter=blob:none --sparse --depth 1 https://github.com/cdcepi/FluSight-forecast-hub %USERPROFILE%\Documents\GitHub\FluSight-forecast-hub
```

therefore succeeds, prints no error, and contains no `auxiliary-data`, no
`target-data` and no `model-output`. The console opens on "Latest vintage:
none" exactly as if nothing had been cloned. This happened in the field on
2026-08-25, and it was invisible because every gate tested for the clone
rather than for its contents.

`setup.ps1` now widens an existing sparse checkout with `git sparse-checkout
add` before it reapplies anything, because `reapply` re-applies the cone
already recorded and that cone is empty. It uses `add` rather than `set`:
`add` extends a cone and fails harmlessly on a full clone, whereas `set`
would delete every directory it is not given, gutting the checkout of
anyone who deliberately cloned the whole hub. `setup.sh` does the same on
macOS and Linux, and `flubnf doctor` now tests for the data directories, so
it can no longer report "you are ready" over an empty clone.

Re-running `setup.ps1` is the repair. Nothing has to be deleted or
re-cloned.

To run the full first-time setup yourself, from the repository folder:

```
powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1
```

It prints where everything will be installed before installing anything,
fetches the sparse FluSight hub clone (about 150 MB), records the
environment, and reports what is still missing. It is idempotent:
re-running it updates an existing hub clone and fixes whatever is absent.

`-NoProfile` is not decoration. A PowerShell profile that sets
`$ErrorActionPreference = "Stop"` turns every line git writes to stderr
into a script-ending error, because Windows PowerShell surfaces native
stderr as error records.

Useful switches and variables:

| what | effect |
|---|---|
| `-NoPrompt` | ask nothing at all. `FluBNF.bat` always passes it; the one question it suppresses is the offer to let winget install Strawberry Perl, which `setup.ps1` then prints as a command to run later. Run `setup.ps1` by hand to be asked. |
| `FLUBNF_HUB` | put the FluSight data somewhere else, e.g. `setx FLUBNF_HUB D:\FluSight-forecast-hub`, then open a new window |
| `FLUBNF_NO_DATA=1` | skip the data clone entirely |
| `FLUBNF_NO_PROBE=1` | skip the read-only check for access to the private PyBNF fork |

The exit code is a statement about setup, not about the externals.
`setup.ps1` exits 0 whenever it finished its work, including on the ordinary
machine that has no access to the private PyBNF fork and therefore ends with
"some externals missing". It exits non-zero only when setup itself could not
proceed: no Python 3.11 or newer, the virtual environment could not be
created, or the package would not install. That distinction is what lets
`FluBNF.bat` report a real problem without crying wolf on every healthy
first run, and the Windows CI job asserts it on all three of its runs.

`setup.ps1` writes `.flubnf.env.cmd` in the repository folder, the Windows
twin of the `.flubnf.env` that `FluBNF.command` sources on macOS.
`FluBNF.bat` calls it on every launch. It matters because the User-scope
environment variables `setup.ps1` also records reach only processes started
afterwards, so without the file a console launched from an already-open
window would still see nothing.

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
- **Windows CI is experimental.** Two jobs in
  `.github/workflows/tests.yml` run on `windows-latest`, both with
  `continue-on-error`, so a red Windows run does not fail the checks while
  the port stabilizes. `test-windows (experimental)` runs the test suite.
  `windows-setup-script (experimental)` is the only automated exercise of
  the first-run path: it parses `setup.ps1` under Windows PowerShell 5.1,
  then runs it four times through the command line `FluBNF.bat` uses --
  once with the data fetch skipped, once performing the real sparse
  FluSight clone, once more over the machine the second run configured, and
  once against a hub cloned **by hand** with `--sparse`, which is the state
  the field report came from and the only one that can show whether the
  repair above works -- checking each transcript against what the script
  promised to say. It holds no credentials, so the engine is always missing
  there and the degraded path is what gets tested. It does not cover
  `FluBNF.bat` itself, the Perl/winget branch, or any non-ASCII profile
  path. Both jobs will be promoted to required checks once they have been
  green for a few consecutive weeks.
- **The PowerShell has never been executed here.** The lab develops on
  macOS and has no PowerShell interpreter, so `setup.ps1` is written from
  the language rules and first runs in CI. The git behaviour it depends on
  (`--sparse` checking out the root only, `reapply` adding nothing, `add`
  being idempotent, `set` pruning a full clone, `pull --ff-only` succeeding
  against a shallow blobless sparse clone) was measured locally on git
  2.39.5, because that is git behaviour rather than platform behaviour, and
  the equivalent bash in `setup.sh` was executed against five clone states.
  What remains unverified is the transliteration into PowerShell 5.1
  syntax, which is what the CI job exists to check.
