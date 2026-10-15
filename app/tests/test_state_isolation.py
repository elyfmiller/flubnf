"""The suite's state folder reaches every Python a test starts: a
subprocess that imports the server (its startup thread writes
component_versions.json) or opens the ledger writes into the suite's temp
folder, never the checkout's app/state (conftest.py sets FLUBNF_STATE_DIR).
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_a_python_a_test_starts_keeps_its_state_out_of_the_checkout():
    code = ("import app.ui.server, app.ui.versions as v, app.core.runs as r; "
            "print(v._VERSIONS_SNAPSHOT.parent); print(r.APP_STATE)")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO,
                         env=dict(os.environ), capture_output=True,
                         text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    snap, state = out.stdout.strip().splitlines()[-2:]
    test_state = Path(os.environ["FLUBNF_STATE_DIR"])
    assert Path(snap) == Path(state) == test_state
    assert test_state != REPO / "app" / "state"


def test_without_the_override_the_state_folder_is_the_checkouts():
    env = {k: v for k, v in os.environ.items() if k != "FLUBNF_STATE_DIR"}
    out = subprocess.run([sys.executable, "-c",
                          "import app.core.runs as r; print(r.APP_STATE)"],
                         cwd=REPO, env=env, capture_output=True, text=True,
                         timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert Path(out.stdout.strip()) == REPO / "app" / "state"
