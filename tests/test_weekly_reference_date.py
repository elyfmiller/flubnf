"""The defaulted reference_date is computed on the deadline zone's clock.

FluSight deadlines are stated in America/New_York. A machine east of that
zone crosses into Saturday hours before the deadline zone does, so near the
Friday/Saturday midnight boundary a machine-local date.today() is already
Saturday while the FluSight week is still Friday's, and the defaulted
reference_date would land one week late (2026-09-01 final pass). These
tests freeze the wall clock on either side of that boundary and check that
the default follows New York, not the machine.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from flubnf import weekly_job


class _FrozenDateTime:
    """Stands in for weekly_job.datetime: now(tz) renders one fixed instant
    in whatever zone the code under test asks for, exactly as a real clock
    would, so the test moves the INSTANT and never the code's zone."""

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
    """03:30 UTC on Saturday 2025-12-06 is 22:30 EST Friday: every zone at
    or east of UTC already shows a Saturday local date, and the old
    date.today() default there skipped to 2025-12-13."""
    clock(datetime(2025, 12, 6, 3, 30))
    assert weekly_job._today_eastern() == date(2025, 12, 5)
    assert weekly_job._default_reference_date() == date(2025, 12, 6)


def test_new_york_into_saturday_rolls_to_the_next_week(clock):
    """06:30 UTC on Saturday 2025-12-06 is 01:30 EST Saturday: the deadline
    zone has crossed the boundary too, so the upcoming submission Saturday
    is now the following week's."""
    clock(datetime(2025, 12, 6, 6, 30))
    assert weekly_job._today_eastern() == date(2025, 12, 6)
    assert weekly_job._default_reference_date() == date(2025, 12, 13)


def test_the_default_is_next_saturday_of_the_eastern_today(clock):
    """Midweek, far from the boundary, the default is unchanged from what
    date.today() always produced: the Saturday ahead."""
    clock(datetime(2025, 12, 3, 15, 0))          # Wednesday everywhere
    assert weekly_job._default_reference_date() == date(2025, 12, 6)
