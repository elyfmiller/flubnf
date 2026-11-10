"""One group new to the file does not outweigh the seasons of the rest
(review of #93 at 3120298e, finding 3; checks._seasons_give_nothing).

Case (b) of the review at d160002b: five groups with the newest season
only, beside one small group whose one earlier season gives a horizon
nothing, must keep their figure: real seasons of the five would help. Its
fix asked every group with data to speak through a live season, so the
mirror came out wrong:

  * five groups from August 2019, 0 at MMWR weeks 21 to 39, the file
    ending 2025-05-10 (week 19), and one group with the newest season
    only. Counts (75, 50, 25, 0), and "Give about 1 more earlier season
    of data", where 25 group-seasons show horizon 4 gets nothing: it
    reads weeks 20 to 23, and only week 20 has cases. The one new group
    had no season to speak with, so the other five were not heard.

Now the file shows it when the groups that speak are more than half of
the groups with data (for either rule): the mirror gives no figure, and
(b), where one group of six speaks, keeps its figure.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core import datasets as D
from app.core.datasets import checks as CK
from app.ui import pipeline
from flubnf import analogue as AN

from test_dataset_donor_horizons import check, counts_of, notice  # noqa: E402
from test_datasets_ui import client, isolated          # noqa: E402,F401

#: the file ends at MMWR week 19 of season 2024-25
END = date(2025, 5, 10)
FIVE = "ABCDE"


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


def mirror_bytes(new_from: int | None = None) -> bytes:
    """Groups A to E from August 2019, 0 at MMWR weeks 21 to 39, cases
    otherwise; group "new" from the newest season (2024-25) on, the same
    shape. With `new_from`, "new" starts in that season instead."""
    s_new = AN.season_of(END)
    first = s_new if new_from is None else new_from
    lines = ["week_ending,group,cases"]
    for i, d in enumerate(_saturdays(date(2019, 8, 1), END)):
        e, s = AN.epiweek(d), AN.season_of(d)
        summer = 20 < e < 40
        for j, g in enumerate(FIVE):
            lines.append(f"{d},{g},{0 if summer else _live(i + 3 * j)}")
        if s >= first:
            lines.append(f"{d},new,{0 if summer else _live(i + 20)}")
    return ("\n".join(lines) + "\n").encode()


# ----------------------------------------------------- the review's file

def test_the_mirror_counts_as_the_review_says():
    rep = D.validate(mirror_bytes())
    assert len(rep.summary["groups"]) == 6
    assert AN.epiweek(END) == 19
    assert counts_of(mirror_bytes()) == (75, 50, 25, 0)


def test_seasons_like_these_never_give_horizon_4_a_donor():
    """The truth the check now says: every group with the same earlier
    seasons, the new one too, still leaves horizon 4 at 0."""
    assert counts_of(mirror_bytes(new_from=2019)) == (90, 60, 30, 0)


def test_the_mirror_gives_no_figure():
    raw = mirror_bytes()
    got = CK.groundhog_donors(D.validate(raw))
    assert got["counts"] == (75, 50, 25, 0)
    assert got["seasons"] is None
    html = check(raw, kind="rate")
    assert notice(html).startswith(
        "Too little history for the Groundhog at some horizons: at the "
        "newest week it finds 0 to 75 group-weeks like it")
    assert notice(html).endswith(
        "At 1 horizon no earlier season in the file has a week like it, so "
        "more seasons like these would not help there.")
    assert "about 1 more" not in html and "Give about" not in html


# ------------------------------------------------- the rule on a bank

def _bank(rows) -> dict:
    return {(g, d): float(v) for g, d, v in rows}


def _window(bank, end):
    S, E = AN.season_of(end), AN.epiweek(end)
    return {d for _, d in bank if AN.season_of(d) < S
            and AN.calendar_distance(AN.epiweek(d), E)
            <= AN.DEFAULT_BANDWIDTH}


def test_rule_one_two_groups_that_speak_outweigh_one_new_group():
    """Groups A and B each have one live earlier season whose weeks 4
    later read 0; group C has the newest season only. Two of three groups
    show it: no figure. One of two (the earlier test, one group beside a
    new one) still gives the figure."""
    rows = []
    for d in _saturdays(date(2023, 8, 1), END):
        v = 0 if 20 < AN.epiweek(d) < 40 else 5
        rows += [("A", d, v), ("B", d, v)]
    rows += [("C", d, 5) for d in _saturdays(date(2024, 8, 1), END)]
    bank = _bank(rows)
    window = _window(bank, END)
    counts = CK.donor_counts(bank, [END])[END]
    assert counts[-1] == 0 and min(counts[:-1]) > 0
    assert CK._seasons_give_nothing(bank, window, counts) is True
    # one of two: C's real seasons could still give it donors
    bank = _bank([r for r in rows if r[0] != "B"])
    assert CK._seasons_give_nothing(bank, window,
                                    CK.donor_counts(bank, [END])[END]) is False


def test_rule_two_two_groups_of_dead_seasons_outweigh_one_new_group():
    """Groups A and B each have two earlier seasons reading 0 throughout,
    then the newest with cases; group C the newest only. Every horizon
    counts 0, and two of three groups have two seasons holding the weeks:
    no figure. With A alone beside C, the figure stays."""
    rows = []
    for d in _saturdays(date(2022, 8, 1), END):
        v = 5 if AN.season_of(d) == AN.season_of(END) else 0
        rows += [("A", d, v), ("B", d, v)]
    rows += [("C", d, 5) for d in _saturdays(date(2024, 8, 1), END)]
    bank = _bank(rows)
    window = _window(bank, END)
    counts = CK.donor_counts(bank, [END])[END]
    assert tuple(counts) == (0, 0, 0, 0)
    assert CK._seasons_give_nothing(bank, window, counts) is True
    bank = _bank([r for r in rows if r[0] != "B"])
    assert CK._seasons_give_nothing(bank, window,
                                    CK.donor_counts(bank, [END])[END]) is False
