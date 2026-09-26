"""FluBNF command-line interface (`flubnf`): the root app and the console
launch. The other command groups live in sibling modules and are mounted at
the bottom of this file, so `flubnf.cli:app` (pyproject's entry point)
carries every command.

Sections, in file order:
  1. help panels, root app and options, _trace
  2. takeover: entry markers, ancestor walk, pid cmdline/liveness probes
     (POSIX and Windows), PF runner sweep, pidfile
  3. ports: candidates, reuse flags, pick/bind
  4. macOS window: activation retries, app naming, zoom API, watchdog,
     WebView2 probe
  5. the `app` and `window` commands and _exit_now
  6. the mounted groups: cli_doctor (doctor, knobs), cli_retro (retro,
     groundhog), cli_verify (oracle, site), cli_bank, cli_datasets

Heavy imports (pandas, scipy, uvicorn) stay inside the commands so that
`flubnf app` opens its window without loading them
(test_cli_import_stays_light). Tests patch the helpers here by name on this
module, so every caller looks them up through the module globals at call
time; keep them in this file.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
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


# ---------------------------------------------------------------------------
# ports: a nearby free port when the preferred one stays bound
# ---------------------------------------------------------------------------
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


def _bind_app_socket(preferred: int = 8710, tries: int = 10,
                     settle: float = 0.0, sleep=None, clock=None):
    """(listening socket, port) for the window path, bound and LISTENING
    before the window opens, then handed to the server. Holding it removes
    the probe-then-bind race, and WKWebView's first request waits in the
    backlog instead of being refused (the dead-first-window bug).
    (None, preferred) when all are busy so uvicorn reports the conflict.

    `settle`: seconds to keep retrying `preferred` first. A relaunch that
    just stopped its predecessor passes it, because the predecessor's
    server process exits up to a second after its window; binding the next
    port instead would change the page's origin, and with it the theme,
    contrast and font size the page keeps in localStorage."""
    import socket
    import time
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    t0 = clock()
    while settle > 0 and clock() - t0 < settle:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            _set_port_reuse(s)
            s.bind(("127.0.0.1", preferred))
            s.listen(128)
            return s, s.getsockname()[1]
        except OSError:
            s.close()
            sleep(0.1)
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


# ---------------------------------------------------------------------------
# macOS window: activation, app name, zoom, load watchdog, WebView2 probe
# ---------------------------------------------------------------------------
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
# The `app` and `window` commands
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


def _start_window_server(sock, port: int, popen=None, platform=None):
    """Start the console server for the window and return a callable that
    stops it.

    POSIX: a child process (python -m flubnf.window_server) that inherits
    the held listening socket, so the window's main thread never shares an
    interpreter lock with the server: a long step of a forecast can no
    longer freeze hover and resizing. The child leaves when this process
    does. Windows, or no held socket (every port busy, so uvicorn reports
    the conflict): a daemon thread, as before."""
    import os
    import sys
    import threading
    platform = platform or os.name
    if platform == "posix" and sock is not None:
        import subprocess
        popen = popen or subprocess.Popen
        repo = str(Path(__file__).resolve().parents[1])
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (repo, env.get("PYTHONPATH", "")) if p)
        fd = sock.fileno()
        proc = popen([sys.executable, "-m", "flubnf.window_server",
                      str(fd), str(os.getpid())],
                     pass_fds=(fd,), cwd=repo, env=env)
        sock.close()            # the child holds its own copy
        _trace(f"window: server process {proc.pid} started on port {port}")

        def _stop():
            # the window is closing: give the server a moment, then end it
            # (a running fit is lost either way, as with the old thread)
            try:
                proc.terminate()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        return _stop

    import uvicorn

    def _serve():
        config = uvicorn.Config("app.ui.server:app", port=port,
                                host="127.0.0.1", log_level="warning")
        uvicorn.Server(config).run(sockets=[sock] if sock else None)

    threading.Thread(target=_serve, daemon=True).start()
    return lambda: None


@app.command("window")
def app_window(port: int = 8710):
    """The console in its own native window (no browser). Needs pywebview:
    .venv/bin/pip install pywebview"""
    import threading
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
    sock, port = _bind_app_socket(port, settle=3.0 if signalled else 0.0)
    url = f"http://localhost:{port}"
    _trace(f"window: port {port} bound and listening "
           f"(held={sock is not None}), starting server thread")

    stop_server = _start_window_server(sock, port)
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
    _exit_now(drop_pidfile, stop_server)


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


# ---------------------------------------------------------------------------
# The other command groups, one module each. Imported here, after `app`
# exists, so `flubnf.cli:app` carries them; the modules import only typer
# and rich at module level (the import-light rule above).
# ---------------------------------------------------------------------------
from .cli_bank import (  # noqa: F401
    bank_app,
    bank_build_cmd,
    bank_show_cmd,
    bank_verify_cmd,
)
from .cli_datasets import (  # noqa: F401
    dataset_app,
    dataset_delete_cmd,
    dataset_import_cmd,
    dataset_list_cmd,
    dataset_validate_cmd,
)
from .cli_doctor import doctor, knobs
from .cli_retro import (  # noqa: F401
    GROUNDHOG_SEASONS,
    groundhog_app,
    groundhog_retro_cmd,
    retro_app,
    retro_cmd,
    retro_export_cmd,
    retro_import_cmd,
)
from .cli_verify import (  # noqa: F401
    oracle_app,
    oracle_backfill_cmd,
    oracle_reproduce_cmd,
    site_app,
    site_build_cmd,
)

app.command()(doctor)
app.command()(knobs)
app.add_typer(retro_app, name="retro")
app.add_typer(groundhog_app, name="groundhog")
app.add_typer(bank_app, name="bank")
app.add_typer(oracle_app, name="oracle")
app.add_typer(site_app, name="site")
app.add_typer(dataset_app, name="dataset")


if __name__ == "__main__":
    app()
