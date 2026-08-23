"""Vintage-true truth for COVID-19, from the CovidHub's versioned time series.

WHAT THIS REPLACES
------------------
FluSight ships one dated CSV per week in `auxiliary-data/target-data-archive/`,
and `app/core/data.py::vintage_path` reads that naming convention. The CovidHub
ships no such directory. It ships something better: a single hubverse
`target-data/time-series.parquet` carrying an `as_of` column with one snapshot
per week. Slicing by `as_of` yields exactly the frame the FluSight archive files
carry, so the model-facing contract is unchanged and no git archaeology is
needed.

Verified against the file itself (as_of 2026-08-19 snapshot, 702,878 rows):
84 distinct `as_of` vintages for `wk inc covid hosp`, 2024-11-20 through
2026-08-19, 53 locations, observations 2024-11-09 through 2026-08-15. Each
vintage's data edge is the Saturday before its as-of date, which is what a
Wednesday forecaster would have seen.

THE HARD LIMIT, STATED WHERE IT CANNOT BE MISSED
------------------------------------------------
The record begins 2024-11-20. Nothing earlier can be made vintage-true for
COVID from any source. That is 1.5 to 1.75 usable seasons against FluSight's
three, and a COVID retrospective does NOT have the flu seal's standing.
`assert_vintage_true` exists so a caller that wanders before the horizon fails
loudly instead of silently scoring settled truth as if it were vintage.

THE CONTRACT
------------
`vintage_path(as_of)` returns a filesystem path to a CSV with the FluSight
archive's own columns (date, location, location_name, value) so every existing
consumer -- `sihrs_fit.resolve_state`, `natgrowth`, the analogue bank builder --
reads it unchanged. Materialized CSVs are cached and content-stable: the same
as-of always yields the same bytes.

Rule 5 is honoured verbatim: a nonexistent vintage raises FileNotFoundError
naming the nearby alternatives. The silent per-record "no vintage" skip cost an
overnight queue slot on 2026-08-16 and must not be reintroduced here.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .settings import LOCATIONS, load_locations

COVID_TARGET = "wk inc covid hosp"
COVID_ED_TARGET = "wk inc covid prop ed visits"
#: Earliest as-of for which a COVID vintage exists anywhere. Three independent
#: sources agree: the parquet (2024-11-20), the hub's git history (2024-11-18),
#: and Delphi Epidata's earliest issue (epiweek 202447).
VINTAGE_HORIZON = "2024-11-20"

# ---------------------------------------------------------------------------
# WHAT THE HORIZON COSTS THE ANALOGUE MEMBER, MEASURED
# ---------------------------------------------------------------------------
# The analogue draws donors from STRICTLY PRIOR seasons at the matching epiweek.
# Under the June boundary, target season 2025 (2025-06-01 to 2026-05-31) may only
# use season 2024 or earlier, and vintage-true that means weeks from 2024-11-09
# onward. Epiweeks roughly 23 to 44 therefore have NO prior-season donor at all.
#
# Measured by research/covid-phase0/analogue_vintage_true.py on the 2025-26
# season: 14 of 45 as-of weeks return zero calendar-matched donors, a contiguous
# block at epiweeks 25 to 38, i.e. 2025-06-25 through 2025-09-24. That block
# BRACKETS the 2025 summer wave, whose national peak of 11,010 admissions
# (week ending 2025-09-06) was the LARGER of that year's two waves.
#
# THIS IS A ONE-TIME COST, NOT A PERMANENT PROPERTY. It is the first target
# season paying for the archive's start date. Once season 2025 is complete it
# becomes a donor season covering the whole calendar, so target season 2026 has
# donors at every epiweek. Say which of the two situations a result comes from.
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
