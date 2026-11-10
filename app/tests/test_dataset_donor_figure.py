"""The "about N more earlier seasons" figure: whole numbers, and groups whose
seasons say nothing (review of #93 at ac51731d, findings 2 and 5;
checks.more_seasons, checks.groundhog_donors).

  2. The figure was worked out in floats, ceil((need - n) / (n / k)), and
     came out one too large where the exact quotient is whole: 15 donor
     weeks over 13 earlier seasons gave "about 14", where 13 more seasons
     like the file's bring every horizon to exactly 30. For need 30 there
     were 43 such pairs of n (1 to 29) and k (1 to 200). It is now the
     ceiling of an exact fraction.
  5. The figure divided by season numbers, so a group reading 0 in every
     earlier season thinned it: group A with two earlier seasons with
     cases beside group B at 0 in both said "about 4", where two ordinary
     seasons of both groups bring every horizon to 30. A season reading 0
     throughout says nothing about growth (review at 42db2a82, findings 1
     and 3), so the figure now divides by the groups' seasons with a case
     and counts every group once: B, or a group with the newest season
     only, is taken to give what A's seasons give.

A real season whose window reads 0 still counts, in one group
(test_dataset_donor_few_seasons, the figure 10) and beside another
(below): seasons like the file's give that much less, and the figure
stays one they reach.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from fractions import Fraction

import pytest

from app.core import datasets as D
from app.core.datasets import checks as CK
from app.ui import pipeline
from flubnf import analogue as AN

from test_dataset_donor_horizons import (               # noqa: E402
    check, counts_of, notice)
from test_datasets_ui import client, isolated          # noqa: E402,F401

#: every file here ends at MMWR week 11 of season 2024-25
END = date(2025, 3, 15)
#: weeks 9 to 17: the donor window of week 11 and the weeks it reads
QUIET = set(range(9, 18))


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


def _csv(lines) -> bytes:
    return ("\n".join(lines) + "\n").encode()


def donors(raw: bytes) -> dict:
    return CK.groundhog_donors(D.validate(raw))


# ---------------------------------------------- 2. in whole numbers

def thirteen(more: int = 0) -> bytes:
    """One series ending at END: 13 earlier seasons, the first 10 with
    cases but none at MMWR weeks 9 to 17, the last 3 with cases
    throughout, then the newest. With `more`, that many more earlier
    seasons in front, in the same mix: 10 quiet to every 3 with cases."""
    s = AN.season_of(END)
    first = s - 13 - more
    quiet = set()
    for k in range(13 + more):
        if k % 13 < 10:
            quiet.add(first + k)
    lines = ["week_ending,cases"]
    for i, d in enumerate(_saturdays(date(first, 8, 1), END)):
        z = AN.season_of(d) in quiet and AN.epiweek(d) in QUIET
        lines.append(f"{d},{0 if z else _live(i)}")
    return _csv(lines)


def test_2_counts_as_the_review_says():
    assert AN.epiweek(END) == 11
    assert counts_of(thirteen()) == (15, 15, 15, 15)
    # 13 more seasons like these bring every horizon to exactly 30
    assert counts_of(thirteen(more=13)) == (30, 30, 30, 30)


def test_2_fifteen_over_thirteen_says_13():
    got = donors(thirteen())
    assert got["counts"] == (15, 15, 15, 15)
    assert got["seasons"] == 13
    assert notice(check(thirteen(), kind="rate")).endswith(
        "Give about 13 more earlier seasons of data.")


def test_2_the_figure_is_the_ceiling_of_the_exact_fraction():
    """Every n under 30, up to 200 seasons, one to three groups; the float
    form was one too large 43 times for one group."""
    floats = 0
    for n in range(1, 30):
        for held in range(1, 201):
            if math.ceil((30 - n) / (n / held)) != -(-(30 - n) * held // n):
                floats += 1
            for groups in (1, 2, 3):
                exact = math.ceil((30 - n) / Fraction(n * groups, held))
                assert CK.more_seasons(30, n, held, groups, 5) == exact, (
                    n, held, groups)
    assert floats == 43
    assert CK.more_seasons(30, 15, 13, 1, 5) == 13
    assert math.ceil((30 - 15) / (15 / 13)) == 14      # the float form


def test_2_with_nothing_to_go_by_an_ordinary_season_of_every_group():
    assert CK.more_seasons(30, 0, 0, 1, 5) == 6
    assert CK.more_seasons(30, 0, 4, 1, 5) == 6
    assert CK.more_seasons(30, 0, 0, 6, 5) == 1
    assert CK.more_seasons(30, 0, 0, 1, 4) == 8        # a week 53
    assert CK.more_seasons(30, 30, 3, 1, 5) == 0
    assert CK.more_seasons(30, 31, 3, 1, 5) == 0


# --------------------------- 5. a group whose seasons say nothing

def two_groups(b: str, more: int = 0, like: bool = False) -> bytes:
    """Groups A and B ending at END, A with cases throughout from August
    2022 (two earlier seasons). B: "dead", 0 in both earlier seasons and
    cases in the newest; "new", the newest season only; "quiet", cases
    but none at MMWR weeks 9 to 17 in both earlier seasons. With `more`,
    that many more earlier seasons of both groups: A's with cases
    throughout, B's ordinary (just before its newest for "new"), or like
    its two when `like`."""
    s = AN.season_of(END)
    lines = ["week_ending,group,cases"]
    for i, d in enumerate(_saturdays(date(s - 2 - more, 8, 1), END)):
        k, e = AN.season_of(d), AN.epiweek(d)
        lines.append(f"{d},A,{_live(i)}")
        mine = s - 2 <= k < s or like and k < s
        v = _live(i + 3)
        if b == "new" and k < s - more:
            continue
        if b == "dead" and mine or b == "quiet" and mine and e in QUIET:
            v = 0
        lines.append(f"{d},B,{v}")
    return _csv(lines)


@pytest.mark.parametrize("b", ["dead", "new"])
def test_5_a_group_whose_seasons_say_nothing_does_not_thin_it(b):
    raw = two_groups(b)
    assert len(D.validate(raw).summary["groups"]) == 2
    assert counts_of(raw) == (10, 10, 10, 10)
    got = donors(raw)
    assert got["seasons"] == 2
    assert notice(check(raw, kind="rate")).endswith(
        "Give about 2 more earlier seasons of data.")
    # the truth the figure stands for: two ordinary seasons of both
    # groups bring every horizon to 30, one does not
    assert counts_of(two_groups(b, more=2)) == (30, 30, 30, 30)
    assert min(counts_of(two_groups(b, more=1))) < 30


def test_5_real_seasons_whose_window_reads_0_still_count():
    """B's two earlier seasons have cases, none in the window: they are
    seasons of the file, so seasons like these give 5 a season and the
    figure is 4. Four more like these bring every horizon to 30, three
    do not."""
    raw = two_groups("quiet")
    assert counts_of(raw) == (10, 10, 10, 10)
    assert donors(raw)["seasons"] == 4
    like_these = two_groups("quiet", more=4, like=True)
    assert counts_of(like_these) == (30, 30, 30, 30)
    assert min(counts_of(two_groups("quiet", more=3, like=True))) < 30
