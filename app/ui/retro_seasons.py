"""The retrospective season registry, its live progress and the ETA.

The retro roots (RETRO_ROOT, this app's own replays, and the read-only
sealed records RETRO_RESEAL and RETRO_SEAL) and the in-memory season claims
(_retro_status, _retro_stop, _retro_claim_at) live here. The registry and
progress functions read them bare, at call time, because tests repoint the
roots. Every other module reads the roots, _known_seasons, _season_root,
_weeks_done, _retro_progress and _archive_entries as retro_seasons.X, so a
patch of the name here reaches them. The replay itself is app/core/retro.py.
"""
from __future__ import annotations

import time
from pathlib import Path

from app.core import ttlcache
from app.ui.templating import _pf_name


# === Cached scan: completed retro weeks (the other scans: shared.py) ===
@ttlcache.ttl_cache()
def _weeks_done(root: Path) -> int:
    """Completed weeks in a season tree (stored samples.json count): the
    retro pages' hot scan."""
    from app.core import retro
    root = Path(root)
    try:
        return len(retro.season_sample_files(root))
    except OSError:
        return 0


# === Retrospective core: roots, claims, season status ===
RETRO_ROOT = Path(__file__).resolve().parents[1] / "state" / "retro"
# The sealed full-grid records, read only: the reseal (production engine,
# the Home/Methods figures) first, then v1.0.0's seal (history).
RETRO_RESEAL = Path(__file__).resolve().parents[1] / "state" / "retro_reseal"
RETRO_SEAL = Path(__file__).resolve().parents[1] / "state" / "retro_seal"


def _sealed_roots() -> tuple:
    """((root, label), ...) in preference order, read at call time (tests
    repoint the roots)."""
    return ((RETRO_RESEAL, "the production engine's record (reseal of "
                           "2026-09-07), the figures on Home and Methods"),
            (RETRO_SEAL, "sealed v1.0.0 engine record (retired raw-space "
                         "kernel); the production engine scores 0.723 "
                         "pooled, see Methods"))


def _sealed_label(root: Path) -> str:
    """The label of the sealed record `root` lies in, or an empty string."""
    for base, label in _sealed_roots():
        try:
            if Path(root).resolve().is_relative_to(Path(base).resolve()):
                return label
        except OSError:
            continue
    return ""


def _is_sealed_root(root: Path) -> bool:
    """Whether root lies under a sealed record: read only, never stale and
    never rescored, even when the hub's truth moves on."""
    try:
        parents = Path(root).resolve().parents
        return any(Path(base).resolve() in parents
                   for base, _ in _sealed_roots())
    except OSError:
        return False


def _season_root(season: str, archive: str = "") -> tuple:
    """(root, is_seal): whichever of the app's retro root and the sealed
    records has the most completed weeks (ties: app, reseal, seal). With an
    archive id, exactly that archived tree."""
    if archive:
        from app.core import retro
        return retro.archive_dir(RETRO_ROOT, season, archive), False
    best, is_seal = RETRO_ROOT / season, False
    n = _weeks_done(best)
    for base, _label in _sealed_roots():
        m = _weeks_done(base / season)
        if m > n:
            best, is_seal, n = base / season, True, m
    return best, is_seal
_retro_status: dict = {}
_retro_stop: set = set()
_retro_claim_at: dict = {}   # season -> when its in-memory claim was made

#: statuses that mean a season worker is alive and holding the engine
_RETRO_ACTIVE = ("running", "stopping", "paused")


def _valid_season(season: str) -> bool:
    """YYYY-YY only (season names become directory names)."""
    import re
    return bool(re.fullmatch(r"\d{4}-\d{2}", season or ""))


def _valid_archive(stamp: str) -> bool:
    """Archive stamp format only (it becomes a directory name)."""
    from app.core import retro
    return retro.valid_stamp(stamp or "")


def _live_root(season: str) -> Path:
    """Where this app's season worker runs (control flags, run record): the
    only tree a Run can resume, archive or discard. Sealed trees are never
    written."""
    return RETRO_ROOT / season


@ttlcache.ttl_cache()
def _seasons_on_disk(retro_root: Path) -> tuple:
    """Seasons under a retro root carrying a run record (cached per root)."""
    from app.core import retro
    names = set()
    try:
        for p in Path(retro_root).iterdir():
            if (_valid_season(p.name) and p.is_dir()
                    and retro.meta_path(p).is_file()):
                names.add(p.name)
    except OSError:
        pass                          # no retro root yet
    return tuple(sorted(names))


def _known_seasons() -> list:
    """In-memory claims (read live, never cached) plus every season with a
    run record on disk (records outlive claims across restarts)."""
    return sorted(set(_retro_status) | set(_seasons_on_disk(RETRO_ROOT)))


@ttlcache.ttl_cache()
def _scan_archive_entries(retro_root: Path, season: str) -> list:
    from app.core import retro
    out = []
    for p in retro.list_archive_dirs(retro_root, season):
        stamp = retro.archive_stamp_of(p.name, season)
        s = retro.run_summary(p)
        size = retro.dir_size(p)
        out.append({"id": stamp, "when": retro.stamp_human(stamp),
                    "weeks": s["weeks"], "elapsed_s": s["elapsed_s"],
                    "rel": s["headline_rel"], "rels": s.get("headline_rels"),
                    # each archive is its own tree, named for what it holds
                    "pf_name": _pf_name(p),
                    "scored": s["scored"],
                    "size": size, "size_h": retro.human_bytes(size)})
    return out


def _archive_entries(season: str) -> list:
    """Archived runs of one season, newest first, as the retro index lists
    them (cached per root + season: sizing every tree is the index's most
    expensive scan)."""
    return _scan_archive_entries(RETRO_ROOT, season)


def _archive_progress(root: Path, season: str) -> dict:
    """An archived run's timing block, shaped like _retro_progress; never
    active."""
    from app.core import retro
    meta = retro.read_meta(root)
    t = retro.timing(meta) if meta else {}
    done = _weeks_done(root)
    return {"season": season, "status": "archived", "done": done,
            # the archive's own settings, not the live season's
            "settings": retro.settings_summary(meta),
            "total": int(t.get("total_weeks") or done),
            "elapsed_s": t.get("elapsed_s"),
            "weeks_measured": t.get("weeks_measured") or 0,
            "mean_s": t.get("mean_s"), "eta_s": None,
            "eta_lo_s": None, "eta_hi_s": None, "eta_basis": None,
            "slowest_week": t.get("slowest_week"),
            "slowest_s": t.get("slowest_s"),
            "started_utc": t.get("started_utc"),
            "finished_utc": t.get("finished_utc"),
            "active": False}


def _season_meta(season: str) -> dict:
    """The season's run record: the live retro root first, then whichever
    root the season page shows (a sealed full-grid run keeps its own)."""
    from app.core import retro
    m = retro.read_meta(_live_root(season))
    if m:
        return m
    root, _is_seal = _season_root(season)
    return retro.read_meta(root)


def _season_status(season: str) -> str:
    """One status per season: running, paused, stopping, stopped, done,
    interrupted, error: …, or "". Across restarts the record's heartbeat
    decides, not the in-memory claim."""
    from app.core import retro
    mem = _retro_status.get(season, "")
    meta = _season_meta(season)
    disk = retro.effective_status(meta) if meta else ""
    if mem not in _RETRO_ACTIVE:
        _retro_claim_at.pop(season, None)   # stamp never outlives its claim
    if mem in _RETRO_ACTIVE:
        if disk == "interrupted":
            # the worker died without releasing the in-memory claim
            _retro_status[season] = "interrupted"
            return "interrupted"
        claimed_at = _retro_claim_at.get(season)
        finished = float((meta or {}).get("finished_utc") or 0)
        if (disk and (disk in ("stopped", "done") or disk.startswith("error"))
                and claimed_at and finished >= claimed_at):
            # the claimed worker finished after the claim was made: the claim
            # is dead (else "stopping" wedges Run). A fresh claim over an
            # older record still reads as live.
            _retro_status[season] = disk
            _retro_stop.discard(season)
            _retro_claim_at.pop(season, None)
            return disk
        if not meta and claimed_at and time.time() - claimed_at > 120:
            # no record two minutes after the claim: the worker never started
            _retro_status[season] = ""
            _retro_stop.discard(season)
            _retro_claim_at.pop(season, None)
            return ""
        if mem == "stopping":
            return "stopping"
        # the record refines running into paused as the worker holds
        return disk if disk in ("running", "paused") else mem
    return mem or disk


# === Retrospective: remaining-time estimate for a live replay ===
# Week cost climbs ~3x through a season, so a global mean freezes. Level =
# recency-weighted measured weeks (half-life 3); shape = a completed
# same-scope run's per-week profile; time spent in the in-flight week is
# credited. Reported as a range with its basis.

def _scope_key(meta: dict):
    """Hashable location-scope identity of a run record (None without
    settings): panel6/all plus '+us' when the national row was fitted
    (heavier weeks); a custom selection by its exact location list."""
    s = (meta or {}).get("settings")
    if not isinstance(s, dict) or not s:
        return None
    scope = str(s.get("scope") or "")
    if scope in ("panel6", "all"):
        from app.core import us_national as usn
        locs = [str(l) for l in (s.get("locations") or [])]
        nat = (any(usn.is_us(l) for l in locs) if locs
               else bool(s.get("national")))
        return scope + ("+us" if nat else "")
    locs = tuple(sorted(str(l) for l in (s.get("locations") or [])))
    return locs or None


#: fewest measured weeks a completed run needs before its per-week seconds
#: can serve as a season shape for another run's estimate
_PROFILE_MIN_WEEKS = 8


@ttlcache.ttl_cache()
def _profile_scan(retro_root: Path, seal_root: Path, season: str,
                  scope_key) -> tuple | None:
    """The same-scope completed run (most measured weeks) whose per-week
    seconds shape the estimate: other seasons' live and sealed trees and
    every archived run, including this season's. Cached by both roots.

    Returns (season_label, ((position 0..1, relative_cost), ...)) or None
    (the estimate then uses its default shape)."""
    if not scope_key:
        return None
    from app.core import retro
    best = None
    for s in retro.available_seasons():
        roots = []
        if s != season:
            roots.append(Path(retro_root) / s)
            roots.append(Path(seal_root) / s)
        roots.extend(retro.list_archive_dirs(retro_root, s))
        for r in roots:
            m = retro.read_meta(r)
            if not m or _scope_key(m) != scope_key:
                continue
            ws = {k: float(v)
                  for k, v in (m.get("week_seconds") or {}).items()
                  if isinstance(v, (int, float)) and float(v) > 0}
            if len(ws) < _PROFILE_MIN_WEEKS:
                continue          # too few weeks to carry a season's shape
            if best is None or len(ws) > best[2]:
                vals = [ws[k] for k in sorted(ws)]
                mean = sum(vals) / len(vals)
                n = len(vals)
                pts = tuple((i / (n - 1) if n > 1 else 0.0, v / mean)
                            for i, v in enumerate(vals))
                best = (s, pts, n)
    return (best[0], best[1]) if best else None


def _eta_estimate(measured, remaining, profile=None, spent_s=0.0,
                  overhead_s=0.0):
    """The remaining-time estimate itself; pure, so tests can replay
    recorded seasons week by week.

    measured    [(position, seconds)] for this run's completed weeks,
                ascending by week; position is the week's fractional place
                in its season, 0..1.
    remaining   [position] for the weeks still to run, the week in flight
                first.
    profile     ((position, relative_cost), ...) from a completed
                same-scope run, or None for a flat profile.
    spent_s     seconds already inside the week in flight.
    overhead_s  per-week seconds this run spends between weeks, measured
                from its own record.

    Returns (lo_s, mid_s, hi_s) or None when nothing is measured. The band
    is the larger of the weighted spread and a schedule calibrated on the
    recorded seasons (test_retro_eta.py), widened with no profile or few
    weeks, and treated as correlated across weeks (never shrunk by count)."""
    if not measured or not remaining:
        return None
    if not profile:
        # No same-scope profile: assume a linear 0.55x -> 1.40x ramp (each
        # week refits from season start, so cost grows). Chosen as the
        # smallest worst-season error among linear ramps replayed against the
        # recorded full-grid seasons (data: app/tests/test_retro_eta.py); a
        # flat default biased the estimate ~40 min low.
        profile = ((0.0, 0.55), (1.0, 1.40))
        default_shape = True
    else:
        default_shape = False

    def cost(p):
        if not profile:
            return 1.0
        if p <= profile[0][0]:
            return profile[0][1]
        for (p0, c0), (p1, c1) in zip(profile, profile[1:]):
            if p <= p1:
                return c0 + ((c1 - c0) * (p - p0) / (p1 - p0)
                             if p1 > p0 else 0.0)
        return profile[-1][1]

    n = len(measured)
    half_life = 3.0               # weeks: the recent past predicts the next
    wts = [0.5 ** ((n - 1 - j) / half_life) for j in range(n)]
    ratios = [s / max(cost(p), 1e-9) for p, s in measured]
    wsum = sum(wts)
    level = sum(w * r for w, r in zip(wts, ratios)) / wsum
    if level <= 0:
        return None
    var = sum(w * (r - level) ** 2 for w, r in zip(wts, ratios)) / wsum
    rel = (var ** 0.5) / level
    preds = [level * cost(q) + max(0.0, float(overhead_s))
             for q in remaining]
    left = max(0.0, sum(preds) - min(max(0.0, float(spent_s)), preds[0]))
    frac_rem = len(remaining) / (n + len(remaining))
    u = max(rel, 0.10 + 0.20 * frac_rem + (0.15 if default_shape else 0.0))
    if n < 3:
        u = max(u, 0.50)          # one or two weeks cannot claim precision
    elif n < 6:
        u = max(u, 0.25)
    return (left * (1.0 - u), left, left * (1.0 + u))


def _inflight_spent(root: Path, remaining: list, now: float) -> float:
    """Seconds already inside the in-flight week (the most recently started
    remaining week directory); zero between weeks."""
    weeks = Path(root) / "weeks"
    best = None
    for asof in remaining:
        wd = weeks / asof
        if not wd.is_dir():
            continue
        try:
            t0 = min((f.stat().st_mtime for f in wd.iterdir()), default=None)
        except OSError:
            continue
        if t0 is not None and (best is None or t0 > best):
            best = t0
    return max(0.0, now - best) if best is not None else 0.0


def _season_eta(meta: dict, season: str, root: Path, t: dict) -> tuple | None:
    """_eta_estimate for a live season: positions from the vintage calendar
    (index fallback), same-scope profile, in-flight seconds, measured
    between-week overhead. Returns (lo_s, mid_s, hi_s, basis) or None."""
    from app.core import retro
    ws = {k: float(v) for k, v in ((meta or {}).get("week_seconds") or {}).items()
          if isinstance(v, (int, float)) and float(v) > 0}
    if not ws:
        return None
    completed = {p.parent.name for p in retro.season_sample_files(root)}
    done = len(completed)
    vintages = list(retro.season_vintages(season))
    if vintages and completed <= set(vintages) and len(vintages) > done:
        posmap = {v: (i / (len(vintages) - 1) if len(vintages) > 1 else 0.0)
                  for i, v in enumerate(vintages)}
        measured = [(posmap.get(k, 1.0), ws[k]) for k in sorted(ws)]
        remaining_names = [v for v in vintages if v not in completed]
        remaining = [posmap[v] for v in remaining_names]
    else:
        # no calendar: place weeks by index; no in-flight credit
        total = max(int(t.get("total_weeks") or 0), done + 1)
        denom = max(total - 1, 1)
        keys = sorted(ws)
        measured = [(j / denom, ws[k]) for j, k in enumerate(keys)]
        remaining_names = []
        remaining = [(done + i) / denom for i in range(total - done)]
    if not remaining:
        return None
    now = time.time()
    spent = (_inflight_spent(root, remaining_names, now)
             if remaining_names else 0.0)
    elapsed = float(t.get("elapsed_s") or 0.0)
    overhead = min(120.0, max(0.0, elapsed - sum(ws.values()) - spent)
                   / max(1, len(ws)))
    prof = _profile_scan(RETRO_ROOT, RETRO_SEAL, season, _scope_key(meta))
    est = _eta_estimate(measured, remaining,
                        profile=(prof[1] if prof else None),
                        spent_s=spent, overhead_s=overhead)
    if est is None:
        return None
    basis = "estimate from %d completed week%s" % (
        len(ws), "" if len(ws) == 1 else "s")
    if prof:
        basis += ", weighted by the %s week profile" % prof[0]
    else:
        basis += ", shaped by the recorded full-grid week profile"
    return est[0], est[1], est[2], basis


def _retro_progress(season: str) -> dict:
    """Live progress and timing for one season, as the retro pages poll it.
    The ETA range (_season_eta) is null unless running and computable."""
    from app.core import retro
    status = _season_status(season)
    meta = _season_meta(season)
    t = retro.timing(meta) if meta else {}
    root, _is_seal = _season_root(season)
    done = _weeks_done(root)
    total = t.get("total_weeks") or len(retro.season_vintages(season))
    mean_s = t.get("mean_s")
    eta_lo = eta_s = eta_hi = eta_basis = None
    if status == "running" and total and done < total:
        est = _season_eta(meta, season, root, t)
        if est:
            eta_lo, eta_s, eta_hi, eta_basis = est
    return {"season": season, "status": status, "done": done,
            "total": int(total or 0),
            "settings": retro.settings_summary(meta),
            "elapsed_s": t.get("elapsed_s"),
            "weeks_measured": t.get("weeks_measured") or 0,
            "mean_s": mean_s, "eta_s": eta_s,
            "eta_lo_s": eta_lo, "eta_hi_s": eta_hi, "eta_basis": eta_basis,
            "slowest_week": t.get("slowest_week"),
            "slowest_s": t.get("slowest_s"),
            "started_utc": t.get("started_utc"),
            "finished_utc": t.get("finished_utc"),
            "active": status in _RETRO_ACTIVE}
