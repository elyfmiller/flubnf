"""The ILI+ donor bank builder: offline tests against a recorded fixture.

The fixture (iliplus_fixture.json, next to this file) holds REAL Delphi
responses for California and Arizona, epiweeks 202340-202410, in the two
modules' own cache-file format: ILINet from ``fluview`` and clinical from
``fluview_clinical``. Every test points both caches at a tmp dir seeded
from the fixture and turns the HTTP layer into an error, so no test ever
touches the network. That matters twice over here: the CI contract has no
hub clone, and Delphi rate-limits bulk callers.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flubnf import iliplus, nrevss                       # noqa: E402

FIXTURE = json.loads((Path(__file__).parent / "iliplus_fixture.json").read_text())
SEASON_START = "2023-10-01"          # epiweek 202340
REGIONS = ["ca", "az"]


@pytest.fixture()
def caches(tmp_path, monkeypatch):
    """Both caches seeded from the fixture; any network call is an error."""
    ic, nc = tmp_path / "iliplus", tmp_path / "nrevss"
    ic.mkdir(); nc.mkdir()
    for reg in REGIONS:
        (ic / f"{reg}_latest.json").write_text(
            json.dumps(FIXTURE[f"ilinet_{reg}"]))
        (nc / f"{reg}_latest.json").write_text(
            json.dumps(FIXTURE[f"clinical_{reg}"]))

    def _no_network(url, timeout=None):
        raise AssertionError(f"offline test attempted network fetch: {url}")

    monkeypatch.setattr(iliplus, "_http_json", _no_network)
    monkeypatch.setattr(nrevss, "_http_json", _no_network)
    monkeypatch.setattr(iliplus, "CACHE_DIR", ic)
    monkeypatch.setattr(nrevss, "CACHE_DIR", nc)
    return ic, nc


# ---------------------------------------------------------------------------
# Pure pieces
# ---------------------------------------------------------------------------

def test_build_url_with_and_without_a_vintage():
    u = iliplus.build_url("ca", 202340, 202410, 202402)
    assert u.startswith("https://api.delphi.cmu.edu/epidata/fluview/?")
    assert "regions=ca" in u and "epiweeks=202340-202410" in u
    assert "issues=202402" in u
    # issue=None omits the parameter, which asks for the latest issue
    assert "issues" not in iliplus.build_url("ca", 202340, 202410, None)


def test_state_regions_excludes_us():
    regs = iliplus.state_regions()
    assert "us" not in regs and "nat" not in regs
    assert "ca" in regs and "ny" in regs
    assert regs == sorted(set(regs))


def test_the_two_mmwr_implementations_agree():
    """The bank is keyed by nrevss's week arithmetic but read by the
    analogue's. A disagreement would put donors in the wrong calendar bin."""
    from flubnf.analogue import epiweek
    from datetime import timedelta
    d, bad = date(2015, 1, 1), 0
    while d < date(2027, 1, 1):
        if epiweek(d) != nrevss.mmwr_week(d)[1]:
            bad += 1
        d += timedelta(days=1)
    assert bad == 0


# ---------------------------------------------------------------------------
# Fetch and cache
# ---------------------------------------------------------------------------

def test_fetch_ili_reads_the_cache_without_network(caches):
    df = iliplus.fetch_ili("ca", SEASON_START, None)
    assert not df.empty
    assert list(df.columns) == ["date", "ili"]
    assert (df["ili"] > 0).all()
    assert df["date"].is_monotonic_increasing
    assert df["date"].iloc[0] == "2023-10-07"      # Saturday ending 202340


def test_a_region_with_no_cache_and_no_network_is_an_error(caches):
    with pytest.raises(AssertionError, match="attempted network fetch"):
        iliplus.fetch_ili("tx", SEASON_START, None)


def test_warm_writes_a_file_per_region_including_empty_ones(tmp_path):
    """A region the response never mentions still gets a file. Without that
    an empty region is refetched forever."""
    env = {"result": 1, "epidata": [
        {"region": "ca", "epiweek": 202340, "ili": 2.0}]}
    import flubnf.iliplus as mod
    orig = mod._http_json
    mod._http_json = lambda url, timeout=None: env
    try:
        mod._warm("http://x", ["ca", "az"], None, 202340, 202410,
                  tmp_path, "latest")
    finally:
        mod._http_json = orig
    assert (tmp_path / "ca_latest.json").exists()
    assert (tmp_path / "az_latest.json").exists()
    az = json.loads((tmp_path / "az_latest.json").read_text())
    assert az["response"]["epidata"] == []


# ---------------------------------------------------------------------------
# The bank
# ---------------------------------------------------------------------------

def test_build_bank_shape_and_keys(caches):
    bank = iliplus.build_bank(SEASON_START, None, regions=REGIONS, pause_s=0)
    assert bank
    for (region, d), v in bank.items():
        assert region in REGIONS
        assert isinstance(d, date)
        assert v > 0
    # the keys are exactly the shape donor_ratios reads
    from flubnf import analogue as AN
    ratios = AN.donor_ratios(bank, AN.epiweek(date(2024, 12, 14)), 2024, 1,
                             exclude_seasons=())
    assert ratios.size >= 0            # runs without raising on this shape


def test_derived_and_reported_agree_except_at_low_positivity(caches):
    """Delphi rounds percent_positive to two decimals, which is 0.005
    absolute and therefore large in relative terms only when positivity is
    small. Anything else would mean the two modes disagree about the data,
    not about precision."""
    a = iliplus.build_bank(SEASON_START, None, regions=REGIONS, pause_s=0,
                           percent_positive="derived")
    b = iliplus.build_bank(SEASON_START, None, regions=REGIONS, pause_s=0,
                           percent_positive="reported")
    common = set(a) & set(b)
    assert len(common) > 20
    worst = max(abs(a[k] / b[k] - 1) for k in common if b[k] > 0)
    assert worst < 0.05            # in-season weeks: well under one percent


def test_percent_positive_mode_is_validated(caches):
    with pytest.raises(ValueError, match="derived.*reported"):
        iliplus.build_bank(SEASON_START, None, regions=REGIONS, pause_s=0,
                           percent_positive="rounded")


def test_min_specimens_drops_thin_weeks(caches):
    lo = iliplus.build_bank(SEASON_START, None, regions=REGIONS, pause_s=0,
                            min_specimens=1)
    hi = iliplus.build_bank(SEASON_START, None, regions=REGIONS, pause_s=0,
                            min_specimens=10_000_000)
    assert lo and not hi


def test_write_bank_round_trips_through_the_engine_loader(caches, tmp_path):
    """One writer, one reader: the format cannot drift between the thing
    that builds the bank and the thing that consumes it."""
    from app.core.engines.analogue import load_aux_bank
    bank = iliplus.build_bank(SEASON_START, None, regions=REGIONS, pause_s=0)
    out = iliplus.write_bank(bank, tmp_path / "bank.json")
    assert load_aux_bank(str(out)) == bank


# ---------------------------------------------------------------------------
# Engine wiring
# ---------------------------------------------------------------------------

def test_engine_builds_the_bank_from_spec_extra(caches, tmp_path):
    from app.core.engines.analogue import splice_args
    from flubnf import analogue as AN
    ic, nc = caches
    adm = {("01", date(2023, 11, 4) + timedelta(days=7 * i)):
           100.0 + i for i in range(60)}
    spec = SimpleNamespace(forecast_date="2024-12-14", extra={"iliplus": {
        "build": {"first_season": SEASON_START, "vintage": False,
                  "regions": REGIONS, "cache_dir": str(ic),
                  "nrevss_cache_dir": str(nc)},
        "shrink": None}})
    sp = splice_args(spec, adm)
    assert isinstance(sp, AN.DonorSplice)
    assert sp.bank and all(isinstance(k[1], date) for k in sp.bank)


def test_engine_refuses_an_empty_built_bank(caches, tmp_path):
    """A spliced run with an empty auxiliary pool is the single-pool forecast
    wearing a label that says otherwise."""
    from app.core.engines.analogue import splice_args
    ic, nc = caches
    spec = SimpleNamespace(forecast_date="2024-12-14", extra={"iliplus": {
        "build": {"first_season": SEASON_START, "vintage": False,
                  "regions": REGIONS, "cache_dir": str(ic),
                  "nrevss_cache_dir": str(nc), "min_specimens": 10_000_000},
        "shrink": None}})
    # min_specimens is not forwarded by the engine, so force emptiness the
    # way a caller actually could: a region list with nothing cached for it.
    spec.extra["iliplus"]["build"]["regions"] = []
    with pytest.raises(ValueError, match="empty"):
        splice_args(spec, {})


def test_engine_rejects_a_non_dict_build(caches):
    from app.core.engines.analogue import splice_args
    spec = SimpleNamespace(forecast_date="2024-12-14",
                           extra={"iliplus": {"build": ["nope"]}})
    with pytest.raises(ValueError, match="must be a dict"):
        splice_args(spec, {})
