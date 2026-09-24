"""Console-wide mutable state and path anchors, one home per object.

Stdlib only: app/ui/server.py imports this before fastapi and app.core, so
the startup trace's "import begin" line still precedes them. Containers are
mutated in place and never rebound; the one rebinding is the data_mod proxy
(its first use swaps in app.core.data), so every other module reads
`state.data_mod` at call time and never imports the name.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
#: app/ui itself (unresolved, like the static and templates directories)
UI_DIR = Path(__file__).parent


def _trace(msg: str) -> None:
    """Startup trace: server half of flubnf/cli.py's _trace (same format and
    FLUBNF_STARTUP_TRACE file, so the two interleave); free when unset."""
    import os as _os
    path = _os.environ.get("FLUBNF_STARTUP_TRACE")
    if not path:
        return
    t = time.time()
    line = (f"{t:.3f} {time.strftime('%H:%M:%S', time.localtime(t))}"
            f".{int(t * 1000) % 1000:03d} [pid {_os.getpid()} srv] {msg}")
    try:
        with open(path, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line, file=sys.stderr, flush=True)


class _LazyDataMod:
    """app.core.data, resolved on first attribute use: importing it here
    would put pandas on the server-import path, which delays the window
    opening. The first use rebinds the global `data_mod` to the module."""

    def __getattr__(self, name):
        from app.core import data as real
        globals()["data_mod"] = real
        return getattr(real, name)


data_mod = _LazyDataMod()

# === Forecast console state ===
# LEGACY names: "ensemble" is the blend retired 2026-09-22 and "amcmc" the
# sampler removed 2026-09-07; readers keep old rows/results, nothing writes them.
ENGINES = ("all", "pf", "analogue")  # "all" = pf + analogue
_status: dict = {"running": None, "log": []}
_last_form: dict = {}

#: ONE lock around every engine busy check and the claim it protects (routes
#: run on a threadpool; an unlocked check-then-claim let two submits both
#: start). Held for check+claim only, never while a run executes. Server-side
#: busy checks mirror /api/busy: the client guard is convenience only.
_engine_lock = threading.Lock()

#: set once the warm pass finished its outlook computation (success or not)
_WARM_DONE = __import__("threading").Event()

#: running: the live fit's run id; claim: the model whose run is being
#: prepared (the engine is booked from the claim on); cancel: Stop pressed
#: during preparation. Every change happens under _engine_lock.
_sandbox_status: dict = {"running": None, "claim": None, "cancel": False}
