"""Lightweight tests for flubnf.ui_plots.

We don't render the chart; we just verify Altair builds it without
errors for representative inputs.
"""

from __future__ import annotations

from datetime import date

import altair as alt
import numpy as np
import pandas as pd

from flubnf.quantiles import FLUSIGHT_QUANTILES
from flubnf.ui_plots import build_quantile_fan, build_submission_diff_chart


def _make_q_forecast(medians: list[float]) -> dict:
    out: dict = {}
    for h_idx, med in enumerate(medians, start=1):
        out[h_idx] = {
            q: float(med + (q - 0.5) * 50.0)
            for q in FLUSIGHT_QUANTILES
        }
    return out


def test_fan_chart_with_dates_builds():
    obs = np.array([10, 20, 30, 40, 50], dtype=float)
    qf = _make_q_forecast([60, 70, 80, 90])
    chart = build_quantile_fan(
        obs, qf, horizons=[1, 2, 3, 4],
        reference_date=date(2026, 1, 3),
        state_name="Alabama",
    )
    assert isinstance(chart, alt.LayerChart) or isinstance(chart, alt.Chart)


def test_fan_chart_with_int_x():
    obs = np.array([1, 2, 3, 4, 5], dtype=float)
    qf = _make_q_forecast([6, 7, 8, 9])
    chart = build_quantile_fan(obs, qf, horizons=[1, 2, 3, 4])
    assert chart is not None


def test_fan_chart_with_actuals_overlay():
    obs = np.array([10, 20, 30, 40], dtype=float)
    qf = _make_q_forecast([50, 60, 70, 80])
    actuals = {1: 55.0, 2: float("nan"), 3: 70.0, 4: 82.0}
    chart = build_quantile_fan(
        obs, qf, horizons=[1, 2, 3, 4],
        reference_date=date(2026, 1, 3),
        actuals=actuals,
    )
    assert chart is not None


def test_fan_chart_falls_back_with_empty_quantiles():
    obs = np.array([10, 20, 30], dtype=float)
    chart = build_quantile_fan(obs, {}, horizons=[1, 2])
    assert chart is not None


def test_chain_trace_handles_empty():
    from flubnf.ui_plots import build_chain_trace_chart
    assert build_chain_trace_chart(pd.DataFrame(), param="b0__FREE") is None


def test_chain_trace_builds():
    from flubnf.ui_plots import build_chain_trace_chart
    rng = np.random.default_rng(0)
    chain = pd.DataFrame({"b0__FREE": rng.normal(0.5, 0.05, 500)})
    chart = build_chain_trace_chart(chain, param="b0__FREE", burn_in_drop=100)
    assert chart is not None


def test_posterior_density_handles_empty():
    from flubnf.ui_plots import build_posterior_density_chart
    assert build_posterior_density_chart(pd.DataFrame(),
                                          param="b0__FREE") is None


def test_posterior_density_builds():
    from flubnf.ui_plots import build_posterior_density_chart
    rng = np.random.default_rng(0)
    chain = pd.DataFrame({"b0__FREE": rng.normal(0.5, 0.05, 500)})
    chart = build_posterior_density_chart(chain, param="b0__FREE",
                                           burn_in_drop=100)
    assert chart is not None


def test_chain_trace_returns_none_for_missing_param():
    from flubnf.ui_plots import build_chain_trace_chart
    chain = pd.DataFrame({"b0__FREE": [0.5, 0.6, 0.55]})
    assert build_chain_trace_chart(chain, param="missing__FREE") is None


def test_forecast_accuracy_chart_handles_empty():
    from flubnf.ui_plots import build_forecast_accuracy_chart
    assert build_forecast_accuracy_chart(pd.DataFrame()) is None


def test_forecast_accuracy_chart_builds():
    from flubnf.ui_plots import build_forecast_accuracy_chart
    df = pd.DataFrame([
        {"reference_date": "2026-01-03", "horizon": 0,
         "our_median": 100, "our_wis": 12, "actual": 105},
        {"reference_date": "2026-01-03", "horizon": 1,
         "our_median": 110, "our_wis": 18, "actual": 130},
        {"reference_date": "2026-01-10", "horizon": 0,
         "our_median": 120, "our_wis": 15, "actual": 130},
    ])
    chart = build_forecast_accuracy_chart(df, state="Alabama")
    assert chart is not None


def test_submission_diff_chart():
    rows_a = []
    rows_b = []
    for h in range(4):
        for q in FLUSIGHT_QUANTILES:
            rows_a.append({
                "reference_date": "2026-01-03",
                "target": "wk inc flu hosp",
                "horizon": h,
                "target_end_date": f"2026-01-0{3+h}",
                "location": "01",
                "output_type": "quantile",
                "output_type_id": float(q),
                "value": 100.0 + h * 10 + (q - 0.5) * 50,
            })
            rows_b.append({
                "reference_date": "2026-01-10",
                "target": "wk inc flu hosp",
                "horizon": h,
                "target_end_date": f"2026-01-0{3+h}",
                "location": "01",
                "output_type": "quantile",
                "output_type_id": float(q),
                "value": 120.0 + h * 10 + (q - 0.5) * 50,
            })
    sub_a = pd.DataFrame(rows_a)
    sub_b = pd.DataFrame(rows_b)
    chart = build_submission_diff_chart(sub_a, sub_b, location="01")
    assert chart is not None
