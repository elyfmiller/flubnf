"""flubnf.quantiles: the 23 FluSight levels, and QuantileForecast.

app/core/submit.py writes submissions with its own QUANTILES tuple; the two
literals are pinned equal here, since nothing else ties them together.
"""

from __future__ import annotations

import numpy as np

from app.core.submit import QUANTILES
from flubnf.quantiles import FLUSIGHT_QUANTILES, QuantileForecast


def test_levels_match_the_submission_writer():
    assert tuple(float(q) for q in FLUSIGHT_QUANTILES) == \
        tuple(float(q) for q in QUANTILES)


def test_23_sorted_levels_symmetric_about_the_median():
    q = np.array(FLUSIGHT_QUANTILES)
    assert len(q) == 23
    assert np.all(np.diff(q) > 0)
    assert q[11] == 0.5
    np.testing.assert_allclose(q + q[::-1], 1.0, atol=1e-12)


def test_to_dict_round_trips():
    horizons = (1, 2, 3, 4)
    quants = np.arange(len(FLUSIGHT_QUANTILES) * len(horizons),
                       dtype=float).reshape(len(FLUSIGHT_QUANTILES),
                                            len(horizons))
    qf = QuantileForecast(horizons=horizons,
                          quantile_levels=FLUSIGHT_QUANTILES,
                          quantiles=quants, point=quants[11])
    d = qf.to_dict()
    assert list(d) == list(horizons)
    for j, h in enumerate(horizons):
        assert list(d[h]) == [float(q) for q in FLUSIGHT_QUANTILES]
        back = np.array([d[h][float(q)] for q in FLUSIGHT_QUANTILES])
        np.testing.assert_array_equal(back, quants[:, j])
        assert d[h][0.5] == qf.point[j]
