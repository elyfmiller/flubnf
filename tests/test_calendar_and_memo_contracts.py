"""Two contracts of the Groundhog's caches (review 3, finding 16).

The calendar. epiweek and season_of are cached on their argument
(flubnf/analogue.py _cached_calendar). Two time-zone-aware stamps for one
instant in different zones compare equal, and hash alike, yet fall on
different calendar days, so a cache keyed on the stamp gave the second the
first's answer. Aware stamps, and anything that cannot be hashed, are now
answered by the rule itself: every input gets the answer, or the refusal,
the code before the cache gave. Dates and naive stamps keep the cache.

The memo. A memo hit is matched on the bank object, not on what it holds
(flubnf/analogue.py _memoised), so a bank changed in place under a kept
memo would return the first scan. Reading the bank to notice would cost
the scan the memo saves, so the rule is the caller's, written on
_memoised, forecast() and LocalPooling: never change a bank in place under
a kept memo. These tests hold the engine to it: every bank any memo of a
run reads (the admissions bank, the research bank, the splice pools'),
on the hub path in every form and on a dataset, run() and nowcast(), is
unchanged from the first time a memo reads it to the end of the run.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.core import datasets as D
from app.core.engines import analogue as EA
from app.core.runs import RunSpec
from flubnf import analogue as AN
from tests.test_groundhog_memo import (_epiweek_before, _groups_bytes,
                                       _hub_forms, _season_of_before, hub)

assert hub                                     # the fixture, imported

ZONES = ("UTC", "America/Los_Angeles", "America/New_York", "Pacific/Kiritimati",
         "Pacific/Pago_Pago", "Asia/Kolkata", "Australia/Adelaide")


@pytest.fixture(autouse=True)
def _cold_calendar_cache():
    AN.epiweek.cache_clear()
    AN.season_of.cache_clear()
    yield
    AN.epiweek.cache_clear()
    AN.season_of.cache_clear()


def _both(x):
    return AN.epiweek(x), AN.season_of(x)


def _before(x):
    return _epiweek_before(x), _season_of_before(x)


# ------------------------------------------------------------- the calendar

def test_one_instant_in_two_zones_gets_each_zones_own_day():
    """The reviewer's case: 2024-08-01 03:00 UTC is still July 31 in Los
    Angeles, season 2023 there; and an instant that is Sunday in UTC and
    Saturday in New York is in two epiweeks. Either order, asked twice."""
    utc = pd.Timestamp("2024-08-01 03:00", tz="UTC")
    la = utc.tz_convert("America/Los_Angeles")
    assert utc == la and hash(utc) == hash(la)
    assert _before(utc)[1] == 2024 and _before(la)[1] == 2023
    sun = pd.Timestamp("2024-01-07 02:00", tz="UTC")
    sat = sun.tz_convert("America/New_York")
    assert _before(sun)[0] == 2 and _before(sat)[0] == 1
    for pair in ((utc, la), (la, utc), (sun, sat), (sat, sun)):
        for _ in range(2):
            for x in pair:
                assert _both(x) == _before(x), x
    # the same with the standard library's own zones
    u = datetime(2024, 8, 1, 3, tzinfo=timezone.utc)
    w = u.astimezone(timezone(timedelta(hours=-7)))
    assert u == w
    for x in (u, w, u, w):
        assert _both(x) == _before(x), x


def test_aware_stamps_never_enter_or_read_the_cache():
    """Aware stamps leave the caches as they were; an aware stamp whose
    naive twin is cached still gets its own day."""
    naive = pd.Timestamp("2024-08-01 03:00")
    assert _both(naive) == (31, 2024)
    before = AN.epiweek.cache_info().currsize, AN.season_of.cache_info().currsize
    for z in ZONES:
        x = pd.Timestamp("2024-08-01 03:00", tz="UTC").tz_convert(z)
        assert _both(x) == _before(x)
        assert _both(x.to_pydatetime()) == _before(x.to_pydatetime())
    assert (AN.epiweek.cache_info().currsize,
            AN.season_of.cache_info().currsize) == before


def test_every_instant_in_every_zone_in_random_order():
    """2,000 random instants 2019-2027 (many near midnight), each in seven
    zones as a pandas Timestamp and a datetime, mixed with naive stamps and
    dates of the same days, in random order, each asked twice: the code
    before the cache's answer every time."""
    rng = random.Random(20261110)
    xs = []
    start = pd.Timestamp("2019-01-01", tz="UTC")
    for _ in range(2000):
        t = start + pd.Timedelta(minutes=rng.randrange(8 * 366 * 24 * 60))
        for z in ZONES:
            a = t.tz_convert(z)
            xs += [a, a.to_pydatetime(), a.tz_localize(None),
                   a.date(), datetime(a.year, a.month, a.day, a.hour)]
    rng.shuffle(xs)
    for x in xs + xs[::-1]:
        assert _both(x) == _before(x), x
    assert AN.epiweek.cache_info().hits > 0       # the cache still works


class _DateLike:
    """A date-like the rule reads (year, month, toordinal) but that cannot
    be hashed."""
    __hash__ = None

    def __init__(self, d: date):
        self._d = d
        self.year, self.month = d.year, d.month

    def toordinal(self) -> int:
        return self._d.toordinal()


@pytest.mark.parametrize("x", [
    _DateLike(date(2024, 8, 1)), _DateLike(date(2020, 12, 31)),
    "2024-08-01", None, 20240801, float("nan"), pd.NaT,
    [date(2024, 8, 1)], {"year": 2024}, np.datetime64("2024-08-01"),
    pd.Timestamp("2024-08-01").to_numpy(),
])
def test_anything_else_is_answered_or_refused_as_before(x):
    """What the rule answers it still answers (an unhashable date-like
    included), and what it refused it refuses with the same exception."""
    for cached, before in ((AN.epiweek, _epiweek_before),
                           (AN.season_of, _season_of_before)):
        for _ in range(2):
            try:
                want = ("ok", repr(before(x)))    # repr: NaT's season is nan
            except Exception as e:            # noqa: BLE001
                want = (type(e), str(e))
            try:
                got = ("ok", repr(cached(x)))
            except Exception as e:            # noqa: BLE001
                got = (type(e), str(e))
            assert got == want, (cached.__name__, x)


def test_the_public_names_and_cache_handles_stay():
    for f, name in ((AN.epiweek, "epiweek"), (AN.season_of, "season_of")):
        assert f.__name__ == name and f.__doc__
        assert callable(f.cache_info) and callable(f.cache_clear)
    assert AN.epiweek.__doc__.startswith("CDC MMWR week number.")
    for d in (date(2024, 8, 1), pd.Timestamp("2024-08-01"),
              datetime(2024, 8, 1, 12)):
        assert _both(d) == _before(d) == _both(d)


# ------------------------------------------------------------------ the memo

class _BankWatch:
    """Inside a monkeypatch context `m`: every bank a memo reads, kept as
    it was when a memo first read it, compared on every later read and by
    check(). The banks: _memoised's (the admissions bank, or the research
    bank built from it), the bank forecast() is given and its splice
    pools' (the splice's own memo and the local form's own-site memo read
    those)."""

    def __init__(self, m):
        self.seen = {}
        self.reads = 0
        real_memoised, real_forecast = AN._memoised, AN.forecast

        def memoised(memo, key, bank, scan):
            self._read(bank)
            return real_memoised(memo, key, bank, scan)

        def forecast(*a, **kw):
            bank = kw["bank"] if "bank" in kw else a[3]
            self._read(bank)
            splice = kw.get("splice")
            for p in (splice.pools if splice is not None else ()):
                self._read(p.bank)
            return real_forecast(*a, **kw)

        m.setattr(AN, "_memoised", memoised)
        m.setattr(AN, "forecast", forecast)

    def _read(self, bank):
        self.reads += 1
        kept = self.seen.get(id(bank))
        if kept is None or kept[0] is not bank:
            self.seen[id(bank)] = (bank, dict(bank))
        else:
            assert dict(bank) == kept[1], "a bank changed in place"

    def check(self, forecasts: bool = True):
        """Every bank as a memo first read it; with `forecasts`, some bank
        was read more than once (a memo did its work)."""
        if forecasts:
            assert self.seen and self.reads > len(self.seen)
        for bank, was in self.seen.values():
            assert dict(bank) == was, "a bank changed in place"


def test_no_run_changes_a_bank_its_memos_read(hub, monkeypatch):
    """The hub fixture, every form test_groundhog_memo.py runs (bare,
    pooled, shipped, a bandwidth and a trim, the zero-anchor blend, the
    research local form with the spike repair), run() and nowcast()."""
    names, dates = hub
    spliced = nowcasts = 0
    for fd in dates:
        for label, (extra, kw) in _hub_forms().items():
            spec = RunSpec(engine="analogue", forecast_date=fd,
                           locations=names, extra=extra, **kw)
            for go in (EA.run, EA.nowcast):
                with monkeypatch.context() as m:
                    watch = _BankWatch(m)
                    out = go(spec)
                assert out, (fd, label)
                # nowcast forecasts only behind a trim (k >= 1)
                q = (go is EA.run
                     or any(v["q"] for v in out.values()))
                nowcasts += go is EA.nowcast and q
                watch.check(forecasts=q)
                spliced += len(watch.seen) > 1
    assert spliced                          # the splice pools were watched
    assert nowcasts                         # and a nowcast's reads


def test_no_dataset_run_changes_a_bank_its_memos_read(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    ds = D.ingest(_groups_bytes(8, date(2021, 8, 7), date(2023, 12, 2)),
                  "eight", kind="count")
    for kw in ({}, {"weeks_to_drop": 1}):
        spec = RunSpec(engine="analogue", forecast_date="2023-12-02",
                       locations=ds.groups, extra={"dataset": ds.ref()}, **kw)
        for go in (EA.run, EA.nowcast):
            with monkeypatch.context() as m:
                watch = _BankWatch(m)
                out = go(spec)
            assert out and len(out) == 8
            watch.check(forecasts=go is EA.run or bool(kw))


def test_the_watch_sees_a_bank_changed_in_place():
    """Not vacuous: a bank revised in place between two forecasts that
    share a memo is caught, and the memo indeed returns the first scan
    (the contract _memoised states)."""
    from tests.test_groundhog_memo import BANK, LEVELS, ASOF
    bank = dict(BANK)
    memo = {}
    with pytest.MonkeyPatch.context() as m:
        _BankWatch(m)
        first = AN.forecast(100.0, ASOF, 2, bank, LEVELS, memo=memo)
        for k in list(bank)[::3]:
            bank[k] *= 3.0                      # revised in place
        with pytest.raises(AssertionError, match="changed in place"):
            AN.forecast(100.0, ASOF, 2, bank, LEVELS, memo=memo)
    assert AN.forecast(100.0, ASOF, 2, bank, LEVELS, memo=memo) == first
    fresh = AN.forecast(100.0, ASOF, 2, bank, LEVELS, memo={})
    assert fresh != first
    assert AN.forecast(100.0, ASOF, 2, dict(bank), LEVELS, memo=memo) == fresh
