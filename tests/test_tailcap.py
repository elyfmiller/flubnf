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
