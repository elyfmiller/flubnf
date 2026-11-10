""""More seasons like these would not help" judged group by group (review
of #93 at d160002b, finding 2; checks._seasons_say).

Rule one said "no figure" when every group-season holding a pair of weeks
(a week of the donor window and the week the horizon reads) found donor
weeks at another horizon. Two shapes came out wrong:

  * (a) a dead season beside live ones: two groups, values 0 at MMWR
    weeks 21 to 39, the file ending 2025-05-10 (week 19); group A has
    2022-23 all 0 and 2023-24 with cases, group B 2023-24 only. Counts
    (6, 4, 2, 0), and "about 3 more earlier seasons", where horizon 4
    reads weeks 21 to 23 and so never gets a donor: with 12 seasons with
    cases it is (72, 48, 24, 0). The dead season found nothing anywhere,
    so it failed the subset test.
  * (b) one small group speaking for the rest: five groups with the
    newest season only, and one small group whose one earlier season
    reads 1 through 2025-01-18 and 0 after. "More seasons like these
    would not help there", where real seasons of the five groups would.

Now a season that finds nothing at any horizon is left out, and every
group with data must speak through a live season: (a) gives no figure.
Each group of (a) speaks through one season only, too few for "would not
help" (review of #93 at 42db2a82, finding 2): the check says more
seasons may.
In (b) the small group speaks and the five have no earlier season: since
the review of #93 at d5a7eb16 (findings 1 and 2) no count of groups
decides, so (b) gives neither its figure nor "would not help": the
earlier seasons in the file give no week like it there, and seasons of
the five may (test_dataset_donor_mixed_groups).
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

#: (a) ends at MMWR week 19 of season 2024-25
END_A = date(2025, 5, 10)
#: (b) ends at MMWR week 2 of season 2025-26
END_B = date(2026, 1, 17)
#: the small group's earlier season reads 1 up to here, 0 after
SMALL_LAST = date(2025, 1, 18)


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


def a_bytes(live_before: int = 0) -> bytes:
    """(a): groups A and B, 0 at MMWR weeks 21 to 39. A: 2022-23 all 0,
    then cases; B from 2023-24. With `live_before`, both groups have that
    many more seasons with cases before 2022-23, and B has 2022-23 too."""
    first = 2022 - live_before
    lines = ["week_ending,group,cases"]
    for i, d in enumerate(_saturdays(date(first, 8, 1), END_A)):
        e, s = AN.epiweek(d), AN.season_of(d)
        summer = 20 < e < 40
        lines.append(f"{d},A,{0 if summer or s == 2022 else _live(i)}")
        if s >= 2023 or live_before:
            lines.append(f"{d},B,{0 if summer else _live(i + 3)}")
    return ("\n".join(lines) + "\n").encode()


def b_bytes(real_seasons: int = 0) -> bytes:
    """(b): groups A to E with the newest season only; the small group
    from August 2024, 1 a week through SMALL_LAST and 0 after. With
    `real_seasons`, A to E also have that many earlier seasons with cases
    (season 2024-25 and before)."""
    s_new = AN.season_of(END_B)
    first = min(2024, s_new - real_seasons)
    lines = ["week_ending,group,cases"]
    for i, d in enumerate(_saturdays(date(first, 8, 1), END_B)):
        s = AN.season_of(d)
        if s >= s_new - real_seasons:
            for j, g in enumerate("ABCDE"):
                lines.append(f"{d},{g},{_live(i + 3 * j)}")
        if s >= 2024:
            lines.append(f"{d},small,{1 if d <= SMALL_LAST else 0}")
    return ("\n".join(lines) + "\n").encode()


# ------------------------------------------- (a): a dead season beside live

def test_a_counts_as_the_review_says():
    assert AN.epiweek(END_A) == 19
    assert counts_of(a_bytes()) == (6, 4, 2, 0)


def test_a_horizon_4_never_gets_a_donor():
    """The truth the check now says: seasons like these, however many,
    leave horizon 4 at 0. Eleven more seasons of both groups (25
    group-seasons with cases) give the others three a season each."""
    assert counts_of(a_bytes(live_before=11)) == (75, 50, 25, 0)


def test_a_gives_no_figure():
    raw = a_bytes()
    rep = D.validate(raw)
    assert len(rep.summary["groups"]) == 2
    got = CK.groundhog_donors(rep)
    assert got["counts"] == (6, 4, 2, 0) and got["seasons"] is None
    assert got["one_season"] == 2 and not got["open"]
    html = check(raw, kind="rate")
    assert notice(html).endswith(
        "At 1 horizon the earlier seasons in the file give no week like "
        "it, but for 2 groups only one season says so, and more seasons "
        "may.")
    assert "about 3 more" not in html and "would not help" not in html


# ---------------------------------- (b): one small group, five new groups

def test_b_counts_as_the_review_says():
    rep = D.validate(b_bytes())
    assert len(rep.summary["groups"]) == 6
    assert counts_of(b_bytes()) == (3, 2, 1, 0)


def test_b_real_seasons_of_the_five_groups_would_help():
    """The truth the figure stands for: the five groups' own seasons bring
    horizon 4 to its 30, the small group's zeros notwithstanding."""
    assert min(counts_of(b_bytes(real_seasons=2))) >= 30


def test_b_says_seasons_of_the_five_may():
    raw = b_bytes()
    got = CK.groundhog_donors(D.validate(raw))
    assert got["counts"] == (3, 2, 1, 0) and got["seasons"] is None
    assert got["open"] == 5 and got["open_new"] is True
    html = check(raw, kind="rate")
    assert notice(html).endswith(
        "At 1 horizon the earlier seasons in the file give no week like "
        "it, but earlier seasons of the 5 groups without any may.")
    assert "would not help" not in html and "Give about" not in html


# ------------------------------------------------ the rule, group by group

def _bank(rows) -> dict:
    return {(g, d): float(v) for g, d, v in rows}


def test_a_group_with_only_dead_seasons_does_not_speak():
    """Group A's live season shows the weeks 4 later read 0; group B's
    one earlier season is all 0 and so says nothing: B could still gain
    from real seasons. Neither a figure (A's seasons show an ordinary one
    gives horizon 4 nothing) nor "would not help"."""
    raw = a_bytes().decode().splitlines()
    out = [raw[0]]
    for ln in raw[1:]:
        d, g, v = ln.split(",")
        if g == "B" and AN.season_of(date.fromisoformat(d)) == 2023:
            v = "0"
        out.append(",".join((d, g, v)))
    raw = ("\n".join(out) + "\n").encode()
    got = CK.groundhog_donors(D.validate(raw))
    assert got["counts"][-1] == 0
    assert got["seasons"] is None
    assert got["open"] == 1 and got["open_new"] is False
    html = check(raw, kind="rate")
    assert notice(html).endswith(
        "At 1 horizon the earlier seasons in the file give no week like "
        "it, but more seasons of the group whose seasons show nothing "
        "either way may.")
    assert "would not help" not in html and "Give about" not in html


def test_the_rule_itself_on_a_bank():
    """One group, one live season whose weeks 4 later read 0, one dead
    season: the dead one is left out, the live one speaks."""
    end = END_A
    S, E = AN.season_of(end), AN.epiweek(end)
    rows = []
    for d in _saturdays(date(2022, 8, 1), end):
        e, s = AN.epiweek(d), AN.season_of(d)
        rows.append(("A", d, 0 if (20 < e < 40 or s == 2022) else 5))
    bank = _bank(rows)
    window = {d for _, d in bank if AN.season_of(d) < S
              and AN.calendar_distance(AN.epiweek(d), E)
              <= AN.DEFAULT_BANDWIDTH}
    counts = CK.donor_counts(bank, [end])[end]
    assert counts[-1] == 0 and min(counts[:-1]) > 0
    assert CK._seasons_say(bank, window, counts) == set()
    # a second group with the newest season only: left open
    rows += [("B", d, 5) for d in _saturdays(date(S, 8, 1), end)]
    bank = _bank(rows)
    assert CK.donor_counts(bank, [end])[end] == counts
    assert CK._seasons_say(bank, window, counts) == {"B"}
