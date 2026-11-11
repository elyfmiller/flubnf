"""The "about N more earlier seasons" figure: whole numbers, and groups whose
seasons say nothing (review of #93 at ac51731d, findings 2 and 5, and at
f2fd03ef; checks.more_seasons, checks.groundhog_donors).

  2. The figure was worked out in floats, ceil((need - n) / (n / k)), and
     came out one too large where the exact quotient is whole: 15 donor
     weeks over 13 earlier seasons gave "about 14", where 13 more seasons
     like the file's bring every horizon to exactly 30. For need 30 there
     were 43 such pairs of n (1 to 29) and k (1 to 200). It is now the
     ceiling of an exact fraction.
  5. Group A with two earlier seasons with cases beside group B at 0 in
     both said "about 4", where two ordinary seasons of both groups bring
     every horizon to 30. For a while (at b62a0e9b) the figure divided by
     each group's seasons with a case and counted every group once, so B,
     or a group with the newest season only, was taken to give what A's
     seasons give, and the figure was 2.
  6. That let the group with the most seasons set every group's rate,
     and the figure came out smaller than seasons like the file's reach
     (review of #93 at f2fd03ef): group A with one earlier season giving
     nothing beside group B with three said "about 2", where 2 more
     seasons like the file's give 25 and 3 give 30; B with ten seasons
     giving one a season said "about 11", where 11 give 21 and it takes
     20; B at 0 in every week of the file halved the figure, "about 2"
     where it takes 4. The figure again divides by the file's earlier
     seasons in which some group with a case holds a week of the window,
     as at ac51731d, in whole numbers. Those three files get 3, 20 and
     4, which seasons like the file's reach exactly; finding 5's file
     gets its 4 again, which they reach too, while two ordinary seasons
     of both groups would do. Of a figure too large that more seasons
     reach and one too small that they do not, the check gives the
     first.

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
    """Every n under 30, up to 200 seasons; the float form was one too
    large 43 times. The groups do not change it: they count for an
    ordinary season only (finding 6 below; at b62a0e9b they divided it,
    and the figure came out too small)."""
    floats = 0
    for n in range(1, 30):
        for held in range(1, 201):
            if math.ceil((30 - n) / (n / held)) != -(-(30 - n) * held // n):
                floats += 1
            exact = math.ceil((30 - n) / Fraction(n, held))
            for groups in (1, 2, 3):
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
    but none at MMWR weeks 9 to 17 in both earlier seasons; "zero", 0 in
    every week of the file. With `more`, that many more earlier seasons
    of both groups: A's with cases throughout, B's ordinary (just before
    its newest for "new"), or like its own when `like` (none for
    "new")."""
    s = AN.season_of(END)
    lines = ["week_ending,group,cases"]
    for i, d in enumerate(_saturdays(date(s - 2 - more, 8, 1), END)):
        k, e = AN.season_of(d), AN.epiweek(d)
        lines.append(f"{d},A,{_live(i)}")
        mine = s - 2 <= k < s or like and k < s
        v = _live(i + 3)
        if b == "new" and k < (s if like else s - more):
            continue
        if b == "dead" and mine or b == "quiet" and mine and e in QUIET:
            v = 0
        if b == "zero":
            v = 0
        lines.append(f"{d},B,{v}")
    return _csv(lines)


@pytest.mark.parametrize("b", ["dead", "new"])
def test_5_a_figure_too_large_that_is_reached_not_one_too_small(b):
    """B's earlier seasons give nothing, or B has none: seasons like the
    file's give 5 a season, A's, and the figure is 4, which 4 more such
    seasons reach. Two ordinary seasons of both groups would do, but
    nothing in the file says B's seasons are ordinary: the 2 that said
    so (at b62a0e9b) is too small wherever they are not."""
    raw = two_groups(b)
    assert len(D.validate(raw).summary["groups"]) == 2
    assert counts_of(raw) == (10, 10, 10, 10)
    got = donors(raw)
    assert got["seasons"] == 4
    assert notice(check(raw, kind="rate")).endswith(
        "Give about 4 more earlier seasons of data.")
    # seasons like the file's: 4 reach 30, 3 do not, and 2 give 20
    assert counts_of(two_groups(b, more=4, like=True)) == (30, 30, 30, 30)
    assert min(counts_of(two_groups(b, more=3, like=True))) < 30
    assert counts_of(two_groups(b, more=2, like=True)) == (20, 20, 20, 20)
    # ordinary seasons of B: the figure is too large, and still reached
    assert counts_of(two_groups(b, more=2)) == (30, 30, 30, 30)
    assert min(counts_of(two_groups(b, more=4))) >= 30


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


# ---------------- 6. the file's seasons, not each group's shared out

def one_beside(b_seasons: int, b_quiet=(), more: int = 0) -> bytes:
    """Groups A and B ending at END, both with cases in the newest season.
    A: one earlier season (2023-24), with cases but none at MMWR weeks 9
    to 17. B: `b_seasons` earlier seasons with cases, none at the MMWR
    weeks `b_quiet`. With `more`, that many more earlier seasons of each
    group, each like its own."""
    s = AN.season_of(END)
    lines = ["week_ending,group,cases"]
    for i, d in enumerate(_saturdays(date(s - b_seasons - more, 8, 1),
                                     END)):
        k, e = AN.season_of(d), AN.epiweek(d)
        if k >= s - 1 - more:
            a = 0 if k < s and e in QUIET else _live(i)
            lines.append(f"{d},A,{a}")
        b = 0 if k < s and e in b_quiet else _live(i + 3)
        lines.append(f"{d},B,{b}")
    return _csv(lines)


#: the review's three files at f2fd03ef: (file, its figure, the figure
#: shared out over the groups gave)
SIX = {
    # A's one season gives nothing, B's three give 5 each
    "one_beside_three": (lambda more=0: one_beside(3, more=more), 3, 2),
    # B's ten give 1 each: week 13 only, of the window's weeks 9 to 13
    "one_beside_ten": (
        lambda more=0: one_beside(10, range(9, 13), more=more), 20, 11),
    # A's two give 5 each; B reads 0 in every week, the newest's too
    "zero_in_every_week": (
        lambda more=0: two_groups("zero", more=more, like=True), 4, 2),
}


@pytest.mark.parametrize("shape", list(SIX))
def test_6_a_figure_seasons_like_the_files_reach_not_one_too_small(shape):
    """The figure is the number of seasons like the file's (each group's
    like its own) that bring every horizon to 30; one fewer does not, nor
    does the figure each group's seasons shared out over the groups gave
    (review of #93 at f2fd03ef)."""
    make, figure, shared = SIX[shape]
    raw = make()
    assert len(D.validate(raw).summary["groups"]) == 2
    got = donors(raw)
    assert got["seasons"] == figure
    assert notice(check(raw, kind="rate")).endswith(
        f"Give about {figure} more earlier seasons of data.")
    assert min(counts_of(make(figure))) == 30
    assert min(counts_of(make(figure - 1))) < 30
    assert min(counts_of(make(shared))) < 30


def test_6_counts_as_the_review_says():
    assert counts_of(one_beside(3)) == (15, 15, 15, 15)
    assert counts_of(one_beside(3, more=2)) == (25, 25, 25, 25)
    assert counts_of(one_beside(10, range(9, 13))) == (10, 10, 10, 10)
    assert counts_of(one_beside(10, range(9, 13), more=11)) == (
        21, 21, 21, 21)
    assert counts_of(two_groups("zero")) == (10, 10, 10, 10)
    assert counts_of(two_groups("zero", more=2, like=True)) == (
        20, 20, 20, 20)
