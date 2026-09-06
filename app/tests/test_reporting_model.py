"""The declared reporting model (research/reporting-model): the real-time
pooled per-lag completeness factor, its leak-proof construction, and its
three wirings (the anchor, the likelihood column and engine key, the
analogue's lag-0 anchor).

Hub-free: the factor is built on an injected archive; prepare() runs on
the same fakes test_swarm_carry uses, with the factor stubbed."""
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np                                       # noqa: E402
import pandas as pd                                      # noqa: E402
import pytest                                            # noqa: E402

from app.core import completeness as comp                # noqa: E402
from app.core.engines import analogue as an_engine       # noqa: E402
from app.core.engines import pf                          # noqa: E402

START = pd.Timestamp("2098-08-01")
LOCS = ("01", "02", "03")
LAG_C = {0: 0.8, 1: 0.95}          # the archive's true completeness by lag


def _archive(n_vintages=12, lag_c=LAG_C, base=100.0, spy=None):
    """A synthetic archive: weekly vintages from START; week w's value in
    the vintage published lag weeks later is base(w, loc) times lag_c[lag]
    (1 for older lags). US rows carry nonsense and must be ignored."""
    dates = [str((START + pd.Timedelta(days=7 * i)).date()) for i in range(n_vintages)]

    def loader(date):
        if spy is not None:
            spy.append(date)
        d = pd.Timestamp(date)
        rows = []
        for i in range(n_vintages):
            w = START + pd.Timedelta(days=7 * i)
            if w > d:
                break
            lag = (d - w).days // 7
            for j, loc in enumerate(LOCS):
                rows.append((w, loc, base * (1 + 0.1 * j + 0.01 * i) * lag_c.get(lag, 1.0)))
            rows.append((w, "US", 1.0))
        return pd.DataFrame(rows, columns=["date", "location", "value"])
    return comp.Archive(dates=dates, loader=loader), dates


def test_factors_recover_the_archive_completeness_by_lag():
    arc, dates = _archive()
    out = comp.factors(dates[10], str(START.date()), arc, min_pairs=3)
    assert out["factors"] == {0: 0.8, 1: 0.95, 2: 1.0}
    # dates at least four weeks before the as-of: i = 0..6 (7 vintages);
    # lag 1 needs w >= start so i >= 1; lag 2 needs i >= 2
    assert out["pairs"] == {0: 7 * 3, 1: 6 * 3, 2: 5 * 3}
    assert out["raw"][2] == 1.0


def test_nothing_after_the_as_of_date_is_opened_and_later_vintages_cannot_leak():
    spy = []
    arc, dates = _archive(spy=spy)
    asof = dates[8]
    a = comp.factors(asof, str(START.date()), arc, min_pairs=3)
    assert all(pd.Timestamp(d) <= pd.Timestamp(asof) for d in spy)
    # a corrupted future: every vintage after the as-of reports garbage
    good_loader = arc._loader

    def poisoned(date):
        if pd.Timestamp(date) > pd.Timestamp(asof):
            df = good_loader(date)
            return df.assign(value=df["value"] * 0.01)
        return good_loader(date)
    arc2 = comp.Archive(dates=dates, loader=poisoned)
    assert comp.factors(asof, str(START.date()), arc2, min_pairs=3) == a


def test_too_few_pairs_and_the_clip():
    arc, dates = _archive()
    early = comp.factors(dates[2], str(START.date()), arc, min_pairs=3)
    assert early["factors"] == {0: 1.0, 1: 1.0, 2: 1.0}
    assert early["pairs"] == {0: 0, 1: 0, 2: 0} and early["raw"][0] is None
    full = comp.factors(dates[10], str(START.date()), arc)     # MIN_PAIRS = 30
    assert full["factors"][0] == 1.0 and full["pairs"][0] == 21
    arc3, dates3 = _archive(lag_c={0: 0.3, 1: 1.2})
    out = comp.factors(dates3[10], str(START.date()), arc3, min_pairs=3)
    assert out["factors"] == {0: 0.5, 1: 1.05, 2: 1.0}
    assert out["raw"][0] == pytest.approx(0.3)


def test_small_mature_values_are_excluded_from_the_pairs():
    arc, dates = _archive(base=5.0)                    # everything below 20
    out = comp.factors(dates[10], str(START.date()), arc, min_pairs=3)
    assert out["pairs"] == {0: 0, 1: 0, 2: 0}
    out = comp.factors(dates[10], str(START.date()), arc, min_pairs=3, min_value=1.0)
    assert out["factors"][0] == 0.8


def test_row_scales_follow_the_lag_from_the_as_of_week():
    fac = {"factors": {0: 0.8, 1: 0.95, 2: 1.0}}
    assert comp.row_scales([0, 1, 5, 6, 7], 7, fac) == [1.0, 1.0, 1.0, 0.95, 0.8]
    assert comp.row_scales([3, 5], 7, fac) == [1.0, 1.0]           # a gap: lags 4 and 2


# ------------------------------------------------------------ prepare() wiring

class _State:
    def __init__(self):
        self.times = np.array([0, 1, 2, 3])
        self.observed = np.array([30.0, 40.0, 50.0, 60.0])
        self.n_obs = 4
        self.last_week_offset = 3
        self.i0 = 5e-3
        self.rhomult = 0.05
        self.population = 1_000_000
        self.attack_rate = 0.1
        self.gamma = 7.0 / 3.2


def _spec(extra=None):
    return type("S", (), {
        "forecast_date": "2098-08-22", "season_start": "2098-08-01",
        "weeks_to_drop": 0, "drop_same_day": False,
        "locations": ["Ohio"], "replicates": 1,
        "particles": 100, "jitter": 0.15,
        "observable_mode": "integrated", "extra": extra})()


FAC = {"factors": {0: 0.8, 1: 0.95, 2: 1.0}, "pairs": {0: 40, 1: 40, 2: 40},
       "raw": {0: 0.8, 1: 0.95, 2: 1.0}}


def _env(monkeypatch, tmp_path):
    import app.core.data as data
    import flubnf.sihrs_fit as sf

    def fake_materialize(s, template, out_path, suffix, extra_tokens=None, **kw):
        p = Path(out_path)
        p.write_text("begin parameters\nend parameters\n")
        return p

    def fake_netgen(cmd, **kw):
        (Path(kw.get("cwd", ".")) / "m.net").write_text("# net\n")
        return types.SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(sf, "resolve_state", lambda loc, **kw: _State())
    monkeypatch.setattr(sf, "materialize_model", fake_materialize)
    monkeypatch.setattr(sf, "write_exp", lambda s, p: Path(p).write_text("# time H_weekly\nplain\n"))
    vfile = tmp_path / "vintage.csv"
    vfile.write_text("date,location,location_name,value\n")
    monkeypatch.setattr(data, "vintage_path", lambda d: str(vfile))
    monkeypatch.setattr(pf.subprocess, "run", fake_netgen)
    monkeypatch.setattr(comp, "factors_cached", lambda asof, start: FAC)


def _cell(monkeypatch, tmp_path, name, extra):
    return pf.prepare(_spec(extra), tmp_path / name)[0]


def test_anchor_mode_corrects_the_anchor_and_nothing_else(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    plain = _cell(monkeypatch, tmp_path, "plain", None)
    c = _cell(monkeypatch, tmp_path, "anchor", {"reporting": {"mode": "anchor"}})
    conf, exp = (Path(c["dir"]) / "pf.conf").read_text(), (Path(c["dir"]) / "Ohio_flu.exp").read_text()
    assert "pf_mean_scale_column" not in conf and exp == "# time H_weekly\nplain\n"
    assert c["reporting"]["mode"] == "anchor"
    assert c["reporting"]["factors"] == {"0": 0.8, "1": 0.95, "2": 1.0}
    assert c["reporting"]["row_scales"] == [1.0, 1.0, 0.95, 0.8]     # as-of week 3
    assert c["i0"] != plain["i0"] and plain["reporting"] is None
    # the corrected count is what the anchor helpers saw
    from flubnf.sihrs_priors import initial_infected_fraction, pin_rho_mult
    corrected = np.array([30.0, 40.0, 50.0 / 0.95, 60.0 / 0.8])
    rm = pin_rho_mult(corrected.sum() / 1_000_000, 0.1)
    assert c["i0"] == pytest.approx(initial_infected_fraction(30.0, 1_000_000, rm, 7.0 / 3.2))


def test_lik_mode_writes_the_column_and_the_engine_key(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    for mode in ("lik", "both"):
        c = _cell(monkeypatch, tmp_path, mode, {"reporting": {"mode": mode}})
        conf = (Path(c["dir"]) / "pf.conf").read_text()
        exp = (Path(c["dir"]) / "Ohio_flu.exp").read_text().splitlines()
        assert "pf_mean_scale_column = completeness\n" in conf
        assert exp[0] == "# time H_weekly completeness"
        assert exp[1:] == ["0 30.000000 1.000000", "1 40.000000 1.000000",
                           "2 50.000000 0.950000", "3 60.000000 0.800000"]
        assert c["reporting"]["mode"] == mode
    cells = json.loads((tmp_path / "lik" / "cells.json").read_text())
    assert cells[0]["reporting"]["pairs"] == {"0": 40, "1": 40, "2": 40}


def test_bad_reporting_configurations_are_refused(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        _cell(monkeypatch, tmp_path, "bad1", {"reporting": {"mode": "nope"}})
    with pytest.raises(ValueError):
        _cell(monkeypatch, tmp_path, "bad2", {"reporting": {"mode": "lik"},
                                              "anchor_asof": "2098-08-15"})
    with pytest.raises(ValueError):
        _cell(monkeypatch, tmp_path, "bad3", {"reporting": {"mode": "lik"},
                                              "variant": "2strain"})


# ------------------------------------------------------------ the analogue

def test_analogue_divides_the_newest_anchor_by_the_lag0_factor_in_both_mode(monkeypatch):
    monkeypatch.setattr(comp, "factors_cached", lambda asof, start: FAC)
    newest = pd.Timestamp("2098-08-22")
    both = _spec({"reporting": {"mode": "both"}})
    assert an_engine.completeness_args(both, "39", newest, newest) == (0.8, None)
    assert an_engine.completeness_args(both, "39", newest - pd.Timedelta(days=7), newest) == (None, None)
    lik = _spec({"reporting": {"mode": "lik"}})
    assert an_engine.completeness_args(lik, "39", newest, newest) == (None, None)
    assert an_engine.completeness_args(_spec(None), "39", newest, newest) == (None, None)
