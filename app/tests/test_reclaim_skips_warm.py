"""Storage's reclaim leaves a season alone while its results job warms
the week map cards (app/ui/routes/storage.py _reclaim_skips).

The warm (app/ui/retro_prep.py _warm_map_cards) reads each stored week's
samples file after the job's 'done' event fires and until its 'warm'
event does. A reclaim then would compress a plain samples.json (writing
the .gz and removing the .json) or prune the week under it, so the season
is skipped, as it is mid-replay or mid-finalize, until the warm ends.

The storage world and its routing are test_reclaim.py's.
"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                    # noqa: E402

from app.tests import test_reclaim as _reclaim_tests         # noqa: E402
from app.ui import retro_prep as ui_retro_prep               # noqa: E402
from app.ui import server as srv                             # noqa: E402
from app.ui.routes import storage as ui_storage              # noqa: E402

client = TestClient(srv.app)

# test_reclaim's storage world, its routing and its names
world, routed = _reclaim_tests.world, _reclaim_tests.routed
SEASON, W1 = _reclaim_tests.SEASON, _reclaim_tests.W1


def _job(done: bool, warm) -> dict:
    """A results job record as _ensure_results_job makes it; warm None is
    a record from before the warm existed."""
    job = {"phase": "done", "done": threading.Event(), "error": "",
           "seconds": 1.0, "season": SEASON, "inputs": None,
           "warm": None if warm is None else threading.Event()}
    if done:
        job["done"].set()
    if warm:
        job["warm"].set()
    return job


def test_a_season_still_warming_its_map_cards_is_skipped(routed):
    root = routed["retro_root"] / SEASON
    ui_retro_prep._results_jobs[str(root)] = _job(done=True, warm=False)
    assert SEASON in ui_storage._reclaim_skips()[0]
    d = client.get("/api/storage/reclaim").json()
    client.post("/storage/reclaim", data={"confirm": d["confirm"]},
                follow_redirects=False)
    # the warm's season kept its plain samples and its intermediates
    wd = root / "weeks" / W1
    assert (wd / "samples.json").is_file()
    assert not (wd / "samples.json.gz").exists()
    assert (wd / "Ohio_r0").is_dir()


def test_the_season_is_reclaimed_once_the_warm_ends(routed):
    root = routed["retro_root"] / SEASON
    job = _job(done=True, warm=False)
    ui_retro_prep._results_jobs[str(root)] = job
    job["warm"].set()
    assert SEASON not in ui_storage._reclaim_skips()[0]
    d = client.get("/api/storage/reclaim").json()
    client.post("/storage/reclaim", data={"confirm": d["confirm"]},
                follow_redirects=False)
    wd = root / "weeks" / W1
    assert (wd / "samples.json.gz").is_file()
    assert not (wd / "Ohio_r0").exists()


def test_a_job_still_finalizing_and_an_old_record_without_a_warm(routed):
    root = routed["retro_root"] / SEASON
    ui_retro_prep._results_jobs[str(root)] = _job(done=False, warm=False)
    assert SEASON in ui_storage._reclaim_skips()[0]
    ui_retro_prep._results_jobs[str(root)] = _job(done=True, warm=None)
    assert SEASON not in ui_storage._reclaim_skips()[0]
    ui_retro_prep._results_jobs[str(root)] = None
    assert SEASON not in ui_storage._reclaim_skips()[0]
