"""The upper-tail cap (flubnf.tailcap): the median and the lower quantiles
untouched, levels above the median clipped at n times the recent level and
never below the median, order kept, unknown or zero recent levels left
alone, and the hub rows of both members capped block by block."""
import math

import pytest

from flubnf import tailcap as TC


LEVELS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975, 0.99)


def _block(med, spread):
    """A monotone block about `med` with a long upper tail."""
    import numpy as np
    z = {0.01: -2.33, 0.025: -1.96, 0.05: -1.64, 0.1: -1.28, 0.25: -0.67,
         0.5: 0.0, 0.75: 0.67, 0.9: 1.28, 0.95: 1.64, 0.975: 1.96, 0.99: 2.33}
    return {l: float(med * np.exp(spread * z[l])) for l in LEVELS}


def test_registered_form_is_no_cap():
    assert TC.CAP_PRODUCTION == 0.0
    assert math.isnan(TC.limit_for(TC.CAP_PRODUCTION, [10, 12, 14]))


def test_recent_level_is_the_mean_of_the_newest_weeks():
    assert TC.recent_level([1, 2, 3, 10, 20, 30]) == 20.0
    assert TC.recent_level([5]) == 5.0
    assert TC.recent_level([float("nan"), 4, None, 8]) == 6.0
    assert math.isnan(TC.recent_level([]))
    assert TC.limit_for(15, [1, 2, 3, 10, 20, 30]) == 300.0


def test_zero_or_unknown_recent_level_means_no_cap():
    assert math.isnan(TC.limit_for(15, [0, 0, 0]))
    assert math.isnan(TC.limit_for(15, []))
    b = _block(5, 1.0)
    assert TC.cap_block(b, float("nan")) == b


def test_cap_clips_only_above_the_median_and_keeps_order():
    b = _block(10, 1.2)          # 97.5% is 10 * e^(2.35) = 105x the median
    c = TC.cap_block(b, 50.0)
    for l in LEVELS:
        if l <= 0.5:
            assert c[l] == b[l]
        else:
            assert c[l] == min(b[l], 50.0)
    vals = [c[l] for l in LEVELS]
    assert vals == sorted(vals)
    assert c[0.975] == 50.0 and c[0.99] == 50.0 and c[0.75] == b[0.75]


def test_cap_never_falls_below_the_median():
    b = _block(100, 0.5)
    c = TC.cap_block(b, 20.0)    # a limit under the median: the median holds
    assert c[0.5] == 100.0
    assert all(c[l] == 100.0 for l in LEVELS if l > 0.5)
    assert all(c[l] == b[l] for l in LEVELS if l < 0.5)


def test_cap_rows_caps_each_block_with_its_locations_limit():
    from app.core.submit import quantile_rows, rows_from_quantiles, QUANTILES
    import numpy as np
    rng = np.random.default_rng(1)
    samples = {str(h): np.exp(np.log(20) + (0.3 + 0.4 * h) * rng.standard_normal(4000))
               for h in range(4)}
    rows = quantile_rows(samples, "33", "2026-10-17")
    q = {str(h): {float(l): v for l, v in zip(QUANTILES, np.quantile(samples[str(h)], QUANTILES))}
         for h in range(4)}
    rows += rows_from_quantiles(q, "48", "2026-10-17")
    lim = {"33": TC.limit_for(15, [8, 10, 12]), "48": float("nan")}
    capped, cells = TC.cap_rows(rows, lim)
    assert len(capped) == len(rows)
    # New Hampshire ("33"): the far horizons are clipped at 150, the median is not
    by = {}
    for r in capped:
        by.setdefault((r["location"], int(r["horizon"])), {})[float(r["output_type_id"])] = float(r["value"])
    assert by[("33", 3)][0.975] == 150.0 and by[("33", 3)][0.5] < 150.0
    assert all(by[("33", h)][0.5] == {float(r["output_type_id"]): float(r["value"])
                                       for r in rows if r["location"] == "33" and int(r["horizon"]) == h}[0.5]
               for h in range(4))
    for key, block in by.items():
        vals = [block[l] for l in sorted(block)]
        assert vals == sorted(vals), key
    # Texas ("48") has no limit: untouched
    tx = [r for r in capped if r["location"] == "48"]
    tx0 = [r for r in rows if r["location"] == "48"]
    assert [r["value"] for r in tx] == [r["value"] for r in tx0]
    assert 1 <= cells <= 4


def test_cap_rows_leaves_other_targets_alone():
    rows = [{"target": "wk flu hosp rate change", "output_type": "pmf", "location": "33",
             "horizon": 3, "output_type_id": "large_increase", "value": 0.9}]
    capped, cells = TC.cap_rows(rows, {"33": 1.0})
    assert capped == rows and cells == 0


def test_exponent_needed_lands_the_tail_on_the_limit():
    b = _block(10, 1.2)
    k = TC.exponent_needed(b, 50.0)
    assert 0 < k < 1
    c = TC.shrink_block(b, k)
    assert abs(c[0.975] - 50.0) < 1e-9
    assert c[0.5] == b[0.5] and all(c[l] == b[l] for l in LEVELS if l < 0.5)
    assert c[0.99] > 50.0                    # the 99% keeps the shape above the target
    vals = [c[l] for l in LEVELS]
    assert vals == sorted(vals)
    assert TC.exponent_needed(b, 1e9) == 1.0 and TC.exponent_needed(b, 5.0) == 1.0
    assert TC.shrink_block(b, 1.0) == b


def test_shrink_rows_uses_the_worst_horizons_exponent_for_every_horizon():
    from app.core.submit import quantile_rows
    import numpy as np
    rng = np.random.default_rng(2)
    samples = {str(h): np.exp(np.log(20) + (0.3 + 0.5 * h) * rng.standard_normal(6000)) for h in range(4)}
    rows = quantile_rows(samples, "33", "2026-10-17")
    lim = {"33": TC.limit_for(15, [8, 10, 12])}      # 150
    shrunk, cells = TC.cap_rows(rows, lim, mode="shrink")
    by0, by1 = {}, {}
    for r, s in zip(rows, shrunk):
        by0.setdefault(int(r["horizon"]), {})[float(r["output_type_id"])] = float(r["value"])
        by1.setdefault(int(s["horizon"]), {})[float(s["output_type_id"])] = float(s["value"])
    ks = {h: TC.exponent_needed(by0[h], 150.0) for h in range(4)}
    kloc = min(ks.values())
    assert kloc < 1 and ks[3] == kloc              # horizon 3 is the worst
    assert abs(by1[3][0.975] - 150.0) <= 0.5        # the worst horizon lands on the limit
    for h in range(3):
        if by0[h][0.975] > by0[h][0.5]:
            # every other horizon shrunk by the same exponent: below the limit, not on it
            # (to within the rounding back to whole admissions)
            expect = by0[h][0.5] * (by0[h][0.975] / by0[h][0.5]) ** kloc
            assert abs(by1[h][0.975] - expect) <= 0.5
            assert by1[h][0.975] <= 150.0 or by0[h][0.975] <= by0[h][0.5]
    for h in range(4):
        assert by1[h][0.5] == by0[h][0.5]
        vals = [by1[h][l] for l in sorted(by1[h])]
        assert vals == sorted(vals)
    assert cells == 4
    # the clip and the shrink agree on the worst horizon's 97.5%, differ below it
    clipped, _ = TC.cap_rows(rows, lim, mode="clip")
    c3 = {float(r["output_type_id"]): float(r["value"]) for r in clipped if int(r["horizon"]) == 3}
    assert abs(c3[0.975] - by1[3][0.975]) < 1e-6 and c3[0.9] == 150.0 and by1[3][0.9] < 150.0


@pytest.mark.parametrize("mode", TC.MODES)
def test_capped_rows_stay_whole_admissions(mode):
    # the hub rows arrive as whole admissions; a limit that is not a whole
    # number (2.5 x 49 = 122.5) must not leave decimals in the file
    import numpy as np
    import pandas as pd
    from app.core.submit import quantile_rows
    rng = np.random.default_rng(3)
    samples = {str(h): np.exp(np.log(20) + (0.3 + 0.5 * h) * rng.standard_normal(6000)) for h in range(4)}
    rows = quantile_rows(samples, "33", "2026-10-17")
    lim = {"33": TC.limit_for(2.5, [49, 49, 49])}
    assert lim["33"] == 122.5
    capped, cells = TC.cap_rows(rows, lim, mode=mode)
    assert cells >= 1
    assert all(type(r["value"]) is int for r in capped)
    assert pd.DataFrame(capped)["value"].dtype.kind == "i"     # the CSV writes '14', never '14.0'
    by = {}
    for r in capped:
        by.setdefault(int(r["horizon"]), {})[float(r["output_type_id"])] = r["value"]
    for h, block in by.items():
        vals = [block[l] for l in sorted(block)]
        assert vals == sorted(vals), h
    assert abs(by[3][0.975] - 122.5) <= 0.5
    assert TC.whole_block({0.5: 10.0, 0.9: 12.0}, {0.5: 10.0, 0.9: 12.0}) == {0.5: 10.0, 0.9: 12.0}


def test_cap_rows_refuses_an_unknown_mode():
    with pytest.raises(ValueError):
        TC.cap_rows([], {}, mode="chop")


# ---- the historical ceiling (knob output.tail_hist)

def _history():
    """Two states, weekly from 2022-08-06 to 2026-10-17. Ohio is flat at 20
    except for one two-week spike of 320 at epiweeks 45-46 of 2022 (16x);
    the anchors within two epiweeks of epiweek 42 (40-44) all sit before
    it, so every horizon's maximum ratio is 16 and most ratios are 1.
    Idaho (2 to 10 a week, a three-week mean under 10) sits under the
    floor in every season and contributes nothing."""
    from datetime import date, timedelta
    oh, idh = [], []
    d = date(2022, 8, 6)
    while d <= date(2026, 10, 17):
        yr = d.year if d.month >= 8 else d.year - 1
        ew = d.isocalendar()[1]
        v = 320.0 if (yr == 2022 and ew in (45, 46)) else 20.0
        oh.append((d.isoformat(), v)); idh.append((d.isoformat(), 2.0 * (ew % 5 + 1)))
        d += timedelta(days=7)
    return {"39": oh, "16": idh}


def test_history_ratios_take_the_maximum_over_earlier_seasons_in_the_window():
    r = TC.history_ratios(_history(), "2026-10-17", level=1.0)
    # the 2022 spike: an anchor at epiweek 41-44 (recent level 20) reaches
    # 320 at some horizon, a 16x rise, and the window around epiweek 42
    # holds those anchors
    assert all(r[h] == pytest.approx(16.0) for h in range(4))
    # a lower quantile never exceeds the maximum, and far enough down the
    # pool (most ratios are 1) it sits at 1
    q = TC.history_ratios(_history(), "2026-10-17", level=0.975)
    assert all(1.0 <= q[h] <= 16.0 for h in range(4))
    assert all(TC.history_ratios(_history(), "2026-10-17", level=0.5)[h] == pytest.approx(1.0) for h in range(4))
    # Idaho's weeks are under the floor: raising the floor above Ohio's base removes everything
    none = TC.history_ratios(_history(), "2026-10-17", level=1.0, floor=1000.0)
    assert all(math.isnan(v) for v in none.values())


def test_history_ratios_ignore_the_current_season_and_far_calendar_weeks():
    h = _history()
    # far from the spike's calendar position every ratio is 1
    r = TC.history_ratios(h, "2027-03-13", level=1.0)
    assert all(r[hh] == pytest.approx(1.0) for hh in range(4))
    # an as-of in 2023 sees 2022's spike; 2023's own weeks never enter
    r23 = TC.history_ratios(h, "2023-10-21", level=1.0)
    assert r23[3] == pytest.approx(16.0)
    r22 = TC.history_ratios(h, "2022-10-22", level=1.0)
    assert all(math.isnan(v) for v in r22.values())      # no earlier season at all


def test_history_limits_scale_by_the_recent_level_and_refuse_a_zero_level():
    lim = TC.history_limits({0: 2.0, 3: 16.0}, 50.0)
    assert lim == {0: 100.0, 3: 800.0}
    assert all(math.isnan(v) for v in TC.history_limits({0: 2.0, 3: 16.0}, 0.0).values())
    assert math.isnan(TC.history_limits({3: float("nan")}, 50.0)[3])


def test_clip_rows_by_horizon_uses_each_horizons_own_limit():
    rows = []
    for h in range(4):
        for l, v in _block(100.0, 0.6 + 0.3 * h).items():
            rows.append({"target": TC.TARGET, "output_type": "quantile", "location": "39",
                         "horizon": str(h), "output_type_id": str(l), "value": int(round(v))})
    rows.append({"target": "peak inc flu hosp", "output_type": "quantile", "location": "39",
                 "horizon": "3", "output_type_id": "0.975", "value": 99999})
    limits = {"39": {0: 200.0, 1: 400.0, 2: 800.0, 3: float("nan")}}
    out, cells = TC.clip_rows_by_horizon(rows, limits)
    by = {}
    for r in out:
        if r["target"] == TC.TARGET:
            by.setdefault(int(r["horizon"]), {})[float(r["output_type_id"])] = r["value"]
    assert by[0][0.975] == 200 and by[1][0.975] == 400 and by[2][0.975] == 800
    assert by[3][0.975] == int(round(_block(100.0, 1.5)[0.975]))         # NaN limit: untouched
    for h in range(4):
        assert by[h][0.5] == 100 and by[h][0.025] == int(round(_block(100.0, 0.6 + 0.3 * h)[0.025]))
        vals = [by[h][l] for l in sorted(by[h])]; assert vals == sorted(vals)
    assert cells == 3
    assert [r for r in out if r["target"] != TC.TARGET][0]["value"] == 99999
    assert all(type(r["value"]) is int for r in out)


def test_registered_form_has_no_historical_ceiling():
    assert TC.HIST_PRODUCTION == 0.0
