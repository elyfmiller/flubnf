"""Groups whose seasons give a horizon nothing beside groups with no earlier
season: neither a figure nor "would not help" (review of #93 at d5a7eb16,
findings 1 and 2; checks._seasons_say, datasets_ui.no_more_seasons).

Each rule that counted groups moved the wrong answer to another mix:

  1. three small groups from August 2024 (1 a week through 2025-01-18,
     then 0) beside two large groups with the newest season only, the
     file ending 2026-01-17: counts (9, 6, 3, 0) and "more seasons like
     these would not help there", where three real earlier seasons of
     the two large groups give (39, 36, 33, 30);
  2. five groups from August 2019, 0 at MMWR weeks 21 to 39, beside five
     new groups, the file ending 2025-05-10: counts (75, 50, 25, 0) and
     "about 1 more earlier season", where seasons like the five's never
     give horizon 4 a donor.

Now no count decides: where some groups show it and others have no
earlier season, the check says the earlier seasons in the file give no
week like it at that horizon and that seasons of the groups without any may.
The figure and "would not help" stay for where every group agrees.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core import datasets as D
from app.core.datasets import checks as CK
from app.ui import datasets_ui as DU
from app.ui import pipeline
from flubnf import analogue as AN

from test_dataset_donor_horizons import check, counts_of, notice  # noqa: E402
from test_datasets_ui import client, isolated          # noqa: E402,F401

#: case 1 ends at MMWR week 2 of season 2025-26
END_1 = date(2026, 1, 17)
#: its small groups read 1 up to here, 0 after
SMALL_LAST = date(2025, 1, 18)
#: case 2 ends at MMWR week 19 of season 2024-25
END_2 = date(2025, 5, 10)


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
    return ("\n".join(["week_ending,group,cases", *lines]) + "\n").encode()


def case1_bytes(real_seasons: int = 0) -> bytes:
    """Small groups s1 to s3 from August 2024, 1 a week through
    SMALL_LAST, 0 after; large groups L1 and L2 with the newest season
    only, or `real_seasons` more seasons with cases before it."""
    s_new = AN.season_of(END_1)
    first = s_new - real_seasons
    lines = []
    for i, d in enumerate(_saturdays(date(min(2024, first), 8, 1), END_1)):
        s = AN.season_of(d)
        if s >= first:
            for j, g in enumerate(("L1", "L2")):
                lines.append(f"{d},{g},{100 + _live(i + 5 * j)}")
        if s >= 2024:
            for g in ("s1", "s2", "s3"):
                lines.append(f"{d},{g},{1 if d <= SMALL_LAST else 0}")
    return _csv(lines)


def case2_bytes(new_from: int | None = None) -> bytes:
    """Old groups A to E from August 2019, new groups N1 to N5 from the
    newest season (or season `new_from`), all 0 at MMWR weeks 21 to 39."""
    first = AN.season_of(END_2) if new_from is None else new_from
    lines = []
    for i, d in enumerate(_saturdays(date(2019, 8, 1), END_2)):
        v = 0 if 20 < AN.epiweek(d) < 40 else None
        for j, g in enumerate("ABCDE"):
            lines.append(f"{d},{g},{_live(i + 3 * j) if v is None else 0}")
        if AN.season_of(d) >= first:
            for j in range(1, 6):
                lines.append(
                    f"{d},N{j},{_live(i + 7 * j) if v is None else 0}")
    return _csv(lines)


# -------------------------------------------- 1. three small, two large

def test_case_1_counts_as_the_review_says():
    rep = D.validate(case1_bytes())
    assert sorted(rep.summary["groups"]) == ["L1", "L2", "s1", "s2", "s3"]
    assert AN.epiweek(END_1) == 2
    assert counts_of(case1_bytes()) == (9, 6, 3, 0)


def test_case_1_real_seasons_of_the_large_groups_would_help():
    assert counts_of(case1_bytes(real_seasons=3)) == (39, 36, 33, 30)


def test_case_1_says_neither_figure_nor_would_not_help():
    raw = case1_bytes()
    got = CK.groundhog_donors(D.validate(raw))
    assert got["counts"] == (9, 6, 3, 0)
    assert got["seasons"] is None
    assert got["open"] == 2 and got["open_new"] is True
    html = check(raw, kind="rate")
    assert notice(html).endswith(
        "At 1 horizon the earlier seasons in the file give no week like "
        "it, but earlier seasons of the 2 groups without any may.")
    assert "would not help" not in html and "Give about" not in html


# ------------------------------------------------ 2. five old, five new

def test_case_2_counts_as_the_review_says():
    rep = D.validate(case2_bytes())
    assert len(rep.summary["groups"]) == 10
    assert counts_of(case2_bytes()) == (75, 50, 25, 0)


def test_case_2_seasons_like_the_old_ones_never_give_horizon_4_a_donor():
    assert counts_of(case2_bytes(new_from=2019))[-1] == 0


def test_case_2_says_neither_figure_nor_would_not_help():
    raw = case2_bytes()
    got = CK.groundhog_donors(D.validate(raw))
    assert got["counts"] == (75, 50, 25, 0)
    assert got["seasons"] is None
    assert got["open"] == 5 and got["open_new"] is True
    html = check(raw, kind="rate")
    assert notice(html).endswith(
        "At 1 horizon the earlier seasons in the file give no week like "
        "it, but earlier seasons of the 5 groups without any may.")
    assert "would not help" not in html and "about 1 more" not in html


def test_where_every_group_agrees_would_not_help_stays():
    """The new groups given the old ones' seasons: every group shows
    horizon 4 gets nothing, so more seasons like these would not help."""
    raw = case2_bytes(new_from=2019)
    got = CK.groundhog_donors(D.validate(raw))
    assert got["seasons"] is None
    assert not got.get("open") and not got.get("open_new")
    assert notice(check(raw, kind="rate")).endswith(
        "At 1 horizon no earlier season in the file has a week like it, so "
        "more seasons like these would not help there.")


def test_each_side_of_case_1_alone():
    """The small groups alone: each one's season finds donors at
    horizons 1 to 3 and none at 4, so every group agrees, but through one
    season each: no figure, and not "would not help" either (review of
    #93 at 42db2a82, finding 2). The large groups alone: one season, no
    group shows anything, so the figure (an ordinary season of each)."""
    raw = case1_bytes()
    lines = raw.decode().splitlines()
    small = _csv(ln for ln in lines[1:] if ",s" in ln)
    got = CK.groundhog_donors(D.validate(small))
    assert got["counts"] == (9, 6, 3, 0)          # the large add none
    assert got["seasons"] is None and not got.get("open")
    assert got["one_season"] == 3
    html = check(small, kind="rate")
    assert notice(html).endswith(
        "At 1 horizon the earlier seasons in the file give no week like "
        "it, but for 3 groups only one season says so, and more seasons "
        "may.")
    assert "would not help" not in html
    large = _csv(ln for ln in lines[1:] if ",L" in ln)
    got = CK.groundhog_donors(D.validate(large))
    assert got["n"] == 0 and got["seasons"] == 3 and not got.get("open")
    assert notice(check(large, kind="rate")).endswith(
        "Give about 3 more earlier seasons of data.")


# ----------------------------------------------- the words, every shape

def test_the_words_for_each_shape():
    assert DU.no_more_seasons((5, 0, 0, 0), 1, True) == (
        "At 3 horizons the earlier seasons in the file give no week like "
        "it, "
        "but earlier seasons of the group without any may.")
    assert DU.no_more_seasons((0, 0, 0, 0), 3, True) == (
        "No earlier season in the file has a week like it at any horizon, "
        "but earlier seasons of the 3 groups without any may.")
    assert DU.no_more_seasons((4, 0), 2, False) == (
        "At 1 horizon the earlier seasons in the file give no week like "
        "it, "
        "but more seasons of the 2 groups whose seasons show nothing "
        "either way may.")
    # every group agrees: as before
    assert DU.no_more_seasons((4, 0)) == (
        "At 1 horizon no earlier season in the file has a week like it, so "
        "more seasons like these would not help there.")
