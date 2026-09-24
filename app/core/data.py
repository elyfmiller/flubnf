"""PRODUCTION: vintage registry and hub freshness (server Data tab, retro,
scoring, engines).

Vintage registry and data-freshness checks.

Constitutional rules enforced here (the lab archive's docs/APP_DESIGN.md):
  rule 5   a nonexistent vintage fails LOUDLY with nearby alternatives
  rule 9   runs read data as it stood on the as-of date: the dated vintage,
           or for a real-time run the live target file when its newest
           week IS the as-of (observed_source)
  rule 10  missing weeks are MISSING (dropped as rows, calendar offsets kept)
           -- implemented downstream in flubnf.sihrs_fit.resolve_state; this
           module's job is to hand it the RIGHT vintage.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from flubnf.settings import ARCHIVE, HUB, LOCATIONS  # noqa: F401


def truth_mtime() -> float:
    """mtime of the hub's current target file, the settled truth every
    retrospective score, playback payload and season report is computed
    against; 0 when absent. Folded into those caches' keys so newer truth
    invalidates them."""
    p = HUB / "target-data" / "target-hospital-admissions.csv"
    try:
        return p.stat().st_mtime if p.is_file() else 0.0
    except OSError:
        return 0.0


def vintages() -> list:
    """Every archived truth vintage, sorted ascending."""
    return sorted(p.name.split("_")[-1].removesuffix(".csv")
                  for p in ARCHIVE.glob("target-hospital-admissions_*.csv"))


def vintage_path(date: str) -> Path:
    """Exact vintage or a LOUD error naming nearby ones (never a silent skip)."""
    p = ARCHIVE / f"target-hospital-admissions_{date}.csv"
    if not p.is_file():
        vs = vintages()
        near = [v for v in vs
                if abs((pd.Timestamp(v) - pd.Timestamp(date)).days) <= 45]
        raise FileNotFoundError(
            f"No vintage for {date}. Nearby: {near or vs[-3:]}")
    return p


#: the hub's live target file, relative to the clone: `git pull` rewrites it
#: every week, the dated archive copy (vintage_path) is added by hand later
LIVE_TARGET = "target-data/target-hospital-admissions.csv"

_live_cache: dict = {}


def live_path() -> Path:
    """The hub clone's live target file (it may be absent)."""
    return HUB / LIVE_TARGET


def newest_row_week(path) -> Optional[str]:
    """The newest `date` in one target CSV (YYYY-MM-DD), None when the file
    is absent or unreadable. Cached on (path, mtime, size): a pull that
    rewrites the file is seen at once."""
    p = Path(path)
    try:
        st = p.stat()
    except OSError:
        return None
    key = (str(p), st.st_mtime_ns, st.st_size)
    if key in _live_cache:
        return _live_cache[key]
    try:
        d = pd.read_csv(p, usecols=["date"], dtype=str)["date"]
        newest = str(d.dropna().str[:10].max()) if len(d) else None
    except Exception:
        newest = None
    _live_cache.clear()                  # one file matters; keep one entry
    _live_cache[key] = newest
    return newest


def live_newest_week() -> Optional[str]:
    """The newest week the live target file holds (None without one)."""
    return newest_row_week(live_path())


def newest_week() -> Optional[str]:
    """The newest week any hub data holds: the live target file's newest
    week or the newest archived vintage, whichever is later. This is the
    week a real-time run forecasts from."""
    vs = vintages()
    cands = [w for w in (live_newest_week(), vs[-1] if vs else None) if w]
    return max(cands) if cands else None


def newest_path() -> Path:
    """The file holding the newest data (for display: the data panels):
    the live target file when it is at least as new as the archive, else
    the newest vintage. Raises like vintage_path when there is neither."""
    vs = vintages()
    lw = live_newest_week()
    if lw and (not vs or lw >= vs[-1]):
        return live_path()
    if not vs:
        raise FileNotFoundError("No hub data: Update data on the Data tab.")
    return vintage_path(vs[-1])


def available_weeks() -> list:
    """Every week a run can anchor on, ascending: the archived vintages,
    plus the live file's newest week when the archive does not hold it yet
    (the hub archives by hand, days or weeks late)."""
    vs = vintages()
    lw = live_newest_week()
    return sorted(set(vs) | {lw}) if lw else vs


class DataSourceError(FileNotFoundError):
    """No file can honestly serve an as-of date (a FileNotFoundError, so
    every caller that already catches a missing vintage catches this)."""


def observed_source(asof: str, mode: str = "realtime", *,
                    archive=None) -> tuple:
    """(path, kind) of the observed admissions a run as of `asof` reads;
    kind is "live" or "vintage". The one resolver every hub consumer uses.

    mode "vintage" (retrospective replays, backdated runs): the dated
    archive only. The live file holds today's REVISED values, which would
    leak hindsight into a past as-of.

    mode "realtime": the live target file when its newest week IS the
    as-of (checked against the hub on 2026-09-23: the live file and the
    2026-07-04 vintage hold the same rows and values, so preferring it is
    safe and does not depend on the archive keeping up). When the live file
    is newer than the as-of the run is not real-time and reads the archive;
    when it is older, the as-of has no data yet and the run is refused.

    `archive` is the dated lookup (default vintage_path, read at call time;
    modules pass their own imported name so a test that fakes it still
    reaches here)."""
    lookup = archive if archive is not None else vintage_path
    if mode == "realtime":
        lw = live_newest_week()
        if lw is not None and lw == asof:
            return live_path(), "live"
        try:
            return Path(lookup(asof)), "vintage"
        except FileNotFoundError as e:
            if lw is not None and lw < asof:
                raise DataSourceError(
                    f"No data for {asof} yet: the hub's target data ends at "
                    f"{lw}. Update data on the Data tab, or forecast from "
                    f"{lw}.") from e
            raise
    return Path(lookup(asof)), "vintage"


def spec_mode(spec) -> str:
    """"vintage" or "realtime" for a run spec: retrospective replays
    (engine "retro") and backdated runs (extra mode "vintage") read the
    archive only; anything else may read the live file for its own week."""
    if str(getattr(spec, "engine", "") or "") == "retro":
        return "vintage"
    extra = getattr(spec, "extra", None) or {}
    return "vintage" if str(extra.get("mode") or "") == "vintage" else "realtime"


def spec_source(spec, asof: Optional[str] = None, *, archive=None) -> tuple:
    """observed_source for a run spec (its forecast date by default)."""
    return observed_source(asof or spec.forecast_date, spec_mode(spec),
                           archive=archive)


def file_sha256(path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def source_record(path, kind: str) -> dict:
    """What a run records about its data: kind, path, sha256, newest week."""
    return {"kind": kind, "path": str(path), "sha256": file_sha256(path),
            "newest_week": newest_row_week(path) or ""}


def source_phrase(rec) -> str:
    """One short phrase for a recorded source: 'live target-data through
    2026-10-03' or 'archived vintage 2026-10-03'; '' when not recorded."""
    if not isinstance(rec, dict) or not rec.get("kind"):
        return ""
    wk = str(rec.get("newest_week") or "")
    if rec["kind"] == "live":
        return f"live target-data through {wk}" if wk else "live target-data"
    return f"archived vintage {wk}" if wk else "archived vintage"


def load_vintage(date: str):
    """One archived vintage as a frame: location zero-filled, value numeric,
    unreported rows dropped (the missingness policy: dropped, never imputed).
    Raises the same LOUD error as vintage_path for a date never archived."""
    df = pd.read_csv(vintage_path(date), dtype={"location": str})
    df["location"] = df["location"].str.zfill(2)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df[df["value"].notna()]


def vintage_summary(date: str) -> dict:
    """What one vintage knew, in one glance: reported rows, jurisdictions
    covered, and the week span. Every count comes from the reported rows
    (value present), the rows every downstream consumer actually uses."""
    df = load_vintage(date)
    return {"date": date,
            "rows": int(len(df)),
            "locations": int(df["location"].nunique()),
            "newest_week": str(df["date"].max())[:10] if len(df) else "",
            "oldest_week": str(df["date"].min())[:10] if len(df) else ""}


def vintage_location_names(date: str) -> list:
    """Location names present in one vintage, US first then alphabetical --
    the order every location selector in the application uses."""
    names = sorted(set(load_vintage(date)["location_name"].astype(str)))
    return ([n for n in names if n.upper() == "US"]
            + [n for n in names if n.upper() != "US"])


def vintage_series(date: str, location_name: str) -> dict:
    """The admissions series one vintage holds for one location, oldest
    first: {'dates': [...], 'values': [...]}. Unknown locations return empty
    lists rather than raising; the caller renders the honest empty state."""
    df = load_vintage(date)
    g = df[df["location_name"].astype(str) == str(location_name)]
    g = g.sort_values("date")
    return {"dates": [str(d)[:10] for d in g["date"]],
            "values": [float(v) for v in g["value"]]}


@dataclass
class Freshness:
    local_latest: Optional[str]
    remote_latest: Optional[str]
    behind: Optional[int]            # commits behind origin, None if unknown
    is_fresh: bool
    detail: str


def check_freshness(fetch: bool = True) -> Freshness:
    """The landing page's 'check for new data' button.

    Compares the local hub checkout against its origin: fetches (read-only),
    counts commits behind, and reports the newest local vintage. Never pulls
    -- updating the checkout is an explicit user action, not a side effect of
    looking.
    """
    local = vintages()
    local_latest = local[-1] if local else None
    behind, remote_latest, detail = None, None, ""
    local_live, remote_live = live_newest_week(), None
    if fetch:
        try:
            f = subprocess.run(["git", "fetch", "origin"], cwd=HUB,
                               capture_output=True, text=True, timeout=60)
            if f.returncode != 0:
                # a network failure exits nonzero without raising; reading the
                # stale origin/main would then say "up to date". Offline is never fresh.
                err = (f.stderr or "").strip().splitlines()
                # prefer git's fatal line: the last line can be a fragment
                fatal = next((l for l in err if l.startswith("fatal:")),
                             err[-1] if err else f"git exited {f.returncode}")
                detail = f"fetch failed: {fatal}"
            else:
                r = subprocess.run(
                    ["git", "rev-list", "--count", "HEAD..origin/main"],
                    cwd=HUB, capture_output=True, text=True, timeout=15)
                behind = int(r.stdout.strip()) if r.returncode == 0 else None
                ls = subprocess.run(
                    ["git", "ls-tree", "-r", "--name-only", "origin/main",
                     "auxiliary-data/target-data-archive/"],
                    cwd=HUB, capture_output=True, text=True, timeout=15)
                remote = sorted(l.split("_")[-1].removesuffix(".csv")
                                for l in ls.stdout.splitlines()
                                if "target-hospital-admissions_" in l)
                remote_latest = remote[-1] if remote else None
                # the live target file moves every week, the archive by
                # hand: its newest week is the data a real-time run gets
                sh = subprocess.run(
                    ["git", "show", f"origin/main:{LIVE_TARGET}"],
                    cwd=HUB, capture_output=True, text=True, timeout=30)
                if sh.returncode == 0:
                    wk = re.findall(r"^\"?(\d{4}-\d{2}-\d{2})", sh.stdout,
                                    flags=re.M)
                    remote_live = max(wk) if wk else None
        except Exception as e:                      # offline is a state, not a crash
            detail = f"fetch failed: {e}"
    is_fresh = (behind == 0) if behind is not None else False
    if remote_live and (not local_live or remote_live > local_live):
        detail = (f"new data through {remote_live} available upstream "
                  f"(local has {local_live or 'none'}): Update data to get it")
    elif remote_latest and local_latest and remote_latest > local_latest:
        detail = (f"new vintage {remote_latest} available upstream "
                  f"(local has {local_latest}): Update data to get it")
    elif behind:
        detail = f"{behind} commit(s) behind origin (no new vintage yet)"
    elif behind == 0:
        detail = "up to date with origin"
    return Freshness(local_latest, remote_latest, behind, is_fresh, detail)


def pull_hub() -> tuple:
    """Explicit update of the hub checkout (the button's second step).

    Returns (ok, message); ok is git's exit code, because the text alone
    cannot say (a fatal error and a fast-forward summary are both one line)."""
    # self-heal older sparse clones: relWIS needs FluSight-baseline's
    # submitted files, and the player's comparison needs FluSight-ensemble's
    for sub in ("model-output/FluSight-baseline",
                "model-output/FluSight-ensemble"):
        try:
            if not (HUB / sub).is_dir():
                subprocess.run(["git", "-C", str(HUB), "sparse-checkout",
                                "add", sub],
                               capture_output=True, text=True, timeout=600)
        except Exception:
            pass
    try:
        r = subprocess.run(["git", "pull", "--ff-only", "origin", "main"],
                           cwd=HUB, capture_output=True, text=True,
                           timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        # no clone, no git, or a hung network: a failure, said as one
        return False, f"{type(e).__name__}: {e}"
    return r.returncode == 0, (r.stdout.strip() or r.stderr.strip())
