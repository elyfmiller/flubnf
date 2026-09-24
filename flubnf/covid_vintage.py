"""RESEARCH (COVID profile seam, reached only via app/core/engines/profiles.py):
vintage-true COVID-19 truth from the CovidHub's versioned
`target-data/time-series.parquet`, sliced by its `as_of` column (one snapshot
per week; each vintage's data edge is the Saturday before its as-of date).

HARD LIMIT: the record begins 2024-11-20; nothing earlier can be made
vintage-true from any source, so a COVID retrospective has ~1.5 seasons, not
the flu seal's standing. `assert_vintage_true` fails loudly before it.

CONTRACT: `vintage_path(as_of)` returns a CSV with the FluSight archive's
columns (date, location, location_name, value), so resolve_state, natgrowth
and the analogue bank builder read it unchanged; the bytes are stable per
as-of. A missing vintage raises FileNotFoundError naming nearby alternatives
(rule 5; never a silent skip).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .settings import load_locations

COVID_TARGET = "wk inc covid hosp"
COVID_ED_TARGET = "wk inc covid prop ed visits"
#: Earliest COVID vintage anywhere (parquet, hub git history and Delphi agree).
VINTAGE_HORIZON = "2024-11-20"

# ---------------------------------------------------------------------------
# WHAT THE HORIZON COSTS THE ANALOGUE MEMBER, MEASURED
# ---------------------------------------------------------------------------
# With donors only from vintage-true prior seasons (from 2024-11-09), target
# season 2025-26 has no calendar-matched donor at epiweeks 25-38 (14 of 45
# as-of weeks), bracketing the larger summer wave. A ONE-TIME cost: season
# 2026 has donors at every epiweek. Say which situation a result comes from.
# (Pinned by tests/test_covid_vintage.py.)
ANALOGUE_SILENT_EPIWEEKS_2025_26 = tuple(range(25, 39))
ANALOGUE_SILENT_WEEKS_2025_26 = 14
ANALOGUE_ASOF_WEEKS_2025_26 = 45

_REPO = Path(__file__).resolve().parents[1]


def _resolve_timeseries() -> Path:
    """Where the hubverse time series lives on this machine.

    FLUBNF_COVID_TIMESERIES wins outright; then a clone named by
    FLUBNF_COVID_HUB; then the conventional clone location; then the copy
    staged under the repo's own data/ directory, which is what a machine
    without a CovidHub clone uses.
    """
    v = os.environ.get("FLUBNF_COVID_TIMESERIES")
    if v:
        return Path(v).expanduser()
    hub = os.environ.get("FLUBNF_COVID_HUB")
    cands = []
    if hub:
        cands.append(Path(hub).expanduser() / "target-data/time-series.parquet")
    cands += [Path("~/Documents/GitHub/covid19-forecast-hub").expanduser()
              / "target-data/time-series.parquet",
              _REPO / "data/covidhub/target-data/time-series.parquet"]
    for c in cands:
        if c.is_file():
            return c
    return cands[-1]


TIMESERIES = _resolve_timeseries()
#: Where materialized per-vintage CSVs are cached.
CACHE = Path(os.environ.get("FLUBNF_COVID_VINTAGE_CACHE",
                            str(_REPO / "data/covidhub/vintage-cache")))


class ParquetEngineMissing(RuntimeError):
    """No parquet reader is installed. Loud, with the fix, rather than a
    cryptic pandas ImportError three frames down."""


@lru_cache(maxsize=2)
def _load(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(
            f"CovidHub time series not found at {p}. Clone "
            "github.com/CDCgov/covid19-forecast-hub and set FLUBNF_COVID_HUB, "
            "or point FLUBNF_COVID_TIMESERIES at target-data/time-series.parquet.")
    try:
        df = pd.read_parquet(p)
    except ImportError as e:                      # pragma: no cover - env-specific
        raise ParquetEngineMissing(
            "reading the CovidHub time series needs a parquet engine; "
            "`pip install pyarrow` into the analysis venv") from e
    df["as_of"] = pd.to_datetime(df["as_of"]).dt.strftime("%Y-%m-%d")
    df["target_end_date"] = pd.to_datetime(df["target_end_date"]).dt.strftime("%Y-%m-%d")
    df["location"] = df["location"].astype(str).str.zfill(2).where(
        df["location"].astype(str) != "US", "US")
    return df


def _frame(target: str = COVID_TARGET) -> pd.DataFrame:
    df = _load(str(TIMESERIES))
    out = df[df["target"] == target]
    if out.empty:
        raise KeyError(f"no rows for target {target!r} in {TIMESERIES}; "
                       f"have {sorted(df['target'].unique())}")
    return out


@lru_cache(maxsize=4)
def _location_names() -> dict:
    """FIPS -> location_name, from the locations table the rest of the stack
    already trusts. The CovidHub's own locations.csv carries the same 53 rows
    and the same four columns, so either source gives the same answer."""
    locs = load_locations(dtype={"location": str})
    locs["location"] = locs["location"].astype(str).str.zfill(2).where(
        locs["abbreviation"] != "US", "US")
    return dict(zip(locs["location"], locs["location_name"]))


def vintages(target: str = COVID_TARGET) -> list:
    """Every as-of snapshot in the archive, ascending."""
    return sorted(_frame(target)["as_of"].unique().tolist())


def assert_vintage_true(as_of: str) -> None:
    """Refuse to pretend a pre-horizon date is vintage-true."""
    if str(as_of) < VINTAGE_HORIZON:
        raise ValueError(
            f"as_of {as_of} predates the COVID vintage horizon {VINTAGE_HORIZON}. "
            "No vintage exists before that date in the hub parquet, the hub git "
            "history, or Delphi Epidata. Scoring here would use settled truth "
            "while claiming to be vintage-true.")


def vintage_frame(as_of: str, target: str = COVID_TARGET) -> pd.DataFrame:
    """One vintage in the FluSight archive's own shape.

    Columns: date, location, location_name, value -- exactly what
    `app/core/data.py::load_vintage` returns, so downstream code is unchanged.
    Rows with a missing observation are DROPPED, never imputed (rule 10).
    """
    assert_vintage_true(as_of)
    df = _frame(target)
    g = df[df["as_of"] == str(as_of)]
    if g.empty:
        vs = vintages(target)
        near = [v for v in vs
                if abs((pd.Timestamp(v) - pd.Timestamp(as_of)).days) <= 45]
        raise FileNotFoundError(
            f"No COVID vintage for {as_of}. Nearby: {near or vs[-3:]}")
    names = _location_names()
    out = pd.DataFrame({
        "date": g["target_end_date"].to_numpy(),
        "location": g["location"].to_numpy(),
        "value": pd.to_numeric(g["observation"], errors="coerce").to_numpy(),
    })
    out["location_name"] = [names.get(l, l) for l in out["location"]]
    out = out[["date", "location", "location_name", "value"]]
    out = out[out["value"].notna()]
    return out.sort_values(["date", "location"]).reset_index(drop=True)


def data_edge(as_of: str, target: str = COVID_TARGET) -> str:
    """Newest week this vintage knows about."""
    return str(vintage_frame(as_of, target)["date"].max())


def vintage_summary(as_of: str, target: str = COVID_TARGET) -> dict:
    """What one vintage knew, in one glance -- same keys as the flu version."""
    df = vintage_frame(as_of, target)
    return {"date": str(as_of),
            "rows": int(len(df)),
            "locations": int(df["location"].nunique()),
            "newest_week": str(df["date"].max()) if len(df) else "",
            "oldest_week": str(df["date"].min()) if len(df) else ""}


def vintage_path(as_of: str, target: str = COVID_TARGET,
                 cache_dir: Path | None = None) -> Path:
    """Materialize one vintage as a CSV and return its path.

    The FluSight archive naming convention is reused deliberately: every
    existing consumer takes a `truth_csv` path, so a COVID fit becomes a
    one-argument change rather than a new code path. Raises the same LOUD
    error as `vintage_frame` for a date never archived.
    """
    d = Path(cache_dir) if cache_dir is not None else CACHE
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"target-hospital-admissions_{as_of}.csv"
    if p.is_file():
        return p
    df = vintage_frame(as_of, target)
    tmp = p.with_suffix(".csv.part")
    df.to_csv(tmp, index=False)
    tmp.replace(p)                       # atomic: a killed run leaves no half file
    return p


def build_bank_rows(as_of: str, target: str = COVID_TARGET):
    """Rows shaped for `flubnf.analogue.build_bank` -- (.location, .date, .value)
    with `date` a datetime.date, which is what the donor bank keys on."""
    df = vintage_frame(as_of, target).copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df[["location", "date", "value"]].itertuples(index=False)
