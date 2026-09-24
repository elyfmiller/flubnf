"""Retrospective (GET /retro, GET /retro/{season}): the season index and
its APIs, the run controls and the season worker, and the season page with
its playback, map swap and report APIs.

The season registry, live progress and ETA live in app/ui/retro_seasons.py,
the results preparation (finalize jobs, score caches, week map cards) in
app/ui/retro_prep.py. POST /retro/stop and POST /retro/run stay above GET
/retro/{season}: the first route a path matches names the Allow header of
a wrong-method request. An APIRouter server.py includes last of the tabs.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.runs import RunSpec, fmt_hms
from app.ui import pipeline, retro_prep, retro_seasons, templating
from app.ui.forms import (_knob_form, _knob_panel, _knob_raw, _knobs,
                          _str_field)
from app.ui.retro_prep import (_job_covered, _relwis_figures, _results_jobs,
                               _results_pending, _retro_map_models,
                               _scores_df, _scores_scoreable_fast,
                               _scoring_failed_hint, _week_map_cards_by_model)
from app.ui.retro_seasons import (_RETRO_ACTIVE, _archive_progress,
                                  _is_sealed_root, _live_root,
                                  _retro_claim_at, _retro_status, _retro_stop,
                                  _sealed_label, _season_status,
                                  _valid_archive, _valid_season)
from app.ui.shared import (_back, _flash, _invalidate_scans,
                           _sandbox_live_reason)
from app.ui.state import REPO, _engine_lock, _status
from app.ui.templating import (_member_colors, _name_fn, _names_for_root,
                               _pf_name, templates)
from app.ui.versions import RUNNING_SHA, VERSIONS

router = APIRouter()


# === Retrospective (season registry and progress: retro_seasons.py) ===
class _RetroStopRequested(Exception):
    """Raised inside the season worker between weeks when a stop was asked."""


# === Retrospective index (/retro) and its APIs -> retro.html ===
def _retro_state_names() -> list:
    """State list for the retro form; packaged locations table when the hub
    is not cloned yet."""
    import pandas as pd
    from flubnf.settings import LOCATIONS
    packaged = REPO / "flubnf/data/locations.csv"
    for src in (LOCATIONS, packaged):
        try:
            locs = pd.read_csv(src, dtype=str)
            return list(locs.location_name[(locs.location.str.len() == 2)
                                           & (locs.abbreviation != "US")])
        except Exception:
            continue
    return []


def _retro_national_name() -> str:
    """The hub's location_name for the national row (as truth and the
    forecast path name it); falls back to the FIPS code."""
    import pandas as pd
    from flubnf.settings import LOCATIONS
    from app.core import us_national as usn
    packaged = REPO / "flubnf/data/locations.csv"
    for src in (LOCATIONS, packaged):
        try:
            locs = pd.read_csv(src, dtype=str)
            hit = locs.location_name[locs.abbreviation == "US"]
            if len(hit):
                return str(hit.iloc[0])
        except Exception:
            continue
    return usn.US_FIPS


@router.get("/retro", response_class=HTMLResponse)
def retro_index(request: Request, dataset: str = "", tab: str = ""):
    """Two tabs (retro.html): the FluSight hub's seasons, or "Your data"
    (tab=own, or dataset=<id>): the replay of a stored dataset. tab=own
    opens the first stored dataset, or with none the upload box alone."""
    from app.core import retro as _retro
    from app.core.retro import available_seasons, season_vintages
    # the own-data replays: their own tab, never beside the hub seasons
    from app.ui import datasets_ui as _dsu
    own_tab = bool(dataset) or tab == "own"
    if own_tab:
        ids = [i for i, _ in _dsu.choices()]
        # tab=own, or a dataset since deleted: the first stored one
        if ids and dataset not in ids:
            return RedirectResponse(f"/retro?dataset={ids[0]}",
                                    status_code=303)
        if dataset and not ids:
            return RedirectResponse("/retro?tab=own", status_code=303)
    if own_tab:
        return templates.TemplateResponse(request, "retro.html", {
            **_dsu.retro_context(dataset), "active": "Retrospective",
            "own_tab": True, "seasons": []})
    seasons = []
    for s in available_seasons():
        total = len(season_vintages(s))
        root, is_seal = retro_seasons._season_root(s)
        done = retro_seasons._weeks_done(root)
        prog = retro_seasons._retro_progress(s)
        status = prog["status"]
        # head scores: one relWIS per scored model
        _summ = _retro.run_summary(root)
        rel = _summ.get("headline_rel")
        rels = _summ.get("headline_rels") or ({"": rel} if rel is not None
                                              else {})
        # one-click resume from the LIVE root's record (never the seal's)
        resume_fields = None
        if status in ("stopped", "interrupted"):
            resume_fields = _retro.resume_form_fields(
                _retro.read_meta(_live_root(s)))
        seasons.append({"name": s, "total": total, "done": done,
                        "seal": is_seal,
                        "seal_label": _sealed_label(root) if is_seal else "",
                        "rel": rel, "rels": rels,
                        # sealed records store the bare filter under pf
                        "pf_name": _pf_name(root),
                        "resume_fields": resume_fields,
                        "settings": prog["settings"],
                        "archives": retro_seasons._archive_entries(s),
                        "status": status,
                        "running": status in ("running", "stopping"),
                        "paused": status == "paused",
                        "active": status in _RETRO_ACTIVE,
                        "elapsed_s": prog["elapsed_s"],
                        "mean_s": prog["mean_s"],
                        "weeks_measured": prog["weeks_measured"],
                        "eta_s": prog["eta_s"],
                        "finished_utc": prog["finished_utc"],
                        "scored": (root / "scores.json").exists()})
    from flubnf.settings import PY_ENGINE, PYBNF
    from app.core.engines.pf import DEFAULT_SHARD_WIDTH, SHARD_WIDTH_CAP
    return templates.TemplateResponse(request, "retro.html",
                                      {"active": "Retrospective",
                                       "own_tab": False, "seasons": seasons,
                                       "state_names": _retro_state_names(),
                                       "default_width": DEFAULT_SHARD_WIDTH,
                                       "width_cap": SHARD_WIDTH_CAP,
                                       "knob_panel": _knob_panel("retro"),
                                       "engine_ok": PY_ENGINE.exists()
                                       and PYBNF.exists()})


@router.get("/api/retro/progress")
def api_retro_progress(season: str = ""):
    """Live retro progress for the tickers: one season, or every season
    with a record or claim (polled, so a guard modal is not wiped)."""
    from app.core.retro import available_seasons
    if season:
        if not _valid_season(season):
            return {}
        return {season: retro_seasons._retro_progress(season)}
    out = {}
    for s in available_seasons():
        p = retro_seasons._retro_progress(s)
        if p["status"] or p["done"]:
            out[s] = p
    return out


@router.get("/api/retro/startover")
def api_retro_startover(season: str = ""):
    """What pressing Run on this season would do, from the LIVE root only.

    weeks == 0: Run starts with no prompt. Exception: an empty live tree
    under a shown SEALED run returns sealed=True with the sealed weeks, so
    the client prompts (choices: cancel or a fresh replay)."""
    from app.core import retro
    from app.core.retro import season_vintages
    if not _valid_season(season):
        return {"season": season, "weeks": 0, "total": 0, "complete": False,
                "elapsed_s": None, "elapsed_hms": "", "finished": "",
                "status": "", "active": False, "archives": 0,
                "sealed": False}
    root = _live_root(season)
    s = retro.run_summary(root)
    total = len(season_vintages(season))
    status = _season_status(season)
    sealed = False
    if not s["weeks"]:
        shown_root, is_seal = retro_seasons._season_root(season)
        if is_seal and retro_seasons._weeks_done(shown_root):
            sealed = True
            s = retro.run_summary(shown_root)
    return {"season": season,
            "sealed": sealed,
            "weeks": s["weeks"],
            "total": total,
            "complete": bool(total and s["weeks"] >= total),
            "elapsed_s": s["elapsed_s"],
            # blank rather than a fabricated 0:00:00
            "elapsed_hms": (fmt_hms(s["elapsed_s"])
                            if s["elapsed_s"] and s["elapsed_s"] >= 1.0
                            else ""),
            "finished": retro.utc_human(s["finished_utc"]
                                        or s["started_utc"]),
            "status": status,
            "active": status in _RETRO_ACTIVE,
            "archives": len(retro_seasons._archive_entries(season))}


@router.post("/retro/{season}/archive/{stamp}/delete")
def retro_archive_delete(request: Request, season: str, stamp: str,
                         confirm: str = Form("")):
    """Delete one archived run permanently: well-formed ids, season not
    replaying, confirmation names the season. The live season is never
    touched."""
    from app.core import retro
    _invalidate_scans()
    if not _valid_season(season) or not _valid_archive(stamp):
        _flash("Unrecognized season or archive identifier. Nothing was "
               "deleted.")
        return _back(request, "/retro")
    if _season_status(season) in _RETRO_ACTIVE:
        _flash(f"{season} is replaying. Stop it first; nothing was deleted.")
        return _back(request, "/retro")
    if confirm != season:
        _flash("The deletion was not confirmed, so nothing was deleted.")
        return _back(request, "/retro")
    p = retro.archive_dir(retro_seasons.RETRO_ROOT, season, stamp)
    if not (p.is_dir() or p.is_symlink()):
        _flash(f"No archived {season} run from {retro.stamp_human(stamp)}. "
               "Nothing was deleted.")
        return _back(request, "/retro")
    weeks = retro.run_summary(p)["weeks"]
    size_h = retro.human_bytes(retro.dir_size(p))
    try:
        retro.delete_tree(p)
    except Exception as e:
        _flash(f"Could not delete the archived {season} run: "
               f"{type(e).__name__}: {str(e)[:160]}. Nothing else changed.")
        return _back(request, "/retro")
    _flash(f"Deleted the archived {season} run from "
           f"{retro.stamp_human(stamp)}: {weeks} completed week"
           f"{'' if weeks == 1 else 's'}, {size_h} freed. The live "
           f"{season} season was not touched.")
    return _back(request, "/retro")


# === Retrospective: results status (preparation: retro_prep.py) ===
#: grace wait before the results route renders the preparing state (small
#: seasons and test trees finish inside it)
_RESULTS_GRACE_S = 1.5


@router.get("/api/retro/{season}/results_status")
def api_retro_results_status(season: str, archive: str = ""):
    """The preparing state's poll: is the finalize job still working, and in
    which phase. Never starts work (the results page does)."""
    if archive and not (_valid_season(season) and _valid_archive(archive)):
        return {"pending": False, "error": "unrecognized archive"}
    if not _valid_season(season):
        return {"pending": False, "error": "unrecognized season"}
    root, _is_seal = retro_seasons._season_root(season, archive)
    job = _results_jobs.get(str(root))
    if job and not job["done"].is_set():
        return {"pending": True, "phase": job["phase"],
                "elapsed_s": round(time.time() - job["t0"], 1)}
    return {"pending": False, "error": (job or {}).get("error", "")}


# === Retrospective: season worker and run controls ===
def _retro_bg(season: str, locations: list, width: int,
              replicates: int = 3, particles: int = 10_000,
              settings: dict | None = None, engine: str = "pf",
              week_extra=None, drop_same_day: bool = False):
    """The season worker. `settings` is the form's choices (scope label,
    engine preset); run_season records them with the rest in run_meta.json
    before the first week."""
    from app.core import retro
    root = retro_seasons.RETRO_ROOT / season
    _retro_status[season] = "running"
    _retro_stop.discard(season)     # no stale stop flag from a past run
    retro.clear_flags(root)         # nor a stale STOP/PAUSE file from one
    guard = pipeline._sleep_guard()  # overnight replays must outlive the lid
    try:
        def _tick(_asof):
            # called after every week: the clean stop point
            if season in _retro_stop:
                raise _RetroStopRequested()
        # model knobs ride in week_extra and settings (None/False/absent
        # on a shipped replay: the call is as it always was)
        kx = {}
        if week_extra is not None:
            kx["week_extra"] = week_extra
        if drop_same_day:
            kx["drop_same_day"] = True
        retro.run_season(root, season, locations, replicates=replicates,
                         particles=particles, width=width, progress=_tick,
                         settings=settings, engine=engine, **kx)
        # finalize (score, national aggregate, playback caches) BEFORE the
        # season reads done, via the shared job registry
        job = retro_prep._ensure_results_job(root, season)
        job["done"].wait()
        if job.get("seconds"):
            retro.record_finalize(root, job["seconds"])
        if job["error"]:
            _retro_status[season] = f"error: {job['error'][:150]}"
        else:
            _retro_status[season] = "done"
    except (_RetroStopRequested, retro.SeasonStopped):
        # completed weeks stay; the results page scores whatever exists
        _retro_status[season] = "stopped"
    except Exception as e:
        _retro_status[season] = f"error: {str(e)[:150]}"
    finally:
        _retro_stop.discard(season)
        _invalidate_scans()
        # flags are requests: a leftover one would stop the NEXT replay
        retro.clear_flags(root)
        if guard is not None:
            try:
                guard.terminate()
            except Exception:
                pass


@router.post("/retro/stop")
def retro_stop():
    """Stop every live replay after the fits in flight (polled between fits).
    Finished fits are kept and a restart resumes there. Paused seasons stop
    too (request_stop clears the pause)."""
    from app.core import retro
    _invalidate_scans()
    stopping = []
    for season, st in list(_retro_status.items()):
        if st != "running" and _season_status(season) not in ("running",
                                                              "paused"):
            continue
        _retro_stop.add(season)
        _retro_status[season] = "stopping"
        stopping.append(season)
        retro.request_stop(_live_root(season))
    if stopping:
        _flash("Stopping " + ", ".join(sorted(stopping)) + " after the "
               "fits now in flight. Completed weeks and finished fits are "
               "kept; the replay resumes from there next time.")
    return RedirectResponse("/retro", status_code=303)


@router.post("/retro/{season}/stop")
def retro_season_stop(request: Request, season: str):
    """Stop ONE season after the fits in flight. Finished fits are
    checkpointed and a half-week never writes samples.json."""
    from app.core import retro
    _invalidate_scans()
    if not _valid_season(season):
        _flash("Unrecognized season name. Nothing was stopped.")
        return _back(request, "/retro")
    if _season_status(season) not in _RETRO_ACTIVE:
        _flash(f"{season} is not replaying, so there was nothing to stop.")
        return _back(request, "/retro")
    retro.request_stop(_live_root(season))
    _retro_stop.add(season)
    if _season_status(season) in ("running", "paused"):
        _retro_status[season] = "stopping"
        _flash(f"Stopping {season} after the fits now in flight. Completed "
               "weeks and finished fits are kept; Run resumes from there.")
    else:
        # not replaying: resolve now, never leave an orphan "stopping" claim
        _retro_status[season] = "stopped"
        _retro_stop.discard(season)
        _flash(f"{season} was not replaying; it is marked stopped and Run "
               "will start it fresh or resume it.")
    return _back(request, "/retro")


@router.post("/retro/{season}/pause")
def retro_season_pause(request: Request, season: str):
    """Hold after the fits in flight (polled between fits). The worker and
    its sleep guard stay alive."""
    from app.core import retro
    _invalidate_scans()
    if not _valid_season(season):
        _flash("Unrecognized season name. Nothing was paused.")
        return _back(request, "/retro")
    if _season_status(season) not in ("running", "paused"):
        _flash(f"{season} is not replaying, so there was nothing to pause.")
        return _back(request, "/retro")
    retro.request_pause(_live_root(season))
    _flash(f"Pausing {season} after the fits now in flight. The replay "
           "holds; Resume continues it.")
    return _back(request, "/retro")


@router.post("/retro/{season}/resume")
def retro_season_resume(request: Request, season: str):
    """Release a hold; the elapsed clock resumes, not restarts."""
    from app.core import retro
    _invalidate_scans()
    if not _valid_season(season):
        _flash("Unrecognized season name. Nothing was resumed.")
        return _back(request, "/retro")
    retro.clear_pause(_live_root(season))
    _flash(f"Resuming {season}.")
    return _back(request, "/retro")


@router.post("/retro/run")
def retro_run(background: BackgroundTasks, season: str = Form(...),
              locations: str = Form("panel6"),
              custom_locations: list = Form([]),
              national: str = Form("1"),
              particles: int = Form(10_000),
              replicates: int = Form(3),
              width: int = Form(4),
              engine: str = Form("pf"),
              mode: str = Form("resume"),
              confirm: str = Form(""),
              # the Model settings panel: knob.<key> fields, or the JSON
              # record a one-click resume posts; the same-day week's knob
              drop_same_day: str = Form(""),
              knobs: str = Form(""),
              knob_fields: dict = Depends(_knob_form)):
    """Start (or resume) a season replay.

    `national`: fit US too (default, like the Forecast tab); "0" = states
    only (a resumed 52-jurisdiction run posts its recorded answer).

    `mode`, the only way an existing season tree is moved or removed:

      resume   completed weeks are kept and skipped
      archive  move the current tree to a timestamped sibling, then run clean
      discard  delete the current tree (confirmation required), then run clean
    """
    from app.core import retro
    from app.core.retro import available_seasons
    _invalidate_scans()
    if not _valid_season(season):
        _flash("Unrecognized season name. Nothing was started.")
        return RedirectResponse("/retro", status_code=303)
    # busy checks, the archive/discard move and the claim all run under
    # _engine_lock (the move is part of claiming the tree); the worker does not
    with _engine_lock:
        if _season_status(season) in _RETRO_ACTIVE:
            _flash(f"{season} is already replaying (status: "
                   f"{_season_status(season)}). One season worker runs at a "
                   "time; stop it first if you want to start over.")
            return RedirectResponse("/retro", status_code=303)
        # server-side mirror of /api/busy (see _engine_lock)
        if _status.get("running"):
            _flash("A console run holds the engine ("
                   + (_status.get("run_label") or str(_status.get("running")))
                   + "). Stop it from the Forecast tab first; nothing was "
                   "started.")
            return RedirectResponse("/retro", status_code=303)
        sb = _sandbox_live_reason()
        if sb:
            _flash(f"Not started: {sb}. Stop it from the Sandbox first.")
            return RedirectResponse("/retro", status_code=303)
        other = sorted(x for x in retro_seasons._known_seasons()
                       if x != season and _season_status(x) in _RETRO_ACTIVE)
        if other:
            _flash("Another season is already replaying ("
                   + ", ".join(other) + "). One season worker runs at a time; "
                   "stop it first. Nothing was started.")
            return RedirectResponse("/retro", status_code=303)
        if mode not in ("resume", "archive", "discard"):
            _flash(f"'{mode}' is not one of resume, archive, or discard. "
                   "Nothing was started and nothing was changed.")
            return RedirectResponse("/retro", status_code=303)
        if season not in available_seasons():
            _flash(f"Season {season} is not available. A season appears once "
                   "its vintage archive exists.")
            return RedirectResponse("/retro", status_code=303)
        if engine not in retro.ENGINES:
            # a future pf2s preset: accept it here, pass {"variant": "2strain"}
            # through retro.run_week's RunSpec, collect it beside pf
            _flash("The engine presets for a retrospective are the Oracle "
                   "SIHRS and the Groundhog, or the Groundhog alone.")
            return RedirectResponse("/retro", status_code=303)
        from app.core import us_national as usn
        all_states = _retro_state_names()
        if locations == "all":
            names = list(all_states)
        elif locations == "custom":
            # a resumed run resubmits its list verbatim, US included
            names = [n for n in custom_locations
                     if n in set(all_states) or usn.is_us(n)]
            if not names:
                _flash("Custom scope selected but no locations were checked. "
                       "Check at least one state and try again.")
                return RedirectResponse("/retro", status_code=303)
        else:
            names = ["Alaska", "New York", "Wyoming", "Pennsylvania",
                     "Vermont", "California"]
        # US rides on every scope unless states only (with_us is idempotent)
        fit_national = str(national).strip().lower() not in ("0", "false",
                                                             "no", "off", "")
        if fit_national:
            names = usn.with_us(names, _retro_national_name())
        # model settings (app/core/knobs.py), validated like every other
        # field before anything is moved or claimed: particles and
        # replicates are knobs now, refused out of range, never clamped
        try:
            vints = retro.season_vintages(season)
            nd = _knobs.resolve(
                _knob_raw(knob_fields, knobs),
                "analogue" if engine == "analogue" else "all",
                scope="retro",
                forecast_date=(vints[0] if vints else None),
                check_dates=tuple(vints[-1:]),
                legacy={"particles": particles, "replicates": replicates,
                        **({"drop_same_day": drop_same_day}
                           if _str_field(drop_same_day).strip() else {})})
        except ValueError as e:              # KnobError is a ValueError
            _flash(f"Model settings: {e}. Nothing was started.")
            return RedirectResponse("/retro", status_code=303)
        particles = int(nd.get("pf.particles", RunSpec.particles))
        replicates = int(nd.get("pf.replicates", RunSpec.replicates))
        width = max(1, min(int(width), 16))
        # start-over handling only AFTER all validation
        live = _live_root(season)
        existing = retro_seasons._weeks_done(live)
        legacy_resume = False
        if mode == "resume" and existing:
            # one configuration per tree: completed weeks were built with
            # the recorded model settings (a pre-registry record: its
            # particles and replicates); a different set starts over
            prior = (retro.read_meta(live) or {}).get("settings") or {}
            had = _knobs.legacy_settings_knobs(prior)
            # a pre-registry tree resumes as it was, never re-recorded
            legacy_resume = bool(prior) and "knobs" not in prior
            if _knobs.digest(had) != _knobs.digest(_knobs.jsonable(nd)):
                _flash(f"{season} has {existing} completed week"
                       f"{'' if existing == 1 else 's'} replayed with model "
                       f"settings {_knobs.label(_knobs.from_record(had))}; "
                       f"this run asks for {_knobs.label(nd)}. Resuming "
                       "would mix two configurations in one season. Archive "
                       "or discard the existing results to run it. Nothing "
                       "was started.")
                return RedirectResponse("/retro", status_code=303)
            # never resume a tree with the other engine preset (weeks would be
            # skipped as done or mislabeled); the record says what ran
            was = str((retro.read_meta(live) or {}).get("settings", {})
                      .get("engine") or "pf")
            if was != engine:
                _flash(f"{season} has {existing} completed week"
                       f"{'' if existing == 1 else 's'} replayed with the "
                       f"{retro_engine_label(was)} preset; the "
                       f"{retro_engine_label(engine)} preset cannot resume "
                       "them. Archive or discard the existing results to "
                       "run it. Nothing was started.")
                return RedirectResponse("/retro", status_code=303)
            # nor with another location scope (the rule lives in
            # retro.run_season, so the CLI refuses it too; checked here
            # first so the refusal comes before anything is claimed)
            change = retro.location_scope_change(
                (retro.read_meta(live) or {}).get("settings", {})
                .get("locations"), names)
            if change:
                _flash(f"{season} has {existing} completed week"
                       f"{'' if existing == 1 else 's'} {change}. "
                       "Resuming would mix two location scopes in one "
                       "season. Archive or discard the existing results to "
                       "run it. Nothing was started.")
                return RedirectResponse("/retro", status_code=303)
        if mode == "discard":
            if confirm != season:
                _flash(f"Discarding {season} was not confirmed, so nothing "
                       "was deleted and nothing was started.")
                return RedirectResponse("/retro", status_code=303)
            if existing:
                try:
                    retro.delete_tree(live)
                except Exception as e:
                    _flash(f"Could not delete the {season} results: "
                           f"{type(e).__name__}: {str(e)[:160]}. Nothing was "
                           "started; the existing results are intact.")
                    return RedirectResponse("/retro", status_code=303)
                _flash(f"Discarded {existing} completed week"
                       f"{'' if existing == 1 else 's'} of {season}. Starting "
                       "a fresh replay.")
        elif mode == "archive" and existing:
            try:
                dst = retro.archive_run(retro_seasons.RETRO_ROOT, season)
            except Exception as e:
                # the move is atomic: a failure leaves the original whole
                _flash(f"Could not archive {season}: {type(e).__name__}: "
                       f"{str(e)[:160]}. Nothing was started; the existing "
                       "results are intact.")
                return RedirectResponse("/retro", status_code=303)
            _flash(f"Archived {existing} completed week"
                   f"{'' if existing == 1 else 's'} of {season} as "
                   f"{dst.name}; it stays viewable from the season list. "
                   "Starting a fresh replay.")
        # claim in the request (not the task) so double submits cannot race
        _invalidate_scans()
        _retro_status[season] = "running"
        _retro_claim_at[season] = time.time()
    # recorded settings the location list alone cannot say
    rsettings = {"scope": locations, "engine": engine,
                 "national": bool(fit_national)}
    wx = None
    if nd:
        # run_season records the knobs; those that travel in each week's
        # extra (not particles, replicates, same-day) ride in week_extra
        if not legacy_resume:
            rsettings["knobs"] = _knobs.jsonable(nd)
        if set(nd) - _knobs.RETRO_ARG_KEYS:
            from app.core.engines import analogue as _an
            pick = _knobs.aux_choice(nd, _an.SHIPPED_AUX)
            base = _an.aux_preset(pick) if pick else _an.bare_analogue
            wx = _knobs.retro_week_extra(base, nd)
    # knob keywords only when set: a shipped replay's call is as before
    kx = {}
    if wx is not None:
        kx["week_extra"] = wx
    if nd.get("run.drop_same_day"):
        kx["drop_same_day"] = True
    background.add_task(_retro_bg, season, names, width, replicates, particles,
                        rsettings, engine, **kx)
    return RedirectResponse("/retro", status_code=303)


#: the retrospective engine presets as the form and the record name them
RETRO_ENGINE_LABELS = {"pf": "Oracle SIHRS and the Groundhog",
                       "analogue": "Groundhog only"}


def retro_engine_label(engine: str) -> str:
    return RETRO_ENGINE_LABELS.get(str(engine), str(engine))


# === Retrospective season page (/retro/{season}) and its APIs -> retro_season.html ===
@router.get("/retro/{season}", response_class=HTMLResponse)
def retro_results(request: Request, season: str, week: str = "",
                  archive: str = "", conv: str = ""):
    """The season results page; `archive` selects an archived run's tree.
    `conv` picks the ONE relWIS convention (app/core/relwis) for the whole
    page: ratio of sums (default) or the CDC's pairwise figure, never mixed;
    panels it cannot express say so."""
    import pandas as pd
    from app.core import relwis
    from app.core import retro
    if archive and not (_valid_season(season) and _valid_archive(archive)):
        _flash("Unrecognized archived run identifier.")
        return RedirectResponse("/retro", status_code=303)
    root, _is_seal = retro_seasons._season_root(season, archive)
    # this tree's names, passed as model_name (shadows the global)
    names = _names_for_root(root)
    # a replay with modified model settings wears its label on the page
    from app.core import site_build as _sb
    _kn = _sb.tree_knobs(root)
    knobs_label = (_knobs.label(_knobs.from_record(_kn)) if _kn else "")
    weeks = [p.parent.name for p in retro.season_sample_files(root)]
    if not weeks:
        # back to the season list, which shows a 0-weeks season
        _flash(f"{season}: no completed weeks yet. Start the replay and "
               "check back shortly." if not archive else
               f"{season}: that archived run has no completed weeks, or it "
               "has been deleted.")
        return RedirectResponse("/retro", status_code=303)
    score_error = ""
    # Heavy scoring never runs in-request: stale caches or ?rescore=1 start
    # the background finalize job and the page shows a polled preparing
    # state (after a short grace wait). A job covering these exact inputs is
    # believed, so an unsettled-truth season never loops.
    if ((request.query_params.get("rescore") and not _is_sealed_root(root))
            or _results_pending(root)):
        job = retro_prep._ensure_results_job(
            root, season, force=bool(request.query_params.get("rescore")))
        job["done"].wait(_RESULTS_GRACE_S)
        if not job["done"].is_set():
            return templates.TemplateResponse(request, "retro_season.html", {
                "active": "Retrospective", "season": season,
                "model_name": _name_fn(names), "knobs_label": knobs_label,
                "preparing": {"phase": job["phase"],
                              "elapsed_s": round(time.time() - job["t0"], 1)},
                "archive": archive,
                "archive_when": retro.stamp_human(archive) if archive else "",
                "heads": {}, "curve": [], "curves": {}, "states": [],
                "season_models": [], "member_colors": _member_colors(),
                "us_row": None,
                "us": None, "pooled_note": "",
                "conv": relwis.DEFAULT_CONVENTION, "figs": None,
                "weeks": weeks, "week": weeks[-1], "map_html": "",
                "official_catalog": [], "prog": None, "n_weeks": 0})
        if job["error"]:
            # show the failure, never pass it off as "truth not settled"
            score_error = job["error"]
    else:
        covered = _job_covered(root)
        if covered and covered.get("error") and not _scores_scoreable_fast(root):
            score_error = covered["error"]
    from app.core import us_national as usn
    df_all = _scores_df(root)
    if df_all is None:
        df_all = pd.DataFrame()
    # THE pooled gate: every figure below uses the 52-jurisdiction frame; the
    # national row is resolved separately, so fitting US never moves the headline
    df = usn.pooled_frame(df_all)
    heads, curve, states = {}, [], []
    curves: dict = {}
    scoreable = (not df.empty) and ("model" in df.columns)
    # THE convention gate: one figures object for tiles and table; with no
    # numbers (pairwise without field data) the page says why, never falls back
    convention = relwis.convention_of(conv)
    figs = _relwis_figures(root, convention) if scoreable else None
    # a season scored before 2026-09-22 also carries the retired blend's
    # rows; they are read (scoring stays whole) but never shown
    from app.core.report_v2 import RETIRED_MODELS
    if figs is not None and figs.available:
        heads = {m: v for m, v in figs.values.items()
                 if m not in RETIRED_MODELS}
        states = list(figs.states)
    if scoreable and convention == relwis.RATIO_OF_SUMS:
        # the cumulative curve is a running ratio of sums: this convention only
        asofs = sorted(df["asof"].unique())
        # one line per shipped model in the frame (relwis.MODELS order)
        for m in relwis.MODELS:
            if m in RETIRED_MODELS:
                continue
            g = df[df.model == m]
            if not len(g):
                continue
            cum = g.groupby("asof")[["wis", "base_wis"]].sum() \
                   .sort_index().cumsum()
            cum = cum.reindex(asofs).ffill().dropna()
            curves[m] = [(str(a)[:10], r.wis / r.base_wis)
                         for a, r in cum.iterrows()]
        curve = curves.get("pf") or next(iter(curves.values()), [])
    # national series via usn.resolve (fitted > constructed > officials), with
    # its provenance label printed; a failure never costs the page
    us = None
    if scoreable:
        try:
            us = usn.resolve(root, df_all)
        except Exception:
            us = None
    # us_row (member -> relWIS plus provenance) is a ratio of sums, so it is
    # offered to that convention only; `us` resolves either way for the player
    us_row = (us.as_dict() if (us is not None and us.has_scores
                               and convention == relwis.RATIO_OF_SUMS)
              else None)
    wk = week if week in weeks else weeks[-1]
    from app.core.usmap import svg_map
    locs = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
    n2a = dict(zip(locs.location_name, locs.abbreviation))
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    by_model = _week_map_cards_by_model(root, wk)
    map_models = _retro_map_models(by_model)
    cards = dict(by_model[map_models[0]]) if map_models else {}
    for name, abbr in n2a.items():
        cards.setdefault(n2f.get(name, name), {"name": name, "abbr": abbr,
                                               "fips": n2f.get(name, "")})
    # model switch (home's control) when the week stored >= 2 models
    map_toggle = ""
    if len(map_models) >= 2:
        from app.core import report_v2
        from app.core import usmap as _usmap
        # report_v2.MODEL_LABEL, with pf's following this tree's name
        map_labels = dict(report_v2.MODEL_LABEL)
        map_short = dict(report_v2.MODEL_SHORT)
        if names.get("pf") != templating._model_names().get("pf"):
            map_labels["pf"] = f"{names['pf']} {report_v2.CAT_FORECAST}"
            map_short["pf"] = names["pf"]
        map_toggle = _usmap.model_toggle(
            map_models, map_labels, map_models[0],
            {m: {"states": _usmap.state_swap_payload(by_model[m]), "us": {}}
             for m in map_models},
            group_id="retro-model", btn_class="quiet",
            active_class="gold", wrap_class="row viewtabs",
            short_labels=map_short)
    map_html = map_toggle + svg_map(cards)
    if not scoreable and not score_error:
        # scored zero cells with no exception: diagnose WHICH input is empty
        try:
            from app.core.scoring import load_truth as _lt
            truth_d, n2f_d = _lt()
            d0 = retro.read_week_samples(root, weeks[len(weeks)//2])
            import numpy as _dn
            pos_med = sum(1 for loc, sm in d0.get("pf", {}).items()
                          for h in ("1",)
                          if _dn.median(_dn.asarray(sm[h], float)) > 0)
            # walk ONE cell through every scoring step and name its killer
            import pandas as _dp
            from app.core import ensemble as _de
            from app.core.scoring import _baseline_cells as _dbc
            from flubnf.wis import wis as _dwis
            loc0 = sorted(d0.get("pf", {}))[0]
            fips0 = n2f_d.get(loc0)
            T0 = _dp.Timestamp(d0["asof"])
            q0 = _de.member_quantiles_from_samples(d0["pf"][loc0]).get("0", {})
            act = truth_d.get((fips0, T0 + _dp.Timedelta(days=7)))
            med = q0.get(0.5, "KEY-MISSING")
            try:
                wv = float(_dwis(q0, act).wis) if act else "skipped"
            except Exception as we:
                wv = f"WIS-THREW {type(we).__name__}: {str(we)[:90]}"
            try:
                bb = _dbc(d0["asof"], {fips0}, truth_d)
                bv = bb.get((fips0, d0["asof"], 0), "BASELINE-MISSING")
            except Exception as be:
                bv = f"BASELINE-THREW {type(be).__name__}: {str(be)[:90]}"
            probe = (f"probe cell {loc0} asof {d0['asof']} h1: actual={act}, "
                     f"median={med}, wis={wv}, baseline={bv}; truth rows "
                     f"{len(truth_d)}, positive-median locs {pos_med}, "
                     f"weeks {len(weeks)}")
            # zero cells is benign only when truth has not settled: only then
            # the calm "No scoreable weeks yet" text. Probe the earliest week
            # too (its truth may have settled while the middle week's has not).
            d_first = retro.read_week_samples(root, weeks[0])
            Tf = _dp.Timestamp(d_first["asof"])
            have_truth = sum(
                1 for dd, TT in ((d0, T0), (d_first, Tf))
                for loc in dd.get("pf", {})
                if truth_d.get((n2f_d.get(loc),
                                TT + _dp.Timedelta(days=7))) is not None)
        except Exception as pe:
            probe = f"diagnostic probe failed: {type(pe).__name__}: {str(pe)[:120]}"
            have_truth = -1      # unknown: surface the probe, never the calm text
        if have_truth != 0:
            score_error = "scored zero cells with no exception. " + probe
    if not scoreable and score_error:
        map_html = _scoring_failed_hint(score_error)
    elif not scoreable:
        map_html = ("<p class='hint'>No scoreable weeks yet. Truth for "
                    "these forecast dates has not settled, so relWIS arrives "
                    "later; the weekly maps below are available now.</p>") + map_html
    # comparators that submitted at least once this season (player toggles)
    from app.core import playback as _playback
    try:
        official_catalog = _playback.season_official_catalog(root)
    except Exception:
        official_catalog = []
    return templates.TemplateResponse(request, "retro_season.html", {
        "active": "Retrospective", "season": season, "heads": heads,
        "model_name": _name_fn(names), "knobs_label": knobs_label,
        "curve": curve, "curves": curves, "states": states,
        "member_colors": _member_colors(),
        # the shipped models this season scored, in table order
        "season_models": [m for m in relwis.MODELS
                          if m not in RETIRED_MODELS
                          and (m in heads or m in curves
                          or any((r.get(m) if isinstance(r, dict)
                                  else getattr(r, m, None))
                                 for r in states))],
        "us_row": us_row,
        # provenance travels WITH the numbers (fitted vs constructed)
        "us": (us.as_dict() if us is not None
               else usn.UsNational(usn.OFFICIALS_ONLY).as_dict()),
        "pooled_note": usn.POOLED_SCOPE_NOTE,
        "conv": convention, "figs": figs,
        "weeks": weeks, "week": wk, "map_html": map_html,
        "official_catalog": official_catalog,
        "prog": (_archive_progress(root, season) if archive
                 else retro_seasons._retro_progress(season)),
        "archive": archive,
        "archive_when": retro.stamp_human(archive) if archive else "",
        "n_weeks": len(weeks) if scoreable else 0})


@router.get("/api/retro/{season}/playback/{asof}")
def api_retro_playback(season: str, asof: str, archive: str = ""):
    """One stored retro week as a playback payload (member fans, settled
    truth, CDC comparators, running relWIS), cached under
    <season_root>/playback_cache/. `archive` reads an archived run."""
    from fastapi.responses import PlainTextResponse
    from app.core import playback
    if archive and not (_valid_season(season) and _valid_archive(archive)):
        return PlainTextResponse("unrecognized archived run identifier",
                                 status_code=404)
    root, _is_seal = retro_seasons._season_root(season, archive)
    try:
        return playback.build_week(root, season, asof)
    except playback.UnknownWeek as e:
        return PlainTextResponse(str(e), status_code=404)


@router.get("/api/retro/{season}/mapswap/{asof}")
def api_retro_mapswap(season: str, asof: str, archive: str = ""):
    """One stored week's map as a swap payload (fips -> fill, opacity,
    hover) from the cached cards: the player renders the SVG once and
    swaps fills per frame."""
    from fastapi.responses import PlainTextResponse
    from app.core.usmap import state_swap_payload
    if archive and not (_valid_season(season) and _valid_archive(archive)):
        return PlainTextResponse("unrecognized archived run identifier",
                                 status_code=404)
    # the week is a path segment: date-shaped only
    import re as _re
    if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", asof):
        return PlainTextResponse(f"no stored week {asof}", status_code=404)
    root, _is_seal = retro_seasons._season_root(season, archive)
    from app.core import retro as _retro
    if _retro.week_samples_path(root, asof) is None:
        return PlainTextResponse(f"no stored week {asof}", status_code=404)
    by_model = _week_map_cards_by_model(root, asof)
    order = _retro_map_models(by_model)
    models = {m: {"states": state_swap_payload(by_model[m])} for m in order}
    default = order[0] if order else ""
    # `states`: the default model's (the pre-per-model shape)
    return {"default": default, "models": models,
            "states": (models[default]["states"] if default
                       else state_swap_payload({}))}


@router.get("/retro/{season}/report")
def retro_season_report(season: str, archive: str = ""):
    """Build (cached by mtime) and download the self-contained season report
    (player plus every week's data, one HTML file); `archive` = that run's."""
    from fastapi.responses import FileResponse, PlainTextResponse
    from app.core import playback, report_season
    if archive and not (_valid_season(season) and _valid_archive(archive)):
        return PlainTextResponse("unrecognized archived run identifier",
                                 status_code=404)
    root, _is_seal = retro_seasons._season_root(season, archive)
    try:
        p = report_season.build_season_report(
            root, season, archive=archive,
            build=RUNNING_SHA, versions=VERSIONS)
    except playback.UnknownWeek as e:
        return PlainTextResponse(str(e), status_code=404)
    return FileResponse(p, filename=p.name, media_type="text/html",
                        content_disposition_type="attachment")


@router.get("/api/retro/{season}/report_path")
def api_retro_report_path(season: str, archive: str = ""):
    """Build the season report if absent and return its path (the results
    page's Reveal button posts it to /output/reveal)."""
    from fastapi.responses import PlainTextResponse
    from app.core import playback, report_season
    if archive and not (_valid_season(season) and _valid_archive(archive)):
        return PlainTextResponse("unrecognized archived run identifier",
                                 status_code=404)
    root, _is_seal = retro_seasons._season_root(season, archive)
    try:
        p = report_season.build_season_report(
            root, season, archive=archive,
            build=RUNNING_SHA, versions=VERSIONS)
    except playback.UnknownWeek as e:
        return PlainTextResponse(str(e), status_code=404)
    return {"path": str(p)}
