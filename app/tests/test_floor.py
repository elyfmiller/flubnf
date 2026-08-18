"""The output floor: degenerate cells gain width, live cells barely move,
identical inputs reproduce bit-for-bit."""
import numpy as np

from app.core.floor import floor_quantiles, floor_samples


def test_degenerate_cell_gains_width_median_stays_zero():
    dead = {"1": [0.0] * 10_000, "2": [0.0] * 10_000}
    out = floor_samples(dead, "Arkansas", "2026-07-04")
    for h in ("1", "2"):
        a = np.asarray(out[h])
        assert np.quantile(a, 0.5) == 0          # dead week: median 0 is right
        assert np.quantile(a, 0.975) >= 1        # but never a point mass
        assert a.max() >= 2


def test_in_season_shift_is_negligible():
    rng = np.random.default_rng(1)
    live = {"1": rng.negative_binomial(20, 0.1, 10_000).astype(float)}
    out = floor_samples(live, "Ohio", "2026-01-24")
    before = np.quantile(np.asarray(live["1"]), [0.25, 0.5, 0.75])
    after = np.quantile(np.asarray(out["1"]), [0.25, 0.5, 0.75])
    assert np.all(np.abs(after - before) <= 2)   # ~+0.35 mean on counts ~180


def test_seeded_reproducibility():
    dead = {"1": [0.0] * 100}
    a = floor_samples(dead, "Arkansas", "2026-07-04")
    b = floor_samples(dead, "Arkansas", "2026-07-04")
    assert a == b
    c = floor_samples(dead, "Arizona", "2026-07-04")
    assert a != c                                 # location enters the seed


def test_quantile_floor_lifts_flat_zero_only_where_needed():
    flat = {"1": {0.025: 0.0, 0.25: 0.0, 0.5: 0.0, 0.75: 0.0, 0.975: 0.0}}
    out = floor_quantiles(flat)
    assert out["1"][0.5] == 0
    assert out["1"][0.75] >= 1
    assert out["1"][0.975] >= 2
    rich = {"1": {0.025: 3.0, 0.5: 10.0, 0.975: 40.0}}
    assert floor_quantiles(rich) == {"1": {0.025: 3.0, 0.5: 10.0, 0.975: 40.0}}
