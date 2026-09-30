"""FluBNF.app as a Dock app: the bundle, its launcher, the in-bundle Python
host (scripts/macos/flubnf_host.c) and every handover to Terminal.

The Dock names a window by the bundle of the executable that owns it. So the
window must run from an executable inside FluBNF.app, not from Python.app
(framework Python) or a bare python3.x (conda). These tests pin what can be
checked off a Mac: the bundle, each branch of flubnf-launch and of
FluBNF.command's headless mode, and the host itself, which builds and runs on
Linux too (the venv logic in CPython's getpath is the same code). On a Mac
the build also checks that the host belongs to its bundle.

Stand-ins replace every program a launcher starts (Terminal, the host, the
build), so no test opens a window or a Terminal.
"""
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import sysconfig
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from flubnf import __version__                                    # noqa: E402
from flubnf.cli import (APP_ENTRY_MARKERS, _cmdline_has_marker,    # noqa: E402
                        _pid_cmdline, _terminate_predecessor)

APP = REPO / "FluBNF.app"
PLIST = APP / "Contents" / "Info.plist"
LAUNCH = APP / "Contents" / "MacOS" / "flubnf-launch"
COMMAND = REPO / "FluBNF.command"
MACOS = REPO / "scripts" / "macos"
BOOT = MACOS / "host_boot.py"
HOST_REL = "FluBNF.app/Contents/MacOS/FluBNF"

posix_only = pytest.mark.skipif(sys.platform.startswith("win"),
                                reason="bash launchers")


def _script(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/bash\n" + body)
    path.chmod(0o755)
    return path


def _env(**extra) -> dict:
    """This environment without FluBNF's own variables or Apple's Terminal
    (whose window FluBNF.command would close), plus `extra`."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("FLUBNF_") and k != "TERM_PROGRAM"}
    env.update({k: str(v) for k, v in extra.items()})
    return env


@pytest.fixture(autouse=True)
def _own_tmpdir(tmp_path, monkeypatch):
    """Each test its own TMPDIR: flubnf-launch keeps its reopen guard in a
    per-user folder under it, which must not carry over between tests."""
    d = tmp_path / "tmpdir"
    d.mkdir()
    monkeypatch.setenv("TMPDIR", str(d))
    return d


def _guard_dir() -> Path:
    """The per-user folder of flubnf-launch's reopen records (off a Mac:
    under TMPDIR)."""
    return Path(os.environ["TMPDIR"]) / f"edu.nau.flubnf-{os.getuid()}"


def _handover_stamp(repo: Path) -> Path:
    """Where flubnf-launch records its last automatic reopen of Terminal
    for the clone `repo`: one record per clone, named by the checksum of
    its real path (FluBNF.command names the same file)."""
    crc = subprocess.run(["cksum"], input=f"{repo.resolve()}\n", text=True,
                         capture_output=True, check=True).stdout.split()[0]
    return _guard_dir() / f"terminal-handover-{crc}"


def _read(rec: Path, name: str):
    """A stand-in's recorded lines, or None when it never ran."""
    p = rec / name
    return p.read_text().splitlines() if p.is_file() else None


def _opener(tmp_path: Path, rec: Path) -> Path:
    """A stand-in for /usr/bin/open that records its call and, like open,
    fails when the file to open is not there."""
    return _script(tmp_path / "bin" / "open",
                   f'printf "%s\\n" "$@" > "{rec}/open"\n[ -e "${{@: -1}}" ]\n')


def _patched_launcher(opener: Path, osascript: Path, limit=None, head=None) -> str:
    """flubnf-launch with Terminal and the alert swapped for recorders (and
    `head`, which tests the folder's access, for a stand-in if given)."""
    src = LAUNCH.read_text()
    swaps = [("local open=/usr/bin/open", f'local open="{opener}"'),
             ("local osascript=/usr/bin/osascript", f'local osascript="{osascript}"')]
    if head is not None:
        swaps.append(("local head=/usr/bin/head", f'local head="{head}"'))
    if limit is not None:
        swaps.append(("local limit=120", f"local limit={limit}"))
    for old, new in swaps:
        assert old in src, f"{old!r} is gone from flubnf-launch; the tests swap that line"
        src = src.replace(old, new, 1)
    return src


# ------------------------------------------------------------------ bundle

def test_the_bundle_is_a_regular_dock_app():
    info = plistlib.loads(PLIST.read_bytes())
    assert info["CFBundlePackageType"] == "APPL"
    assert info["CFBundleIdentifier"] == "edu.nau.flubnf"
    assert info["CFBundleName"] == info["CFBundleDisplayName"] == "FluBNF"
    # either key would take the icon out of the Dock
    assert "LSUIElement" not in info and "LSBackgroundOnly" not in info
    assert info["NSHighResolutionCapable"] is True
    assert (APP / "Contents" / "Resources"
            / (info["CFBundleIconFile"] + ".icns")).is_file()
    # lockstep, as flubnf/__init__.py says
    assert info["CFBundleShortVersionString"] == info["CFBundleVersion"] == __version__


def _git(*args, cwd=REPO) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, text=True)


def test_a_fresh_clone_opens_through_the_tracked_launcher():
    """The bundle's executable is the tracked script, so a clone opens before
    any host is built. The host is built per machine and never tracked, so
    it can never be a tracked file that blocks the launcher's fast-forward."""
    info = plistlib.loads(PLIST.read_bytes())
    assert APP / "Contents" / "MacOS" / info["CFBundleExecutable"] == LAUNCH
    staged = _git("ls-files", "-s", "FluBNF.app/Contents/MacOS/flubnf-launch").stdout
    assert staged.startswith("100755 "), staged
    assert _git("ls-files", HOST_REL).stdout == ""
    for built in (HOST_REL, HOST_REL + ".new", "app/state/logs/launch.log",
                  ".venv/.app-host.stamp"):
        assert _git("check-ignore", "-q", built).returncode == 0, built
    assert _git("check-ignore", "-q",
                "FluBNF.app/Contents/MacOS/flubnf-launch").returncode == 1


@posix_only
@pytest.mark.parametrize("script", [
    LAUNCH, COMMAND, MACOS / "build_app_host.sh", REPO / "setup.sh"])
def test_the_scripts_parse(script):
    r = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_the_hosted_command_lines_are_takeover_targets():
    """ps shows the host's exec line; the pidfile takeover and reinstall.sh's
    running-console check must both match it."""
    pattern = re.search(r"pgrep -U \"\$\(id -u\)\" -f '([^']+)'",
                        (REPO / "reinstall.sh").read_text()).group(1)
    for sub in ("window", "app"):          # a Dock launch, a Terminal launch
        cmd = ("/Users/x/flubnf/FluBNF.app/Contents/MacOS/FluBNF "
               f"/Users/x/flubnf/.venv/bin/flubnf {sub}")
        assert _cmdline_has_marker(cmd, APP_ENTRY_MARKERS), cmd
        assert re.search(pattern, cmd), (pattern, cmd)


# ---------------------------------------------------- flubnf-launch (Dock)

def _launch_repo(tmp_path, *, venv=True, command=True, prep="exit 0",
                 build="exit 0", host=True, limit=None, refused=False):
    """A clone as FluBNF.app sees it, with a stand-in for every program the
    launcher starts; each records its call in rec/."""
    repo = tmp_path / "clone"
    rec = tmp_path / "rec"
    rec.mkdir(parents=True)
    macos = repo / "FluBNF.app" / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    opener = _opener(tmp_path, rec)
    alert = _script(tmp_path / "bin" / "osascript",
                    f'printf "%s\\n" "$@" > "{rec}/osascript"\n')
    launcher = macos / "flubnf-launch"
    # macOS privacy refusing this app its folder: reads fail with EPERM
    head = _script(tmp_path / "bin" / "head",
                   'echo "head: $3: Operation not permitted" >&2\nexit 1\n') \
        if refused else None
    launcher.write_text(_patched_launcher(opener, alert, limit, head))
    launcher.chmod(0o755)
    if command:
        _script(repo / "FluBNF.command", f'env > "{rec}/prep.env"\n{prep}\n')
    if venv:
        _script(repo / ".venv" / "bin" / "flubnf", "exit 0\n")
        (repo / ".venv" / "pyvenv.cfg").write_text(
            "home = /opt/base/bin\nversion = 3.12.4\n")
    _script(repo / "scripts" / "macos" / "build_app_host.sh",
            f'echo built > "{rec}/build"\n{build}\n')
    if host:
        _script(macos / "FluBNF",
                f'printf "%s\\n" "$@" > "{rec}/host"\nenv > "{rec}/host.env"\n')
    (repo / ".flubnf.env").write_text('export FLUBNF_HUB="/x/hub"\n')
    return repo, rec


def _launch(repo: Path, args=(), **env):
    t0 = time.monotonic()
    r = subprocess.run(["bash", str(repo / "FluBNF.app/Contents/MacOS/flubnf-launch"),
                        *args],
                       env=_env(**env), stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=120)
    log = repo / "app" / "state" / "logs" / "launch.log"
    return r, (log.read_text() if log.is_file() else ""), time.monotonic() - t0


def _envfile(lines) -> dict:
    return dict(line.split("=", 1) for line in lines if "=" in line)


@posix_only
def test_a_ready_clone_execs_the_host_as_the_window(tmp_path):
    repo, rec = _launch_repo(tmp_path)
    r, log, _ = _launch(repo)
    assert r.returncode == 0, log
    assert _read(rec, "open") is None, log
    # the checks ran headless, with no way to wait on a hidden prompt
    prep = _envfile(_read(rec, "prep.env"))
    assert prep["FLUBNF_PREPARE_ONLY"] == "1" and prep["GIT_TERMINAL_PROMPT"] == "0"
    assert _read(rec, "build") == ["built"]
    # the takeover's marker, by absolute path
    assert _read(rec, "host") == [str(repo / ".venv" / "bin" / "flubnf"), "window"]
    env = _envfile(_read(rec, "host.env"))
    assert env["FLUBNF_HOST_FALLBACK"] == "1"
    # what a Terminal launch would give the console
    assert env["PATH"].startswith(f"{repo}/.venv/bin:/opt/base/bin:"), env["PATH"]
    assert env["FLUBNF_HUB"] == "/x/hub"
    assert env.get("LANG")
    assert "starting the console" in log


@posix_only
@pytest.mark.parametrize("via", ["env", "argv"])
def test_a_ready_launch_skips_the_checks_and_starts_the_console(tmp_path, via):
    """Ready (FluBNF.command ran the update, the checks and the build a
    moment ago, then asked LaunchServices for the app): straight to the
    host, as `app` (what FluBNF.command runs), output left with the asking
    Terminal (launch.log gets one line naming how ready arrived), the
    status file passed through. Ready arrives as FLUBNF_LAUNCH=ready, or as
    `--ready <status file>` arguments, which macOS cannot drop; either way
    the host gets FLUBNF_LAUNCH=ready, so its own handover reports too."""
    repo, rec = _launch_repo(tmp_path)
    status = tmp_path / "boot"
    if via == "env":
        r, log, _ = _launch(repo, FLUBNF_LAUNCH="ready",
                            FLUBNF_BOOT_STATUS=str(status))
    else:
        r, log, _ = _launch(repo, args=["--ready", str(status)])
    assert r.returncode == 0, r.stdout + r.stderr
    assert _read(rec, "prep.env") is None and _read(rec, "build") is None
    assert _read(rec, "host") == [f"{repo}/.venv/bin/flubnf", "app"]
    env = _envfile(_read(rec, "host.env"))
    assert env["FLUBNF_HOST_FALLBACK"] == "1"
    assert env["FLUBNF_BOOT_STATUS"] == str(status)
    assert env["FLUBNF_LAUNCH"] == "ready"
    assert log.count("\n") == 1 and "ready launch from FluBNF.command" in log
    assert f"via {via}" in log
    assert "starting the console" in r.stdout
    assert _read(rec, "open") is None


@posix_only
def test_a_ready_launch_ignores_a_launchd_wide_terminal_setting(tmp_path):
    """`launchctl setenv FLUBNF_LAUNCH terminal` (docs/LAUNCHERS.md) holds
    for every app until logout and may win over open's --env. The --ready
    arguments still make the launch ready, and it does not hand back."""
    repo, rec = _launch_repo(tmp_path)
    status = tmp_path / "boot"
    r, _, _ = _launch(repo, args=["--ready", str(status)],
                      FLUBNF_LAUNCH="terminal")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _read(rec, "host") == [f"{repo}/.venv/bin/flubnf", "app"]
    assert _read(rec, "open") is None and not status.exists()


@posix_only
def test_a_ready_launch_that_cannot_start_reports_and_never_opens_terminal(tmp_path):
    """No second Terminal from a launch a Terminal asked for: the reason
    goes to the status file, and that Terminal starts the console itself."""
    repo, rec = _launch_repo(tmp_path, host=False)
    status = tmp_path / "boot"
    r, _, _ = _launch(repo, FLUBNF_LAUNCH="ready",
                      FLUBNF_BOOT_STATUS=str(status))
    assert r.returncode == 1
    assert "no FluBNF host" in status.read_text()
    assert _read(rec, "open") is None and _read(rec, "osascript") is None


def _handover(repo: Path, why="the console stopped at startup (exit 3)",
              args=(), **env):
    return subprocess.run(
        ["bash", str(repo / "FluBNF.app/Contents/MacOS/flubnf-launch"),
         *args, "--handover", why],
        env=_env(**env), stdin=subprocess.DEVNULL, capture_output=True,
        text=True, timeout=60)


def _age(stamp: Path, minutes: float) -> None:
    stamp.write_text(f"{int(time.time() - minutes * 60)}\n")


@posix_only
def test_a_handover_reopens_terminal_once_then_alerts(tmp_path):
    """The host and host_boot.py hand a startup failure to the launcher.
    It reopens Terminal, but not twice within HANDOVER_MIN minutes: the
    second is an alert, so a failure that repeats cannot open Terminal
    without end. The record lives outside the clone, in seconds."""
    repo, rec = _launch_repo(tmp_path)
    r = _handover(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _read(rec, "open") == ["-a", "Terminal", str(repo / "FluBNF.command")]
    assert _read(rec, "prep.env") is None and _read(rec, "host") is None
    log = (repo / "app/state/logs/launch.log").read_text()
    assert "stopped at startup (exit 3)" in log
    stamp = _handover_stamp(repo)
    assert abs(int(stamp.read_text()) - time.time()) < 60
    (rec / "open").unlink()
    r = _handover(repo)
    assert r.returncode == 1
    assert _read(rec, "open") is None
    said = "\n".join(_read(rec, "osascript"))
    assert "could not start" in said and "already reopened in Terminal" in said
    assert "as critical" in said
    # the launcher's own reasons too, worded as what they are: a note, not
    # a failure
    (rec / "osascript").unlink()
    r, _, _ = _launch(repo, FLUBNF_LAUNCH="terminal")
    assert r.returncode == 1 and _read(rec, "open") is None
    said = "\n".join(_read(rec, "osascript"))
    assert "FluBNF needs Terminal (FLUBNF_LAUNCH=terminal)" in said
    assert "does not open another so soon" in said
    assert "FluBNF did not open Terminal again" in said and "as critical" not in said
    # nine minutes on, still refused; eleven, allowed again
    (rec / "osascript").unlink()
    _age(stamp, 9)
    assert _handover(repo).returncode == 1 and _read(rec, "open") is None
    _age(stamp, 11)
    assert _handover(repo).returncode == 0
    assert _read(rec, "open") == ["-a", "Terminal", str(repo / "FluBNF.command")]


@posix_only
def test_a_ready_launch_that_reaches_the_console_clears_the_record(tmp_path):
    """The Terminal a handover opened asks for the app again (ready); once
    that launch reaches the console, the next reopen is allowed, so a
    quick second Dock click after a good start is never refused."""
    repo, rec = _launch_repo(tmp_path)
    assert _handover(repo).returncode == 0
    assert _handover_stamp(repo).exists()
    r, _, _ = _launch(repo, args=["--ready", str(tmp_path / "boot")])
    assert r.returncode == 0, r.stdout + r.stderr
    assert not _handover_stamp(repo).exists()
    (rec / "open").unlink()
    assert _handover(repo).returncode == 0 and _read(rec, "open")


@posix_only
def test_a_reopen_it_cannot_record_is_an_alert(tmp_path, monkeypatch):
    """Fail closed: when the record cannot be written, nothing bounds the
    reopens, so there is none."""
    repo, rec = _launch_repo(tmp_path)
    blocker = tmp_path / "a-file"
    blocker.write_text("")
    monkeypatch.setenv("TMPDIR", str(blocker / "sub"))
    r = _handover(repo)
    assert r.returncode == 1
    assert _read(rec, "open") is None
    assert "cannot record reopening Terminal" in "\n".join(_read(rec, "osascript"))


@posix_only
def test_the_record_is_per_clone_and_counts_only_a_terminal_that_opened(tmp_path):
    """A copy moved out of its clone (to Applications) cannot open Terminal:
    each click says why, and leaves no record that would refuse the real
    clone. Two clones keep separate records."""
    moved, mrec = _launch_repo(tmp_path / "moved", command=False)
    for _ in range(2):
        r, _, _ = _launch(moved)
        assert r.returncode == 1
        said = "\n".join(_read(mrec, "osascript"))
        assert "could not open FluBNF.command" in said, said
    assert not _handover_stamp(moved).exists()
    a, arec = _launch_repo(tmp_path / "a")
    b, brec = _launch_repo(tmp_path / "b")
    assert _handover(a).returncode == 0 and _read(arec, "open")
    assert _handover(b).returncode == 0 and _read(brec, "open")
    assert _handover_stamp(a).exists() and _handover_stamp(b).exists()
    assert _handover_stamp(a) != _handover_stamp(b)


@posix_only
@pytest.mark.parametrize("how", ["env", "argv"])
def test_a_handover_from_a_launch_a_terminal_asked_for_reports_to_it(tmp_path, how):
    """A Terminal waits on this launch (FLUBNF_LAUNCH=ready, or --ready):
    the reason goes to that Terminal's status file, and no Terminal or
    alert opens."""
    repo, rec = _launch_repo(tmp_path)
    status = tmp_path / "boot"
    if how == "env":
        r = _handover(repo, FLUBNF_LAUNCH="ready", FLUBNF_BOOT_STATUS=status)
    else:
        r = _handover(repo, args=["--ready", str(status)])
    assert r.returncode == 1
    assert "stopped at startup (exit 3)" in status.read_text()
    assert _read(rec, "open") is None and _read(rec, "osascript") is None


def _launchservices(tmp_path: Path, rec: Path, send: str) -> None:
    """A stand-in for `open -W -n -a FluBNF.app ...`: runs the app's
    launcher and waits, passing the --env values and/or the --args as
    `send` says (both, env, argv, none): macOS may drop some."""
    _script(tmp_path / "osbin" / "open", f"""app="" ; envs=() ; args=()
while [ $# -gt 0 ]; do
  case "$1" in
    -a) app="$2"; shift ;;
    --env) envs+=("$2"); shift ;;
    --stdout|--stderr) shift ;;
    --args) shift; args=("$@"); break ;;
  esac
  shift
done
echo "{send}" >> "{rec}/launches"
case "{send}" in both|env) ;; *) envs=() ;; esac
case "{send}" in both|argv) ;; *) args=() ;; esac
env "${{envs[@]}}" bash "$app/Contents/MacOS/flubnf-launch" "${{args[@]}}"
exit 0
""")


@posix_only
@pytest.mark.parametrize("send", ["both", "argv", "env"])
def test_a_terminal_launch_that_fails_at_startup_never_opens_another_terminal(
        tmp_path, send):
    """The endless-Terminals bug, end to end, through the real FluBNF.command
    and flubnf-launch: FluBNF.command opens the app through LaunchServices,
    the console stops at startup and the host hands over. With the ready
    signal as --env, as --args or both, the failure goes back to the
    waiting Terminal, which starts the console in view: no second
    Terminal."""
    repo, rec = _command_repo(tmp_path)
    path = _as_os(tmp_path, repo, rec)
    macos = repo / "FluBNF.app" / "Contents" / "MacOS"
    terminal = _script(tmp_path / "bin" / "open-terminal",
                       f'printf "%s\\n" "$@" >> "{rec}/terminal"\n')
    alert = _script(tmp_path / "bin" / "osascript",
                    f'printf "%s\\n" "$@" >> "{rec}/alert"\n')
    (macos / "flubnf-launch").write_text(_patched_launcher(terminal, alert))
    (macos / "flubnf-launch").chmod(0o755)
    # the host: under FluBNF.app's flag the console stops at startup and
    # hands over, as host_boot.py does; in Terminal (no flag) it fails too.
    # A few handovers at most, so a regression fails instead of hanging.
    _script(repo / HOST_REL, f"""echo "host $*" >> "{rec}/console"
fb="${{FLUBNF_HOST_FALLBACK:-}}"
unset FLUBNF_HOST_FALLBACK            # as the real host does
if [ -n "$fb" ]; then
  echo x >> "{rec}/handovers"
  [ "$(wc -l < "{rec}/handovers")" -le 3 ] \\
    && bash "$(dirname "$0")/flubnf-launch" --handover "the console stopped at startup (exit 1)"
fi
exit 1
""")
    _launchservices(tmp_path, rec, send)
    r = _command(repo, PATH=path)
    said = r.stdout + r.stderr
    assert _read(rec, "terminal") is None, said
    assert _read(rec, "alert") is None, said
    assert _read(rec, "handovers") == ["x"], said
    # the app's run (fails, reports), then the console in view: under the
    # host, then without it
    assert _read(rec, "console") == [f"host {repo}/.venv/bin/flubnf app"] * 2 \
        + ["direct app"], said
    assert "stopped at startup (exit 1); starting it here to show why" in said


@posix_only
@pytest.mark.parametrize("state", ["usable", "unwritable"])
def test_a_chain_that_loses_its_ready_signal_opens_terminal_at_most_once(
        tmp_path, state):
    """Worst case: macOS drops both the --env values and the --args, so the
    app FluBNF.command opened runs as a Dock launch, and its console stops
    at startup. The first handover opens one Terminal; the app that
    Terminal opens fails the same way, and its handover is an alert. With
    no place to record the reopen (a refused or read-only folder), not even
    the first Terminal opens."""
    repo, rec = _command_repo(tmp_path)
    path = _as_os(tmp_path, repo, rec)
    if state == "unwritable":
        # the record's folder cannot be made (FluBNF.command's own status
        # file, beside it in TMPDIR, still can)
        _guard_dir().write_text("")
    macos = repo / "FluBNF.app" / "Contents" / "MacOS"
    terminal = _script(tmp_path / "bin" / "open-terminal", f"""echo x >> "{rec}/terminal"
[ "$(wc -l < "{rec}/terminal")" -le 4 ] || exit 1
# a new Terminal window: a login environment, not the launcher's
env -u FLUBNF_LAUNCH -u FLUBNF_BOOT_STATUS -u FLUBNF_HOST_FALLBACK \
  -u FLUBNF_PREPARE_ONLY bash "${{@: -1}}"
""")
    alert = _script(tmp_path / "bin" / "osascript",
                    f'echo x >> "{rec}/alert"\n')
    (macos / "flubnf-launch").write_text(_patched_launcher(terminal, alert))
    (macos / "flubnf-launch").chmod(0o755)
    _script(repo / HOST_REL, f"""echo "host $*" >> "{rec}/console"
fb="${{FLUBNF_HOST_FALLBACK:-}}"
unset FLUBNF_HOST_FALLBACK            # as the real host does
if [ -n "$fb" ]; then
  echo x >> "{rec}/handovers"
  [ "$(wc -l < "{rec}/handovers")" -le 6 ] \\
    && bash "$(dirname "$0")/flubnf-launch" --handover "the console stopped at startup (exit 1)"
fi
exit 1
""")
    _launchservices(tmp_path, rec, "none")
    r = _command(repo, PATH=path)
    said = r.stdout + r.stderr
    assert _read(rec, "terminal") == (["x"] if state == "usable" else None), said
    assert _read(rec, "alert") == ["x"], said
    assert len(_read(rec, "handovers")) == (2 if state == "usable" else 1), said


@posix_only
@pytest.mark.parametrize("send", ["argv", "none"])
def test_a_dock_launch_whose_checks_keep_asking_for_terminal_opens_one(tmp_path, send):
    """The Dock half of the endless-Terminals bug: the quiet checks hand over
    to Terminal for a reason Terminal cannot clear (an engine install that
    keeps failing while a checkout exists), and FluBNF.command there opens
    the app again. That app used to run the checks again, hand over again,
    and so on. Now it is ready (--args) and starts the console; or, with
    every ready signal lost, its handover is an alert. One Terminal."""
    repo, rec = _command_repo(tmp_path, engine=False)
    path = _as_os(tmp_path, repo, rec)
    checkout = tmp_path / "PyBNF-pf"
    (checkout / ".git").mkdir(parents=True)
    _script(repo / "setup_engine.sh",
            '[ "${1:-}" = --print-bundle ] && exit 0\necho "engine install failed"\nexit 1\n')
    macos = repo / "FluBNF.app" / "Contents" / "MacOS"
    # Terminal: runs FluBNF.command (in the foreground here), and refuses
    # past a few, so a regression fails the test instead of hanging it
    terminal = _script(tmp_path / "bin" / "open-terminal", f"""echo x >> "{rec}/terminal"
[ "$(wc -l < "{rec}/terminal")" -le 4 ] || exit 1
# a new Terminal window: a login environment, not the launcher's
env -u FLUBNF_LAUNCH -u FLUBNF_BOOT_STATUS -u FLUBNF_HOST_FALLBACK \
  -u FLUBNF_PREPARE_ONLY bash "${{@: -1}}"
""")
    alert = _script(tmp_path / "bin" / "osascript",
                    f'printf "%s\\n" "$@" >> "{rec}/alert"\n')
    (macos / "flubnf-launch").write_text(_patched_launcher(terminal, alert))
    (macos / "flubnf-launch").chmod(0o755)
    # a console that starts: it empties the status file, as cli.py does
    _script(repo / HOST_REL, f"""echo "host $*" >> "{rec}/console"
[ -z "${{FLUBNF_BOOT_STATUS:-}}" ] || : > "$FLUBNF_BOOT_STATUS"
exit 0
""")
    _launchservices(tmp_path, rec, send)
    r = subprocess.run(["bash", str(macos / "flubnf-launch")],
                       env=_env(PATH=path, HOME=repo.parent, FLUBNF_PYBNF=checkout),
                       stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       timeout=120)
    log = (repo / "app/state/logs/launch.log").read_text()
    said = log + r.stdout + r.stderr
    assert _read(rec, "terminal") == ["x"], said
    assert "setup work to show" in log
    if send == "argv":
        assert _read(rec, "alert") is None, said
        assert _read(rec, "console") == [f"host {repo}/.venv/bin/flubnf app"], said
    else:
        assert "does not open another so soon" in "\n".join(_read(rec, "alert")), said


@posix_only
def test_a_folder_macos_refuses_is_named_in_the_waiting_terminal(tmp_path):
    """The Mac Studio's launch.log: `./FluBNF.command: Operation not
    permitted`. macOS refuses FluBNF.app ~/Documents while Terminal has it,
    and no setting changes that (the app starts as a shell script, so macOS
    asks about /bin/bash). The ready launch tells the waiting Terminal that
    FluBNF.command moves the folder, opens no settings page, and never
    starts a host that cannot read the venv."""
    home = tmp_path / "home"
    repo, rec = _launch_repo(home / "Documents" / "GitHub", refused=True)
    status = tmp_path / "boot"
    r, _, _ = _launch(repo, args=["--ready", str(status)], HOME=home)
    assert r.returncode == 1, r.stdout + r.stderr
    said = status.read_text()
    assert "in your Documents folder" in said and "moves it to ~/GitHub" in said
    assert "flubnf-launch:" not in r.stdout, "said twice in that Terminal"
    assert _read(rec, "open") is None
    assert _read(rec, "host") is None and _read(rec, "osascript") is None


@posix_only
def test_a_dock_launch_from_documents_goes_to_terminal_then_says_how(tmp_path):
    """From the Dock: no checks it cannot read, straight to Terminal (where
    FluBNF.command moves the folder). Clicked again before that: an alert
    that says what to do, not that Terminal opened moments ago."""
    home = tmp_path / "home"
    repo, rec = _launch_repo(home / "Documents" / "GitHub", refused=True)
    r, log, _ = _launch(repo, HOME=home)
    assert r.returncode == 0, log
    assert _read(rec, "open") == ["-a", "Terminal", str(repo / "FluBNF.command")]
    assert "in your Documents folder" in log
    assert _read(rec, "prep.env") is None and _read(rec, "host") is None
    (rec / "open").unlink()
    r, _, _ = _launch(repo, HOME=home)
    assert r.returncode == 1 and _read(rec, "open") is None
    said = "\n".join(_read(rec, "osascript"))
    assert "Open FluBNF.command in that folder once" in said
    assert "FluBNF cannot open from the Dock yet" in said
    assert "less than" not in said and "as critical" not in said


@posix_only
def test_a_refused_folder_elsewhere_says_to_move_it(tmp_path):
    """Refused outside Documents, Desktop and Downloads (another guarded
    place): no setting helps either, so the reason says to move it."""
    repo, rec = _launch_repo(tmp_path, refused=True)
    status = tmp_path / "boot"
    r, _, _ = _launch(repo, args=["--ready", str(status)], HOME=tmp_path / "home")
    assert r.returncode == 1
    said = status.read_text()
    assert "no privacy setting changes that" in said and "~/GitHub" in said


@posix_only
def test_a_handover_from_a_refused_folder_names_the_refusal(tmp_path):
    """The host could not read the venv (it reads as missing): its
    handover reports the real reason, not a first run."""
    home = tmp_path / "home"
    repo, rec = _launch_repo(home / "Documents", refused=True)
    status = tmp_path / "boot"
    r = _handover(repo, why="no .venv yet (first run, or setup did not finish)",
                  args=["--ready", str(status)], HOME=home)
    assert r.returncode == 1
    assert "in your Documents folder" in status.read_text()


@posix_only
@pytest.mark.parametrize("case, why", [
    ("asked", "FLUBNF_LAUNCH=terminal"),
    ("first-run", "first run"),
    ("setup-work", "setup work to show"),
    ("checks-failed", "the pre-launch checks stopped (status 1)"),
    ("no-builder", "no host builder"),
    ("no-host-build", "no FluBNF host for this Python"),
    ("host-will-not-start", "the FluBNF host would not start"),
    ("unwritable-log", "cannot write"),
])
def test_every_launch_it_cannot_finish_opens_terminal(tmp_path, case, why):
    """Never a bouncing icon that vanishes: each way the quiet launch can
    stop ends in FluBNF.command in Terminal, with the reason logged."""
    repo, rec = _launch_repo(
        tmp_path, venv=case != "first-run",
        prep={"setup-work": "exit 75", "checks-failed": "exit 1"}.get(case, "exit 0"),
        build="exit 1" if case == "no-host-build" else "exit 0",
        host=case != "host-will-not-start")
    if case == "no-builder":
        (repo / "scripts" / "macos" / "build_app_host.sh").unlink()
    if case == "unwritable-log":
        (repo / "app" / "state" / "logs" / "launch.log").mkdir(parents=True)
    r, log, _ = _launch(repo, **({"FLUBNF_LAUNCH": "terminal"} if case == "asked" else {}))
    said = log + r.stdout + r.stderr
    assert _read(rec, "open") == ["-a", "Terminal", str(repo / "FluBNF.command")], said
    assert _read(rec, "host") is None, said
    assert why in (r.stdout if case == "unwritable-log" else log), said


@posix_only
def test_checks_that_hang_are_cut_off_and_handed_to_terminal(tmp_path):
    """git has no connect timeout; a stalled network must not leave a Dock
    launch waiting in silence."""
    repo, rec = _launch_repo(tmp_path, prep="exec sleep 60", limit=1)
    r, log, took = _launch(repo)
    assert _read(rec, "open") == ["-a", "Terminal", str(repo / "FluBNF.command")], log
    assert "took longer than 1s" in log
    assert took < 30


@posix_only
def test_the_cut_off_also_stops_what_the_checks_started(tmp_path):
    """The hang is a git fetch run BY FluBNF.command. Killing only that bash
    leaves the fetch running, holding the repo's locks while Terminal's
    FluBNF.command fetches and merges, so the whole group is stopped."""
    pidfile = tmp_path / "rec" / "child.pid"      # _launch_repo's rec/
    repo, rec = _launch_repo(
        tmp_path, limit=1,
        prep=f"/bin/sh -c 'echo $$ > \"{pidfile}\"; exec sleep 60'\n"
             "echo unreachable")
    r, log, _ = _launch(repo)
    assert "took longer than 1s" in log
    assert _read(rec, "open") == ["-a", "Terminal", str(repo / "FluBNF.command")], log
    pid = int(_read(rec, "child.pid")[0])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        os.kill(pid, 9)
        pytest.fail("the checks' child outlived the cut-off")


@posix_only
def test_a_copy_outside_its_clone_says_so(tmp_path):
    """FluBNF.app dragged to Applications has no FluBNF.command beside it:
    when `open` fails, an alert explains, where the launch would otherwise
    end in silence."""
    repo, rec = _launch_repo(tmp_path, venv=False, command=False)
    r, log, _ = _launch(repo)
    assert r.returncode == 1
    assert _read(rec, "open") == ["-a", "Terminal", str(repo / "FluBNF.command")]
    alert = "\n".join(_read(rec, "osascript") or [])
    assert "display alert" in alert and str(repo) in alert, log
    # its new folder is not a clone: no app/state/logs left in it, and the
    # reason given is the missing FluBNF.command, not a first run
    assert not (repo / "app").exists()
    assert "no FluBNF.command beside FluBNF.app" in r.stdout
    assert "first run" not in r.stdout


@posix_only
def test_a_copy_reinstall_set_aside_never_starts(tmp_path):
    """reinstall.sh renames the old clone and clears its launchers' exec bits
    (its venv's scripts point into the new clone). A kept Dock icon follows
    the rename, so the app honours the mark instead of running
    FluBNF.command through bash regardless."""
    repo, rec = _launch_repo(tmp_path)
    (repo / "FluBNF.command").chmod(0o644)
    r, log, _ = _launch(repo)
    assert r.returncode == 1, log
    assert _read(rec, "prep.env") is None and _read(rec, "host") is None
    assert _read(rec, "open") is None
    assert "set aside by a reinstall" in "\n".join(_read(rec, "osascript") or []), log
    # and reinstall.sh still marks the old launchers that way
    assert re.search(r'for l in FluBNF\.command SetupEngine\.command; do\n\s+\[ -f "\$DEST-old-\$STAMP/\$l" \] && chmod a-x',
                     (REPO / "reinstall.sh").read_text())


# ------------------------------- FluBNF.command: headless and Terminal runs

def _command_repo(tmp_path, *, venv=True, stamp=True, engine=True):
    """A clone for the real FluBNF.command (no .git: the update is skipped),
    its console a stand-in that records each run (the engine update the
    launcher runs first is recorded apart, in "engine-update")."""
    repo = tmp_path / "clone"
    rec = tmp_path / "rec"
    rec.mkdir(parents=True)
    repo.mkdir()
    shutil.copy(COMMAND, repo / "FluBNF.command")
    (repo / "pyproject.toml").write_text("[project]\n")
    if venv:
        _script(repo / ".venv" / "bin" / "flubnf",
                f'if [ "$1" = engine-update ]; then\n'
                f'  echo "$*" >> "{rec}/engine-update"; exit 0\nfi\n'
                f'echo "direct $*" >> "{rec}/console"\nexit 0\n')
        if stamp:
            shutil.copy(repo / "pyproject.toml", repo / ".venv" / ".pyproject.stamp")
    if engine:
        (repo / ".flubnf.env").write_text(
            f'export FLUBNF_PY_ENGINE="{shutil.which("true")}"\n')
    return repo, rec


def _as_os(tmp_path, repo, rec, name="Darwin", *, build="exit 0", host_rc=0,
           opened="ok") -> str:
    """PATH under which `uname -s` says `name`, with a host and a build
    stand-in in the clone, and `open` a stand-in for LaunchServices that
    records its call. `opened`: ok (the console started, emptying the
    status file, and later quit), boot-fail (the app wrote a startup
    failure there), silent (the app died without a word, leaving the
    default) or refuse (open itself failed, as an older macOS without
    --env does)."""
    _script(tmp_path / "osbin" / "uname", f"echo {name}\n")
    _script(tmp_path / "osbin" / "open", f"""printf "%s\\n" "$@" > "{rec}/open"
boot=""
while [ $# -gt 0 ]; do
  case "$1" in --ready) boot="${{2:-}}"; shift ;; esac
  shift
done
[ -z "$boot" ] || cp "$boot" "{rec}/boot-default"
case "{opened}" in
  refuse) exit 1 ;;
  ok) : > "$boot" ;;
  boot-fail) echo "the console stopped at startup (exit 1)" > "$boot" ;;
esac
exit 0
""")
    _script(repo / "scripts" / "macos" / "build_app_host.sh",
            f'echo built >> "{rec}/build"\n{build}\n')
    _script(repo / HOST_REL, f'echo "host $*" >> "{rec}/console"\nexit {host_rc}\n')
    return str(tmp_path / "osbin") + os.pathsep + os.environ["PATH"]


def _command(repo: Path, **env) -> subprocess.CompletedProcess:
    env.setdefault("HOME", repo.parent)
    return subprocess.run(["bash", str(repo / "FluBNF.command")],
                          env=_env(**env),
                          stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=60)


@posix_only
@pytest.mark.parametrize("case", ["first-run", "deps-changed", "engine-install"])
def test_headless_mode_hands_slow_work_to_terminal(tmp_path, case):
    """FluBNF.app runs FluBNF.command headless first; work a person should
    watch exits 75 before it starts, and the app reopens it in Terminal."""
    repo, rec = _command_repo(tmp_path, venv=case != "first-run",
                              stamp=case != "deps-changed",
                              engine=case != "engine-install")
    env = {"FLUBNF_PREPARE_ONLY": "1"}
    if case == "engine-install":
        checkout = tmp_path / "PyBNF-pf"
        (checkout / ".git").mkdir(parents=True)
        env["FLUBNF_PYBNF"] = checkout
        _script(repo / "setup_engine.sh", "exit 0\n")      # --print-bundle: none
    r = _command(repo, **env)
    assert r.returncode == 75, r.stdout + r.stderr
    assert "handing over to Terminal" in r.stdout
    assert _read(rec, "console") is None


@posix_only
def test_headless_mode_stops_before_the_console_when_ready(tmp_path):
    """Ready: exit 0 and nothing started. The app builds and starts the host
    itself, so the headless run does neither, even on a Mac."""
    repo, rec = _command_repo(tmp_path)
    path = _as_os(tmp_path, repo, rec)
    r = _command(repo, FLUBNF_PREPARE_ONLY="1", PATH=path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "· ready" in r.stdout
    assert _read(rec, "console") is None and _read(rec, "build") is None


@posix_only
def test_the_terminal_launch_opens_the_app_through_launchservices(tmp_path):
    """From Terminal the window starts as a Dock click does (open -W -n -a
    FluBNF.app), not as this shell's child: recent macOS never makes a
    Terminal child the active app, so it showed no hover and would not
    resize. The app skips the checks this file just ran: ready as --env,
    and as --args, which macOS cannot drop. The status file starts out
    saying the app quit early; the console empties it once up."""
    repo, rec = _command_repo(tmp_path)
    path = _as_os(tmp_path, repo, rec)
    r = _command(repo, PATH=path)
    assert r.returncode == 0, r.stdout + r.stderr
    args = _read(rec, "open")
    assert args[:6] == ["-W", "-n", "-a", f"{repo}/FluBNF.app", "--env",
                        "FLUBNF_LAUNCH=ready"], args
    boot = [a for a in args if a.startswith("FLUBNF_BOOT_STATUS=")]
    assert len(boot) == 1
    path_ = boot[0].split("=", 1)[1]
    assert args[-3:] == ["--args", "--ready", path_], args
    assert not Path(path_).exists()
    assert _read(rec, "boot-default") == ["FluBNF.app quit before the console started"]
    assert _read(rec, "console") is None          # nothing ran as a child
    assert _read(rec, "build") == ["built"]


@posix_only
@pytest.mark.parametrize("host_rc, again", [
    (0, False), (130, False), (137, False), (143, False),   # quit, Ctrl-C, takeovers
    (1, True), (139, True)])                                # a start that failed
@pytest.mark.parametrize("opened", ["boot-fail", "silent", "refuse"])
def test_the_terminal_launch_runs_the_console_under_the_host(tmp_path, host_rc,
                                                              again, opened):
    """When the app fails at startup (it says so in the status file), dies
    without a word (the status file keeps its default) or macOS will not
    open it, the console starts here in view, under the host, as it did
    before; a start that fails under the host gets one run without it."""
    repo, rec = _command_repo(tmp_path)
    path = _as_os(tmp_path, repo, rec, host_rc=host_rc, opened=opened)
    r = _command(repo, PATH=path)
    assert _read(rec, "open"), r.stdout + r.stderr
    runs = _read(rec, "console")
    assert runs[0] == f"host {repo}/.venv/bin/flubnf app", r.stdout + r.stderr
    assert runs[1:] == (["direct app"] if again else [])
    assert r.returncode == (0 if again else host_rc)
    assert _read(rec, "build") == ["built"]
    if opened == "silent":
        assert "quit before the console started; starting it here" in r.stdout


@posix_only
def test_without_a_status_file_the_terminal_launch_runs_in_view(tmp_path, monkeypatch):
    """No status file (mktemp failed): nothing could report a failure back,
    so the console starts here instead of through LaunchServices."""
    repo, rec = _command_repo(tmp_path)
    path = _as_os(tmp_path, repo, rec)
    monkeypatch.setenv("TMPDIR", str(tmp_path / "no-such-dir"))
    r = _command(repo, PATH=path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _read(rec, "open") is None
    assert _read(rec, "console") == [f"host {repo}/.venv/bin/flubnf app"]


@posix_only
@pytest.mark.parametrize("branch", ["no-host", "open-refused", "no-status-file",
                                    "setup-failed"])
def test_a_terminal_run_without_the_app_lets_the_dock_open_terminal_again(
        tmp_path, branch):
    """A Dock launch that needed Terminal (here: no host for this Python)
    records the reopen. FluBNF.command there then starts the console
    itself, or stops, without ever opening the app: no chain can follow,
    so it clears the record, and the next Dock click that needs Terminal
    opens it instead of an alert."""
    repo, rec = _command_repo(tmp_path, venv=branch != "setup-failed")
    path = _as_os(tmp_path, repo, rec, build="exit 1" if branch == "no-host" else "exit 0",
                  opened="refuse" if branch == "open-refused" else "ok")
    if branch == "no-status-file":
        _script(tmp_path / "osbin" / "mktemp", "exit 1\n")
    if branch == "setup-failed":
        _script(repo / "setup.sh", 'echo "setup failed"\nexit 1\n')
    macos = repo / "FluBNF.app" / "Contents" / "MacOS"
    terminal = _script(tmp_path / "bin" / "open-terminal", f'echo x >> "{rec}/terminal"\n')
    alert = _script(tmp_path / "bin" / "osascript", f'echo x >> "{rec}/alert"\n')
    (macos / "flubnf-launch").write_text(_patched_launcher(terminal, alert))
    (macos / "flubnf-launch").chmod(0o755)
    assert _handover(repo, "no FluBNF host for this Python").returncode == 0
    assert _handover_stamp(repo).exists()
    r = _command(repo, PATH=path)
    said = r.stdout + r.stderr
    assert not _handover_stamp(repo).exists(), said
    assert _read(rec, "console") == (None if branch == "setup-failed" else
                                     ["direct app"] if branch == "no-host" else
                                     [f"host {repo}/.venv/bin/flubnf app"]), said
    assert _handover(repo, "no FluBNF host for this Python").returncode == 0
    assert _read(rec, "terminal") == ["x", "x"] and _read(rec, "alert") is None


@posix_only
@pytest.mark.parametrize("opened", ["ok", "boot-fail", "silent"])
def test_a_terminal_run_that_opened_the_app_keeps_the_record(tmp_path, opened):
    """Once FluBNF.command has opened the app, the record stays: if that app
    lost its ready signal it handed over, and the record is what ends the
    chain."""
    repo, rec = _command_repo(tmp_path)
    path = _as_os(tmp_path, repo, rec, opened=opened)
    stamp = _handover_stamp(repo)
    stamp.parent.mkdir(parents=True)
    stamp.write_text(f"{int(time.time())}\n")
    r = _command(repo, PATH=path)
    assert _read(rec, "open"), r.stdout + r.stderr
    assert stamp.exists()


@posix_only
@pytest.mark.parametrize("name, build", [("Darwin", "exit 1"), ("Linux", "exit 0")])
def test_without_a_host_the_terminal_launch_is_unchanged(tmp_path, name, build):
    """No host (a failed build, no Command Line Tools) or not a Mac: the
    console runs straight from the venv, as it always has."""
    repo, rec = _command_repo(tmp_path)
    path = _as_os(tmp_path, repo, rec, name, build=build)
    r = _command(repo, PATH=path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _read(rec, "console") == ["direct app"]
    # the engine is brought up to production first, once (ENGINE.md)
    assert _read(rec, "engine-update") == ["engine-update --quiet"]
    assert _read(rec, "build") == (["built"] if name == "Darwin" else None)


# --------------------------------- FluBNF.command: out of Documents, once

def _documents_setup(tmp_path):
    """An older setup: the clone, the FluSight hub and PyBNF in
    ~/Documents/GitHub, the engine venv in ~/.venvs importing PyBNF from its
    checkout, and paths to all of them in .flubnf.env, the venv and
    app/state."""
    home = tmp_path / "home"
    gh = home / "Documents" / "GitHub"
    repo, rec = _command_repo(gh)
    repo = repo.rename(gh / "flubnf")
    old = str(repo)
    for name in ("FluSight-forecast-hub", "PyBNF-pf"):
        (gh / name / ".git").mkdir(parents=True)
    engine = home / ".venvs" / "flubnf-engine"
    _script(engine / "bin" / "python", "exit 0\n")
    site = engine / "lib" / "site-packages"
    site.mkdir(parents=True)
    (site / "__editable__.pybnf.pth").write_text(f"{gh}/PyBNF-pf\n")
    (repo / ".flubnf.env").write_text(
        f'export FLUBNF_HUB="{gh}/FluSight-forecast-hub"\n'
        f'export FLUBNF_PY_ENGINE="{engine}/bin/python"\n'
        f'export FLUBNF_PYBNF="{gh}/PyBNF-pf"\n')
    _script(repo / ".venv" / "bin" / "tool", f"#!{old}/.venv/bin/python\n")
    # as Python 3.12's venv writes it: where the venv was made
    (repo / ".venv" / "bin" / "activate").write_text(
        'if [ "${OSTYPE:-}" = "cygwin" ] ; then\n'
        f'    export VIRTUAL_ENV=$(cygpath "{old}/.venv")\n'
        'else\n'
        f'    export VIRTUAL_ENV="{old}/.venv"\n'
        'fi\n')
    vsite = repo / ".venv" / "lib" / "site-packages"
    vsite.mkdir(parents=True)
    (vsite / "__editable__.flubnf.pth").write_text(f"{old}\n{old}-old/keep\n")
    (repo / ".venv" / "bin" / "linked").symlink_to(f"{old}/nowhere")
    (repo / "app" / "state").mkdir(parents=True)
    (repo / "app" / "state" / "datasets.json").write_text(f'{{"dir": "{old}/app/state/x"}}\n')
    path = _as_os(tmp_path, repo, rec)
    shutil.copy(MACOS / "move_home.sh", repo / "scripts" / "macos" / "move_home.sh")
    return home, repo, rec, path, engine


@posix_only
def test_a_clone_in_documents_moves_to_github_with_everything_it_names(tmp_path):
    """macOS never lets FluBNF.app read Documents (it asks about /bin/bash,
    which no setting covers). So FluBNF.command, in Terminal, moves the
    clone, the hub and PyBNF to ~/GitHub, rewrites every path that named
    them, and starts again from there: pull, open, done."""
    home, repo, rec, path, engine = _documents_setup(tmp_path)
    old = str(repo)
    r = _command(repo, PATH=path, HOME=home)
    said = r.stdout + r.stderr
    assert r.returncode == 0, said
    new = home / "GitHub" / "flubnf"
    assert not repo.exists() and new.is_dir(), said
    assert (home / "GitHub" / "FluSight-forecast-hub" / ".git").is_dir()
    assert (home / "GitHub" / "PyBNF-pf" / ".git").is_dir()
    assert not list((home / "Documents" / "GitHub").glob("[FP]*"))
    envf = (new / ".flubnf.env").read_text()
    assert "Documents" not in envf and f"{home}/GitHub/PyBNF-pf" in envf, envf
    assert f"#!{new}/.venv/bin/python" in (new / ".venv" / "bin" / "tool").read_text()
    pth = (new / ".venv" / "lib" / "site-packages" / "__editable__.flubnf.pth").read_text()
    assert pth == f"{new}\n{old}-old/keep\n", "only whole names are rewritten"
    assert (new / ".venv" / "bin" / "linked").is_symlink()
    assert str(new) in (new / "app" / "state" / "datasets.json").read_text()
    assert (engine / "lib" / "site-packages" / "__editable__.pybnf.pth").read_text() \
        == f"{home}/GitHub/PyBNF-pf\n"
    assert f"moved here from {old}" in (new / "app/state/logs/launch.log").read_text()
    # then it started again from the new folder, and opened the app there
    assert "starting again from" in said
    assert _read(rec, "open")[3] == f"{new}/FluBNF.app", said
    assert "Locate" in said


@posix_only
def test_a_clone_moved_by_hand_is_relinked_on_the_next_open(tmp_path):
    """The Mac Studio: the folders reached ~/GitHub but the venv still named
    ~/Documents/GitHub (`bad interpreter`, `No module named 'flubnf'`).
    Every open reads where the venv was made and where the hub and PyBNF
    went, and points the paths there, however the folders moved."""
    home, repo, rec, path, engine = _documents_setup(tmp_path)
    old = str(repo)
    gh = home / "GitHub"
    gh.mkdir()
    for name in ("FluSight-forecast-hub", "PyBNF-pf", "flubnf"):
        (home / "Documents" / "GitHub" / name).rename(gh / name)
    new = gh / "flubnf"
    r = _command(new, PATH=path, HOME=home)
    said = r.stdout + r.stderr
    assert r.returncode == 0, said
    assert f"#!{new}/.venv/bin/python" in (new / ".venv/bin/tool").read_text()
    assert (new / ".venv/lib/site-packages/__editable__.flubnf.pth").read_text() \
        == f"{new}\n{old}-old/keep\n"
    assert "Documents" not in (new / ".flubnf.env").read_text()
    assert (engine / "lib/site-packages/__editable__.pybnf.pth").read_text() \
        == f"{gh}/PyBNF-pf\n"
    assert "relinked" in (new / "app/state/logs/launch.log").read_text()
    assert _read(rec, "open")[3] == f"{new}/FluBNF.app", said
    # nothing left to do: the next open changes nothing
    assert subprocess.run(["bash", str(MACOS / "move_home.sh"), "--relink"], cwd=new,
                          env=_env(HOME=home), capture_output=True).returncode == 1


@posix_only
def test_a_venv_that_still_cannot_load_flubnf_is_reinstalled_into(tmp_path):
    """After the paths are relinked, a venv that still cannot import flubnf
    gets it reinstalled (pip, no dependencies), not a dead console."""
    home, repo, rec, path, _ = _documents_setup(tmp_path)
    gh = home / "GitHub"
    gh.mkdir()
    new = gh / "flubnf"
    repo.rename(new)
    _script(new / ".venv" / "bin" / "python",
            f'echo "$*" >> "{rec}/python"\n[ "$1" != -c ]\n')
    r = subprocess.run(["bash", str(MACOS / "move_home.sh"), "--relink"], cwd=new,
                       env=_env(HOME=home), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "-m pip install -q --no-deps -e ." in _read(rec, "python"), r.stderr
    # headless: never pip in the background; Terminal does it
    r = subprocess.run(["bash", str(MACOS / "move_home.sh"), "--relink"], cwd=new,
                       env=_env(HOME=home, FLUBNF_PREPARE_ONLY=1), capture_output=True)
    assert r.returncode in (1, 3)


@posix_only
@pytest.mark.parametrize("why", ["taken", "off", "running", "not-a-mac"])
def test_a_clone_in_documents_stays_when_it_cannot_move(tmp_path, why):
    """The new folder exists, FLUBNF_MOVE=off, FluBNF is running from this
    clone, or this is not a Mac: nothing moves, and FluBNF runs in place
    (through Terminal) as before."""
    home, repo, rec, path, _ = _documents_setup(tmp_path)
    env = {"PATH": path, "HOME": home}
    running = None
    if why == "taken":
        (home / "GitHub" / "flubnf").mkdir(parents=True)
    elif why == "off":
        env["FLUBNF_MOVE"] = "off"
    elif why == "running":
        fake = _script(tmp_path / "bin" / "flubnf", "sleep 60\n")
        running = subprocess.Popen([str(fake), "app"])
        (repo / "app" / "state" / "app.pid").write_text(str(running.pid))
    else:
        _as_os(tmp_path, repo, rec, "Linux")
    try:
        r = _command(repo, **env)
    finally:
        if running:
            running.kill()
            running.wait()
    said = r.stdout + r.stderr
    assert repo.is_dir() and (repo / ".flubnf.env").read_text().count("Documents") == 2, said
    assert not (home / "GitHub" / "FluSight-forecast-hub").exists()
    assert {"taken": "already exists", "running": "Quit it", "off": "",
            "not-a-mac": ""}[why] in said
    assert r.returncode == 0, said
    if why != "not-a-mac":
        assert _read(rec, "open")[3] == f"{repo}/FluBNF.app", said


@posix_only
def test_headless_mode_hands_the_move_to_terminal(tmp_path):
    """The Dock app's headless run never moves folders out of sight."""
    home, repo, rec, path, _ = _documents_setup(tmp_path)
    r = _command(repo, PATH=path, HOME=home, FLUBNF_PREPARE_ONLY="1")
    assert r.returncode == 75, r.stdout + r.stderr
    assert "moves out of Documents" in r.stdout and repo.is_dir()


# ---------------------------------------------------------------- host_boot

def _boot():
    import importlib.util
    spec = importlib.util.spec_from_file_location("host_boot", BOOT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("exc, expect_terminal", [
    (SystemExit(1), True), (SystemExit("pywebview not installed"), True),
    (ImportError("webview"), True), (SystemExit(0), False),
    (SystemExit(None), False)])
def test_boot_reopens_terminal_only_for_an_early_failure(
        monkeypatch, exc, expect_terminal):
    boot = _boot()
    calls = []
    monkeypatch.setattr(boot, "to_terminal", lambda why: calls.append(why))

    def run(path, run_name):
        raise exc
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    monkeypatch.setattr(sys, "path", list(sys.path))
    with pytest.raises(SystemExit):
        boot.main(["host_boot.py", "/x/.venv/bin/flubnf", "window"],
                  clock=iter([0.0, 1.0]).__next__, run=run)
    assert bool(calls) is expect_terminal


def test_boot_leaves_a_late_crash_alone(monkeypatch):
    boot = _boot()
    calls = []
    monkeypatch.setattr(boot, "to_terminal", lambda why: calls.append(why))

    def run(path, run_name):
        raise RuntimeError("after an hour of use")
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    monkeypatch.setattr(sys, "path", list(sys.path))
    with pytest.raises(RuntimeError):
        boot.main(["host_boot.py", "/x/flubnf", "window"],
                  clock=iter([0.0, 3600.0]).__next__, run=run)
    assert calls == []


@pytest.mark.parametrize("exc", [SystemExit(1), ImportError("webview")])
def test_boot_reports_to_the_asking_terminal_instead_of_opening_one(
        monkeypatch, tmp_path, exc):
    """A launch FluBNF.command made through `open` names a status file: an
    early failure is written there (that Terminal then starts the console
    in view) and no second Terminal opens."""
    boot = _boot()
    status = tmp_path / "boot"
    status.write_text("")
    monkeypatch.setenv("FLUBNF_BOOT_STATUS", str(status))
    calls = []
    monkeypatch.setattr(boot, "to_terminal", lambda why: calls.append(why))

    def run(path, run_name):
        raise exc
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    monkeypatch.setattr(sys, "path", list(sys.path))
    with pytest.raises(SystemExit):
        boot.main(["host_boot.py", "/x/.venv/bin/flubnf", "app"],
                  clock=iter([0.0, 1.0]).__next__, run=run)
    assert calls == []
    assert "at startup" in status.read_text()


def test_boot_runs_the_script_as_python_would(monkeypatch):
    boot = _boot()
    seen = {}

    def run(path, run_name):
        seen.update(path=path, run_name=run_name, argv=list(sys.argv),
                    path0=sys.path[0])
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    monkeypatch.setattr(sys, "path", list(sys.path))
    boot.main(["host_boot.py", "/x/.venv/bin/flubnf", "window"], run=run)
    assert seen == {"path": "/x/.venv/bin/flubnf", "run_name": "__main__",
                    "argv": ["/x/.venv/bin/flubnf", "window"],
                    "path0": os.path.dirname(os.path.abspath("/x/.venv/bin/flubnf"))}


def test_boot_opens_this_clones_launcher_and_never_raises(monkeypatch):
    """Never Terminal directly: the bundle's launcher decides (its guards
    stop a launch from reopening Terminal without end)."""
    boot = _boot()
    monkeypatch.setattr(boot.sys, "platform", "darwin")
    calls = []
    boot.to_terminal("why", run=lambda args, **kw: calls.append(args))
    assert len(calls) == 1 and calls[0][0] == "/bin/bash"
    assert os.path.samefile(calls[0][1], LAUNCH)
    assert calls[0][2:] == ["--handover", "why"]

    def broken(*a, **kw):
        raise OSError("no open here")
    boot.to_terminal("why", run=broken)


# ------------------------------------------------------ the host itself

def _base_python() -> str:
    return getattr(sys, "_base_executable", None) or sys.executable


def _can_embed() -> bool:
    """What build_app_host.sh needs: Python.h, a libpython to link and a C
    compiler (on a Mac, the Command Line Tools)."""
    if sys.platform.startswith("win"):
        return False
    v = sysconfig.get_config_var
    if not Path(v("INCLUDEPY") or "", "Python.h").is_file():
        return False
    if sys.platform == "darwin":
        if subprocess.run(["xcode-select", "-p"], capture_output=True).returncode:
            return False
    elif not (shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")):
        return False
    if v("PYTHONFRAMEWORK"):
        return Path(sys.base_prefix, v("PYTHONFRAMEWORK")).is_file()
    libdir = str(v("LIBDIR"))
    if v("Py_ENABLE_SHARED"):
        return Path(libdir, str(v("LDLIBRARY"))).is_file()
    ver = str(v("LDVERSION") or v("VERSION"))
    return any(Path(libdir, f"libpython{ver}{ext}").is_file() for ext in (".dylib", ".so"))


embeds = pytest.mark.skipif(not _can_embed(),
                            reason="no shared libpython, Python.h or C compiler here")
not_on_a_mac = pytest.mark.skipif(sys.platform == "darwin",
                                  reason="would open Terminal on this Mac")


def _host_clone(tmp_path: Path, name="clone"):
    """A scratch clone holding what the build reads, with a real venv of this
    Python whose flubnf and webview are stand-ins (the build's test run
    imports both). Returns (clone, site-packages)."""
    repo = tmp_path / name
    (repo / "scripts" / "macos").mkdir(parents=True)
    (repo / "FluBNF.app" / "Contents" / "MacOS").mkdir(parents=True)
    for f in ("flubnf_host.c", "build_app_host.sh", "host_boot.py"):
        shutil.copy(MACOS / f, repo / "scripts" / "macos" / f)
    shutil.copy(PLIST, repo / "FluBNF.app" / "Contents" / "Info.plist")
    subprocess.run([_base_python(), "-m", "venv", "--without-pip", str(repo / ".venv")],
                   check=True)
    purelib = Path(subprocess.run(
        [str(repo / ".venv" / "bin" / "python"), "-c",
         "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        capture_output=True, text=True, check=True).stdout.strip())
    for pkg in ("flubnf", "webview"):
        (purelib / pkg).mkdir(parents=True, exist_ok=True)
        (purelib / pkg / "__init__.py").write_text("")
    return repo, purelib


def _build(repo: Path, *args, **env) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(repo / "scripts" / "macos" / "build_app_host.sh"), *args],
                          env=_env(FLUBNF_HOST_ANY_OS=1, **env),
                          capture_output=True, text=True, timeout=300)


def _built(tmp_path: Path):
    repo, purelib = _host_clone(tmp_path)
    b = _build(repo)
    assert b.returncode == 0, b.stdout + b.stderr
    return repo, purelib, repo / HOST_REL


@posix_only
@embeds
def test_the_host_runs_as_the_venvs_python(tmp_path):
    """sys.prefix and sys.executable are the venv's, launcher variables that
    would point getpath elsewhere are gone, and a child is the venv's
    python, not the host."""
    repo, _, host = _built(tmp_path)
    probe = ("import os, subprocess, sys; print(sys.prefix); print(sys.executable); "
             "print(os.environ.get('__PYVENV_LAUNCHER__')); "
             "print(os.environ.get('PYTHONHOME')); "
             "print(subprocess.run([sys.executable, '-c', 'import sys; print(sys.prefix)'],"
             " capture_output=True, text=True).stdout.strip())")
    r = subprocess.run([str(host), "-c", probe], capture_output=True, text=True,
                       timeout=60, env=_env(__PYVENV_LAUNCHER__="/elsewhere/python",
                                            PYTHONHOME="/elsewhere"))
    prefix, exe, launcher, home, child = r.stdout.splitlines()[:5]
    venv = (repo / ".venv").resolve()
    assert Path(prefix).resolve() == venv, r.stderr
    assert exe.endswith("/.venv/bin/python") and Path(exe).parents[1].resolve() == venv
    assert launcher == home == "None"
    assert Path(child).resolve() == venv


@posix_only
@embeds
def test_the_host_refuses_to_guess(tmp_path):
    repo, _, host = _built(tmp_path)
    loose = tmp_path / "FluBNF"                  # outside any bundle
    shutil.copy(host, loose)
    assert subprocess.run([str(loose), "-c", ""], capture_output=True).returncode == 70
    cfg = repo / ".venv" / "pyvenv.cfg"
    text = cfg.read_text()
    assert re.search(r"(?m)^version\s*=", text), text
    cfg.write_text(re.sub(r"(?m)^version\s*=.*$", "version = 2.7.18", text))
    r = subprocess.run([str(host), "-c", ""], capture_output=True, text=True)
    assert r.returncode == 69 and "not a Python" in r.stderr
    shutil.rmtree(repo / ".venv")
    assert subprocess.run([str(host), "-c", ""], capture_output=True).returncode == 69


@posix_only
@embeds
@not_on_a_mac
def test_a_dock_launch_that_stops_at_startup_goes_to_terminal(tmp_path):
    """Through the real host and host_boot.py: only under FluBNF.app's flag
    and only for a failure. A console run in view by FluBNF.command has no
    flag, so that
    Terminal launch cannot reach this path (FluBNF.command's own launch
    through `open` reports to that Terminal instead); no child sees it."""
    repo, _, host = _built(tmp_path)
    script = repo / ".venv" / "bin" / "flubnf"
    script.write_text("import sys\nsys.exit(3)\n")
    dock = subprocess.run([str(host), str(script), "window"], capture_output=True,
                          text=True, env=_env(FLUBNF_HOST_FALLBACK=1), timeout=60)
    assert dock.returncode == 3
    assert "handing over to FluBNF.command in Terminal" in dock.stderr
    term = subprocess.run([str(host), str(script), "app"], capture_output=True,
                          text=True, env=_env(), timeout=60)
    assert term.returncode == 3 and "Terminal" not in term.stderr
    script.write_text("import os, sys\nprint(sys.argv[1:], os.environ.get('FLUBNF_HOST_FALLBACK'))\n")
    ok = subprocess.run([str(host), str(script), "window"], capture_output=True,
                        text=True, env=_env(FLUBNF_HOST_FALLBACK=1), timeout=60)
    assert ok.returncode == 0 and "Terminal" not in ok.stderr
    assert ok.stdout.strip() == "['window'] None"


@posix_only
@embeds
def test_a_host_that_cannot_start_python_hands_over_to_the_launcher(tmp_path):
    """The host's own checks (no venv, a venv of another Python) never open
    Terminal themselves: under FluBNF.app's flag they exec the bundle's
    flubnf-launch --handover <why>, whose guards decide, and the flag is
    gone from its environment. Without the flag, just the error."""
    repo, _, host = _built(tmp_path)
    rec = tmp_path / "handover"
    _script(host.parent / "flubnf-launch",
            f'printf "%s\\n" "$@" > "{rec}.args"\nenv > "{rec}.env"\n')
    cfg = repo / ".venv" / "pyvenv.cfg"
    cfg.write_text(cfg.read_text().replace("version", "version = 2.7.18\nold_version"))
    r = subprocess.run([str(host), str(repo / ".venv/bin/flubnf"), "window"],
                       capture_output=True, text=True, check=False,
                       env=_env(FLUBNF_HOST_FALLBACK=1), timeout=60)
    args = Path(f"{rec}.args").read_text().splitlines()
    assert args[0] == "--handover" and "is not a Python" in args[1], r.stderr
    assert "FLUBNF_HOST_FALLBACK=" not in Path(f"{rec}.env").read_text()
    Path(f"{rec}.args").unlink()
    plain = subprocess.run([str(host), str(repo / ".venv/bin/flubnf"), "app"],
                           capture_output=True, text=True, check=False,
                           env=_env(), timeout=60)
    assert plain.returncode == 69 and not Path(f"{rec}.args").exists()


@posix_only
@embeds
def test_a_launch_stopped_on_request_before_its_window_is_up_is_no_failure(tmp_path):
    """A second FluBNF.command moments after the first: the newer launch
    takes over (SIGTERM) before the first one's window is up. The host
    empties the first Terminal's status file, so that Terminal stands down
    instead of starting the console again and taking over the newer one in
    turn. A crash leaves the file saying the app quit early."""
    import signal
    repo, _, host = _built(tmp_path)
    script = repo / ".venv" / "bin" / "flubnf"
    status = tmp_path / "boot"
    early = "FluBNF.app quit before the console started\n"

    def run(body, stop):
        script.write_text(body)
        status.write_text(early)
        p = subprocess.Popen([str(host), str(script), "app"], stdout=subprocess.PIPE,
                             text=True, env=_env(FLUBNF_BOOT_STATUS=status))
        try:
            assert p.stdout.readline().strip() == "importing"
            if stop:
                p.send_signal(stop)
            return p.wait(timeout=60)
        finally:
            p.kill()
            p.stdout.close()

    waits = "import time\nprint('importing', flush=True)\ntime.sleep(60)\n"
    assert run(waits, signal.SIGTERM) == -signal.SIGTERM
    assert status.read_text() == ""
    crash = "import os\nprint('importing', flush=True)\nos.abort()\n"
    assert run(crash, None) == -signal.SIGABRT
    assert status.read_text() == early
    # a console run in view (no status file) is stopped as before
    script.write_text(waits)
    p = subprocess.Popen([str(host), str(script), "app"], stdout=subprocess.PIPE,
                         text=True, env=_env())
    try:
        assert p.stdout.readline().strip() == "importing"
        p.terminate()
        assert p.wait(timeout=60) == -signal.SIGTERM
    finally:
        p.kill()
        p.stdout.close()


@posix_only
@embeds
def test_the_takeover_and_reinstall_sh_recognise_a_hosted_window(tmp_path):
    """A real host process running `flubnf window`: the pidfile takeover
    reads its command line, matches and ends it, and reinstall.sh's pgrep
    pattern finds it."""
    repo, _, host = _built(tmp_path)
    script = repo / ".venv" / "bin" / "flubnf"
    script.write_text("import time\ntime.sleep(60)\n")
    p = subprocess.Popen([str(host), str(script), "window"], env=_env(),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        cmd = ""
        while not cmd and time.monotonic() < deadline:
            cmd = _pid_cmdline(p.pid)
            time.sleep(0.05)
        assert cmd.split()[:3] == [str(host), str(script), "window"], cmd
        assert _cmdline_has_marker(cmd, APP_ENTRY_MARKERS), cmd
        pattern = re.search(r"pgrep -U \"\$\(id -u\)\" -f '([^']+)'",
                            (REPO / "reinstall.sh").read_text()).group(1)
        if shutil.which("pgrep"):
            found = subprocess.run(["pgrep", "-f", pattern], capture_output=True,
                                   text=True).stdout.split()
            assert str(p.pid) in found, (pattern, cmd)
        pidfile = tmp_path / "app.pid"
        pidfile.write_text(str(p.pid))
        assert _terminate_predecessor(pidfile=pidfile, wait=5.0)
        p.wait(timeout=15)
    finally:
        if p.poll() is None:
            p.kill()
            p.wait(timeout=15)


@posix_only
@embeds
def test_the_host_is_rebuilt_when_the_venv_changes_or_it_stops_loading(tmp_path):
    repo, purelib, host = _built(tmp_path)
    assert _build(repo, "--check").returncode == 0
    stamp = (repo / ".venv" / ".app-host.stamp").read_text()
    (purelib / "newpkg").mkdir()                   # an install or a refresh
    assert _build(repo, "--check").returncode == 1
    assert _build(repo).returncode == 0
    assert (repo / ".venv" / ".app-host.stamp").read_text() != stamp
    # a host that no longer loads (a libpython removed, say): rebuilt, not run
    host.unlink()
    host.write_bytes(b"\0" * 64)
    host.chmod(0o755)
    assert _build(repo, "--check").returncode == 1
    assert _build(repo).returncode == 0
    assert _build(repo, "--check").returncode == 0


def _no_compiler_path(tmp_path: Path) -> Path:
    """A PATH with every tool the build uses except a C compiler."""
    nocc = tmp_path / "nocc"
    nocc.mkdir()
    for tool in ("bash", "basename", "cat", "chmod", "cp", "cut", "dirname", "grep", "head",
                 "ln", "ls", "mkdir", "mktemp", "mv", "rm", "sed", "sha1sum",
                 "shasum", "tail", "touch", "uname"):
        found = shutil.which(tool)
        if found:
            (nocc / tool).symlink_to(found)
    return nocc


@posix_only
@embeds
@pytest.mark.skipif(sys.platform == "darwin",
                    reason="a Mac asks xcode-select, not PATH, for its compiler")
def test_a_failed_rebuild_keeps_a_host_that_still_loads(tmp_path):
    """A package install moves the fingerprint; if the compiler is gone by
    then (a macOS upgrade, an Xcode licence), the host already built still
    runs this venv and stays in use, stamped so the doomed rebuild is not
    retried on every launch. A compiler coming back earns the rebuild."""
    repo, purelib, host = _built(tmp_path)
    before = host.read_bytes()
    (purelib / "newpkg").mkdir()
    nocc = _no_compiler_path(tmp_path)
    first = _build(repo, PATH=nocc)
    assert first.returncode == 0, first.stdout + first.stderr
    assert "no C compiler" in first.stdout and "keeps using it" in first.stdout
    stamp = repo / ".venv" / ".app-host.stamp"
    assert stamp.read_text().startswith("kept ")
    assert host.read_bytes() == before
    assert _build(repo, "--check", PATH=nocc).returncode == 0
    again = _build(repo, PATH=nocc)
    assert again.returncode == 0 and "keeps its earlier host" in again.stdout
    assert "tries again" in again.stdout
    fixed = _build(repo)
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    assert stamp.read_text().startswith("ok ")
    # without a host that loads, a failure is still a failure
    host.unlink()
    (purelib / "another").mkdir()
    gone = _build(repo, PATH=nocc)
    assert gone.returncode == 1 and stamp.read_text().startswith("fail ")


@posix_only
@embeds
def test_a_host_built_from_other_source_is_never_kept(tmp_path):
    """A host from older source may predate a fix in it (the direct reopen
    of Terminal that looped): when its rebuild fails it is not kept, and it
    can no longer run, so the console starts from Terminal until it is."""
    repo, _, host = _built(tmp_path)
    src = repo / "scripts" / "macos" / "flubnf_host.c"
    src.write_text(src.read_text() + "\n/* a newer host */\n")
    nocc = _no_compiler_path(tmp_path)
    r = _build(repo, PATH=nocc)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "keeps using it" not in r.stdout
    assert (repo / ".venv" / ".app-host.stamp").read_text().startswith("fail ")
    assert not os.access(host, os.X_OK)
    fixed = _build(repo)
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    assert os.access(host, os.X_OK)


@posix_only
@embeds
@pytest.mark.skipif(sys.platform == "darwin",
                    reason="a Mac asks xcode-select, not PATH, for its compiler")
def test_a_failed_build_waits_for_a_compiler_and_spares_tmp(tmp_path):
    """No compiler: the build fails once, is stamped, and is not retried on
    every launch; a compiler appearing earns the retry with no --force. The
    failure path never touches an exported $TMP."""
    repo, _ = _host_clone(tmp_path)
    nocc = _no_compiler_path(tmp_path)
    canary = tmp_path / "canary"
    canary.mkdir()
    (canary / "keep").write_text("mine\n")
    first = _build(repo, PATH=nocc, TMP=canary)
    assert first.returncode == 1 and "no C compiler" in first.stdout, first.stdout + first.stderr
    assert (canary / "keep").is_file()
    assert (repo / ".venv" / ".app-host.stamp").read_text().startswith("fail ")
    again = _build(repo, PATH=nocc)
    assert again.returncode == 1 and "tries again" in again.stdout
    assert _build(repo, "--check", PATH=nocc).returncode == 2
    fixed = _build(repo)
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    assert (repo / HOST_REL).is_file()


@posix_only
@embeds
def test_a_dock_launch_end_to_end_never_blocks_the_update(tmp_path):
    """The whole Dock path on a real clone: flubnf-launch runs FluBNF.command
    headless (which fast-forwards), builds the host, execs it, and the
    console runs as the venv's python with `window`. What it leaves behind
    (host, stamp, log) is all ignored, so the next fast-forward, which
    changes files inside FluBNF.app, goes through."""
    rec = tmp_path / "rec"
    rec.mkdir()
    opener = _opener(tmp_path, rec)
    alert = _script(tmp_path / "bin" / "osascript", f'echo alert > "{rec}/osascript"\n')
    tracked = {
        ".gitignore": (REPO / ".gitignore").read_text(),
        "FluBNF.command": COMMAND.read_text(),
        "pyproject.toml": "[project]\nname = 'x'\n",
        "FluBNF.app/Contents/Info.plist": PLIST.read_text(),
        "FluBNF.app/Contents/MacOS/flubnf-launch": _patched_launcher(opener, alert),
    }
    for f in ("flubnf_host.c", "build_app_host.sh", "host_boot.py"):
        tracked[f"scripts/macos/{f}"] = (MACOS / f).read_text()
    work = tmp_path / "work"
    for rel, text in tracked.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text)
    for rel in ("FluBNF.command", "FluBNF.app/Contents/MacOS/flubnf-launch",
                "scripts/macos/build_app_host.sh"):
        (work / rel).chmod(0o755)
    ident = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.invalid",
             "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.invalid"}

    def git(cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, env=_env(**ident), text=True,
                              capture_output=True, check=True).stdout.strip()

    git(work, "-c", "init.defaultBranch=main", "init", "-q", ".")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "v1")
    origin = tmp_path / "origin.git"
    git(tmp_path, "clone", "-q", "--bare", str(work), str(origin))
    git(work, "remote", "add", "origin", str(origin))
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(origin), str(clone))

    # the clone's own machine state, all of it untracked
    subprocess.run([_base_python(), "-m", "venv", "--without-pip", str(clone / ".venv")],
                   check=True)
    purelib = Path(subprocess.run(
        [str(clone / ".venv" / "bin" / "python"), "-c",
         "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        capture_output=True, text=True, check=True).stdout.strip())
    for pkg in ("flubnf", "webview"):
        (purelib / pkg).mkdir(parents=True, exist_ok=True)
        (purelib / pkg / "__init__.py").write_text("")
    console = clone / ".venv" / "bin" / "flubnf"
    console.write_text(
        "import json, os, sys\n"
        f"with open({str(rec / 'console.json')!r}, 'a') as f:\n"
        "    f.write(json.dumps([sys.argv[1:], sys.prefix, sys.executable,\n"
        "                        os.environ.get('FLUBNF_HOST_FALLBACK')]) + '\\n')\n")
    console.chmod(0o755)
    shutil.copy(clone / "pyproject.toml", clone / ".venv" / ".pyproject.stamp")
    (clone / ".flubnf.env").write_text(f'export FLUBNF_PY_ENGINE="{shutil.which("true")}"\n')

    def origin_moves(n):
        """A commit that edits files inside the bundle, the ones a build
        product would sit beside."""
        plist = work / "FluBNF.app/Contents/Info.plist"
        plist.write_text(plist.read_text().replace("</dict></plist>",
                                                   f"<!-- v{n} --></dict></plist>"))
        with open(work / "FluBNF.app/Contents/MacOS/flubnf-launch", "a") as f:
            f.write(f"# v{n}\n")
        git(work, "commit", "-qam", f"v{n}")
        git(work, "push", "-q", "origin", "main")
        return git(work, "rev-parse", "HEAD")

    for n in (2, 3):
        head = origin_moves(n)
        r = subprocess.run(["bash", str(clone / "FluBNF.app/Contents/MacOS/flubnf-launch")],
                           env=_env(FLUBNF_HOST_ANY_OS=1, HOME=tmp_path),
                           stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=300)
        log = (clone / "app/state/logs/launch.log").read_text()
        assert r.returncode == 0, log + r.stdout + r.stderr
        assert _read(rec, "open") is None and _read(rec, "osascript") is None, log
        assert git(clone, "rev-parse", "HEAD") == head, log
        assert "up to date with origin" in log
        assert (clone / HOST_REL).is_file()
        assert git(clone, "status", "--porcelain", "--untracked-files=all") == ""
        runs = [json.loads(line) for line in (rec / "console.json").read_text().splitlines()]
        assert len(runs) == n - 1
        args, prefix, exe, flag = runs[-1]
        assert args == ["window"] and flag is None
        assert Path(prefix).resolve() == (clone / ".venv").resolve()
        assert exe.endswith("/.venv/bin/python")
