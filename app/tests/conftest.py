"""Suite-wide guards for the app tests.

One rule so far: the PF engine's takeover registry (the record of live
runner process groups that a console relaunch may sweep) lives beside the
app's real state, app/state/pf_runners.json. No test may write there --
the file is read by a REAL relaunch, and a test's fake runner pids landing
in it could aim a sweep at recycled pids on the developer's machine -- so
every test records into its own temporary file instead.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core.engines import pf                          # noqa: E402


@pytest.fixture(autouse=True)
def _runner_registry_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "RUNNER_PIDS_FILE", tmp_path / "pf_runners.json")
