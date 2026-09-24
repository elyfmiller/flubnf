"""SHIPPED (used by the FluBNF console, app/).

Vintage-true NREVSS typed-influenza (A vs B) data layer.

Source: Delphi Epidata's ``fluview_clinical`` endpoint,

    GET https://api.delphi.cmu.edu/epidata/fluview_clinical/
        ?regions=<r>&epiweeks=<a>-<b>[&issues=<i>]

Rows carry ``epiweek, issue, lag, total_specimens, total_a, total_b,
release_date``. Regions: lowercase state abbreviations ('pa'),
'hhs1'..'hhs10', or 'nat'. ``issues=<i>`` returns the data as published at
issue i; weeks a snapshot lacks are absent (never imputed), and every raw
response is cached on disk so replays never re-hit the network.

Issue ``<ew>`` is published the Friday after epiweek ``<ew>`` ends; for
data strictly before a midweek deadline pass an ``asof`` a week earlier.
This module fetches the asof epiweek's issue, falling back two issues for
holiday publishing gaps. HTTP via urllib, MMWR arithmetic inline.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

BASE_URL = "https://api.delphi.cmu.edu/epidata/fluview_clinical/"
HTTP_TIMEOUT = 20.0

#: Raw responses are cached here, one file per (region, issue).  Tests
#: monkeypatch this to a tmp dir; callers may also pass cache_dir=.
CACHE_DIR = Path(__file__).resolve().parents[1] / "app" / "state" / "nrevss"

#: Documented default for :func:`a0_share` when no week reaches the
#: specimen threshold: typical early-season influenza A dominance.
DEFAULT_A_SHARE = 0.85

#: Minimum typed specimens (A+B) for a week to anchor the a0 share.
MIN_TYPED = 20

#: HHS region membership by postal abbreviation: the fallback series when a
#: state withholds clinical data (no rows / all-zero specimens).
STATE_TO_HHS = {
    "ct": 1, "me": 1, "ma": 1, "nh": 1, "ri": 1, "vt": 1,
    "nj": 2, "ny": 2, "pr": 2, "vi": 2,
    "de": 3, "dc": 3, "md": 3, "pa": 3, "va": 3, "wv": 3,
    "al": 4, "fl": 4, "ga": 4, "ky": 4, "ms": 4, "nc": 4, "sc": 4, "tn": 4,
    "il": 5, "in": 5, "mi": 5, "mn": 5, "oh": 5, "wi": 5,
    "ar": 6, "la": 6, "nm": 6, "ok": 6, "tx": 6,
    "ia": 7, "ks": 7, "mo": 7, "ne": 7,
    "co": 8, "mt": 8, "nd": 8, "sd": 8, "ut": 8, "wy": 8,
    "az": 9, "ca": 9, "hi": 9, "nv": 9, "as": 9, "gu": 9, "mp": 9,
    "ak": 10, "id": 10, "or": 10, "wa": 10,
}


# ---------------------------------------------------------------------------
# MMWR week arithmetic
# ---------------------------------------------------------------------------
def _as_date(d) -> date:
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d)[:10])


def _week1_sunday(year: int) -> date:
    """The Sunday starting MMWR week 1 of `year` (the Sunday on or
    before January 4)."""
    jan4 = date(year, 1, 4)
    # date.weekday(): Monday=0..Sunday=6; days since the preceding Sunday:
    return jan4 - timedelta(days=(jan4.weekday() + 1) % 7)


def mmwr_week(d) -> tuple:
    """MMWR (epi) year and week of a date -> (year, week).

    MMWR weeks run Sunday-Saturday; week 1 is the Sunday-start week
    containing January 4. Equals isocalendar(d + 1 day)[:2] EXCEPT in years
    whose January 4 is a Sunday (2015, 2026, ...), where MMWR week = ISO
    week - 1 and ISO week 1 is the old year's week 53 (2014 and 2025 have
    53 MMWR weeks; Delphi has epiweek 202553).
    """
    d = _as_date(d)
    for year in (d.year + 1, d.year, d.year - 1):
        start = _week1_sunday(year)
        if d >= start:
            return year, (d - start).days // 7 + 1
    raise ValueError(f"no MMWR week for {d}")  # pragma: no cover


def week_ending(year: int, week: int) -> str:
    """ISO date of the Saturday ending MMWR week (year, week)."""
    return (_week1_sunday(year) + timedelta(days=(week - 1) * 7 + 6)).isoformat()


def _ew(d) -> int:
    """Date -> epiweek integer YYYYWW."""
    y, w = mmwr_week(d)
    return y * 100 + w


def _ew_shift(ew: int, weeks: int) -> int:
    """Shift an epiweek integer by a number of weeks (negative = earlier)."""
    y, w = divmod(ew, 100)
    return _ew(_as_date(week_ending(y, w)) + timedelta(weeks=weeks))


# ---------------------------------------------------------------------------
# HTTP + per-(region, issue) disk cache
# ---------------------------------------------------------------------------
def build_url(region: str, ew_start: int, ew_end: int, issue: int) -> str:
    """The exact vintage query URL (pure; unit-tested)."""
    params = {
        "regions": region,
        "epiweeks": f"{ew_start}-{ew_end}",
        "issues": str(issue),
    }
    return BASE_URL + "?" + urllib.parse.urlencode(params)


def _http_json(url: str, timeout: float = HTTP_TIMEOUT) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "flubnf-nrevss"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(
            f"NREVSS fetch failed (network error contacting Delphi Epidata): "
            f"{url}: {e}"
        ) from e


def _snapshot(region: str, issue: int, ew_start: int, ew_end: int,
              cache_dir=None) -> list:
    """Rows of the (region, issue) snapshot covering [ew_start, ew_end].

    The raw response (empty ones included) is cached at
    ``<cache_dir>/<region>_<issue>.json`` BEFORE any fallback, so a replay
    is served from disk. The file records its epiweek range; a request
    outside it misses and refetches, storing the new request's range.
    """
    cache_dir = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    path = cache_dir / f"{region}_{issue}.json"
    if path.exists():
        blob = json.loads(path.read_text())
        a, b = blob.get("epiweeks", (0, -1))
        if a <= ew_start and ew_end <= b:
            env = blob["response"]
            rows = env.get("epidata") or []
            return [r for r in rows if ew_start <= r["epiweek"] <= ew_end]
    env = _http_json(build_url(region, ew_start, ew_end, issue))
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({
        "region": region,
        "issue": issue,
        "epiweeks": [ew_start, ew_end],
        "response": env,
    }, indent=1))
    tmp.replace(path)
    return env.get("epidata") or []


# ---------------------------------------------------------------------------
# Public data API
# ---------------------------------------------------------------------------
_COLUMNS = ["date", "total_a", "total_b", "total_specimens"]


def fetch_typed(region: str, season_start_iso, asof_iso,
                cache_dir=None) -> pd.DataFrame:
    """Typed-influenza counts for `region`, AS KNOWN at `asof_iso`.

    Requests ``epiweeks=<season_start_ew>-<asof_ew>`` at
    ``issues=<asof_ew>``, falling back to the two preceding issues if empty
    (holiday gaps). Returns [date, total_a, total_b, total_specimens], date
    the epiweek's Saturday, sorted; missing weeks are absent, never imputed.
    ``total_specimens`` is for withheld-state detection.
    """
    ew_start = _ew(season_start_iso)
    ew_end = _ew(asof_iso)
    rows: list = []
    for back in range(3):
        issue = _ew_shift(ew_end, -back)
        # an issue holds no later epiweeks (lag >= 0); clamping also lets a
        # replay hit the cached primary-issue file
        rows = _snapshot(region, issue, ew_start, min(ew_end, issue),
                         cache_dir=cache_dir)
        if rows:
            break
    if not rows:
        return pd.DataFrame(columns=_COLUMNS)
    # One row per epiweek at a fixed issue; dedupe defensively on the
    # latest issue should the API ever return several.
    best: dict = {}
    for r in rows:
        k = r["epiweek"]
        if k not in best or r.get("issue", 0) > best[k].get("issue", 0):
            best[k] = r
    recs = [
        {
            "date": week_ending(*divmod(k, 100)),
            "total_a": int(r["total_a"] or 0),
            "total_b": int(r["total_b"] or 0),
            "total_specimens": int(r["total_specimens"] or 0),
        }
        for k, r in sorted(best.items())
    ]
    return pd.DataFrame(recs, columns=_COLUMNS)


def _locations(locations_csv=None) -> pd.DataFrame:
    if locations_csv is None:
        from . import settings
        locations_csv = settings.LOCATIONS
        if not Path(locations_csv).exists():  # hub clone absent: packaged copy
            locations_csv = Path(__file__).parent / "data" / "locations.csv"
    return pd.read_csv(locations_csv, dtype=str)


def _abbr_for(state_name: str, locations_csv=None) -> str:
    loc = _locations(locations_csv)
    m = loc[loc["location_name"].str.strip().str.lower()
            == state_name.strip().lower()]
    if m.empty:
        raise KeyError(f"unknown location name: {state_name!r}")
    return m.iloc[0]["abbreviation"].strip().lower()


def a_share_series(state_name: str, season_start, asof,
                   locations_csv=None, cache_dir=None) -> pd.DataFrame:
    """As-of typed series for a full state name, with HHS fallback.

    Full name -> abbreviation via the locations csv ('US' -> 'nat'). No
    rows or all-zero specimens (withheld data) falls back to the HHS
    region; the region used is in the 'source' column and
    ``df.attrs['source']`` (e.g. 'pa', 'hhs3').
    """
    abbr = _abbr_for(state_name, locations_csv)
    region = "nat" if abbr == "us" else abbr
    df = fetch_typed(region, season_start, asof, cache_dir=cache_dir)
    source = region
    if (df.empty or int(df["total_specimens"].sum()) == 0) \
            and abbr in STATE_TO_HHS:
        source = f"hhs{STATE_TO_HHS[abbr]}"
        df = fetch_typed(source, season_start, asof, cache_dir=cache_dir)
    df = df.copy()
    df["source"] = source
    df.attrs["source"] = source
    return df


def a0_share(state_name: str, season_start, asof,
             locations_csv=None, cache_dir=None) -> float:
    """A/(A+B) of the FIRST as-of week with >= MIN_TYPED typed specimens.

    DEFAULT_A_SHARE (0.85) when no week qualifies or on ANY failure: never
    raises. Clipped to [0.01, 0.99] so a one-typed week is not degenerate.
    """
    try:
        df = a_share_series(state_name, season_start, asof,
                            locations_csv=locations_csv, cache_dir=cache_dir)
        typed = df["total_a"] + df["total_b"]
        ok = df[typed >= MIN_TYPED]
        if ok.empty:
            return DEFAULT_A_SHARE
        r = ok.iloc[0]
        share = float(r["total_a"]) / float(r["total_a"] + r["total_b"])
        return min(max(share, 0.01), 0.99)
    except Exception:
        return DEFAULT_A_SHARE
