"""Run a console script under FluBNF.app's host, and reopen Terminal when it
fails at startup.

flubnf_host.c runs `<venv python> host_boot.py <script> [args...]` for a
launch from the Dock (FLUBNF_HOST_FALLBACK, set only by flubnf-launch). This
behaves as `python <script> [args...]`, except in one case. A failure in the
first STARTUP seconds is reported to the Terminal that asked for this launch
(FLUBNF_BOOT_STATUS), or else handed to the bundle's launcher
(`flubnf-launch --handover <why>`), which reopens FluBNF.command in Terminal,
where the launch repeats in view, unless its guards say that would loop. A
failure is an uncaught exception or a nonzero exit. Without this, a Dock
launch that fails shows a bouncing icon that vanishes.

The C host cannot do this itself. An uncaught SystemExit from a script ends
in Py_Exit() -> exit() (Python/pythonrun.c, handle_system_exit), so
Py_BytesMain never returns to it.
"""
import os
import runpy
import subprocess
import sys
import time

#: a failure this early is a startup failure, not a crash after use
STARTUP = 30.0

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
#: every automatic reopen of Terminal goes through the launcher's guards
LAUNCHER = os.path.join(REPO, "FluBNF.app", "Contents", "MacOS", "flubnf-launch")


def report(why: str) -> bool:
    """A launch that FluBNF.command started through `open` (FLUBNF_LAUNCH=
    ready) passes FLUBNF_BOOT_STATUS: write `why` there, where the Terminal
    that asked reads it and starts the console in view, rather than opening
    a second Terminal. True when reported so."""
    path = os.environ.get("FLUBNF_BOOT_STATUS")
    if not path:
        return False
    try:
        with open(path, "w") as fh:
            fh.write(why + "\n")
    except OSError:
        return False
    sys.stderr.write(f"flubnf-host: {why}\n")
    sys.stderr.flush()
    return True


def to_terminal(why: str, run=subprocess.run) -> None:
    """Say why in the launch log, then hand over to the launcher, which
    reopens FluBNF.command in Terminal unless its guards say not to (a
    Terminal already waits on this launch; it reopened a moment ago).
    Waits for the launcher (`open` returns once Terminal has the request),
    so the request is sent before this process exits. Never raises."""
    sys.stderr.write(f"flubnf-host: {why}; handing over to FluBNF.command "
                     "in Terminal\n")
    sys.stderr.flush()
    if sys.platform != "darwin":
        return
    try:
        run(["/bin/bash", LAUNCHER, "--handover", why],
            stdin=subprocess.DEVNULL, timeout=30, check=False)
    except Exception as e:
        sys.stderr.write(f"flubnf-host: could not hand over: {e}\n")


def main(argv=None, clock=time.monotonic, run=runpy.run_path) -> None:
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 2:
        sys.exit("usage: host_boot.py <script> [args...]")
    script = argv[1]
    # the launch log gets each line as it is written, as a Terminal would;
    # not PYTHONUNBUFFERED, which every child would inherit
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass
    # as `python <script> args` sets them
    sys.argv = argv[1:]
    sys.path[0] = os.path.dirname(os.path.abspath(script))
    t0 = clock()
    try:
        run(script, run_name="__main__")
    except SystemExit as e:
        if e.code not in (None, 0) and clock() - t0 < STARTUP:
            why = f"the console stopped at startup (exit {e.code})"
            report(why) or to_terminal(why)
        raise
    except BaseException:
        if clock() - t0 >= STARTUP:
            raise
        import traceback
        traceback.print_exc()
        report("the console failed at startup") \
            or to_terminal("the console failed at startup")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
