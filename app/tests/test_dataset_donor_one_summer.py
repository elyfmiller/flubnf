"""One summer of zeros that straddles 1 August is one season in the "more
seasons" hint, not two (review of #93 at d415a9fa, finding 2;
checks._seasons_heard, datasets_ui.no_more_seasons).

One series from 2022-10-01 with 0 at MMWR weeks 21 to 39 of 2023 only,
ending at week 32 of 2024 (2024-08-10): the donor window is weeks 30 to
34, and week 30 of 2023 (2023-07-29) falls in season 2022-23 while weeks
31 to 34 fall in 2023-24. Counted by season label, that one run of zeros
was two seasons showing that horizons 3 and 4 get nothing, and the check
said "more seasons like these would not help there", although one season
is too few to say so (review of #93 at 42db2a82, finding 2). Ending at
week 31 it said the same; ending at week 29, 30, 33 or 34, "only one
season says so". Begun in 2016 with cases in the other summers, the file
counts (31, 31, 30, 30) at week 32: more seasons do help.

The check now counts passes of the window, a year apart counted back from
the newest week, in place of season labels: the summer of 2023 is one
pass whichever seasons it falls in. Two summers of zeros are still two,
and still say "would not help".
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core import datasets as D
from app.core.datasets import checks as CK
from app.ui import pipeline
from flubnf import analogue as AN

from test_dataset_donor_horizons import (               # noqa: E402
    check, counts_of, notice)
from test_datasets_ui import client, isolated          # noqa: E402,F401

#: the review's file ends at MMWR week 32 of 2024 (season 2024-25)
END = date(2024, 8, 10)
#: the same file ending at weeks 29 to 34: (newest week, its counts)
ENDS = {
    date(2024, 7, 20): (29, (0, 0, 0, 0)),
    date(2024, 7, 27): (30, (0, 0, 0, 0)),
    date(2024, 8, 3): (31, (2, 1, 0, 0)),
    date(2024, 8, 10): (32, (1, 1, 0, 0)),
    date(2024, 8, 17): (33, (0, 0, 0, 0)),
    date(2024, 8, 24): (34, (0, 0, 0, 0)),
}
#: the summer of zeros
SUMMER = set(range(21, 40))


@pytest.fixture(autouse=True)
def engine_ready(monkeypatch):
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "ready")


def _saturdays(start: date, end: date):
    d = start + timedelta(days=(5 - start.weekday()) % 7)
    while d <= end:
        yield d
        d += timedelta(days=7)


def summers(start: date = date(2022, 10, 1), end: date = END,
            zero=(2023,)) -> bytes:
    """One series from `start` to `end`: 0 at MMWR weeks 21 to 39 of the
    calendar years `zero`, cases otherwise."""
    lines = ["week_ending,cases"]
    for i, d in enumerate(_saturdays(start, end)):
        z = d.year in zero and AN.epiweek(d) in SUMMER
        lines.append(f"{d},{0 if z else 10 + (i * 7) % 40}")
    return ("\n".join(lines) + "\n").encode()


def donors(raw: bytes) -> dict:
    return CK.groundhog_donors(D.validate(raw))


def test_counts_as_the_review_says():
    # the summer of 2023 falls in two seasons
    assert AN.epiweek(date(2023, 7, 29)) == 30
    assert AN.season_of(date(2023, 7, 29)) == 2022
    assert AN.epiweek(date(2023, 8, 5)) == 31
    assert AN.season_of(date(2023, 8, 5)) == 2023
    for end, (week, counts) in ENDS.items():
        assert AN.epiweek(end) == week, end
        assert counts_of(summers(end=end)) == counts, end
    # begun in 2016, with cases in the other summers
    assert counts_of(summers(date(2016, 10, 1))) == (31, 31, 30, 30)


@pytest.mark.parametrize("end", list(ENDS), ids=lambda d: f"week{ENDS[d][0]}")
def test_one_summer_across_1_august_is_one_season(end):
    """Whichever week the file ends at, one summer shows the horizons at
    0 get nothing: neither a figure nor "would not help", and more
    seasons may. Weeks 31 and 32 said "would not help there"."""
    raw = summers(end=end)
    got = donors(raw)
    assert got["seasons"] is None
    assert got["one_season"] == 1 and not got["open"]
    assert got["unspoken"] == 0
    html = check(raw, kind="rate")
    zeros = sum(1 for c in ENDS[end][1] if not c)
    assert notice(html).endswith(
        "No earlier season in the file has a week like it at any horizon, "
        "but only one season says so, and more seasons may."
        if zeros == 4 else
        f"At {zeros} horizons the earlier seasons in the file give no week "
        "like it, but only one season says so, and more seasons may.")
    assert "would not help" not in html and "Give about" not in html


def test_two_summers_of_zeros_still_say_would_not_help():
    """Begun a year earlier with the summer of 2022 at 0 too: two passes
    of the window show horizons 3 and 4 get nothing, so more seasons like
    these would not help there, as before."""
    raw = summers(date(2021, 10, 2), zero=(2022, 2023))
    assert counts_of(raw) == (1, 1, 0, 0)
    got = donors(raw)
    assert got["seasons"] is None
    assert not got["one_season"] and not got["open"]
    assert notice(check(raw, kind="rate")).endswith(
        "At 2 horizons no earlier season in the file has a week like it, "
        "so more seasons like these would not help there.")
