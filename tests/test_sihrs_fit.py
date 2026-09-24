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
