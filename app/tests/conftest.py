"""Suite-wide guards for the app tests.

Two rules, both of the same kind: no test may touch, or depend on, the
developer's real install.

  * The PF engine's takeover registry (the record of live runner process
    groups that a console relaunch may sweep) lives beside the app's real
    state, app/state/pf_runners.json. No test may write there -- the file
    is read by a REAL relaunch, and a test's fake runner pids landing in it
    could aim a sweep at recycled pids on the developer's machine -- so
    every test records into its own temporary file instead.

  * prepare() refuses to write a fit_type = pf configuration when the fork
    path holds no pybnf/pf.py (app/core/engines/pf.py::engine_available).
    Every test that calls it would otherwise pass on the development host,
    which has the fork, and fail in CI, which does not. So the fork is
    faked here for the whole suite; a test about the preflight itself
    points PYBNF_PF at its own directory and wins, being later.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core.engines import pf                          # noqa: E402


@pytest.fixture(autouse=True)
def _runner_registry_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "RUNNER_PIDS_FILE", tmp_path / "pf_runners.json")


@pytest.fixture(scope="session")
def _engine_root(tmp_path_factory):
    """A fork-shaped directory: the one file the engine preflight looks
    for, built once for the session."""
    root = tmp_path_factory.mktemp("fork")
    (root / "pybnf").mkdir()
    (root / "pybnf" / "pf.py").write_text("# stub: presence is the test\n")
    return root


@pytest.fixture(autouse=True)
def _engine_in_tmp(_engine_root, monkeypatch):
    monkeypatch.setattr(pf, "PYBNF_PF", _engine_root)
