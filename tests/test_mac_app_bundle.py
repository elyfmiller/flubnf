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


def _read(rec: Path, name: str):
    """A stand-in's recorded lines, or None when it never ran."""
    p = rec / name
    return p.read_text().splitlines() if p.is_file() else None


def _opener(tmp_path: Path, rec: Path) -> Path:
    """A stand-in for /usr/bin/open that records its call and, like open,
    fails when the file to open is not there."""
    return _script(tmp_path / "bin" / "open",
                   f'printf "%s\\n" "$@" > "{rec}/open"\n[ -e "${{@: -1}}" ]\n')


def _patched_launcher(opener: Path, osascript: Path, limit=None) -> str:
    """flubnf-launch with Terminal and the alert swapped for recorders."""
    src = LAUNCH.read_text()
    swaps = [("local open=/usr/bin/open", f"local open={opener}"),
             ("local osascript=/usr/bin/osascript", f"local osascript={osascript}")]
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
                 build="exit 0", host=True, limit=None):
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
    launcher.write_text(_patched_launcher(opener, alert, limit))
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


def _launch(repo: Path, **env):
    t0 = time.monotonic()
    r = subprocess.run(["bash", str(repo / "FluBNF.app/Contents/MacOS/flubnf-launch")],
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
    its console a stand-in that records each run."""
    repo = tmp_path / "clone"
    rec = tmp_path / "rec"
    rec.mkdir(parents=True)
    repo.mkdir()
    shutil.copy(COMMAND, repo / "FluBNF.command")
    (repo / "pyproject.toml").write_text("[project]\n")
    if venv:
        _script(repo / ".venv" / "bin" / "flubnf",
                f'echo "direct $*" >> "{rec}/console"\nexit 0\n')
        if stamp:
            shutil.copy(repo / "pyproject.toml", repo / ".venv" / ".pyproject.stamp")
    if engine:
        (repo / ".flubnf.env").write_text(
            f'export FLUBNF_PY_ENGINE="{shutil.which("true")}"\n')
    return repo, rec


def _as_os(tmp_path, repo, rec, name="Darwin", *, build="exit 0", host_rc=0) -> str:
    """PATH under which `uname -s` says `name`, with a host and a build
    stand-in in the clone."""
    _script(tmp_path / "osbin" / "uname", f"echo {name}\n")
    _script(repo / "scripts" / "macos" / "build_app_host.sh",
            f'echo built >> "{rec}/build"\n{build}\n')
    _script(repo / HOST_REL, f'echo "host $*" >> "{rec}/console"\nexit {host_rc}\n')
    return str(tmp_path / "osbin") + os.pathsep + os.environ["PATH"]


def _command(repo: Path, **env) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(repo / "FluBNF.command")],
                          env=_env(HOME=repo.parent, **env),
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
@pytest.mark.parametrize("host_rc, again", [
    (0, False), (130, False), (137, False), (143, False),   # quit, Ctrl-C, takeovers
    (1, True), (139, True)])                                # a start that failed
def test_the_terminal_launch_runs_the_console_under_the_host(tmp_path, host_rc, again):
    """From Terminal too the window is FluBNF.app's once the host exists, so
    Keep in Dock after a first run pins FluBNF.app. A start that fails under
    the host gets one run without it, as the console ran before."""
    repo, rec = _command_repo(tmp_path)
    path = _as_os(tmp_path, repo, rec, host_rc=host_rc)
    r = _command(repo, PATH=path)
    runs = _read(rec, "console")
    assert runs[0] == f"host {repo}/.venv/bin/flubnf app", r.stdout + r.stderr
    assert runs[1:] == (["direct app"] if again else [])
    assert r.returncode == (0 if again else host_rc)
    assert _read(rec, "build") == ["built"]


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
    assert _read(rec, "build") == (["built"] if name == "Darwin" else None)


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
    boot = _boot()
    monkeypatch.setattr(boot.sys, "platform", "darwin")
    calls = []
    boot.to_terminal("why", run=lambda args, **kw: calls.append(args))
    assert len(calls) == 1 and calls[0][:3] == ["/usr/bin/open", "-a", "Terminal"]
    assert os.path.samefile(calls[0][3], REPO / "FluBNF.command")

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
    and only for a failure. FluBNF.command never sets the flag, so a
    Terminal launch cannot loop back to Terminal; no child sees it."""
    repo, _, host = _built(tmp_path)
    script = repo / ".venv" / "bin" / "flubnf"
    script.write_text("import sys\nsys.exit(3)\n")
    dock = subprocess.run([str(host), str(script), "window"], capture_output=True,
                          text=True, env=_env(FLUBNF_HOST_FALLBACK=1), timeout=60)
    assert dock.returncode == 3
    assert "reopening FluBNF.command in Terminal" in dock.stderr
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
    for tool in ("bash", "basename", "cat", "cp", "cut", "dirname", "grep", "head",
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
