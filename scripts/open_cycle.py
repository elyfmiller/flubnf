"""Manual launch-cycle harness for the REAL windowed app (GUI machine only).

Launches `.venv/bin/flubnf app` the way FluBNF.command does, with the
startup trace enabled (FLUBNF_STARTUP_TRACE), waits for the load watchdog's
verdict, closes the app, and repeats. Prints one row per cycle:

    cycle  result     window_s  loaded_s  notes

where window_s is command-entry to window-shown and loaded_s is
command-entry to the page's loaded event (the "usable" moment). A cycle
whose watchdog reports FAILED, or that never reports, is a failure.

Usage (from the repo root):
    .venv/bin/python scripts/open_cycle.py            # 10 warm cycles
    .venv/bin/python scripts/open_cycle.py --cycles 3
    .venv/bin/python scripts/open_cycle.py --cold     # purge snapshot +
                                                      # repo bytecode first

This is a manual diagnostic, not a CI test: it opens real windows on the
current GUI session and needs pywebview. It always removes the app pidfile
when it finishes.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PIDFILE = REPO / "app" / "state" / "app.pid"
SNAPSHOT = REPO / "app" / "state" / "component_versions.json"

_STAMP = re.compile(r"^(\d+\.\d+) ")

RESULTS = ("watchdog: loaded within first wait",
           "watchdog: recovered after reload",
           "watchdog: FAILED, showing failure page")


def purge_cold() -> None:
    """Approximate a cold launch without root: drop the versions snapshot
    (first-ever-launch shape) and the repo's own bytecode caches. OS page
    cache for site-packages cannot be purged without sudo; the sequence
    log still shows the ordering, which is the diagnosis."""
    SNAPSHOT.unlink(missing_ok=True)
    for base in (REPO / "flubnf", REPO / "app"):
        for pyc in base.rglob("__pycache__"):
            shutil.rmtree(pyc, ignore_errors=True)
    print("cold: snapshot and repo bytecode purged")


def stamp_of(line: str) -> float:
    m = _STAMP.match(line)
    return float(m.group(1)) if m else 0.0


def one_cycle(idx: int, log: Path, settle: float, timeout: float) -> dict:
    log.unlink(missing_ok=True)
    env = dict(os.environ, FLUBNF_STARTUP_TRACE=str(log))
    proc = subprocess.Popen([str(REPO / ".venv" / "bin" / "flubnf"), "app"],
                            cwd=str(REPO), env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    verdict, lines = "no-verdict", []
    t_start = time.time()
    while time.time() - t_start < timeout:
        if log.is_file():
            lines = log.read_text().splitlines()
            hit = [l for l in lines if any(r in l for r in RESULTS)]
            if hit:
                verdict = ("loaded" if "first wait" in hit[0]
                           else "recovered" if "recovered" in hit[0]
                           else "FAILED")
                break
        if proc.poll() is not None:
            verdict = f"exited({proc.returncode})"
            break
        time.sleep(0.2)
    time.sleep(settle)          # let the warm thread lines land in the log
    if log.is_file():
        lines = log.read_text().splitlines()

    def when(needle: str) -> float:
        for l in lines:
            if needle in l:
                return stamp_of(l)
        return 0.0

    t0 = when("app: command entered")
    row = {"cycle": idx, "result": verdict,
           "window_s": round(when("start callback fired") - t0, 2)
           if t0 and when("start callback fired") else None,
           "loaded_s": round(when("watchdog: loaded event fired") - t0, 2)
           if t0 and when("watchdog: loaded event fired") else None,
           "lines": lines}
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(5)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=10)
    ap.add_argument("--cold", action="store_true",
                    help="purge snapshot + repo bytecode before cycle 1")
    ap.add_argument("--settle", type=float, default=3.0,
                    help="seconds to keep the app open after the verdict")
    ap.add_argument("--timeout", type=float, default=45.0)
    ap.add_argument("--verbose", action="store_true",
                    help="print the full trace of every cycle")
    args = ap.parse_args()
    if args.cold:
        purge_cold()
    log = REPO / "app" / "state" / "open_cycle_trace.log"
    rows, failures = [], 0
    try:
        for i in range(1, args.cycles + 1):
            row = one_cycle(i, log, args.settle, args.timeout)
            rows.append(row)
            ok = row["result"] in ("loaded", "recovered")
            failures += 0 if ok else 1
            print(f"cycle {row['cycle']:2d}  {row['result']:<12} "
                  f"window {row['window_s'] if row['window_s'] is not None else '?':>5}s  "
                  f"loaded {row['loaded_s'] if row['loaded_s'] is not None else '?':>5}s")
            if args.verbose or not ok:
                for l in row["lines"]:
                    print("    " + l)
            time.sleep(1.0)
    finally:
        PIDFILE.unlink(missing_ok=True)
    print(f"\n{len(rows) - failures}/{len(rows)} cycles succeeded")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
