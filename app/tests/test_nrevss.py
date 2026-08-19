"""Vintage-true NREVSS layer: offline tests against a recorded fixture.

The fixture (nrevss_fixture.json, next to this file) holds two REAL
Delphi fluview_clinical responses recorded 2026-08-19 — Pennsylvania and
HHS region 3, epiweeks 202340-202401 as published at issue 202401 — in
the module's own cache-file format.  Every test points the cache at a
tmp dir seeded from the fixture and stubs the HTTP layer, so no test
ever touches the network.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flubnf import nrevss

FIXTURE = json.loads((Path(__file__).parent / "nrevss_fixture.json").read_text())
LOCATIONS = Path(__file__).resolve().parents[2] / "flubnf" / "data" / "locations.csv"

SEASON_START = "2023-10-01"          # epiweek 202340
ASOF = "2024-01-06"                  # Saturday ending epiweek 202401


@pytest.fixture()
def cache(tmp_path, monkeypatch):
    """Tmp cache seeded from the fixture; network calls become errors."""
    for key in ("pa_202401", "hhs3_202401"):
        (tmp_path / f"{key}.json").write_text(json.dumps(FIXTURE[key]))

    def _no_network(url, timeout=None):
        raise AssertionError(f"offline test attempted network fetch: {url}")

    monkeypatch.setattr(nrevss, "_http_json", _no_network)
    monkeypatch.setattr(nrevss, "CACHE_DIR", tmp_path)
    return tmp_path


def _reseed(cache, key, mutate):
    """Overwrite one cache entry with a mutated copy of a fixture entry."""
    blob = json.loads(json.dumps(FIXTURE[key]))  # deep copy
    mutate(blob)
    (cache / f"{blob['region']}_{blob['issue']}.json").write_text(json.dumps(blob))
    return blob


# ---------------------------------------------------------------------------
# 1. vintage query construction
# ---------------------------------------------------------------------------
def test_vintage_query_construction():
    url = nrevss.build_url("pa", 202340, 202401, 202401)
    assert url.startswith("https://api.delphi.cmu.edu/epidata/fluview_clinical/?")
    q = dict(p.split("=") for p in url.split("?", 1)[1].split("&"))
    assert q == {"regions": "pa", "epiweeks": "202340-202401", "issues": "202401"}


# ---------------------------------------------------------------------------
# 2. epiweek <-> date round-trips on known values
# ---------------------------------------------------------------------------
def test_epiweek_date_roundtrip_known_values():
    # Verified live against the API (release cadence + 202553's existence).
    known = {
        (2023, 40): "2023-10-07",
        (2023, 51): "2023-12-23",
        (2024, 1): "2024-01-06",
        (2014, 53): "2015-01-03",   # 53-week MMWR year
        (2025, 53): "2026-01-03",   # 53-week MMWR year (in the API)
        (2026, 1): "2026-01-10",
    }
    from datetime import date, timedelta
    for (y, w), sat in known.items():
        assert nrevss.week_ending(y, w) == sat
        # every day of the MMWR week maps back to (y, w)
        end = date.fromisoformat(sat)
        for back in range(7):
            assert nrevss.mmwr_week(end - timedelta(days=back)) == (y, w)


def test_epiweek_matches_two_independent_references():
    """13 years of daily dates against (a) a brute-force majority-rule
    reference and (b) shifted isocalendar with its documented exception:
    in years whose Jan 4 is a Sunday (2015, 2026) the schemes' week-1
    anchors differ by one week — MMWR week = ISO week - 1, ISO week 1
    belonging to the old MMWR year as week 53."""
    from datetime import date, timedelta

    def ref_mmwr(d):  # Sunday-start; week owned by the year holding >=4 days
        def start_of(x):
            return x - timedelta(days=(x.weekday() + 1) % 7)

        def owner(s):
            ys = [(s + timedelta(k)).year for k in range(7)]
            return max(set(ys), key=ys.count)

        s = start_of(d)
        year, n = owner(s), 0
        while owner(s) == year:
            s -= timedelta(days=7)
            n += 1
        return year, n

    def iso_expect(d):
        iy, iw, _ = (d + timedelta(days=1)).isocalendar()
        if date(iy, 1, 4).weekday() == 6:  # Jan 4 Sunday: offset all year
            return (iy, iw - 1) if iw >= 2 else (iy - 1, 53)
        return (iy, iw)

    d = date(2013, 6, 1)
    while d < date(2026, 6, 1):
        m = nrevss.mmwr_week(d)
        assert m == ref_mmwr(d) == iso_expect(d), d
        d += timedelta(days=1)


# ---------------------------------------------------------------------------
# 3. as-of fetch from cache; missing weeks are absent, never imputed
# ---------------------------------------------------------------------------
def test_fetch_typed_from_cache_is_vintage_true(cache):
    df = nrevss.fetch_typed("pa", SEASON_START, ASOF)
    assert list(df.columns) == ["date", "total_a", "total_b", "total_specimens"]
    assert len(df) == 14
    assert df["date"].iloc[0] == "2023-10-07" and df["date"].iloc[-1] == "2024-01-06"
    row = df[df["date"] == "2023-12-23"].iloc[0]      # epiweek 202351 as-published
    assert (row["total_a"], row["total_b"]) == (293, 24)


def test_missing_week_is_absent_not_imputed(cache):
    _reseed(cache, "pa_202401", lambda b: b["response"]["epidata"].__setitem__(
        slice(None),
        [r for r in b["response"]["epidata"] if r["epiweek"] != 202350]))
    df = nrevss.fetch_typed("pa", SEASON_START, ASOF)
    assert len(df) == 13
    assert "2023-12-16" not in set(df["date"])        # the dropped week's Saturday
    assert {"2023-12-09", "2023-12-23"} <= set(df["date"])   # neighbors intact


def test_holiday_gap_falls_back_to_earlier_issue(cache):
    # asof in epiweek 202402, whose issue is a cached EMPTY response
    # (holiday publishing gap) -> fall back to issue 202401.
    (cache / "pa_202402.json").write_text(json.dumps({
        "region": "pa", "issue": 202402, "epiweeks": [202340, 202402],
        "response": {"result": -2, "message": "no results", "epidata": []},
    }))
    df = nrevss.fetch_typed("pa", SEASON_START, "2024-01-13")
    assert len(df) == 14                              # the issue-202401 snapshot
    assert "2024-01-13" not in set(df["date"])        # week 202402: absent, not imputed
    assert df["date"].iloc[-1] == "2024-01-06"


# ---------------------------------------------------------------------------
# 4. withheld-state fallback to the HHS region
# ---------------------------------------------------------------------------
def test_state_series_used_when_present(cache):
    df = nrevss.a_share_series("Pennsylvania", SEASON_START, ASOF,
                               locations_csv=LOCATIONS)
    assert set(df["source"]) == {"pa"} and df.attrs["source"] == "pa"
    assert len(df) == 14


def test_withheld_state_falls_back_to_hhs_region(cache):
    def zero_out(blob):
        for r in blob["response"]["epidata"]:
            r["total_specimens"] = 0
            r["total_a"] = 0
            r["total_b"] = 0
    _reseed(cache, "pa_202401", zero_out)             # PA "withholds" clinical data
    df = nrevss.a_share_series("Pennsylvania", SEASON_START, ASOF,
                               locations_csv=LOCATIONS)
    assert set(df["source"]) == {"hhs3"} and df.attrs["source"] == "hhs3"
    row = df[df["date"] == "2023-10-07"].iloc[0]      # real recorded hhs3 values
    assert (row["total_a"], row["total_b"]) == (21, 5)


# ---------------------------------------------------------------------------
# 5. a0_share threshold behavior
# ---------------------------------------------------------------------------
def test_a0_uses_first_week_reaching_threshold(cache):
    # Real PA vintage: first week with total_a+total_b >= 20 is epiweek
    # 202347 (a=22, b=3), NOT the season's first week -> 22/25.
    a0 = nrevss.a0_share("Pennsylvania", SEASON_START, ASOF,
                         locations_csv=LOCATIONS)
    assert a0 == pytest.approx(22 / 25)


def test_a0_threshold_boundary_and_default(cache):
    def thin(blob):  # every week just below threshold: typed = 19
        for r in blob["response"]["epidata"]:
            r["total_a"], r["total_b"] = 16, 3
    _reseed(cache, "pa_202401", thin)
    _reseed(cache, "hhs3_202401", thin)               # fallback also below threshold
    assert nrevss.a0_share("Pennsylvania", SEASON_START, ASOF,
                           locations_csv=LOCATIONS) == nrevss.DEFAULT_A_SHARE

    def exact(blob):  # exactly at threshold: typed = 20 counts
        for r in blob["response"]["epidata"]:
            r["total_a"], r["total_b"] = 15, 5
    _reseed(cache, "pa_202401", exact)
    assert nrevss.a0_share("Pennsylvania", SEASON_START, ASOF,
                           locations_csv=LOCATIONS) == pytest.approx(0.75)


def test_a0_clipped_into_open_interval(cache):
    def pure_a(blob):  # b = 0 everywhere -> raw share 1.0, must clip
        for r in blob["response"]["epidata"]:
            r["total_a"], r["total_b"] = 40, 0
    _reseed(cache, "pa_202401", pure_a)
    a0 = nrevss.a0_share("Pennsylvania", SEASON_START, ASOF,
                         locations_csv=LOCATIONS)
    assert 0.0 < a0 < 1.0 and a0 == 0.99


def test_a0_never_crashes(cache, tmp_path, monkeypatch):
    # Empty cache + dead network: a0_share still answers with the default.
    empty = tmp_path / "empty_cache"
    monkeypatch.setattr(nrevss, "CACHE_DIR", empty)

    def dead(url, timeout=None):
        raise RuntimeError("NREVSS fetch failed (network error ...)")

    monkeypatch.setattr(nrevss, "_http_json", dead)
    assert nrevss.a0_share("Pennsylvania", SEASON_START, ASOF,
                           locations_csv=LOCATIONS) == nrevss.DEFAULT_A_SHARE
    # but fetch_typed itself raises loudly on network failure
    with pytest.raises(RuntimeError, match="NREVSS fetch failed"):
        nrevss.fetch_typed("pa", SEASON_START, ASOF)
