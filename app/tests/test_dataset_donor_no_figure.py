"""No "about N more earlier seasons" for a horizon the file's own seasons
give nothing (review of #93, re-check R1; checks.groundhog_donors,
datasets_ui.model_view).

  * one group, 13 seasons, values 0 outside MMWR weeks 40 to 20, ending
    at week 19: the newest week finds 36, 24, 12 and 0 donor weeks. Each
    earlier season holds the weeks the last horizon reads, and gives it
    none: with 6 or 30 more such seasons it is still 0. The check gives
    no figure there and says that horizon finds no week like it;
  * a newest week in a summer of zeros: no horizon finds one, and no
    figure is given;
  * a horizon at 0 only because no earlier season holds the weeks it
    reads: a file of one season still gets a figure, as before. One that
    starts a few weeks before the newest week's season got it too, until
    the review of #93 at f2fd03ef: it holds an earlier season, whose
    weeks show nothing either way there, so no figure, and more seasons
    may (test_dataset_donor_nothing_speaks).
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
    badge, check, counts_of, notice, series_bytes)
from test_datasets_ui import client, isolated          # noqa: E402,F401

#: the review's file ends at MMWR week 19 (2025-05-10)
END_19 = date(2025, 5, 10)


def r1(seasons: int) -> bytes:
    return series_bytes(END_19, seasons, low=40, high=20)


@pytest.fixture(autouse=True)
def engine_ready(monkeypatch):
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "ready")


def test_the_review_file_counts_as_the_review_says():
    assert AN.epiweek(END_19) == 19
    assert counts_of(r1(13)) == (36, 24, 12, 0)
    # more seasons like these never bring the last horizon off 0
    assert counts_of(r1(13 + 6)) == (54, 36, 18, 0)
    assert counts_of(r1(13 + 30))[-1] == 0


def test_no_figure_for_a_horizon_its_seasons_give_nothing():
    rep = D.validate(r1(13))
    got = CK.groundhog_donors(rep)
    assert got["counts"] == (36, 24, 12, 0) and got["seasons"] is None
    assert CK.groundhog_shortfall(rep) == {"n": 0, "need": 30,
                                           "seasons": None}


def test_the_check_says_that_horizon_finds_no_week_like_it():
    html = check(r1(13), kind="rate")
    assert badge(html) == ("warn", "some horizons only")
    assert notice(html) == (
        "Too little history for the Groundhog at some horizons: at the "
        "newest week it finds 0 to 36 weeks like it in earlier seasons, "
        "depending on the horizon, and needs 30 at each, so it will "
        "forecast 1 of its 4 horizons on its own. At 1 horizon no earlier "
        "season in the file has a week like it, so more seasons like these "
        "would not help there.")
    assert "about" not in notice(html)
    # counts without a population: the Liu-West filter is still offered
    html = check(r1(13), kind="count")
    assert notice(html).endswith(
        "forecast 1 of its 4 horizons on its own. At 1 horizon no earlier "
        "season in the file has a week like it, so more seasons like these "
        "would not help there. Add a population column so the Liu-West "
        "filter can fit it.")


def test_the_engine_not_ready_is_named_too(monkeypatch):
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "missing")
    rep = D.validate(r1(13))
    view = DU.model_view(rep, {}, "count")
    assert view["groundhog_fix"] == (
        "At 1 horizon no earlier season in the file has a week like it, so "
        "more seasons like these would not help there. Add a population "
        "column and set up the engine so the Liu-West filter can fit it.")
    raw = r1(13).replace(b"week_ending,cases", b"week_ending,cases,population")
    raw = b"\n".join(ln + (b",1000000" if i else b"")
                     for i, ln in enumerate(raw.rstrip(b"\n").split(b"\n")))
    view = DU.model_view(D.validate(raw + b"\n"), {}, "count")
    assert view["groundhog_fix"] == (
        "At 1 horizon no earlier season in the file has a week like it, so "
        "more seasons like these would not help there. Set up the engine "
        "so the Liu-West filter can fit it.")


def test_a_summer_of_zeros_gives_no_horizon_a_figure():
    end = date(2025, 7, 26)                       # MMWR week 30, in summer
    raw = series_bytes(end, 5, low=40, high=20)
    assert counts_of(raw) == (0, 0, 0, 0)
    assert CK.groundhog_donors(D.validate(raw))["seasons"] is None
    html = check(raw, kind="rate")
    assert badge(html) == ("warn", "too little history")
    assert notice(html) == (
        "Too little history for the Groundhog: at the newest week it finds "
        "0 weeks like it in earlier seasons and needs 30, so it will not "
        "forecast this data on its own. No earlier season in the file has "
        "a week like it at any horizon, so more seasons like these would "
        "not help.")
    assert DU.no_more_seasons((0, 0, 3, 0)).startswith("At 3 horizons ")


# ------- a 0 with no season to go by: the figure for the newest season only

def test_one_season_still_gets_a_figure():
    raw = series_bytes(END_19, 1)
    rep = D.validate(raw)
    assert {AN.season_of(d) for _, d in CK._newest(rep.records)} == {
        AN.season_of(END_19)}
    got = CK.groundhog_donors(rep)
    assert got["n"] == 0 and got["seasons"] == 6
    assert "Give about 6 more earlier seasons of data." in check(
        raw, kind="rate")


def test_a_season_whose_weeks_fall_after_the_newest_gives_no_figure():
    """The newest week is in a season's second week; the file starts four
    weeks before it, so the season before holds weeks of the window whose
    later weeks (horizons 3 and 4) are not in the file yet: 0 there, but
    not because those seasons give nothing. It gave "about 6" until the
    review of #93 at f2fd03ef: the file holds an earlier season that
    shows nothing either way there, so no figure, and more seasons may
    (eight seasons do)."""
    end = date(2025, 8, 9)
    assert AN.epiweek(end) == 32 and AN.season_of(end) == 2025
    raw = series_bytes(end, 2)
    raw = b"\n".join([raw.split(b"\n")[0]] + [
        ln for ln in raw.split(b"\n")[1:]
        if ln and ln.split(b",")[0] >= b"2025-07-19"]) + b"\n"
    assert counts_of(raw) == (1, 1, 0, 0)
    got = CK.groundhog_donors(D.validate(raw))
    assert got["seasons"] is None and got["unspoken"] == 2
    assert not got["open"] and not got["one_season"]
    html = check(raw, kind="rate")
    assert notice(html).endswith(
        "At 2 horizons no earlier season in the file has a week like it, "
        "but the earlier seasons in the file show nothing either way "
        "there, and more seasons may.")
    assert "Give about" not in html and "would not help" not in html
    more = series_bytes(end, 2 + 6)
    assert min(counts_of(more)) >= 30
