"""PRODUCTION: WIS scoring and the scored-cell rule (server run scoring, retro,
playback, site_build).

WIS scoring of stored forecasts against truth: the report's accuracy
figures and the per-run WIS breakdown.

Settled truth available NOW for actuals, the FluSight baseline from the same
series; relWIS < 1 beats the baseline. Cells are (location, forecast_date,
horizon).

THE CELL RULE is FluSight's (hubEvals and scoringutils, which the CDC
dashboard runs), defined once here (`cell_scored`) and used by every
scorer: a cell is scored when settled truth exists (finite and at least 0,
so a week of 0 admissions counts), the model's forecast for the cell exists
with finite quantiles (a median of 0 counts too), and FluSight-baseline
scored the same cell (the ratio needs it). A model contributes only the
cells it forecast, so two models' cell sets can differ. Until 2026-09-25
the rule also required truth above 0 and a positive median; figures
recorded before then (oracle_text.RECORD, the sealed seasons, docs tables)
were measured that way and differ from a rescore at about the third
decimal.

PER-CELL METRICS (`cell_metrics`, from flubnf.wis): WIS, log-scale WIS
(WIS of log(x + 1), the dashboard's log scale) and whether truth lies
inside the central 50, 80 and 95 percent intervals (inclusive), plus the
baseline's WIS and log-scale WIS on the same cell. `pooled_metrics`
summarises scored rows: relWIS and log-scale relWIS as ratios of sums, and
coverage as the fraction of cells covered.
"""
from __future__ import annotations

import math
from datetime import timedelta
from typing import Mapping

import numpy as np
import pandas as pd

from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
from flubnf.wis import COVERAGE_BANDS, coverage, log_wis, wis
from flubnf.settings import HUB


#: what the last load_truth() served: "settled", or "vintage <date>" when the
#: newest archived vintage stood in (surfaces print it: never a silent fallback)
TRUTH_SOURCE = "settled"


def load_truth() -> tuple:
    """(location_fips, week_ending Timestamp) -> value, from the hub's
    current target file; plus name->fips. Sets TRUTH_SOURCE."""
    global TRUTH_SOURCE
    target = HUB / "target-data/target-hospital-admissions.csv"
    TRUTH_SOURCE = "settled"
    if not target.is_file():
        # the newest vintage is settled for older weeks (retrospectives) but
        # provisional for its last 1-2: record the substitution and say so
        from app.core.data import vintage_path, vintages
        vs = vintages()
        if not vs:
            raise FileNotFoundError(
                f"no settled truth: {target} missing and no dated vintages in "
                f"{HUB}/auxiliary-data/target-data-archive. Update the hub "
                "clone from the Data tab.")
        target = vintage_path(vs[-1])
        TRUTH_SOURCE = f"vintage {vs[-1]}"
        import sys
        print(f"scoring: current target file missing; scoring against the "
              f"newest archived vintage ({vs[-1]}). Its final weeks may be "
              "provisional. Update the hub clone from the Data tab.",
              file=sys.stderr)
    t = pd.read_csv(target, dtype={"location": str})
    t["location"] = t["location"].str.zfill(2)
    t["date"] = pd.to_datetime(t["date"])
    locs = pd.read_csv(HUB / "auxiliary-data/locations.csv", dtype=str)
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    truth = {(r.location, r.date): float(r.value)
             for r in t.itertuples() if np.isfinite(r.value)}
    return truth, n2f


#: the per-cell metric columns a scored row carries beside location, horizon
#: and the baseline join (base_wis, base_log_wis, rel): cov* are 0/1
METRIC_COLUMNS = ("wis", "log_wis", "cov50", "cov80", "cov95")
#: the coverage columns, in COVERAGE_BANDS order, and their labels
COVERAGE_COLUMNS = tuple(f"cov{label}" for label, _lo, _hi in COVERAGE_BANDS)
COVERAGE_LABELS = tuple(label for label, _lo, _hi in COVERAGE_BANDS)


# ------------------------------------------------------------ the cell rule

def truth_settled(actual) -> bool:
    """Settled truth for a cell: a finite value of at least 0 (a week of 0
    admissions is scored, as FluSight scores it)."""
    try:
        a = float(actual)
    except (TypeError, ValueError):
        return False
    return math.isfinite(a) and a >= 0


def forecast_scoreable(q) -> bool:
    """A forecast cell that can be scored: a quantile set holding the median
    with every value finite (a median of 0 is a forecast like any other)."""
    if not q:
        return False
    try:
        pairs = [(float(L), float(v)) for L, v in q.items()]
    except (AttributeError, TypeError, ValueError):
        return False
    return (any(abs(L - 0.5) < 1e-9 for L, _v in pairs)
            and all(math.isfinite(v) for _L, v in pairs))


def cell_scored(q, actual, base) -> bool:
    """THE cell rule (module docstring): settled truth, a scoreable forecast
    and a baseline score for the same cell."""
    if base is None:
        return False
    try:
        if not math.isfinite(float(base)):
            return False
    except (TypeError, ValueError):
        return False
    return truth_settled(actual) and forecast_scoreable(q)


def cell_metrics(q, actual) -> dict | None:
    """{"wis", "log_wis", "cov50", "cov80", "cov95"} for one forecast cell
    against its truth (cov* 1 when truth lies inside the interval, 0 when
    not, None when the forecast lacks its levels); None when these
    quantiles give no WIS (a level missing)."""
    try:
        w = float(wis(q, actual).wis)
        lw = float(log_wis(q, actual))
    except Exception:
        return None
    cov = coverage(q, actual)
    return {"wis": w, "log_wis": lw,
            **{f"cov{k}": cov[k] for k in COVERAGE_LABELS}}


# -------------------------------------------------------------- the baseline

#: the log-scale scores the last _baseline_cells call built beside its WIS,
#: so the _baseline_log_cells call after it reads the file once: one
#: (key, truth, cells) tuple, replaced whole (a reader in another thread sees
#: the old tuple or the new one). Holds the truth mapping itself (identity
#: check), never just its id.
_LOG_SLOT: dict = {}


def _baseline_frame(forecast_date: str, fips_set, truth) -> pd.DataFrame:
    """The validated FluSight-baseline rows for one forecast date (wis and
    log_wis per cell). Raises when the clone lacks FluSight-baseline."""
    from flubnf.baseline import baseline_cells
    from flubnf.settings import HUB as _HUB
    if not (_HUB / "model-output" / "FluSight-baseline").is_dir():
        raise FileNotFoundError(
            "the hub clone has no model-output/FluSight-baseline (sparse "
            "checkout predates the baseline requirement). Press Update data "
            "on the Data tab to fetch it, then rescore.")
    return baseline_cells([forecast_date], set(fips_set), truth, hub=_HUB)


def _cells_of(b: pd.DataFrame, column: str) -> dict:
    if b.empty or column not in b.columns:
        # early season (<5 history points): an empty frame has no columns
        return {}
    k = list(zip(b.location, b["asof"], b.horizon))
    s = pd.Series(list(b[column]), index=k)
    return s[~s.index.duplicated()].to_dict()


def _baseline_cells(forecast_date: str, fips_set, truth):
    """The VALIDATED baseline construction (flubnf.baseline; a hand-rolled
    one scored ~40% easier): {(fips, forecast_date, horizon): WIS}. Raises
    when the clone lacks FluSight-baseline."""
    b = _baseline_frame(forecast_date, fips_set, truth)
    _LOG_SLOT["last"] = ((str(forecast_date), frozenset(fips_set)), truth,
                         _cells_of(b, "log_wis"))
    return _cells_of(b, "wis")


def _baseline_log_cells(forecast_date: str, fips_set, truth) -> dict:
    """The same cells' log-scale WIS, {(fips, forecast_date, horizon):
    log WIS}; {} when the baseline cannot be built (the log figures are
    then absent, never a failure of the natural-scale score)."""
    last = _LOG_SLOT.get("last")
    if (last is not None and last[1] is truth
            and last[0] == (str(forecast_date), frozenset(fips_set))):
        return dict(last[2])
    try:
        return _cells_of(_baseline_frame(forecast_date, fips_set, truth),
                         "log_wis")
    except Exception:
        return {}


# ----------------------------------------------------------------- scorers

def _scored_frame(rows: list, forecast_date: str, truth) -> pd.DataFrame:
    """Join the baseline onto per-cell rows (location, fips, horizon and the
    METRIC_COLUMNS) and keep the cells the rule scores."""
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    bs = _baseline_cells(forecast_date, set(df.fips), truth)
    lbs = _baseline_log_cells(forecast_date, set(df.fips), truth)
    df["base_wis"] = [bs.get((r.fips, forecast_date, r.horizon), np.nan)
                      for r in df.itertuples()]
    df["base_log_wis"] = [lbs.get((r.fips, forecast_date, r.horizon), np.nan)
                          for r in df.itertuples()]
    df = df.dropna(subset=["base_wis"])
    df["rel"] = df.wis / df.base_wis
    return df


def _cell_row(loc, fips, h: int, q, actual) -> dict | None:
    """One scored row before the baseline join, or None when the forecast
    or the truth fails the rule (the baseline half is checked at the join)."""
    if not (truth_settled(actual) and forecast_scoreable(q)):
        return None
    m = cell_metrics(q, actual)
    if m is None:
        return None
    return {"location": loc, "fips": fips, "horizon": h, **m}


def score_samples(samples_by_loc: Mapping, forecast_date: str,
                  name2fips: Mapping, truth: Mapping) -> pd.DataFrame:
    """rows: location, fips, horizon, the METRIC_COLUMNS, base_wis,
    base_log_wis, rel. Scored under the cell rule."""
    rows = []
    T = pd.Timestamp(forecast_date)
    for loc, s in samples_by_loc.items():
        fips = name2fips.get(loc)
        if not fips:
            continue
        for h in (0, 1, 2, 3):
            # canonical h is h+1 weeks past the as-of; ORIGIN is never scored
            arr = np.asarray(s.get(str(h), []), float)
            arr = arr[np.isfinite(arr)]
            if not arr.size:
                continue
            actual = truth.get((fips, T + timedelta(days=7 * (h + 1))))
            q = {float(L): float(np.quantile(arr, L)) for L in QL}
            row = _cell_row(loc, fips, h, q, actual)
            if row is not None:
                rows.append(row)
    return _scored_frame(rows, forecast_date, truth)


def score_quantiles(q_by_loc: Mapping, forecast_date: str,
                    name2fips: Mapping, truth: Mapping) -> pd.DataFrame:
    """score_samples for members stored as quantile sets, {location:
    {"0".."3": {level: value}}}: same cell rule, baseline and columns."""
    rows = []
    T = pd.Timestamp(forecast_date)
    for loc, qs in q_by_loc.items():
        fips = name2fips.get(loc)
        if not fips or not isinstance(qs, Mapping):
            continue
        for h in (0, 1, 2, 3):
            q = qs.get(str(h)) or qs.get(h)
            if not q:
                continue
            try:
                q = {float(L): float(v) for L, v in q.items()}
            except (TypeError, ValueError):
                continue
            actual = truth.get((fips, T + timedelta(days=7 * (h + 1))))
            row = _cell_row(loc, fips, h, q, actual)
            if row is not None:
                rows.append(row)
    return _scored_frame(rows, forecast_date, truth)


# ----------------------------------------------------------------- summaries

def _ratio(num, den):
    return (float(num) / float(den)) if den else None


def pooled_metrics(df) -> dict:
    """{"rel", "log_rel", "cov", "n"} over a frame of scored rows: relWIS
    and log-scale relWIS as ratios of sums, `cov` the fraction of cells
    inside each central interval ({"50", "80", "95"}), `n` the cell count.

    A figure the frame cannot give is None: log_rel and cov when its columns
    are absent or incomplete (a scores.json written before these metrics, a
    sealed root), all of them for an empty frame."""
    out = {"rel": None, "log_rel": None, "cov": None, "n": 0}
    if df is None or not len(df) or not {"wis", "base_wis"} <= set(df.columns):
        return out
    out["n"] = int(len(df))
    out["rel"] = _ratio(df["wis"].sum(), df["base_wis"].sum())
    if {"log_wis", "base_log_wis"} <= set(df.columns):
        lw = pd.to_numeric(df["log_wis"], errors="coerce")
        lb = pd.to_numeric(df["base_log_wis"], errors="coerce")
        if lw.notna().all() and lb.notna().all():
            out["log_rel"] = _ratio(lw.sum(), lb.sum())
    cov = {}
    for label, col in zip(COVERAGE_LABELS, COVERAGE_COLUMNS):
        if col in df.columns:
            c = pd.to_numeric(df[col], errors="coerce")
            if c.notna().all():
                cov[label] = float(c.mean())
    out["cov"] = cov if len(cov) == len(COVERAGE_LABELS) else None
    return out


#: THE cell rule in one sentence, printed wherever scored-cell counts are
CELL_RULE_NOTE = (
    "A cell is scored when settled truth exists (a week of 0 included), "
    "the model forecast it, and FluSight-baseline scored the same cell, as "
    "in FluSight's own scoring.")


def earlier_rule_note(stored: list, fresh: list) -> str:
    """The line printed where a page shows figures read from a scores.json
    of an earlier retro.SCORES_V (a sealed record, scored when truth and the
    median had to be above 0) beside figures scored under CELL_RULE_NOTE's
    rule. `stored` and `fresh` name each set's figures, lower case."""
    def _and(items):
        items = list(items)
        return (", ".join(items[:-1]) + " and " + items[-1]
                if len(items) > 1 else "".join(items))
    return ("Read from this season's stored scores, which used an earlier "
            "cell rule (settled truth and a forecast median both above 0): "
            f"{_and(stored)}. Scored under FluSight's rule: {_and(fresh)}. "
            "The two rules can give slightly different figures.")


#: the empty-table placeholder (the weekly report recognises it)
NO_SCORES_HTML = ("<p class='hint'>No scored weeks yet. relWIS appears once "
                  "truth for forecast weeks is published.</p>")


def _member_name(model: str) -> str:
    fallback = {"pf": "Oracle SIHRS", "analogue": "Groundhog"}
    try:                       # the shared name map, one source (no drift)
        from app.core.report_season import MODEL_NAMES
        return MODEL_NAMES.get(model, fallback.get(model, model))
    except Exception:
        return fallback.get(model, model)


def summary_table_html(df: pd.DataFrame, model: str | None = None) -> str:
    """The report's WIS-breakdown card for one member (`model`, default the
    Oracle SIHRS): the member named in the header, ok/bad classes, each
    score with its cell count; a placeholder when empty, naming the member
    when `model` is given. The US row keeps its own (fitted) line but stays
    out of the pooled total (us_national.POOLED_INCLUDES_US)."""
    from app.core import us_national as usn
    if df.empty:
        if model is None:
            return NO_SCORES_HTML
        return (f"<p class='hint'>{_member_name(model)}: no scored weeks "
                "yet. relWIS appears once truth for forecast weeks is "
                "published.</p>")
    member = _member_name(model or "pf")
    per_loc = (df.groupby("location")
                 .apply(lambda g: g.wis.sum() / g.base_wis.sum(),
                        include_groups=False)
                 .sort_values())
    cells = df.groupby("location").size()
    pooled = usn.pooled_frame(df)
    has_us = len(pooled) != len(df)
    total = (pooled.wis.sum() / pooled.base_wis.sum()) if len(pooled) else None

    def score_td(v):
        return f'<td class="num {"ok" if v < 1 else "bad"}">{v:.3f}</td>'

    def label_of(l):
        return (usn.SHORT_LABELS[usn.FITTED] if usn.is_us(l) else str(l))

    rows = "".join(
        f"<tr><td>{label_of(l)}</td>{score_td(v)}"
        f'<td class="num hint">{int(cells.get(l, 0))}</td></tr>'
        for l, v in per_loc.items())
    # the total row names its scope when US is present
    total_label = ("All jurisdictions (US excluded)" if has_us
                   else "All locations")
    total_row = (
        f'<tr class="total"><td>{total_label}</td>{score_td(total)}'
        f'<td class="num hint">{len(pooled)}</td></tr>'
        if total is not None else "")
    note = (f'<p class="hint">{usn.POOLED_SCOPE_NOTE}</p>' if has_us else "")
    # disclose the cell rule where the counts render; the frame's own
    # truth_source stamp wins over the (racy) module global
    src = getattr(df, "attrs", {}).get("truth_source", TRUTH_SOURCE)
    rule = ('<p class="hint">' + CELL_RULE_NOTE
            + (f" Truth source: {src}."
               if src != "settled" else "") + '</p>')
    # the Oracle SIHRS member's US row never had the Oracle step
    us_note = (f'<p class="hint">{usn.PF_US_NOTE}</p>'
               if has_us and (model or "pf") == "pf" else "")
    return ('<table><thead><tr><th>Location</th>'
            f'<th class="num">{member} relWIS</th>'
            '<th class="num">Cells</th></tr></thead><tbody>'
            + rows + total_row + "</tbody></table>" + note + us_note + rule)
