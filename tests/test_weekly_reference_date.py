"""The defaulted reference_date follows the deadline zone's clock
(America/New_York), not the machine's: east of it, date.today() turns
Saturday early and would land the reference a week late. The wall clock is
frozen on either side of the boundary.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from flubnf import weekly_job


class _FrozenDateTime:
    """Stands in for weekly_job.datetime: now(tz) renders one fixed instant in
    the requested zone, so tests move the INSTANT, never the code's zone."""

    instant: datetime

    @classmethod
    def now(cls, tz=None):
        return cls.instant.astimezone(tz)


@pytest.fixture
def clock(monkeypatch):
    def at(instant_utc: datetime):
        _FrozenDateTime.instant = instant_utc.replace(tzinfo=timezone.utc)
        monkeypatch.setattr(weekly_job, "datetime", _FrozenDateTime)
    return at


def test_new_york_still_friday_keeps_the_imminent_saturday(clock):
    """03:30 UTC Saturday 2025-12-06 is 22:30 EST Friday (the old default
    skipped to 2025-12-13)."""
    clock(datetime(2025, 12, 6, 3, 30))
    assert weekly_job._today_eastern() == date(2025, 12, 5)
    assert weekly_job._default_reference_date() == date(2025, 12, 6)


def test_new_york_into_saturday_rolls_to_the_next_week(clock):
    """06:30 UTC Saturday is 01:30 EST Saturday: the next week's Saturday."""
    clock(datetime(2025, 12, 6, 6, 30))
    assert weekly_job._today_eastern() == date(2025, 12, 6)
    assert weekly_job._default_reference_date() == date(2025, 12, 13)


def test_the_default_is_next_saturday_of_the_eastern_today(clock):
    """Midweek, far from the boundary, the default is unchanged from what
    date.today() always produced: the Saturday ahead."""
    clock(datetime(2025, 12, 3, 15, 0))          # Wednesday everywhere
    assert weekly_job._default_reference_date() == date(2025, 12, 6)
