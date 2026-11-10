"""Seasons that say nothing, and one season alone, in the "more seasons"
hint (review of #93 at 42db2a82, findings 1 to 3; checks.groundhog_donors,
checks._seasons_heard, datasets_ui.no_more_seasons).

  1. A season reading 0 throughout says nothing about growth. One series
     with two such seasons and a live newest one said "more seasons like
     these would not help", where six real seasons give (31, 31, 31, 31).
     Such a season is no longer counted either way: the figure is back.
  2. One earlier season decided "would not help". One season with a run
     of zeros at MMWR weeks 4 to 8 said it of horizon 4, where six
     ordinary seasons give (34, 33, 32, 31). It now takes two seasons
     with cases holding the weeks. With one, the check gives neither a
     figure (seasons like that one never bring horizon 4 off 0) nor
     "would not help", and says more seasons may.
  3. The figure divided by seasons reading 0 throughout: (5, 5, 5, 5)
     with one such season and one live said "about 10", where 5 suffice.
     It now divides by the earlier seasons with a case. A real season
     whose window weeks read 0 still counts: seasons like the file's give
     that much less, and the figure stays one they reach.

The rule for groups that disagree (test_dataset_donor_mixed_groups) is as
it was.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.core import datasets as D
from app.core.datasets import checks as CK
from app.ui import datasets_ui as DU
from app.ui import pipeline
from flubnf import analogue as AN

from test_dataset_donor_horizons import (               # noqa: E402
    check, counts_of, notice, series_bytes)
from test_datasets_ui import client, isolated          # noqa: E402,F401

#: finding 1's file ends at MMWR week 2 of season 2021-22
END_1 = date(2022, 1, 15)
#: finding 2's at week 2 of season 2025-26
END_2 = date(2026, 1, 17)
#: finding 3's at week 11 of season 2024-25
END_3 = date(2025, 3, 15)
#: the run of zeros of finding 2
RUN = set(range(4, 9))
#: weeks 9 to 17: the donor window of week 11 and the weeks it reads
QUIET = set(range(9, 18))


@pytest.fixture(autouse=True)
def engine_ready(monkeypatch):
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "ready")


def zeroed(raw: bytes, seasons, weeks=None) -> bytes:
    """`raw` with every week of `seasons` (or only its MMWR `weeks`) at 0."""
    lines = raw.decode().splitlines()
    out = [lines[0]]
    for ln in lines[1:]:
        p = ln.split(",")
        d = date.fromisoformat(p[0])
        if AN.season_of(d) in seasons and (weeks is None
                                           or AN.epiweek(d) in weeks):
            p[-1] = "0"
        out.append(",".join(p))
    return ("\n".join(out) + "\n").encode()


def donors(raw: bytes) -> dict:
    return CK.groundhog_donors(D.validate(raw))


# --------------------------- 1. seasons reading 0 throughout say nothing

def finding_1(real_before: int = 0) -> bytes:
    """One series: 2019-20 and 2020-21 read 0, 2021-22 (the newest) has
    cases; with `real_before`, that many seasons with cases before them."""
    return zeroed(series_bytes(END_1, 3 + real_before), {2019, 2020})


def test_1_counts_and_the_real_seasons_as_the_review_says():
    assert AN.epiweek(END_1) == 2
    assert counts_of(finding_1()) == (0, 0, 0, 0)
    assert counts_of(finding_1(real_before=6)) == (31, 31, 31, 31)


def test_1_two_seasons_of_zeros_give_the_figure_back():
    got = donors(finding_1())
    assert got["seasons"] == 6
    assert not got["open"] and not got["one_season"]
    html = check(finding_1(), kind="rate")
    assert notice(html).endswith(
        "so it will not forecast this data on its own. Give about 6 more "
        "earlier seasons of data.")
    assert "would not help" not in html and "may." not in html


def test_1_seasons_of_zeros_do_not_make_a_live_one_two():
    """A live season with finding 2's run of zeros and a season of zeros:
    one season with cases, so not "would not help"."""
    raw = zeroed(zeroed(series_bytes(END_2, 3), {2024}, RUN), {2023})
    got = donors(raw)
    assert got["counts"] == (3, 2, 1, 0)
    assert got["seasons"] is None and got["one_season"] == 1
    assert "would not help" not in check(raw, kind="rate")


def test_1_on_a_bank_seasons_of_zeros_say_nothing():
    """CK._cased: a group's season with a value above 0 anywhere."""
    bank = {("A", date(2023, 9, 2)): 0.0, ("A", date(2024, 1, 6)): 0.0,
            ("A", date(2024, 9, 7)): 0.0, ("A", date(2025, 3, 1)): 2.0,
            ("B", date(2023, 9, 2)): 1.0}
    assert CK._cased(bank) == {("A", 2024), ("B", 2023)}


# ------------------------------------------ 2. one season alone does not

def finding_2(seasons: int = 1, ordinary_before: int = 0) -> bytes:
    """One series ending at END_2: `seasons` earlier seasons with zeros at
    MMWR weeks 4 to 8, the newest, and `ordinary_before` seasons with
    cases throughout before them."""
    s = AN.season_of(END_2)
    runs = set(range(s - seasons, s))
    return zeroed(series_bytes(END_2, 1 + seasons + ordinary_before),
                  runs, RUN)


def test_2_counts_and_the_ordinary_seasons_as_the_review_says():
    assert AN.epiweek(END_2) == 2
    assert counts_of(finding_2()) == (3, 2, 1, 0)
    assert counts_of(finding_2(ordinary_before=6)) == (34, 33, 32, 31)


def test_2_one_season_says_neither_figure_nor_would_not_help():
    got = donors(finding_2())
    assert got["counts"] == (3, 2, 1, 0)
    assert got["seasons"] is None
    assert got["one_season"] == 1 and not got["open"]
    html = check(finding_2(), kind="rate")
    assert notice(html).endswith(
        "At 1 horizon the earlier seasons in the file give no week like "
        "it, but only one season of the group says so, and more seasons "
        "may.")
    assert "would not help" not in html and "Give about" not in html


def test_2_two_such_seasons_still_say_it():
    got = donors(finding_2(seasons=2))
    assert got["counts"] == (6, 4, 2, 0)
    assert got["seasons"] is None
    assert not got["open"] and not got["one_season"]
    assert notice(check(finding_2(seasons=2), kind="rate")).endswith(
        "At 1 horizon no earlier season in the file has a week like it, so "
        "more seasons like these would not help there.")


def test_2_the_words_for_one_season():
    assert DU.no_more_seasons((3, 2, 1, 0), 0, False, 1) == (
        "At 1 horizon the earlier seasons in the file give no week like "
        "it, but only one season of the group says so, and more seasons "
        "may.")
    assert DU.no_more_seasons((3, 2, 0, 0), 0, False, 4) == (
        "At 2 horizons the earlier seasons in the file give no week like "
        "it, but for 4 groups only one season says so, and more seasons "
        "may.")
    # groups with no season that shows it are named first, as before
    assert DU.no_more_seasons((3, 2, 1, 0), 2, True, 1) == (
        "At 1 horizon the earlier seasons in the file give no week like "
        "it, but earlier seasons of the 2 groups without any may.")


# ------------------- 3. the figure divides by the seasons with a case

def finding_3(live_before: int = 0) -> bytes:
    """One series ending at END_3: 2022-23 reads 0, 2023-24 has cases, then
    the newest; with `live_before`, that many seasons with cases before
    2022-23."""
    return zeroed(series_bytes(END_3, 3 + live_before), {2022})


def test_3_counts_as_the_review_says():
    assert AN.epiweek(END_3) == 11
    assert counts_of(finding_3()) == (5, 5, 5, 5)
    # five seasons like the live one suffice
    assert counts_of(finding_3(live_before=5)) == (30, 30, 30, 30)


def test_3_the_figure_leaves_the_season_of_zeros_out():
    got = donors(finding_3())
    assert got["counts"] == (5, 5, 5, 5)
    assert got["seasons"] == 5
    assert CK.groundhog_shortfall(D.validate(finding_3())) == {
        "n": 5, "need": 30, "seasons": 5}
    assert notice(check(finding_3(), kind="rate")).endswith(
        "Give about 5 more earlier seasons of data.")


def quiet_window(more: int = 0) -> bytes:
    """One series ending at END_3: 2022-23 has cases but none at MMWR
    weeks 9 to 17 (the window of week 11 and the weeks it reads),
    2023-24 has cases throughout; with `more`, that many seasons before,
    every other one quiet like 2022-23."""
    quiet = {2022 - 2 * k for k in range(0, more // 2 + 1)}
    return zeroed(series_bytes(END_3, 3 + more), quiet, QUIET)


def test_3_a_real_season_with_a_quiet_window_still_counts():
    """It has cases, so it is one of the file's seasons: seasons like
    these give 2.5 a season, and 10 bring every horizon to 30 where 5 do
    not. The figure stays one seasons like the file's reach."""
    assert counts_of(quiet_window()) == (5, 5, 5, 5)
    assert donors(quiet_window())["seasons"] == 10
    assert counts_of(quiet_window(more=10)) == (30, 30, 30, 30)
    assert counts_of(quiet_window(more=4))[0] < 30
