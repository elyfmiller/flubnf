# Launchers, setup scripts and environment variables

The root scripts that install, update and open FluBNF, who calls each, and every `FLUBNF_*` variable.

## Launchers and setup scripts

| File | Platform | What it does | Called by |
|---|---|---|---|
| `install.sh` | macOS, Linux | Clones to `$FLUBNF_DIR`, then runs `setup.sh` | user: `curl … install.sh \| bash` |
| `setup.sh` | macOS, Linux | `.venv` + editable install + BioNetGen, sparse hub clone, sets `core.hooksPath=.githooks`, writes `.flubnf.env`, runs doctor | `install.sh`, `FluBNF.command` (first run), `reinstall.sh`, user |
| `setup_engine.sh` | macOS, Linux | Installs the engine: PyBNF fork from an archive, bundle, checkout or clone, engine venv, bngsim; rewrites `.flubnf.env`. `--print-bundle` only names the archive it would use | `FluBNF.command` (engine missing), `SetupEngine.command`, `reinstall.sh`, user |
| `FluBNF.command` | macOS | Double click: self-update (fast-forward only), dependency refresh, first-run `setup.sh`, engine auto-install, `flubnf engine-update` (a clean engine checkout on the production branch fast-forwards to the production build; [ENGINE.md](ENGINE.md)), then the console: with `FluBNF.app`'s host it opens the app through LaunchServices (`open -W -n -a FluBNF.app`, `FLUBNF_LAUNCH=ready`), as a Dock click does, because macOS never makes a Terminal child the active app (no hover, no resizing); a start that fails there, or no host, runs `.venv/bin/flubnf app` in view. Ready also travels as `--args --ready <status file>`, which a new instance always gets, in case macOS drops the `--env` values; the status file says "quit before the console started" until the console's window is up, so an app that dies without a word also ends in the console in view, while one stopped on request (a newer launch taking over) empties it and this Terminal stands down. A run that starts the console, or stops, without opening the app clears `FluBNF.app`'s reopen record. `FLUBNF_PREPARE_ONLY=1` runs the checks only | user, `FluBNF.app` |
| `FluBNF.app/` | macOS | App bundle, keepable in the Dock. `Contents/MacOS/flubnf-launch` runs `FluBNF.command` headless, then execs the host `Contents/MacOS/FluBNF` as `flubnf window`; anything to watch opens `FluBNF.command` in Terminal instead. With `FLUBNF_LAUNCH=ready` or `--ready <status file>` (FluBNF.command's own launch) it skips the checks, runs `flubnf app` with `FLUBNF_LAUNCH=ready` exported, and writes a startup failure to the status file rather than opening Terminal. `--handover "<why>"` is the host's and `host_boot.py`'s way back to Terminal: it reports to a waiting Terminal, or reopens one. Every automatic reopen is recorded first, per clone; a second within ten minutes, or one that cannot be recorded, is an alert instead ([below](#flubnfapp-in-the-dock-macos)) | user, Dock |
| `scripts/macos/build_app_host.sh` | macOS | Compiles `scripts/macos/flubnf_host.c` against the venv's libpython into `FluBNF.app/Contents/MacOS/FluBNF` (gitignored), signs it ad hoc. Quiet when current; `--force`, `--check` | `setup.sh`, `FluBNF.command`, `flubnf-launch` |
| `scripts/macos/host_boot.py` | macOS | Runs the console script under the host for a Dock launch; a failure in the first 30 s is reported to the Terminal that asked, or handed to `flubnf-launch --handover` | the host |
| `scripts/macos/move_home.sh` | macOS | Moves a clone in Documents, Desktop or Downloads to `~/GitHub`, with the FluSight hub and PyBNF checkout `.flubnf.env` names, and rewrites the paths that named them (`.flubnf.env`, `.venv`, `app/state`, the engine venv). One rename each on the same disk; nothing is copied. `--check` says whether one is due. `--relink`, run by every `FluBNF.command` open, reads where the venv was made (`.venv/bin/activate`) and where the hub and PyBNF went, and rewrites the paths to match, so a clone moved by hand is repaired too; a venv that still cannot import flubnf gets `pip install --no-deps -e .` | `FluBNF.command` |
| `SetupEngine.command` | macOS | Double click: finds a PyBNF checkout or engine archive, runs `setup_engine.sh` | user |
| `reinstall.sh` | macOS, Linux | Clean reinstall: sets the old clone and engine venv aside, moves old engine files to `Downloads/old-engine-files`, then `setup.sh` + `setup_engine.sh` with the newest archive | user: `curl … reinstall.sh \| bash` |
| `FluBNF.bat` | Windows | Twin of `FluBNF.command`. Self-update (fast-forward only): when it cannot, it says whether origin rewrote its history (nothing unique would be lost), the branch is gone upstream (switch to `main`), or this clone has commits or edits of its own, and prints the recovery commands with the folder in them (`git -C "<folder>" …`), one per line. Rebuilds a `.venv` that was moved with its folder (the old one is kept as `.venv.moved-<stamp>`); first run makes `.venv` with Python 3.12 or 3.11 where it can. Reads `.flubnf.env.cmd`, offers `setup.ps1` when hub data is missing, runs `flubnf engine-update`, installs the engine from `pybnf-pf-<sha>.tar.gz` (unpacked to `%LOCALAPPDATA%\FluBNF\PyBNF-Private`, which a newer archive replaces) or `pybnf.bundle` into the engine venv `%USERPROFILE%\.venvs\flubnf-engine` (Python 3.12 or 3.11), retries a failed install on every open while an engine file or folder is there, then starts the console ([WINDOWS.md](WINDOWS.md#the-particle-filter-engine-on-windows)) Before the console starts, runs `scripts\windows\shortcuts.ps1` when the Start menu shortcut is missing or opens another folder (`FLUBNF_SHORTCUTS=off` skips it). | user |
| `setup.ps1` | Windows | Twin of `setup.sh` plus Perl and engine checks; names the engine file `FluBNF.bat` would install from (and then skips the GitHub access check); writes User env vars and `.flubnf.env.cmd`, runs doctor | `FluBNF.bat` (`-NoPrompt`), user, CI job `windows-setup-script` |
| `scripts/windows/shortcuts.ps1` | Windows | Puts FluBNF in the Start menu (so Windows search finds it by name) and, once per account, on the Desktop: `cmd.exe /c FluBNF.bat` with `scripts/windows/FluBNF.ico`, pinnable to the taskbar. Never fails a launch | `FluBNF.bat` |
| `scripts/cut_engine_archive.sh` | maintainer | Cuts `pybnf-pf-<sha>.tar.gz` from the fork with `git archive`; the file the others install | maintainer ([ENGINE.md](ENGINE.md)) |
| `.githooks/pre-push` | git | On a push to `*/main`, runs both suites with `FLUBNF_HUB=/nonexistent`, as CI does | git (enabled by `setup.sh`) |

Files they leave behind (all gitignored or inside `.venv`, except the Windows shortcuts and their record, which live in the user profile):

| File | Written by | Read by |
|---|---|---|
| `.flubnf.env` | `setup.sh`, `setup_engine.sh` | `FluBNF.command`, `reinstall.sh` |
| `.flubnf.env.cmd` | `setup.ps1` | `FluBNF.bat` |
| `.venv/.pyproject.stamp` (`.venv\pyproject.stamp` on Windows) | `FluBNF.command`, `FluBNF.bat` | the same launcher (refresh deps when `pyproject.toml` changes) |
| `.venv/.engine-attempt` (`.venv\engine-attempt.txt` on Windows) | `FluBNF.command`, `FluBNF.bat` | the same launcher: after a failed install, skips the retry only while there is nothing to install from (no engine file, bundle or checkout) |
| `%LOCALAPPDATA%\FluBNF\start-menu.txt`, `desktop-shortcut.txt`; `FluBNF.lnk` in the Start menu's Programs folder and on the Desktop | `scripts/windows/shortcuts.ps1` | `FluBNF.bat`: the folder the Start menu entry opens (remade when it differs); the Desktop shortcut is made once per account |
| `app/state/engine_update.json` | `flubnf engine-update` (every launcher) | the console's build warning: why the last open left the engine where it is |
| `FluBNF.app/Contents/MacOS/FluBNF` | `build_app_host.sh` | `flubnf-launch`, `FluBNF.command` |
| `.venv/.app-host.stamp` | `build_app_host.sh` | `build_app_host.sh`: `ok` with the fingerprint built for; `fail` (no usable host) or `kept` (a rebuild failed, and the host already installed still loads and stays in use), each with the fingerprint, the compiler and the reason |
| `app/state/logs/launch.log` | `flubnf-launch`, the host | people: what a Dock launch did, and why it went to Terminal |
| `<per-user temp folder>/edu.nau.flubnf-<uid>/terminal-handover-<cksum of the clone's real path>` (macOS: `getconf DARWIN_USER_TEMP_DIR`; elsewhere `$TMPDIR`) | `flubnf-launch` (each automatic reopen of Terminal that opened, in epoch seconds; removed when a console starts: a ready launch reaching it, or `FluBNF.command` running without the app) | `flubnf-launch`: another reopen within ten minutes is an alert, so a failure that repeats cannot reopen Terminal without end. Outside the clone, which FluBNF.app may be refused |
| `.venv/.app-host.src` | `build_app_host.sh` (a successful build) | `build_app_host.sh`: a host from other source is never kept after a failed rebuild, and is made unrunnable |

PyBNF checkout search order (every script and `flubnf/settings.py`): `FLUBNF_PYBNF`, then `PyBNF-pf`, then `PyBNF-Private`. On Windows each name is looked for under `%USERPROFILE%\Documents\GitHub`, then `%LOCALAPPDATA%\FluBNF` (never `%USERPROFILE%\GitHub`), and `FluBNF.bat`, `setup.ps1` and `flubnf/settings.py` pass over any folder, `FLUBNF_PYBNF`'s included, that holds no engine (no `.git`, no `pybnf\pf.py`), as `FluBNF.command` and `settings.py` do on macOS.

Tests that pin these scripts: `tests/test_engine_bundle.py`, `tests/test_launcher_update.py`, `tests/test_mac_app_bundle.py`, `tests/test_reinstall_script.py`, `tests/test_first_run_sparse_hub.py`, `tests/test_windows_controlled_folder_access.py` ([tests/README.md](../tests/README.md)).

## Reinstalling from scratch (macOS and Linux)

The [README](../README.md#install-and-run) gives the one line; this is what it does. Save the engine archive in Downloads and delete any older `pybnf-pf-*.tar.gz` downloads first, then:

    curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/reinstall.sh | bash

`reinstall.sh` sets the old install aside with a date stamp (nothing is deleted), moves every other engine file (`pybnf*.tar.gz`, `pybnf*.bundle`) out of the folders setup searches into `Downloads/old-engine-files`, installs fresh, installs the engine from the archive it found, and opens the console. A machine that is already current is left alone, and so is a developer's checkout with uncommitted work. The `FLUBNF_REINSTALL_*` variables below change those choices; the script's header lists each. The line does not run on Windows: "Resetting or reinstalling (Windows)" in [INSTALL-STUDENTS.md](INSTALL-STUDENTS.md#resetting-or-reinstalling-windows) has the Command Prompt steps.

## FluBNF.app in the Dock (macOS)

The Dock names a window, picks its icon and decides what Keep in Dock pins from the app bundle that holds the running program. A venv's `python` is `Python.app` (python.org, Homebrew) or a bare `python3.12` (Anaconda), so a console started that way shows as "Python" or "python3.12", and a kept icon cannot reopen FluBNF. Renaming at run time does not change this.

So `setup.sh` compiles a small host, `scripts/macos/flubnf_host.c`, into `FluBNF.app/Contents/MacOS/FluBNF`. It links the libpython the venv was made from and runs as the venv's own `python`: same `sys.prefix`, packages and `sys.executable`. Its program sits inside `FluBNF.app`, so the window is FluBNF in the Dock, with one icon, and Keep in Dock pins `FluBNF.app`. `ps` shows `…/FluBNF.app/Contents/MacOS/FluBNF …/.venv/bin/flubnf window`, which the single-instance takeover and `reinstall.sh`'s running check both match.

A Dock launch (`flubnf-launch`) runs `FluBNF.command` headless, output in `app/state/logs/launch.log`, then execs the host. It opens `FluBNF.command` in Terminal instead for: a first run; local edits in the way of the update; a dependency refresh; an engine install; no host; checks that fail or take over two minutes; a console that stops within 30 s; `FLUBNF_LAUNCH=terminal`. It never opens Terminal twice within ten minutes without a console starting in between: the second time is an alert. A Terminal launch runs the console under the host too, once it exists, and without it after a failed start. A copy that cannot start at all (moved out of its clone, or an old clone `reinstall.sh` set aside) shows an alert saying so.

The host is per machine and gitignored. A fresh clone opens through Terminal until setup has built it. It is rebuilt when the venv, its packages or the source change. A failed build (no Command Line Tools, a static-only Python) is not retried on every launch; installing the tools earns a retry. It is signed ad hoc (`codesign -s -`), which Apple Silicon requires and which is enough for a program built on the same Mac. Gatekeeper only checks quarantined files, and a file compiled locally has no quarantine flag.

FluBNF lives in `~/GitHub`, not `~/Documents/GitHub`. macOS keeps Documents, Desktop and Downloads from apps it has not been told to trust, and FluBNF.app cannot be: its executable is a shell script, so macOS asks whether `/bin/bash` may read the folder (the TCC log says `BUNDLE_ATTRIBUTION: executable path file:///bin/bash resolves to attributed bundle: (null)`), and neither Files and Folders nor Full Disk Access for FluBNF counts. The app can still write the files it made (`launch.log`) but reads nothing else there (`Operation not permitted`). Terminal is allowed, which is why `FluBNF.command` always worked. So a Dock launch that finds its clone refused hands over to Terminal, and `FluBNF.command` there moves the clone to `~/GitHub` (`scripts/macos/move_home.sh`), together with the FluSight hub and the PyBNF checkout, and starts again from its new folder. After that the Dock opens FluBNF directly. GitHub Desktop then lists those repositories as missing: Locate… points it at the new folders. `FLUBNF_MOVE=off` keeps a clone where it is (FluBNF then always runs through Terminal).

To check a Mac: `scripts/macos/build_app_host.sh --force` shows the build; `tail app/state/logs/launch.log` shows what the last Dock launch did.

## Environment variables

Paths default to `~/GitHub/<name>` (an older setup's `~/Documents/GitHub/<name>` is used until `FluBNF.command` moves it); on Windows, to `%LOCALAPPDATA%\FluBNF\<name>` unless a checkout already exists at the Documents path ([WINDOWS.md](WINDOWS.md)).

**Machine paths** (the console reads them through `flubnf/settings.py`; `flubnf doctor` reports which externals a machine can see, and each resolves from `flubnf/settings.py` unless one of these points it elsewhere: `FLUBNF_HUB` the hub clone, `FLUBNF_BNG` BNG2.pl, `FLUBNF_PY_ENGINE` the python of the engine venv, `FLUBNF_PYBNF` the PyBNF checkout):

| Variable | Honored by | Default |
|---|---|---|
| `FLUBNF_HUB` | `flubnf/settings.py`, `setup.sh`, `setup.ps1`, `FluBNF.bat`; set to `/nonexistent` by CI and `.githooks/pre-push` | `FluSight-forecast-hub` checkout |
| `FLUBNF_PYBNF` | `flubnf/settings.py`, every launcher and setup script but `install.sh` | `PyBNF-pf`, else `PyBNF-Private` checkout |
| `FLUBNF_PY_ENGINE` | `flubnf/settings.py`, `FluBNF.command`, `reinstall.sh`; written by the setup scripts; `FluBNF.bat` sets it, for the console it starts, to the python of the engine venv it verified (`FLUBNF_ENGINE_VENV`) | `~/.venvs/flubnf/bin/python`, else `~/.venvs/flubnf-engine/bin/python`; on Windows `%USERPROFILE%\.venvs\flubnf\Scripts\python.exe`, else `%USERPROFILE%\.venvs\flubnf-engine\Scripts\python.exe` |
| `FLUBNF_BNG` | `flubnf/settings.py` | BNG2.pl of `.venv`'s `bionetgen`, else on `PATH` |
| `FLUBNF_ENGINE_VENV` | `setup.sh`, `setup_engine.sh`, `setup.ps1`, `FluBNF.bat`, `reinstall.sh` | `~/.venvs/flubnf-engine` (`%USERPROFILE%\.venvs\flubnf-engine` on Windows) |

**Install and launch:**

| Variable | Honored by | Default |
|---|---|---|
| `FLUBNF_DIR` | `install.sh`, `reinstall.sh` | `~/GitHub/flubnf` (`reinstall.sh`: an existing `~/Documents/GitHub/flubnf` when there is none) |
| `FLUBNF_MOVE` | `FluBNF.command`, `move_home.sh` | unset = move a clone out of Documents, Desktop or Downloads; `off` leaves it |
| `FLUBNF_HOME_DIR` | `move_home.sh` | `~/GitHub` (where a clone moves to) |
| `FLUBNF_REPO` | `reinstall.sh` | `https://github.com/elyfmiller/flubnf` |
| `FLUBNF_UPDATE` | `FluBNF.command`, `FluBNF.bat` | unset = fast-forward; `off` skips it and the engine update (`flubnf engine-update`); `force` resets to origin |
| `FLUBNF_LAUNCH` | `flubnf-launch` (`FluBNF.app`) | unset = quiet launch; `terminal` opens `FluBNF.command` in Terminal (not twice within ten minutes: the second is an alert); `ready` is FluBNF.command's own launch. `open` does not pass a shell's variables on: run `FLUBNF_LAUNCH=terminal FluBNF.app/Contents/MacOS/flubnf-launch`, or `launchctl setenv FLUBNF_LAUNCH terminal` (until logout) |
| `FLUBNF_PREPARE_ONLY` | `FluBNF.command`; set by `flubnf-launch` | unset; `1` = update and checks only, exit 75 when Terminal is needed |
| `FLUBNF_BOOT_STATUS` | `flubnf-launch`, the host, `host_boot.py`, `flubnf/cli.py`; set by `FluBNF.command` (also as `--ready <file>`) | the status file of a Terminal waiting on the app: it says the app quit early until the console's window is shown (or its page served), which empties it; a failure at startup writes its reason there, and a SIGTERM before then (a stop on request) empties it |
| `FLUBNF_HOST_FALLBACK` | the host, `host_boot.py`; set by `flubnf-launch` | unset; `1` = a startup failure goes back to Terminal (through `flubnf-launch --handover`). Removed before the console starts |
| `FLUBNF_HOST_ANY_OS` | `build_app_host.sh` (test hook) | unset; `1` builds the host off macOS |
| `FLUBNF_NO_DATA` | `setup.sh`, `setup.ps1` | unset; `1` skips the hub clone |
| `FLUBNF_NO_PROBE` | `setup.ps1` | unset; `1` skips the fork access probe |
| `FLUBNF_PYBNF_BUNDLE` | `setup_engine.sh`, `FluBNF.bat`, `setup.ps1`; set by `reinstall.sh` | unset = search Downloads and nearby folders. Either shape: a `.tar.gz` is installed as an archive, anything else as a bundle |
| `FLUBNF_PYBNF_REMOTE` | `setup_engine.sh`, `setup.ps1` (Windows: `setx FLUBNF_PYBNF_REMOTE "…"`, then a new window) | `https://github.com/elyfmiller/PyBNF-Private.git` |
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
| `FLUBNF_DOWNLOAD_REPLACE` | `flubnf/window_downloads.py` (the macOS window) | unset = a download saved over an existing file replaces it once you confirm Replace (under pywebview 6 only; another version keeps its own save, and the startup trace says so); `off` keeps pywebview's own save, which leaves the old file in place |
| `FLUBNF_ORACLE_RECORD`, `FLUBNF_ORACLE_FULL` | `tests/test_oracle*.py` | lab-only record; `FULL=1` compares every screened date |
