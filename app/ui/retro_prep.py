"""Season results preparation for the retrospective pages.

One finalize job per season root (_ensure_results_job, shared by the season
worker and the page visits that find stale caches), the LRU caches of parsed
scores and relWIS figures, the checks of whether a results page can render
from caches alone, and the week map cards. Not named retro_results: that is
the name of the GET /retro/{season} handler.
"""
from __future__ import annotations

import html as _htmlmod
import time
from collections import OrderedDict
from pathlib import Path

from app.core import horizons as _hzmod
from app.ui import state
from app.ui.retro_seasons import _is_sealed_root
from app.ui.shared import _invalidate_scans


# === Retrospective: results preparation (season finalize, off request paths) ===
# Scoring a season takes minutes, so finalize runs as one background job per
# season root, shared by the worker (before marking done) and page visits
# that find stale caches (they poll /api/retro/{season}/results_status).

_results_jobs: dict = {}          # str(root) -> job record
_results_lock = __import__("threading").Lock()


def _scoring_failed_hint(score_error: str) -> str:
    """The season map panel's scoring-failed fragment; score_error is
    escaped HERE (the template injects map_html with | safe)."""
    return ("<p class='hint'>Scoring failed: <code>"
            + _htmlmod.escape(score_error) + "</code>. The fitted forecasts "
            "below are intact; fix the scoring input (usually the FluSight "
            "hub clone, via the Data tab) and reload this page.</p>")


def _week_map_cards_by_model(root: Path, wk: str) -> dict:
    """{model: {fips: card}} for one stored retro week, every model it
    stored: each member's 23-level quantile sidecar
    (retro.week_member_quantiles) through the categorical CDF, anchor-week
    median as baseline.

    Disk-cached in playback_cache/map_cards/<wk>.json keyed by samples
    mtime. A SUBDIRECTORY because report_season._newest_input globs
    playback_cache/*.json as report inputs: cache warming must not look
    like new data."""
    import json as _json
    import numpy as np
    from app.core import retro
    from app.core.categorical import CATS, probs_from_quantiles
    root = Path(root)
    sp = retro.week_samples_path(root, wk)
    if sp is None:
        return {}
    try:
        mtime = int(sp.stat().st_mtime)
    except OSError:
        return {}
    cf = root / "playback_cache" / "map_cards" / f"{wk}.json"
    try:
        cached = _json.loads(cf.read_text())
        if cached.get("mtime") == mtime and cached.get("v") == 2:
            return cached["cards"]
    except Exception:
        pass
    locs = __import__("flubnf.settings",
                      fromlist=["load_locations"]).load_locations()
    n2a = dict(zip(locs.location_name, locs.abbreviation))
    n2p = dict(zip(locs.location_name, locs.population.astype(float)))
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    # baseline: the PF's origin draws (the reported value replicated); an
    # analogue-only week has none, so read the week's vintage instead
    mq = retro.week_member_quantiles(root, wk)
    base = {}
    try:
        d = retro.read_samples(sp)
        for loc, sm in (d.get("pf") or {}).items():
            o = np.asarray(sm.get(_hzmod.ORIGIN, []), float)
            o = o[np.isfinite(o)]
            if o.size:
                base[loc] = float(np.median(o))
    except Exception:
        pass
    if not base:
        try:
            base = _last_reported_before(wk, n2f)
        except Exception:
            base = {}
    by_model = {}
    for model, by_loc in mq.items():
        cards = {}
        for loc, qs in by_loc.items():
            q1 = qs.get("0")                      # one week ahead, canonical
            lo = base.get(loc)
            if not q1 or lo is None or loc not in n2f:
                continue
            probs = probs_from_quantiles(q1, lo, int(n2p.get(loc, 0)), 0)
            if not probs:
                continue
            med = float(q1.get(0.5, 0.0))
            # hover_html reaches innerHTML: escape the name
            hover = (f"<b>{_htmlmod.escape(loc)}</b><br>1-wk median: "
                     f"{med:.0f}<br>" +
                     "<br>".join(f"{c.replace('_',' ')}: {probs.get(c,0):.0%}"
                                 for c in CATS))
            cards[n2f[loc]] = {"probs": probs, "name": loc,
                               "abbr": n2a.get(loc, ""), "fips": n2f[loc],
                               "hover_html": hover}
        if cards:
            by_model[model] = cards
    try:
        # write beside, then replace
        import os as _os
        cf.parent.mkdir(parents=True, exist_ok=True)
        tmp = cf.with_name(cf.name + ".tmp")
        tmp.write_text(_json.dumps({"mtime": mtime, "v": 2, "cards": by_model}))
        _os.replace(tmp, cf)
    except Exception:
        pass                      # an unwritable cache costs speed, not truth
    return by_model


def _last_reported_before(wk: str, n2f: dict) -> dict:
    """{location: last reported value} from the vintage dated `wk`, the
    baseline a week stores no anchor draws for."""
    import pandas as pd
    df = pd.read_csv(state.data_mod.vintage_path(wk), dtype={"location": str})
    df["location"] = df["location"].str.zfill(2)
    df = df[df.date <= wk].dropna(subset=["value"]).sort_values("date")
    last = df.groupby("location")["value"].last()
    return {loc: float(last[f]) for loc, f in n2f.items() if f in last.index}


def _retro_map_models(by_model: dict) -> list:
    """Models a week's map can show, in display order (a stored blend only
    when the week holds nothing else)."""
    from app.core import report_v2
    order = report_v2.toggle_models(by_model)
    return order or [m for m in report_v2.MODEL_ORDER if m in by_model]


def _week_map_cards(root: Path, wk: str) -> dict:
    """The first display-order model's cards for the week (the default
    view before the toggle)."""
    by_model = _week_map_cards_by_model(root, wk)
    order = _retro_map_models(by_model)
    return dict(by_model[order[0]]) if order else {}


def _ensure_results_job(root: Path, season: str,
                        force: bool = False) -> dict:
    """Start or join THE finalize job for this root (one per root; racing
    callers share the record, whose 'done' event fires when caches are
    ready). `force` rescores; ignored when joining a running job."""
    import threading
    from app.core import retro
    key = str(root)
    with _results_lock:
        job = _results_jobs.get(key)
        if job and not job["done"].is_set():
            return job
        if _is_sealed_root(root):
            # the sealed record is read only: nothing is scored into it
            job = {"phase": "sealed", "t0": time.time(),
                   "done": threading.Event(), "seconds": 0.0,
                   "season": season, "inputs": None,
                   "error": "the sealed validation record is read only; "
                            "its scores stand and are never recomputed"}
            job["done"].set()
            _results_jobs[key] = job
            return job
        job = {"phase": "preparing", "t0": time.time(),
               "done": threading.Event(), "error": "", "seconds": None,
               "season": season,
               "inputs": retro.newest_samples_mtime(root)}
        _results_jobs[key] = job

    def _run():
        try:
            job["seconds"] = retro.finalize_season(
                root, season,
                phase_cb=lambda p: job.__setitem__("phase", p),
                force=force)
            # warm the default view's (last week's) map cards
            wks = [p.parent.name for p in retro.season_sample_files(root)]
            if wks:
                _week_map_cards(root, wks[-1])
        except Exception as e:
            job["error"] = f"{type(e).__name__}: {str(e)[:220]}"
        finally:
            job["done"].set()
            _invalidate_scans()

    threading.Thread(target=_run, daemon=True,
                     name=f"flubnf-results-{season}").start()
    return job


def _job_covered(root: Path) -> dict | None:
    """The completed job that ran on this root's CURRENT inputs, or None.
    Empty scores plus a covering job means truth has not settled (or
    job['error']): render that state, do not recompute every visit."""
    from app.core import retro
    job = _results_jobs.get(str(root))
    if (job and job["done"].is_set()
            and job["inputs"] >= retro.newest_samples_mtime(root)):
        return job
    return None


#: LRU of parsed scores.json frames keyed by (path, mtime_ns, size), so a
#: rescore invalidates by construction. ~50 MB per frame; cap 3 holds the
#: three sealed seasons without eviction while bounding archive sweeps.
_SCORES_FRAMES_MAX = 3
_SCORES_FRAMES: "OrderedDict" = OrderedDict()


def _scores_df(root: Path):
    """Parsed scores.json for this root (None if missing/unparseable), one
    parse per file content. Callers must not mutate the frame."""
    import pandas as pd
    sf = Path(root) / "scores.json"
    try:
        st = sf.stat()
    except OSError:
        return None
    key = (str(sf), st.st_mtime_ns, st.st_size)
    hit = _SCORES_FRAMES.get(key)
    if hit is not None:
        _SCORES_FRAMES.move_to_end(key)      # least-recently-used ordering
        return hit
    try:
        df = pd.read_json(sf)
    except Exception:
        return None
    _SCORES_FRAMES[key] = df
    while len(_SCORES_FRAMES) > _SCORES_FRAMES_MAX:
        _SCORES_FRAMES.popitem(last=False)   # evict one, never flush the lot
    return df


#: LRU of season relWIS figures keyed by scores identity, convention and (for
#: pairwise, ~3 s per season) the field data's identity. Entries are small.
_RELWIS_FIGS_MAX = 12
_RELWIS_FIGS: "OrderedDict" = OrderedDict()


def _relwis_conventions() -> list:
    """The convention switch's options; the project's own (the default,
    and every sealed number's) first."""
    from app.core import relwis
    return [relwis.CONVENTION_INFO[k] for k in relwis.CONVENTIONS]


def _relwis_figures(root: Path, convention: str):
    """This root's relWIS figures under ONE convention, cached on identity.
    Without the FluSight field data, pairwise figures carry the reason and
    NO numbers; never substitute the other convention (app/core/relwis).
    """
    from app.core import relwis
    from app.core import us_national as usn
    conv = relwis.convention_of(convention)
    # the field (600k+ cells) only when the convention needs it
    field = relwis.load_field_cells() if conv == relwis.PAIRWISE else None
    sf = Path(root) / "scores.json"
    try:
        st = sf.stat()
        ident = (st.st_mtime_ns, st.st_size)
    except OSError:
        ident = (0, 0)
    key = (str(sf), ident, conv,
           (field.stamp, field.reason) if field is not None else ())
    hit = _RELWIS_FIGS.get(key)
    if hit is not None:
        _RELWIS_FIGS.move_to_end(key)
        return hit
    figs = relwis.season_figures(usn.pooled_frame(_scores_df(root)), conv,
                                 field=field)
    _RELWIS_FIGS[key] = figs
    while len(_RELWIS_FIGS) > _RELWIS_FIGS_MAX:
        _RELWIS_FIGS.popitem(last=False)
    return figs


def _scores_current_fast(root: Path) -> bool:
    """retro.scores_current's rule (exists, parses, newer than every week
    and the hub's truth) from stats and the cached parse. Sealed roots are
    current whenever their scores parse."""
    from app.core import retro
    root = Path(root)
    weeks = retro.season_sample_files(root)
    if not weeks:
        return True
    sf = root / "scores.json"
    if not sf.is_file():
        return False
    if _is_sealed_root(root):
        return _scores_df(root) is not None
    try:
        from app.core.data import truth_mtime
        if sf.stat().st_mtime < max([p.stat().st_mtime for p in weeks]
                                    + [truth_mtime()]):
            return False           # older than a sample, or than the truth
    except OSError:
        return False
    return _scores_df(root) is not None


def _scores_scoreable_fast(root: Path) -> bool:
    """retro.scores_scoreable's exact rule (a model column and at least one
    cell), from the shared cached parse."""
    df = _scores_df(root)
    return df is not None and (not df.empty) and ("model" in df.columns)


def _results_pending(root: Path) -> str:
    """'' when the results page can render from caches alone, else why not
    (stats and cached reads only, never computation)."""
    from app.core import retro
    if not _scores_current_fast(root):
        return "scores stale"
    if not _scores_scoreable_fast(root):
        return "" if _job_covered(root) else "scores empty"
    if not retro.national_aggregate_fresh(root):
        return "national aggregate stale"
    return ""
