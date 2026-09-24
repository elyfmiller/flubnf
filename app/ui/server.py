"""FastAPI operations console: the app, assembled from the tab routers, and
the Forecast, run-page and Retrospective routes.

Server-rendered (locked decision: FastAPI + templates, no build chain).
Run:  .venv/bin/uvicorn app.ui.server:app --port 8710

Support modules beside this one (app/ui), read by the tabs:

  state.py            REPO, startup trace, ENGINES, _status, _last_form,
                      _engine_lock, the data_mod proxy, the sandbox claim
  versions.py         build SHA, restart banner, component versions
  templating.py       templates (the one Jinja env) and its globals, model
                      names and colors, season month axis
  shared.py           CSRF guard, request helpers, cached scans, run
                      labels, outcome chips, latest results, sandbox claim
                      readers
  forms.py            the model-settings (knob) form channel, anchor dates
  retro_seasons.py    retro roots and claims, the season registry and
                      status, completed weeks, live progress and ETA
  retro_prep.py       season results preparation (finalize jobs), scores
                      and relWIS caches, week map cards
  pipeline.py         the forecast pipeline _run_all, sleep guard, weekly
                      report, forecast archive

Tab modules (app/ui/routes), each an APIRouter included by the Bootstrap
section below, in this order and ahead of the routes in this module
(templates under app/ui/templates):

  shell.py            GET /api/versions, /favicon.ico, /api/busy
  home.py             GET /, GET /api/outlook-ready            home.html
  data.py             GET /data, POST /data/pull, POST /freshness
                                                               data.html
  storage.py          GET /storage (= /runs), POST /runs/clear,
                      /storage/delete, /storage/clear-workroots,
                      GET /api/storage/reclaim, POST /storage/reclaim
                                                               runs.html
  output.py           submission files; GET /output, /output/download,
                      POST /output/reveal, GET /output/report,
                      /output/report/download                  output.html
  sandbox.py          GET /sandbox, POST /sandbox/*, GET /api/sandbox/*,
                      GET /sandbox/models|runs/{id}/download; the sandbox
                      engine guard (middleware)                sandbox.html
  models.py           GET /models, /model/{name}               model.html
  methods.py          GET /methods                             methods.html

Contents, in file order (each section starts with a `# === ... ===` banner):

  Bootstrap           app, /static, the middleware (the CSRF guard, then
                      the sandbox engine guard around it), the tab routers,
                      the sandbox_storage global
  Startup warm        _start_background_warm (started last, below)
  Forecast            GET /forecast                            forecast.html
  Console controls    POST /run/stop
  Run pages           GET /runs/{id}, /report, /report/download,
                      POST /runs/{id}/rerun                    run.html
  Forecast APIs       GET /api/series, GET /api/progress
  Retrospective       the season worker's stop signal
                      GET /retro, /api/retro/progress, /api/retro/startover,
                      POST /retro/{s}/archive/{stamp}/delete   retro.html
                      GET /api/retro/{s}/results_status
                      worker _retro_bg, POST /retro/stop, /retro/{s}/stop,
                      /pause, /resume, POST /retro/run
                      GET /retro/{s}, /api/retro/{s}/playback/{asof},
                      /mapswap/{asof}, /retro/{s}/report,
                      /api/retro/{s}/report_path           retro_season.html
  Forecast            POST /run (form and rerun entry to _run_all)
  Custom datasets     app/ui/datasets_ui.py's router: POST /data/datasets,
                      /data/datasets/check, /data/datasets/{id}/delete,
                      /run/dataset, /retro/dataset/run; GET
                      /retro/dataset/{id}/{stamp}; Data, Forecast and
                      /api/series take ?source=<id>, /retro ?dataset=<id>
  Startup warm        _start_background_warm() at import
"""
from __future__ import annotations

import time
import sys
from pathlib import Path

from app.ui import state

sys.path.insert(0, str(state.REPO))
state._trace("import begin (fastapi + app.core next)")

from fastapi import (BackgroundTasks, Depends, FastAPI, Form,  # noqa: E402
                     Request)
from fastapi.responses import HTMLResponse, RedirectResponse  # noqa: E402

from app.core import runs as _runs                              # noqa: E402
from app.core.runs import (Ledger, RunSpec, fmt_hms,            # noqa: E402
                           results_html, spec_settings, version_pairs)
from app.ui import shared, templating, versions                 # noqa: E402
from app.ui import pipeline, retro_prep, retro_seasons          # noqa: E402
from app.ui.routes import data as data_routes                   # noqa: E402
from app.ui.routes import home as home_routes                   # noqa: E402
from app.ui.routes import methods as methods_routes             # noqa: E402
from app.ui.routes import models as models_routes               # noqa: E402
from app.ui.routes import output as output_routes               # noqa: E402
from app.ui.routes import sandbox as sandbox_routes             # noqa: E402
from app.ui.routes import shell as shell_routes                 # noqa: E402
from app.ui.routes import storage as storage_routes             # noqa: E402
from app.ui.forms import (_default_forecast_date, _int_field,   # noqa: E402
                          _knob_form, _knob_panel, _knob_raw, _knobs,
                          _str_field, resolve_anchor)
from app.ui.retro_prep import (_job_covered, _relwis_figures,   # noqa: E402
                               _results_jobs, _results_pending,
                               _retro_map_models, _scores_df,
                               _scores_scoreable_fast, _scoring_failed_hint,
                               _week_map_cards_by_model)
from app.ui.retro_seasons import (_RETRO_ACTIVE,                # noqa: E402
                                  _archive_progress, _is_sealed_root,
                                  _live_root, _retro_claim_at, _retro_status,
                                  _retro_stop, _sealed_label,
                                  _season_status, _valid_archive,
                                  _valid_season)
from app.ui.shared import (_back, _console_elapsed, _flash,     # noqa: E402
                           _invalidate_scans, _outcome_chips, _run_label,
                           _sandbox_live_reason)
from app.ui.state import (ENGINES, _engine_lock, _last_form,    # noqa: E402
                          _status)
from app.ui.templating import (_member_colors, _name_fn,        # noqa: E402
                               _names_for_root, _pf_name, _script_json,
                               _season_colors, templates)
from app.ui.versions import RUNNING_SHA, VERSIONS               # noqa: E402

# === Bootstrap: app, static mount, middleware, the tab routers ===
app = FastAPI(title="FluBNF")
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")),
          name="static")
# the same-host (CSRF) guard first: the sandbox engine guard, added next,
# wraps it (Starlette puts the last-added middleware outermost)
app.middleware("http")(shared._same_host_guard)
app.middleware("http")(sandbox_routes._sandbox_engine_guard)
# the tab routers before the handlers still decorated on the app below: POST
# /runs/clear (storage) must precede GET /runs/{run_id}, since the first
# route a path matches names the Allow header of a wrong-method request
app.include_router(shell_routes.router)
app.include_router(home_routes.router)
app.include_router(data_routes.router)
app.include_router(storage_routes.router)
app.include_router(output_routes.router)
app.include_router(sandbox_routes.router)
app.include_router(models_routes.router)
app.include_router(methods_routes.router)
# the Storage panel's read-only sandbox line (a tab's own Jinja global)
templates.env.globals["sandbox_storage"] = sandbox_routes._sandbox_storage_line


#: Statuses offered the one-click re-run. Console fits hold no checkpoint, so
#: it is a FRESH run with the recorded settings (never worded "resume").
RERUN_STATUSES = ("stopped", "error", "failed", "interrupted", "partial")

# === Startup warm (the version probe itself: app/ui/versions.py) ===
def _start_background_warm() -> None:
    """Daemon thread started at import: version probe, home template and
    outlook (always, since even the empty silhouette pays the science
    imports), latest vintage frame and report modules. Best-effort: never
    delays the first request, failures are silent."""
    import threading

    def _warm():
        t0 = time.perf_counter()
        state._trace("warm: thread begin (versions probe)")
        versions._warm_versions()
        state._trace(
            f"warm: versions done at +{time.perf_counter() - t0:.2f}s")
        try:
            # compile once, here
            templating.templates.env.get_template("home.html")
        except Exception:
            pass
        state._trace(
            f"warm: template done at +{time.perf_counter() - t0:.2f}s")
        try:
            rid, _res = shared._latest_results()
            home_routes._outlook_block(rid)
        except Exception:
            pass
        finally:
            state._WARM_DONE.set()
        state._trace(
            f"warm: outlook done at +{time.perf_counter() - t0:.2f}s")
        # pre-fill the latest vintage frame for the Forecast tab's first click
        try:
            vs = state.data_mod.vintages()
            if vs:
                data_routes._vintage_frame(
                    str(state.data_mod.vintage_path(vs[-1])))
            templating.templates.env.get_template("forecast.html")
            # model-name/color maps ride the report modules (~0.6 s import)
            from app.core import report_season, report_v2   # noqa: F401
        except Exception:
            pass
        state._trace(
            f"warm: forecast done at +{time.perf_counter() - t0:.2f}s")

    threading.Thread(target=_warm, daemon=True,
                     name="flubnf-startup-warm").start()


# === Forecast (/forecast) -> forecast.html ===
@app.get("/forecast", response_class=HTMLResponse)
def forecast_page(request: Request, source: str = ""):
    # a custom dataset as the data source: opt-in per page (app/ui/datasets_ui.py)
    from app.ui import datasets_ui as _dsu
    if source:
        refused = _dsu.local_only(request)
        if refused:
            return refused
        ds = _dsu.get_dataset(source)
        if ds is not None:
            return _dsu.forecast_page(request, ds)
        _flash("That dataset is not stored; showing the FluSight hub.")
    import pandas as pd
    from flubnf.settings import load_locations
    # a missing state list must be visible: without it runs cover all 52
    locations_error = ""
    try:
        _l = load_locations()
        all_locs = list(_l.location_name[(_l.location.str.len() == 2)
                                         & (_l.abbreviation != "US")])
    except Exception as e:
        all_locs = []
        locations_error = (f"State list unavailable ({type(e).__name__}); "
                           "runs will cover all 52 jurisdictions.")
    form = dict(_last_form) or {"forecast_date": _default_forecast_date(),
                                "locations": ["all"], "engine": "all",
                                "weeks_to_drop": 0, "weeks_to_nowcast": 0,
                                "replicates": 3, "members": 2, "season_start": ""}
    rid, res = shared._latest_results()
    # data panel: latest-vintage series for the selected locations (visible
    # before any run); seeded with US national, the panel's default
    import json as _json
    sel = ["US (national)"] + [l for l in form["locations"] if l != "all"]
    series = {}
    try:
        vs = state.data_mod.vintages()
        tdf = data_routes._vintage_frame(
            str(state.data_mod.vintage_path(vs[-1])))
        n2f_ = dict(zip(_l.location_name, _l.location.str.zfill(2)))
        n2f_["US (national)"] = "US"
        for loc in sel[:8]:
            g = tdf[tdf.location == n2f_.get(loc, "")].sort_values("date")
            g = g[pd.to_numeric(g.value, errors="coerce").notna()]
            series[loc] = {"dates": [str(d)[:10] for d in g.date],
                           "values": [float(v) for v in g.value]}
    except Exception:
        pass
    fanq = {}
    # fans: the latest STORED run's models (no session gate: they survive a
    # restart; the card title names the run's date)
    if res:
        for mname, md in res["models"].items():
            good = {loc: qs for loc, qs in md.items()
                    if all(isinstance(v, dict) for v in qs.values())}
            if good:
                fanq[mname] = good
        # the shipped models only: a legacy run's retired blend is not drawn
        from app.core.report_v2 import toggle_models
        fanq = {m: fanq[m] for m in toggle_models(fanq)}
    # the hub view's latest-run card never shows a run on a custom dataset
    ledger_rows = [r for r in Ledger().rows(25)
                   if '"dataset": {' not in (r.get("spec") or "")][:5]
    for r in ledger_rows:
        r["label"] = _run_label(r["run_id"], r.get("spec", ""))
        r["modified"] = _runs.is_modified(r.get("spec", ""))
        r["chips"] = _outcome_chips(r.get("outcome", ""))
        r["settings"] = spec_settings(r.get("spec", ""))
        # the latest-run card links the weekly report when one exists
        try:
            r["has_report"] = bool(_json.loads(r.get("outcome")
                                               or "{}").get("report"))
        except Exception:
            r["has_report"] = False
        if r["status"] == "running" and not (_status.get("running") or "").endswith(r["run_id"]):
            r["status"] = "interrupted"
    # archived Saturdays, newest first, for the form's picker (the native
    # date popup fails in some webviews); str() because the list is
    # serialised into the page and date objects would break the render
    try:
        vintage_dates = [str(v) for v in reversed(state.data_mod.vintages())]
    except Exception:
        vintage_dates = []
    _anchor, _ = resolve_anchor(form.get("forecast_date", ""), vintage_dates)
    anchor_note = (f"Anchor week: {_anchor}."
                   if _anchor else "No archived week on or before that date.")
    return templates.TemplateResponse(request, "forecast.html", {
        "active": "Forecast", "engines": ENGINES, "status": _status,
        "ledger": ledger_rows, "all_locs": all_locs,
        "vintage_dates": vintage_dates, "anchor_note": anchor_note,
        "default_date": _default_forecast_date(),
        "locations_error": locations_error, "form": form,
        "knob_panel": _knob_panel("forecast", form),
        "elapsed0": _console_elapsed(),
        "series_json": _script_json(series), "fanq_json": _script_json(fanq),
        "model_names_json": _script_json(templating._model_names()),
        "member_colors_json": _script_json(_member_colors()),
        "season_colors_json": _script_json(_season_colors()),
        "run_obs_json": _script_json((res or {}).get("observed", {})),
        "fc_date": (res or {}).get("forecast_date", ""),
        "dataset": None, "source_choices": _dsu.choices()})


# === Console controls: /run/stop (the rest: routes/shell.py, data.py) ===
@app.post("/run/stop")
def run_stop():
    _invalidate_scans()
    w = _status.get("workroot")
    running = _status.get("running") or ""
    if w and running:
        (Path(w) / "STOP").touch()
        if (Path(w) / "pf2s").is_dir():        # the two-strain pass polls its
            (Path(w) / "pf2s" / "STOP").touch()  # own subdir for the flag
        _status["phase"] = "stopping…"
    elif running == "starting" and not w:
        # a claim with no worker behind it: release it so the console unwedges
        _status["running"] = None
        _status["run_label"] = ""
        _status["expected_total"] = None
        _status["started_utc"] = None
        _status["phase"] = ""
    return RedirectResponse("/forecast#results", status_code=303)


# === Run pages (/runs/{id}, report, download, rerun) -> run.html ===
@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: str):
    import json as _json
    from app.core.runs import APP_STATE, Ledger
    w = APP_STATE / "workroots" / run_id
    res = {}
    if (w / "results.json").is_file():
        res = _json.loads((w / "results.json").read_text())
    subs = output_routes._submission_files(w)
    report = (w / "report.html").name if (w / "report.html").is_file() else None
    status, err, spec_json = "", "", ""
    o = {}
    sub_errors: dict = {}
    pf_failures: dict = {}
    step_errors: dict = {}
    ens_analogue_only: list = []
    ens_withheld = ""
    row_sha, row_engine_versions = "", {}
    for r in Ledger().rows(200):
        if r.get("run_id") == run_id:
            status = r.get("status", "")
            spec_json = r.get("spec", "") or ""
            row_sha = r.get("flubnf_sha", "") or ""
            try:
                ev = _json.loads(r.get("engine_versions") or "{}")
                row_engine_versions = ev if isinstance(ev, dict) else {}
            except Exception:
                row_engine_versions = {}
            try:
                o = _json.loads(r.get("outcome") or "{}")
                err = o.get("error", "")
                sub_errors = o.get("submission_errors", {}) or {}
                # failures and step errors in full (the chips only count them)
                pf_failures = o.get("pf_failures", {}) or {}
                step_errors = {k: str(o[k]) for k in
                               ("score_error", "archive_error",
                                "report_inputs_error", "report_error")
                               if o.get(k)}
            except Exception:
                err = ""
            break
    # a 'running' row with no live worker = the app was closed mid-run
    if status == "running" and not (_status.get("running") or "").endswith(run_id):
        status = "interrupted"
    # settings, build and engine versions all from the ledger row: "Produced
    # by" must never print this process's build. Names-only engine_versions
    # rows yield an app-build-only block (version_pairs omits unknowns).
    from app.core.runs import is_research
    dsx = {}
    if res.get("dataset"):
        # a run on a custom dataset: exports (never submissions) and fans
        from app.ui import datasets_ui as _dsu
        dsx = _dsu.run_page_extra(w, res)
    return templates.TemplateResponse(request, "run.html", {
        **dsx,
        "active": "Storage", "run_id": run_id, "status": status, "error": err,
        "results": results_html(o, spec_json),
        # the page shows a research badge, so the label stays untagged
        "label": _run_label(run_id, spec_json, tag=False),
        "research": is_research(spec_json),
        "modified": _runs.is_modified(spec_json),
        "override": _knobs.override_reason(spec_json),
        # a legacy run's retired blend is not shown
        "models": {m: v for m, v in (res.get("models") or {}).items()
                   if m not in _report_v2_retired()},
        "settings": spec_settings(spec_json),
        "versions": version_pairs(row_sha, row_engine_versions),
        "can_rerun": (bool(spec_json) and status in RERUN_STATUSES
                      and not dsx),
        "pf_failures": pf_failures, "step_errors": step_errors,
        "subs": subs, "sub_errors": sub_errors, "report": report})


@app.get("/runs/{run_id}/report", response_class=HTMLResponse)
def run_report(run_id: str):
    from app.core.runs import APP_STATE
    d = APP_STATE / "workroots" / run_id
    if not (d / "report.html").is_file():
        return HTMLResponse("<p>no report for this run</p>")
    # rebuilt if stale, as /output/report
    return HTMLResponse(output_routes._report_for_serving(d))


@app.get("/runs/{run_id}/report/download")
def run_report_download(run_id: str):
    """Save this run's weekly report, named for the run's forecast date."""
    from app.core.runs import APP_STATE
    d = APP_STATE / "workroots" / run_id
    date = ""
    try:
        import json as _json
        date = _json.loads((d / "results.json").read_text()).get(
            "forecast_date", "")
    except Exception:
        pass                 # no results.json yet: fall back to the run id
    return output_routes._weekly_report_file(d, date or run_id)


@app.post("/runs/{run_id}/rerun")
def run_rerun(request: Request, background: BackgroundTasks, run_id: str):
    """Re-run a recorded console run: a FRESH run (no checkpoint) with the
    row's exact spec through the /run path (its vintage and busy checks);
    refuses if that path cannot reproduce the spec verbatim."""
    import json as _json
    from dataclasses import asdict as _asdict
    from datetime import date as _date
    row = next((r for r in Ledger().rows(500)
                if r.get("run_id") == run_id), None)
    try:
        d = _json.loads((row or {}).get("spec") or "")
    except (ValueError, TypeError):
        d = None
    if not isinstance(d, dict) or not d.get("forecast_date"):
        _flash("That run's settings were not recorded, so it cannot be "
               "re-run from here. Set the run up on the Forecast form "
               "instead. Nothing was started.")
        return _back(request, "/forecast")
    members = 3 if (d.get("extra") or {}).get("members") == 3 else 2
    locs = [str(l) for l in (d.get("locations") or [])]
    # aux pools re-run their preset (name before the digest tag); none = bare
    _x = d.get("extra") if isinstance(d.get("extra"), dict) else {}
    aux = (str(_x.get("analogue_aux") or "").split("+", 1)[0]
           if _x.get("aux_pools") else "")
    # likewise a plain-filter row re-runs the plain filter
    oracle = "none" if str(_x.get("oracle") or "") == "none" else None
    # model knobs re-run from the row's own record; an override is never
    # inherited (a fresh decision each time), so it is left out of the
    # comparison and the re-run exports under the non-hub name
    _rec = _knobs.record_of(d)
    had_override = bool(_knobs.override_reason(d))
    if had_override:
        d["extra"].pop(_knobs.OVERRIDE_KEY, None)
    try:
        _nd = _knobs.from_record(_rec)
        _cx = _run_extra(members, _spec_mode(d),
                         _knobs.aux_choice(_nd, aux),
                         oracle)
        _knobs.write_extra(_nd, _cx)
    except ValueError:
        _flash("This run's recorded model settings are not readable, so it "
               "cannot be re-run from here. Nothing was started.")
        return _back(request, "/forecast")
    # what /run would build, compared field by field with the stored spec
    candidate = RunSpec(
        engine=str(d.get("engine") or ""),
        forecast_date=str(d.get("forecast_date") or ""),
        season_start=str(d.get("season_start") or ""),
        locations=(locs if any(l.upper() in ("US", "US (NATIONAL)")
                               for l in locs) else locs + ["US"]),
        weeks_to_drop=int(d.get("weeks_to_drop") or 0),
        weeks_to_nowcast=int(d.get("weeks_to_nowcast") or 0),
        # pre-nowcast-rule rows kept the same-day week: reproduce, not default
        drop_same_day=bool(d.get("drop_same_day", False)),
        replicates=int(d.get("replicates") or 3),
        particles=int(d.get("particles") or 10_000),
        jitter=float(d.get("jitter", RunSpec.jitter)),
        extra=_cx)
    # a row recorded before the mode existed reads as a real-time run
    if isinstance(d.get("extra"), dict):
        d["extra"].setdefault("mode", "realtime")
    else:
        d["extra"] = {"mode": "realtime"}
    recon = _asdict(candidate)
    off = [k for k in sorted(d) if recon.get(k) != d[k]]
    try:
        if _date.fromisoformat(candidate.forecast_date).weekday() != 5:
            off.append("forecast_date")   # /run would snap it: not verbatim
    except ValueError:
        off.append("forecast_date")
    if not (1_000 <= candidate.particles <= 100_000):
        off.append("particles")           # /run would refuse it
    if (candidate.jitter != RunSpec.jitter
            and "pf.jitter" not in _rec):
        off.append("jitter")              # only the knob channel sets it
    if off:
        _flash("This run's recorded settings cannot be reproduced from the "
               "console path (" + ", ".join(dict.fromkeys(off)) + " differ "
               "from what the form would run), so nothing was started. "
               "Re-run it from a script using its ledger row.")
        return _back(request, "/forecast")
    if had_override:
        _flash("The earlier run exported under the hub names by override; "
               "an override is never carried over, so this re-run's files "
               "carry the non-hub name.")
    return run_models(request, background,
                      forecast_date=candidate.forecast_date,
                      locations=locs,
                      weeks_to_drop=candidate.weeks_to_drop,
                      weeks_to_nowcast=candidate.weeks_to_nowcast,
                      replicates=candidate.replicates,
                      season_start=candidate.season_start,
                      engine=candidate.engine,
                      members=members,
                      particles=candidate.particles,
                      mode=_spec_mode(d),
                      drop_same_day=1 if candidate.drop_same_day else 0,
                      aux=aux, oracle=oracle,
                      knob_fields={},
                      knobs=(_json.dumps(_rec) if _rec else ""),
                      submit_modified="", modified_reason="")


# === Forecast APIs: /api/series, /api/progress ===
@app.get("/api/series")
def api_series(request: Request, locs: str = "", source: str = ""):
    """Data-panel series for the checked locations (live, before any run);
    `source` = a custom dataset's id (its groups' newest data)."""
    if source:
        from app.ui import datasets_ui as _dsu
        refused = _dsu.local_only(request)
        if refused:
            return refused
        ds = _dsu.get_dataset(source)
        return _dsu.api_series(ds, locs) if ds is not None else {}
    import pandas as pd
    sel = [l for l in locs.split("|") if l][:8] or ["Ohio"]
    out = {}
    try:
        _l = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
        n2f_ = dict(zip(_l.location_name, _l.location.str.zfill(2)))
        n2f_["US (national)"] = "US"
        vs = state.data_mod.vintages()
        tdf = pd.read_csv(state.data_mod.vintage_path(vs[-1]),
                          dtype={"location": str})
        tdf["location"] = tdf["location"].str.zfill(2)
        for loc in sel:
            g = tdf[tdf.location == n2f_.get(loc, "")].sort_values("date")
            g = g[pd.to_numeric(g.value, errors="coerce").notna()]
            out[loc] = {"dates": [str(d)[:10] for d in g.date],
                        "values": [float(v) for v in g.value]}
    except Exception:
        pass
    return out


@app.get("/api/progress")
def api_progress():
    import glob
    import json as _json
    import time as _time
    w = _status.get("workroot")
    out = {"running": bool(_status.get("running")),
           "phase": _status.get("phase", ""),
           "label": _status.get("run_label", ""),
           # anchors for the browser's own ticking clock
           "started_utc": _status.get("started_utc"),
           "elapsed_s": _console_elapsed(),
           # (label, value) pairs for a client that arrived mid-run
           "settings": list(_status.get("settings") or [])}
    if w:
        done = total = 0
        t0 = None
        # pf_status*.json.prog: the pre-shard merged name and per-shard files
        for f in (glob.glob(w + "/pf_status*.json.prog")
                  + glob.glob(w + "/pf2s/pf_status*.json.prog")):
            try:
                d = _json.loads(open(f).read())
                done += d["done"]; total += d["total"]
                t0 = min(t0 or d["t0"], d["t0"])
            except Exception:
                pass
        # stable denominator from the claim; shard totals grow toward it
        total = max(total, int(_status.get("expected_total") or 0))
        out["done"], out["total"] = done, total
        if done and total and t0:
            rate = (_time.time() - t0) / done
            out["eta_s"] = int(rate * (total - done))
    elif _status.get("expected_total"):
        # run claimed but workroot not created yet: report 0/N, not silence
        out["done"], out["total"] = 0, int(_status["expected_total"])
    return out


def _run_extra(members: int, mode: str, aux: str | None = None,
               oracle: str | None = None) -> dict:
    """spec.extra for a console run: form mode, members=3 research flag,
    Groundhog aux pools (recorded in the spec so it replays), Oracle switch.

    aux: None = shipped (analogue.SHIPPED_AUX, digests recorded), a preset
    name, or "" = bare analogue (research; file withheld).
    oracle: None = shipped Oracle SIHRS, "none" = plain filter (research;
    file withheld); anything else raises."""
    from app.core.engines import analogue as _an
    mode = mode if mode in ("realtime", "vintage") else "realtime"
    extra = {"mode": mode}
    if members == 3:
        extra["members"] = 3
    name = _an.SHIPPED_AUX if aux is None else str(aux)
    if name:
        fn = _an.aux_preset(name)                # unknown name raises here
        extra["aux_pools"] = fn(None, 0, None)["aux_pools"]
        extra["analogue_aux"] = fn.__name__.split(":", 1)[1]
    if oracle is not None and str(oracle) != "":
        if str(oracle) != "none":
            raise ValueError(f"oracle must be 'none' (the plain filter, a "
                             f"research run) or absent, not {oracle!r}")
        extra["oracle"] = "none"
    return extra


def _knob_run_parts(kraw: dict, engine: str, forecast_date: str,
                    members: int, mode: str, aux, oracle, *, legacy: dict,
                    override: bool = False, reason: str = "") -> tuple:
    """(non-default knob values, spec.extra) for a console run; raises
    KnobError/ValueError on anything refused. Knobs that do not apply to
    the engine (or the Oracle step when it is off) are dropped, never
    recorded. No knob off shipped -> exactly today's extra."""
    eng = engine if engine in _knobs.ENGINE_MEMBERS else "all"
    step = str(oracle or "") != "none"
    nd = _knobs.resolve(kraw, eng, scope="forecast",
                        forecast_date=forecast_date, oracle_step=step,
                        legacy=legacy, two_strain=(members == 3))
    if "groundhog.aux" in nd and aux is not None:
        want = _knobs.aux_choice(nd, None)
        if str(aux) != want:
            raise _knobs.KnobError(
                f"groundhog.aux: the form gives two donor banks "
                f"({aux or 'none'} and {want or 'none'}); give one")
    if override and nd and not reason:
        raise _knobs.KnobError(
            "exporting under the hub names needs a reason; type one, or "
            "untick the box to export under the non-hub name")
    extra = _run_extra(members, mode, _knobs.aux_choice(nd, aux), oracle)
    _knobs.write_extra(nd, extra, override=(reason if override else ""))
    return nd, extra


def _spec_mode(d: dict) -> str:
    extra = d.get("extra") if isinstance(d.get("extra"), dict) else {}
    m = str(extra.get("mode") or "realtime")
    return m if m in ("realtime", "vintage") else "realtime"


def _report_v2_retired() -> tuple:
    """report_v2.RETIRED_MODELS, imported lazily (report_v2 pulls plotly)."""
    from app.core.report_v2 import RETIRED_MODELS
    return RETIRED_MODELS


# === Retrospective (season registry and progress: retro_seasons.py) ===
class _RetroStopRequested(Exception):
    """Raised inside the season worker between weeks when a stop was asked."""


# === Retrospective index (/retro) and its APIs -> retro.html ===
def _retro_state_names() -> list:
    """State list for the retro form; packaged locations table when the hub
    is not cloned yet."""
    import pandas as pd
    from flubnf.settings import LOCATIONS
    from pathlib import Path as _P
    packaged = _P(__file__).resolve().parents[2] / "flubnf/data/locations.csv"
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
    from pathlib import Path as _P
    from app.core import us_national as usn
    packaged = _P(__file__).resolve().parents[2] / "flubnf/data/locations.csv"
    for src in (LOCATIONS, packaged):
        try:
            locs = pd.read_csv(src, dtype=str)
            hit = locs.location_name[locs.abbreviation == "US"]
            if len(hit):
                return str(hit.iloc[0])
        except Exception:
            continue
    return usn.US_FIPS


@app.get("/retro", response_class=HTMLResponse)
def retro_index(request: Request, dataset: str = ""):
    from app.core import retro as _retro
    from app.core.retro import available_seasons, season_vintages
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
    # the own-data replays: their own card, never beside the hub seasons
    from app.ui import datasets_ui as _dsu
    return templates.TemplateResponse(request, "retro.html",
                                      {**_dsu.retro_context(dataset),
                                       "active": "Retrospective", "seasons": seasons,
                                       "state_names": _retro_state_names(),
                                       "default_width": DEFAULT_SHARD_WIDTH,
                                       "width_cap": SHARD_WIDTH_CAP,
                                       "knob_panel": _knob_panel("retro"),
                                       "engine_ok": PY_ENGINE.exists()
                                       and PYBNF.exists()})


@app.get("/api/retro/progress")
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


@app.get("/api/retro/startover")
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


@app.post("/retro/{season}/archive/{stamp}/delete")
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


@app.get("/api/retro/{season}/results_status")
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


@app.post("/retro/stop")
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


@app.post("/retro/{season}/stop")
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


@app.post("/retro/{season}/pause")
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


@app.post("/retro/{season}/resume")
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


@app.post("/retro/run")
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
@app.get("/retro/{season}", response_class=HTMLResponse)
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


@app.get("/api/retro/{season}/playback/{asof}")
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


@app.get("/api/retro/{season}/mapswap/{asof}")
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


@app.get("/retro/{season}/report")
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


@app.get("/api/retro/{season}/report_path")
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


# === Forecast: POST /run (form and rerun entry to _run_all) ===
@app.post("/run")
def run_models(request: Request,
               background: BackgroundTasks,
               forecast_date: str = Form(...),
               locations: list = Form([]),
               weeks_to_drop: int = Form(0),
               weeks_to_nowcast: int = Form(0),
               replicates: int = Form(3),
               engine: str = Form("all"),
               members: int = Form(2),
               particles: int = Form(10_000),
               season_start: str = Form(""),   # blank = Aug 1 of the season
               mode: str = Form("realtime"),   # recorded: vintage or real-time
               # re-run-only fields (not on the form): None/0 = today's
               # shipped config; /runs/{id}/rerun passes the row's values
               drop_same_day: int = Form(0),
               aux: str | None = Form(None),    # Groundhog donors; "" = bare
               oracle: str | None = Form(None),  # "none" = plain filter
               # the Model settings panel (app/core/knobs.py): knob.<key>
               # fields, or one JSON dict (the re-run path); the override
               # exports a modified run under the hub names, with a reason
               knob_fields: dict = Depends(_knob_form),
               knobs: str = Form(""),
               submit_modified: str = Form(""),
               modified_reason: str = Form("")):
    # non-Saturdays snap via resolve_anchor; a typed Saturday is honoured or
    # refused below (never re-aimed)
    from datetime import date as _date
    try:
        _d = _date.fromisoformat(forecast_date)
        if _d.weekday() != 5:
            # the form already shows this anchor; no banner
            _pick, _ = resolve_anchor(forecast_date)
            forecast_date = _pick or forecast_date
    except ValueError:
        pass
    try:
        state.data_mod.vintage_path(forecast_date)
    except Exception:
        # archive gaps are real (holiday weeks): suggest the nearest EARLIER
        # vintage only; a later one would leak hindsight
        vs = state.data_mod.vintages()
        earlier = [v for v in vs if v <= forecast_date]
        near = max(earlier) if earlier else (min(vs) if vs else None)
        if near and _last_form:
            _last_form["forecast_date"] = near
        if not vs:
            _flash(f"No archived data for {forecast_date}. Pull the "
                   "FluSight hub on the Data tab first.")
        elif earlier:
            _flash(f"The FluSight hub archived no data snapshot dated "
                   f"{forecast_date}; such gaps are real, usually holiday "
                   "weeks. The graphs still show a point at that date "
                   "because they draw today's settled data, which was not "
                   "yet reported on the day itself. Nearest earlier "
                   f"archived Saturday: {near}. A later one would leak a "
                   "week of hindsight, so it is not offered.")
        else:
            _flash(f"No archived data for {forecast_date}; the archive "
                   f"starts at {near}.")
        return _back(request, "/forecast")
    # A direct call (rerun) may pass Form default objects: read them as blank
    season_start = _str_field(season_start).strip()
    kraw = _knob_raw(knob_fields, knobs)
    override = _str_field(submit_modified).lower() in ("1", "on", "true", "yes")
    reason = _str_field(modified_reason).strip()
    _last_form.update({"forecast_date": forecast_date, "locations": locations,
                       "engine": engine, "weeks_to_drop": weeks_to_drop,
                       "weeks_to_nowcast": weeks_to_nowcast,
                       "replicates": replicates, "members": members,
                       "season_start": season_start,
                       "particles": particles,
                       "drop_same_day": _int_field(drop_same_day),
                       "knobs": {k: v for k, v in kraw.items()
                                 if isinstance(v, str)},
                       "submit_modified": override,
                       "modified_reason": reason})
    # model settings, validated BEFORE the engine is claimed: a refusal
    # starts nothing. The legacy fields (season start, weeks to drop,
    # replicates, particles, same-day week) set their knob; a value outside
    # a knob's range is refused, never clamped.
    try:
        nd, extra = _knob_run_parts(
            kraw, engine, forecast_date, members, mode, aux, oracle,
            legacy={"particles": particles, "replicates": replicates,
                    "season_start": season_start,
                    "weeks_to_drop": weeks_to_drop,
                    "drop_same_day": bool(_int_field(drop_same_day))},
            override=override, reason=reason)
    except ValueError as e:                  # KnobError is a ValueError
        _flash(f"Model settings: {e}. Nothing was run.")
        return _back(request, "/forecast")
    kspec = _knobs.spec_fields(nd)
    season_start = kspec.get("season_start", "")
    weeks_to_drop = int(kspec.get("weeks_to_drop", 0))
    replicates = int(kspec.get("replicates", RunSpec.replicates))
    particles = int(kspec.get("particles", RunSpec.particles))
    # checkboxes arrive as a list, text inputs as comma-separated strings
    locations = [x.strip() for l in locations
                 for x in str(l).split(",") if x.strip()]
    if not locations:
        _flash("Select at least one location, or all 52 jurisdictions. "
               "Nothing was run.")
        return _back(request, "/forecast")
    # busy check + claim under _engine_lock (see its comment)
    with _engine_lock:
        if _status.get("running"):
            _status["log"].append("A run is already in progress; not starting another.")
            return RedirectResponse("/forecast#results", status_code=303)
        live_retro = sorted(x for x in retro_seasons._known_seasons()
                            if _season_status(x) in _RETRO_ACTIVE)
        if live_retro:
            _flash("A retrospective replay holds the engine ("
                   + ", ".join(live_retro) + "). Stop or pause it from the "
                   "Retrospective tab first; nothing was run.")
            return _back(request, "/forecast")
        sb = _sandbox_live_reason()
        if sb:
            _flash(f"Not run: {sb}. Stop it from the Sandbox first.")
            return _back(request, "/forecast")
        # background tasks fire after the redirect: claim NOW so the landing
        # page shows the run
        _status["running"] = "starting"
        _invalidate_scans()
        _status["started_utc"] = __import__("time").time()
        _status["run_label"] = f"{forecast_date} · queued"
    from app.core import us_national as _usn
    if "all" in [l.lower() for l in locations]:
        _l = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
        locs_list = list(_l.location_name[(_l.location.str.len() == 2)
                                          & (_l.abbreviation != "US")])
        us = _l.location_name[_l.abbreviation == "US"]
        if len(us):
            locs_list.append(str(us.iloc[0]))   # national, fitted directly
    else:
        locs_list = list(locations)
    # national always fitted (as on the Retrospective tab)
    locs_list = _usn.with_us(locs_list)
    n_states = len(_usn.state_names(locs_list))
    _status["run_label"] = f"{forecast_date} · {n_states} state(s) + US · queued"
    # progress denominator known now (shards grow toward it); clear the old
    # workroot so its .prog files never show. The analogue alone gets none.
    _status["workroot"] = None
    _status["expected_total"] = (len(locs_list) * int(replicates)
                                 * (2 if members == 3 else 1)
                                 if engine in ("all", "pf") else None)
    # particles, replicates and weeks to drop were range-checked as knobs
    # above (refused, never clamped: replicates = 0 once ran zero fits)
    # mode follows the anchor: real-time means the newest archived vintage
    try:
        newest = state.data_mod.vintages()[-1]
    except Exception:
        newest = None
    if newest and mode == "realtime" and forecast_date != newest:
        mode = "vintage"
        extra["mode"] = mode
        _flash(f"Anchored on the archived week {forecast_date}, not the "
               f"newest vintage ({newest}): recorded as a vintage run.")
    spec = RunSpec(engine=engine, forecast_date=forecast_date,
                   locations=locs_list,
                   season_start=season_start,
                   weeks_to_drop=weeks_to_drop,
                   weeks_to_nowcast=weeks_to_nowcast,
                   drop_same_day=bool(kspec.get("drop_same_day", False)),
                   replicates=replicates,
                   particles=particles,
                   **({"jitter": float(kspec["jitter"])}
                      if "jitter" in kspec else {}),
                   extra=extra)

    if engine in ("all", "pf", "analogue"):
        # 'analogue' = the same pipeline with the PF block skipped
        background.add_task(pipeline._run_all, spec)
    else:
        # unknown engine: release the claim rather than wedge the console
        _status["running"] = None
        _status["run_label"] = ""
        _status["expected_total"] = None
        _status["started_utc"] = None
        _flash(f"'{engine}' is not one of the available engines. "
               "Nothing was run.")
    return RedirectResponse("/forecast#results", status_code=303)


# === Custom datasets: upload, browse, forecast, replay (app/ui/datasets_ui.py) ===
from app.ui import datasets_ui as _datasets_ui              # noqa: E402
app.include_router(_datasets_ui.router)
# the upload box's size limit, wherever the box is placed
templates.env.globals["dataset_upload_mb"] = _datasets_ui.max_mb


# === Startup warm (LAST, so every function it reaches is defined) ===
state._trace("import complete, starting background warm")
_start_background_warm()
