"""The FluSurv-NET donor bank: offline tests against a recorded fixture.

The fixture holds a REAL Delphi flusurv response for three sites over the
2017-18 season, in the module's own cache-file format. Every test points the
cache at a tmp dir seeded from it and turns the HTTP layer into an error, so
no test touches the network.
"""
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flubnf import analogue as AN, flusurv                # noqa: E402

FIXTURE = json.loads((Path(__file__).parent / "flusurv_fixture.json").read_text())


@pytest.fixture()
def cache(tmp_path, monkeypatch):
    (tmp_path / "snapshot.json").write_text(json.dumps(FIXTURE))
    (tmp_path / "locations.json").write_text(json.dumps(["ca", "co", "mn"]))

    def _no_network(url, timeout=None):
        raise AssertionError(f"offline test attempted network fetch: {url}")

    monkeypatch.setattr(flusurv, "_http_json", _no_network)
    monkeypatch.setattr(flusurv, "CACHE_DIR", tmp_path)
    return tmp_path


def test_build_url_uses_locations_not_regions():
    """flusurv takes `locations`; fluview and fluview_clinical take
    `regions`. Getting it wrong returns an EMPTY result rather than an
    error, which is exactly the silence a donor pool must never absorb."""
    u = flusurv.build_url(["ca", "co"], 201740, 201820)
    assert u.startswith("https://api.delphi.cmu.edu/epidata/flusurv/?")
    assert "locations=ca%2Cco" in u
    assert "regions=" not in u
    assert "epiweeks=201740-201820" in u


def test_build_bank_shape_and_keys(cache):
    bank = flusurv.build_bank(201740)
    assert bank
    for (site, d), v in bank.items():
        assert site in ("ca", "co", "mn")
        assert isinstance(d, date) and v > 0
    # the keys are exactly the shape donor_ratios reads
    r = AN.donor_ratios(bank, 5, 9999, 1, exclude_seasons=())
    assert r.size > 0


def test_dates_are_the_epiweek_saturdays(cache):
    bank = flusurv.build_bank(201740)
    for (_, d) in bank:
        assert d.weekday() == 5                      # Saturday
    # and the analogue's own epiweek agrees with the key it was built from
    from flubnf.nrevss import mmwr_week
    for (_, d) in bank:
        assert AN.epiweek(d) == mmwr_week(d)[1]


def test_no_vintage_argument_exists():
    """The endpoint carries no revision history, so offering an as-of would
    be a lie in the signature. This pins that it is not there."""
    import inspect
    params = inspect.signature(flusurv.build_bank).parameters
    assert "asof" not in params and "issue" not in params
    assert "vintage" not in params


def test_catchment_is_read_from_cache(cache):
    assert flusurv.catchment() == ["ca", "co", "mn"]


def test_a_site_outside_the_cache_is_not_invented(cache):
    """The cached snapshot covers three sites. Asking for a fourth must go
    to the network rather than silently returning a short bank."""
    with pytest.raises(AssertionError, match="attempted network fetch"):
        flusurv.build_bank(201740, locations=["ca", "co", "mn", "ny_albany"])


def test_an_empty_bank_raises(cache, tmp_path):
    empty = dict(FIXTURE)
    empty["response"] = {"result": 1, "epidata": []}
    (tmp_path / "snapshot.json").write_text(json.dumps(empty))
    with pytest.raises(ValueError, match="empty"):
        flusurv.build_bank(201740)


def test_write_bank_round_trips_through_the_engine_loader(cache, tmp_path):
    from app.core.engines.analogue import load_aux_bank
    bank = flusurv.build_bank(201740)
    out = flusurv.write_bank(bank, tmp_path / "fs.json")
    assert load_aux_bank(str(out)) == bank


# ---------------------------------------------------------------------------
# Engine wiring
# ---------------------------------------------------------------------------

def test_engine_builds_a_flusurv_pool(cache, tmp_path):
    from app.core.engines.analogue import splice_args
    spec = SimpleNamespace(forecast_date="2025-12-20", extra={"aux_pools": [{
        "stream": "flusurv", "weight": 0.5, "shrink": None,
        "build": {"first_epiweek": 201740, "locations": ["ca", "co", "mn"],
                  "cache_dir": str(tmp_path)}}]})
    sp = splice_args(spec, {})
    assert len(sp.pools) == 1
    assert sp.pools[0].label == "flusurv"
    assert sp.primary_weight == 0.5


def test_engine_refuses_a_vintage_request_for_flusurv(cache, tmp_path):
    """Silently ignoring it would let a run claim a vintage discipline the
    data cannot support."""
    from app.core.engines.analogue import splice_args
    spec = SimpleNamespace(forecast_date="2025-12-20", extra={"aux_pools": [{
        "stream": "flusurv", "weight": 0.5,
        "build": {"vintage": True, "cache_dir": str(tmp_path)}}]})
    with pytest.raises(ValueError, match="no vintage option"):
        splice_args(spec, {})
