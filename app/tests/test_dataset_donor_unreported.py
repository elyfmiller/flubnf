"""A horizon at 0 counts in "would not help there" only where a season
speaks for it (review of #93 at ac51731d, finding 3; checks._seasons_heard,
datasets_ui.no_more_seasons).

A hubverse file may leave weeks without a value (NA rows are dropped). Two
earlier seasons with week 3 at 0 and weeks 4 to 8 not reported, the file
ending at MMWR week 2, count (4, 2, 0, 0): horizon 3 reads week 3, which
reads 0 in both seasons, but horizon 4 reads only weeks nobody reported.
The check said "At 2 horizons no earlier season in the file has a week
like it, so more seasons like these would not help there", reading the
unreported weeks as proof; with those weeks reported the counts are (6,
6, 6, 8). Now it counts horizon 3 alone, and says of horizon 4 that the
file's seasons show nothing either way there and more seasons may.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core import datasets as D
from app.core.datasets import checks as CK
from app.ui import datasets_ui as DU
from app.ui import pipeline
from flubnf import analogue as AN

from test_dataset_donor_horizons import (               # noqa: E402
    check, counts_of, notice)
from test_datasets_ui import client, isolated          # noqa: E402,F401

#: the file ends at MMWR week 2 of season 2025-26
END = date(2026, 1, 17)
HEADER = "target_end_date,location,location_name,observation"


@pytest.fixture(autouse=True)
def engine_ready(monkeypatch):
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "ready")


def _saturdays(start: date, end: date):
    d = start + timedelta(days=(5 - start.weekday()) % 7)
    while d <= end:
        yield d
        d += timedelta(days=7)


def unreported(reported: bool = False) -> bytes:
    """One location from August 2023 to END: in the two earlier seasons
    week 3 reads 0 and weeks 4 to 8 are NA (17 a week when `reported`);
    cases otherwise."""
    rows = [HEADER]
    for i, d in enumerate(_saturdays(date(2023, 8, 1), END)):
        e, s = AN.epiweek(d), AN.season_of(d)
        v = str(10 + (i * 7) % 40)
        if s < AN.season_of(END) and e == 3:
            v = "0"
        elif s < AN.season_of(END) and 4 <= e <= 8:
            v = "17" if reported else "NA"
        rows.append(f"{d},01,Alabama,{v}")
    return ("\n".join(rows) + "\n").encode()


def test_counts_as_the_review_says():
    assert AN.epiweek(END) == 2
    rep = D.validate(unreported())
    assert rep.summary["format"] == "hubverse"
    assert rep.summary["na_dropped"] == 10
    assert counts_of(unreported()) == (4, 2, 0, 0)
    assert counts_of(unreported(reported=True)) == (6, 6, 6, 8)


def test_the_unreported_horizon_is_not_counted_in_would_not_help():
    got = CK.groundhog_donors(D.validate(unreported()))
    assert got["counts"] == (4, 2, 0, 0)
    assert got["seasons"] is None
    assert not got["open"] and not got["one_season"]
    assert got["unspoken"] == 1
    html = check(unreported(), kind="rate")
    assert notice(html).endswith(
        "At 1 horizon no earlier season in the file has a week like it, so "
        "more seasons like these would not help there. At 1 more horizon "
        "there is none either, but the earlier seasons in the file show "
        "nothing either way there, and more seasons may.")
    assert "At 2 horizons" not in html


def test_where_every_horizon_at_0_is_spoken_for_nothing_is_added():
    """R1's shape: each earlier season holds the weeks horizon 4 reads."""
    from test_dataset_donor_no_figure import r1
    got = CK.groundhog_donors(D.validate(r1(13)))
    assert got["counts"] == (36, 24, 12, 0) and got["unspoken"] == 0
    assert "there is none either" not in check(r1(13), kind="rate")


def test_the_words_with_horizons_nobody_speaks_for():
    assert DU.no_more_seasons((4, 2, 0, 0), unspoken=1) == (
        "At 1 horizon no earlier season in the file has a week like it, so "
        "more seasons like these would not help there. At 1 more horizon "
        "there is none either, but the earlier seasons in the file show "
        "nothing either way there, and more seasons may.")
    assert DU.no_more_seasons((0, 0, 0, 0), 0, False, 1, unspoken=2) == (
        "At 2 horizons the earlier seasons in the file give no week like "
        "it, but only one season says so, and more seasons may. At 2 more "
        "horizons there is none either, but the earlier seasons in the "
        "file show nothing either way there, and more seasons may.")
    # every horizon at 0 spoken for: as before
    assert DU.no_more_seasons((0, 0, 0, 0)) == (
        "No earlier season in the file has a week like it at any horizon, "
        "so more seasons like these would not help.")
