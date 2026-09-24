"""GroundHogCGR replayed on its own: the scoring arithmetic, offline (hub
pieces are synthetic): which week a horizon lands on, which cells a figure
covers, and whether two arms are compared on the same cells.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import groundhog as G, horizons as HZ, scoring     # noqa: E402

from flubnf.quantiles import FLUSIGHT_QUANTILES as QL              # noqa: E402


def _q(center):
    """A symmetric fan about `center` at all 23 FluSight levels (a partial
    set is silently left unscored by score_quantiles). The 95 covers
    center +/- 38, the 50 covers center +/- 20."""
    return {float(L): float(center + 80.0 * (float(L) - 0.5)) for L in QL}


def _cells(rows):
    return pd.DataFrame(rows, columns=["location", "fips", "horizon", "wis",
                                       "base_wis", "asof", "season", "arm"])


def _cov(rows):
    return pd.DataFrame(rows, columns=["location", "fips", "horizon", "band",
                                       "hit", "scored", "asof", "season", "arm"])


# ------------------------------------------------------------------ summarise

def test_relwis_is_a_ratio_of_sums_not_a_mean_of_ratios():
    c = _cells([("A", "01", 0, 1.0, 10.0, "2025-01-04", "s", "x"),
                ("A", "01", 1, 9.0, 10.0, "2025-01-04", "s", "x")])
    got = G.summarise(c, _cov([]))["states"]
    assert got["relwis"] == pytest.approx(10.0 / 20.0)
    assert got["cells"] == 2 and got["weeks"] == 1


def test_the_asof_column_is_read_as_a_column():
    """DataFrame.asof is a pandas METHOD. Reaching the column as df.asof
    returns a bound method and fails far from the cause; this is the
    regression test for having done exactly that."""
    c = _cells([("A", "01", 0, 1.0, 2.0, "2025-01-04", "s", "x"),
                ("A", "01", 0, 1.0, 2.0, "2025-01-11", "s", "x")])
    assert G.summarise(c, _cov([]))["states"]["weeks"] == 2


def test_coverage_uses_the_scored_cells_only():
    """One universe for both headline numbers. The unscored row here is a
    miss; if it counted, coverage would read 0.5 instead of 1.0."""
    c = _cells([("A", "01", 0, 1.0, 2.0, "2025-01-04", "s", "x")])
    v = _cov([("A", "01", 0, "50", 1, True, "2025-01-04", "s", "x"),
              ("A", "01", 1, "50", 0, False, "2025-01-04", "s", "x")])
    got = G.summarise(c, v)["states"]
    assert got["cov50"] == 1.0
    assert got["worst_dev"] == pytest.approx(0.5)      # |1.0 - 0.50|


def test_the_national_row_is_reported_beside_the_states_never_inside():
    c = _cells([("A", "01", 0, 5.0, 10.0, "2025-01-04", "s", "x"),
                ("US", "US", 0, 1.0, 10.0, "2025-01-04", "s", "x")])
    got = G.summarise(c, _cov([]))
    assert got["states"]["relwis"] == pytest.approx(0.5)     # not 6/20
    assert got["us"]["relwis"] == pytest.approx(0.1)
    assert got["states"]["cells"] == 1


def test_an_arm_with_nothing_scored_says_so():
    assert G.summarise(_cells([]), _cov([]))["states"] == {"cells": 0}


# -------------------------------------------------------------------- compare

def test_two_arms_are_compared_on_identical_cells():
    """Arm b declines a cell that arm a scored badly. Compared on their own
    cells a would look worse than it is relative to b."""
    a = _cells([("A", "01", 0, 2.0, 10.0, "2025-01-04", "s", "a"),
                ("A", "01", 1, 50.0, 10.0, "2025-01-04", "s", "a"),
                ("A", "01", 0, 2.0, 10.0, "2025-01-11", "s", "a")])
    b = _cells([("A", "01", 0, 1.0, 10.0, "2025-01-04", "s", "b"),
                ("A", "01", 0, 1.0, 10.0, "2025-01-11", "s", "b")])
    got = G.compare(a, _cov([]), b, _cov([]), reps=200)
    assert got["common_cells"] == 2
    assert got["a"]["relwis"] == pytest.approx(4.0 / 20.0)   # the 50.0 is out
    assert got["b"]["relwis"] == pytest.approx(2.0 / 20.0)


def test_the_bootstrap_clusters_on_as_of_dates_and_is_reproducible():
    rows_a, rows_b = [], []
    for i in range(6):
        d = f"2025-01-{4 + 7 * i:02d}" if 4 + 7 * i < 29 else f"2025-02-{4 + 7 * i - 28:02d}"
        rows_a.append(("A", "01", 0, 4.0, 10.0, d, "s", "a"))
        rows_b.append(("A", "01", 0, 2.0, 10.0, d, "s", "b"))
    one = G.compare(_cells(rows_a), _cov([]), _cells(rows_b), _cov([]), reps=300)
    two = G.compare(_cells(rows_a), _cov([]), _cells(rows_b), _cov([]), reps=300)
    bs = one["bootstrap"]
    assert bs["clusters"] == 6 and bs["reps"] == 300
    assert bs["median"] == pytest.approx(-0.2)       # 0.2 minus 0.4, every draw
    assert bs["b_better"] == 300
    assert one["bootstrap"] == two["bootstrap"]      # seeded


def test_by_season_breakdown_keeps_the_arms_paired():
    a = _cells([("A", "01", 0, 4.0, 10.0, "2024-01-06", "2023-24", "a"),
                ("A", "01", 0, 1.0, 10.0, "2025-01-04", "2024-25", "a")])
    b = _cells([("A", "01", 0, 2.0, 10.0, "2024-01-06", "2023-24", "b"),
                ("A", "01", 0, 3.0, 10.0, "2025-01-04", "2024-25", "b")])
    got = G.compare(a, _cov([]), b, _cov([]), reps=100)["by_season"]
    assert got["2023-24"]["a"]["relwis"] == pytest.approx(0.4)
    assert got["2023-24"]["b"]["relwis"] == pytest.approx(0.2)
    assert got["2024-25"]["b"]["relwis"] == pytest.approx(0.3)   # b is WORSE here


# ----------------------------------------------------------------- score_week

@pytest.fixture()
def baseline(monkeypatch):
    """Stand in for the hub's FluSight baseline: every (fips, asof, h) cell
    present, base WIS 10."""
    monkeypatch.setattr(
        scoring, "_baseline_cells",
        lambda asof, fips_set, truth: {(f, asof, h): 10.0
                                       for f in fips_set for h in (0, 1, 2, 3)})


def test_canonical_horizon_h_is_scored_against_h_plus_one_weeks_out(baseline):
    """The week a horizon lands on. Truth exists ONLY one week past the
    as-of, so exactly horizon 0 can be scored; an off-by-one in either
    direction scores nothing, or scores horizon 1."""
    asof = "2025-01-04"
    truth = {("01", pd.Timestamp("2025-01-11")): 100.0}
    q = {"A": {h: _q(100.0) for h in HZ.HORIZONS}}
    cells, cov = G.score_week(q, asof, {"A": "01"}, truth)
    assert sorted(cells.horizon) == [0]
    assert sorted(set(cov.horizon)) == [0]
    assert cov.hit.all()                     # truth sits on the median


def test_each_horizon_meets_its_own_week(baseline):
    asof = "2025-01-04"
    truth = {("01", pd.Timestamp("2025-01-04") + pd.Timedelta(days=7 * (h + 1))):
             100.0 * (h + 1) for h in range(4)}
    # horizon h forecasts 100*(h+1): right on its own week, badly wrong on
    # any other, so a shifted join shows up as misses at the 95
    q = {"A": {str(h): _q(100.0 * (h + 1)) for h in range(4)}}
    cells, cov = G.score_week(q, asof, {"A": "01"}, truth)
    assert sorted(cells.horizon) == [0, 1, 2, 3]
    assert cov[cov.band == "95"].hit.all()


def test_coverage_rows_say_whether_their_cell_was_scored(monkeypatch):
    """No baseline for horizon 1: that cell is not in the relWIS universe,
    and its coverage rows must be flagged so summarise can leave them out."""
    monkeypatch.setattr(scoring, "_baseline_cells",
                        lambda asof, fips_set, truth: {(f, asof, 0): 10.0
                                                       for f in fips_set})
    asof = "2025-01-04"
    truth = {("01", pd.Timestamp("2025-01-11")): 100.0,
             ("01", pd.Timestamp("2025-01-18")): 100.0}
    q = {"A": {"0": _q(100.0), "1": _q(100.0)}}
    cells, cov = G.score_week(q, asof, {"A": "01"}, truth)
    assert sorted(cells.horizon) == [0]
    assert cov[cov.horizon == 0].scored.all()
    assert not cov[cov.horizon == 1].scored.any()


def test_a_location_with_no_fips_is_skipped_not_guessed(baseline):
    truth = {("01", pd.Timestamp("2025-01-11")): 100.0}
    cells, cov = G.score_week({"Nowhere": {"0": _q(100.0)}}, "2025-01-04",
                              {"A": "01"}, truth)
    assert cells.empty and cov.empty


# ----------------------------------------------------------------- run_season

def test_a_season_with_no_vintages_raises_rather_than_scoring_nothing(monkeypatch):
    """The failure `flubnf retro` had: a season that 'completes' empty and
    reports success. This path refuses instead."""
    from app.core import retro
    monkeypatch.setattr(retro, "season_vintages", lambda season: [])
    monkeypatch.setattr(G, "console_locations", lambda: ["A"])
    monkeypatch.setattr(G, "_name2fips", lambda: {"A": "01"})
    monkeypatch.setattr(scoring, "load_truth", lambda: ({}, {}))
    with pytest.raises(FileNotFoundError, match="no hub vintages"):
        G.run_season("2099-00")


def test_an_unknown_preset_fails_before_any_week_runs():
    with pytest.raises(ValueError, match="unknown auxiliary preset"):
        G.run_season("2024-25", "flusrv")
