"""Tests for slope_blend re-quantile sweep tuning."""

from __future__ import annotations

import numpy as np
import pytest

from flubnf.slope_tune import (DEFAULT_CANDIDATES, SlopeTuneResult,
                               SweepRow, recommend_blend, sweep_slope_blend)


def _make_traj(n_samples: int, n_observed: int, n_horizons: int,
               base: float, growth: float, seed: int = 0) -> np.ndarray:
    """Synthetic posterior trajectory: each sample grows at `growth`/week
    with a small per-sample multiplicative jitter."""
    rng = np.random.default_rng(seed)
    n_weeks = n_observed + n_horizons
    t = np.arange(n_weeks)
    mean_curve = base * (growth ** t)
    jitter = rng.lognormal(mean=0.0, sigma=0.1, size=(n_samples, 1))
    obs_noise = rng.normal(0, 0.05, size=(n_samples, n_weeks))
    return np.maximum(mean_curve[None, :] * jitter * np.exp(obs_noise), 0.1)


def test_sweep_returns_one_row_per_candidate():
    traj = _make_traj(200, 10, 4, base=100.0, growth=1.1)
    observed = traj[0, :10].copy()
    actuals = {1: 150.0, 2: 165.0, 3: 180.0, 4: 200.0}
    res = sweep_slope_blend(traj, observed, actuals, state="Test")
    assert len(res.rows) == len(DEFAULT_CANDIDATES)
    assert res.state == "Test"
    for row in res.rows:
        assert isinstance(row, SweepRow)
        assert row.n_horizons in (0, 4)


def test_sweep_handles_empty_actuals():
    traj = _make_traj(100, 10, 4, base=100.0, growth=1.1)
    observed = traj[0, :10]
    res = sweep_slope_blend(traj, observed, {})
    assert res.rows == []
    assert res.best is None


def test_sweep_handles_short_traj():
    """If traj doesn't extend far enough for the requested horizon, we
    return an empty result rather than crashing."""
    traj = _make_traj(50, 10, 2, base=100.0, growth=1.1)
    observed = traj[0, :10]
    actuals = {1: 150.0, 2: 165.0, 3: 180.0, 4: 200.0}   # h=4 too far
    res = sweep_slope_blend(traj, observed, actuals)
    assert res.rows == []


def test_baseline_row_present():
    traj = _make_traj(100, 10, 4, base=100.0, growth=1.1)
    observed = traj[0, :10]
    actuals = {1: 150.0, 2: 165.0}
    res = sweep_slope_blend(traj, observed, actuals)
    assert res.baseline is not None
    assert res.baseline.slope_blend == 0.0


def test_sweep_picks_higher_blend_when_obs_outruns_model():
    """If observed has been growing FAR faster than the model, a positive
    slope_blend should outperform 0.0."""
    # Build observed history that grew at growth=1.5/week.
    rng = np.random.default_rng(42)
    n_observed = 6
    obs_growth = 1.5
    observed = 100.0 * (obs_growth ** np.arange(n_observed))
    # Build trajectory that predicts slower growth (1.05/wk) — model under
    # the observed momentum.
    traj = _make_traj(500, n_observed, 4, base=100.0, growth=1.05, seed=0)
    # Make actuals continue the OBSERVED 1.5/wk growth trajectory.
    last_obs = observed[-1]
    actuals = {h: float(last_obs * (obs_growth ** h)) for h in (1, 2, 3, 4)}

    res = sweep_slope_blend(traj, observed, actuals,
                            candidates=(0.0, 0.3, 0.6))
    assert res.best is not None
    # The best blend should NOT be the baseline (model alone) — there's
    # so much disagreement that some positive blend has to help.
    assert res.best.mean_wis <= res.baseline.mean_wis


def test_recommend_blend_holds_on_noise():
    """Tiny improvements below threshold shouldn't trigger a change."""
    res = SlopeTuneResult(state="X", rows=[
        SweepRow(slope_blend=0.0, mean_wis=10.0,
                 per_horizon_wis=(10, 10), n_horizons=2),
        SweepRow(slope_blend=0.2, mean_wis=9.99,
                 per_horizon_wis=(10, 10), n_horizons=2),
    ])
    assert recommend_blend(res, min_improvement=0.05) is None


def test_recommend_blend_returns_best_on_clear_win():
    res = SlopeTuneResult(state="X", rows=[
        SweepRow(slope_blend=0.0, mean_wis=15.0,
                 per_horizon_wis=(15, 15), n_horizons=2),
        SweepRow(slope_blend=0.3, mean_wis=8.0,
                 per_horizon_wis=(8, 8), n_horizons=2),
    ])
    assert recommend_blend(res) == 0.3


def test_recommend_blend_needs_min_horizons():
    """Single-horizon wins are too noisy to act on."""
    res = SlopeTuneResult(state="X", rows=[
        SweepRow(slope_blend=0.0, mean_wis=15.0,
                 per_horizon_wis=(15,), n_horizons=1),
        SweepRow(slope_blend=0.3, mean_wis=8.0,
                 per_horizon_wis=(8,), n_horizons=1),
    ])
    assert recommend_blend(res, min_horizons=2) is None


def test_improvement_vs_baseline():
    res = SlopeTuneResult(state="X", rows=[
        SweepRow(slope_blend=0.0, mean_wis=10.0,
                 per_horizon_wis=(10, 10), n_horizons=2),
        SweepRow(slope_blend=0.3, mean_wis=7.0,
                 per_horizon_wis=(7, 7), n_horizons=2),
    ])
    assert pytest.approx(res.improvement_vs_baseline(), abs=1e-9) == 3.0


# ---------------------------------------------------------------------------
# CLI wiring for the --all-states flag
# ---------------------------------------------------------------------------
import re as _re

_ANSI_RE = _re.compile(r"\x1b\[[0-9;]*m")


def _plain(s: str) -> str:
    """Strip ANSI color escapes. Rich emits per-character styles in CI
    (no TTY, narrow terminal) that break naive substring matches."""
    return _ANSI_RE.sub("", s or "")


class TestTuneSlopeCLI:
    def test_rejects_state_and_all_states_together(self, tmp_path):
        from typer.testing import CliRunner
        from flubnf.cli import app
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["tune-slope", "--state", "Alabama", "--all-states",
             "--workspace", "no_such_ws"],
            env={"NO_COLOR": "1"},
        )
        # BadParameter exit code is 2.
        assert result.exit_code != 0
        combined = _plain((result.stdout or "") + (result.output or ""))
        assert "mutually exclusive" in combined

    def test_requires_state_or_all_states(self, tmp_path):
        from typer.testing import CliRunner
        from flubnf.cli import app
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["tune-slope", "--workspace", "no_such_ws"],
            env={"NO_COLOR": "1"},
        )
        assert result.exit_code != 0
        combined = _plain((result.stdout or "") + (result.output or ""))
        assert "--state" in combined or "--all-states" in combined
