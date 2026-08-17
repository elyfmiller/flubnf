"""Tests for flubnf.historical_priors."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flubnf.conf_files import FreeParam
from flubnf.historical_priors import (StateHistory, SeasonSummary,
                                       informed_initial_bounds, load_history,
                                       record_season, save_history)


def _fake_pop(rng_seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(rng_seed)
    return pd.DataFrame({
        "Obj": rng.uniform(1000, 2000, 50),
        "b0__FREE": rng.normal(0.5, 0.05, 50),
        "gamma__FREE": rng.normal(0.2, 0.02, 50),
        "mult__FREE": rng.normal(1000, 100, 50),
        "t0__FREE": rng.normal(3, 0.5, 50),
        "I0__FREE": rng.normal(0.005, 0.001, 50),
    })


class TestRecordAndLoad:
    def test_record_creates_file(self, tmp_path: Path):
        pop = _fake_pop(0)
        obs = np.array([10, 50, 200, 400, 800, 600, 300, 100], dtype=float)
        hist = record_season(tmp_path, "Alabama", 2024, pop, obs, n_steps_final=2)
        assert len(hist.seasons) == 1
        assert hist.seasons[0].season_year == 2024
        assert hist.seasons[0].peak_admissions == 800
        assert hist.seasons[0].n_steps_final == 2
        # File exists.
        assert (tmp_path / "historical_priors" / "Alabama.json").exists()

    def test_record_appends_to_existing(self, tmp_path: Path):
        record_season(tmp_path, "Alabama", 2024,
                      _fake_pop(0), np.arange(10, dtype=float))
        record_season(tmp_path, "Alabama", 2025,
                      _fake_pop(1), np.arange(10, dtype=float))
        hist = load_history(tmp_path, "Alabama")
        assert [s.season_year for s in hist.seasons] == [2024, 2025]

    def test_re_record_same_year_overwrites(self, tmp_path: Path):
        record_season(tmp_path, "Alabama", 2024,
                      _fake_pop(0), np.arange(10, dtype=float))
        # Re-record with different population.
        record_season(tmp_path, "Alabama", 2024,
                      _fake_pop(99), np.arange(10, dtype=float) * 100)
        hist = load_history(tmp_path, "Alabama")
        assert len(hist.seasons) == 1
        assert hist.seasons[0].peak_admissions == 900

    def test_load_missing_returns_none(self, tmp_path: Path):
        assert load_history(tmp_path, "DoesNotExist") is None


class TestInformedBounds:
    def test_no_history_returns_base(self, tmp_path: Path):
        base = [FreeParam("b0__FREE", 0.1, 1.5)]
        hist = StateHistory(state="X", seasons=[])
        out = informed_initial_bounds(base, hist)
        assert out[0].low == 0.1
        assert out[0].high == 1.5

    def test_with_history_blends_toward_p25p75(self, tmp_path: Path):
        # History has tight bounds around 0.5.
        hist = StateHistory(
            state="X",
            seasons=[SeasonSummary(
                season_year=2024,
                best_params={"b0__FREE": 0.5},
                p25_params={"b0__FREE": 0.45},
                p75_params={"b0__FREE": 0.55},
            )],
        )
        base = [FreeParam("b0__FREE", 0.1, 1.5)]
        out = informed_initial_bounds(base, hist, blend_weight=0.5)
        # new_low = 0.5*0.1 + 0.5*0.45 = 0.275
        # new_high = 0.5*1.5 + 0.5*0.55 = 1.025
        assert out[0].low == pytest.approx(0.275, abs=0.01)
        assert out[0].high == pytest.approx(1.025, abs=0.01)

    def test_min_history_window_enforced(self, tmp_path: Path):
        # History extremely tight; blend would shrink range too much.
        hist = StateHistory(
            state="X",
            seasons=[SeasonSummary(
                season_year=2024,
                p25_params={"b0__FREE": 0.4999},
                p75_params={"b0__FREE": 0.5001},
            )],
        )
        base = [FreeParam("b0__FREE", 0.1, 1.5)]
        out = informed_initial_bounds(
            base, hist, blend_weight=0.95,
            min_history_window_pct=0.30,
        )
        # 30% of 1.4 = 0.42; new range must be >= 0.42.
        assert out[0].high - out[0].low == pytest.approx(0.42, abs=1e-6)

    def test_no_negative_low_when_base_was_nonneg(self):
        # History p25 is negative, but base was positive.
        hist = StateHistory(
            state="X",
            seasons=[SeasonSummary(
                season_year=2024,
                p25_params={"b0__FREE": -0.1},
                p75_params={"b0__FREE": 0.5},
            )],
        )
        base = [FreeParam("b0__FREE", 0.1, 1.0)]
        out = informed_initial_bounds(base, hist, blend_weight=1.0)
        assert out[0].low >= 0.0

    def test_multi_season_uses_median_of_p25p75(self):
        hist = StateHistory(
            state="X",
            seasons=[
                SeasonSummary(
                    season_year=2023,
                    p25_params={"b0__FREE": 0.30},
                    p75_params={"b0__FREE": 0.40},
                ),
                SeasonSummary(
                    season_year=2024,
                    p25_params={"b0__FREE": 0.50},
                    p75_params={"b0__FREE": 0.60},
                ),
            ],
        )
        base = [FreeParam("b0__FREE", 0.1, 1.0)]
        # blend=1 -> just the historical median(p25), median(p75).
        out = informed_initial_bounds(
            base, hist, blend_weight=1.0,
            min_history_window_pct=0.0,
        )
        # median of [0.30, 0.50] = 0.40; median of [0.40, 0.60] = 0.50.
        assert out[0].low == pytest.approx(0.40, abs=0.01)
        assert out[0].high == pytest.approx(0.50, abs=0.01)
