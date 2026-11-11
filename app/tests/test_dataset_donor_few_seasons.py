"""Seasons that say nothing, and one season alone, in the "more seasons"
hint (review of #93 at 42db2a82, findings 1 to 3; checks.groundhog_donors,
checks._seasons_heard, datasets_ui.no_more_seasons).

  1. A season reading 0 throughout says nothing about growth. One series
     with two such seasons and a live newest one said "more seasons like
     these would not help", where six real seasons give (31, 31, 31, 31).
     Such a season is no longer counted either way: the figure was back,
     and since the review at f2fd03ef there is none, the file holding
     earlier seasons: they show nothing either way, and more seasons may
     (test_dataset_donor_nothing_speaks).
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

Review of #93 at ac51731d (finding 4, and the independent check's on the
figure; section 4 below):

  * A season with cases whose window reads 0 did not speak when it was
    the only one: one series with zeros at MMWR weeks 21 to 39, ending at
    week 32, starting in June 2023, said "about 6 more earlier seasons",
    where seasons like it never give a week like it. The June start cuts
    the season before to its summer of zeros, which says nothing;
    started in May, that season has cases and the file said "would not
    help". Such a season now speaks like any season with a case: one
    gives neither a figure nor "would not help", two say "would not
    help". The June and May starts still differ, and both are true of
    their files. Two seasons reading 0 throughout still say nothing.
  * The one-season sentence said "of the group" in a single series, which
    has no group column, and named no group in a file of several. It now
    names none in a file of one group and the group in a file of several.

Review of #93 at f2fd03ef: so does the sentence for a group with no season
that shows it (section 4's last test).
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


def test_1_two_seasons_of_zeros_say_nothing_and_more_seasons_may():
    """Not "would not help". It said "about 6" (an ordinary season) until
    the review of #93 at f2fd03ef: the file holds earlier seasons, so no
    figure; six real seasons bring every horizon off 0, so "may"."""
    got = donors(finding_1())
    assert got["seasons"] is None and got["unspoken"] == 4
    assert not got["open"] and not got["one_season"]
    html = check(finding_1(), kind="rate")
    assert notice(html).endswith(
        "so it will not forecast this data on its own. No earlier season "
        "in the file has a week like it at any horizon, but the earlier "
        "seasons in the file show nothing either way, and more seasons "
        "may.")
    assert "would not help" not in html and "Give about" not in html


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
    # one series, no group column: no group to name (it said "of the
    # group" before the review of #93 at ac51731d)
    assert notice(html).endswith(
        "At 1 horizon the earlier seasons in the file give no week like "
        "it, but only one season says so, and more seasons may.")
    assert "would not help" not in html and "Give about" not in html
    assert "group" not in notice(html)


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
        "it, but only one season says so, and more seasons may.")
    assert DU.no_more_seasons((3, 2, 1, 0), 0, False, 1, group="B") == (
        "At 1 horizon the earlier seasons in the file give no week like "
        "it, but for group 'B' only one season says so, and more seasons "
        "may.")
    assert DU.no_more_seasons((0, 0, 0, 0), 0, False, 1) == (
        "No earlier season in the file has a week like it at any horizon, "
        "but only one season says so, and more seasons may.")
    assert DU.no_more_seasons((3, 2, 0, 0), 0, False, 4) == (
        "At 2 horizons the earlier seasons in the file give no week like "
        "it, but for 4 groups only one season says so, and more seasons "
        "may.")
    # groups with no season that shows it are named first, as before
    assert DU.no_more_seasons((3, 2, 1, 0), 2, True, 1) == (
        "At 1 horizon the earlier seasons in the file give no week like "
        "it, but earlier seasons of the 2 groups without any may.")


def _saturdays(start: date, end: date):
    d = start + timedelta(days=(5 - start.weekday()) % 7)
    while d <= end:
        yield d
        d += timedelta(days=7)


def _live(i: int) -> int:
    return 10 + (i * 7) % 40


def two_groups_one_season() -> bytes:
    """Groups A and B, 0 at MMWR weeks 21 to 39, ending 2025-05-10 (week
    19): A from August 2022 (two earlier seasons), B from August 2023
    (one). Each season's weeks 4 after the window read 0."""
    lines = ["week_ending,group,cases"]
    for i, d in enumerate(_saturdays(date(2022, 8, 1), date(2025, 5, 10))):
        e, s = AN.epiweek(d), AN.season_of(d)
        summer = 20 < e < 40
        lines.append(f"{d},A,{0 if summer else _live(i)}")
        if s >= 2023:
            lines.append(f"{d},B,{0 if summer else _live(i + 3)}")
    return ("\n".join(lines) + "\n").encode()


def test_2_in_a_file_of_several_groups_the_one_is_named():
    """A shows horizon 4 gets nothing through two seasons, B through one:
    the sentence says which group (review of #93 at ac51731d, finding
    4), where "the group" named none."""
    raw = two_groups_one_season()
    rep = D.validate(raw)
    assert rep.summary["groups"] == ["A", "B"]
    got = CK.groundhog_donors(rep)
    assert got["counts"] == (9, 6, 3, 0)
    assert got["seasons"] is None and not got["open"]
    assert got["one_season"] == 1 and got["one_group"] == "B"
    assert H.unescape(notice(check(raw, kind="rate"))).endswith(
        "At 1 horizon the earlier seasons in the file give no week like "
        "it, but for group 'B' only one season says so, and more seasons "
        "may.")


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


# ------------ 4. a season with cases whose window reads 0 speaks alone too

#: the independent check's files end at MMWR week 32 of season 2024-25,
#: in the summer of zeros: the window is weeks 30 to 34
END_4 = date(2024, 8, 10)
#: the summer of zeros
SUMMER = set(range(21, 40))


def summer_start(start: date, end: date = END_4) -> bytes:
    """One series from `start` to `end`: 0 at MMWR weeks 21 to 39, cases
    otherwise."""
    lines = ["week_ending,cases"]
    for i, d in enumerate(_saturdays(start, end)):
        lines.append(f"{d},{0 if AN.epiweek(d) in SUMMER else _live(i)}")
    return ("\n".join(lines) + "\n").encode()


def _window_and_cased(raw: bytes):
    """The earlier seasons' weeks of the donor window with their values,
    and the (group, season)s with a case (checks._cased)."""
    bank = CK._newest(D.validate(raw).records)
    S, E = AN.season_of(END_4), AN.epiweek(END_4)
    window = {(g, d): v for (g, d), v in bank.items()
              if AN.season_of(d) < S
              and AN.calendar_distance(AN.epiweek(d), E)
              <= AN.DEFAULT_BANDWIDTH}
    return window, CK._cased(bank)


def test_4_counts_as_the_check_says():
    assert AN.epiweek(END_4) == 32 and AN.season_of(END_4) == 2024
    for start in (date(2023, 6, 3), date(2023, 8, 5), date(2023, 5, 6)):
        assert counts_of(summer_start(start)) == (0, 0, 0, 0), start


def test_4_seasons_like_the_june_start_never_reach_a_figure():
    """Every June start from 2017 to 2023 counts 0 at every horizon, and
    so does an August start with seven earlier seasons: "about 6 more
    earlier seasons" was false of such a file."""
    for year in range(2017, 2024):
        assert counts_of(summer_start(date(year, 6, 3))) == (0, 0, 0, 0)
    assert counts_of(summer_start(date(2017, 8, 5))) == (0, 0, 0, 0)


@pytest.mark.parametrize("start", [date(2023, 6, 3), date(2023, 8, 5)],
                         ids=["june", "august"])
def test_4_one_season_with_cases_says_more_seasons_may_no_figure(start):
    """June: the season before is in the file as its summer of zeros
    only, so it says nothing, and one season with cases is left. August:
    the file starts with that one season. Either way neither a figure
    nor "would not help"."""
    raw = summer_start(start)
    got = donors(raw)
    assert got["counts"] == (0, 0, 0, 0)
    assert got["seasons"] is None
    assert got["one_season"] == 1 and not got["open"]
    assert got["unspoken"] == 0
    html = check(raw, kind="rate")
    assert notice(html) == (
        "Too little history for the Groundhog: at the newest week it finds "
        "0 weeks like it in earlier seasons and needs 30, so it will not "
        "forecast this data on its own. No earlier season in the file has "
        "a week like it at any horizon, but only one season says so, and "
        "more seasons may.")
    assert "Give about" not in html and "would not help" not in html
    # counts without a population: the Liu-West filter is still offered
    assert notice(check(raw)).endswith(
        "but only one season says so, and more seasons may. Add a "
        "population column so the Liu-West filter can fit it.")


def test_4_may_start_says_would_not_help_also_true_of_its_two_seasons():
    """Started in May, the season before has cases (weeks 18 to 20): two
    seasons with cases give every horizon nothing, so more seasons like
    these would not help, as before."""
    raw = summer_start(date(2023, 5, 6))
    got = donors(raw)
    assert got["seasons"] is None
    assert not got["one_season"] and not got["open"]
    assert notice(check(raw, kind="rate")).endswith(
        "No earlier season in the file has a week like it at any horizon, "
        "so more seasons like these would not help.")


def test_4_june_and_may_starts_differ_and_both_are_true():
    """The two files read the same weeks of the window, all 0; they differ
    only in whether the season before has a case. The June start's
    season before is its summer of zeros, which says nothing, so one
    season speaks ("more seasons may"); the May start's has cases in
    May, so two do ("would not help"). Not a bug: each sentence is true
    of its own file."""
    june, may = summer_start(date(2023, 6, 3)), summer_start(date(2023, 5, 6))
    (wj, cj), (wm, cm) = _window_and_cased(june), _window_and_cased(may)
    assert wj == wm and set(wj.values()) == {0.0} and len(wj) == 6
    assert cj == {("series", 2023)}
    assert cm == {("series", 2022), ("series", 2023)}
    assert "more seasons may" in check(june, kind="rate")
    assert "would not help" in check(may, kind="rate")


def test_4_two_seasons_reading_0_throughout_still_say_nothing():
    """Beside the cases above: the same newest week, two earlier seasons
    reading 0 throughout and cases in the newest. They are no seasons
    with a case, so they say nothing (review of #93 at 42db2a82, finding
    1): neither "would not help" nor, since the review at f2fd03ef, the
    ordinary season's "about 6"; more seasons may."""
    lines = ["week_ending,cases"]
    for i, d in enumerate(_saturdays(date(2022, 8, 6), END_4)):
        lines.append(f"{d},{_live(i) if AN.season_of(d) == 2024 else 0}")
    raw = ("\n".join(lines) + "\n").encode()
    assert counts_of(raw) == (0, 0, 0, 0)
    got = donors(raw)
    assert got["seasons"] is None and got["unspoken"] == 4
    assert not got["one_season"] and not got["open"]
    html = check(raw, kind="rate")
    assert notice(html).endswith(
        "No earlier season in the file has a week like it at any horizon, "
        "but the earlier seasons in the file show nothing either way, and "
        "more seasons may.")
    assert "would not help" not in html and "Give about" not in html


def test_4_a_group_whose_one_season_has_a_quiet_window_is_named():
    """Two groups at the same newest week: A from August 2022 (two
    seasons with cases), B from August 2023 (one). B's season speaks too:
    it is no group "whose seasons show nothing either way", it shows it
    through one season, and the sentence names it."""
    a = summer_start(date(2022, 8, 6)).decode().splitlines()[1:]
    b = summer_start(date(2023, 8, 5)).decode().splitlines()[1:]
    lines = ["week_ending,group,cases"]
    lines += [ln.replace(",", ",A,") for ln in a]
    lines += [ln.replace(",", ",B,") for ln in b]
    raw = ("\n".join(lines) + "\n").encode()
    got = donors(raw)
    assert got["counts"] == (0, 0, 0, 0) and got["seasons"] is None
    assert not got["open"]
    assert got["one_season"] == 1 and got["one_group"] == "B"
    assert H.unescape(notice(check(raw, kind="rate"))).endswith(
        "No earlier season in the file has a week like it at any horizon, "
        "but for group 'B' only one season says so, and more seasons may.")


def test_4_a_group_with_no_earlier_season_is_named():
    """A from August 2022, B from August 2024 (the newest season only):
    A's two seasons show every horizon gets nothing, B has none. The
    sentence said "of the group without any", naming none in a file of
    two (review of #93 at f2fd03ef); it names B."""
    a = summer_start(date(2022, 8, 6)).decode().splitlines()[1:]
    b = summer_start(date(2024, 8, 3)).decode().splitlines()[1:]
    lines = ["week_ending,group,cases"]
    lines += [ln.replace(",", ",A,") for ln in a]
    lines += [ln.replace(",", ",B,") for ln in b]
    raw = ("\n".join(lines) + "\n").encode()
    rep = D.validate(raw)
    assert rep.summary["groups"] == ["A", "B"]
    got = CK.groundhog_donors(rep)
    assert got["counts"] == (0, 0, 0, 0) and got["seasons"] is None
    assert got["open"] == 1 and got["open_new"] is True
    assert got["open_group"] == "B"
    text = H.unescape(notice(check(raw, kind="rate")))
    assert text.endswith(
        "No earlier season in the file has a week like it at any horizon, "
        "but earlier seasons of group 'B', which has none in the file, "
        "may.")
    assert "the group" not in text


def test_4_a_group_whose_seasons_read_0_throughout_is_named():
    """The same A beside a B whose every week reads 0: B has earlier
    seasons, which show nothing either way, and the sentence names it."""
    a = summer_start(date(2022, 8, 6)).decode().splitlines()[1:]
    lines = ["week_ending,group,cases"]
    lines += [ln.replace(",", ",A,") for ln in a]
    lines += [ln.split(",")[0] + ",B,0" for ln in a]
    raw = ("\n".join(lines) + "\n").encode()
    got = donors(raw)
    assert got["counts"] == (0, 0, 0, 0) and got["seasons"] is None
    assert got["open"] == 1 and got["open_new"] is False
    assert got["open_group"] == "B"
    text = H.unescape(notice(check(raw, kind="rate")))
    assert text.endswith(
        "No earlier season in the file has a week like it at any horizon, "
        "but more seasons of group 'B', whose seasons show nothing either "
        "way, may.")
    assert "the group" not in text
