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
    from app.core import replay_bundle, retro
    out = []
    for p in retro.list_archive_dirs(retro_root, season):
        stamp = retro.archive_stamp_of(p.name, season)
        s = retro.run_summary(p)
        size = retro.dir_size(p)
        out.append({"id": stamp, "when": retro.stamp_human(stamp),
                    # a replay imported from another machine wears that
                    # label ("imported from <host> on <date>") in place of
                    # the archived-run one
                    "imported": replay_bundle.imported_label(p),
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
            # frozen: the season's week list growing later adds nothing here
            "added": [], "added_n": 0, "sealed": False,
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
# Each week refits from the season start, so a week costs more the more data
# it covers: a near-straight line through the season (the recorded full-grid
# seasons climb 200 s -> 607 s over 32 weeks, a few percent off the line).
# The estimate fits that line to this run's own weeks and prices every week
# still to run on it. Until enough weeks are in, it leans on the recorded
# ramp scaled to this run. Time already spent in the week in flight is
# credited. Reported as a range with its basis.

#: measured weeks by which this run's own line has replaced the prior
_LINE_FULL_WEEKS = 8


def _ramp(p: float) -> float:
    """The prior's relative week cost at season position p (0..1): a linear
    0.55x -> 1.40x ramp, the smallest worst-season error among linear ramps
    replayed against the recorded full-grid seasons."""
    return 0.55 + 0.85 * min(1.0, max(0.0, p))


def _line_fit(measured) -> tuple:
    """Least-squares seconds = a + b * position over the measured weeks, the
    slope held at zero or above (more data never makes a week cheaper).
    Returns (a, b, residual_sd, mean_position, sxx)."""
    n = len(measured)
    xs = [p for p, _ in measured]
    ys = [s for _, s in measured]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = (max(0.0, sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx)
         if sxx > 0 else 0.0)
    a = my - b * mx
    sd = ((sum((y - a - b * x) ** 2 for x, y in zip(xs, ys)) / (n - 2)) ** 0.5
          if n > 2 else 0.0)
    return a, b, sd, mx, sxx


def _eta_estimate(measured, remaining, spent_s=0.0, overhead_s=0.0):
    """The remaining-time estimate itself; pure, so tests can replay
    recorded seasons week by week.

    measured    [(position, seconds)] for this run's completed weeks,
                ascending by week; position is the week's fractional place
                in its season, 0..1.
    remaining   [position] for the weeks still to run, the week in flight
                first.
    spent_s     seconds already inside the week in flight.
    overhead_s  per-week seconds this run spends between weeks, measured
                from its own record.

    Returns (lo_s, mid_s, hi_s) or None when nothing is measured. Each
    remaining week is priced on the line through the measured weeks,
    blended with the prior (the recorded ramp at this run's recency-weighted
    level) until _LINE_FULL_WEEKS are measured. The line's band is its
    prediction error for the sum of the remaining weeks (two standard
    errors, never under 8%); the prior's band is calibrated on the recorded
    seasons (test_retro_eta.py) and never shrunk by week count."""
    if not measured or not remaining:
        return None
    n, m = len(measured), len(remaining)
    # the prior: the recorded ramp, scaled to the recent weeks (half-life 3)
    wts = [0.5 ** ((n - 1 - j) / 3.0) for j in range(n)]
    ratios = [s / _ramp(p) for p, s in measured]
    wsum = sum(wts)
    level = sum(w * r for w, r in zip(wts, ratios)) / wsum
    if level <= 0:
        return None
    rel = (sum(w * (r - level) ** 2 for w, r in zip(wts, ratios))
           / wsum) ** 0.5 / level
    prior = [level * _ramp(q) for q in remaining]
    u_prior = max(rel, 0.25 + 0.20 * m / (n + m))
    # this run's own line, weighted in as its weeks accumulate
    w = min(1.0, (n - 1) / (_LINE_FULL_WEEKS - 1))
    preds, u = prior, u_prior
    if w > 0:
        a, b, sd, mx, sxx = _line_fit(measured)
        line = [a + b * q for q in remaining]
        tot = sum(line)
        tilt = sum(q - mx for q in remaining)
        se = sd * (m + m * m / n + (tilt * tilt / sxx if sxx > 0 else 0.0)) ** 0.5
        u_line = max(0.08, 2.0 * se / tot) if tot > 0 else u_prior
        preds = [w * l + (1.0 - w) * p for l, p in zip(line, prior)]
        u = w * u_line + (1.0 - w) * u_prior
    if n < 3:
        u = max(u, 0.50)          # one or two weeks cannot claim precision
    elif n < 6:
        u = max(u, 0.25)
    u = min(u, 0.95)
    preds = [max(0.0, p) + max(0.0, float(overhead_s)) for p in preds]
    left = max(0.0, sum(preds) - min(max(0.0, float(spent_s)), preds[0]))
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
    (index fallback), in-flight seconds, measured between-week overhead. Returns (lo_s, mid_s, hi_s, basis) or None."""
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
    est = _eta_estimate(measured, remaining, spent_s=spent, overhead_s=overhead)
    if est is None:
        return None
    n = len(ws)
    if n >= _LINE_FULL_WEEKS:
        basis = ("estimate from this run's %d completed weeks, priced on "
                 "their week-by-week climb" % n)
    else:
        basis = ("estimate from %d completed week%s and the recorded season "
                 "ramp, until this run's own climb takes over at %d weeks"
                 % (n, "" if n == 1 else "s", _LINE_FULL_WEEKS))
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
    vints = retro.season_vintages(season)
    # the season's week list can grow after a replay finished (the hub
    # archive or the shipped snapshots gained a week): the total follows
    # the list, and `added` names the weeks a Resume would run
    total = max(int(t.get("total_weeks") or 0), len(vints))
    added = ([v for v in vints if not retro.week_done(root, v)]
             if status == "done" and done else [])
    mean_s = t.get("mean_s")
    eta_lo = eta_s = eta_hi = eta_basis = None
    if status == "running" and total and done < total:
        est = _season_eta(meta, season, root, t)
        if est:
            eta_lo, eta_s, eta_hi, eta_basis = est
    return {"season": season, "status": status, "done": done,
            "total": int(total or 0),
            "added": added, "added_n": len(added), "sealed": _is_seal,
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
