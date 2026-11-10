"""The Groundhog's donor weeks horizon by horizon, in the upload check
(review 3 of #93: S2 2, S3 9 and 14).

  * the check's badge, its notice and its fix go by one count, the newest
    week's scarcest horizon, as the Forecast tab's line does
    (datasets_ui.donor_weeks): "ready" only when every horizon has
    enough, "some horizons only" when some do, "too little history"
    when none does. A file whose horizons find 32, 24, 16 and 8 never
    reads "ready";
  * "about N more earlier seasons" holds at a newest week 53, whose
    window takes four weeks of an ordinary season, not five;
  * with several groups the counts are group-weeks, and say so;
  * the notice dataset_checks stores (meta.json) keeps its words.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

from app.core import datasets as D
from app.core.datasets import checks as CK
from app.ui import datasets_ui as DU
from app.ui import pipeline
from flubnf import analogue as AN

from test_dataset_engines import grouped_bytes         # noqa: E402
from test_datasets_ui import (client, isolated,        # noqa: E402,F401
                              stored)


def series_bytes(end: date, seasons: int, groups=("",), *,
                 low=None, high=None) -> bytes:
    """`seasons` flu seasons of weekly counts ending at `end` (a Saturday),
    the first from its season's first Saturday in August. One series when
    `groups` is ("",). With `low` and `high`, weeks whose MMWR week lies
    after `high` and before `low` read 0 (a summer without cases)."""
    d = date(end.year - (end.month < 8) - seasons + 1, 8, 1)
    d += timedelta(days=(5 - d.weekday()) % 7)
    one = groups == ("",)
    lines = ["week_ending,cases" if one else "week_ending,group,cases"]
    i = 0
    while d <= end:
        e = AN.epiweek(d)
        for j, g in enumerate(groups):
            v = 10 + (i * 7 + j * 3) % 40
            if low is not None and high < e < low:
                v = 0
            lines.append(f"{d.isoformat()},{v}" if one else
                         f"{d.isoformat()},{g},{v}")
        d += timedelta(days=7)
        i += 1
    return ("\n".join(lines) + "\n").encode()


#: the review's two files: one group, values zero outside MMWR weeks 40 to
#: 20, ending at week 18 (2025-05-03); nine seasons find 32, 24, 16 and 8
#: donor weeks at the newest week, seven find 24, 18, 12 and 6
END_18 = date(2025, 5, 3)


def scenario(seasons: int) -> bytes:
    return series_bytes(END_18, seasons, low=40, high=20)


def counts_of(raw: bytes) -> tuple:
    """The donor weeks at each horizon at the file's newest week."""
    rep = D.validate(raw)
    assert rep.ok, [str(p) for p in rep.problems]
    bank = CK._newest(rep.records)
    last = max(d for _, d in bank)
    return CK.donor_counts(bank, [last])[last]


def check(raw: bytes, kind: str = "count") -> str:
    j = client.post("/data/datasets/check",
                    files={"file": ("d.csv", raw, "text/csv")},
                    data={"kind": kind}).json()
    assert j["ok"]
    return " ".join(j["html"].split())


def badge(html: str) -> tuple:
    """The Groundhog's badge in the preview's Models row."""
    box = html[html.index('aria-label="Models"'):]
    return re.search(r'<dt>Groundhog \(own data\)</dt><dd><span '
                     r'class="uk-stat-v"><span class="uk-badge uk-badge--'
                     r'(\w+)" data-state="\w+"><svg.*?</svg><span '
                     r'class="uk-badge-t">([^<]+)</span>', box).groups()


def notice(html: str) -> str:
    """The Groundhog's alert line under the preview's heading."""
    m = re.search(r'id="dsup-data-gh".*?(Too little history[^<]*)<', html)
    return m.group(1).strip() if m else ""


@pytest.fixture(autouse=True)
def engine_ready(monkeypatch):
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "ready")


# --------------------------------------------- one count for every horizon

def test_the_review_files_count_as_the_review_says():
    assert AN.epiweek(END_18) == 18
    assert counts_of(scenario(9)) == (32, 24, 16, 8)
    assert counts_of(scenario(7)) == (24, 18, 12, 6)


def test_a_file_short_at_its_later_horizons_is_not_ready():
    """32, 24, 16 and 8: no stored notice (horizon 1 has its 30), yet a
    run forecasts one horizon of four. The badge, the notice and the fix
    all go by the 8, the count the Forecast tab's line quotes."""
    raw = scenario(9)
    rep = D.validate(raw)
    CK.dataset_checks(rep)
    assert not [w for w in rep.warnings if w.startswith(CK.TOO_LITTLE_HISTORY)]
    html = check(raw)
    assert badge(html) == ("warn", "some horizons only")
    assert notice(html) == (
        "Too little history for the Groundhog at some horizons: at the "
        "newest week it finds 8 to 32 weeks like it in earlier seasons, "
        "depending on the horizon, and needs 30 at each, so it will "
        "forecast 1 of its 4 horizons on its own. Add a population column "
        "so the Liu-West filter can fit it, or give about 22 more earlier "
        "seasons of data.")
    assert "ready" not in badge(html)[1]
    # each earlier season gives the furthest horizon one donor week here
    # (the zeros from MMWR week 21): 22 more seasons bring the 8 to 30
    assert min(counts_of(scenario(9 + 22))) >= 30 \
        > min(counts_of(scenario(9 + 21)))
    # the Forecast tab's line, on the same file stored
    ds = stored(raw, "Thin")
    newest = ds.forecast_dates()[-1]
    assert DU.donor_weeks(ds)[newest] == 8 == min(counts_of(raw))


def test_a_file_short_everywhere_quotes_the_count_its_fix_is_worked_from():
    """24, 18, 12 and 6: the stored notice quotes horizon 1's 24; the
    check quotes 6 to 24 and works its "about N more seasons" from the 6,
    at what each earlier season gave it (one week, not five)."""
    raw = scenario(7)
    html = check(raw, kind="rate")
    assert badge(html) == ("warn", "too little history")
    assert notice(html) == (
        "Too little history for the Groundhog: at the newest week it finds "
        "6 to 24 weeks like it in earlier seasons, depending on the "
        "horizon, and needs 30, so it will not forecast this data on its "
        "own. Give about 24 more earlier seasons of data.")
    # 24 more seasons bring the 6 to 30: the fix is worked from that count
    assert min(counts_of(scenario(7 + 24))) >= 30 \
        > min(counts_of(scenario(7 + 23)))
    # the stored notice keeps its words (meta.json is unchanged)
    ds = stored(raw, "Short", kind="rate")
    (w,) = [w for w in ds.meta["warnings"] if "Groundhog" in w]
    assert w == ("Too little history for the Groundhog: at the newest week "
                 "it finds 24 weeks like it in earlier seasons and needs 30, "
                 "so it will not forecast this data on its own.")


def test_a_file_with_enough_at_every_horizon_is_ready():
    raw = series_bytes(END_18, 9)
    assert min(counts_of(raw)) >= 30
    html = check(raw)
    assert badge(html) == ("ok", "ready")
    assert notice(html) == "" and "Too little history" not in html


def test_one_count_however_the_horizons_fall():
    """The badge's state for each mix of horizons: by the fewest."""
    donors = {"counts": (31, 30, 29, 0), "need": 30, "enough": 2}
    assert DU.groundhog_notice(donors, 1).startswith(
        "Too little history for the Groundhog at some horizons: at the "
        "newest week it finds 0 to 31 weeks")
    assert "it will forecast 2 of its 4 horizons" in \
        DU.groundhog_notice(donors, 1)
    assert DU.groundhog_notice({"counts": (30,) * 4, "need": 30,
                                "enough": 4}, 1) == ""
    assert DU.groundhog_notice({"counts": (12,) * 4, "need": 30,
                                "enough": 0}, 1) == (
        "Too little history for the Groundhog: at the newest week it finds "
        "12 weeks like it in earlier seasons and needs 30, so it will not "
        "forecast this data on its own.")


# ------------------------------------------- about N more, at a week 53

def test_a_week_53_window_takes_four_weeks_of_an_ordinary_season():
    assert CK.window_weeks_a_season(53) == 4
    assert {CK.window_weeks_a_season(e) for e in range(1, 53)} == {5}
    assert CK.window_weeks_a_season(53, 3) == 6


@pytest.mark.parametrize("end", [date(2026, 1, 3), date(2025, 1, 4),
                                 date(2025, 11, 15), date(2025, 3, 8)])
@pytest.mark.parametrize("seasons", [2, 3, 4, 5, 6])
def test_about_n_more_seasons_is_enough(end, seasons):
    """Adding the N the check states brings the newest week's fewest
    horizon to the need, at a week 53 too (2026-01-03 ends MMWR week 53
    of 2025; the review found 24 to 29 there in 8 of 10 cases)."""
    raw = series_bytes(end, seasons)
    rep = D.validate(raw)
    short = CK.groundhog_shortfall(rep)
    if short is None:
        return
    more = series_bytes(end, seasons + short["seasons"])
    assert min(counts_of(more)) >= 30, (end, seasons, short)


def test_the_epiweek_53_end_is_one():
    assert AN.epiweek(date(2026, 1, 3)) == 53
    raw = series_bytes(date(2026, 1, 3), 3)
    short = CK.groundhog_shortfall(D.validate(raw))
    assert short == {"n": 8, "need": 30, "seasons": 6}


# ------------------------------------------------- several groups' weeks

def test_several_groups_count_group_weeks_and_say_so():
    """Each group's weeks count apart (the engine's 30 is of group-weeks):
    two groups of two earlier seasons find 20 group-weeks, and one more
    season of both brings 10 more."""
    raw = grouped_bytes(groups=("North", "South"), start=date(2023, 8, 5),
                        end=date(2025, 11, 15), pop=False, rate=True)
    html = check(raw, kind="rate")
    assert notice(html) == (
        "Too little history for the Groundhog: at the newest week it finds "
        "20 group-weeks like it in earlier seasons and needs 30, so it will "
        "not forecast this data on its own. Give about 1 more earlier "
        "season of data.")
    assert badge(html) == ("warn", "too little history")


def test_the_forecast_page_says_what_its_counts_count():
    """The Forecast tab's donor line counts the same group-weeks: its
    context names the unit for the line's words (datasets_ui.donor_unit)."""
    from test_datasets_ui import TEMPLATE
    three = stored(TEMPLATE.read_bytes(), "Kids")
    one = stored(scenario(9), "Thin")
    assert len(three.groups) == 3 and len(one.groups) == 1
    got = {ds.id: client.get(f"/forecast?source={ds.id}").context["dataset"]
           for ds in (three, one)}
    assert got[three.id]["donor_unit"] == "group-weeks"
    assert got[one.id]["donor_unit"] == "weeks"
    assert got[one.id]["donor_weeks"][one.forecast_dates()[-1]] == 8
