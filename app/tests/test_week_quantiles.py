"""The per-week quantile sidecar: written when a week is stored, recomputed
when missing or older than the samples, kept by the pruner, and read by
playback and the season scorer instead of the 140 MB samples parse."""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np                                       # noqa: E402

from app.core import horizons as hz                      # noqa: E402
from app.core import reclaim, retro, playback            # noqa: E402

W = "2098-01-03"


def _payload(asof=W, seed=0):
    """One week's record in CANONICAL horizons ("0".."3", no anchor); medians
    encode the physical week (51..54) so horizons stay distinguishable."""
    rng = np.random.default_rng(seed)
    return {"asof": asof,
            "pf": {"Ohio": {h: rng.gamma(4.0, 25.0, 300).tolist() for h in hz.HORIZONS}},
            "analogue": {"Ohio": {h: {"0.025": 10.0, "0.5": 51.0 + int(h), "0.975": 120.0} for h in hz.HORIZONS},
                         "Utah": {h: {"0.025": 1.0, "0.5": 5.0, "0.975": 12.0} for h in hz.HORIZONS}}}


def _root(tmp_path, payload, plain=False):
    root = tmp_path / "2098-99"; wd = root / "weeks" / payload["asof"]; wd.mkdir(parents=True)
    if plain:
        # a pre-write_week_samples week: STORED convention on disk,
        # translated here as the storage boundary would
        (wd / retro.SAMPLES_JSON).write_text(json.dumps(hz.record_to_stored(payload)))
    else:
        retro.write_week_samples(wd, payload)
    return root, wd


def test_storing_a_week_writes_the_sidecar_and_it_reads_back_exactly(tmp_path):
    p = _payload()
    root, wd = _root(tmp_path, p)
    assert (wd / retro.QUANTILES_NAME).is_file()
    back = retro.read_week_quantiles(wd)
    ref = retro.member_quantiles(p)
    assert back == ref                              # floats round-trip through repr
    assert set(back) == {"pf", "analogue"} and "ensemble" not in back
    assert all(isinstance(L, float) for L in back["pf"]["Ohio"]["1"])
    assert len(back["pf"]["Ohio"]["1"]) == 23


def test_a_week_stored_without_a_sidecar_gets_one_on_first_read(tmp_path):
    p = _payload()
    root, wd = _root(tmp_path, p, plain=True)
    assert not (wd / retro.QUANTILES_NAME).is_file()
    mq = retro.week_member_quantiles(root, W)
    assert mq == retro.member_quantiles(p)
    assert (wd / retro.QUANTILES_NAME).is_file()    # written for next time


def test_a_stale_sidecar_is_recomputed_from_newer_samples(tmp_path):
    p = _payload(seed=1)
    root, wd = _root(tmp_path, p)
    fresh = retro.read_week_quantiles(wd)
    # the samples change after the sidecar: the sidecar must lose
    time.sleep(0.02)
    p2 = _payload(seed=2)
    (wd / retro.SAMPLES_GZ).unlink()
    (wd / retro.SAMPLES_JSON).write_text(json.dumps(hz.record_to_stored(p2)))
    future = time.time() + 5
    os.utime(wd / retro.SAMPLES_JSON, (future, future))
    assert retro.read_week_quantiles(wd) is None
    mq = retro.week_member_quantiles(root, W)
    assert mq == retro.member_quantiles(p2) and mq != fresh


def test_the_pruner_keeps_the_sidecar(tmp_path):
    root, wd = _root(tmp_path, _payload())
    (wd / "Ohio_r0").mkdir(); (wd / "Ohio_r0" / "big.txt").write_text("x" * 100)
    reclaim.prune_week(wd)
    assert not (wd / "Ohio_r0").exists()
    assert (wd / retro.QUANTILES_NAME).is_file() and (wd / retro.SAMPLES_GZ).is_file()


def test_playback_members_come_from_the_sidecar_and_match_the_formula(tmp_path):
    p = _payload(seed=3)
    root, wd = _root(tmp_path, p)
    q = playback._week_model_quantiles(root, W)
    assert q["pf"]["Ohio"] == playback._member_q(p["pf"]["Ohio"])
    assert q["analogue"]["Utah"]["1"][0.5] == 5.0
    assert "ensemble" not in q                  # nothing blended (2026-09-22)
    # the samples are not needed once the sidecar exists
    (wd / retro.SAMPLES_GZ).rename(wd / "samples.json.gz.away")
    (wd / retro.SAMPLES_GZ).write_text("")          # present for samples_file, unreadable
    os.utime(wd / retro.QUANTILES_NAME, None)
    assert playback._week_model_quantiles(root, W)["pf"]["Ohio"] == q["pf"]["Ohio"]
