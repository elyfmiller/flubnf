"""Tests for flubnf.analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from flubnf.analysis import (compare_models_aicc, recommend_bounds,
                             recommend_piecewise_step,
                             recommend_remove_step)
from flubnf.conf_files import FreeParam


# ---------------------------------------------------------------------------
# Bounds expansion
# ---------------------------------------------------------------------------
class TestRecommendBounds:
    def test_no_recommendation_when_well_inside(self):
        pop = pd.DataFrame({"Obj": np.arange(50.0),
                            "b0__FREE": np.full(50, 0.5)})
        bounds = [FreeParam("b0__FREE", 0.0, 1.0)]
        recs = recommend_bounds(pop, bounds)
        assert recs == []

    def test_expands_when_crowded_at_high(self):
        # All top-N have b0=0.98 with bounds 0..1.
        pop = pd.DataFrame({"Obj": np.arange(50.0),
                            "b0__FREE": np.full(50, 0.98)})
        bounds = [FreeParam("b0__FREE", 0.0, 1.0)]
        recs = recommend_bounds(pop, bounds)
        assert len(recs) == 1
        r = recs[0]
        assert r.changed
        assert r.new_high > 1.0
        assert r.new_low == 0.0  # untouched

    def test_expands_when_crowded_at_low(self):
        pop = pd.DataFrame({"Obj": np.arange(50.0),
                            "b0__FREE": np.full(50, 0.001)})
        bounds = [FreeParam("b0__FREE", 0.0, 1.0)]
        recs = recommend_bounds(pop, bounds, keep_positive=False)
        assert recs[0].new_low < 0.0
        # With keep_positive (default), it should clamp at 0.
        recs2 = recommend_bounds(pop, bounds, keep_positive=True)
        assert recs2[0].new_low == 0.0

    def test_threshold_respected(self):
        # 10% of top-50 at boundary -> below 30% default, no expansion.
        b0 = np.full(50, 0.5)
        b0[:5] = 0.99
        pop = pd.DataFrame({"Obj": np.arange(50.0), "b0__FREE": b0})
        bounds = [FreeParam("b0__FREE", 0.0, 1.0)]
        assert recommend_bounds(pop, bounds, crowding_threshold=0.30) == []
        # Lower the threshold and we should get a rec.
        recs = recommend_bounds(pop, bounds, crowding_threshold=0.05)
        assert len(recs) == 1


# ---------------------------------------------------------------------------
# Piecewise step recommendation
# ---------------------------------------------------------------------------
class TestRecommendPiecewiseStep:
    def test_no_step_when_residuals_small(self):
        obs = np.arange(10, dtype=float) + 10
        pred = obs + np.array([0.1, -0.1, 0.05, -0.05, 0.1,
                               -0.1, 0.05, -0.05, 0.1, -0.1])
        rec = recommend_piecewise_step(pred, obs, n_current_steps=1)
        assert not rec.needs_new_step

    def test_step_when_trailing_run_of_underpredictions(self):
        # Observed is increasing; predictions level off (under-predict).
        obs = np.array([10, 12, 15, 20, 30, 50, 80, 120, 160, 200], dtype=float)
        pred = np.array([10, 12, 15, 20, 25, 30, 35, 40, 45, 50], dtype=float)
        rec = recommend_piecewise_step(pred, obs, n_current_steps=1)
        assert rec.needs_new_step
        assert rec.residual_run_length >= 3
        # Predictions are below observed -> negative residual run.

    def test_max_steps_cap(self):
        obs = np.array([10, 20, 30, 40, 50], dtype=float)
        pred = np.zeros(5)
        rec = recommend_piecewise_step(pred, obs,
                                       n_current_steps=8, max_steps=8)
        assert not rec.needs_new_step
        assert "cap" in rec.reason


# ---------------------------------------------------------------------------
# AICc model comparison
# ---------------------------------------------------------------------------
class TestCompareModelsAicc:
    def test_favors_smaller_when_residuals_similar(self):
        # 20 obs, K=5 vs K+1=6 with identical residuals -> penalty favors K.
        resid = np.random.default_rng(0).normal(size=20)
        cmp = compare_models_aicc(resid, resid.copy(), n_params_k=5,
                                  n_params_kp1=6)
        assert cmp.favored == "K"

    def test_favors_larger_when_rss_drops(self):
        rng = np.random.default_rng(0)
        resid_k = rng.normal(size=50) * 10  # large variance
        resid_kp1 = rng.normal(size=50) * 1  # much smaller variance
        cmp = compare_models_aicc(resid_k, resid_kp1, n_params_k=3,
                                  n_params_kp1=4)
        assert cmp.favored == "K+1"
        assert cmp.delta_aicc < -2.0

    def test_handles_tiny_sample(self):
        # n_obs = 3, k = 3 -> AICc denominator (n-k-1) = -1; fallback to AIC.
        cmp = compare_models_aicc(np.array([0.1, -0.1, 0.05]),
                                  np.array([0.05, 0.0, -0.05]),
                                  n_params_k=3, n_params_kp1=4)
        assert cmp.favored in {"K", "K+1", "tie"}


# ---------------------------------------------------------------------------
# Step REMOVAL (bidirectional K control)
# ---------------------------------------------------------------------------
class TestRecommendRemoveStep:
    def test_no_removal_with_single_step(self):
        pop = pd.DataFrame({"Obj": [1.0, 2.0],
                            "b0__FREE": [0.5, 0.6]})
        r = recommend_remove_step(pop)
        assert not r.needs_removal
        assert r.n_current_steps == 1

    def test_removes_redundant_last_step(self):
        # b0 and b1 posteriors are essentially identical → b1 is redundant.
        rng = np.random.default_rng(0)
        pop = pd.DataFrame({
            "Obj": np.arange(50.0),
            "b0__FREE": rng.normal(0.3, 0.02, 50),
            "b1__FREE": rng.normal(0.3, 0.02, 50),
            "t0__FREE": rng.uniform(0, 5, 50),
            "t1__FREE": rng.uniform(5, 10, 50),
        })
        r = recommend_remove_step(pop)
        assert r.needs_removal
        assert r.step_to_remove == 1

    def test_keeps_distinct_steps(self):
        # b0 = 0.3, b1 = 0.8 — clearly different segments.
        rng = np.random.default_rng(1)
        pop = pd.DataFrame({
            "Obj": np.arange(50.0),
            "b0__FREE": rng.normal(0.3, 0.02, 50),
            "b1__FREE": rng.normal(0.8, 0.02, 50),
            "t0__FREE": rng.uniform(0, 5, 50),
            "t1__FREE": rng.uniform(5, 10, 50),
        })
        r = recommend_remove_step(pop)
        assert not r.needs_removal

    def test_removes_most_recent_when_two_are_redundant(self):
        # b0 ≈ b1 ≈ b2. We should recommend removing b2 (the LAST one).
        rng = np.random.default_rng(2)
        pop = pd.DataFrame({
            "Obj": np.arange(50.0),
            "b0__FREE": rng.normal(0.5, 0.02, 50),
            "b1__FREE": rng.normal(0.5, 0.02, 50),
            "b2__FREE": rng.normal(0.5, 0.02, 50),
            "t0__FREE": rng.uniform(0, 5, 50),
            "t1__FREE": rng.uniform(5, 10, 50),
            "t2__FREE": rng.uniform(10, 15, 50),
        })
        r = recommend_remove_step(pop)
        assert r.needs_removal
        assert r.step_to_remove == 2

    def test_threshold_respected(self):
        # b0=0.5, b1=0.55 — 10% relative diff exactly at the threshold.
        rng = np.random.default_rng(3)
        pop = pd.DataFrame({
            "Obj": np.arange(50.0),
            "b0__FREE": rng.normal(0.5, 0.005, 50),
            "b1__FREE": rng.normal(0.55, 0.005, 50),
            "t0__FREE": rng.uniform(0, 5, 50),
            "t1__FREE": rng.uniform(5, 10, 50),
        })
        # With min_relative_diff=0.10 (default), 10% diff is borderline.
        # With stricter 0.05, it should NOT remove.
        r_strict = recommend_remove_step(pop, min_relative_diff=0.05)
        assert not r_strict.needs_removal
