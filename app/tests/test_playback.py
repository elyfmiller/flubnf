"""Playback payload: structure from a synthetic mini season root, the
official-comparator join (reference_date = asof + 7, US label), stats
sourcing (scores.json vs on-the-fly), caching, and a real-file spot check
guarded by hub presence."""
import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import playback                            # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL    # noqa: E402

ASOF = "2026-01-03"
SEASON = "2025-26"
N2F = {"Ohio": "39", "Utah": "49"}
OFFICIAL_HEADER = ("reference_date,horizon,target,target_end_date,"
                   "location,output_type,output_type_id,value")


def _truth():
    """(fips, week-ending Timestamp) -> value; positive everywhere."""
    t = {}
    for fips, base in (("39", 100.0), ("49", 50.0), ("US", 1000.0)):
        for k in range(-8, 6):
            d = pd.Timestamp(ASOF) + pd.Timedelta(days=7 * k)
            t[(fips, d)] = base + k
    return t, dict(N2F)


def _q23(center, spread=10.0):
    return {str(L): center + (L - 0.5) * spread for L in QL}


def _write_official(hub, om, asof=ASOF):
    """One synthetic submitted hub file for an official model."""
    ref = (pd.Timestamp(asof) + pd.Timedelta(days=7)).date().isoformat()
    rows = [OFFICIAL_HEADER]
    for fips, base in (("39", 100.0), ("US", 1000.0)):
        for h in (-1, 0, 1):              # -1 must be dropped by the parser
            actual = base + h + 1
            ted = (pd.Timestamp(ref) + pd.Timedelta(days=7 * h)).date()
            for L in QL:
                rows.append(f"{ref},{h},wk inc flu hosp,{ted},{fips},"
                            f"quantile,{L},{actual + (L - 0.5) * 20}")
    d = hub / "model-output" / om
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{ref}-{om}.csv").write_text("\n".join(rows) + "\n")


def _mk_root(tmp_path, monkeypatch, with_pf2s=True, official_models=("FluSight-baseline",)):
    """A one-week synthetic season root plus a synthetic hub; truth and the
    baseline denominator are monkeypatched so no real data is touched."""
    truth, n2f = _truth()
    monkeypatch.setattr(playback, "load_truth", lambda: (truth, n2f))
    monkeypatch.setattr(playback, "_baseline_cells",
                        lambda asof, fips_set, tr: {(f, asof, h): 2.0
                                                    for f in fips_set
                                                    for h in range(4)})
    hub = tmp_path / "hub"
    monkeypatch.setattr(playback, "HUB", hub)
    for om in official_models:
        _write_official(hub, om)

    root = tmp_path / "seasonroot"
    wd = root / "weeks" / ASOF
    wd.mkdir(parents=True)
    pf, pf2s, an = {}, {}, {}
    for loc, fips in N2F.items():
        pf[loc] = {str(h): [truth[(fips, pd.Timestamp(ASOF)
                                   + pd.Timedelta(days=7 * h))] + d
                            for d in (-1.0, 0.0, 1.0)] for h in range(5)}
        pf2s[loc] = {h: [v + 2.0 for v in s] for h, s in pf[loc].items()}
        an[loc] = {str(h): _q23(truth[(fips, pd.Timestamp(ASOF)
                                       + pd.Timedelta(days=7 * h))] + 4.0)
                   for h in range(1, 5)}
    d = {"asof": ASOF, "pf": pf, "analogue": an}
    if with_pf2s:
        d["pf2s"] = pf2s
    (wd / "samples.json").write_text(json.dumps(d))
    return root


# ----------------------------------------------------------------- structure

def test_payload_structure_members_official_truth_stats(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    p = playback.build_week(root, SEASON, ASOF)
    assert set(p) == {"_v", "asof", "locations", "truth", "models", "official",
                      "stats"}
    assert p["asof"] == ASOF
    assert p["locations"] == ["Ohio", "Utah"]

    # members: sample-shaped converted, analogue as-is, pf2s included
    assert set(p["models"]) == {"pf", "pf2s", "analogue", "ensemble"}
    oh = p["models"]["pf"]["Ohio"]
    assert set(oh) == {"1", "2", "3", "4"}          # horizon 0 not served
    assert set(oh["1"]) == {str(float(L)) for L in QL}
    assert oh["1"]["0.5"] == pytest.approx(101.0)   # truth base 100, k=1
    # ensemble = equal-weight blend: medians 101 (pf), 103 (pf2s), 105 (an)
    assert p["models"]["ensemble"]["Ohio"]["1"]["0.5"] == pytest.approx(103.0)

    # truth: full-season settled series, US always included (the player
    # offers a US view in every week)
    assert set(p["truth"]) == {"Ohio", "Utah", "US"}
    dates = [d for d, _ in p["truth"]["Ohio"]]
    assert dates == sorted(dates) and len(dates) == 14
    assert p["truth"]["Ohio"][-1][1] == pytest.approx(105.0)

    # official: the join (hub horizon 0 -> our "1"), US labeled, missing
    # FluSight-ensemble file omitted entirely
    assert set(p["official"]) == {"FluSight-baseline"}
    ob = p["official"]["FluSight-baseline"]
    assert set(ob) == {"Ohio", "US"}
    assert set(ob["Ohio"]) == {"1", "2"}            # h -1 dropped, 0/1 kept
    assert ob["Ohio"]["1"]["0.5"] == pytest.approx(101.0)
    assert ob["US"]["1"]["0.5"] == pytest.approx(1001.0)

    # stats: every member plus covered officials; single week => cum == week
    assert set(p["stats"]) == {"pf", "pf2s", "analogue", "ensemble",
                               "FluSight-baseline"}
    for m, s in p["stats"].items():
        assert s["week_rel"] is not None and s["week_rel"] > 0
        assert s["cum_rel"] == pytest.approx(s["week_rel"])


def test_vectorized_member_quantiles_match_reference():
    """playback._member_q is a speed rewrite of ens.member_quantiles_from_
    samples (one np.quantile call per horizon, not 23); the two must stay
    bit-identical or the served fans drift from the scored ones."""
    import numpy as np
    from app.core import ensemble as ens
    rng = np.random.default_rng(7)
    s = {h: rng.gamma(2.0, 40.0, 999).tolist() for h in ("1", "2", "3", "4")}
    s["2"][0] = float("nan")                     # finite-filter path too
    s["4"] = []                                  # empty horizon dropped
    assert playback._member_q(s) == ens.member_quantiles_from_samples(s)


def test_unknown_week_raises(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    with pytest.raises(playback.UnknownWeek):
        playback.build_week(root, SEASON, "1900-01-01")


# ------------------------------------------------------------------- caching

def test_cache_written_served_and_invalidated(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    playback.build_week(root, SEASON, ASOF)
    cf = root / "playback_cache" / f"{ASOF}.json"
    assert cf.is_file()
    # fresh cache is served verbatim (the sentinel carries the full validity
    # shape: both officials present and the always-present US truth key)
    cf.write_text(json.dumps({"_v": playback.CACHE_V, "asof": "sentinel",
                              "models": {}, "truth": {"US": []},
                              "official": {"FluSight-baseline": {},
                                           "FluSight-ensemble": {}}}))
    future = cf.stat().st_mtime + 60
    os.utime(cf, (future, future))
    assert playback.build_week(root, SEASON, ASOF)["asof"] == "sentinel"
    # newer samples.json invalidates it
    sp = root / "weeks" / ASOF / "samples.json"
    os.utime(sp, (future + 60, future + 60))
    assert playback.build_week(root, SEASON, ASOF)["asof"] == ASOF


# ------------------------------------------------------------ stats sourcing

def test_stats_prefer_scores_json_for_covered_models(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    pd.DataFrame([
        {"model": "pf", "location": "Ohio", "asof": ASOF,
         "horizon": 0, "wis": 4.0, "base_wis": 2.0},
        {"model": "pf", "location": "Ohio", "asof": "2025-12-27",
         "horizon": 0, "wis": 2.0, "base_wis": 2.0},
    ]).to_json(root / "scores.json")
    p = playback.build_week(root, SEASON, ASOF)
    # covered model: week from this asof's rows, cum through asof
    assert p["stats"]["pf"]["week_rel"] == pytest.approx(2.0)
    assert p["stats"]["pf"]["cum_rel"] == pytest.approx(1.5)
    # uncovered models still get on-the-fly stats
    assert p["stats"]["analogue"]["week_rel"] is not None
    assert p["stats"]["FluSight-baseline"]["week_rel"] is not None


# ---------------------------------------------------- stats cache staleness

def test_stats_cache_refreshes_when_scores_json_arrives(tmp_path, monkeypatch):
    """The field case: scoring succeeded AFTER the caches were built. The
    stats cache checked sample mtimes only, so the late scores.json never
    propagated and relWIS stayed pending forever."""
    root = _mk_root(tmp_path, monkeypatch)
    p1 = playback.build_week(root, SEASON, ASOF)     # no scores.json yet
    assert p1["stats"]["pf"]["week_rel"] is not None  # on-the-fly, cached
    sf = root / "scores.json"
    pd.DataFrame([
        {"model": "pf", "location": "Ohio", "asof": ASOF,
         "horizon": 0, "wis": 4.0, "base_wis": 2.0},
    ]).to_json(sf)
    p2 = playback.build_week(root, SEASON, ASOF)
    # stats now come from scores.json (wis/base = 4/2), not the stale cache
    assert p2["stats"]["pf"]["week_rel"] == pytest.approx(2.0)
    assert p2["stats"]["pf"]["cum_rel"] == pytest.approx(2.0)
    # and the cache entry was revalidated against the new scores.json
    cells = json.loads((root / "playback_cache"
                        / "stats_cells.json").read_text())
    assert cells["weeks"][ASOF]["scores_mtime"] == sf.stat().st_mtime


def test_stats_cache_gains_late_official_files(tmp_path, monkeypatch):
    """Update data healing the sparse hub clone changes no samples mtime;
    the official-file existence set must be part of the cache validity or
    the comparators never join the stats."""
    root = _mk_root(tmp_path, monkeypatch, official_models=())
    p1 = playback.build_week(root, SEASON, ASOF)
    assert "FluSight-baseline" not in p1["stats"]
    _write_official(tmp_path / "hub", "FluSight-baseline")
    p2 = playback.build_week(root, SEASON, ASOF)
    assert "FluSight-baseline" in p2["official"]
    st = p2["stats"]["FluSight-baseline"]
    assert st["week_rel"] is not None and st["cum_rel"] is not None


def test_us_truth_present_without_officials(tmp_path, monkeypatch):
    """A week with no official submission still carries the US truth
    series: the player's location list offers US in every week, and gating
    the national truth on official presence made those frames render as
    bare empty axes (field-found on the 2025-26 season player, weeks
    outside the officials' competition window)."""
    root = _mk_root(tmp_path, monkeypatch, official_models=())
    p = playback.build_week(root, SEASON, ASOF)
    assert p["official"] == {}
    assert "US" in p["truth"]
    assert p["truth"]["US"], "the settled national series must be served"
    assert p["truth"]["US"][-1][1] == pytest.approx(1005.0)


def test_cached_payload_without_us_truth_upgrades(tmp_path, monkeypatch):
    """A payload cached before US truth rode along unconditionally rebuilds
    on first serve, the same lazy-heal rule as late official files."""
    root = _mk_root(tmp_path, monkeypatch, official_models=())
    playback.build_week(root, SEASON, ASOF)
    cf = root / "playback_cache" / f"{ASOF}.json"
    stale = json.loads(cf.read_text())
    del stale["truth"]["US"]                      # the pre-fix cache shape
    cf.write_text(json.dumps(stale))
    future = cf.stat().st_mtime + 60
    os.utime(cf, (future, future))                # fresh by mtime alone
    p = playback.build_week(root, SEASON, ASOF)
    assert "US" in p["truth"]


def test_season_official_catalog(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)           # baseline only
    assert playback.season_official_catalog(root) == ["FluSight-baseline"]


def test_season_official_catalog_empty_hub(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch, official_models=())
    assert playback.season_official_catalog(root) == []


# ---------------------------------------------------------------- route + real

def test_route_unknown_week_is_plain_404():
    from fastapi.testclient import TestClient
    from app.ui.server import app as srv
    r = TestClient(srv).get("/api/retro/2024-25/playback/1900-01-01")
    assert r.status_code == 404
    assert "1900-01-01" in r.text


def test_mapswap_route_refuses_unknown_and_unsafe_weeks():
    """The map swap payload endpoint (the per-frame map path since
    2026-08-22): an unknown week is a plain 404, and a week that is not
    date-shaped never reaches the filesystem as a path segment."""
    from fastapi.testclient import TestClient
    from app.ui.server import app as srv
    c = TestClient(srv)
    assert c.get("/api/retro/2024-25/mapswap/1900-01-01").status_code == 404
    assert c.get("/api/retro/2024-25/mapswap/..%2F..%2Fpasswd").status_code == 404


from flubnf.settings import HUB as _HUB                  # noqa: E402

_SEAL = Path(__file__).resolve().parents[1] / "state" / "retro_seal" / "2024-25"
_real_ok = ((_SEAL / "weeks").is_dir()
            and (_HUB / "model-output" / "FluSight-baseline").is_dir()
            and (_HUB / "auxiliary-data" / "locations.csv").is_file())


@pytest.mark.skipif(not _real_ok, reason="seal root or hub files absent")
def test_real_first_seal_week_spot():
    weeks = playback.season_weeks(_SEAL)
    asof = weeks[0]
    p = playback.build_week(_SEAL, "2024-25", asof)
    assert p["asof"] == asof
    assert {"pf", "analogue", "ensemble"} <= set(p["models"])
    assert "FluSight-baseline" in p["official"]
    us = p["official"]["FluSight-baseline"].get("US")
    assert us and "1" in us and "0.5" in us["1"]
    assert p["stats"]["ensemble"]["cum_rel"] is not None
    # second call comes from the cache and agrees
    assert playback.build_week(_SEAL, "2024-25", asof)["asof"] == asof


@pytest.mark.skipif(not _real_ok, reason="seal root or hub files absent")
def test_real_mapswap_covers_every_state_shape():
    """The swap payload the player mutates fills from must state an entry
    for EVERY state path on the map (states without samples wear the
    no-data tone), each with fill, opacity, and hover, so a frame can
    never leave a stale fill from the previous week behind."""
    from fastapi.testclient import TestClient
    from app.core.usmap import state_paths
    from app.ui.server import app as srv
    asof = playback.season_weeks(_SEAL)[0]
    r = TestClient(srv).get(f"/api/retro/2024-25/mapswap/{asof}")
    assert r.status_code == 200
    states = r.json()["states"]
    assert set(states) == set(state_paths())
    for s in states.values():
        assert set(s) == {"f", "o", "h"}
