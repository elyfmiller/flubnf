"""Launch and supervise PyBNF runs.

This module is a thin process wrapper around the PyBNF CLI:

    pybnf -c <state>.conf

It exists so the UI / CLI have one place to launch jobs, capture exit codes,
stash stdout/stderr per run, and decide which states need to be rerun.

There are two execution modes:

  - `local_sequential`:  run one state at a time on the local machine. Slow
    but predictable; the right choice when each PyBNF run already uses many
    cores via `parallel_count` in the conf.
  - `local_parallel`:    fan out N states at a time as separate subprocesses.
    Useful with the upcoming in-process BNGsim engine where individual runs
    are short.

Both modes write a per-state log to `<workspace>/run_logs/<state>.log`.

The actual PyBNF binary path is read from `FluBNFConfig.pybnf_command`
(falls back to `pybnf` on PATH).
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import FluBNFConfig
from .paths import WorkspacePaths

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunResult:
    state: str
    conf: Path
    log: Path
    returncode: int
    seconds: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_one(
    state: str,
    paths: WorkspacePaths,
    config: FluBNFConfig,
    *,
    pybnf_command: str = "pybnf",
    extra_args: Iterable[str] = (),
) -> RunResult:
    """Run PyBNF for a single state. Blocks until the run finishes."""
    conf_path = paths.conf_file(state)
    if not conf_path.exists():
        raise FileNotFoundError(f"conf file missing: {conf_path}")
    log_dir = paths.root / "run_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{state}.log"

    cmd = [pybnf_command, "-c", str(conf_path), *extra_args]
    log.info("launching: %s", " ".join(cmd))
    t0 = time.time()
    with open(log_path, "w") as f:
        f.write(f"$ {' '.join(cmd)}\n")
        f.flush()
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT,
                              cwd=paths.root)
    return RunResult(
        state=state, conf=conf_path, log=log_path,
        returncode=proc.returncode, seconds=time.time() - t0,
    )


def run_many(
    states: Iterable[str],
    paths: WorkspacePaths,
    config: FluBNFConfig,
    *,
    parallel: int = 1,
    pybnf_command: str = "pybnf",
) -> list[RunResult]:
    """Run PyBNF for many states. Use `parallel=1` for sequential, > 1 to
    fan out concurrent subprocesses."""
    states = list(states)
    if parallel <= 1:
        return [run_one(s, paths, config, pybnf_command=pybnf_command)
                for s in states]
    results: list[RunResult] = []
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = {
            pool.submit(run_one, s, paths, config, pybnf_command=pybnf_command): s
            for s in states
        }
        for fut in as_completed(futures):
            results.append(fut.result())
    # Preserve input ordering for predictable downstream consumption.
    by_state = {r.state: r for r in results}
    return [by_state[s] for s in states if s in by_state]


def needs_rerun(
    state: str, paths: WorkspacePaths, *, max_age_hours: float = 1e9,
) -> bool:
    """Trivial freshness check: returns True when no `sorted_params_final.txt`
    exists, or when the file is older than `max_age_hours`. The orchestrator
    uses this to skip states that already have a fresh fit."""
    final = paths.results_for(state) / "Results" / "sorted_params_final.txt"
    if not final.exists():
        return True
    age_h = (time.time() - final.stat().st_mtime) / 3600.0
    return age_h > max_age_hours
