# Launchers, setup scripts and environment variables

The root scripts that install, update and open FluBNF, who calls each, and every `FLUBNF_*` variable.

## Launchers and setup scripts

| File | Platform | What it does | Called by |
|---|---|---|---|
| `install.sh` | macOS, Linux | Clones to `$FLUBNF_DIR`, then runs `setup.sh` | user: `curl … install.sh \| bash` |
| `setup.sh` | macOS, Linux | `.venv` + editable install + BioNetGen, sparse hub clone, sets `core.hooksPath=.githooks`, writes `.flubnf.env`, runs doctor | `install.sh`, `FluBNF.command` (first run), `reinstall.sh`, user |
| `setup_engine.sh` | macOS, Linux | Installs the engine: PyBNF fork from an archive, bundle, checkout or clone, engine venv, bngsim; rewrites `.flubnf.env`. `--print-bundle` only names the archive it would use | `FluBNF.command` (engine missing), `SetupEngine.command`, `reinstall.sh`, user |
| `FluBNF.command` | macOS | Double click: self-update (fast-forward only), dependency refresh, first-run `setup.sh`, engine auto-install, then `.venv/bin/flubnf app`, under `FluBNF.app`'s host when there is one. `FLUBNF_PREPARE_ONLY=1` runs the checks only | user, `FluBNF.app` |
| `FluBNF.app/` | macOS | App bundle, keepable in the Dock. `Contents/MacOS/flubnf-launch` runs `FluBNF.command` headless, then execs the host `Contents/MacOS/FluBNF` as `flubnf window`; anything to watch opens `FluBNF.command` in Terminal instead ([below](#flubnfapp-in-the-dock-macos)) | user, Dock |
| `scripts/macos/build_app_host.sh` | macOS | Compiles `scripts/macos/flubnf_host.c` against the venv's libpython into `FluBNF.app/Contents/MacOS/FluBNF` (gitignored), signs it ad hoc. Quiet when current; `--force`, `--check` | `setup.sh`, `FluBNF.command`, `flubnf-launch` |
| `scripts/macos/host_boot.py` | macOS | Runs the console script under the host for a Dock launch; a failure in the first 30 s reopens `FluBNF.command` in Terminal | the host |
| `SetupEngine.command` | macOS | Double click: finds a PyBNF checkout or engine archive, runs `setup_engine.sh` | user |
| `reinstall.sh` | macOS, Linux | Clean reinstall: sets the old clone and engine venv aside, moves old engine files to `Downloads/old-engine-files`, then `setup.sh` + `setup_engine.sh` with the newest archive | user: `curl … reinstall.sh \| bash` |
| `FluBNF.bat` | Windows | Twin of `FluBNF.command`: self-update, reads `.flubnf.env.cmd`, offers `setup.ps1` when hub data is missing, installs the engine inline, starts the console | user |
| `setup.ps1` | Windows | Twin of `setup.sh` plus Perl and engine checks; writes User env vars and `.flubnf.env.cmd`, runs doctor | `FluBNF.bat` (`-NoPrompt`), user, CI job `windows-setup-script` |
| `scripts/cut_engine_archive.sh` | maintainer | Cuts `pybnf-pf-<sha>.tar.gz` from the fork with `git archive`; the file the others install | maintainer ([ENGINE.md](ENGINE.md)) |
| `.githooks/pre-push` | git | On a push to `*/main`, runs both suites with `FLUBNF_HUB=/nonexistent`, as CI does | git (enabled by `setup.sh`) |

Files they leave behind (all gitignored or inside `.venv`):

| File | Written by | Read by |
|---|---|---|
| `.flubnf.env` | `setup.sh`, `setup_engine.sh` | `FluBNF.command`, `reinstall.sh` |
| `.flubnf.env.cmd` | `setup.ps1` | `FluBNF.bat` |
| `.venv/.pyproject.stamp` | `FluBNF.command` | `FluBNF.command` (refresh deps when `pyproject.toml` changes) |
| `.venv/.engine-attempt` (`.venv\engine-attempt.txt` on Windows) | `FluBNF.command`, `FluBNF.bat` | the same launcher: skips a retry that cannot succeed |
| `FluBNF.app/Contents/MacOS/FluBNF` | `build_app_host.sh` | `flubnf-launch`, `FluBNF.command` |
| `.venv/.app-host.stamp` | `build_app_host.sh` | `build_app_host.sh`: `ok` with the fingerprint built for; `fail` (no usable host) or `kept` (a rebuild failed, and the host already installed still loads and stays in use), each with the fingerprint, the compiler and the reason |
| `app/state/logs/launch.log` | `flubnf-launch`, the host | people: what a Dock launch did, and why it went to Terminal |

PyBNF checkout search order (every script and `flubnf/settings.py`): `FLUBNF_PYBNF`, then `PyBNF-pf`, then `PyBNF-Private`.

Tests that pin these scripts: `tests/test_engine_bundle.py`, `tests/test_launcher_update.py`, `tests/test_mac_app_bundle.py`, `tests/test_reinstall_script.py`, `tests/test_first_run_sparse_hub.py`, `tests/test_windows_controlled_folder_access.py` ([tests/README.md](../tests/README.md)).

## FluBNF.app in the Dock (macOS)

The Dock names a window, picks its icon and decides what Keep in Dock pins from the app bundle that holds the running program. A venv's `python` is `Python.app` (python.org, Homebrew) or a bare `python3.12` (Anaconda), so a console started that way shows as "Python" or "python3.12", and a kept icon cannot reopen FluBNF. Renaming at run time does not change this.

So `setup.sh` compiles a small host, `scripts/macos/flubnf_host.c`, into `FluBNF.app/Contents/MacOS/FluBNF`. It links the libpython the venv was made from and runs as the venv's own `python`: same `sys.prefix`, packages and `sys.executable`. Its program sits inside `FluBNF.app`, so the window is FluBNF in the Dock, with one icon, and Keep in Dock pins `FluBNF.app`. `ps` shows `…/FluBNF.app/Contents/MacOS/FluBNF …/.venv/bin/flubnf window`, which the single-instance takeover and `reinstall.sh`'s running check both match.

A Dock launch (`flubnf-launch`) runs `FluBNF.command` headless, output in `app/state/logs/launch.log`, then execs the host. It opens `FluBNF.command` in Terminal instead for: a first run; local edits in the way of the update; a dependency refresh; an engine install; no host; checks that fail or take over two minutes; a console that stops within 30 s; `FLUBNF_LAUNCH=terminal`. A Terminal launch runs the console under the host too, once it exists, and without it after a failed start. A copy that cannot start at all (moved out of its clone, or an old clone `reinstall.sh` set aside) shows an alert saying so.

The host is per machine and gitignored. A fresh clone opens through Terminal until setup has built it. It is rebuilt when the venv, its packages or the source change. A failed build (no Command Line Tools, a static-only Python) is not retried on every launch; installing the tools earns a retry. It is signed ad hoc (`codesign -s -`), which Apple Silicon requires and which is enough for a program built on the same Mac. Gatekeeper only checks quarantined files, and a file compiled locally has no quarantine flag.

On the first Dock launch macOS may ask whether FluBNF can use the Documents folder (and, while the engine is missing, Downloads and Desktop): Terminal held those permissions before. It may ask again after the host is rebuilt for a new Python.

To check a Mac: `scripts/macos/build_app_host.sh --force` shows the build; `tail app/state/logs/launch.log` shows what the last Dock launch did.

## Environment variables

Paths default to `~/Documents/GitHub/<name>`; on Windows, to `%LOCALAPPDATA%\FluBNF\<name>` unless a checkout already exists at the Documents path ([WINDOWS.md](WINDOWS.md)).

**Machine paths** (the console reads them through `flubnf/settings.py`; `flubnf doctor` reports them):

| Variable | Honored by | Default |
|---|---|---|
| `FLUBNF_HUB` | `flubnf/settings.py`, `setup.sh`, `setup.ps1`, `FluBNF.bat`; set to `/nonexistent` by CI and `.githooks/pre-push` | `FluSight-forecast-hub` checkout |
| `FLUBNF_PYBNF` | `flubnf/settings.py`, every launcher and setup script but `install.sh` | `PyBNF-pf`, else `PyBNF-Private` checkout |
| `FLUBNF_PY_ENGINE` | `flubnf/settings.py`, `FluBNF.command`, `FluBNF.bat`, `reinstall.sh`; written by the setup scripts | `~/.venvs/flubnf/bin/python`, else `~/.venvs/flubnf-engine/bin/python` |
| `FLUBNF_BNG` | `flubnf/settings.py` | BNG2.pl of `.venv`'s `bionetgen`, else on `PATH` |
| `FLUBNF_ENGINE_VENV` | `setup.sh`, `setup_engine.sh`, `setup.ps1`, `FluBNF.bat`, `reinstall.sh` | `~/.venvs/flubnf-engine` |

**Install and launch:**

| Variable | Honored by | Default |
|---|---|---|
| `FLUBNF_DIR` | `install.sh`, `reinstall.sh` | `~/Documents/GitHub/flubnf` |
| `FLUBNF_REPO` | `reinstall.sh` | `https://github.com/elyfmiller/flubnf` |
| `FLUBNF_UPDATE` | `FluBNF.command`, `FluBNF.bat` | unset = fast-forward; `off` skips; `force` resets to origin |
| `FLUBNF_LAUNCH` | `flubnf-launch` (`FluBNF.app`) | unset = quiet launch; `terminal` always opens `FluBNF.command` in Terminal. `open` does not pass a shell's variables on: run `FLUBNF_LAUNCH=terminal FluBNF.app/Contents/MacOS/flubnf-launch`, or `launchctl setenv FLUBNF_LAUNCH terminal` (until logout) |
| `FLUBNF_PREPARE_ONLY` | `FluBNF.command`; set by `flubnf-launch` | unset; `1` = update and checks only, exit 75 when Terminal is needed |
| `FLUBNF_HOST_FALLBACK` | the host, `host_boot.py`; set by `flubnf-launch` | unset; `1` = a startup failure reopens Terminal. Removed before the console starts |
| `FLUBNF_HOST_ANY_OS` | `build_app_host.sh` (test hook) | unset; `1` builds the host off macOS |
| `FLUBNF_NO_DATA` | `setup.sh`, `setup.ps1` | unset; `1` skips the hub clone |
| `FLUBNF_NO_PROBE` | `setup.ps1` | unset; `1` skips the fork access probe |
| `FLUBNF_PYBNF_BUNDLE` | `setup_engine.sh`, `FluBNF.bat`; set by `reinstall.sh` | unset = search Downloads and nearby folders |
| `FLUBNF_PYBNF_REMOTE` | `setup_engine.sh`, `setup.ps1` | `https://github.com/elyfmiller/PyBNF-Private.git` |
| `FLUBNF_BNGSIM_REMOTE` | `setup_engine.sh` | `https://github.com/elyfmiller/bngsim` |
| `FLUBNF_ENGINE_CHECKOUT_ONLY` | `setup_engine.sh` (test hook) | unset; `1` stops after the checkout |
| `FLUBNF_REINSTALL_YES`, `_FORCE`, `_NO_INSTALL`, `_NO_OPEN`, `_IGNORE_RUNNING` | `reinstall.sh` (header lists each) | unset |
| `FLUBNF_PYBNF_FORK` | `scripts/cut_engine_archive.sh` | `~/Documents/GitHub/PyBNF-Private` |
| `FLUBNF_RLIB` | `scripts/validate_submission.R` | unset; an extra R library path |

**Console and research knobs:**

| Variable | Honored by | Default |
|---|---|---|
| `FLUBNF_PF_WIDTH` | `app/core/engines/pf.py` | unset = automatic shard width; `1` = one process |
| `FLUBNF_PROTECT_ROOTS` | `app/core/reclaim.py` | unset; extra roots storage reclaim must not touch |
| `FLUBNF_FIELD_CELLS` | `app/core/relwis.py` | `app/state/field_cells` |
| `FLUBNF_STARTUP_TRACE` | `flubnf/cli.py`, `app/ui/state.py`, `scripts/open_cycle.py` | unset; a file path turns on the launch trace |
| `FLUBNF_ORACLE_RECORD`, `FLUBNF_ORACLE_FULL` | `tests/test_oracle*.py` | lab-only record; `FULL=1` compares every screened date |
