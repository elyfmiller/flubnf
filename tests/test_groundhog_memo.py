"""The Groundhog's donor memo: one bank scan per selection, the same forecasts.

A week's donor selection depends on the bank, the as-of's epiweek and
season, the horizon, the bandwidth and the exclusions, never on the
location, so a run scans each bank once per selection instead of once per
location and horizon (flubnf/analogue.py _memoised; the pooled form's memo
is app/core/engines/analogue.py _walk's, the local form's is the run's
LocalPooling). epiweek and season_of are cached on the date.

Every comparison is against the uncached path, which scans the bank on
every call as the code before the memo did: forecast() with memo=None and
a LocalPooling whose memo never keeps anything (_NoStore).
"""
from __future__ import annotations

import collections
import dataclasses
import json
import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.core import datasets as D
from app.core.engines import analogue as EA
from app.core.runs import RunSpec
from flubnf import analogue as AN

LEVELS = (0.025, 0.25, 0.5, 0.75, 0.975)
ASOF = date(2026, 12, 12)


# --------------------------------------------------- the code before the cache

def _epiweek_before(d) -> int:
    """flubnf.analogue.epiweek before the cache, verbatim."""
    y = d.year
    for yy in (y + 1, y, y - 1):
        j = date(yy, 1, 1)
        wd = (j.weekday() + 1) % 7          # Sunday = 0
        start = date.fromordinal(j.toordinal() - wd + (7 if wd > 3 else 0))
        n = (d.toordinal() - start.toordinal()) // 7
        if 0 <= n < 53:
            return n + 1
    return -1


def _season_of_before(d) -> int:
    """flubnf.analogue.season_of before the cache, verbatim."""
    return d.year if d.month >= AN.SEASON_BOUNDARY_MONTH else d.year - 1


class _NoStore(dict):
    """A memo that never keeps anything: every call scans the bank."""

    def __setitem__(self, key, value):
        pass


@pytest.fixture(autouse=True)
def _cold_calendar_cache():
    AN.epiweek.cache_clear()
    AN.season_of.cache_clear()
    yield
    AN.epiweek.cache_clear()
    AN.season_of.cache_clear()


def _uncached(m):
    """Inside a monkeypatch context `m`: the engine runs with no memo."""
    real_forecast, real_local_args = AN.forecast, EA.local_args

    def forecast(*a, memo=None, **kw):
        return real_forecast(*a, memo=None, **kw)

    def local_args(*a, **kw):
        lp = real_local_args(*a, **kw)
        return None if lp is None else dataclasses.replace(lp, _memo=_NoStore())

    m.setattr(AN, "forecast", forecast)
    m.setattr(EA, "local_args", local_args)


def _scan_counter(m):
    """Inside a monkeypatch context `m`: count every donor scan, keyed by
    the selection it makes (bank, epiweek, season, horizon, bandwidth,
    exclusions, sites)."""
    seen = collections.Counter()
    real_keyed, real_donor = AN.keyed_ratios, AN.donor_ratios

    def keyed(bank, ew, se, horizon, bandwidth=AN.DEFAULT_BANDWIDTH, *,
              exclude_seasons=AN.EXCLUDED_DONOR_SEASONS, sites=None, **kw):
        ex = tuple(exclude_seasons)
        seen[("keyed", id(bank), ew, se, horizon, bandwidth,
              frozenset(ex), None if sites is None else frozenset(sites))] += 1
        return real_keyed(bank, ew, se, horizon, bandwidth,
                          exclude_seasons=ex, sites=sites, **kw)

    def donor(bank, ew, se, horizon, bandwidth=AN.DEFAULT_BANDWIDTH,
              *a, exclude_seasons=AN.EXCLUDED_DONOR_SEASONS):
        ex = tuple(exclude_seasons)
        seen[("donor", id(bank), ew, se, horizon, bandwidth,
              frozenset(ex), None)] += 1
        return real_donor(bank, ew, se, horizon, bandwidth, *a,
                          exclude_seasons=ex)

    m.setattr(AN, "keyed_ratios", keyed)
    m.setattr(AN, "donor_ratios", donor)
    return seen


def _record(spec):
    """Everything a run hands back, as the JSON a byte comparison reads."""
    notes, flags = {}, []
    q = EA.run(spec, notes, flags)
    return q, json.dumps({"q": q, "notes": notes, "flags": flags},
                         sort_keys=True)


# ------------------------------------------------------------ epiweek, season

def test_the_cached_calendar_is_the_code_before_it_on_every_day():
    """Every day 1990-2040, as a date, a datetime and a pandas Timestamp,
    each asked twice (the second answer is the cache's)."""
    days = [date(1990, 1, 1) + timedelta(days=i) for i in range(18_627)]
    for d in days:
        want_w, want_s = _epiweek_before(d), _season_of_before(d)
        for x in (d, datetime(d.year, d.month, d.day, 13, 30), pd.Timestamp(d)):
            assert AN.epiweek(x) == want_w == AN.epiweek(x), x
            assert AN.season_of(x) == want_s == AN.season_of(x), x
    assert AN.epiweek.cache_info().hits >= 3 * len(days)
    assert AN.season_of.cache_info().hits >= 3 * len(days)
    # the edges the MMWR rule turns on
    assert AN.epiweek(date(2020, 12, 31)) == 53
    assert AN.epiweek(date(2021, 1, 9)) == 1
    assert AN.season_of(date(2024, 7, 31)) == 2023
    assert AN.season_of(date(2024, 8, 1)) == 2024


# ------------------------------------------------------- the library's memo

def _bank(locations, seasons, growth, seed=7):
    """Weekly series per location and season, location-specific growth."""
    rng = np.random.default_rng(seed)
    bank = {}
    for s in seasons:
        for loc in locations:
            d = date(s, 8, 1)
            d += timedelta(days=(5 - d.weekday()) % 7)      # a Saturday
            v = 50.0
            for _ in range(52):
                v = max(v * growth[loc] * (1 + rng.uniform(-0.05, 0.05)), 1.0)
                bank[(loc, d)] = v
                d += timedelta(days=7)
    return bank


LOCS = ["A", "B", "C", "D", "E", "F"]
GROWTH = {"A": 1.15, "B": 0.95, "C": 0.95, "D": 1.0, "E": 1.0, "F": 1.0}
BANK = _bank(LOCS, range(2016, 2026), GROWTH)


def test_an_exclusion_iterator_is_read_once_on_both_paths():
    """The memo key and the scan read one resolved set: a one-shot
    iterator must exclude its seasons as the tuple does (review of the
    plan: the key used it up and the scan saw no exclusion)."""
    kw = dict(anchor=100.0, as_of=ASOF, horizon=2, bank=BANK, levels=LEVELS)
    pooled = AN.forecast(**kw, exclude_seasons=(2021,))
    assert pooled != AN.forecast(**kw, exclude_seasons=())      # 2021 matters
    assert AN.forecast(**kw, exclude_seasons=iter([2021]), memo={}) == pooled
    assert AN.forecast(**kw, exclude_seasons=iter([2021])) == pooled
    local = AN.forecast(**kw, exclude_seasons=(2021,),
                        local=AN.LocalPooling(own_share=0.5), location="A")
    assert local != AN.forecast(**kw, exclude_seasons=(),
                                local=AN.LocalPooling(own_share=0.5),
                                location="A")
    assert AN.forecast(**kw, exclude_seasons=iter([2021]),
                       local=AN.LocalPooling(own_share=0.5),
                       location="A") == local


def test_one_memo_two_banks_and_read_only_ratios():
    """A memo shared by two banks hands each its own ratios, and what it
    hands out cannot be written."""
    other = _bank(LOCS, range(2016, 2026), {**GROWTH, "D": 1.3}, seed=8)
    memo = {}
    for bank in (BANK, other, BANK, other):
        for h in (1, 2, 3, 4):
            assert (AN.forecast(100.0, ASOF, h, bank, LEVELS, memo=memo)
                    == AN.forecast(100.0, ASOF, h, bank, LEVELS))
    assert len(memo) == 8
    lp = AN.LocalPooling(own_share=0.5, anchor_weight="kernel", ess_floor=30.0)
    for bank in (BANK, other, BANK):
        for loc in LOCS:
            fresh = AN.LocalPooling(own_share=0.5, anchor_weight="kernel",
                                    ess_floor=30.0, _memo=_NoStore())
            assert (AN.forecast(100.0, ASOF, 2, bank, LEVELS, local=lp,
                                location=loc)
                    == AN.forecast(100.0, ASOF, 2, bank, LEVELS, local=fresh,
                                   location=loc))
    primary = [v for k, v in lp._memo.items() if k[0] == "primary"]
    assert len(primary) == 2
    arrays = [out for _b, out in memo.values()]
    arrays += [a for _b, out in primary for a in out]
    assert arrays and not any(a.flags.writeable for a in arrays)
    with pytest.raises(ValueError):
        arrays[0][0] = 1.0


# --------------------------------------------------- the engine on the hub path

@pytest.fixture
def hub(tmp_path, monkeypatch):
    """The test hub archive (app/tests/test_dataset_engines.py)."""
    from app.tests.test_dataset_engines import GOLDEN_DATES, HUB_LOCS, _hub_archive
    arch = _hub_archive(tmp_path / "hub")
    monkeypatch.setattr(EA, "vintage_path", lambda d: arch["vintages"][str(d)])
    monkeypatch.setattr(EA, "LOCATIONS", arch["locations"])
    return [n for _f, _a, n, _p in HUB_LOCS], GOLDEN_DATES


def _hub_forms():
    shipped_aux = EA.aux_preset(EA.SHIPPED_AUX)(None, 0, None)
    research = {"own_share": 0.3, "region_share": 0.2, "own_site": True,
                "anchor_weight": "kernel", "ess_floor": 30.0,
                "repair_spikes": True, "anchor_floor": 2.0}
    return {
        "bare": ({"local_pools": None}, {}),
        "pooled groundhog": ({**shipped_aux, "local_pools": None}, {}),
        "shipped groundhog": (shipped_aux, {}),
        "shipped, drop 1, bandwidth 3": (
            {**shipped_aux, "knobs": {"groundhog.bandwidth": 3}},
            {"weeks_to_drop": 1}),
        "zero anchors blended": (
            {**shipped_aux, "knobs": {"groundhog.zero_anchor": "blend"}}, {}),
        "research local form": ({**shipped_aux, "local_pools": research}, {}),
    }


def test_the_hub_path_is_the_same_with_and_without_the_memo(hub, monkeypatch):
    names, dates = hub
    forecasts = 0
    for fd in dates:
        for label, (extra, kw) in _hub_forms().items():
            spec = RunSpec(engine="analogue", forecast_date=fd,
                           locations=names, extra=extra, **kw)
            AN.epiweek.cache_clear()
            AN.season_of.cache_clear()
            q, cached = _record(spec)
            with monkeypatch.context() as m:
                _uncached(m)
                AN.epiweek.cache_clear()
                AN.season_of.cache_clear()
                _q, plain = _record(spec)
            assert cached == plain, (fd, label)
            forecasts += sum(len(hq) for hq in q.values())
    assert forecasts >= 2 * len(_hub_forms()) * 3 * 4      # not vacuous


def test_a_run_scans_each_selection_once(hub, monkeypatch):
    """The shipped Groundhog on the fixture: every (bank, calendar,
    horizon) selection is scanned once; without the memo the admissions
    bank is scanned for every location and horizon."""
    names, dates = hub
    spec = RunSpec(engine="analogue", forecast_date=dates[0], locations=names,
                   extra=EA.aux_preset(EA.SHIPPED_AUX)(None, 0, None))
    with monkeypatch.context() as m:
        seen = _scan_counter(m)
        q = EA.run(spec)
    assert len(q) == len(names)
    assert seen and max(seen.values()) == 1
    primary = sum(n for k, n in seen.items() if k[0] == "keyed")
    assert primary == 4                     # one per horizon, not per location
    with monkeypatch.context() as m:
        seen = _scan_counter(m)
        _uncached(m)
        assert EA.run(spec) == q
    assert sum(n for k, n in seen.items() if k[0] == "keyed") == 4 * len(names)


# ------------------------------------------------------- a 60-group dataset

def _groups_bytes(n_groups: int, first: date, last: date) -> bytes:
    """n_groups seasonal waves with their own phases and sizes."""
    lines = ["date,target_group,value,population"]
    d = first + timedelta(days=(5 - first.weekday()) % 7)
    i = 0
    while d <= last:
        for j in range(n_groups):
            phase = ((i + 3 * j) % 52) / 52.0
            w = math.exp(-((phase - 0.4) ** 2) / 0.008)
            v = round((3.0 + j % 17) * (0.6 + 9.0 * w) * (1 + 0.05 * ((i * 7 + j) % 5)))
            lines.append(f"{d.isoformat()},G{j:03d},{v:g},{100_000 * (j + 1)}")
        d += timedelta(days=7)
        i += 1
    return ("\n".join(lines) + "\n").encode()


def test_a_60_group_dataset_is_the_same_with_and_without_the_memo(
        tmp_path, monkeypatch):
    """Own data in the pooled form (a dataset's default), the case the memo
    exists for: one scan per location and horizon grew with the square of
    the groups. One prior season keeps the uncached arm about a second."""
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    ds = D.ingest(_groups_bytes(60, date(2022, 8, 6), date(2023, 12, 2)),
                  "sixty", kind="count")
    assert len(ds.groups) == 60
    spec = RunSpec(engine="analogue", forecast_date="2023-12-02",
                   locations=ds.groups, extra={"dataset": ds.ref()})
    q, cached = _record(spec)
    assert len(q) == 60 and all(len(hq) == 4 for hq in q.values())
    with monkeypatch.context() as m:
        seen = _scan_counter(m)
        _uncached(m)
        AN.epiweek.cache_clear()
        AN.season_of.cache_clear()
        _q, plain = _record(spec)
    assert cached == plain
    assert sum(seen.values()) == 4 * 60          # the uncached arm did scan
