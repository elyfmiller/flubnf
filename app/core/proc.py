"""PRODUCTION: reduced-priority subprocess helpers (engines/pf.py, retro
runners).

How this application starts fit subprocesses: below the interactive
server's scheduling priority.

With the cores saturated, page latency rose ~25 -> ~260 ms; niceness 5 costs
the fits a few percent only while the user is clicking. The command is
prefixed with `nice` (which execs the target, so Popen still refers to the real
process) rather than os.nice in preexec_fn, because callers spawn from threads
and preexec_fn is unsafe with threads. Windows uses BELOW_NORMAL_PRIORITY_CLASS.
Best effort: on any failure the process starts unmodified; no run may fail
for want of lower priority.
"""
from __future__ import annotations

import os
import shutil

#: a light touch: interactive requests preempt promptly; 10+ would lengthen overnight runs
NICENESS = 5


def low_priority_prefix(niceness: int = NICENESS) -> list:
    """Command prefix that starts a child at reduced priority, or [].

    Returns [] rather than raising on any platform or lookup failure: the
    caller then spawns the process unmodified.
    """
    if os.name != "posix" or not niceness:
        return []
    try:
        nice = shutil.which("nice") or (
            "/usr/bin/nice" if os.path.exists("/usr/bin/nice") else "")
    except Exception:
        return []
    return [nice, "-n", str(int(niceness))] if nice else []


def low_priority_cmd(cmd: list, niceness: int = NICENESS) -> list:
    """`cmd` rewritten to start at reduced priority where the platform
    allows it, and returned unchanged where it does not."""
    return low_priority_prefix(niceness) + list(cmd)


def low_priority_popen_kwargs(niceness: int = NICENESS) -> dict:
    """Popen kwargs for reduced priority where a prefix cannot (Windows:
    BELOW_NORMAL_PRIORITY_CLASS), else {}. Call sites combine both forms and
    each platform activates exactly one:

        Popen(low_priority_cmd(cmd), **low_priority_popen_kwargs())
    """
    if os.name != "nt" or not niceness:
        return {}
    try:
        import subprocess
        return {"creationflags": subprocess.BELOW_NORMAL_PRIORITY_CLASS}
    except Exception:
        return {}
