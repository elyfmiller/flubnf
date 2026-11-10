""""More seasons like these would not help" only when the file shows it
(review of #93, re-check at 099907c, finding 1; checks.groundhog_donors).

A horizon at 0 donor weeks although an earlier season holds a week of the
donor window and the week that horizon later gave no figure for "about N
more earlier seasons". One dead season, or one small group of zeros, did
that, and real seasons would help there. Now no figure only when:

  * every group-season holding such a pair gives donor weeks at another
    horizon (the window's weeks have cases, the weeks that horizon later
    do not: R1's 36, 24, 12 and 0), or
  * two or more earlier seasons of every group with data hold the pair.

Otherwise the figure is given, as before R1's fix. Where some groups
show it and others have no earlier season, the check gives neither a
figure nor "would not help" (review of #93 at d5a7eb16, findings 1 and
2; test_dataset_donor_mixed_groups).

Since the review of #93 at 42db2a82 (findings 1 and 2;
test_dataset_donor_few_seasons) a season reading 0 throughout counts for
nothing either way, so the small group's three seasons of zeros no longer
speak and the file of (b) gets its figure back; and "would not help"
takes two seasons with cases: one live season gives neither a figure nor
"would not help".
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from app.core import datasets as D
from app.core.datasets import checks as CK
from app.ui import pipeline
from flubnf import analogue as AN

from test_dataset_donor_horizons import (               # noqa: E402
    check, counts_of, notice, series_bytes)
from test_datasets_ui import client, isolated          # noqa: E402,F401

#: the review's scenario (a) ends here: MMWR week 2 of season 2021-22
END_A = date(2022, 1, 15)
#: scenario (b): week 2 of season 2025-26
END_B = date(2026, 1, 17)


@pytest.fixture(autouse=True)
def engine_ready(monkeypatch):
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "ready")


def _saturdays(start: date, end: date):
    d = start + timedelta(days=(5 - start.weekday()) % 7)
    while d <= end:
        yield d
        d += timedelta(days=7)


def _live(i: int) -> int:
    return 10 + (i * 7) % 40


def dead_season_bytes(live_before: int = 0) -> bytes:
    """Scenario (a): one series from August 2020; season 2020-21 reads 0
    throughout; 2021-22 has cases up to END_A. With `live_before`, that
    many seasons with cases come before the dead one."""
    lines = ["week_ending,cases"]
    start = date(2020 - live_before, 8, 1)
    for i, d in enumerate(_saturdays(start, END_A)):
        lines.append(f"{d},{0 if AN.season_of(d) == 2020 else _live(i)}")
    return ("\n".join(lines) + "\n").encode()


def zero_group_bytes(live_seasons: int = 0) -> bytes:
    """Scenario (b): five groups with the newest season only, and one
    small group with three earlier seasons reading 0 (1 a week in the
    newest). With `live_seasons`, each of the six groups also has that
    many seasons with cases just before the newest, after the small
    group's zeros."""
    s = AN.season_of(END_B)
    live = s - live_seasons              # the first season with cases
    lines = ["week_ending,group,cases"]
    for i, d in enumerate(_saturdays(date(live - 3, 8, 1), END_B)):
        k = AN.season_of(d)
        for j, g in enumerate("ABCDE"):
            if k >= live:
                lines.append(f"{d},{g},{_live(i + 3 * j)}")
        small = 1 if k == s else (0 if k < live else _live(i + 20))
        lines.append(f"{d},small,{small}")
    return ("\n".join(lines) + "\n").encode()


def _figure(end: date, groups: int) -> int:
    """The figure with nothing to go by: an ordinary season of every
    group (window_weeks_a_season), as before R1's fix."""
    return math.ceil(30 / (CK.window_weeks_a_season(AN.epiweek(end))
                           * groups))


# ------------------------------------------------ the review's two files

def test_one_dead_season_gets_its_figure_back():
    raw = dead_season_bytes()
    assert counts_of(raw) == (0, 0, 0, 0)
    got = CK.groundhog_donors(D.validate(raw))
    assert got["seasons"] == _figure(END_A, 1) == 6
    html = check(raw, kind="rate")
    assert notice(html).endswith(
        "so it will not forecast this data on its own. Give about 6 more "
        "earlier seasons of data.")
    assert "would not help" not in html


def test_real_seasons_would_help_the_dead_season_file():
    """The figure holds: 6 seasons with cases before the dead one bring
    every horizon to its 30, so "would not help" was wrong."""
    assert min(counts_of(dead_season_bytes(live_before=6))) >= 30


def test_one_zero_group_beside_new_groups_gets_its_figure_back():
    """The small group's seasons read 0 throughout and say nothing, so no
    group speaks: an ordinary season of each of the six, as before R1's
    fix (review of #93 at 42db2a82, finding 1)."""
    raw = zero_group_bytes()
    rep = D.validate(raw)
    assert len(rep.summary["groups"]) == 6
    assert counts_of(raw) == (0, 0, 0, 0)
    got = CK.groundhog_donors(rep)
    assert got["seasons"] == _figure(END_B, 6) == 1
    assert not got["open"] and not got["one_season"]
    html = check(raw, kind="rate")
    assert notice(html).endswith(
        "so it will not forecast this data on its own. Give about 1 more "
        "earlier season of data.")
    assert "would not help" not in html and "without any may" not in html


def test_real_seasons_of_every_group_would_help_the_zero_group_file():
    assert min(counts_of(zero_group_bytes(live_seasons=1))) >= 30


# ------------------------------- where the file does show it, still none

def test_one_live_season_that_gives_other_horizons_donors_still_none():
    """R1's shape with one earlier season: the window's weeks have cases
    (horizons 1 to 3 find donors), the weeks 4 later read 0. That season
    is evidence enough for no figure, but one season is too few for
    "would not help" (review of #93 at 42db2a82, finding 2)."""
    raw = series_bytes(date(2025, 5, 10), 2, low=40, high=20)
    c = counts_of(raw)
    assert c[-1] == 0 and min(c[:-1]) > 0
    got = CK.groundhog_donors(D.validate(raw))
    assert got["seasons"] is None and got["one_season"] == 1


def test_two_dead_seasons_of_the_only_group_get_the_figure():
    """Two earlier seasons of the only group hold the weeks and read 0
    throughout: they say nothing, so the figure (review of #93 at
    42db2a82, finding 1; test_dataset_donor_few_seasons)."""
    lines = ["week_ending,cases"]
    for i, d in enumerate(_saturdays(date(2019, 8, 1), END_A)):
        zero = AN.season_of(d) in (2019, 2020)
        lines.append(f"{d},{0 if zero else _live(i)}")
    raw = ("\n".join(lines) + "\n").encode()
    assert counts_of(raw) == (0, 0, 0, 0)
    assert CK.groundhog_donors(D.validate(raw))["seasons"] == _figure(
        END_A, 1) == 6


def test_a_dead_season_among_two_still_none():
    """A dead season and a live one whose weeks 4 later read 0: the live
    one gives no figure; the dead one does not make it two, so not
    "would not help" either (review of #93 at 42db2a82, findings 1 and
    2)."""
    raw = series_bytes(date(2025, 5, 10), 3, low=40, high=20)
    lines = raw.decode().splitlines()
    out = [lines[0]] + [
        (ln.split(",")[0] + ",0")
        if AN.season_of(date.fromisoformat(ln.split(",")[0])) == 2022
        else ln for ln in lines[1:]]
    raw = ("\n".join(out) + "\n").encode()
    assert counts_of(raw)[-1] == 0
    got = CK.groundhog_donors(D.validate(raw))
    assert got["seasons"] is None and got["one_season"] == 1
