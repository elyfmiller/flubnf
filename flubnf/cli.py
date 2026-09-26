"""FluBNF command-line interface (`flubnf`).

In file order: the help panels and root options, the doctor and knobs
commands, the console launch plumbing (takeover, ports, window watchdog),
then app, window and retro and the groundhog/bank/oracle/site/dataset
sub-apps. Most commands wrap a module function, imported inside the command
so that `flubnf app` opens its window without loading pandas or scipy
(test_cli_import_stays_light).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, List, Optional

import typer
from rich.console import Console
from rich.table import Table
from typer.core import TyperGroup

#: `flubnf --help` panels and their top-level commands, in display order;
#: every top-level command must be listed (the group refuses to build
#: otherwise, so a new command cannot silently land in the wrong panel).
HELP_PANELS = {
    "Console": ("app", "window", "doctor", "knobs", "dataset"),
    "Replay & verification": ("retro", "groundhog", "oracle", "site"),
    "Donor banks": ("bank",),
}


OTHER_PANEL = "Other"


class _PanelledGroup(TyperGroup):
    """The root group: files each command under its HELP_PANELS panel and
    lists them panel by panel (help order only; dispatch is by name)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, cmd in self.commands.items():
            panel = next(
                (p for p, names in HELP_PANELS.items() if name in names), None)
            # never refuse to build: `flubnf app` is what the launchers run.
            # tests/test_cli_panels.py fails when a command is unlisted.
            cmd.rich_help_panel = panel or OTHER_PANEL

    def list_commands(self, ctx):
        panels = list(HELP_PANELS) + [OTHER_PANEL]

        def rank(name):
            panel = self.commands[name].rich_help_panel
            names = HELP_PANELS.get(panel, ())
            return panels.index(panel), (names.index(name) if name in names
                                         else len(names))
        return sorted(super().list_commands(ctx), key=rank)


app = typer.Typer(
    cls=_PanelledGroup,
    add_completion=False,
    help="FluBNF: open the forecasting console, replay and verify seasons, "
         "and manage the committed donor banks.",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def _root(verbose: bool = typer.Option(False, "--verbose", "-v")):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _trace(msg: str) -> None:
    """Startup trace: a timestamped line to stderr and to the file named by
    FLUBNF_STARTUP_TRACE. A no-op when that is unset, except under a Dock
    launch (FLUBNF_HOST_FALLBACK, set by flubnf-launch), whose stderr is
    app/state/logs/launch.log: there the trace is the only record of what
    macOS answered. The launch has four actors (this process, uvicorn, the
    warm thread, WKWebView) and their ordering is the diagnosis."""
    import os
    import sys as _sys
    import time as _time
    path = os.environ.get("FLUBNF_STARTUP_TRACE")
    if not path and not os.environ.get("FLUBNF_HOST_FALLBACK"):
        return
    t = _time.time()
    line = (f"{t:.3f} {_time.strftime('%H:%M:%S', _time.localtime(t))}"
            f".{int(t * 1000) % 1000:03d} [pid {os.getpid()} cli] {msg}")
    if path:
        try:
            with open(path, "a") as fh:
                fh.write(line + "\n")
        except Exception:
            pass
    print(line, file=_sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# doctor and knobs
# ---------------------------------------------------------------------------
@app.command()
def doctor(
    online: bool = typer.Option(
        False, "--online",
        help="Include network checks (Delphi Epidata and GitHub).",
    ),
    # Accepted and ignored: the checks read no config, workspace or Mac
    # Studio flag (the legacy workspace CLI that used them is gone), and old
    # scripts pass them.
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", hidden=True),
    workspace: Optional[str] = typer.Option(
        None, "--workspace", "-w", hidden=True),
    pre_studio: bool = typer.Option(False, "--pre-studio", hidden=True),
):
    """Diagnose the environment and dependencies.

    Catches the common showstoppers (broken venv, missing engine or hub
    clone, missing BNG2.pl, NumPy 2.0 / pybnf incompat patch missing)
    before they bite mid-run. Exits 1 when any check fails.
    """
    from . import doctor as docmod
    if config is not None or workspace is not None or pre_studio:
        console.print("[dim]--config, --workspace and --pre-studio are "
                      "ignored: the doctor reads no config.[/dim]")
    rep = docmod.run_doctor(online=online)

    table = Table(title="FluBNF doctor")
    table.add_column("status"); table.add_column("check"); table.add_column("detail")
    color = {
        docmod.Status.OK: "green",
        docmod.Status.WARN: "yellow",
        docmod.Status.FAIL: "red",
    }
    for c in rep.checks:
        table.add_row(
            f"[{color[c.status]}]{c.status.value}[/]",
            c.name, c.detail,
        )
    console.print(table)

    # Surface hints below the table for any WARN/FAIL.
    hints = [c for c in rep.checks if c.hint and c.status is not docmod.Status.OK]
    if hints:
        console.print("\n[bold]hints[/]")
        for c in hints:
            console.print(f"  • [{color[c.status]}]{c.name}[/]: {c.hint}")

    console.print(
        f"\n[bold]summary:[/] "
        f"{len(rep.checks) - rep.n_fail - rep.n_warn} ok, "
        f"[yellow]{rep.n_warn} warn[/], "
        f"[red]{rep.n_fail} fail[/]"
    )
    if rep.n_fail:
        raise typer.Exit(code=1)


@app.command()
def knobs(
    as_json: bool = typer.Option(False, "--json",
                                 help="Print the registry as JSON."),
):
    """List the model knobs: shipped value, allowed range, the models each
    affects and its class (run or method), then the locked settings.

    Any value other than the shipped one marks a run as modified."""
    import json

    from app.core import knobs as K
    if as_json:
        locked = [{"key": l.key, "value": l.value, "source": l.source,
                   "why": l.why} for l in K.LOCKED]
        typer.echo(json.dumps({"knobs": K.describe(), "locked": locked},
                              indent=1, default=list))
        return
    names = {"pf": "Oracle SIHRS", "analogue": "Groundhog"}
    table = Table(title="Model knobs")
    table.add_column("knob", no_wrap=True)
    for col in ("shipped", "range", "affects", "class"):
        table.add_column(col)
    for r in K.describe():
        d = r["default"]
        shown = (f"[{', '.join(f'{x:g}' for x in d)}]" if isinstance(d, list)
                 else f"{d:,}" if r["kind"] == "int"
                 else ("on" if d else "off") if isinstance(d, bool) else str(d))
        table.add_row(r["key"], shown + (f" {r['unit']}" if r["unit"] else ""),
                      r["range"], ", ".join(names[m] for m in r["affects"]),
                      r["class"])
    console.print(table)
    locked = Table(title="Locked")
    for col in ("setting", "value", "why"):
        locked.add_column(col)
    for l in K.LOCKED:
        locked.add_row(l.key, str(l.value), l.why)
    console.print(locked)


# ---------------------------------------------------------------------------
# Console launch
# ---------------------------------------------------------------------------
# Survival guards, so a relaunch never binds its window to a dying
# predecessor's server: pidfile takeover of the predecessor, a nearby free
# port when the preferred one stays bound, and a load watchdog that reloads a
# page that never arrived instead of showing it dead.

APP_PID_FILE = (Path(__file__).resolve().parents[1]
                / "app" / "state" / "app.pid")
# Entry shapes a takeover target's command line must contain (word match, see
# _cmdline_has_marker). Command-shaped on purpose: a bare "flubnf" matches any
# venv process, e.g. a recycled pid now running a PyBNF fit. The .exe forms are
# the Windows spellings (FluBNF.bat, pip's console-script launcher).
APP_ENTRY_MARKERS = ("flubnf app", "flubnf window",
                     "flubnf.exe app", "flubnf.exe window")


#: the root command's options (see _root): the only words that may come
#: between the program and its subcommand in a console command line
_ROOT_SWITCHES = frozenset({"-v", "--verbose"})


def _cmdline_has_marker(cmd: str, markers) -> bool:
    """Whether a process command line is one of our entry points.

    Word match, not substring: quotes stripped, split on whitespace; a
    marker's first word is compared by file name (after the last / or \\),
    the rest exactly. pip's Windows launcher puts a quote between exe and
    subcommand ('"...\\flubnf.exe" app'), which a substring test never
    matched; words also reject 'grep flubnf app.log' and 'notflubnf app'."""
    if not cmd:
        return False
    import os
    fold = os.name == "nt"           # NTFS file names ignore case
    words = cmd.replace('"', " ").split()
    for mk in markers:
        want = str(mk).split()
        if not want:
            continue
        first = want[0].casefold() if fold else want[0]
        for i, word in enumerate(words):
            head = word.replace("\\", "/").rsplit("/", 1)[-1]
            if (head.casefold() if fold else head) != first:
                continue
            j = i + 1
            if len(want) > 1:
                # only the root's value-less switches may sit between program
                # and subcommand; skipping any '-' word would let
                # `grep flubnf -r app` pass for the console
                while j < len(words) and words[j] in _ROOT_SWITCHES:
                    j += 1
            if words[j:j + len(want) - 1] == want[1:]:
                return True
    return False


def _posix_parent_pid(pid: int):
    """The parent of `pid` on Linux (/proc) or macOS (ps), or None."""
    import subprocess
    try:
        stat = Path(f"/proc/{int(pid)}/stat")
        if stat.exists():
            # comm is parenthesised and may hold spaces; then state, ppid
            return int(stat.read_text().rsplit(")", 1)[1].split()[1])
    except Exception:
        pass
    try:
        out = subprocess.run(["ps", "-o", "ppid=", "-p", str(int(pid))],
                             capture_output=True, text=True, timeout=5)
        return int(out.stdout.strip()) if out.returncode == 0 else None
    except Exception:
        return None


def _windows_parent_map(kernel32=None) -> dict:
    """pid -> parent pid for every process, from one Toolhelp snapshot
    (CreateToolhelp32Snapshot / Process32FirstW / Process32NextW). {} when
    the snapshot cannot be taken. Never raises. `kernel32` is injectable
    for tests on other platforms."""
    try:
        import ctypes
        from ctypes import wintypes

        class _Entry(ctypes.Structure):          # PROCESSENTRY32W
            _fields_ = [("dwSize", wintypes.DWORD),
                        ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t),
                        ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", wintypes.DWORD),
                        ("szExeFile", ctypes.c_wchar * 260)]

        if kernel32 is None:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
            kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD,
                                                          wintypes.DWORD)
            for fn in (kernel32.Process32FirstW, kernel32.Process32NextW):
                fn.restype = wintypes.BOOL
                fn.argtypes = (wintypes.HANDLE, ctypes.POINTER(_Entry))
            kernel32.CloseHandle.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        TH32CS_SNAPPROCESS = 0x2
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snap or snap == INVALID_HANDLE_VALUE:
            return {}
        try:
            entry = _Entry()
            entry.dwSize = ctypes.sizeof(_Entry)
            out = {}
            ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
            while ok and len(out) < 1_000_000:
                out[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
            return out
        finally:
            kernel32.CloseHandle(snap)
    except Exception:
        return {}


def _ancestor_pids(start=None, parent_of=None, limit: int = 32) -> set:
    """Ancestor pids of `start` (default: this process), nearest first,
    until the chain ends, loops, or `limit` is reached.

    The takeover never signals these: on Windows the launcher and redirector
    in the chain carry the server's entry shape, and a stale app.pid reused
    for one of them would take the new console down (kill-on-close job).
    Never raises; an unreadable parent ends the walk (os.getppid() is always
    included for this process)."""
    import os
    me = os.getpid()
    start = me if start is None else int(start)
    if parent_of is None:
        parent_of = (_windows_parent_map().get if os.name == "nt"
                     else _posix_parent_pid)
    out = set()
    cur = start
    for _ in range(max(0, int(limit))):
        try:
            ppid = parent_of(cur)
        except Exception:
            ppid = None
        if not ppid or int(ppid) <= 0 or int(ppid) == start or ppid in out:
            break
        out.add(int(ppid))
        cur = int(ppid)
    if start == me:
        try:
            if os.getppid() > 0:
                out.add(os.getppid())
        except Exception:
            pass
    return out

# Orphaned PF runner groups to sweep on takeover: runners are Popen children
# in their own process groups, so killing the server leaves them fitting.
# MUST match app/core/engines/pf.py RUNNER_PIDS_FILE.
PF_RUNNER_PIDS_FILE = APP_PID_FILE.parent / "pf_runners.json"

# Shown by the load watchdog when every reload fails. Loaded via load_html:
# pywebview 6.2.1 misroutes data: URLs as file paths.
_SERVER_FAIL_PAGE = """<!doctype html><html><head><title>FluBNF</title></head>
<body style="font-family:-apple-system,Helvetica,sans-serif;background:#101223;
color:#E9EAF4;padding:2.5rem;max-width:34rem">
<h2>The console server did not start</h2>
<p>The FluBNF window opened, but the local server behind it never answered.
Close this window and relaunch FluBNF. If it happens again, start it from
Terminal (<code>.venv/bin/flubnf app</code>) to see the error output.</p>
</body></html>"""


def _pid_cmdline_windows_native(pid: int, ntdll=None,
                                kernel32=None) -> str:
    """Windows: command line via NtQueryInformationProcess (class 60), in
    process, needing only PROCESS_QUERY_LIMITED_INFORMATION. Preferred over
    WMI, whose cold PowerShell can exceed the 10 s timeout (no wmic on Server
    2025). Decoded as UTF-16-LE by byte length (not wstring_at, whose wchar_t
    is 4 bytes off Windows) so stubbed tests read what Windows would. Answers
    only for a STILL_ACTIVE process. Never raises; '' means "could not
    inspect". `ntdll`/`kernel32` injectable for tests."""
    try:
        import ctypes
        from ctypes import wintypes
        if kernel32 is None:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL,
                                             wintypes.DWORD)
            kernel32.CloseHandle.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel32.GetExitCodeProcess.restype = wintypes.BOOL
            kernel32.GetExitCodeProcess.argtypes = (
                wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        if ntdll is None:
            ntdll = ctypes.WinDLL("ntdll")
            ntdll.NtQueryInformationProcess.restype = ctypes.c_long
            ntdll.NtQueryInformationProcess.argtypes = (
                wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                wintypes.ULONG, ctypes.POINTER(wintypes.ULONG))

        class _UnicodeString(ctypes.Structure):
            _fields_ = [("Length", ctypes.c_ushort),
                        ("MaximumLength", ctypes.c_ushort),
                        ("Buffer", ctypes.c_void_p)]

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        PROCESS_COMMAND_LINE_INFORMATION = 60
        STILL_ACTIVE = 259
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,
                                      False, int(pid))
        if not handle:
            return ""
        try:
            code = wintypes.DWORD(0)
            if not (kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
                    and code.value == STILL_ACTIVE):
                return ""                    # exited, or cannot tell
            need = wintypes.ULONG(0)
            # sizing call: fails with STATUS_INFO_LENGTH_MISMATCH, sets need
            ntdll.NtQueryInformationProcess(
                handle, PROCESS_COMMAND_LINE_INFORMATION, None, 0,
                ctypes.byref(need))
            size = int(need.value)
            if size < ctypes.sizeof(_UnicodeString) or size > (1 << 20):
                return ""
            buf = ctypes.create_string_buffer(size)
            status = ntdll.NtQueryInformationProcess(
                handle, PROCESS_COMMAND_LINE_INFORMATION, buf, size,
                ctypes.byref(need))
            if status != 0:
                return ""
            ustr = _UnicodeString.from_buffer(buf)
            if not ustr.Buffer or not ustr.Length:
                return ""
            base = ctypes.addressof(buf)
            if not (base <= ustr.Buffer
                    and ustr.Buffer + ustr.Length <= base + size):
                return ""                    # never read outside our buffer
            raw = ctypes.string_at(ustr.Buffer, ustr.Length)
            return raw.decode("utf-16-le", errors="replace").strip()
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""


def _pid_cmdline_windows(pid: int) -> str:
    """Windows: the command line, natively first, then via WMI (wmic where
    present, else PowerShell CIM). '' fails safe: the takeover signals only
    a marker match, so the relaunch falls back to a free port. A dead pid
    skips WMI (each PowerShell start can take seconds)."""
    import subprocess
    native = _pid_cmdline_windows_native(pid)
    if native:
        return native
    if not _pid_alive_windows(pid):
        return ""
    queries = (
        ["wmic", "process", "where", f"ProcessId={int(pid)}",
         "get", "CommandLine", "/format:list"],
        ["powershell", "-NoProfile", "-Command",
         f"(Get-CimInstance Win32_Process -Filter "
         f"'ProcessId={int(pid)}').CommandLine"],
    )
    for q in queries:
        try:
            out = subprocess.run(q, capture_output=True, text=True,
                                 timeout=10)
        except Exception:
            continue
        if out.returncode != 0:
            continue
        text = out.stdout.strip()
        if text.startswith("CommandLine="):     # wmic /format:list shape
            text = text.split("=", 1)[1]
        text = text.strip()
        if text:
            return text
    return ""


def _pid_cmdline(pid: int) -> str:
    """The command line of a live process, or '' if absent/uninspectable.
    Linux: /proc/<pid>/cmdline (immune to ps formatting and <defunct>
    rewriting); Windows: _pid_cmdline_windows; else ps. No psutil."""
    import os
    import subprocess
    if os.name == "nt":
        return _pid_cmdline_windows(pid)
    proc_path = Path(f"/proc/{int(pid)}/cmdline")
    try:
        if proc_path.exists():
            raw = proc_path.read_bytes()
            return raw.replace(b"\0", b" ").decode(errors="replace").strip()
    except Exception:
        pass
    try:
        out = subprocess.run(["ps", "-p", str(int(pid)), "-o", "command="],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def _pid_alive_windows(pid: int, kernel32=None) -> bool:
    """Windows liveness via OpenProcess + GetExitCodeProcess: os.kill(pid, 0)
    on Windows calls TerminateProcess, so the POSIX probe would KILL it.
    `kernel32` injectable for tests."""
    try:
        import ctypes
        import ctypes.wintypes as wintypes
        if kernel32 is None:
            kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        ERROR_ACCESS_DENIED = 5
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            # access denied: alive but someone else's (empty cmdline, so
            # the takeover leaves it alone)
            return kernel32.GetLastError() == ERROR_ACCESS_DENIED
        try:
            code = wintypes.DWORD()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return False


def _pid_alive(pid: int) -> bool:
    """Signal-0 liveness: true for running OR zombie, so callers pair it with
    the cmdline check. Windows uses _pid_alive_windows (see there)."""
    import os
    if os.name == "nt":
        return _pid_alive_windows(pid)
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _sweep_runner_groups(registry: Optional[Path] = None,
                         wait: float = 5.0) -> int:
    """Terminate every PF runner process GROUP in the registry (the
    predecessor's orphans), then clear it. A pid whose live command line no
    longer names its recorded runner script is left alone (recycled pid).
    POSIX: SIGTERM the group, SIGKILL survivors after `wait`; Windows:
    taskkill /T /F. Never raises; returns how many groups were signalled."""
    import json
    import os
    import signal
    import subprocess
    import time
    registry = registry if registry is not None else PF_RUNNER_PIDS_FILE
    swept = 0
    try:
        entries = json.loads(Path(registry).read_text())
        if not isinstance(entries, dict):
            entries = {}
    except Exception:
        entries = {}
    targets = []
    for pid_s, meta in entries.items():
        try:
            pid = int(pid_s)
        except (TypeError, ValueError):
            continue
        runner = str((meta or {}).get("runner") or "")
        marker = os.path.basename(runner) if runner else ""
        cmd = _pid_cmdline(pid)
        if not cmd or not marker or marker not in cmd:
            continue          # dead, or not the process that was recorded
        try:
            pgid = int((meta or {}).get("pgid") or pid)
        except (TypeError, ValueError):
            pgid = pid
        targets.append((pid, pgid))
    for pid, pgid in targets:
        try:
            if os.name == "posix":
                os.killpg(pgid, signal.SIGTERM)
            else:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, timeout=15)
            swept += 1
        except Exception:
            continue
    if targets and os.name == "posix":
        # the cmdline pairing skips unreaped zombies, same as the takeover
        t0 = time.time()
        while (time.time() - t0 < wait
               and any(_pid_alive(p) and _pid_cmdline(p)
                       for p, _ in targets)):
            time.sleep(0.1)
        for pid, pgid in targets:
            if _pid_alive(pid) and _pid_cmdline(pid):
                try:
                    os.killpg(pgid, getattr(signal, "SIGKILL",
                                            signal.SIGTERM))
                except Exception:
                    pass
    try:
        Path(registry).unlink(missing_ok=True)
    except Exception:
        pass
    return swept


def _terminate_predecessor(pidfile: Optional[Path] = None,
                           markers: tuple = APP_ENTRY_MARKERS,
                           wait: float = 5.0,
                           runner_pids: Optional[Path] = None) -> bool:
    """Single-instance takeover: if the pidfile names a live process with our
    entry point, SIGTERM it (SIGKILL after `wait`) so the relaunch owns the
    port. The stale pidfile is removed either way. PF runner groups are
    swept AFTER the server dies (so it cannot dispatch replacements), and
    even with no pidfile (a window close skips the finally blocks). Never
    raises; True when a predecessor was signalled.

    An explicit `pidfile` with no `runner_pids` sweeps nothing, so a test
    probing a private pidfile never reclaims the real console's fits."""
    import os
    import signal
    import time
    if pidfile is None:
        pidfile = APP_PID_FILE
        if runner_pids is None:
            runner_pids = PF_RUNNER_PIDS_FILE
    signalled = False
    try:
        if pidfile.is_file():
            pid = int(pidfile.read_text().strip())
            if pid != os.getpid():
                cmd = _pid_cmdline(pid)
                if (_cmdline_has_marker(cmd, markers)
                        and pid not in _ancestor_pids()):
                    try:
                        os.kill(pid, signal.SIGTERM)
                        signalled = True
                        t0 = time.time()
                        while (time.time() - t0 < wait and _pid_alive(pid)
                               and _pid_cmdline(pid)):
                            time.sleep(0.1)
                        if _pid_alive(pid) and _pid_cmdline(pid):
                            # no SIGKILL on Windows, where SIGTERM is
                            # already TerminateProcess
                            os.kill(pid, getattr(signal, "SIGKILL",
                                                 signal.SIGTERM))
                    except (ProcessLookupError, PermissionError):
                        pass
    except Exception:
        pass
    try:
        pidfile.unlink(missing_ok=True)
    except Exception:
        pass
    if runner_pids is not None:
        _sweep_runner_groups(runner_pids, wait=wait)
    return signalled


def _write_pidfile(pidfile: Optional[Path] = None):
    """Record this process for the next launch's takeover; atexit removes
    the pidfile if this process still owns it. Returns that cleanup (for
    tests). Never raises."""
    import atexit
    import os
    pidfile = pidfile if pidfile is not None else APP_PID_FILE
    me = str(os.getpid())

    def _cleanup():
        try:
            if pidfile.is_file() and pidfile.read_text().strip() == me:
                pidfile.unlink()
        except Exception:
            pass

    try:
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        pidfile.write_text(me)
        atexit.register(_cleanup)
    except Exception:
        pass
    return _cleanup


_MAX_PORT = 65535


def _port_candidates(preferred: int, tries: int) -> range:
    """Ports preferred..preferred+tries-1, CLAMPED at 65535; empty if
    `preferred` is out of range. bind() raises OverflowError (not OSError)
    above 65535, which would escape the callers' `except OSError` fallback
    (macOS ephemeral ports, as the tests use, reach 65535). A negative
    preferred is not slid to 0: 0 means a random ephemeral port."""
    if not 0 <= preferred <= _MAX_PORT:
        return range(0)
    return range(preferred, min(preferred + max(1, tries), _MAX_PORT + 1))


def _set_port_reuse(s) -> None:
    """Make a probe/bind mean 'a TIME_WAIT ghost passes, a live listener
    fails': SO_REUSEADDR on POSIX (as uvicorn binds); SO_EXCLUSIVEADDRUSE on
    Windows, where SO_REUSEADDR lets a socket steal a LISTENING port."""
    import socket
    import sys
    if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


def _pick_port(preferred: int = 8710, tries: int = 10) -> int:
    """The first bindable port in _port_candidates, probed as uvicorn will
    bind (_set_port_reuse). If all are busy, `preferred`, so uvicorn
    reports the real conflict."""
    import socket
    for port in _port_candidates(preferred, tries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                _set_port_reuse(s)
                s.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
    return preferred


def _bind_app_socket(preferred: int = 8710, tries: int = 10):
    """(listening socket, port) for the window path, bound and LISTENING
    before the window opens, then handed to uvicorn (sockets=...). Holding
    it removes the probe-then-bind race, and WKWebView's first request waits
    in the backlog instead of being refused (the dead-first-window bug).
    (None, preferred) when all are busy so uvicorn reports the conflict."""
    import socket
    for port in _port_candidates(preferred, tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            _set_port_reuse(s)
            s.bind(("127.0.0.1", port))
            s.listen(128)
            # the kernel's port: preferred=0 (tests) reports what was bound
            return s, s.getsockname()[1]
        except OSError:
            s.close()
            continue
    return None, preferred


def _server_answering(url: str, timeout: float = 1.0) -> bool:
    """True when the server behind `url` answers HTTP with any status. The
    watchdog reloads only then (server up, window showing a dead page)."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/versions",
                                    timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


#: Seconds after show to ask macOS to activate the window. macOS 14+ may
#: decline a Terminal-launched process (clicks then ignored until the user
#: switches apps), so retry until active with a key window.
ACTIVATE_DELAYS = (0.0, 0.3, 1.0, 2.0, 4.0, 8.0)

#: Then watch (total, step) seconds, trace-only, for when activation lands.
ACTIVATE_WATCH = (120.0, 2.0)


def _activate_once(appkit) -> tuple:
    """One activation attempt on the Cocoa main thread. Returns (active,
    key). Each call is tried on its own: activate (macOS 14),
    activateIgnoringOtherApps_ (deprecated, often ignored), the
    running-application form, and ordering visible windows front and key
    (pywebview does that only once, before its run loop)."""
    app = appkit.NSApplication.sharedApplication()
    try:
        app.setActivationPolicy_(appkit.NSApplicationActivationPolicyRegular)
    except Exception:
        pass
    try:
        if app.respondsToSelector_("activate"):
            app.activate()
    except Exception:
        pass
    try:
        app.activateIgnoringOtherApps_(True)
    except Exception:
        pass
    try:
        appkit.NSRunningApplication.currentApplication().activateWithOptions_(
            appkit.NSApplicationActivateAllWindows
            | getattr(appkit, "NSApplicationActivateIgnoringOtherApps", 0))
    except Exception:
        pass
    # macOS 14+: ask on behalf of the focused app (the launching Terminal),
    # the form cooperative activation is designed around
    try:
        me = appkit.NSRunningApplication.currentApplication()
        front = appkit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if (front is not None and me.respondsToSelector_(
                "activateFromApplication:options:")):
            me.activateFromApplication_options_(
                front, appkit.NSApplicationActivateAllWindows)
    except Exception:
        pass
    for w in (app.windows() or []):
        try:
            if w.isVisible():
                w.makeKeyAndOrderFront_(None)
                w.orderFrontRegardless()
        except Exception:
            pass
    return bool(app.isActive()), app.keyWindow() is not None


#: the window's title, and the app menu's name (About, Hide, Quit)
APP_NAME = "FluBNF"


def _name_mac_process(name: str = APP_NAME) -> bool:
    """Name the app menu's items for a window started outside FluBNF.app.

    This does not rename the Dock icon, and cannot. The Dock and Keep in
    Dock follow the app bundle that holds the running program: Python.app
    for a framework Python, a bare python3.x otherwise. Only FluBNF.app's
    host (scripts/macos/flubnf_host.c) makes the window FluBNF in the Dock.

    What this does do: pywebview builds "About/Hide/Quit <CFBundleName>"
    from this same in-memory dictionary (webview/platforms/cocoa.py), so a
    window run without the host reads "Quit FluBNF", not "Quit Python".
    Under the host the bundle already says FluBNF. Returns True when the
    dictionary took the name; never raises."""
    import sys
    if sys.platform != "darwin":
        return False
    try:
        from Foundation import NSBundle, NSProcessInfo
        ok = False
        bundle = NSBundle.mainBundle()
        for info in (bundle.localizedInfoDictionary(), bundle.infoDictionary()):
            if info is not None:
                info["CFBundleName"] = name
                ok = True
        NSProcessInfo.processInfo().setProcessName_(name)
        return ok
    except Exception:
        return False


#: page zoom steps, as browsers offer them (1.0 = 100%)
ZOOM_STEPS = (0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0,
              2.5, 3.0)


def _zoom_step(current: float, step: int) -> float:
    """The next zoom level from `current`: step +1 / -1 moves one notch
    (clamped to ZOOM_STEPS), 0 resets to 100%."""
    if step == 0:
        return 1.0
    if step > 0:
        return next((z for z in ZOOM_STEPS if z > current + 1e-6),
                    ZOOM_STEPS[-1])
    return next((z for z in reversed(ZOOM_STEPS) if z < current - 1e-6),
                ZOOM_STEPS[0])


class _WindowApi:
    """Exposed to the page as window.pywebview.api: whole-page zoom for the
    native macOS window (WKWebView has no zoom menu of its own). The page
    calls zoom(+1 | -1 | 0) from Cmd+= / Cmd+- / Cmd+0 and the Display
    menu, and set_zoom(level) to restore the stored level on load."""

    def __init__(self):
        self._window = None
        self._level = 1.0

    def _apply(self, level: float) -> float:
        import sys
        level = min(ZOOM_STEPS[-1], max(ZOOM_STEPS[0], float(level)))
        if sys.platform != "darwin" or self._window is None:
            return self._level
        try:
            from PyObjCTools import AppHelper
            from webview.platforms.cocoa import BrowserView
            view = BrowserView.instances[self._window.uid].webview

            def _set():
                try:
                    view.setPageZoom_(level)            # macOS 11+
                except Exception:
                    try:
                        view.setMagnification_(level)
                    except Exception:
                        pass
            AppHelper.callAfter(_set)
            self._level = level
        except Exception:
            pass
        return self._level

    def zoom(self, step: int = 0) -> float:
        return self._apply(_zoom_step(self._level, int(step)))

    def set_zoom(self, level: float = 1.0) -> float:
        try:
            return self._apply(float(level))
        except (TypeError, ValueError):
            return self._level


def _allow_pinch_zoom(window) -> None:
    """Trackpad pinch magnifies the native macOS window (WKWebView keeps it
    off unless asked). Call on the Cocoa main thread."""
    try:
        from webview.platforms.cocoa import BrowserView
        BrowserView.instances[window.uid].webview.setAllowsMagnification_(True)
    except Exception:
        pass


def _bring_window_forward(appkit, call_after, delays=ACTIVATE_DELAYS,
                          watch=ACTIVATE_WATCH, sleep=None,
                          clock=None, stop=None) -> bool:
    """Ask macOS at each of `delays` (on the main thread via `call_after`)
    to activate this app until it is active with a key window. Every
    outcome goes to the startup trace. Returns whether a request succeeded.

    `stop` (a threading.Event) ends the wait early: the window closed. Run
    this on a daemon thread only. pywebview runs the start callback on a
    non-daemon thread, and a wait left there (the declined-activation watch
    is up to ACTIVATE_WATCH[0] seconds) keeps the process alive after the
    window closes: a spinning cursor for up to two minutes, then exit."""
    import platform
    import threading as _th
    import time as _t
    sleep = sleep or _t.sleep
    clock = clock or _t.monotonic
    stop = stop or _th.Event()
    t0 = clock()
    _trace(f"window: macOS {platform.mac_ver()[0] or 'unknown'}, "
           f"{len(delays)} activation requests planned")

    def _on_main(fn):
        box, done = {}, _th.Event()

        def _run():
            try:
                box["r"] = fn()
            except Exception:
                box["r"] = None
            done.set()
        call_after(_run)
        for _ in range(20):
            if done.wait(0.1) or stop.is_set():
                break
        return box.get("r")

    def _stopped() -> bool:
        if stop.is_set():
            _trace(f"window: closed at +{clock() - t0:.1f}s; activation "
                   "watch ended")
            return True
        return False

    for i, d in enumerate(delays):
        wait = d - (clock() - t0)
        if wait > 0:
            sleep(wait)
        if _stopped():
            return False
        r = _on_main(lambda: _activate_once(appkit)) or (False, False)
        active, key = r
        _trace(f"window: activation request {i + 1} at "
               f"+{clock() - t0:.1f}s: active={active} key_window={key}")
        if active and key:
            return True
    _trace("window: macOS declined every activation request; clicks may be "
           "ignored until the user switches to another app and back")
    total, step = watch
    while clock() - t0 < total:
        sleep(step)
        if _stopped():
            return False
        app = appkit.NSApplication.sharedApplication()
        if _on_main(lambda: bool(app.isActive())):
            _trace(f"window: app became active at +{clock() - t0:.1f}s "
                   "(not by request)")
            return False
    _trace(f"window: still not active after +{total:.0f}s")
    return False


def _window_watchdog(window, url: str, wait: float = 4.0, retries: int = 3,
                     fail_page: str = _SERVER_FAIL_PAGE,
                     probe=None) -> str:
    """Wait for the window's `loaded` event (run on a thread from the start
    callback). If it never fires: reload only when the server answers HTTP
    (WKWebView cached a refused page); otherwise keep waiting, because
    load_url would cache another refused page and cancel the in-flight
    navigation (the reload storm). Show `fail_page` only after the whole
    budget. `probe` (injectable) defaults to a 1 s /api/versions request.

    Relies on pywebview 6.2.1: events.loaded fires only after a successful
    navigation; load_url clears it and dispatches to the Cocoa main loop, so
    calling it from this thread is safe.

    Returns 'loaded', 'recovered', or 'failed' (for tests)."""
    import threading
    if probe is None:
        probe = lambda: _server_answering(url)   # noqa: E731
    loaded = threading.Event()

    def _mark():
        _trace("watchdog: loaded event fired")
        loaded.set()

    try:
        window.events.loaded += _mark
        if window.events.loaded.is_set():   # fired before we attached
            loaded.set()
    except Exception:
        return "failed"
    _trace(f"watchdog: attached, waiting {wait}s for loaded")
    if loaded.wait(wait):
        _trace("watchdog: loaded within first wait")
        return "loaded"
    for attempt in range(max(1, retries)):
        if probe():
            # server up, page dead: the one case a reload fixes
            loaded.clear()
            _trace(f"watchdog: server answers but page dead, "
                   f"reload attempt {attempt + 1}")
            try:
                window.load_url(url)
            except Exception:
                pass
        else:
            _trace(f"watchdog: server not answering, waiting on "
                   f"(attempt {attempt + 1})")
        if loaded.wait(wait):
            _trace("watchdog: recovered within budget")
            return "recovered"
    _trace("watchdog: FAILED, showing failure page")
    try:
        window.load_html(fail_page)
    except Exception:
        pass
    return "failed"


def _windows_mshtml_only() -> bool:
    """True on Windows without the WebView2 runtime, where pywebview falls
    back to MSHTML (IE11): it renders pages but not the console JS, so forms
    silently misfire (a location pick ignored, a full-grid run launched).
    Probes Microsoft's documented EdgeUpdate client key `pv` (HKLM both
    views, HKCU); unreadable counts as missing, and the caller then opens
    the default browser instead.
    """
    import sys
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:
        return True
    key_id = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    probes = (
        (winreg.HKEY_LOCAL_MACHINE,
         "SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\" + key_id),
        (winreg.HKEY_LOCAL_MACHINE,
         "SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\" + key_id),
        (winreg.HKEY_CURRENT_USER,
         "Software\\Microsoft\\EdgeUpdate\\Clients\\" + key_id),
    )
    for hive, path in probes:
        try:
            with winreg.OpenKey(hive, path) as k:
                pv = winreg.QueryValueEx(k, "pv")[0]
            if pv and pv != "0.0.0.0":
                return False
        except OSError:
            continue
    return True


# ---------------------------------------------------------------------------
# Console, replay, verification and bank commands
# ---------------------------------------------------------------------------
@app.command("app")
def app_serve(port: int = 8710):
    """Launch the operations console. Prefers a native desktop window
    (pywebview) and falls back to the browser without it."""
    _trace("app: command entered")
    try:
        import webview  # noqa: F401
        if _windows_mshtml_only():
            print("WebView2 runtime not found: the native window would "
                  "render on MSHTML (IE11), which cannot run the console's "
                  "pages. Opening your default browser instead.")
        else:
            return app_window(port=port)
    except ImportError:
        pass
    import socket
    import threading
    import time
    import webbrowser

    import uvicorn

    # the same takeover and free-port guards as the window path
    _terminate_predecessor()
    _write_pidfile()
    port = _pick_port(port)
    url = f"http://localhost:{port}"

    def _wait_ready(timeout=30.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                with socket.create_connection(("127.0.0.1", port), 0.5):
                    return True
            except OSError:
                time.sleep(0.3)
        return False

    def _open():
        if _wait_ready():
            webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()
    # warning level, no colors: cmd shows ANSI escapes as garbage and the
    # progress poll would log a line a second; matches the window path
    uvicorn.run("app.ui.server:app", port=port, host="127.0.0.1",
                log_level="warning", use_colors=False)


@app.command("window")
def app_window(port: int = 8710):
    """The console in its own native window (no browser). Needs pywebview:
    .venv/bin/pip install pywebview"""
    import threading

    import uvicorn
    try:
        import webview
    except ImportError:
        print("pywebview not installed: .venv/bin/pip install pywebview")
        raise SystemExit(1)
    # pywebview refuses downloads unless ALLOW_DOWNLOADS is set (6.2.1
    # default False); without it "Download season report" is a dead end.
    if _windows_mshtml_only():
        print("WebView2 runtime not found: this window would render on "
              "MSHTML (IE11), which cannot run the console's pages. "
              "Serving to your default browser instead; install the "
              "Evergreen WebView2 Runtime from Microsoft to get the "
              "native window back.")
        return app_serve(port=port)
    webview.settings['ALLOW_DOWNLOADS'] = True
    _name_mac_process()
    _trace("window: webview imported, settings applied")
    # single instance: take over from a predecessor, then bind AND HOLD a
    # free port (otherwise the window can end up bound to nothing)
    signalled = _terminate_predecessor()
    _trace(f"window: predecessor takeover done (signalled={signalled})")
    drop_pidfile = _write_pidfile()
    sock, port = _bind_app_socket(port)
    url = f"http://localhost:{port}"
    _trace(f"window: port {port} bound and listening "
           f"(held={sock is not None}), starting server thread")

    def _serve():
        config = uvicorn.Config("app.ui.server:app", port=port,
                                host="127.0.0.1", log_level="warning")
        uvicorn.Server(config).run(sockets=[sock] if sock else None)

    threading.Thread(target=_serve, daemon=True).start()
    # Open the window now: the held socket queues WKWebView's first request
    # until the server finishes importing, so it is never refused.
    _trace("window: creating window (server import in flight)")
    api = _WindowApi()
    # zoomable: pinch and Ctrl+wheel zoom (pywebview blocks both otherwise)
    window = webview.create_window(APP_NAME, url,
                                   width=1120, height=800,
                                   min_size=(760, 520),
                                   zoomable=True, js_api=api)
    api._window = window
    closed = threading.Event()
    try:
        window.events.closed += closed.set
    except Exception:
        pass

    def _activate():
        # Runs on a secondary, NON-daemon thread of pywebview's: everything
        # that waits goes to a daemon thread of its own, and stops when the
        # window closes, or the process outlives the window (a spinning
        # cursor until the wait ends). Cocoa calls go through callAfter to
        # the main loop. A non-bundled process may start deactivated, hence
        # _bring_window_forward; the watchdog recovers a page that never
        # loaded.
        _trace("window: start callback fired (window shown)")
        threading.Thread(target=_window_watchdog, args=(window, url),
                         daemon=True).start()
        try:
            # pyobjc ships with pywebview
            import AppKit
            from AppKit import NSApplication, NSImage
            from PyObjCTools import AppHelper

            # Dock icon: a plain interpreter shows the Python icon; NSImage
            # cannot load the SVG, so use the 512px PNG. Under FluBNF.app's
            # host the Dock already shows the bundle's FluBNF.icns, which
            # the PNG would replace at launch.
            icon_png = (Path(__file__).resolve().parents[1]
                        / "app" / "ui" / "static" / "brand"
                        / "pybnf_icon_512.png")

            def _icon():
                try:
                    bid = AppKit.NSBundle.mainBundle().bundleIdentifier()
                    _trace(f"window: main bundle {bid}")
                    if bid == "edu.nau.flubnf":
                        return
                    if icon_png.is_file():
                        img = NSImage.alloc().initWithContentsOfFile_(
                            str(icon_png))
                        if img:
                            NSApplication.sharedApplication() \
                                .setApplicationIconImage_(img)
                except Exception:
                    pass
            AppHelper.callAfter(_icon)
            AppHelper.callAfter(_allow_pinch_zoom, window)
            threading.Thread(target=_bring_window_forward,
                             args=(AppKit, AppHelper.callAfter),
                             kwargs={"stop": closed}, daemon=True).start()
        except Exception:
            pass
    _trace("window: entering webview.start (main loop)")
    webview.start(_activate)
    # The window is gone: leave now. Every helper thread is a daemon, but
    # the interpreter's exit also waits on any thread a library left
    # running, and the user has closed the app, so nothing here is worth
    # a wait (a running fit is already lost with the server).
    _trace("window: closed; exiting")
    _exit_now(drop_pidfile)


def _exit_now(*cleanups) -> None:
    """Run `cleanups`, flush the standard streams and end the process
    without waiting for other threads (os._exit): the exit after the
    window closes, which must be immediate."""
    import os
    import sys as _sys
    for fn in cleanups:
        try:
            fn()
        except Exception:
            pass
    for stream in (_sys.stdout, _sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    os._exit(0)


class _RetroGroup(TyperGroup):
    """`flubnf retro <season> ...` replays a season (the `run` command,
    kept as the bare form); `export` and `import` move a replayed season
    between machines. A first word that is neither a subcommand nor --help
    (a season, or an option such as --locations) goes to `run`."""

    def parse_args(self, ctx, args):
        if args and args[0] not in self.commands and args[0] != "--help":
            args = ["run"] + list(args)
        return super().parse_args(ctx, args)


retro_app = typer.Typer(
    cls=_RetroGroup, add_completion=False, no_args_is_help=True,
    help="Replay a season as a competition (`flubnf retro <season>`), or "
         "export and import a replayed season as one zip bundle.")
app.add_typer(retro_app, name="retro")


@retro_app.command("run")
def retro_cmd(
    season: Annotated[str, typer.Argument(
        help="Season to replay, e.g. 2024-25.")],
    locations: Annotated[str, typer.Option(
        help="Comma-separated location names, or 'all' (52 jurisdictions).")] = "all",
    width: int = 0,
    replicates: Annotated[int, typer.Option(
        help="Particle-filter replicates (seeds) per location-week.")] = 3,
    root: Annotated[str, typer.Option(
        help="Season root to write (default: the console's "
             "app/state/retro/<season>, wherever the command runs).")] = "",
    aux: Annotated[str, typer.Option(
        help="Analogue donor preset; empty = the shipped Groundhog, "
             "'none' = the bare analogue (research).")] = "",
    oracle: Annotated[str, typer.Option(
        help="Empty = the Oracle SIHRS; 'none' = the plain filter "
             "(research).")] = "",
    knob: Annotated[Optional[list[str]], typer.Option(
        "--knob", help="Model knob as key=value (repeatable; see `flubnf "
                       "knobs`). Off-shipped values are recorded in "
                       "run_meta.json and a tree built with other values "
                       "is refused, not resumed.")] = None,
):
    """Run a season-as-competition retrospective (resumable).

    --width (shard width) 0 means auto: the engine's default_shard_width()
    for this machine, the same default the console form offers.

    aux names the analogue donor preset (analogue.AUX_PRESETS, e.g.
    'flusurv'). Empty runs the shipped Groundhog (analogue.SHIPPED_AUX);
    'none' the bare calendar analogue (research). The name and its bank
    digests go into run_meta.json.

    oracle: empty stores the Oracle SIHRS under pf (app/core/oracle.py
    applied to the filter's samples; the filter's quantiles are kept in
    oracle.json); 'none' stores the plain filter (research), which the
    week's oracle.json records.

    --knob key=value sets a model knob (app/core/knobs.py, parsed and
    range-checked by knobs.resolve). pf.particles and pf.replicates also
    come from here (--replicates is the older spelling of the latter; two
    different values are refused)."""
    import pandas as pd
    from pathlib import Path as _P
    from app.core import knobs as _K
    from app.core import retro
    from app.core.engines import pf as _pf
    pairs = {}
    for item in knob or []:
        k, sep, v = str(item).partition("=")
        if not sep or not k.strip():
            raise typer.BadParameter(f"--knob takes key=value, got {item!r}")
        if k.strip() in pairs:
            raise typer.BadParameter(f"--knob {k.strip()} given twice")
        pairs[k.strip()] = v.strip()
    # a season name becomes a directory: YYYY-YY with consecutive years
    import re as _re
    m = _re.fullmatch(r"(\d{4})-(\d{2})", season)
    if not m or (int(m.group(1)) + 1) % 100 != int(m.group(2)):
        raise typer.BadParameter(
            f"{season!r} is not a season; give one such as 2024-25")
    vints = retro.season_vintages(season)
    if not vints:
        from app.core import data as _data
        typer.echo(f"refused: no archived vintages for {season} in "
                   f"{_data.ARCHIVE} and no shipped snapshots for it in "
                   f"{_data.SHIPPED}; nothing was run. Update the hub clone, "
                   "or pick a season it holds.", err=True)
        raise typer.Exit(2)
    try:
        nd = _K.resolve(pairs, "all", scope="retro",
                        forecast_date=(vints[0] if vints else None),
                        check_dates=tuple(vints[-1:]),
                        oracle_step=(oracle != "none"),
                        legacy={"replicates": replicates})
    except _K.KnobError as e:
        raise typer.BadParameter(str(e)) from None
    replicates = int(nd.get("pf.replicates", 3))
    particles = int(nd.get("pf.particles", 10_000))
    width = _pf.resolve_width(width)
    from flubnf.settings import LOCATIONS
    locs = pd.read_csv(LOCATIONS, dtype=str)
    names = (list(locs.location_name[locs.location.str.len() == 2]
                  [locs.abbreviation != "US"])
             if locations == "all" else
             [x.strip() for x in locations.split(",")])
    # ABSOLUTE: runner subprocesses resolve conf/shard paths against their
    # own cwd, so a relative --root fails every fit.
    # the default is the console's own retro root (app/state/retro, beside
    # this package), never one under the shell's current directory
    from app.core.runs import APP_STATE as _APP_STATE
    r = (_P(root) if root else _APP_STATE / "retro" / season).resolve()
    from app.core.engines import analogue as _an
    if aux == "none":
        week_extra = _an.bare_analogue
    elif aux:
        week_extra = _an.aux_preset(aux)      # unknown name raises here
    else:
        week_extra = _an.aux_preset(_an.SHIPPED_AUX)
    print(f"  analogue donor configuration: {week_extra.__name__}")
    if oracle == "none":
        inner = week_extra

        def week_extra(asof, i, vintages, _inner=inner):
            d = dict(_inner(asof, i, vintages))
            d["oracle"] = "none"
            return d
        week_extra.__name__ = inner.__name__ + "+oracle:none"
        print("  Oracle step: none (the plain filter, a research run)")
    elif oracle:
        raise typer.BadParameter(
            "--oracle takes 'none' (the plain filter, a research run) or "
            "nothing (the Oracle SIHRS)")
    else:
        print("  Oracle step: applied (w = 0.5; the donor bank built from "
              "each week's vintage, named in the week's oracle.json)")
    kx = {}
    if nd:
        if "groundhog.aux" in nd and aux:
            if (_K.aux_choice(nd, None) or "none") != aux:
                raise typer.BadParameter(
                    "--aux and --knob groundhog.aux disagree; give one")
        if "groundhog.aux" in nd:
            pick = _K.aux_choice(nd, None)
            week_extra = (_an.aux_preset(pick) if pick
                          else _an.bare_analogue)
            if oracle == "none":
                inner2 = week_extra

                def week_extra(asof, i, vintages, _inner=inner2):
                    d = dict(_inner(asof, i, vintages))
                    d["oracle"] = "none"
                    return d
                week_extra.__name__ = inner2.__name__ + "+oracle:none"
        week_extra = _K.retro_week_extra(week_extra, nd)
        kx = {"settings": {"knobs": _K.jsonable(nd)},
              "drop_same_day": bool(nd.get("run.drop_same_day", False))}
        print(f"  model settings: {_K.label(nd)}")
    try:
        done = retro.run_season(r, season, names, replicates=replicates,
                                particles=particles,
                                width=width, week_extra=week_extra,
                                progress=lambda a: print(f"  {a} done",
                                                         flush=True), **kx)
    except retro.EngineBuildChanged as e:
        typer.echo(f"stopped: {e}", err=True)
        raise typer.Exit(2)
    except retro.ResumeMismatch as e:
        typer.echo(f"refused: {e}", err=True)
        raise typer.Exit(2)
    print(f"{season}: {len(done)} weeks complete -> {r}")


def _retro_root_default() -> Path:
    """The console's retro root (app/state/retro), read at call time."""
    from app.core.runs import APP_STATE
    return APP_STATE / "retro"


@retro_app.command("export")
def retro_export_cmd(
    season: Annotated[str, typer.Argument(
        help="Season to export, e.g. 2024-25.")],
    archive: Annotated[str, typer.Option(
        "--archive", help="Export this archived run (its stamp, as the "
                          "season list shows it) instead of the live one.")] = "",
    out: Annotated[str, typer.Option(
        "--out", help="Folder for the bundle (default: app/state/exports).")] = "",
    root: Annotated[str, typer.Option(
        "--root", help="Retro root holding the season (default: the "
                       "console's app/state/retro).")] = "",
):
    """Write a season's replay bundle: one zip of its run record, scores
    and every stored week, for `flubnf retro import` or the Retrospective
    tab on another machine. Prints the bundle's path and size."""
    from app.core import replay_bundle, retro
    rr = Path(root) if root else _retro_root_default()
    src = retro.archive_dir(rr, season, archive) if archive else rr / season
    if archive and not retro.valid_stamp(archive):
        raise typer.BadParameter(f"{archive!r} is not an archive stamp")
    try:
        p = replay_bundle.export_season(
            src, season, Path(out) if out else _retro_root_default().parent
            / "exports", stamp=archive)
    except replay_bundle.BundleError as e:
        typer.echo(f"refused: {e}", err=True)
        raise typer.Exit(2)
    m = replay_bundle.inspect_bundle(p)
    print(f"{season}: {len(m['weeks'])} weeks, "
          f"{retro.human_bytes(p.stat().st_size)} -> {p}")


@retro_app.command("import")
def retro_import_cmd(
    file: Annotated[Path, typer.Argument(
        exists=True, dir_okay=False, help="The .flubnf-replay.zip to import.")],
    replace: Annotated[bool, typer.Option(
        "--replace", help="Replace a copy already imported from the same "
                          "export.")] = False,
    root: Annotated[str, typer.Option(
        "--root", help="Retro root to import into (default: the console's "
                       "app/state/retro).")] = "",
):
    """Import a replay bundle as a read-only archived run of its season
    (<season>__archived_<export stamp> under the retro root). The live
    season tree is never written."""
    from app.core import replay_bundle
    rr = Path(root) if root else _retro_root_default()
    try:
        r = replay_bundle.import_bundle(file, rr, replace=replace)
    except replay_bundle.BundleError as e:
        typer.echo(f"refused: {e}", err=True)
        raise typer.Exit(2)
    when = (r.exported_at or "")[:10]
    print(f"imported {r.season}: {len(r.weeks)} weeks, exported from "
          f"{r.from_host or 'another machine'}"
          f"{' on ' + when if when else ''} -> {r.root}")
    print(f"  open it as /retro/{r.season}?archive={r.stamp}")
    for w in r.warnings:
        print(f"  note: {w}")


# ---------------------------------------------------------------------------
# groundhog: the calendar member alone. No particle filter or toolchain,
# about two minutes a season.
# ---------------------------------------------------------------------------
groundhog_app = typer.Typer(
    add_completion=False, no_args_is_help=True,
    help="GroundHogCGR, the calendar member, replayed and scored on its own.")
app.add_typer(groundhog_app, name="groundhog")

GROUNDHOG_SEASONS = ("2023-24", "2024-25", "2025-26")


def _gh_row(label: str, b: dict) -> str:
    if not b.get("cells"):
        return f"  {label:<26} no scorable cells"
    return (f"  {label:<26}{b['relwis']:>8.4f}"
            f"{b.get('cov50', float('nan')):>8.3f}"
            f"{b.get('cov80', float('nan')):>8.3f}"
            f"{b.get('cov95', float('nan')):>8.3f}"
            f"{b['worst_dev']:>8.3f}{b['cells']:>9,}{b['weeks']:>7}")


@groundhog_app.command("retro")
def groundhog_retro_cmd(
    season: str = typer.Argument(
        ..., help="A season such as 2024-25, or 'all' for the three on record."),
    aux: str = typer.Option(
        "", "--aux",
        help="Auxiliary donor preset (flusurv, iliplus, both); flusurv is "
             "the Groundhog. Empty runs the bare single-pool analogue "
             "(arm directory 'shipped', its historical name)."),
    compare: bool = typer.Option(
        True, "--compare/--no-compare",
        help="With --aux: also run the shipped member and report both on "
             "identical cells, with a clustered bootstrap on the difference."),
    with_us: bool = typer.Option(
        False, "--with-us",
        help="Also forecast the national row. Reported separately, never "
             "pooled into the state figures."),
):
    """Replay the calendar member alone over a season and score it.

    No particle filter, no PyBNF: only this repository, the committed donor
    bank, and a hub clone for the vintages, the truth and the FluSight
    baseline. About two minutes a season.
    """
    import pandas as pd
    from app.core import groundhog as gh
    seasons = list(GROUNDHOG_SEASONS) if season == "all" else [season]
    arms = ([gh.SHIPPED, aux] if (aux and compare) else [aux or gh.SHIPPED])
    runs = {a: [] for a in arms}
    for a in arms:
        for s in seasons:
            console.print(f"[bold]{a}[/bold]  {s}")
            try:
                r = gh.run_season(
                    s, "" if a == gh.SHIPPED else a, with_us=with_us,
                    progress=lambda asof, i, n: (
                        console.print(f"    {i:>3}/{n}  {asof}")
                        if (i % 8 == 0 or i == n) else None))
            except Exception as e:
                console.print(f"[red]{s}: {e}[/red]")
                raise typer.Exit(1)
            runs[a].append(r)
            if r["meta"]["aux"]:
                console.print(f"    donors: {r['meta']['aux']}")
            console.print(f"    -> {r['dir']}")

    head = (f"  {'':<26}{'relWIS':>8}{'cov50':>8}{'cov80':>8}{'cov95':>8}"
            f"{'worst':>8}{'cells':>9}{'weeks':>7}")
    pooled = {a: (pd.concat([r["cells"] for r in rs], ignore_index=True),
                  pd.concat([r["coverage"] for r in rs], ignore_index=True))
              for a, rs in runs.items()}

    console.print("\n[bold]Each arm on its own cells[/bold]  (52 states, US "
                  "national excluded)")
    console.print(head)
    for a, (c, v) in pooled.items():
        sm = gh.summarise(c, v)
        console.print(_gh_row(a, sm["states"]))
        if "us" in sm:
            console.print(_gh_row(f"{a}, US national", sm["us"]))

    if len(arms) == 2:
        (ac, av), (bc, bv) = pooled[arms[0]], pooled[arms[1]]
        cmp_ = gh.compare(ac, av, bc, bv)
        console.print(f"\n[bold]On identical cells[/bold]  "
                      f"({cmp_['common_cells']:,} common)")
        console.print(head)
        console.print(_gh_row(arms[0], cmp_["a"]))
        console.print(_gh_row(arms[1], cmp_["b"]))
        if len(seasons) > 1:
            console.print("\n[bold]By season[/bold]")
            console.print(f"  {'season':<10}{arms[0]:>10}{arms[1]:>10}"
                          f"{'change':>9}{'worst a':>9}{'worst b':>9}")
            for s, d in cmp_["by_season"].items():
                ra, rb = d["a"]["relwis"], d["b"]["relwis"]
                console.print(f"  {s:<10}{ra:>10.4f}{rb:>10.4f}"
                              f"{(1 - rb / ra) * 100:>+8.1f}%"
                              f"{d['a']['worst_dev']:>9.3f}"
                              f"{d['b']['worst_dev']:>9.3f}")
        bs = cmp_.get("bootstrap")
        if bs:
            console.print(
                f"\n  clustered bootstrap over {bs['clusters']} as-of dates, "
                f"{bs['reps']} replicates\n"
                f"  {arms[1]} minus {arms[0]}: median {bs['median']:+.4f}, "
                f"95 percent interval [{bs['lo']:+.4f}, {bs['hi']:+.4f}], "
                f"better in {bs['b_better']} of {bs['reps']}")
    console.print("\nSelf scored, ratio of WIS sums against the FluSight "
                  "baseline of the same\nreference date, on FluSight's cell "
                  "rule (truth of 0 and a median of 0 scored).\nThe FluSight "
                  "dashboard reports pairwise scaled relative WIS, within "
                  "about\n0.02 of this on the same cells. No finite-sample "
                  "coverage guarantee is claimed.")


# ---------------------------------------------------------------------------
# bank: build once with network, commit, then `verify` rebuilds from source
# and reports drift.
# ---------------------------------------------------------------------------
bank_app = typer.Typer(
    add_completion=False, no_args_is_help=True,
    help="Build, inspect and verify the committed auxiliary donor banks.")
app.add_typer(bank_app, name="bank")


@bank_app.command("build")
def bank_build_cmd(
    stream: str = typer.Argument(..., help="flusurv or iliplus"),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Write here instead of data/banks/."),
):
    """Build a donor bank from its upstream source and commit it.

    Needs network access once. Everything afterwards reads the committed
    file, so a clone with no network still produces a spliced forecast and
    a Delphi outage on submission day is not a failure.
    """
    from datetime import datetime, timezone
    from flubnf import bank as bankmod
    if stream not in bankmod.STREAMS:
        console.print(f"[red]unknown stream {stream!r}; "
                      f"known: {', '.join(bankmod.STREAMS)}[/red]")
        raise typer.Exit(2)
    console.print(f"[bold]building[/bold] the {stream} donor bank")
    try:
        b, url = bankmod.build_from_source(stream)
    except Exception as e:
        console.print(f"[red]build failed: {e}[/red]")
        raise typer.Exit(1)
    prev = None
    try:
        prev, _ = bankmod.read(stream, out)
    except Exception:
        pass                       # no committed bank yet, or an unusable one
    man = bankmod.write(stream, b, source_url=url,
                        built_utc=datetime.now(timezone.utc).isoformat(
                            timespec="seconds"),
                        builder="flubnf bank build", banks_dir=out)
    console.print(f"  cells     {man['cells']:>9,}")
    console.print(f"  locations {man['location_count']:>9}")
    console.print(f"  span      {man['span'][0]} to {man['span'][1]}")
    console.print(f"  digest    {man['digest'][:32]}")
    console.print(f"  -> {bankmod.bank_path(stream, out)}")
    console.print(f"  -> {bankmod.manifest_path(stream, out)}")
    if prev is not None:
        d = bankmod.compare(prev, b)
        if d["identical"]:
            console.print("  [green]unchanged from the committed bank[/green]")
        else:
            console.print(f"  [yellow]changed: +{d['added']} cells, "
                          f"-{d['removed']}, {d['changed']} revised[/yellow]")
    console.print("\n[bold]commit both files.[/bold] The bank is only "
                  "reproducible if the manifest travels with it.")


@bank_app.command("verify")
def bank_verify_cmd(
    stream: str = typer.Argument(..., help="flusurv or iliplus"),
    banks: Optional[Path] = typer.Option(
        None, "--banks", help="Read from here instead of data/banks/."),
):
    """Rebuild from source and say what moved against the committed bank.

    Exits non-zero when they differ, so a scheduled job can notice drift
    instead of a person having to remember to look.
    """
    from flubnf import bank as bankmod
    try:
        committed, man = bankmod.read(stream, banks)
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    console.print(f"[bold]committed[/bold] {man['cells']:,} cells, built "
                  f"{man['built_utc']}, digest {man['digest'][:16]}")
    try:
        fresh, _ = bankmod.build_from_source(stream)
    except Exception as e:
        console.print(f"[red]could not rebuild from source: {e}[/red]")
        raise typer.Exit(1)
    d = bankmod.compare(committed, fresh)
    if d["identical"]:
        console.print("[green]identical: the committed bank is current[/green]")
        return
    console.print(f"[yellow]DRIFT[/yellow]  fresh {d['fresh_cells']:,} cells "
                  f"against committed {d['committed_cells']:,}")
    console.print(f"  added   {d['added']:>6}  {d['added_sample']}")
    console.print(f"  removed {d['removed']:>6}  {d['removed_sample']}")
    console.print(f"  revised {d['changed']:>6}")
    for c in d["changed_sample"]:
        console.print(f"    {c['cell']}: {c['committed']} -> {c['fresh']}")
    console.print("\nRebuild with `flubnf bank build "
                  f"{stream}` and commit both files, or leave it: a "
                  "committed bank is a frozen donor pool and staying on it "
                  "is a legitimate choice, so long as it is a choice.")
    raise typer.Exit(1)


@bank_app.command("show")
def bank_show_cmd(
    stream: str = typer.Argument(..., help="flusurv or iliplus"),
    banks: Optional[Path] = typer.Option(
        None, "--banks", help="Read from here instead of data/banks/."),
):
    """Print a committed bank's manifest, digest verified."""
    from flubnf import bank as bankmod
    try:
        _, man = bankmod.read(stream, banks)
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    for k in ("stream", "built_utc", "source_url", "cells", "location_count",
              "span", "digest", "layout_version", "builder"):
        if k in man:
            console.print(f"  {k:<15} {man[k]}")
    console.print(f"  {'locations':<15} {', '.join(man['locations'])}")


# ---------------------------------------------------------------------------
# oracle: verification only. Backfill a stored season's Oracle SIHRS into a
# NEW root from its samples (no refit, no engine) and score it beside the
# registered screen (docs/ORACLE-SIHRS.md). Seasons are run by a replay.
# ---------------------------------------------------------------------------
oracle_app = typer.Typer(
    add_completion=False, no_args_is_help=True,
    help="Verification only: backfill a stored season into a new root and "
         "reproduce the registered screen's relWIS with the app's scorer, "
         "no refit. A season is run and viewed by a console replay "
         "(flubnf retro, or the Retrospective tab).")
app.add_typer(oracle_app, name="oracle")


@oracle_app.command("backfill")
def oracle_backfill_cmd(
    season: str = typer.Argument(..., help="The season the root holds, e.g. 2025-26."),
    source: Path = typer.Option(
        ..., "--source", help="A season root of stored weeks. Read only."),
    out: Path = typer.Option(
        ..., "--out",
        help="A NEW season root to write. Never the source or a path under "
             "it, never under app/state, never a non-empty tree without --force."),
    force: bool = typer.Option(
        False, "--force", help="Write into a non-empty --out."),
    keep_filter: bool = typer.Option(
        True, "--keep-filter/--no-keep-filter",
        help="Keep the source's pf verbatim under the research key pf_filter "
             "beside the member (a research root; a replay's stored week "
             "does not carry it)."),
):
    """Compute the Oracle SIHRS for every stored week of a season root, from
    the stored samples and no refit, into a new root: a verification that
    the app's code reproduces the registered screen, not how a season is
    run or viewed (that is a console replay, flubnf retro).

    Each week is read through the storage boundary and written back
    through it: pf the member (the submitted seed's samples), pf_filter
    the source's pf, analogue verbatim, the sidecar, oracle.json and the
    donor pool beside it. The hub this process reads (FLUBNF_HUB) supplies
    the vintages the pools are built from.
    """
    from app.core import oracle_backfill as obf
    try:
        res = obf.backfill_season(
            source, out, season, force=force, keep_filter=keep_filter,
            progress=lambda a, m: console.print(f"  {a}  {m}"))
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    console.print(f"[bold]{season}[/bold]: {len(res['weeks'])} weeks backfilled "
                  f"-> {res['out']} in {res['seconds']}s"
                  + (f"; skipped (no pf block): {', '.join(res['skipped'])}"
                     if res["skipped"] else ""))


@oracle_app.command("reproduce")
def oracle_reproduce_cmd(
    roots: List[Path] = typer.Argument(
        ..., help="Backfilled season roots (one or more)."),
    source: Optional[List[Path]] = typer.Option(
        None, "--source",
        help="The source roots, scored read only for the plain filter (the "
             "NULL); every week's quantile sidecar must be current."),
    screen: Optional[Path] = typer.Option(
        None, "--screen",
        help="The registered screen's screen_scores.json (or the B2 screen's "
             "screen_b2_scores.json, the shipped bank), printed beside."),
):
    """Score backfilled roots with the app's own scorer and print relWIS
    per season and over the seasons together, on the record definition
    (each member's own scored cells) and on the common set (cells both
    stored members scored), each with its cell count, beside the screen's
    tables. FLUBNF_HUB must be the hub whose truth and baseline the screen
    used.
    """
    from flubnf.settings import HUB
    from app.core import oracle_backfill as obf
    try:
        res = obf.reproduce(list(roots), source_roots=(list(source) if source else None),
                            screen_json=screen)
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    console.print(f"[bold]reproduce[/bold]  hub {HUB}")
    for line in obf.report_lines(res):
        console.print(line, highlight=False)
    console.print(f"  cells scored (member root): {res['cells_scored']:,}")
    if res.get("screen"):
        console.print(f"  screen frozen document {res['screen'].get('frozen_document_sha256')}"
                      + (f", B2 document {res['screen']['b2_frozen_sha256']}"
                         if res['screen'].get('b2_frozen_sha256') else ""))


# ---------------------------------------------------------------------------
# site: build the public static site from the lab's own state.
# ---------------------------------------------------------------------------
site_app = typer.Typer(
    add_completion=False, no_args_is_help=True,
    help="Build the public static site from the lab's retrospectives.")
app.add_typer(site_app, name="site")


@site_app.command("build")
def site_build_cmd(
    out: Optional[Path] = typer.Option(
        None, "--out", help="Output directory (default: the repo's site/)."),
    season: str = typer.Option(
        "", "--season",
        help="Pin the home outlook to this season instead of the newest "
             "forecast. Deliberate override; recorded in the payload."),
    asof: str = typer.Option(
        "", "--asof",
        help="Pin the home outlook to this forecast week (YYYY-MM-DD). "
             "Requires the week to exist in the chosen season."),
    check: bool = typer.Option(
        False, "--check",
        help="Exit non-zero if any computed score disagrees with the "
             "figure the console publishes for the same season."),
):
    """Read the app's state and write the static site.

    Everything on the page is computed here from the stored forecasts: the
    outlook map from the newest full-country forecast, the season table from
    whichever retrospective seasons exist on disk, and Methods from the
    console's own templates. Nothing is copied from a note.
    """
    from app.core import site_build as sb
    pin = (season, asof) if (season or asof) else None
    try:
        res = sb.build(out_dir=out, pin=pin)
    except sb.BuildError as e:
        console.print(f"[red]site build: {e}[/red]")
        raise typer.Exit(2)

    src = res["outlook"]
    console.print(f"[bold]site[/bold] -> {res['out']}")
    console.print(f"  page      {res['page_bytes']:>9,} bytes")
    console.print(f"  payload   {res['payload_bytes']:>9,} bytes"
                  "   (site.json, review this diff)")
    console.print(f"  plotly    {res['plotly_bytes']:>9,} bytes"
                  "   (cached sibling, not inlined)")
    console.print(f"  outlook   {src['label']}")
    console.print(f"  locations {res['locations']}")
    console.print(f"  seasons   {', '.join(res['seasons']) or 'none'}")
    if res["pooled"] is not None:
        console.print(f"  pooled    Oracle SIHRS relWIS {res['pooled']:.4f}")
    console.print(f"  built in  {res['elapsed_s']:.1f}s")

    if res["mismatches"]:
        console.print("[red]scores disagree with the console:[/red]")
        for m in res["mismatches"]:
            console.print(f"  {m['what']}: computed {m['computed']:.4f}, "
                          f"console states {m['app']:.4f}")
        if check:
            raise typer.Exit(1)
    else:
        console.print("[green]  scores match the console's published "
                      "figures[/green]")


# ---------------------------------------------------------------------------
# dataset: custom target data (grouped or hubverse CSV), checked offline.
# ---------------------------------------------------------------------------
dataset_app = typer.Typer(
    add_completion=False, no_args_is_help=True,
    help="Check, import, list and delete custom target data (a grouped "
         "CSV or a hubverse time series; comma, semicolon or tab separated; "
         "UTF-8, UTF-16 or Windows-1252; or a folder of snapshot files, one "
         "per as_of).")
app.add_typer(dataset_app, name="dataset")

_KIND_HELP = ("'count' or 'rate'; default: from the values (whole numbers "
              "are counts; numbers like 1.234, whose dot could separate "
              "thousands, need it).")
_COLUMN_HELP = ("ROLE=HEADER (or ROLE=#N, the Nth column) when the headers "
                "do not say which column is which; ROLE is date, group, "
                "value or population. Repeat for each.")


def _dataset_columns(pairs) -> dict:
    """--column ROLE=HEADER pairs as validate's mapping; a malformed pair
    or an unknown role is a usage error (exit 2)."""
    from app.core import datasets as ds
    out = {}
    for pair in pairs or []:
        role, sep, header = str(pair).partition("=")
        role = role.strip().lower()
        if not sep or role not in ds.ROLES or not header.strip():
            raise typer.BadParameter(
                f"{pair!r}: expected ROLE=HEADER with ROLE one of "
                f"{', '.join(ds.ROLES)}.", param_hint="--column")
        out[role] = header.strip()
    return out


_PATHS_HELP = ("A CSV, or a folder of snapshot files (or several files): "
               "one per as_of, each named by its as_of date "
               "(2024-10-05.csv) or holding an as_of column, read as one "
               "vintage-true dataset.")


def _dataset_sources(paths) -> tuple:
    """(label, [(filename, path), ...]) for the paths given: a file as
    itself, a folder as its CSV, TSV and TXT files (named with the folder,
    so the dataset takes the folder's name). Exit 2 on an empty folder."""
    out = []
    for p in paths:
        if p.is_dir():
            got = sorted(q for q in p.iterdir() if q.is_file()
                         and q.suffix.lower() in (".csv", ".tsv", ".txt"))
            if not got:
                raise typer.BadParameter(f"{p} holds no CSV, TSV or TXT "
                                         "files.", param_hint="PATHS")
            out += [(f"{p.name}/{q.name}", q) for q in got]
        else:
            out.append((p.name, p))
    label = (paths[0].name if len(paths) == 1
             else f"{len(out)} files")
    return label, out


def _print_dataset_problems(name: str, rep_problems, rep=None) -> None:
    from app.core import datasets as ds
    print(f"{name}: {len(rep_problems)} problem(s), nothing stored")
    if rep is not None:
        lines = ds.problem_lines(rep)
    else:
        lines = []
        for kind, probs in ds.problem_groups(rep_problems):
            lines.append(f"{kind}:")
            lines += [f"  - {p}" for p in probs]
    for line in lines:
        print(f"  {line}")


@dataset_app.command("validate")
def dataset_validate_cmd(
    paths: List[Path] = typer.Argument(..., exists=True,
                                       help="The CSV to check. " + _PATHS_HELP),
    kind: Optional[str] = typer.Option(None, "--kind", help=_KIND_HELP),
    target: Optional[str] = typer.Option(
        None, "--target", help="The target to keep when the file has several."),
    column: Optional[List[str]] = typer.Option(
        None, "--column", help=_COLUMN_HELP),
    sunday: bool = typer.Option(
        False, "--sunday", hidden=True,
        help="Accepted and ignored: any one weekday is moved to Saturday."),
):
    """Validate a dataset CSV (or a folder of snapshot files) and print
    every problem, or a summary.

    Exit code 0 when the data is valid, 1 when it has problems. Nothing is
    stored."""
    from app.core import datasets as ds
    label, sources = _dataset_sources(paths)
    rep = ds.validate_snapshots(sources, kind=kind, target=target,
                                columns=_dataset_columns(column))
    if not rep.ok:
        _print_dataset_problems(label, rep.problems, rep)
    else:
        print(f"{label}: valid")
        for line in ds.summary_lines(rep):
            print(f"  {line}")
    for w in rep.warnings:
        print(f"  note: {w}")
    if not rep.ok:
        raise typer.Exit(1)


@dataset_app.command("import")
def dataset_import_cmd(
    paths: List[Path] = typer.Argument(..., exists=True,
                                       help="The CSV to store. " + _PATHS_HELP),
    kind: Optional[str] = typer.Option(None, "--kind", help=_KIND_HELP),
    name: Optional[str] = typer.Option(
        None, "--name", help="The dataset's name (default: the file name, "
                             "with the target when the file holds several; "
                             "a folder's name for its snapshots)."),
    target: Optional[str] = typer.Option(
        None, "--target", help="The target to keep when the file has several."),
    column: Optional[List[str]] = typer.Option(
        None, "--column", help=_COLUMN_HELP),
    sunday: bool = typer.Option(
        False, "--sunday", hidden=True,
        help="Accepted and ignored: any one weekday is moved to Saturday."),
):
    """Validate and store a dataset CSV (or a folder of snapshot files),
    as the console's upload does.

    Prints the dataset's id and summary (exit 0), or every problem (exit 1,
    nothing stored). Importing the same data with the same options again
    returns the stored dataset."""
    from app.core import datasets as ds
    columns = _dataset_columns(column)
    label, sources = _dataset_sources(paths)
    try:
        d = ds.ingest_snapshots(sources, (name or "")[:80] or None,
                                kind=kind, target=target, columns=columns)
    except ds.DatasetError as e:
        _print_dataset_problems(label, e.problems, e.report)
        raise typer.Exit(1)
    print(f"stored {d.name!r} as {d.id}")
    print(f"  groups      {len(d.groups)}: {', '.join(d.groups[:8])}"
          + (" ..." if len(d.groups) > 8 else ""))
    print(f"  weeks       {len(d.weeks())} ({d.meta['date_range'][0]} to "
          f"{d.meta['date_range'][1]})")
    inferred = d.meta.get("options", {}).get("kind_from") == "values"
    print(f"  kind        {d.kind}"
          + (" (inferred from the values; --kind to change)" if inferred
             else ""))
    print(f"  population  {'yes' if d.has_population else 'no'}")
    print(f"  vintages    " + (f"{len(d.vintages())} (vintage-true)"
                               if d.vintage_true else "none (final data)")
          + (f", from {len(d.meta['snapshot_files'])} files"
             if d.meta.get("snapshot_files") else ""))
    if d.meta.get("target"):
        print(f"  target      {d.meta['target']}")
    if d.national_group:
        print(f"  national    {d.national_group}")
    for w in d.meta.get("warnings") or []:
        print(f"  note: {w}")


@dataset_app.command("list")
def dataset_list_cmd():
    """List the stored datasets, newest first."""
    from app.core import datasets as ds
    items = ds.list_datasets()
    if not items:
        print("no datasets stored")
        return
    for d in items:
        print(f"{d.id}  {d.name!r}  {len(d.groups)} group(s), "
              f"{len(d.weeks())} week(s), {d.kind}, population "
              f"{'yes' if d.has_population else 'no'}, vintages "
              f"{'yes' if d.vintage_true else 'no'}")


@dataset_app.command("delete")
def dataset_delete_cmd(
    dataset_id: str = typer.Argument(..., help="The id `dataset list` prints."),
    yes: bool = typer.Option(False, "--yes", help="Delete without asking."),
):
    """Delete a stored dataset and its replays (runs keep their results)."""
    from app.core import datasets as ds
    try:
        d = ds.get(dataset_id)
    except ds.DatasetError as e:
        print(str(e))
        raise typer.Exit(1)
    if not yes and not typer.confirm(f"Delete {d.name!r} ({d.id}) and its "
                                     "replays?"):
        print("nothing deleted")
        raise typer.Exit(1)
    ds.delete(d.id)
    print(f"deleted {d.name!r} ({d.id})")


if __name__ == "__main__":
    app()
