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

from flubnf import vintages as shipped_vintages
from flubnf.settings import ARCHIVE, HUB, LOCATIONS  # noqa: F401

#: the committed snapshots for the as-of weeks the hub archive skipped
#: (flubnf/vintages.py); a module-level name so tests can point it at an
#: empty folder, the way they repoint ARCHIVE
SHIPPED = shipped_vintages.VINTAGES_DIR


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


def archive_vintages() -> list:
    """The hub archive's truth vintages alone, sorted ascending."""
    return sorted(p.name.split("_")[-1].removesuffix(".csv")
                  for p in ARCHIVE.glob("target-hospital-admissions_*.csv"))


def shipped_weeks() -> list:
    """The as-of weeks the shipped snapshot folder (SHIPPED) can serve."""
    return shipped_vintages.weeks(SHIPPED)


def vintages() -> list:
    """Every truth vintage a run can read, sorted ascending: the hub archive
    and the shipped snapshots (flubnf/vintages.py), one entry per week."""
    return sorted(set(archive_vintages()) | set(shipped_weeks()))


def vintage_path(date: str) -> Path:
    """The file holding the truth as of `date`: the hub archive's vintage
    when it has one, else the shipped snapshot (sha256 verified against its
    manifest), else a LOUD error naming both folders and nearby weeks
    (never a silent skip)."""
    p = ARCHIVE / f"target-hospital-admissions_{date}.csv"
    if p.is_file():
        return p
    if str(date) in shipped_weeks():
        return shipped_vintages.shipped_path(date, SHIPPED)
    vs = vintages()
    near = [v for v in vs
            if abs((pd.Timestamp(v) - pd.Timestamp(date)).days) <= 45]
    raise FileNotFoundError(
        f"No vintage for {date} in the hub archive {ARCHIVE} or the shipped "
        f"snapshots {SHIPPED}. Nearby: {near or vs[-3:]}")


def vintage_source(date: str) -> dict:
    """Where a week's truth comes from, for provenance: {"kind": "archive"
    | "shipped" | "none", "path", "label", "commit"}. label reads 'hub
    archive' or 'hub snapshot, commit 1c8e1141 (2024-11-27)'."""
    p = ARCHIVE / f"target-hospital-admissions_{date}.csv"
    if p.is_file():
        return {"kind": "archive", "path": str(p), "label": "hub archive",
                "commit": ""}
    e = shipped_vintages.entry(date, SHIPPED)
    if e is not None and str(date) in shipped_weeks():
        return {"kind": "shipped", "path": str(SHIPPED / e["file"]),
                "label": shipped_vintages.provenance(date, SHIPPED),
                "commit": str(e.get("hub_commit") or "")}
    return {"kind": "none", "path": "", "label": "", "commit": ""}


def no_data_weeks() -> dict:
    """{as_of: manifest entry} for the weeks with no published data and no
    FluSight round (flubnf/vintages.py)."""
    return shipped_vintages.no_data_weeks(SHIPPED)


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


#: (forecast date, mode) -> (path, kind) a console run pinned for its whole
#: length (one run at a time holds the engine): every step of the run reads
#: the same bytes even if Update data rewrites the hub mid-run
_PINNED: dict = {}


def pin_source(spec, path, kind: str) -> None:
    _PINNED[(str(spec.forecast_date), spec_mode(spec))] = (Path(path), kind)


def unpin_source(spec) -> None:
    _PINNED.pop((str(spec.forecast_date), spec_mode(spec)), None)


def spec_source(spec, asof: Optional[str] = None, *, archive=None) -> tuple:
    """observed_source for a run spec (its forecast date by default); the
    run's pinned copy while one is pinned."""
    if asof is None or str(asof) == str(spec.forecast_date):
        hit = _PINNED.get((str(spec.forecast_date), spec_mode(spec)))
        if hit is not None:
            return hit
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
    """What a run records about its data: kind, path, sha256, newest week;
    for a shipped snapshot also the hub commit it was taken from."""
    rec = {"kind": kind, "path": str(path), "sha256": file_sha256(path),
           "newest_week": newest_row_week(path) or ""}
    commit = shipped_commit(path)
    if commit:
        rec["snapshot_commit"] = commit
    return rec


def shipped_commit(path) -> str:
    """The hub commit a shipped snapshot file was taken from, '' for any
    other file (the archive's, the live file, a dataset's)."""
    try:
        p = Path(path).resolve()
        if p.parent != Path(SHIPPED).resolve():
            return ""
    except OSError:
        return ""
    asof = p.name.removeprefix(shipped_vintages.FILE_PREFIX).removesuffix(".csv")
    e = shipped_vintages.entry(asof, SHIPPED)
    return str(e.get("hub_commit") or "") if e else ""


def source_phrase(rec) -> str:
    """One short phrase for a recorded source: 'live target-data through
    2026-10-03', 'archived vintage 2026-10-03' or 'shipped snapshot
    2024-11-23, hub commit 1c8e1141'; '' when not recorded."""
    if not isinstance(rec, dict) or not rec.get("kind"):
        return ""
    wk = str(rec.get("newest_week") or "")
    if rec["kind"] == "live":
        return f"live target-data through {wk}" if wk else "live target-data"
    commit = str(rec.get("snapshot_commit") or "")
    if commit:
        return (f"shipped snapshot {wk}, hub commit {commit}" if wk
                else f"shipped snapshot, hub commit {commit}")
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
                # the weeks a pull can bring: origin's archive plus the
                # shipped snapshots (already local; folded in so the two
                # lists compare like for like with vintages())
                remote = sorted(set(l.split("_")[-1].removesuffix(".csv")
                                    for l in ls.stdout.splitlines()
                                    if "target-hospital-admissions_" in l)
                                | set(shipped_weeks()))
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


def _hub_not_own_repo():
    """None when HUB is the top of its own git repository; otherwise why
    not, in plain words."""
    what = f"Not pulled: the hub folder {HUB} "
    try:
        r = subprocess.run(["git", "-C", str(HUB), "rev-parse",
                            "--show-toplevel"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return what + f"could not be checked with git ({type(e).__name__})."
    top = (r.stdout or "").strip()
    if r.returncode != 0 or not top:
        return what + "is not a git clone of the FluSight hub."
    try:
        same = Path(top).resolve() == Path(HUB).resolve()
    except OSError:
        same = False
    if not same:
        return (what + f"is inside another git repository ({top}), not a "
                "clone of its own, so pulling would update that one.")
    return None


def pull_hub() -> tuple:
    """Explicit update of the hub checkout (the button's second step).

    Returns (ok, message); ok is git's exit code, because the text alone
    cannot say (a fatal error and a fast-forward summary are both one line)."""
    # the hub folder must be the top of its own clone: a missing or plain
    # folder inside another repository (this app's, say) would otherwise
    # pull THAT repository
    refusal = _hub_not_own_repo()
    if refusal:
        return False, refusal
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
