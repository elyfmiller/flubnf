"""The optional missing-data rules (app/core/missing.py; docs/MISSING-DATA.md).

Off by default and byte-identical when off; when on, a flagged newest week
leaves both members exactly as a trimmed week does (anchor moved back,
horizons as-of-aligned), and every flagged week is recorded.
"""
import json
from datetime import date, timedelta

import pytest

from app.core import knobs as K
from app.core import missing as MS
from app.core.engines import analogue as EA
from app.core.engines import pf
from app.core.runs import RunSpec, results_html
from app.tests.test_pf_hardening import _prep_env

ON_ZERO = {"knobs": {"data.trailing_zero": "missing"}}
ON_PARTIAL = {"knobs": {"data.partial_week": "missing"}}


# --- the rule itself ---------------------------------------------------------------

@pytest.mark.parametrize("values, rules, want", [
    ([5, 3, 0], {}, []),                                  # off: nothing
    ([5, 3, 0], ON_ZERO["knobs"], [(2, "trailing zero")]),
    ([5, 0, 0], ON_ZERO["knobs"], [(1, "trailing zero"), (2, "trailing zero")]),
    ([5, 0, 0, 0], ON_ZERO["knobs"], []),                 # longer than MAX_CARRY
    ([0, 0], ON_ZERO["knobs"], []),                       # nothing positive before
    ([5, 3, 1], ON_ZERO["knobs"], []),
    ([100, 19], ON_PARTIAL["knobs"], [(1, "partial week")]),
    ([100, 20], ON_PARTIAL["knobs"], []),                 # exactly a fifth: kept
    ([19, 1], ON_PARTIAL["knobs"], []),                   # previous under the floor
    ([5, 3, 0], ON_PARTIAL["knobs"], []),
])
def test_tail_flags(values, rules, want):
    assert MS.tail_flags(values, rules) == want


def test_rules_read_only_the_record():
    assert MS.rules_of(None) == {} and MS.rules_of({}) == {}
    assert MS.rules_of({"knobs": {"data.trailing_zero": "keep"}}) == {}
    assert MS.rules_of(ON_ZERO) == {"data.trailing_zero": "missing"}


def test_knobs_are_off_by_default_and_panelled_with_the_fit_window():
    for key in MS.KEYS:
        k = K.BY_KEY[key]
        assert k.default == "keep" and k.affects == K.BOTH and k.stage == "fit"
        assert K._group_of(k) == "data"
    got = K.resolve({"knob.data.partial_week": "missing"}, "all",
                    forecast_date="2026-10-03")
    assert got == {"data.partial_week": "missing"}
    extra = K.write_extra(got, {})
    assert MS.rules_of(extra) == {"data.partial_week": "missing"}
    assert K.fit_extra(extra)["knobs"] == {"data.partial_week": "missing"}


def test_run_page_line():
    assert MS.line({}) == "" and MS.line({"pf": [], "analogue": []}) == ""
    row = {"location": "Vermont", "week": "2026-06-27", "value": 0.0,
           "rule": "trailing zero"}
    got = MS.line({"analogue": [row], "pf": [dict(row)]})
    assert got == ("1 week to 2026-06-27 treated as unreported "
                   "(trailing zero): Vermont 1")
    two = MS.line({"analogue": [row, {**row, "week": "2026-06-20"},
                                {**row, "location": "Maine",
                                 "rule": "partial week"}]})
    assert two == ("3 weeks to 2026-06-27 treated as unreported (partial "
                   "week, trailing zero): Vermont 2, Maine 1")
    html = results_html({"data_flags": {"analogue": [row]}},
                        {"engine": "all", "forecast_date": "2026-07-04",
                         "extra": ON_ZERO})
    assert "Missing-data rules" in html and "(trailing zero): Vermont 1" in html
    assert "Missing-data rules" not in results_html(
        {"pf_cells": 3}, {"engine": "all", "forecast_date": "2026-07-04"})


# --- the Groundhog -----------------------------------------------------------------

AS_OF = date(2017, 1, 7)
STATES = {"01": "Alpha", "02": "Beta", "04": "Gamma", "05": "Delta"}


def _hub(tmp_path, monkeypatch, tail):
    """A synthetic vintage: four states, six prior seasons of smooth waves
    (the donors), and this season's last three weeks set per state by
    `tail` ({name: [v-2, v-1, v0]})."""
    rows = []
    start = AS_OF - timedelta(weeks=7 * 52)
    d = start
    i = 0
    while d <= AS_OF:
        for n, (fips, name) in enumerate(STATES.items()):
            v = 20 + 15 * (1 + n) * (1 + ((i % 52) / 52.0)) + (i % 7)
            rows.append((d.isoformat(), fips, name, round(v)))
        d += timedelta(weeks=1)
        i += 1
    tail_dates = [(AS_OF - timedelta(weeks=2 - j)).isoformat() for j in range(3)]
    by_key = {(r[0], r[2]): r for r in rows}
    for name, vals in tail.items():
        for dt, v in zip(tail_dates, vals):
            r = by_key[(dt, name)]
            by_key[(dt, name)] = (r[0], r[1], r[2], v)
    v = tmp_path / "vintage.csv"
    v.write_text("date,location,location_name,value\n" + "".join(
        f"{a},{b},{c},{x}\n" for a, b, c, x in by_key.values()))
    locs = tmp_path / "locations.csv"
    locs.write_text("location,location_name,abbreviation,population\n" + "".join(
        f"{f},{n},{n[:2].upper()},1000000\n" for f, n in STATES.items()))
    monkeypatch.setattr(EA, "vintage_path", lambda _d: v)
    monkeypatch.setattr(EA, "LOCATIONS", locs)


def _spec(extra=None, weeks_to_drop=0):
    return RunSpec(engine="analogue", forecast_date=AS_OF.isoformat(),
                   locations=list(STATES.values()),
                   weeks_to_drop=weeks_to_drop, extra=dict(extra or {}))


def test_groundhog_default_is_unchanged(tmp_path, monkeypatch):
    _hub(tmp_path, monkeypatch, {"Alpha": [40, 30, 0], "Beta": [200, 190, 12]})
    base = EA.run(_spec())
    flags = []
    assert EA.run(_spec(), flags=flags) == base and flags == []
    assert "Alpha" not in base            # a zero anchor abstains, as shipped
    assert {"Beta", "Gamma", "Delta"} <= set(base)


def test_groundhog_trailing_zero_carries_the_anchor_back(tmp_path, monkeypatch):
    _hub(tmp_path, monkeypatch, {"Alpha": [40, 30, 0]})
    flags = []
    got = EA.run(_spec(ON_ZERO), flags=flags)
    trimmed = EA.run(_spec(weeks_to_drop=1))
    assert got["Alpha"] == trimmed["Alpha"]
    assert got["Beta"] == EA.run(_spec())["Beta"]         # unflagged: untouched
    assert flags == [{"location": "Alpha", "rule": "trailing zero",
                      "week": AS_OF.isoformat(), "value": 0.0}]


def test_groundhog_partial_week(tmp_path, monkeypatch):
    _hub(tmp_path, monkeypatch, {"Beta": [200, 190, 12]})
    flags = []
    got = EA.run(_spec(ON_PARTIAL), flags=flags)
    assert got["Beta"] == EA.run(_spec(weeks_to_drop=1))["Beta"]
    assert got["Beta"] != EA.run(_spec())["Beta"]
    assert [f["location"] for f in flags] == ["Beta"]


# --- the particle filter -----------------------------------------------------------

class _State:
    def __init__(self, observed):
        self.observed = list(observed)
        self.times = list(range(15 - len(observed), 15))   # ends at the as-of
        self.n_obs = len(observed)
        self.last_week_offset = self.times[-1]
        self.i0, self.rhomult = 5e-3, 0.05
        self.population, self.attack_rate, self.gamma = 1_000_000, 0.1, 1.0


def _pf_spec(extra=None):
    # 2098-11-07 is week 14 of a 2098-08-01 season
    return type("S", (), {
        "forecast_date": "2098-11-07", "season_start": "2098-08-01",
        "weeks_to_drop": 0, "drop_same_day": False,
        "locations": ["Ohio"], "replicates": 1, "particles": 100,
        "jitter": 0.3, "observable_mode": "integrated", "extra": extra})()


def test_pf_default_cells_are_unchanged(monkeypatch, tmp_path):
    _prep_env(monkeypatch, tmp_path, lambda loc, **kw: _State([40, 50, 5]))
    cells = pf.prepare(_pf_spec(), tmp_path / "wr")
    assert cells[0]["weeks_dropped"] == 0 and "data_flags" not in cells[0]


def test_pf_flagged_week_is_trimmed_and_recorded(monkeypatch, tmp_path):
    _prep_env(monkeypatch, tmp_path, lambda loc, **kw: _State([40, 50, 5]))
    w = tmp_path / "wr"
    cells = pf.prepare(_pf_spec(ON_PARTIAL), w)
    assert cells[0]["weeks_dropped"] == 1
    assert cells[0]["data_flags"] == [
        {"week": "2098-11-07", "rule": "partial week", "value": 5.0}]
    assert "pf_forecast_intervals = 5" in (w / "Ohio_r0" / "pf.conf").read_text()
    assert json.loads((w / "cells.json").read_text()) == cells
