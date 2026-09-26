"""Run a console script under FluBNF.app's host, and reopen Terminal when it
fails at startup.

flubnf_host.c runs `<venv python> host_boot.py <script> [args...]` for a
launch from the Dock (FLUBNF_HOST_FALLBACK, set only by flubnf-launch). This
behaves as `python <script> [args...]`, except in one case. A failure in the
first STARTUP seconds also opens FluBNF.command in Terminal, where the launch
repeats in view. A failure is an uncaught exception or a nonzero exit.
Without this, a Dock launch that fails shows a bouncing icon that vanishes.

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


def to_terminal(why: str, run=subprocess.run) -> None:
    """Say why in the launch log, then open FluBNF.command in Terminal.
    Waits for `open` (it returns once Terminal has the request), so the
    request is sent before this process exits. Never raises."""
    sys.stderr.write(f"flubnf-host: {why}; reopening FluBNF.command in Terminal\n")
    sys.stderr.flush()
    if sys.platform != "darwin":
        return
    try:
        run(["/usr/bin/open", "-a", "Terminal",
             os.path.join(REPO, "FluBNF.command")],
            stdin=subprocess.DEVNULL, timeout=30, check=False)
    except Exception as e:
        sys.stderr.write(f"flubnf-host: could not open Terminal: {e}\n")


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
            to_terminal(f"the console stopped at startup (exit {e.code})")
        raise
    except BaseException:
        if clock() - t0 >= STARTUP:
            raise
        import traceback
        traceback.print_exc()
        to_terminal("the console failed at startup")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
