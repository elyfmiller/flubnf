"""Tests for flubnf.diagnostics."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flubnf.conf_files import FreeParam
from flubnf.diagnostics import (Action, compute_diagnostics,
                                detect_beta_waning_degeneracy,
                                react_to_diagnostics)


# ---------------------------------------------------------------------------
# SIRS-vs-beta degeneracy detector (SIRS-migration, Phase 4)
# ---------------------------------------------------------------------------
def _single_wave():
    # Rises to one peak then decays — no rebound.
    return np.array([1, 3, 8, 20, 45, 60, 50, 30, 15, 6, 2], dtype=float)


def _double_wave():
    # Peak, trough, then a clear second rise (>30% of peak).
    return np.array([1, 5, 20, 50, 60, 30, 12, 8, 25, 40, 22, 9], dtype=float)


class TestDegeneracyDetector:
    def test_second_wave_with_straddling_amplitude_flags(self):
        # Last amplitude db2 straddles 0 AND a second wave is present.
        chain = pd.DataFrame({
            "b0__FREE": np.full(200, 0.3),
            "db1__FREE": np.random.default_rng(0).normal(0.8, 0.05, 200),
            "db2__FREE": np.random.default_rng(1).normal(0.0, 0.5, 200),
        })
        flag = detect_beta_waning_degeneracy(chain, _double_wave())
        assert flag.degenerate is True
        assert flag.amplitude_param == "db2__FREE"
        assert flag.second_wave is True

    def test_second_wave_with_confident_amplitude_not_flagged(self):
        # db2 confidently positive (95% CI excludes 0) -> beta explains the
        # second wave; not degenerate.
        chain = pd.DataFrame({
            "b0__FREE": np.full(200, 0.3),
            "db1__FREE": np.full(200, 0.8),
            "db2__FREE": np.random.default_rng(2).normal(0.9, 0.05, 200),
        })
        flag = detect_beta_waning_degeneracy(chain, _double_wave())
        assert flag.degenerate is False
        assert flag.second_wave is True

    def test_no_second_wave_never_flags(self):
        # Even a straddling amplitude is benign without a second wave.
        chain = pd.DataFrame({
            "b0__FREE": np.full(200, 0.3),
            "db1__FREE": np.random.default_rng(3).normal(0.0, 0.5, 200),
        })
        flag = detect_beta_waning_degeneracy(chain, _single_wave())
        assert flag.degenerate is False
        assert flag.second_wave is False

    def test_pinned_bound_flags_on_second_wave(self):
        # db2 median pinned to its upper bound while a second wave is present.
        chain = pd.DataFrame({
            "b0__FREE": np.full(50, 0.3),
            "db1__FREE": np.full(50, 0.8),
            "db2__FREE": np.full(50, 1.19),  # ~ pinned to high=1.2
        })
        bounds = [FreeParam("db2__FREE", -1.2, 1.2)]
        flag = detect_beta_waning_degeneracy(
            chain, _double_wave(), bounds=bounds)
        assert flag.degenerate is True

    def test_empty_chain_safe(self):
        flag = detect_beta_waning_degeneracy(pd.DataFrame(), _double_wave())
        assert flag.degenerate is False


def _write_fake_amcmc(workspace: Path, state: str, n_samples: int,
                      mixing: bool = True, boundary_param: str = None):
    """Write a synthetic AMCMC chain + scores file."""
    runs = workspace / state / "Results" / "A_MCMC" / "Runs"
    runs.mkdir(parents=True)
    rng = np.random.default_rng(42)

    bounds = {
        "I0__FREE": (0.001, 0.01),
        "b0__FREE": (0.1, 1.5),
        "gamma__FREE": (0.01, 0.5),
        "mult__FREE": (100, 8000),
        "r__FREE": (1, 30),
        "t0__FREE": (0, 12),
    }
    cols = list(bounds.keys())
    rows = []
    for _ in range(n_samples):
        sample = {}
        for c in cols:
            lo, hi = bounds[c]
            if c == boundary_param:
                # Pile up at the upper edge.
                sample[c] = rng.uniform(hi * 0.95, hi)
            else:
                sample[c] = rng.uniform(lo, hi)
        rows.append(sample)
    params_df = pd.DataFrame(rows)
    # PyBNF format: tab-separated header, space-separated rows.
    with open(runs / "params_0.txt", "w") as f:
        f.write("\t".join(cols) + "\n")
        for _, row in params_df.iterrows():
            f.write(" ".join(f"{row[c]:.10e}" for c in cols) + "\n")

    # Scores.
    if mixing:
        scores = rng.normal(-1000, 5, size=n_samples)
    else:
        # Stuck: every consecutive iteration has the same score (no acceptance).
        # Most rows duplicated 4-10x.
        chunks: list[float] = []
        n_left = n_samples
        while n_left > 0:
            score = rng.normal(-1000, 5)
            run_len = int(min(rng.integers(20, 50), n_left))
            chunks.extend([float(score)] * run_len)
            n_left -= run_len
        scores = np.array(chunks)
    np.savetxt(runs / "scores_0.txt", scores)


def test_compute_diagnostics_returns_none_when_missing(tmp_path):
    assert compute_diagnostics(tmp_path, "Alabama") is None


def test_compute_diagnostics_basic_shape(tmp_path):
    _write_fake_amcmc(tmp_path, "Alabama", n_samples=500, mixing=True)
    rep = compute_diagnostics(tmp_path / "Alabama", "Alabama",
                              burn_in_drop=100)
    assert rep is not None
    assert rep.state == "Alabama"
    assert rep.n_samples == 400  # 500 - 100 burn-in
    assert rep.acceptance_proxy > 0.5
    assert rep.ess_proxy > 100
    # Has 6 param stats.
    assert len(rep.param_stats) == 6


def test_diagnostics_detects_stuck_chain(tmp_path):
    _write_fake_amcmc(tmp_path, "Alabama", n_samples=500, mixing=False)
    rep = compute_diagnostics(tmp_path / "Alabama", "Alabama",
                              burn_in_drop=100)
    assert rep is not None
    assert not rep.healthy
    # Should warn about poor mixing (very small score range or low ESS).
    assert any("mix" in w.lower() or "stuck" in w.lower() or "ess" in w.lower()
               or "sample size" in w.lower()
               for w in rep.warnings)


def test_diagnostics_flags_boundary_crowding(tmp_path):
    _write_fake_amcmc(tmp_path, "Alabama", n_samples=500, mixing=True,
                      boundary_param="b0__FREE")
    bounds = [
        FreeParam("I0__FREE", 0.001, 0.01),
        FreeParam("b0__FREE", 0.1, 1.5),
        FreeParam("gamma__FREE", 0.01, 0.5),
        FreeParam("mult__FREE", 100, 8000),
        FreeParam("r__FREE", 1, 30),
        FreeParam("t0__FREE", 0, 12),
    ]
    rep = compute_diagnostics(tmp_path / "Alabama", "Alabama",
                              bounds=bounds, burn_in_drop=100)
    assert rep is not None
    # b0 should crowd the high boundary.
    b0_stats = next(p for p in rep.param_stats if p.name == "b0__FREE")
    assert b0_stats.frac_near_high > 0.5
    assert any("b0__FREE crowds high" in w for w in rep.warnings)


def test_react_emits_expand_bound_action(tmp_path):
    _write_fake_amcmc(tmp_path, "Alabama", n_samples=500, mixing=True,
                      boundary_param="b0__FREE")
    bounds = [
        FreeParam("b0__FREE", 0.1, 1.5),
        FreeParam("I0__FREE", 0.001, 0.01),
    ]
    rep = compute_diagnostics(tmp_path / "Alabama", "Alabama",
                              bounds=bounds, burn_in_drop=100)
    actions = react_to_diagnostics(rep)
    expand = [a for a in actions if a.kind == "expand_bound" and a.param == "b0__FREE"]
    assert len(expand) >= 1
    assert expand[0].factor > 0   # expand upward


def test_react_returns_no_action_on_clean(tmp_path):
    _write_fake_amcmc(tmp_path, "Alabama", n_samples=500, mixing=True)
    bounds = [
        FreeParam("I0__FREE", 0.001, 0.01),
        FreeParam("b0__FREE", 0.1, 1.5),
        FreeParam("gamma__FREE", 0.01, 0.5),
        FreeParam("mult__FREE", 100, 8000),
        FreeParam("r__FREE", 1, 30),
        FreeParam("t0__FREE", 0, 12),
    ]
    rep = compute_diagnostics(tmp_path / "Alabama", "Alabama",
                              bounds=bounds, burn_in_drop=100)
    actions = react_to_diagnostics(rep)
    # Synthetic uniform samples don't crowd boundaries.
    assert all(a.kind == "no_action" for a in actions)
