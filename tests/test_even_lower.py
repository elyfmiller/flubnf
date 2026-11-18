"""scripts/even_lower.py: the lower half narrowed so the 95% band is no
wider below the median than above on the log scale; the median, the upper
half and every other row untouched."""
from __future__ import annotations

import importlib.util
import math
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "even_lower.py"
LEVELS = [0.01, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5,
          0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.975, 0.99]


@pytest.fixture(scope="module")
def ev():
    spec = importlib.util.spec_from_file_location("even_lower", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _block(m, below, above):
    """Values symmetric in log about m with log half-widths below/above."""
    out = {}
    for lv in LEVELS:
        z = (lv - 0.5) / 0.475                      # -1 at 2.5%, +1 at 97.5%
        out[lv] = float(round(m * math.exp(z * (below if z < 0 else above))))
    return out


def _frame(blocks):
    rows = []
    for (loc, h), v in blocks.items():
        for lv in LEVELS:
            rows.append({"reference_date": "2026-11-21", "target": "wk inc flu hosp",
                         "horizon": h, "target_end_date": "2026-11-28", "location": loc,
                         "output_type": "quantile", "output_type_id": str(lv),
                         "value": v[lv]})
    return pd.DataFrame(rows)


def _balance(v):
    return math.log(v[0.5] / v[0.025]) / math.log(v[0.975] / v[0.5])


def test_a_band_wider_below_comes_out_even_per_horizon(ev):
    blocks = {("01", 0): _block(1000, 0.9, 0.5), ("01", 1): _block(1200, 1.2, 0.6)}
    out, changed = ev.even_lower(_frame(blocks))
    assert {(c[0], c[1]) for c in changed} == {("01", 0), ("01", 1)}
    for h in (0, 1):
        g = out[out.horizon == h]
        v = dict(zip(g.output_type_id.astype(float), g.value.astype(float)))
        assert abs(_balance(v) - 1.0) < 0.02
        old = blocks[("01", h)]
        assert all(v[lv] == old[lv] for lv in LEVELS if lv >= 0.5)   # median, top
        assert all(v[lv] >= old[lv] for lv in LEVELS if lv < 0.5)    # only narrower
        vals = [v[lv] for lv in LEVELS]
        assert vals == sorted(vals)


def test_per_location_takes_the_smallest_exponent(ev):
    blocks = {("01", 0): _block(1000, 0.9, 0.5), ("01", 1): _block(1200, 1.2, 0.6)}
    _, by_h = ev.even_lower(_frame(blocks))
    _, by_loc = ev.even_lower(_frame(blocks), per_horizon=False)
    k = min(c[2] for c in by_h)
    assert all(abs(c[2] - k) < 1e-9 for c in by_loc)


def test_a_band_narrower_below_and_other_rows_are_left_alone(ev):
    blocks = {("02", 0): _block(500, 0.4, 0.8), ("02", 1): _block(500, 0.45, 0.5)}
    f = _frame(blocks)
    f = pd.concat([f, pd.DataFrame([{"reference_date": "2026-11-21",
                   "target": "wk flu hosp rate change", "horizon": 0,
                   "target_end_date": "2026-11-21", "location": "02",
                   "output_type": "pmf", "output_type_id": "increase", "value": 0.4}])])
    out, changed = ev.even_lower(f)
    assert changed == []
    assert out.value.astype(float).tolist() == f.value.astype(float).tolist()


def test_zeros_stay_zero_and_the_script_writes_whole_numbers(ev, tmp_path):
    v = _block(20, 2.0, 0.4)
    v[0.01] = 0.0
    src, dst = tmp_path / "in.csv", tmp_path / "out.csv"
    _frame({("56", 0): v}).to_csv(src, index=False)
    r = subprocess.run([sys.executable, str(SCRIPT), str(src), str(dst)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "narrowed in 1 blocks" in r.stdout
    out = pd.read_csv(dst, dtype=str)
    assert all("." not in x for x in out.value)
    got = dict(zip(out.output_type_id.astype(float), out.value.astype(float)))
    assert got[0.01] == 0.0 and got[0.5] == 20.0
