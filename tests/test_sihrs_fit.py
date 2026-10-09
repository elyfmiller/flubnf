"""Tests for flubnf.sihrs_fit's data path: resolve_state and write_exp, and
the vendored locations table."""

from __future__ import annotations


# --- multi-season data accuracy: NaN weeks + calendar anchoring --------------

def test_nan_weeks_dropped_with_true_offsets(tmp_path):
    """The May-Oct 2024 reporting pause: NaN weeks drop as ROWS, survivors keep
    TRUE week offsets (calendar-anchored phi1), and i0/rhomult stay finite."""
    import numpy as np, pandas as pd
    from flubnf.sihrs_fit import resolve_state, write_exp
    dates = pd.date_range("2024-06-22", periods=10, freq="7D")
    vals = [3.0, np.nan, np.nan, 5.0, 8.0, np.nan, 12.0, 20.0, 31.0, 45.0]
    truth = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"),
                          "location": "25", "value": vals})
    (tmp_path / "truth.csv").write_text(truth.to_csv(index=False))
    (tmp_path / "locs.csv").write_text(
        "location,abbreviation,location_name,population\n"
        "25,MA,Massachusetts,7136171\n")
    s = resolve_state("Massachusetts", truth_csv=tmp_path/"truth.csv",
                      locations_csv=tmp_path/"locs.csv",
                      season_start="2024-06-22", as_of="2024-08-24")
    assert s.n_obs == 7                                   # 3 NaNs dropped
    assert s.times.tolist() == [0, 3, 4, 6, 7, 8, 9]      # true offsets kept
    assert s.last_week_offset == 9                        # NOT n_obs-1 == 6
    assert np.isfinite(s.i0) and np.isfinite(s.rhomult)
    exp = write_exp(s, tmp_path/"m.exp").read_text().splitlines()
    assert exp[1].startswith("0 ") and exp[2].startswith("3 ")
    assert not any("nan" in l for l in exp)


def test_an_all_zero_season_start_says_so(tmp_path):
    # the hub's first weeks of 2024-25 had 21 jurisdictions with no
    # admission yet; the refusal named rho_mult, gamma and population
    import pandas as pd, pytest
    from flubnf.sihrs_fit import resolve_state
    dates = pd.date_range("2024-08-03", periods=3, freq="7D")
    truth = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"),
                          "location": "56", "value": [0.0, 0.0, 0.0]})
    (tmp_path / "truth.csv").write_text(truth.to_csv(index=False))
    (tmp_path / "locs.csv").write_text(
        "location,abbreviation,location_name,population\n"
        "56,WY,Wyoming,584057\n")
    with pytest.raises(ValueError, match="no admissions reported in "
                       r"2024-08-01\.\.2024-08-17 \(3 week\(s\), all zero\)"):
        resolve_state("Wyoming", truth_csv=tmp_path / "truth.csv",
                      locations_csv=tmp_path / "locs.csv",
                      season_start="2024-08-01", as_of="2024-08-17")


def test_all_nan_errors_loudly(tmp_path):
    import numpy as np, pandas as pd, pytest
    from flubnf.sihrs_fit import resolve_state
    dates = pd.date_range("2024-06-22", periods=4, freq="7D")
    truth = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"),
                          "location": "25", "value": [np.nan]*4})
    (tmp_path / "truth.csv").write_text(truth.to_csv(index=False))
    (tmp_path / "locs.csv").write_text(
        "location,abbreviation,location_name,population\n"
        "25,MA,Massachusetts,7136171\n")
    with pytest.raises(ValueError, match="all 4 weeks are NaN"):
        resolve_state("Massachusetts", truth_csv=tmp_path/"truth.csv",
                      locations_csv=tmp_path/"locs.csv",
                      season_start="2024-06-22", as_of="2024-07-13")


def test_vendored_locations_matches_hub():
    """settings.load_locations falls back to the vendored copy; drift up to
    3.3% was found and fixed 2026-08-17. This pins them equal forever."""
    import pandas as pd, pytest
    from pathlib import Path
    from flubnf import settings
    hub = Path(settings.HUB) / 'auxiliary-data/locations.csv'
    if not hub.is_file():
        pytest.skip("hub checkout not present")
    vendored = Path(__file__).resolve().parents[1] / 'flubnf/data/locations.csv'
    h = pd.read_csv(hub); v = pd.read_csv(vendored)
    m = h.merge(v, on='location', suffixes=('_h','_v'))
    assert len(m) == len(h)
    assert (m.population_h == m.population_v).all(), "vendored locations.csv drifted from hub — refresh it"


# --- the seed denominator (research knob pf.seed_denominator) ----------------

CURRENT = [5, 6, 8, 10, 14, 20, 28, 40, 55, 75]        # 2025-26 to date: 261
POP = 11_000_000


def _seasons_csv(tmp_path, current, *, past=True):
    """A hub-shaped truth file for Ohio (39). With `past`: a 2022-23 season
    with 20 finite weeks (the rest NaN), a complete 2023-24 at 100 a week
    (5200) and a 2024-25 at 200 a week with 2 NaN weeks (the pause; 10000).
    Then the 2025-26 weeks `current` from 2025-08-02. (truth, locations)."""
    import numpy as np, pandas as pd
    rows = []
    if past:
        for start, n_finite, v, nan_at in (("2022-08-06", 20, 50.0, ()),
                                           ("2023-08-05", 52, 100.0, ()),
                                           ("2024-08-03", 52, 200.0, (40, 41))):
            for i, d in enumerate(pd.date_range(start, periods=52, freq="7D")):
                val = v if i < n_finite and i not in nan_at else np.nan
                rows.append((d.strftime("%Y-%m-%d"), "39", val))
    for v, d in zip(current, pd.date_range("2025-08-02", periods=len(current),
                                           freq="7D")):
        rows.append((d.strftime("%Y-%m-%d"), "39", float(v)))
    truth = pd.DataFrame(rows, columns=["date", "location", "value"])
    (tmp_path / "truth.csv").write_text(truth.to_csv(index=False))
    (tmp_path / "locs.csv").write_text(
        "location,abbreviation,location_name,population\n"
        f"39,OH,Ohio,{POP}\n")
    return dict(truth_csv=tmp_path / "truth.csv",
                locations_csv=tmp_path / "locs.csv",
                season_start="2025-08-01", as_of="2025-10-04")


def test_season_total_pins_on_the_median_of_the_completed_past_seasons(tmp_path):
    """season_total: the expectation is the median per-capita total of the
    completed past seasons (the 20-week one is left out, NaN weeks drop);
    rho*mult is pinned on it and i0 shrinks by the factor expected/to-date."""
    import numpy as np, pytest
    from flubnf.sihrs_fit import resolve_state
    from flubnf.sihrs_priors import ATTACK_RATE_RANGE, MIN_COMPLETE_WEEKS
    kw = _seasons_csv(tmp_path, CURRENT)
    shipped = resolve_state("Ohio", **kw)
    s = resolve_state("Ohio", seed_denominator="season_total", **kw)
    expected = float(np.median([5200 / POP, 10000 / POP]))
    assert s.seed_denominator == "season_total"
    assert s.expected_total_pc == pytest.approx(expected)
    assert set(s.seed_record["seasons"]) == {"2023-24", "2024-25"}
    assert s.seed_record["seasons"]["2024-25"] == pytest.approx(10000 / POP)
    assert s.seed_record["min_weeks"] == MIN_COMPLETE_WEEKS == 35
    assert s.seed_record["median"] == pytest.approx(expected)
    assert s.seed_record["mean"] == pytest.approx(7600 / POP)
    assert "fallback" not in s.seed_record
    factor = expected / (261 / POP)
    assert factor > 1 and s.seed_factor == pytest.approx(factor)
    assert s.rhomult == pytest.approx(expected / float(np.mean(ATTACK_RATE_RANGE)))
    assert s.rhomult == pytest.approx(shipped.rhomult * factor)
    assert s.i0 == pytest.approx(shipped.i0 / factor)
    # the observations and their offsets are the shipped ones
    assert s.observed.tolist() == shipped.observed.tolist() == CURRENT
    assert s.times.tolist() == shipped.times.tolist() == list(range(10))


def test_season_total_is_floored_at_to_date(tmp_path):
    """To-date admissions above the expectation: the factor is exactly 1
    and rho*mult and i0 are the shipped numbers, bit for bit."""
    import pytest
    from flubnf.sihrs_fit import resolve_state
    kw = _seasons_csv(tmp_path, [2000.0] * 10)              # 20000 > 10000
    shipped = resolve_state("Ohio", **kw)
    s = resolve_state("Ohio", seed_denominator="season_total", **kw)
    assert s.seed_factor == 1.0
    assert (s.rhomult, s.i0) == (shipped.rhomult, shipped.i0)
    assert s.expected_total_pc == pytest.approx(7600 / POP)   # still recorded


def test_season_total_falls_back_to_to_date_without_a_completed_season(tmp_path):
    """No completed season in the vintage (a new location, a custom
    dataset): the record says so and the numbers are the shipped ones."""
    from flubnf.sihrs_fit import resolve_state
    kw = _seasons_csv(tmp_path, CURRENT, past=False)
    shipped = resolve_state("Ohio", **kw)
    s = resolve_state("Ohio", seed_denominator="season_total", **kw)
    assert s.expected_total_pc is None and s.seed_factor == 1.0
    assert s.seed_record["seasons"] == {} and "to-date" in s.seed_record["fallback"]
    assert (s.rhomult, s.i0) == (shipped.rhomult, shipped.i0)


def test_the_default_denominator_is_the_shipped_computation(tmp_path):
    """to_date (the default): StateSetup carries the numbers the code
    computed before the knob existed, bit for bit, with an empty record."""
    import numpy as np, pytest
    from flubnf.sihrs_fit import resolve_state
    from flubnf.sihrs_priors import (ATTACK_RATE_RANGE, gamma_per_week,
                                     initial_infected_fraction, pin_rho_mult)
    kw = _seasons_csv(tmp_path, CURRENT)
    s = resolve_state("Ohio", **kw)
    obs = np.asarray(CURRENT, dtype=float)
    rhomult = pin_rho_mult(float(obs.sum()) / POP, float(np.mean(ATTACK_RATE_RANGE)))
    i0 = initial_infected_fraction(max(float(obs[0]), 1.0), POP, rhomult,
                                   gamma_per_week())
    assert (s.rhomult, s.i0) == (rhomult, i0)
    assert s.seed_denominator == "to_date" and s.expected_total_pc is None
    assert s.seed_factor == 1.0 and s.seed_record == {}
    with pytest.raises(ValueError, match="seed_denominator must be one of"):
        resolve_state("Ohio", seed_denominator="median", **kw)


def test_expected_total_counts_only_seasons_ended_by_the_as_of(tmp_path):
    """A season counts when it starts before the season start, ends at or
    before the as-of and holds min_weeks finite weeks; the current season
    and a still-running one never do."""
    import pandas as pd, pytest
    from flubnf.sihrs_priors import expected_total_per_capita
    kw = _seasons_csv(tmp_path, CURRENT)
    t = pd.read_csv(kw["truth_csv"], dtype={"location": str})
    t["date"] = pd.to_datetime(t["date"])
    # a week of 2024-25: only 2023-24 is complete (2022-23 has 20 weeks)
    e, rec = expected_total_per_capita(t, "39", POP, "2024-08-01", "2024-12-07")
    assert e == pytest.approx(5200 / POP) and list(rec["seasons"]) == ["2023-24"]
    # a June season start with a July as-of: 2024-25 has not ended yet
    e, rec = expected_total_per_capita(t, "39", POP, "2025-06-21", "2025-07-05")
    assert list(rec["seasons"]) == ["2023-24"]
    # a lower bar lets the 20-week season in; the median of three
    e, rec = expected_total_per_capita(t, "39", POP, "2025-08-01", "2025-10-04",
                                       min_weeks=20)
    assert set(rec["seasons"]) == {"2022-23", "2023-24", "2024-25"}
    assert e == pytest.approx(5200 / POP)
    assert rec["mean"] == pytest.approx(16200 / 3 / POP)
    # a location the vintage lacks
    assert expected_total_per_capita(t, "06", POP, "2025-08-01", "2025-10-04") == (
        None, {"seasons": {}, "min_weeks": 35})


def test_season_total_early_is_the_expectation_early_and_the_shipped_rule_after(tmp_path):
    """season_total_early: below a quarter of the expectation (261 of 7,600
    here) it is the season_total pin, bit for bit; at or above it, the
    shipped pin, bit for bit; the record names the stage."""
    import pytest
    from flubnf.sihrs_fit import resolve_state
    from flubnf.sihrs_priors import EARLY_FRACTION
    assert EARLY_FRACTION == 0.25
    kw = _seasons_csv(tmp_path, CURRENT)
    shipped = resolve_state("Ohio", **kw)
    total = resolve_state("Ohio", seed_denominator="season_total", **kw)
    early = resolve_state("Ohio", seed_denominator="season_total_early", **kw)
    assert early.seed_denominator == "season_total_early"
    assert (early.rhomult, early.i0, early.seed_factor) == (
        total.rhomult, total.i0, total.seed_factor)
    assert early.seed_record["stage"] == "expected"
    assert early.seed_record["early_fraction"] == 0.25
    assert early.expected_total_pc == pytest.approx(7600 / POP)
    assert early.i0 == pytest.approx(shipped.i0 / early.seed_factor)
    # the same season with 2,000 a week: 20,000 to date, above the expectation
    kw = _seasons_csv(tmp_path, [2000.0] * 10)
    shipped = resolve_state("Ohio", **kw)
    late = resolve_state("Ohio", seed_denominator="season_total_early", **kw)
    assert (late.rhomult, late.i0) == (shipped.rhomult, shipped.i0)
    assert late.seed_factor == 1.0 and late.seed_record["stage"] == "to_date"
    assert late.expected_total_pc == pytest.approx(7600 / POP)   # still recorded


def test_season_total_early_switches_exactly_at_the_quarter(tmp_path):
    """One admission below a quarter of the expectation (1,899 of 7,600)
    pins on the expectation; exactly a quarter (1,900) pins on the to-date
    count: the comparison is strict."""
    from flubnf.sihrs_fit import pin_from, resolve_state
    from flubnf.sihrs_priors import gamma_per_week
    g = gamma_per_week()
    kw = _seasons_csv(tmp_path, [1.0] + [0.0] * 8 + [1898.0])   # 1,899 to date
    below = resolve_state("Ohio", seed_denominator="season_total_early", **kw)
    assert below.seed_factor > 1 and below.seed_record["stage"] == "expected"
    kw = _seasons_csv(tmp_path, [1.0] + [0.0] * 8 + [1899.0])   # 1,900 to date
    at = resolve_state("Ohio", seed_denominator="season_total_early", **kw)
    assert at.seed_factor == 1.0 and at.seed_record["stage"] == "to_date"
    # pin_from directly: no expectation means the to-date rule for every value
    rm, i0, f = pin_from([4.0, 5.0], POP, 0.18, None, g, "season_total_early")
    assert f == 1.0 and (rm, i0) == pin_from([4.0, 5.0], POP, 0.18, None, g)[:2]



def test_the_stage_is_read_off_the_pin_not_the_factor():
    """An all-zero series (a trim can leave one: weeks_to_drop=1 on
    [0, 0, 3]) still pins on the expectation under season_total_early, and
    its factor is NaN, so seed_stage reads the stage off the pin: expected.
    The to-date rule with an expectation is a caller's mistake and raises;
    so is a rule that is not a seed denominator."""
    import math, pytest
    from flubnf.sihrs_fit import pin_from, seed_stage
    from flubnf.sihrs_priors import gamma_per_week
    g = gamma_per_week()
    rm, i0, f = pin_from([0.0, 0.0], POP, 0.18, 2e-3, g, "season_total_early")
    assert math.isnan(f) and rm > 0 and i0 > 0
    assert seed_stage([0.0, 0.0], POP, 2e-3, "season_total_early") == "expected"
    # a to-date count past the quarter: the shipped stage
    assert seed_stage([2000.0] * 10, POP, 2e-3, "season_total_early") == "to_date"
    # no expectation: the to-date stage whatever the count
    assert seed_stage([0.0, 0.0], POP, None, "season_total_early") == "to_date"
    with pytest.raises(ValueError, match="to-date rule"):
        pin_from([4.0, 5.0], POP, 0.18, 2e-3, g)
    with pytest.raises(ValueError, match="unknown seed denominator"):
        pin_from([4.0, 5.0], POP, 0.18, None, g, "season_totl")
