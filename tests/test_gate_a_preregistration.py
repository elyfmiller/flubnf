"""The Gate A bars are pre-registered. These tests stop them from moving.

A gate that can be adjusted after seeing the result is not a gate. The bars come
from the decision memo; they are asserted here against their memo values, and
the harness's own exclusion logic is exercised on synthetic records so a live
run cannot be the first time it is tested.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / "research/covid-phase0/gate_a.py"

pytestmark = pytest.mark.skipif(
    not GATE.is_file(),
    reason="research/ is not tracked in the public repository (see "
           "docs/RELEASE-1.0.md); this suite runs where the tree is present")


@pytest.fixture(scope="module")
def ga():
    spec = importlib.util.spec_from_file_location("gate_a", GATE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TestBarsMatchTheMemo:
    def test_width_bar_is_the_flu_sihrs_figure(self, ga):
        assert ga.FLU_WIDTH_REFERENCE == 4.06

    def test_kill_is_twenty_percent_over(self, ga):
        assert ga.WIDTH_KILL == pytest.approx(4.06 * 1.20)

    def test_sampler_bars(self, ga):
        assert ga.RHAT_BAR == 1.05
        assert ga.ESS_BAR == 200.0

    def test_omega_window_is_three_to_twelve_months(self, ga):
        from flubnf.covid_fit import omega_to_months
        lo, hi = ga.COVID_OMEGA_GATE
        assert omega_to_months(hi) == pytest.approx(3.0)
        assert omega_to_months(lo) == pytest.approx(12.0)

    def test_the_season_boundary_used_is_the_profile_one(self, ga):
        from flubnf.profiles import COVID
        assert ga.SEASON_START == COVID.season_start(2025)

    def test_horizons_are_one_to_four(self, ga):
        assert ga.HORIZONS == (1, 2, 3, 4)

    def test_the_influenza_sampler_reference_is_carried(self, ga):
        """So a clause-(2) failure is read as a sampler verdict, not a COVID
        one. Written down before the run, on purpose."""
        assert ga.FLU_SAMPLER_REFERENCE["rhat"] == 3.25
        assert ga.FLU_SAMPLER_REFERENCE["ess_total"] == 44.0

    def test_the_preregistration_hash_is_reported(self, ga):
        h = ga.preregistration_hash()
        assert len(h) == 16 and h == ga.preregistration_hash()


def _rec(state, asof, edge, width_rel, n=400):
    """A synthetic fit record whose horizon-h samples have a known central-95
    width relative to an actual of 100."""
    rng = np.random.default_rng(0)
    base = rng.normal(0, 1, n)
    base = (base - np.median(base)) / (np.percentile(base, 97.5)
                                       - np.percentile(base, 2.5))
    return {"state": state, "asof": asof, "ok": True, "data_edge": edge,
            "n_obs": 40, "waves": 2, "last_observed": 100.0,
            "samples": {str(h): (100.0 + base * width_rel * 100.0).tolist()
                        for h in (0, 1, 2, 3, 4)}}


class TestExclusionInScoring:
    def test_a_straddling_cell_is_dropped_and_its_reason_recorded(self, ga,
                                                                  monkeypatch):
        truth = pd.DataFrame({
            "date": ["2026-03-07", "2026-03-14", "2026-03-21", "2026-03-28"],
            "location": ["36"] * 4, "location_name": ["New York"] * 4,
            "value": [100.0] * 4})
        monkeypatch.setattr(ga, "settled_truth", lambda: truth)
        cells = ga.width_cells([_rec("New York", "2026-03-04", "2026-02-28", 2.0)])
        assert len(cells) == 4
        bad = cells[cells["target"] == "2026-03-28"]
        assert len(bad) == 1
        assert bool(bad["excluded"].iloc[0]) is True
        assert bool(bad["usable"].iloc[0]) is False
        assert "INSTRUMENT" in str(bad["exclusion_reason"].iloc[0]) or \
            "instrument" in str(bad["exclusion_reason"].iloc[0]).lower()

    def test_cells_before_the_break_are_kept(self, ga, monkeypatch):
        truth = pd.DataFrame({
            "date": ["2026-02-07", "2026-02-14", "2026-02-21", "2026-02-28"],
            "location": ["36"] * 4, "location_name": ["New York"] * 4,
            "value": [100.0] * 4})
        monkeypatch.setattr(ga, "settled_truth", lambda: truth)
        cells = ga.width_cells([_rec("New York", "2026-01-07", "2026-01-31", 2.0)])
        assert bool(cells["usable"].all())
        assert not bool(cells["excluded"].any())

    def test_width_rel_is_computed_as_specified(self, ga, monkeypatch):
        truth = pd.DataFrame({
            "date": ["2026-02-07", "2026-02-14", "2026-02-21", "2026-02-28"],
            "location": ["36"] * 4, "location_name": ["New York"] * 4,
            "value": [100.0] * 4})
        monkeypatch.setattr(ga, "settled_truth", lambda: truth)
        cells = ga.width_cells([_rec("New York", "2026-01-07", "2026-01-31", 2.5)])
        assert cells["width_rel"].median() == pytest.approx(2.5, rel=0.05)


class TestVerdictLogic:
    def _table(self, ga, width, monkeypatch):
        truth = pd.DataFrame({
            "date": ["2026-02-07", "2026-02-14", "2026-02-21", "2026-02-28"],
            "location": ["36"] * 4, "location_name": ["New York"] * 4,
            "value": [100.0] * 4})
        monkeypatch.setattr(ga, "settled_truth", lambda: truth)
        recs = [_rec("New York", "2026-01-07", "2026-01-31", width)]
        return ga.gate_table(recs, ga.width_cells(recs))

    def test_width_pass(self, ga, monkeypatch):
        t = self._table(ga, 3.0, monkeypatch)
        assert t["gate"]["3_width_first"]["verdict"] == "PASS"

    def test_width_fail_but_not_kill(self, ga, monkeypatch):
        t = self._table(ga, 4.4, monkeypatch)
        assert t["gate"]["3_width_first"]["verdict"] == "FAIL (not kill)"

    def test_width_kill(self, ga, monkeypatch):
        t = self._table(ga, 6.0, monkeypatch)
        assert t["gate"]["3_width_first"]["verdict"] == "KILL"

    def test_missing_omega_reads_as_no_data_not_as_pass(self, ga, monkeypatch):
        t = self._table(ga, 3.0, monkeypatch)
        assert t["gate"]["1_omega"]["verdict"] == "NO DATA"
        assert t["gate"]["2_sampler"]["verdict"] == "NO DATA"
