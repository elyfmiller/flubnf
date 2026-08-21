"""How this application starts the processes that do the fitting.

One rule, and the reason for it: a fit subprocess starts at a LOWER
scheduling priority than the interactive server.

The trade is deliberate. During a multi-hour run the fitting processes will
take every core they are given, and the server answering the user's clicks
is then just another runnable process competing with them. Measured on the
development machine with the cores saturated, page latency rose from about
25 ms to about 260 ms, and the retrospective index from 68 ms to 383 ms.
Niceness 5 costs the fits a few percent of throughput only while the user is
actually clicking (an idle machine gives the niced processes everything
anyway), and it buys back an application that stays usable for the whole run.
For an application whose runs last all night, that is the correct trade.

Mechanism: the command is prefixed with the platform's `nice`, which execs
the target, so the returned Popen still refers to the real process and stop
and terminate behave exactly as before. `nice` is preferred over os.nice(5)
in a preexec_fn because both call sites spawn from a background thread while
the heartbeat and server threads run, and preexec_fn is documented as unsafe
in the presence of threads. Both forms ask the kernel for the same thing.

Guarded throughout: on a platform without `nice`, or if the lookup fails,
the prefix is empty and the process starts exactly as it did before. Lower
priority is an optimization, never a precondition, and no run may fail
because it was unavailable.
"""
from __future__ import annotations

import os
import shutil

#: How much to yield. 5 is a light touch: enough that an interactive request
#: preempts a fit promptly, far short of the 10-plus that would visibly
#: lengthen an overnight run on an otherwise idle machine.
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
