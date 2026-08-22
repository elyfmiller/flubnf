"""Build 2 additive parameter: completeness-corrected analogue anchor.

The default path must remain byte-identical to the pre-change analogue.
These tests pin that identity, the algebra of the correction, and the
lag-0 gating of the engine helper. No vintage files are needed: the
library tests run on a synthetic bank, the helper tests on dummy specs.
"""
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flubnf import analogue as AN                      # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL  # noqa: E402


def _bank():
    """Two full prior seasons, eight locations, smooth positive values:
    plenty of donors at every epiweek for MIN_DONORS."""
    bank = {}
    d0 = date(2023, 8, 5)
    for li in range(8):
        loc = f"L{li}"
        for w in range(104):
            d = d0 + timedelta(days=7 * w)
            bank[(loc, d)] = 80.0 + 30.0 * math.sin(w / 6.0 + li) + 2.0 * li
    return bank


ASOF = date(2025, 12, 20)     # season 2025, all bank seasons strictly prior
ANCHOR = 123.0


def test_default_identity():
    """Explicit None arguments are byte-identical to omitting them."""
    bank = _bank()
    for h in (1, 2, 3, 4):
        base = AN.forecast(ANCHOR, ASOF, h, bank, QL)
        same = AN.forecast(ANCHOR, ASOF, h, bank, QL,
                           completeness=None, widen_log_sd=None)
        assert base is not None
        assert same == base


def test_neutral_values_identity():
    """completeness=1.0 and widen_log_sd=0.0 change nothing."""
    bank = _bank()
    base = AN.forecast(ANCHOR, ASOF, 2, bank, QL)
    neut = AN.forecast(ANCHOR, ASOF, 2, bank, QL,
                       completeness=1.0, widen_log_sd=0.0)
    assert neut == base


def test_completeness_scales_every_quantile():
    bank = _bank()
    base = AN.forecast(ANCHOR, ASOF, 1, bank, QL)
    corr = AN.forecast(ANCHOR, ASOF, 1, bank, QL, completeness=0.8)
    assert base is not None and corr is not None
    for L in base:
        assert corr[L] == pytest.approx(base[L] / 0.8, rel=1e-12)


def test_widening_keeps_median_and_widens_tails():
    bank = _bank()
    base = AN.forecast(ANCHOR, ASOF, 3, bank, QL)
    wide = AN.forecast(ANCHOR, ASOF, 3, bank, QL, widen_log_sd=0.15)
    assert base is not None and wide is not None
    assert wide[0.5] == base[0.5]                 # z(0.5) = 0 exactly
    assert wide[0.975] > base[0.975]
    assert wide[0.025] < base[0.025]
    vals = [wide[float(L)] for L in sorted(wide)]
    assert all(b >= a for a, b in zip(vals, vals[1:]))
    assert all(v > 0 for v in vals)


def test_bad_completeness_fails_loudly():
    bank = _bank()
    for bad in (0.0, -0.5, float("nan")):
        with pytest.raises(ValueError):
            AN.forecast(ANCHOR, ASOF, 1, bank, QL, completeness=bad)
    with pytest.raises(ValueError):
        AN.forecast(ANCHOR, ASOF, 1, bank, QL, widen_log_sd=-0.1)


def test_engine_helper_default_and_gating():
    from app.core.engines.analogue import completeness_args
    lag0 = "2025-12-20"
    older = "2025-12-13"

    # spec without an extra attribute at all
    assert completeness_args(object(), "06", lag0, lag0) == (None, None)
    # extra=None and extra={} both mean: no correction
    assert completeness_args(SimpleNamespace(extra=None),
                             "06", lag0, lag0) == (None, None)
    assert completeness_args(SimpleNamespace(extra={}),
                             "06", lag0, lag0) == (None, None)
    # a table without this state: no correction
    spec = SimpleNamespace(extra={"analogue_completeness": {"48": 0.9},
                                  "analogue_widen_log_sd": 0.12})
    assert completeness_args(spec, "06", lag0, lag0) == (None, None)
    # this state, but the anchor is older than the vintage's newest week
    assert completeness_args(spec, "48", older, lag0) == (None, None)
    # this state at lag 0: correction and widening apply
    assert completeness_args(spec, "48", lag0, lag0) == (0.9, 0.12)
    # scale-only arm: no widening key
    spec2 = SimpleNamespace(extra={"analogue_completeness": {"48": 0.9}})
    assert completeness_args(spec2, "48", lag0, lag0) == (0.9, None)
