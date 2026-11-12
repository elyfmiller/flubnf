"""A file of daily counts is refused with a hint that says so (UX review
F60, package P4): its dates fall on every weekday, most a day after the
one before in their group. A weekly file with a few stray weekdays gets
the weekday problem without the hint."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core import datasets as D

HINT = ("These look like daily counts: FluBNF reads one row per week. Sum "
        "each week's days into one row dated the Saturday that ends it "
        "(Sunday to Saturday), then upload again.")


@pytest.fixture(autouse=True)
def _store_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")


def rows(days, groups=("A",), value=lambda i, j: 3 + (i + j) % 9):
    out = ["date,group,value"]
    for i, d in enumerate(days):
        for j, g in enumerate(groups):
            out.append(f"{d.isoformat()},{g},{value(i, j)}")
    return ("\n".join(out) + "\n").encode()


def weekday_problem(rep) -> str:
    (p,) = [p for p in rep.problems if p.code == "weekday"]
    return p.message


def test_daily_counts_are_told_to_sum_into_weeks():
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(400)]
    msg = weekday_problem(D.validate(rows(days, ("North", "South"))))
    assert msg.startswith("The dates fall on 7 different weekdays: ")
    assert msg.endswith("Every date must be the same day of its week. "
                        + HINT)


def test_daily_rates_are_told_to_combine_them():
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(60)]
    raw = rows(days, value=lambda i, j: f"{1.5 + i % 4:.1f}")
    msg = weekday_problem(D.validate(raw, kind="rate"))
    assert msg.endswith("These look like daily values: FluBNF reads one row "
                        "per week. Combine each week's days into one row "
                        "dated the Saturday that ends it (Sunday to "
                        "Saturday), then upload again.")


def test_weekdays_only_are_daily_too():
    """A dashboard that reports Monday to Friday: five weekdays, most a
    day apart."""
    days = [d for d in (date(2024, 1, 1) + timedelta(days=i)
                        for i in range(120)) if d.weekday() < 5]
    assert HINT in weekday_problem(D.validate(rows(days)))


def test_a_weekly_file_with_stray_weekdays_gets_no_hint():
    sats = [date(2023, 9, 2) + timedelta(days=7 * i) for i in range(60)]
    # five rows a day early or late, on five other weekdays
    for k, off in zip((5, 15, 25, 35, 45), (-1, -2, -3, 1, 2)):
        sats[k] += timedelta(days=off)
    rep = D.validate(rows(sats, ("North", "South")))
    msg = weekday_problem(rep)
    assert msg.startswith("The dates fall on 6 different weekdays: ")
    assert "daily" not in msg


def test_two_weekdays_are_never_called_daily():
    """Fewer than five weekdays: the weekday problem alone, even where the
    two days sit side by side."""
    days = []
    for i in range(30):
        s = date(2023, 9, 2) + timedelta(days=7 * i)
        days += [s - timedelta(days=1), s]
    msg = weekday_problem(D.validate(rows(days)))
    assert "daily" not in msg
