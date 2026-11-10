"""Season results preparation for the retrospective pages.

One finalize job per season root (_ensure_results_job, shared by the season
worker and the page visits that find stale caches), the LRU cache of relWIS
figures (the parsed scores' LRU is app.core.retro_store.scores_frame, named
here as _SCORES_FRAMES), the checks of whether a results page can render
from caches alone, and the week map cards, warmed for every week once a
job is done. Not named retro_results: that is the name of the GET
/retro/{season} handler.
"""
from __future__ import annotations

import html as _htmlmod
import json as _json
import os as _os
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
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
_results_lock = threading.Lock()


#: the map-card cache's shape (v3: the Liu-West filter alone joins)
_MAP_CARDS_V = 3

#: (root, week) -> [lock, holders]: one computation of a week's map cards
#: at a time, so the warm after a finalize, a mapswap request and the
#: season report export wait for a week in flight instead of repeating
#: it (each reads the week's samples file). An entry lives while held.
_MAP_CARD_LOCKS: dict = {}
_MAP_CARD_LOCKS_GUARD = threading.Lock()


@contextmanager
def _map_cards_lock(root: Path, wk: str):
    key = (str(root), wk)
    with _MAP_CARD_LOCKS_GUARD:
        ent = _MAP_CARD_LOCKS.setdefault(key, [threading.Lock(), 0])
        ent[1] += 1
    try:
        with ent[0]:
            yield
    finally:
        with _MAP_CARD_LOCKS_GUARD:
            ent[1] -= 1
            if ent[1] == 0 and _MAP_CARD_LOCKS.get(key) is ent:
                del _MAP_CARD_LOCKS[key]


def _cached_map_cards(cf: Path, mtime: int):
    """The cards cached in `cf` for this samples mtime, or None."""
    try:
        cached = _json.loads(cf.read_text(encoding="utf-8"))
        if cached.get("mtime") == mtime and cached.get("v") == _MAP_CARDS_V:
            return cached["cards"]
    except Exception:
        pass
    return None


def _week_map_cards_by_model(root: Path, wk: str) -> dict:
    """{model: {fips: card}} for one stored retro week, every model it
    stored: each member's 23-level quantile sidecar
    (retro.week_member_quantiles) through the categorical CDF, anchor-week
    median as baseline.

    Disk-cached in playback_cache/map_cards/<wk>.json keyed by samples
    mtime. A SUBDIRECTORY because report_season._newest_input globs
    playback_cache/*.json as report inputs: cache warming must not look
    like new data. One computation per week at a time (_map_cards_lock)."""
    from app.core import retro
    root = Path(root)
    sp = retro.week_samples_path(root, wk)
    if sp is None:
        return {}
    try:
        mtime = int(sp.stat().st_mtime)
    except OSError:
        return {}
    cf = root / "playback_cache" / "map_cards" / f"{wk}.json"
    hit = _cached_map_cards(cf, mtime)
    if hit is not None:
        return hit
    with _map_cards_lock(root, wk):
        # a caller that waited on the lock finds the week just written
        hit = _cached_map_cards(cf, mtime)
        if hit is not None:
            return hit
        return _compute_map_cards(root, wk, sp, mtime, cf)


def _compute_map_cards(root: Path, wk: str, sp: Path, mtime: int,
                       cf: Path) -> dict:
    """_week_map_cards_by_model's computation and cache write."""
    import numpy as np
    from app.core import retro
    from app.core.categorical import CATS, probs_from_quantiles
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
    # the warm checks again just before it writes: a delete or a move of
    # the tree may have stopped it while this week was worked out
    job = getattr(_WARM_THREAD, "job", None)
    if job is not None and job.get("warm_stop"):
        return by_model
    try:
        # write beside, then replace; never re-creating a season tree
        # deleted meanwhile (no parents=True above playback_cache)
        cf.parent.parent.mkdir(exist_ok=True)
        cf.parent.mkdir(exist_ok=True)
        tmp = cf.with_name(cf.name + ".tmp")
        tmp.write_text(_json.dumps({"mtime": mtime, "v": _MAP_CARDS_V,
                                    "cards": by_model}), encoding="utf-8")
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


#: whether a finalize job goes on to warm every other week's map cards
#: (_warm_map_cards) once its results are ready; a test that wants the
#: warm turns it on and waits on the job's "warm" event
_WARM_MAP_CARDS = True
#: the longest pause between two warmed weeks. Each pause matches the
#: time the week just took, up to this (one week's samples decode holds
#: the interpreter about a second; a cached week needs no pause)
_WARM_PAUSE_S = 0.2
#: how long the warm waits for the season worker whose finalize this was
#: to mark the season done (it does so just after the job); a season still
#: replaying after that is busy, and the warm does not start
_WARM_SETTLE_S = 10.0
#: how long a delete or a move of a season tree waits for the warm it
#: stopped to leave the week in hand (_stop_warm; a week takes about a
#: second, a large one on a slow computer several)
_WARM_STOP_WAIT_S = 20.0
#: the warm's own thread knows its job (_warm_map_cards sets it), so the
#: card write (_compute_map_cards) can check the job's stop just before
#: writing; other callers' writes are left as they were
_WARM_THREAD = threading.local()


def _season_busy(season: str) -> bool:
    """A replay of `season` holds the season: its worker's in-memory claim
    here, or the live root's run record (another process's replay).
    Read only: no status is corrected here."""
    from app.core import retro
    from app.ui import retro_seasons
    if retro_seasons._retro_status.get(season) in retro_seasons._RETRO_ACTIVE:
        return True
    try:
        meta = retro.read_meta(retro_seasons._live_root(season))
        return (bool(meta) and retro.effective_status(meta)
                in retro_seasons._RETRO_ACTIVE)
    except Exception:
        return True


def _warm_should_stop(root: Path, season: str, job: dict) -> bool:
    """Whether the map-card warm stops before its next week: a delete or a
    move of the tree stopped it (_stop_warm), a newer job claimed the
    root, the season tree is gone, a forecast run or a sandbox fit or
    experiment is active, a replay of any season holds the engine here, or
    a replay of the season holds it."""
    from app.ui import retro_seasons
    if job.get("warm_stop"):
        return True
    if _results_jobs.get(str(root)) is not job:
        return True
    if not (Path(root) / "weeks").is_dir():
        return True
    if (state._status.get("running") or state._sandbox_status.get("running")
            or state._sandbox_status.get("experiment")):
        return True
    # another season's replay is a run too (it holds the engine, as the
    # Forecast form's busy check says): the warm leaves it the machine
    if any(st in retro_seasons._RETRO_ACTIVE
           for st in list(retro_seasons._retro_status.values())):
        return True
    return _season_busy(season)


def _warm_settled(root: Path, season: str, job: dict) -> bool:
    """Whether the warm may start: the season worker that ran this job (if
    any) has released the season within _WARM_SETTLE_S, and the job is
    still the root's and not stopped."""
    t_end = time.monotonic() + _WARM_SETTLE_S
    while _season_busy(season):
        if (time.monotonic() >= t_end or job.get("warm_stop")
                or _results_jobs.get(str(root)) is not job):
            return False
        time.sleep(0.25)
    return not job.get("warm_stop")


def _warm_map_cards(root: Path, season: str, job: dict) -> None:
    """After a finalize: every stored week's map cards, newest first, so
    playing the season never waits on a week's forecasting samples. A cached
    week costs a stat and a small read; a failed week is left for its
    first view, as before. Sets job["warm"] however it ends, after its
    last write."""
    from app.core import retro
    _WARM_THREAD.job = job
    try:
        if not _warm_settled(root, season, job):
            return
        weeks = [p.parent.name for p in retro.season_sample_files(root)]
        for wk in reversed(weeks):
            if _warm_should_stop(root, season, job):
                break
            t = time.monotonic()
            try:
                _week_map_cards_by_model(root, wk)
            except Exception:
                pass
            time.sleep(min(_WARM_PAUSE_S, time.monotonic() - t))
    except Exception:
        pass
    finally:
        _WARM_THREAD.job = None
        job["warm"].set()


def _jobs_on(root: Path) -> list:
    """The results jobs recorded for the tree at `root`: under its own
    name, or the same folder named another way."""
    root = Path(root)
    out = []
    for key, job in list(_results_jobs.items()):
        if not job:
            continue
        same = key == str(root)
        if not same:
            try:
                same = Path(key).resolve() == root.resolve()
            except OSError:
                same = False
        if same:
            out.append(job)
    return out


def _stop_warm(root: Path) -> bool:
    """Before a season tree is deleted or moved (Start's discard and
    archive, an archived run's delete, Storage's delete): stop the map-card
    warm on it, so it begins no other week and writes no other card, and
    wait up to _WARM_STOP_WAIT_S for it to leave the week in hand. Without
    this the warm could make playback_cache again inside a tree the
    delete had half removed, and the delete fail with the weeks gone.

    True when no warm can write into the tree any more; False while one is
    still on its week (the caller refuses, nothing removed). A finalize
    still running is not waited for, as before the warm existed; its warm
    will not start."""
    t_end = time.monotonic() + _WARM_STOP_WAIT_S
    stopped = True
    for job in _jobs_on(root):
        warm = job.get("warm")
        if warm is None:
            continue                  # a record from before the warm
        job["warm_stop"] = True
        done = job.get("done")
        if done is not None and not done.is_set():
            continue
        if not warm.wait(max(0.0, t_end - time.monotonic())):
            stopped = False
    return stopped


#: the trees a delete or a move is removing right now, by path as named
#: and resolved (key -> holders; under _results_lock): no finalize job
#: starts on one (_ensure_results_job refuses), so a results page opened
#: during a delete cannot score into the half removed tree
_REMOVING: dict = {}

#: the refusals' words: a results page flashes them, a job carries them
_REMOVING_WHY = "the run is being deleted or moved; its results are not " \
                "prepared"
_GONE_WHY = "the run is no longer on disk; its results are not prepared"

#: what _removing yields while another delete, move or Replace import
#: already holds the tree: the caller refuses in these words, nothing
#: removed (two removers of one tree cannot both succeed; the loser's
#: delete failed on the tree the winner had taken). A Run form's discard
#: or archive, whose tree is the live season, says its own sentence
_ALREADY_REMOVING = "already being deleted or replaced"


def _tree_keys(root: Path) -> set:
    """The tree's path as named and as resolved."""
    root = Path(root)
    keys = {str(root)}
    try:
        keys.add(str(root.resolve()))
    except OSError:
        pass
    return keys


def _being_removed(root: Path) -> bool:
    """Whether a delete or a move of the tree at `root` is under way (no
    file system call while none is)."""
    return bool(_REMOVING) and not _tree_keys(root).isdisjoint(_REMOVING)


@contextmanager
def _removing(root: Path):
    """Around a season tree's delete or move (Start's discard and archive,
    an archived run's delete, Storage's delete, an import's Replace). The
    tree is marked first, so from here on no finalize job starts on it,
    then yields _ALREADY_REMOVING ("already being deleted or replaced")
    while another such block holds it, under its name or the same folder
    named another way (two deletes at once: the caller refuses, nothing
    removed);
    "results" while a finalize still runs on it (it would go on writing
    into the half removed tree: the caller refuses, nothing removed); or
    "" when the caller may remove or move it. The mark is lifted when the
    block ends."""
    keys = _tree_keys(root)
    with _results_lock:
        held = not keys.isdisjoint(_REMOVING)
        for k in keys:
            _REMOVING[k] = _REMOVING.get(k, 0) + 1
        finalizing = any(job and job.get("done") is not None
                         and not job["done"].is_set()
                         and not _tree_keys(k).isdisjoint(keys)
                         for k, job in list(_results_jobs.items()))
    try:
        yield (_ALREADY_REMOVING if held
               else "results" if finalizing else "")
    finally:
        with _results_lock:
            for k in keys:
                n = _REMOVING.pop(k, 0) - 1
                if n > 0:
                    _REMOVING[k] = n


def _ensure_results_job(root: Path, season: str,
                        force: bool = False) -> dict:
    """Start or join THE finalize job for this root (one per root; racing
    callers share the record, whose 'done' event fires when caches are
    ready, and whose 'warm' event fires once the other weeks' map cards
    are warmed after that, or the warm stopped). `force` rescores; ignored
    when joining a running job."""
    from app.core import retro
    key = str(root)
    with _results_lock:
        job = _results_jobs.get(key)
        if job and not job["done"].is_set():
            return job
        why = (_REMOVING_WHY if _being_removed(root)
               else "" if Path(root).is_dir() else _GONE_WHY)
        if why:
            # not recorded: once the delete ends, or the tree is replayed
            # again, the next caller starts a job as before
            job = {"phase": "refused", "t0": time.time(),
                   "done": threading.Event(), "seconds": None,
                   "season": season, "inputs": None, "error": why,
                   "refused": True}
            job["done"].set()
            return job
        if _is_sealed_root(root):
            # the sealed record is read only: nothing is scored into it
            job = {"phase": "sealed", "t0": time.time(),
                   "done": threading.Event(), "seconds": 0.0,
                   "season": season, "inputs": None,
                   "warm": threading.Event(),
                   "error": "the sealed validation record is read only; "
                            "its scores stand and are never recomputed"}
            job["done"].set()
            job["warm"].set()
            _results_jobs[key] = job
            return job
        job = {"phase": "preparing", "t0": time.time(),
               "done": threading.Event(), "error": "", "seconds": None,
               "season": season, "warm": threading.Event(),
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
        if _WARM_MAP_CARDS and not job["error"]:
            _warm_map_cards(root, season, job)
        else:
            job["warm"].set()

    threading.Thread(target=_run, daemon=True,
                     name=f"flubnf-results-{season}").start()
    return job


def _job_covered(root: Path) -> dict | None:
    """The completed job that ran on this root's CURRENT inputs, or None.
    Empty scores plus a covering job means truth has not settled (or
    job['error']): render that state, do not recompute every visit. A
    sealed record's job (no inputs stamp) covers it: a seal is never
    recomputed."""
    from app.core import retro
    job = _results_jobs.get(str(root))
    if (job and job["done"].is_set()
            and (job["inputs"] is None
                 or job["inputs"] >= retro.newest_samples_mtime(root))):
        return job
    return None


#: the LRU of parsed scores.json frames lives in app/core/retro_store
#: (scores_frame), shared with the season player. _SCORES_FRAMES and
#: _SCORES_FRAMES_MAX here name its objects (module __getattr__ below):
#: looked up on use, so importing this module (the server's import) loads
#: no part of app.core.retro_store
_SCORES_ALIASES = {"_SCORES_FRAMES": "SCORES_FRAMES",
                   "_SCORES_FRAMES_MAX": "SCORES_FRAMES_MAX"}


def __getattr__(name: str):
    if name in _SCORES_ALIASES:
        from app.core import retro_store
        return getattr(retro_store, _SCORES_ALIASES[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _scores_df(root: Path):
    """Parsed scores.json for this root (None if missing/unparseable), one
    parse per file content (retro_store.scores_frame, under its lock).
    Callers must not mutate the frame."""
    from app.core import retro_store
    return retro_store.scores_frame(root)


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
    """retro.scores_current's rule (exists, parses, this scores version,
    newer than every week and the hub's truth) from stats and the cached
    parse. Sealed roots are current whenever their scores parse."""
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
    # a file scored under the earlier cell rule (retro.SCORES_V), or before
    # the Liu-West filter alone was scored, is stale; a job that already
    # rescored these inputs is believed, so a week whose filter scores no
    # cell never loops
    df = _scores_df(root)
    return (retro.scores_frame_current(df)
            and not (retro.filter_scores_missing(root, df)
                     and not _job_covered(root)))


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
