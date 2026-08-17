"""Plotting helpers for the Streamlit UI.

Streamlit's built-in `st.line_chart` is fine for single series; for the
FluSight-style quantile fan we use Altair directly so we can nest the
50% / 80% / 95% interval bands behind the median.

Inputs are deliberately simple dataframes so this module has no UI
dependency beyond pandas + altair.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Sequence

import altair as alt
import numpy as np
import pandas as pd

from .quantiles import FLUSIGHT_QUANTILES


# Map of FluSight quantile levels to "PI cover %" bands we'll shade.
# Each band is (lower_q, upper_q, label).
PI_BANDS: list[tuple[float, float, str]] = [
    (0.025, 0.975, "95% PI"),
    (0.10,  0.90,  "80% PI"),
    (0.25,  0.75,  "50% PI"),
]


def build_quantile_fan(
    observed: np.ndarray,
    quantile_forecast: dict,
    horizons: Sequence[int],
    *,
    reference_date: Optional[date] = None,
    actuals: Optional[dict] = None,
    state_name: str = "",
) -> alt.Chart:
    """Build an Altair fan chart of observed history + quantile forecast.

    Args:
      observed:          historical H_weekly series, 1 value per week.
      quantile_forecast: dict[h] -> dict[quantile_level] -> value (FluSight format).
      horizons:          1-indexed horizons (e.g. [1,2,3,4]).
      reference_date:    Saturday of the last observed week. Used to label the
                         x-axis as a date series if provided; otherwise weeks
                         are indexed as integers.
      actuals:           dict[h] -> observed actual at horizon h, plotted as
                         dots over the forecast. Used in retrospective mode.
      state_name:        for the chart title.
    """
    horizons = tuple(horizons)
    n_obs = len(observed)
    if reference_date is not None:
        # x-axis = actual dates. observed weeks end on the last observed Saturday.
        last_sat = reference_date  # convention: reference_date = last obs week's Saturday
        weeks_back = [last_sat - timedelta(days=7 * (n_obs - 1 - i)) for i in range(n_obs)]
        obs_df = pd.DataFrame({"date": weeks_back, "value": observed,
                               "kind": "observed"})
        future_dates = [last_sat + timedelta(days=7 * h) for h in horizons]
    else:
        obs_df = pd.DataFrame({"date": list(range(n_obs)), "value": observed,
                               "kind": "observed"})
        future_dates = [n_obs - 1 + h for h in horizons]

    # Build long-form quantile DataFrame
    rows = []
    for h, dt in zip(horizons, future_dates):
        qd = quantile_forecast.get(h, {})
        for q in FLUSIGHT_QUANTILES:
            v = qd.get(q) or qd.get(float(q))
            if v is None:
                continue
            rows.append({"date": dt, "quantile": float(q), "value": float(v)})
    q_df = pd.DataFrame(rows)

    if q_df.empty:
        # Nothing to plot.
        return alt.Chart(obs_df).mark_line(color="#16355f").encode(
            x=alt.X("date:T" if reference_date else "date:Q", title=None),
            y=alt.Y("value:Q", title="H_weekly"),
        ).properties(title=f"{state_name} — observed only", height=320)

    # Pivot to wide for band drawing.
    wide = q_df.pivot(index="date", columns="quantile", values="value").reset_index()

    # Layered fan: outer → inner bands so inner ones are drawn on top.
    layers = []
    for lo, hi, label in PI_BANDS:
        if lo not in wide.columns or hi not in wide.columns:
            continue
        # Find the band that contains this layer for opacity tuning.
        opacity = {"95% PI": 0.18, "80% PI": 0.30, "50% PI": 0.45}[label]
        band = alt.Chart(wide).mark_area(
            color="#0b6b3a", opacity=opacity,
        ).encode(
            x=alt.X("date:T" if reference_date else "date:Q", title=None),
            y=alt.Y(f"{lo}:Q", title="H_weekly",
                    scale=alt.Scale(zero=False)),
            y2=alt.Y2(f"{hi}:Q"),
            tooltip=[alt.Tooltip("date:T" if reference_date else "date:Q",
                                 title="week"),
                     alt.Tooltip(f"{lo}:Q", title="lo", format=".0f"),
                     alt.Tooltip(f"{hi}:Q", title="hi", format=".0f")],
        )
        layers.append(band)

    # Median line (q=0.5).
    if 0.5 in wide.columns:
        median = alt.Chart(wide).mark_line(
            color="#0b6b3a", strokeWidth=2.5,
        ).encode(
            x=alt.X("date:T" if reference_date else "date:Q"),
            y=alt.Y("0.5:Q"),
            tooltip=[alt.Tooltip("date:T" if reference_date else "date:Q",
                                 title="week"),
                     alt.Tooltip("0.5:Q", title="forecast median",
                                 format=".0f")],
        )
        layers.append(median)
        # Marker on the median dots.
        layers.append(alt.Chart(wide).mark_circle(
            color="#0b6b3a", size=70,
        ).encode(
            x=alt.X("date:T" if reference_date else "date:Q"),
            y=alt.Y("0.5:Q"),
        ))

    # Observed line in navy.
    obs_layer = alt.Chart(obs_df).mark_line(
        color="#16355f", strokeWidth=2.5,
    ).encode(
        x=alt.X("date:T" if reference_date else "date:Q", title=None),
        y=alt.Y("value:Q", title="H_weekly"),
        tooltip=[alt.Tooltip("date:T" if reference_date else "date:Q",
                             title="week"),
                 alt.Tooltip("value:Q", title="observed", format=".0f")],
    )
    obs_dots = alt.Chart(obs_df).mark_circle(
        color="#16355f", size=40,
    ).encode(
        x=alt.X("date:T" if reference_date else "date:Q"),
        y=alt.Y("value:Q"),
    )
    layers = [obs_layer, obs_dots] + layers

    # Actuals overlay if provided (red Xs).
    if actuals:
        actuals_rows = []
        for h, dt in zip(horizons, future_dates):
            v = actuals.get(h)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                actuals_rows.append({"date": dt, "value": float(v)})
        if actuals_rows:
            actuals_df = pd.DataFrame(actuals_rows)
            actuals_marker = alt.Chart(actuals_df).mark_point(
                color="#c0392b", shape="cross", size=180, filled=True,
                strokeWidth=3,
            ).encode(
                x=alt.X("date:T" if reference_date else "date:Q"),
                y=alt.Y("value:Q"),
                tooltip=[alt.Tooltip("value:Q", title="actual",
                                     format=".0f")],
            )
            layers.append(actuals_marker)

    chart = alt.layer(*layers).resolve_scale(y="shared").properties(
        height=340,
        title=f"{state_name} — observed history + forecast quantile fan"
        if state_name else "Observed history + forecast quantile fan",
    ).interactive()
    return chart


def build_chain_trace_chart(
    chain: pd.DataFrame, *, param: str, burn_in_drop: int = 100,
) -> Optional[alt.Chart]:
    """Trace plot of one parameter over iterations — visual mixing check.

    Healthy chains wander broadly across iterations; stuck chains stay
    flat for long runs. We draw a thin line + a smoother (rolling
    median) on top so the eye can see the bulk shape.
    """
    if chain is None or chain.empty or param not in chain.columns:
        return None
    df = pd.DataFrame({"iter": range(len(chain)),
                       "value": chain[param].astype(float).values})
    if burn_in_drop > 0:
        df = df[df["iter"] >= burn_in_drop].reset_index(drop=True)
    if df.empty:
        return None
    smooth = df.assign(
        smoothed=df["value"].rolling(window=max(5, len(df) // 20),
                                      min_periods=1, center=True).median()
    )
    line = alt.Chart(df).mark_line(
        color="#999", strokeWidth=0.6, opacity=0.5,
    ).encode(
        x=alt.X("iter:Q", title="iteration"),
        y=alt.Y("value:Q", title=param,
                scale=alt.Scale(zero=False)),
    )
    smoothed = alt.Chart(smooth).mark_line(
        color="#16355f", strokeWidth=2,
    ).encode(
        x=alt.X("iter:Q"),
        y=alt.Y("smoothed:Q"),
    )
    return alt.layer(line, smoothed).properties(
        height=200, title=f"chain trace — {param}",
    ).interactive()


def build_posterior_density_chart(
    chain: pd.DataFrame, *, param: str, burn_in_drop: int = 100,
) -> Optional[alt.Chart]:
    """Posterior density (kde proxy via histogram) for one parameter."""
    if chain is None or chain.empty or param not in chain.columns:
        return None
    df = pd.DataFrame({"value": chain[param].astype(float).values})
    if burn_in_drop > 0 and len(df) > burn_in_drop:
        df = df.iloc[burn_in_drop:].reset_index(drop=True)
    if df.empty:
        return None
    chart = alt.Chart(df).mark_bar(
        opacity=0.7, color="#16355f",
    ).encode(
        alt.X(f"value:Q", bin=alt.Bin(maxbins=40), title=param),
        alt.Y("count():Q", title="samples"),
    ).properties(
        height=200, title=f"posterior density — {param}",
    )
    # Median rule overlaid.
    median = float(df["value"].median())
    median_rule = alt.Chart(pd.DataFrame({"v": [median]})).mark_rule(
        color="#c0392b", strokeWidth=2,
    ).encode(x="v:Q")
    return alt.layer(chart, median_rule).resolve_scale(y="independent")


def build_forecast_accuracy_chart(
    forecast_actuals: pd.DataFrame,
    *,
    state: str = "",
) -> Optional[alt.Chart]:
    """Show how previous forecasts compared to realized actuals over
    the season.

    `forecast_actuals` columns:
      reference_date, horizon, our_median, our_wis, actual
    """
    if forecast_actuals is None or forecast_actuals.empty:
        return None
    df = forecast_actuals.copy()
    df["reference_date"] = pd.to_datetime(df["reference_date"])
    # Two layers: connected dots for actual, dots for median by horizon.
    h_chart = alt.Chart(df).mark_line(
        opacity=0.6, point=True, strokeWidth=1.5,
    ).encode(
        x=alt.X("reference_date:T", title="reference Saturday"),
        y=alt.Y("our_median:Q", title="H_weekly"),
        color=alt.Color("horizon:O", title="horizon ahead"),
        tooltip=["reference_date:T", "horizon:O", "our_median:Q",
                 "actual:Q", "our_wis:Q"],
    )
    # Single black line of realized actuals at h=0.
    h0 = df[df["horizon"] == 0]
    if not h0.empty:
        actuals_chart = alt.Chart(h0).mark_line(
            color="#16355f", strokeWidth=2.5,
        ).encode(
            x=alt.X("reference_date:T"),
            y=alt.Y("actual:Q"),
            tooltip=["reference_date:T", "actual:Q"],
        )
        layers = [h_chart, actuals_chart]
    else:
        layers = [h_chart]
    return alt.layer(*layers).properties(
        height=300, title=f"{state} — forecast medians vs realized actuals"
        if state else "Forecast medians vs realized actuals",
    ).interactive()


def build_submission_diff_chart(
    sub_a: pd.DataFrame, sub_b: pd.DataFrame, location: str,
    *, label_a: str = "A", label_b: str = "B",
) -> Optional[alt.Chart]:
    """Side-by-side chart of two submissions' quantile bands for a single
    location, useful in the Submission Hub for diffing week-over-week."""
    a = sub_a[(sub_a.location == location) & (sub_a.output_type == "quantile")].copy()
    b = sub_b[(sub_b.location == location) & (sub_b.output_type == "quantile")].copy()
    if a.empty and b.empty:
        return None
    rows: list[dict] = []
    for df, label in [(a, label_a), (b, label_b)]:
        for _, r in df.iterrows():
            rows.append({
                "target_end_date": pd.to_datetime(r["target_end_date"]).date(),
                "quantile": float(r["output_type_id"]),
                "value": float(r["value"]),
                "submission": label,
            })
    long_df = pd.DataFrame(rows)
    if long_df.empty:
        return None
    wide = long_df.pivot_table(
        index=["target_end_date", "submission"],
        columns="quantile", values="value",
    ).reset_index()
    chart = alt.Chart(wide).mark_area(opacity=0.35).encode(
        x=alt.X("target_end_date:T", title="forecast date"),
        y=alt.Y("0.05:Q", title="H_weekly"),
        y2="0.95:Q",
        color=alt.Color("submission:N"),
    )
    medians = alt.Chart(wide).mark_line(strokeWidth=2.5).encode(
        x="target_end_date:T",
        y="0.5:Q",
        color="submission:N",
    )
    return alt.layer(chart, medians).resolve_scale(y="shared").properties(
        height=320,
        title=f"FIPS {location} — {label_a} vs {label_b} forecasts",
    ).interactive()
