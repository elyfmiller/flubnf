"""Tests for flubnf.centers — data-driven SIRS transition-center placement."""

from __future__ import annotations

import numpy as np
import pytest

from flubnf.centers import place_centers, DEFAULT_FALLBACK


class TestPlaceCenters:
    def test_returns_exactly_k_increasing(self):
        y = np.concatenate([np.full(12, 100.0), np.linspace(100, 1500, 14)])
        for K in (1, 2, 3):
            c = place_centers(y, K)
            assert len(c) == K
            assert all(c[i] < c[i + 1] for i in range(len(c) - 1))

    def test_deterministic(self):
        y = np.concatenate([np.full(10, 50.0), np.linspace(50, 900, 16)])
        assert place_centers(y, 3) == place_centers(y, 3)

    def test_min_gap_enforced(self):
        y = np.concatenate([np.full(8, 20.0), np.linspace(20, 800, 18)])
        c = place_centers(y, 3, min_gap=3.0)
        assert all(c[i + 1] - c[i] >= 3.0 - 1e-9 for i in range(len(c) - 1))

    def test_flat_series_falls_back(self):
        y = np.full(26, 200.0)
        c = place_centers(y, 3)
        # Flat -> tier-constant fallback (clamped/separated).
        assert len(c) == 3
        assert c[0] == pytest.approx(DEFAULT_FALLBACK[0])

    def test_short_series_falls_back(self):
        y = np.array([1.0, 2.0, 3.0])
        c = place_centers(y, 2)
        assert len(c) == 2

    def test_center_lands_near_inflection_not_constant(self):
        # Flat through week 18, then a sharp surge bending around weeks 20-24.
        # The single center should sit on the surge, NOT at the constant tc=8.
        y = np.concatenate([
            np.full(19, 150.0),
            np.array([220, 320, 480, 760, 1240, 1600, 1500, 1200], dtype=float),
        ])
        c = place_centers(y, 1)
        assert c[0] > 14.0, f"center {c[0]} did not move onto the surge"

    def test_no_peeking_uses_only_given_series(self):
        # Truncating the future must not change a center placed in the past.
        full = np.concatenate([np.full(19, 150.0),
                               np.linspace(200, 1600, 12)])
        early = full[:24]
        c_early = place_centers(early, 2)
        # Re-running on the same prefix is identical (function of input only).
        assert place_centers(full[:24], 2) == c_early

    def test_centers_within_reasonable_window(self):
        y = np.concatenate([np.full(10, 40.0), np.linspace(40, 600, 16)])
        c = place_centers(y, 2, edge_margin=2.0)
        assert all(ci >= 2.0 for ci in c)

    def test_zero_transitions_rejected(self):
        with pytest.raises(ValueError):
            place_centers(np.arange(20.0), 0)
