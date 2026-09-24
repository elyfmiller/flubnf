"""Epiweek 53: the seam, pinned (MMWR 2014, 2020 and 2025 have one; the
2025-26 season peaked on an epiweek-53 Saturday).

1. WHICH donor weeks match the target's calendar position compares epiweek
   LABELS via `calendar_distance`, which seats week 53 between 52 and 1.
2. WHERE a donor's future value is read from is DATE arithmetic
   (`d + 7 * horizon days`), never labels, so a week-52 donor reads week 53
   at horizon 1 and week 1 at horizon 2. Label arithmetic would silently
   skip a week.
"""
from datetime import date, timedelta

import numpy as np

from flubnf import analogue as AN

# MMWR 2014 has 53 weeks: week 52 ends 2014-12-27, week 53 ends 2015-01-03,
# week 1 of 2015 ends 2015-01-10.
W52, W53, W01 = date(2014, 12, 27), date(2015, 1, 3), date(2015, 1, 10)


def test_the_fixture_dates_are_the_weeks_this_file_says_they_are():
    assert (AN.epiweek(W52), AN.epiweek(W53), AN.epiweek(W01)) == (52, 53, 1)
    assert AN.epiweek(date(2021, 1, 2)) == 53          # MMWR 2020
    assert AN.epiweek(date(2026, 1, 3)) == 53          # MMWR 2025
    # and a 52-week year has no week 53 at all
    assert AN.epiweek(date(2024, 12, 28)) == 52
    assert AN.epiweek(date(2025, 1, 4)) == 1


def test_week_53_sits_between_52_and_1_not_on_top_of_1():
    d = AN.calendar_distance
    assert d(53, 52) == 1 and d(53, 1) == 1
    assert d(53, 51) == 2 and d(53, 2) == 2
    assert d(53, 50) == 3 and d(53, 3) == 3
    assert d(53, 53) == 0
    # the bug this replaced: plain mod-52 put week 53 ONTO week 1
    assert d(53, 1) != 0


def test_the_distance_is_symmetric_across_the_seam():
    for a in (50, 51, 52, 53, 1, 2, 3):
        for b in (50, 51, 52, 53, 1, 2, 3):
            assert AN.calendar_distance(a, b) == AN.calendar_distance(b, a)


def test_weeks_1_to_52_are_untouched():
    """The historical integer arithmetic, exactly."""
    for a in range(1, 53):
        for b in range(1, 53):
            want = min(abs(a - b), 52 - abs(a - b))
            assert AN.calendar_distance(a, b) == want


def _bank():
    """One location, a run of Saturdays through the 2014 seam, values that
    identify the week they belong to."""
    bank, d, v = {}, date(2014, 11, 29), 100.0
    while d <= date(2015, 2, 7):
        bank[("xx", d)] = v
        d += timedelta(days=7)
        v += 10.0
    return bank


def test_a_ratio_across_the_seam_is_read_by_date_not_by_label():
    """The donor anchored at week 52 of a 53-week year."""
    bank = _bank()
    v52, v53, v01 = bank[("xx", W52)], bank[("xx", W53)], bank[("xx", W01)]
    # target anchored at week 52, a later season, bandwidth 0: the only
    # admissible donor is the week-52 Saturday itself
    r1 = AN.donor_ratios(bank, 52, 2030, 1, bandwidth=0, exclude_seasons=())
    r2 = AN.donor_ratios(bank, 52, 2030, 2, bandwidth=0, exclude_seasons=())
    assert r1.tolist() == [v53 / v52]      # horizon 1 lands ON week 53
    assert r2.tolist() == [v01 / v52]      # horizon 2 lands on week 1
    # label arithmetic would have read week 1 at horizon 1
    assert r1.tolist() != [v01 / v52]


def test_a_week_53_target_admits_both_sides_evenly():
    bank = _bank()
    got = []
    for (loc, d) in bank:
        if AN.calendar_distance(AN.epiweek(d), 53) <= 2:
            got.append(AN.epiweek(d))
    assert sorted(got, key=lambda w: (w < 40, w)) == [51, 52, 53, 1, 2]


def test_a_week_53_anchor_can_itself_be_a_donor():
    bank = _bank()
    r = AN.donor_ratios(bank, 53, 2030, 1, bandwidth=0, exclude_seasons=())
    assert r.tolist() == [bank[("xx", W01)] / bank[("xx", W53)]]


def test_the_committed_banks_carry_their_week_53_saturdays():
    """The committed banks keep their week-53 Saturdays (flusurv.build_bank
    silently drops cells whose date disagrees with the analogue's epiweek)."""
    from flubnf import bank as B
    fs, _ = B.read("flusurv")
    il, _ = B.read("iliplus")
    fs53 = {d for (_, d) in fs if AN.epiweek(d) == 53}
    il53 = {d for (_, d) in il if AN.epiweek(d) == 53}
    assert date(2015, 1, 3) in fs53, "flusurv lost MMWR 2014 week 53"
    assert date(2021, 1, 2) in il53, "ILI+ lost MMWR 2020 week 53"
    # and they are usable as donors: the next Saturday is present too
    assert any((loc, date(2015, 1, 10)) in fs for (loc, d) in fs
               if d == date(2015, 1, 3))
