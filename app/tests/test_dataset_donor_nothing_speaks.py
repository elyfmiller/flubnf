"""A horizon at 0 that no earlier season speaks for, in a file that holds
earlier seasons: no figure, and more seasons may (review of #93 at
f2fd03ef; checks.groundhog_donors, datasets_ui.no_more_seasons).

Where no earlier season with a case held the weeks a horizon at 0 reads,
the check gave "about 6 more earlier seasons", the figure for an ordinary
season. Two files said it where seasons like their own never bring the
horizon off 0:

  * one series with zeros at MMWR weeks 21 to 39, from June 2023 to a
    newest week in weeks 22 to 30 (2024-07-27, week 30, say): its only
    earlier season is the summer of zeros it starts with, which says
    nothing. Started six, seven or twelve years earlier it still counts
    (0, 0, 0, 0);
  * a hubverse file reported from October to May only (observation NA
    at MMWR weeks 21 to 39 every year), ending at week 20 (2025-05-17):
    (6, 3, 0, 0) from 2021-10-09 and (40, 20, 0, 0) from 2004-10-09.
    Horizons 3 and 4 read weeks 21 to 24, which no season reports.

The figure is now given only for a file of the newest season only: a
newcomer's file, for whom the ordinary season is the most useful figure
there is. A file that holds earlier seasons gets none: the earlier seasons
in the file show nothing either way there, and more seasons may. "Would
not help" still takes two seasons with cases that show it.
"""
from __future__ import annotations

import html as H
from datetime import date, timedelta

import pytest

from app.core import datasets as D
from app.core.datasets import checks as CK
from app.ui import datasets_ui as DU
from app.ui import pipeline
from flubnf import analogue as AN

from test_dataset_donor_few_seasons import summer_start  # noqa: E402
from test_dataset_donor_horizons import (               # noqa: E402
    badge, check, counts_of, notice)
from test_datasets_ui import client, isolated          # noqa: E402,F401

#: the June file's newest week: MMWR week 30, in the summer of zeros
END_JUNE = date(2024, 7, 27)
#: the hubverse file's newest week: MMWR week 20, its last reported
END_HUB = date(2025, 5, 17)
HEADER = "target_end_date,location,location_name,observation"

ALL_ZERO = ("No earlier season in the file has a week like it at any "
            "horizon, but the earlier seasons in the file show nothing "
            "either way, and more seasons may.")
TWO_ZERO = ("At 2 horizons no earlier season in the file has a week like "
            "it, but the earlier seasons in the file show nothing either "
            "way there, and more seasons may.")


@pytest.fixture(autouse=True)
def engine_ready(monkeypatch):
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "ready")


def _saturdays(start: date, end: date):
    d = start + timedelta(days=(5 - start.weekday()) % 7)
    while d <= end:
        yield d
        d += timedelta(days=7)


def hub_bytes(start: date, end: date = END_HUB,
              places=(("01", "Alabama"),)) -> bytes:
    """A hubverse file from `start` to `end`: observation NA at MMWR weeks
    21 to 39 every year, cases otherwise; one location unless `places`."""
    rows = [HEADER]
    for i, d in enumerate(_saturdays(start, end)):
        for j, (code, name) in enumerate(places):
            v = ("NA" if 21 <= AN.epiweek(d) <= 39
                 else str(10 + (i * 7 + j * 3) % 40))
            rows.append(f"{d},{code},{name},{v}")
    return ("\n".join(rows) + "\n").encode()


def donors(raw: bytes) -> dict:
    return CK.groundhog_donors(D.validate(raw))


# -------------------------------- the June start, ending in the summer

def test_the_june_start_counts_as_the_review_says():
    assert AN.epiweek(END_JUNE) == 30 and AN.season_of(END_JUNE) == 2023
    for end in _saturdays(date(2024, 6, 1), END_JUNE):
        assert 22 <= AN.epiweek(end) <= 30
        assert counts_of(summer_start(date(2023, 6, 3), end)) == (
            0, 0, 0, 0), end
    # seasons like its own never bring a horizon off 0
    for year in (2017, 2016, 2011):
        assert counts_of(summer_start(date(year, 6, 3), END_JUNE)) == (
            0, 0, 0, 0), year


def test_the_june_start_gives_no_figure():
    """Its one earlier season is the summer of zeros it starts with: no
    season speaks, and the file holds an earlier season, so no figure,
    at every newest week from 22 to 30."""
    for end in _saturdays(date(2024, 6, 1), END_JUNE):
        got = donors(summer_start(date(2023, 6, 3), end))
        assert got["seasons"] is None, end
        assert got["unspoken"] == 4
        assert not got["open"] and not got["one_season"]
    raw = summer_start(date(2023, 6, 3), END_JUNE)
    html = check(raw, kind="rate")
    assert badge(html) == ("warn", "too little history")
    assert notice(html) == (
        "Too little history for the Groundhog: at the newest week it finds "
        "0 weeks like it in earlier seasons and needs 30, so it will not "
        "forecast this data on its own. " + ALL_ZERO)
    assert "Give about" not in html and "would not help" not in html
    assert "group" not in notice(html)
    # counts without a population: the Liu-West filter is still offered
    assert notice(check(raw)).endswith(
        ALL_ZERO[:-1] + ". Add a population column so the Liu-West filter "
        "can fit it.")


# ------------------------------- a hubverse file reported October to May

@pytest.mark.parametrize("start, counts", [
    (date(2021, 10, 9), (6, 3, 0, 0)), (date(2004, 10, 9), (40, 20, 0, 0))],
    ids=["2021", "2004"])
def test_the_hubverse_file_counts_as_the_review_says(start, counts):
    rep = D.validate(hub_bytes(start))
    assert rep.summary["format"] == "hubverse"
    assert AN.epiweek(END_HUB) == 20
    assert counts_of(hub_bytes(start)) == counts


@pytest.mark.parametrize("start", [date(2021, 10, 9), date(2004, 10, 9)],
                         ids=["2021", "2004"])
def test_the_hubverse_file_gives_no_figure(start):
    raw = hub_bytes(start)
    got = donors(raw)
    assert got["seasons"] is None
    assert got["unspoken"] == 2
    assert not got["open"] and not got["one_season"]
    html = check(raw, kind="rate")
    assert notice(html).endswith(TWO_ZERO)
    assert "Give about" not in html and "would not help" not in html


def test_the_2004_hubverse_file_says_what_it_forecasts():
    html = check(hub_bytes(date(2004, 10, 9)), kind="rate")
    assert badge(html) == ("warn", "some horizons only")
    assert notice(html) == (
        "Too little history for the Groundhog at some horizons: at the "
        "newest week it finds 0 to 40 weeks like it in earlier seasons, "
        "depending on the horizon, and needs 30 at each, so it will "
        "forecast 1 of its 4 horizons on its own. " + TWO_ZERO)


def test_several_groups_read_the_same():
    """Two locations reported October to May: the counts are group-weeks,
    and the sentence names no group (none differs from the other)."""
    raw = hub_bytes(date(2021, 10, 9),
                    places=(("01", "Alabama"), ("02", "Alaska")))
    rep = D.validate(raw)
    assert len(rep.summary["groups"]) == 2
    got = CK.groundhog_donors(rep)
    assert got["counts"] == (12, 6, 0, 0) and got["seasons"] is None
    assert got["unspoken"] == 2
    text = H.unescape(notice(check(raw, kind="rate")))
    assert text == (
        "Too little history for the Groundhog: at the newest week it finds "
        "0 to 12 group-weeks like it in earlier seasons, depending on the "
        "horizon, and needs 30, so it will not forecast this data on its "
        "own. " + TWO_ZERO)


# ------------------------------------ the newest season only: the figure

def test_a_file_of_the_newest_season_only_keeps_its_figure():
    """A newcomer's file: no earlier week at all. The ordinary season is
    the figure, for one series and for several groups."""
    one = summer_start(date(2023, 8, 5), END_JUNE)
    rep = D.validate(one)
    assert AN.season_of(date.fromisoformat(rep.summary["first"])) == 2023
    got = CK.groundhog_donors(rep)
    assert got["counts"] == (0, 0, 0, 0)
    assert got["seasons"] == 6 and got["unspoken"] == 0
    assert notice(check(one, kind="rate")).endswith(
        "so it will not forecast this data on its own. Give about 6 more "
        "earlier seasons of data.")
    two = hub_bytes(date(2024, 10, 5),
                    places=(("01", "Alabama"), ("02", "Alaska")))
    got = donors(two)
    assert got["counts"] == (0, 0, 0, 0) and got["seasons"] == 3
    assert notice(check(two, kind="rate")).endswith(
        "Give about 3 more earlier seasons of data.")


# ------------------------------------------------------------ the words

def test_the_words_when_no_season_speaks():
    assert DU.no_more_seasons((0, 0, 0, 0), unspoken=4) == ALL_ZERO
    assert DU.no_more_seasons((6, 3, 0, 0), unspoken=2) == TWO_ZERO
    assert DU.no_more_seasons((6, 3, 1, 0), unspoken=1) == (
        "At 1 horizon no earlier season in the file has a week like it, "
        "but the earlier seasons in the file show nothing either way "
        "there, and more seasons may.")
