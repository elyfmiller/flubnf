"""Vintage registry and data-freshness checks.

Constitutional rules enforced here (docs/APP_DESIGN.md):
  rule 5   a nonexistent vintage fails LOUDLY with nearby alternatives
  rule 9   real-time runs use vintage data only
  rule 10  missing weeks are MISSING (dropped as rows, calendar offsets kept)
           -- implemented downstream in flubnf.sihrs_fit.resolve_state; this
           module's job is to hand it the RIGHT vintage.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from flubnf.settings import ARCHIVE, HUB, LOCATIONS  # noqa: F401


def vintages() -> list:
    """Every archived truth vintage, sorted ascending."""
    return sorted(p.name.split("_")[-1].removesuffix(".csv")
                  for p in ARCHIVE.glob("target-hospital-admissions_*.csv"))


def vintage_path(date: str) -> Path:
    """Exact vintage or a LOUD error naming the alternatives -- the silent
    per-record 'no vintage' skip cost an overnight queue slot (2026-08-16)."""
    p = ARCHIVE / f"target-hospital-admissions_{date}.csv"
    if not p.is_file():
        vs = vintages()
        near = [v for v in vs
                if abs((pd.Timestamp(v) - pd.Timestamp(date)).days) <= 45]
        raise FileNotFoundError(
            f"No vintage for {date}. Nearby: {near or vs[-3:]}")
    return p


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
    if fetch:
        try:
            f = subprocess.run(["git", "fetch", "origin"], cwd=HUB,
                               capture_output=True, text=True, timeout=60)
            if f.returncode != 0:
                # A plain network failure exits nonzero WITHOUT raising.
                # Reading origin/main after a failed fetch compares against
                # the STALE local ref and reports "up to date" while a new
                # vintage sits upstream -- offline must never read as fresh.
                err = (f.stderr or "").strip().splitlines()
                detail = ("fetch failed: "
                          + (err[-1] if err else f"git exited {f.returncode}"))
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
        except Exception as e:                      # offline is a state, not a crash
            detail = f"fetch failed: {e}"
    is_fresh = (behind == 0) if behind is not None else False
    if remote_latest and local_latest and remote_latest > local_latest:
        detail = (f"new vintage {remote_latest} available upstream "
                  f"(local has {local_latest}) — pull to update")
    elif behind:
        detail = f"{behind} commit(s) behind origin (no new vintage yet)"
    elif behind == 0:
        detail = "up to date with origin"
    return Freshness(local_latest, remote_latest, behind, is_fresh, detail)


def pull_hub() -> str:
    """Explicit update of the hub checkout (the button's second step)."""
    # Self-heal sparse clones that predate the baseline requirement: the
    # validated relWIS baseline scores the CDC's own submitted files, so a
    # clone without model-output/FluSight-baseline cannot score anything.
    # FluSight-ensemble joined the set for the playback comparison feature
    # (same pattern: the hub's own submitted files, parsed per week).
    for sub in ("model-output/FluSight-baseline",
                "model-output/FluSight-ensemble"):
        try:
            if not (HUB / sub).is_dir():
                subprocess.run(["git", "-C", str(HUB), "sparse-checkout",
                                "add", sub],
                               capture_output=True, text=True, timeout=600)
        except Exception:
            pass
    r = subprocess.run(["git", "pull", "--ff-only", "origin", "main"],
                       cwd=HUB, capture_output=True, text=True, timeout=300)
    return r.stdout.strip() or r.stderr.strip()
