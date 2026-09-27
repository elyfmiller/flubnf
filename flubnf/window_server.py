"""The console server for the native window, in a process of its own.

`flubnf window` binds the port, then starts this module with the listening
socket's file descriptor and its own pid:

    python -m flubnf.window_server <fd> <parent pid>

Why a separate process: in one process the window's main thread (Cocoa on
macOS) and the server share one interpreter lock, so any long step of a
forecast held in the server (reading a filter's samples, the Oracle step,
building a report) also stops the window from handling events: no hover,
no resizing, until the step ends. Here the server can be as busy as it
likes; the window stays responsive.

The server exits when its parent does (checked every second), so a window
that is killed or crashes never leaves a server holding the port.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time

PARENT_POLL_S = 1.0


def _parent_gone(parent: int) -> bool:
    """True once `parent` is no longer this process's parent (it exited and
    the process was re-parented) or no longer exists."""
    if os.getppid() != parent:
        return True
    if os.name != "posix":
        # os.kill(pid, 0) TERMINATES the process on Windows; this module
        # is started on POSIX only, so the parent check above is enough
        return False
    try:
        os.kill(parent, 0)
    except ProcessLookupError:
        return True
    except OSError:
        pass            # exists, owned elsewhere: still alive
    return False


def watch_parent(parent: int, poll: float = PARENT_POLL_S,
                 exit_now=os._exit, sleep=time.sleep) -> None:
    """Leave (immediately, no cleanup: the window is gone) when `parent`
    exits. Runs on a daemon thread."""
    while not _parent_gone(parent):
        sleep(poll)
    exit_now(0)


def main(argv: list | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    fd, parent = int(argv[0]), int(argv[1])
    # family and type are read from the descriptor (a TCP listener)
    sock = socket.socket(fileno=fd)
    threading.Thread(target=watch_parent, args=(parent,), daemon=True,
                     name="parent-watch").start()
    import uvicorn
    config = uvicorn.Config("app.ui.server:app", host="127.0.0.1",
                            log_level="warning", use_colors=False)
    uvicorn.Server(config).run(sockets=[sock])


if __name__ == "__main__":
    main()
