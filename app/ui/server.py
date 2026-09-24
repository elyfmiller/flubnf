"""FastAPI operations console: every tab of the FluBNF app in one module.

Server-rendered (locked decision: FastAPI + templates, no build chain).
Run:  .venv/bin/uvicorn app.ui.server:app --port 8710

Support modules beside this one (app/ui), read by the tabs below:

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

Contents, in file order (each section starts with a `# === ... ===` banner;
templates under app/ui/templates):

  Bootstrap           app, /static, the CSRF guard's registration,
                      startup warm, GET /api/versions
  Home               GET /, GET /api/outlook-ready            home.html
  Methods             GET /methods                             methods.html
  Forecast            GET /forecast                            forecast.html
  Data                GET /data                                data.html
  Storage             GET /storage (= /runs), POST /runs/clear,
                      /storage/delete, /storage/clear-workroots,
                      GET /api/storage/reclaim, POST /storage/reclaim
                                                               runs.html
  Console controls    POST /run/stop, GET /api/busy, POST /data/pull,
                      POST /freshness (renders data.html)
  Submission files    registered model ids, _submission_files
  Run pages           GET /runs/{id}, /report, /report/download,
                      POST /runs/{id}/rerun                    run.html
  Forecast APIs       GET /api/series, GET /api/progress
  Output              GET /output, /output/download, POST /output/reveal,
                      GET /output/report, /output/report/download
                                                               output.html
  Sandbox             GET /sandbox, POST /sandbox/*, GET /api/sandbox/*,
                      GET /sandbox/models|runs/{id}/download
                                                               sandbox.html
  Models              GET /models, /model/{name}               model.html
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

import html as _htmlmod
import threading
import time
import sys
from pathlib import Path

from app.ui import state

sys.path.insert(0, str(state.REPO))
state._trace("import begin (fastapi + app.core next)")

from fastapi import (BackgroundTasks, Depends, FastAPI, Form,  # noqa: E402
                     Request)
from fastapi.responses import (HTMLResponse, JSONResponse, PlainTextResponse,  # noqa: E402
                               RedirectResponse)

from app.core import horizons as _hzmod                         # noqa: E402
from app.core import ttlcache                                   # noqa: E402
from app.core import runs as _runs                              # noqa: E402
from app.core.runs import (Ledger, RunSpec, fmt_hms,            # noqa: E402
                           results_html, spec_settings, version_pairs)
from app.core import oracle_text as _oracle_text                # noqa: E402
from app.ui import shared, templating, versions                 # noqa: E402
from app.ui import pipeline, retro_prep, retro_seasons          # noqa: E402
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
                                  _retro_stop, _sealed_label, _sealed_roots,
                                  _season_status, _valid_archive,
                                  _valid_season)
from app.ui.shared import (_LOCAL_HOSTNAMES, _archive_dates,    # noqa: E402
                           _authority_hostname, _back, _console_elapsed,
                           _flash, _invalidate_scans, _outcome_chips,
                           _run_label, _sandbox_live, _sandbox_live_reason,
                           _scan_archive_dates)
from app.ui.state import (ENGINES, REPO, _engine_lock,          # noqa: E402
                          _last_form, _sandbox_status, _status)
from app.ui.templating import (_member_colors, _name_fn,        # noqa: E402
                               _names_for_root, _pf_name, _script_json,
                               _season_colors, templates)
from app.ui.versions import (RUNNING_SHA, VERSIONS,             # noqa: E402
                             versions_resolved)

# === Bootstrap: app, static mount, CSRF guard ===
app = FastAPI(title="FluBNF")
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")),
          name="static")
# the same-host (CSRF) guard first: the sandbox engine guard, added below,
# wraps it (Starlette puts the last-added middleware outermost)
app.middleware("http")(shared._same_host_guard)


#: Statuses offered the one-click re-run. Console fits hold no checkpoint, so
#: it is a FRESH run with the recorded settings (never worded "resume").
RERUN_STATUSES = ("stopped", "error", "failed", "interrupted", "partial")

# === Startup warm (the version probe itself: app/ui/versions.py) ===
def _outlook_ready() -> bool:
    """Whether home can render its outlook inline without paying the first
    science import: warm pass done, or pandas already loaded. False only on
    a cold first paint (home then serves the preparing silhouette)."""
    return state._WARM_DONE.is_set() or "pandas" in sys.modules


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
            _outlook_block(rid)
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
                _vintage_frame(str(state.data_mod.vintage_path(vs[-1])))
            templating.templates.env.get_template("forecast.html")
            # model-name/color maps ride the report modules (~0.6 s import)
            from app.core import report_season, report_v2   # noqa: F401
        except Exception:
            pass
        state._trace(
            f"warm: forecast done at +{time.perf_counter() - t0:.2f}s")

    threading.Thread(target=_warm, daemon=True,
                     name="flubnf-startup-warm").start()


@app.get("/api/versions")
def api_versions():
    """Versions as known now, and whether the probe landed (home and Methods
    poll this while a value is pending)."""
    return {"versions": dict(VERSIONS), "resolved": versions_resolved()}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """PyBNF brand kit favicon (small-size mark)."""
    from fastapi.responses import FileResponse
    ico = Path(__file__).parent / "static" / "brand" / "favicon.ico"
    return FileResponse(ico, media_type="image/x-icon")


# === Home (/): outlook map, diagram feed -> home.html ===
def _outlook_cards(res: dict | None, rid: str | None = None) -> tuple:
    """(fips -> hover card for svg_map, source meta) for the home outlook.

    Exact path: the run's report bundle (report_inputs.json), so home shows
    the weekly report's categories; used as-is when it holds >= 2 per-model
    card sets. Otherwise one card set per stored model is approximated from
    results.json quantiles (categorical_probs_from_quantiles): meta
    approx=True, meta["by_model"] funds the toggle. A pre-v3 bundle that
    cannot fund a toggle keeps its exact single-model cards. Card-less
    states get empty cards so the full silhouette renders."""
    import json as _json

    from app.core import report_v2
    from app.core.report import categorical_probs_from_quantiles
    from app.core.report_v2 import CATS
    from app.core.runs import APP_STATE
    bundle_cards = bundle_meta = None
    if rid:
        try:
            b = APP_STATE / "workroots" / rid / report_v2.BUNDLE_NAME
            if b.is_file():
                bundle = _json.loads(b.read_text())
                if (bundle.get("version")
                        in report_v2.SUPPORTED_BUNDLE_VERSIONS):
                    cards = {c["fips"]: c
                             for c in (bundle.get("cards") or {}).values()
                             if isinstance(c, dict) and c.get("fips")}
                    model = bundle.get("cards_model") or "pf"
                    if (model not in report_v2.RETIRED_MODELS
                            and any(c.get("probs") for c in cards.values())):
                        bundle_cards = cards
                        bundle_meta = {"model": model, "approx": False,
                                       "label": report_v2.MODEL_LABEL.get(
                                           model, report_v2.MODEL_LABEL["pf"]),
                                       # bundle v4 coverage; None -> 'no data'
                                       "fitted_fips": bundle.get(
                                           "fitted_fips")}
                        # >= 2 per-model card sets: exact cards and toggle
                        cbm = bundle.get("cards_by_model") or {}
                        if sum(1 for cs in cbm.values()
                               if any(isinstance(c, dict) and c.get("probs")
                                      for c in (cs or {}).values())) >= 2:
                            return bundle_cards, bundle_meta
        except Exception:
            bundle_cards = bundle_meta = None   # broken bundle: approximate
    _l = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
    n2f = dict(zip(_l.location_name, _l.location.str.zfill(2)))
    n2a = dict(zip(_l.location_name, _l.abbreviation))
    n2p = dict(zip(_l.location_name, _l.population.astype(float)))
    models = (res or {}).get("models", {})
    # PF first, then the Groundhog (a legacy run's blend is not shown)
    model = next((m for m in ("pf", "analogue") if models.get(m)), "pf")
    observed = (res or {}).get("observed", {})
    by_model: dict = {}
    models = _hzmod.models_to_canonical(models)
    for mname, md in models.items():
        cards = {}
        for loc, qd in (md or {}).items():
            fips = n2f.get(loc, "")
            q1 = (qd or {}).get("0")      # one week ahead, canonical
            obs = observed.get(loc) or []
            # tolerate the pre-quantile results schema (medians-only floats)
            if len(fips) != 2 or not isinstance(q1, dict) or not obs:
                continue
            lo = float(obs[-1][1])
            probs = categorical_probs_from_quantiles(q1, lo, int(n2p[loc]), 0)
            if not probs:
                continue
            vals = [float(v) for v in q1.values()]
            med1 = float(q1.get("0.5", vals[len(vals) // 2]))
            # hover_html reaches innerHTML: escape the name at the source
            hover = (f"<b>{_htmlmod.escape(loc)}</b><br>current: {lo:.0f}"
                     f"<br>1-wk median: {med1:.0f}<br>" +
                     "<br>".join(f"{c.replace('_',' ')}: {probs.get(c,0):.0%}"
                                 for c in CATS))
            cards[fips] = {"probs": probs, "name": loc,
                           "abbr": n2a.get(loc, ""),
                           "fips": fips, "hover_html": hover}
        if cards:
            by_model[mname] = cards
    # the retired blend is never the map, even on a legacy run
    from app.core.report_v2 import RETIRED_MODELS
    by_model = {m: c for m, c in by_model.items() if m not in RETIRED_MODELS}
    if model not in by_model and by_model:
        model = next(iter(by_model))
    # no toggle possible: an exact single-model bundle beats the approximation
    if bundle_cards is not None and len(by_model) < 2:
        return bundle_cards, bundle_meta
    cards = dict(by_model.get(model) or {})
    for name, fips in n2f.items():
        if len(fips) == 2:
            cards.setdefault(fips, {"name": name, "abbr": n2a.get(name, ""),
                                    "fips": fips})
    from app.core.report_v2 import MODEL_LABEL
    return cards, {"model": model, "approx": True,
                   "label": MODEL_LABEL.get(model, MODEL_LABEL["pf"]),
                   "by_model": by_model}


def _outlook_models(rid: str | None) -> dict:
    """{model: {fips: card}} from the bundle's cards_by_model (v3), models
    with data only; {} for older bundles (home then uses _outlook_cards'
    approximate sets)."""
    import json as _json

    from app.core import report_v2
    from app.core.runs import APP_STATE
    if not rid:
        return {}
    try:
        b = APP_STATE / "workroots" / rid / report_v2.BUNDLE_NAME
        if not b.is_file():
            return {}
        bundle = _json.loads(b.read_text())
        if bundle.get("version") not in report_v2.SUPPORTED_BUNDLE_VERSIONS:
            return {}
        out = {}
        for m, cards in (bundle.get("cards_by_model") or {}).items():
            byf = {c["fips"]: c for c in (cards or {}).values()
                   if isinstance(c, dict) and c.get("fips")
                   and c.get("probs")}
            if byf:
                out[m] = byf
        return out
    except Exception:
        return {}          # a broken bundle degrades to the plain map


def _diagram_data(res: dict | None) -> dict:
    """Per-location annotations for the compartment diagram: fitted-parameter
    medians (results.json 'params'), last observation, 1-week median. No
    template reads the 'diagram' key today; test_pages covers this."""
    out = {"date": "", "has_pf2s": False, "locations": {}, "order": []}
    if not res:
        return out
    try:
        out["date"] = res.get("forecast_date", "") or ""
        params = res.get("params") or {}
        pf_p = params.get("pf") or {}
        p2_p = params.get("pf2s") or {}
        models = _hzmod.models_to_canonical(res.get("models") or {})
        out["has_pf2s"] = bool(p2_p) or bool(models.get("pf2s"))
        observed = res.get("observed") or {}
        picked = (models.get("pf") or models.get("analogue")
                  or models.get("ensemble") or {})
        for loc in set(pf_p) | set(p2_p) | set(observed) | set(picked):
            e = {}
            if isinstance(pf_p.get(loc), dict) and pf_p[loc]:
                e["pf"] = pf_p[loc]
            if isinstance(p2_p.get(loc), dict) and p2_p[loc]:
                e["pf2s"] = p2_p[loc]
            obs = observed.get(loc) or []
            if obs:
                e["obs"] = obs[-1]
            q1 = (picked.get(loc) or {}).get("0")   # one week ahead
            if isinstance(q1, dict) and q1.get("0.5") is not None:
                e["med1"] = float(q1["0.5"])
            if e:
                out["locations"][str(loc)] = e
        out["order"] = sorted(
            out["locations"],
            key=lambda l: (l.upper() not in ("US", "US (NATIONAL)"), l))
    except Exception:
        return {"date": "", "has_pf2s": False, "locations": {}, "order": []}
    return out


def _outlook_results_mtime(rid: str | None) -> float:
    """Outlook cache-key term: the run's results.json mtime (0.0 if none)."""
    if not rid:
        return 0.0
    from app.core.runs import APP_STATE
    try:
        return (APP_STATE / "workroots" / rid / "results.json").stat().st_mtime
    except OSError:
        return 0.0


@ttlcache.ttl_cache(ttl_s=300.0)
def _outlook_block_cached(rid: str | None, mtime: float) -> dict:
    """Home outlook (map, caption facts, model toggle), cached per (run,
    results mtime) so the long TTL never serves a stale map."""
    import json as _json
    res = None
    if rid:
        from app.core.runs import APP_STATE
        try:
            res = _json.loads((APP_STATE / "workroots" / rid
                               / "results.json").read_text())
        except Exception:
            res = None
    # latest run's outlook, else the empty-country silhouette
    map_svg, outlook_date, outlook_n = "", "", 0
    outlook_src: dict = {}
    outlook_toggle = ""
    try:
        from app.core import report_v2, usmap
        from app.core.usmap import map_legend, svg_map
        cards = {}
        try:
            cards, outlook_src = _outlook_cards(res, rid)
            if any(c.get("probs") for c in cards.values()):
                outlook_date = (res or {}).get("forecast_date", "")
            else:
                outlook_src = {}      # an empty map needs no model label
        except Exception:
            pass                      # no LOCATIONS/hub -> bare silhouette
        with_data = {c["abbr"] for c in cards.values() if c.get("probs")}
        # caption counts only colored jurisdictions (US has no state shape)
        outlook_n = len(with_data - {"US"})
        # fitted_fips (bundle v4) lets hovers tell a reporting gap from 'not
        # fitted'; absent -> hovers claim only 'no data'
        scope = outlook_src.get("fitted_fips") if outlook_src else None
        scope = set(scope) if scope is not None else None
        map_svg = ("<div style='max-width:880px;margin:0 auto'>"
                   "<script>window.MAP_LINK='/output/report';</script>"
                   + svg_map(cards, clickable=with_data, scope_fips=scope)
                   + map_legend() + "</div>")
        # toggle from the v3 bundle's per-model cards, else the approximate
        # sets; fewer than two models -> label only, never a dead control
        try:
            by_model = _outlook_models(rid) if outlook_src else {}
            if not by_model and outlook_src.get("approx"):
                by_model = outlook_src.get("by_model") or {}
            order = report_v2.toggle_models(by_model)
            if len(order) >= 2:
                default = (outlook_src.get("model")
                           if outlook_src.get("model") in order
                           else order[0])
                payload = {m: {"states": usmap.state_swap_payload(
                                   by_model[m], scope_fips=scope),
                               "us": {}}
                           for m in order}
                outlook_toggle = usmap.model_toggle(
                    order, report_v2.MODEL_LABEL, default, payload,
                    group_id="outlook-model", btn_class="quiet",
                    active_class="gold", wrap_class="row viewtabs",
                    short_labels=report_v2.MODEL_SHORT)
        except Exception:
            outlook_toggle = ""
    except Exception:
        pass
    return {"map_svg": map_svg, "outlook_date": outlook_date,
            "outlook_n": outlook_n,
            "label": outlook_src.get("label", ""),
            "approx": bool(outlook_src.get("approx")),
            "toggle": outlook_toggle}


def _outlook_block(rid: str | None) -> dict:
    return _outlook_block_cached(rid, _outlook_results_mtime(rid))


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    _t0 = time.perf_counter()
    state._trace("home: request begin")
    try:
        rid, res = shared._latest_results()
    except Exception:
        rid, res = None, None
    pending = not _outlook_ready()
    if pending:
        # give the warm pass 1.5 s so a warm machine paints complete
        state._WARM_DONE.wait(1.5)
        pending = not _outlook_ready()
    if pending:
        # truly cold start: silhouette + preparing note now; the page polls
        # /api/outlook-ready and reloads once
        from app.core.usmap import map_legend, svg_map
        ob = {"map_svg": ("<div style='max-width:880px;margin:0 auto'>"
                          + svg_map({}, clickable=set()) + map_legend()
                          + "</div>"),
              "outlook_date": "", "outlook_n": 0,
              "label": "", "approx": False, "toggle": ""}
    else:
        ob = _outlook_block(rid)
    state._trace(f"home: outlook ready at +{time.perf_counter() - _t0:.2f}s "
                 f"(pending={pending}), rendering")
    return templates.TemplateResponse(request, "home.html", {
        "active": "Home", "map_svg": ob["map_svg"],
        "outlook_date": ob["outlook_date"],
        "outlook_n": ob["outlook_n"],
        "outlook_model_label": ob["label"],
        "outlook_approx": ob["approx"],
        "outlook_toggle": ob["toggle"],
        "outlook_pending": pending,
        "versions": VERSIONS, "diagram": _diagram_data(res),
        "missing": __import__("flubnf.settings", fromlist=["check"]).check(verbose=False)})


@app.get("/api/outlook-ready")
def api_outlook_ready():
    """Whether home's outlook now renders inline (polled by the cold first
    paint's preparing state)."""
    return {"ready": _outlook_ready()}


# === Methods (/methods) -> methods.html ===
@app.get("/methods", response_class=HTMLResponse)
def methods_page(request: Request):
    """Methodology reference: the SIHRS compartment model, the fitting
    machinery, the Oracle step, the Groundhog, and the data and verification
    policies."""
    return templates.TemplateResponse(request, "methods.html", {
        "active": "Methods", "versions": VERSIONS})


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
        tdf = _vintage_frame(str(state.data_mod.vintage_path(vs[-1])))
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


# === Data (/data): read-only vintage views -> data.html ===
# Archived vintage CSVs (~600 KB) are immutable: long TTL, keyed by path +
# date; the hub pull calls _invalidate_scans().

VINTAGE_TTL_S = 300.0


@ttlcache.ttl_cache(ttl_s=VINTAGE_TTL_S)
def _vintage_frame(path: str):
    """A vintage CSV parsed once and shared, keyed by path. Callers must
    not mutate the frame."""
    import pandas as pd
    tdf = pd.read_csv(path, dtype={"location": str})
    tdf["location"] = tdf["location"].str.zfill(2)
    return tdf


@ttlcache.ttl_cache(ttl_s=VINTAGE_TTL_S)
def _vintage_summary(path: str, date: str) -> dict:
    return state.data_mod.vintage_summary(date)


@ttlcache.ttl_cache(ttl_s=VINTAGE_TTL_S)
def _vintage_locations(path: str, date: str) -> tuple:
    return tuple(state.data_mod.vintage_location_names(date))


@ttlcache.ttl_cache(ttl_s=VINTAGE_TTL_S)
def _vintage_series(path: str, date: str, loc: str) -> dict:
    return state.data_mod.vintage_series(date, loc)


def _data_context(loc: str = "", vintage: str = "", freshness=None) -> dict:
    """Data page context: the latest vintage's freshness panel and the
    vintage browser's selection. Read-only; bad selections fall back to the
    defaults with a note, never an error page."""
    import re as _re
    vs = state.data_mod.vintages()
    ctx = {"active": "Data", "latest_vintage": vs[-1] if vs else "none",
           "n_vintages": len(vs), "freshness": freshness,
           "latest": None, "vintages": list(reversed(vs)),
           "sel_vintage": "", "sel_loc": "", "loc_names": [],
           "sel_summary": None, "series_table": [], "series_n": 0,
           "series_json": "null", "peak": None, "view_note": "",
           # season-over-season chart palette (fallback for --season-N)
           "season_colors_json": _script_json(_season_colors())}
    ctx["vintage_rows"] = _vintage_rows(vs)
    # the "Your datasets" card (built here so /freshness keeps it)
    from app.ui import datasets_ui as _dsu
    ctx.update({"datasets": _dsu.dataset_rows(), "upload": None, "ds": None})
    if not vs:
        return ctx
    latest = vs[-1]
    try:
        ctx["latest"] = _vintage_summary(
            str(state.data_mod.vintage_path(latest)), latest)
    except Exception as e:
        ctx["view_note"] = ("Could not read the latest vintage "
                            f"({type(e).__name__}). The archive may still "
                            "be updating; try again shortly.")
        return ctx
    sel_v = (vintage if _re.fullmatch(r"\d{4}-\d{2}-\d{2}", vintage or "")
             and vintage in vs else latest)
    if vintage and sel_v != vintage:
        ctx["view_note"] = (f"No archived vintage for {vintage}; showing "
                            f"the latest, {latest}.")
    try:
        pv = str(state.data_mod.vintage_path(sel_v))
        names = list(_vintage_locations(pv, sel_v))
        sel_loc = loc if loc in names else (names[0] if names else "")
        if loc and sel_loc != loc:
            note = (f"{ctx['view_note']} " if ctx["view_note"] else "")
            ctx["view_note"] = (note + "That location is not in the "
                                f"{sel_v} vintage; showing {sel_loc}.")
        ctx["sel_vintage"], ctx["sel_loc"] = sel_v, sel_loc
        ctx["loc_names"] = names
        ctx["sel_summary"] = _vintage_summary(pv, sel_v)
        series = _vintage_series(pv, sel_v, sel_loc) if sel_loc else {}
        dates = list(series.get("dates") or [])
        values = list(series.get("values") or [])
        ctx["series_n"] = len(dates)
        # recent weeks, newest first
        ctx["series_table"] = list(zip(dates, values))[-12:][::-1]
        if values:
            pk = max(range(len(values)), key=lambda i: values[i])
            ctx["peak"] = (dates[pk], values[pk])
        # the full series for the Plotly chart
        if values:
            ctx["series_json"] = _script_json(
                {"dates": [str(d)[:10] for d in dates],
                 "values": [float(v) for v in values]})
    except Exception as e:
        ctx["view_note"] = (f"Could not read the {sel_v} vintage "
                            f"({type(e).__name__}).")
    return ctx


def _vintage_rows(vs) -> list:
    """The archive as rows: one per season (August to July), each vintage
    a (week offset from August 1, date) point, newest season first."""
    from datetime import date as _d
    rows = {}
    for v in vs:
        try:
            d = _d.fromisoformat(str(v)[:10])
        except ValueError:
            continue
        y = d.year if d.month >= 8 else d.year - 1
        off = (d - _d(y, 8, 1)).days // 7
        rows.setdefault(y, []).append((off, str(v)[:10]))
    pal = _season_colors() or []          # the player's palette: a list
    out = []
    for i, y in enumerate(sorted(rows, reverse=True)):
        label = f"{y}-{str(y + 1)[2:]}"
        if isinstance(pal, dict):
            color = pal.get(label, "currentColor")
        elif pal and isinstance(pal[0], (list, tuple)):
            color = dict(pal).get(label, "currentColor")
        else:
            color = pal[i % len(pal)] if pal else "currentColor"
        out.append({"season": label, "points": sorted(rows[y]), "color": color})
    return out


@app.get("/data", response_class=HTMLResponse)
def data_page(request: Request, loc: str = "", vintage: str = "",
              source: str = ""):
    if source:
        # browse one custom dataset in the vintage browser's place
        from app.ui import datasets_ui as _dsu
        refused = _dsu.local_only(request)
        if refused:
            return refused
        ds = _dsu.get_dataset(source)
        if ds is not None:
            ctx = _data_context()
            ctx.update(_dsu.data_context(ds, loc, vintage))
            return templates.TemplateResponse(request, "data.html", ctx)
        _flash("That dataset is not stored; showing the FluSight hub.")
    return templates.TemplateResponse(request, "data.html",
                                      _data_context(loc, vintage))


# === Storage (/storage, /runs): inventory, delete, clear, reclaim -> runs.html ===
# The sealed records and the hub clone are never deletable (no control, and
# refused again on POST); running/paused trees are refused server-side.
# Every destructive POST requires a confirmation naming exactly what the
# user saw (name or count); a stale confirmation deletes nothing.

@ttlcache.ttl_cache(ttl_s=60.0)
def _tree_size(path: str) -> int:
    from app.core import retro
    return retro.dir_size(Path(path))


def _storage_protected(p: Path) -> bool:
    """True when a path lies inside a sealed record or the hub clone."""
    from flubnf.settings import HUB
    try:
        rp = Path(p).resolve()
    except OSError:
        return True                      # unresolvable: refuse, never guess
    for root in [base for base, _ in _sealed_roots()] + [HUB]:
        try:
            r = Path(root).resolve()
            if rp == r or rp.is_relative_to(r):
                return True
        except OSError:
            continue
    return False


def _live_workroot_ids() -> set:
    """Workroot directory names a worker may be writing into right now."""
    out = set()
    running = _status.get("running") or ""
    if running and ":" in running:
        out.add(running.split(":", 1)[1])
    w = _status.get("workroot")
    if w:
        out.add(Path(w).name)
    return out


def _storage_inventory() -> dict:
    """Storage panel rows with sizes: workroots, live retro seasons, retro
    archives, report archives, your datasets (each with a busy flag), plus
    the protected trees (no controls). total_bytes/total_h sum the managed
    categories only, each byte once: a dataset adds its own folder (the
    upload and its replays), its runs being counted as workroots."""
    import re as _re
    from app.core import retro
    from app.core.runs import APP_STATE, is_research, run_display
    from app.ui import datasets_ui as _dsu
    from flubnf.settings import HUB
    inv = {"workroots": [], "retro": [], "retro_archives": [],
           "report_archives": [], "datasets": [], "protected": [],
           "total_bytes": 0, "total_h": ""}
    live_ids = _live_workroot_ids()
    console_busy = bool(_status.get("running"))
    # ledger rows label each workroot; one without a row reads as unrecorded
    try:
        led_rows = {r["run_id"]: r for r in Ledger().rows(100_000)}
    except Exception:
        led_rows = {}
    wr = APP_STATE / "workroots"
    if wr.is_dir():
        for p in sorted((d for d in wr.iterdir() if d.is_dir()),
                        key=lambda d: d.name, reverse=True):
            size = _tree_size(str(p))
            inv["total_bytes"] += size
            row = led_rows.get(p.name) or {}
            disp = run_display(p.name, row.get("spec"),
                               row.get("created_utc"))
            inv["workroots"].append({
                "id": p.name, "size_h": retro.human_bytes(size),
                "label": disp["what"], "when": disp["when"],
                "scope": disp["scope"], "recorded": disp["recorded"],
                "research": is_research(row.get("spec", "")),
                "modified": _runs.is_modified(row.get("spec", "")),
                "busy": p.name in live_ids,
                # for the dataset rows: the run's size and its dataset
                "bytes": size, "dataset": _dsu.spec_dataset(row.get("spec"))})
    if retro_seasons.RETRO_ROOT.is_dir():
        for p in sorted(retro_seasons.RETRO_ROOT.iterdir()):
            if not p.is_dir() and not p.is_symlink():
                continue
            if _valid_season(p.name):
                st = _season_status(p.name)
                size = _tree_size(str(p))
                inv["total_bytes"] += size
                inv["retro"].append({
                    "id": p.name, "size_h": retro.human_bytes(size),
                    "status": st, "busy": st in _RETRO_ACTIVE})
                continue
            m = _re.match(r"(\d{4}-\d{2})", p.name)
            if m and retro.archive_stamp_of(p.name, m.group(1)):
                season = m.group(1)
                stamp = retro.archive_stamp_of(p.name, season)
                size = _tree_size(str(p))
                inv["total_bytes"] += size
                inv["retro_archives"].append({
                    "id": p.name, "season": season,
                    "when": retro.stamp_human(stamp),
                    "size_h": retro.human_bytes(size),
                    "busy": _season_status(season) in _RETRO_ACTIVE})
    arch = APP_STATE / "archive"
    for d in reversed(_scan_archive_dates(arch)):
        size = _tree_size(str(arch / d))
        inv["total_bytes"] += size
        inv["report_archives"].append({
            "id": d, "size_h": retro.human_bytes(size),
            "busy": console_busy})
    inv["datasets"] = _dsu.storage_rows(inv["workroots"])
    inv["total_bytes"] += sum(d["own_bytes"] for d in inv["datasets"])
    for label, p in (("Production engine record", retro_seasons.RETRO_RESEAL),
                     ("Sealed validation record", retro_seasons.RETRO_SEAL),
                     ("FluSight hub clone", HUB)):
        if Path(p).exists():
            inv["protected"].append({
                "label": label, "path": str(p),
                "size_h": retro.human_bytes(_tree_size(str(p)))})
    inv["total_h"] = retro.human_bytes(inv["total_bytes"])
    return inv


def _clearable_workroots() -> list:
    """[{"id", "bytes"}] newest first: every workroot except the active
    run's and anything inside a protected tree."""
    from app.core.runs import APP_STATE
    live = _live_workroot_ids()
    out = []
    wr = APP_STATE / "workroots"
    if wr.is_dir():
        for p in sorted((d for d in wr.iterdir() if d.is_dir()),
                        key=lambda d: d.name, reverse=True):
            if p.name in live or _storage_protected(p):
                continue
            out.append({"id": p.name, "bytes": _tree_size(str(p))})
    return out


def _clearable_run_ids(ledger) -> list:
    """Ledger run ids the clear control may remove: all but the active
    run's row."""
    live = _status.get("running") or ""
    out = []
    for r in ledger.rows(100_000):
        rid = r.get("run_id") or ""
        if r.get("status") == "running" and live.endswith(rid) and rid:
            continue
        out.append(rid)
    return out


@app.get("/storage", response_class=HTMLResponse)
@app.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request):
    """Storage tab: storage panel, then the run ledger. /runs is a kept
    alias (old reports and bookmarks link it)."""
    from app.core.runs import APP_STATE, is_research
    from app.core import retro
    ledger = Ledger()
    rows = ledger.rows(50)
    for r in rows:
        # the research badge carries the tag, so the label stays untagged
        r["label"] = _run_label(r["run_id"], r.get("spec", ""), tag=False)
        r["research"] = is_research(r.get("spec", ""))
        r["modified"] = _runs.is_modified(r.get("spec", ""))
        r["chips"] = _outcome_chips(r.get("outcome", ""))
        # a 'running' row with no live worker = the app was closed mid-run
        if r["status"] == "running" and not (_status.get("running") or "").endswith(r["run_id"]):
            r["status"] = "interrupted"
        # a deleted workroot keeps its row and shows a dash for disk use
        w = APP_STATE / "workroots" / r["run_id"]
        r["disk_h"] = (retro.human_bytes(_tree_size(str(w)))
                       if w.is_dir() else None)
    cw = _clearable_workroots()
    return templates.TemplateResponse(request, "runs.html", {
        "active": "Storage", "ledger": rows,
        "clear_count": len(_clearable_run_ids(ledger)),
        "storage": _storage_inventory(),
        # clear-all: count and weight, named by the confirmation
        "clear_workroots": {"count": len(cw),
                            "size_h": retro.human_bytes(
                                sum(w["bytes"] for w in cw))}})


@app.post("/runs/clear")
def runs_clear(request: Request, confirm: str = Form("")):
    """Clear every completed ledger row (confirmation = the count seen).
    Never the active run's row; never deletes workroot data on disk."""
    _invalidate_scans()
    ledger = Ledger()
    ids = _clearable_run_ids(ledger)
    if not ids:
        _flash("The run ledger has no completed rows to clear.")
        return _back(request, "/storage")
    if confirm != str(len(ids)):
        _flash("The ledger changed since this page was rendered "
               f"({len(ids)} clearable row{'' if len(ids) == 1 else 's'} "
               "now). Nothing was cleared; review and confirm again.")
        return _back(request, "/storage")
    n = ledger.delete_runs(ids)
    _invalidate_scans()
    _flash(f"Cleared {n} completed row{'' if n == 1 else 's'} from the run "
           "ledger. No data on disk was deleted: the runs' workroots stay "
           "in the storage panel until deleted there.")
    return _back(request, "/storage")


def _storage_target(kind: str, ident: str):
    """(path, busy_reason) for one storage delete request, after all
    validation EXCEPT the confirmation; (None, message) when refused."""
    import re as _re
    from app.core import retro
    from app.core.runs import APP_STATE
    if kind == "workroot":
        if not _re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", ident or ""):
            return None, "Unrecognized workroot name."
        p = APP_STATE / "workroots" / ident
        if ident in _live_workroot_ids():
            return None, (f"The run {ident} is active; its workroot cannot "
                          "be deleted while it runs.")
        base = APP_STATE / "workroots"
    elif kind == "retro-season":
        if not _valid_season(ident):
            return None, "Unrecognized season name."
        if _season_status(ident) in _RETRO_ACTIVE:
            return None, (f"{ident} is replaying (status: "
                          f"{_season_status(ident)}); stop it first.")
        p = retro_seasons.RETRO_ROOT / ident
        base = retro_seasons.RETRO_ROOT
    elif kind == "retro-archive":
        m = _re.match(r"(\d{4}-\d{2})", ident or "")
        stamp = (retro.archive_stamp_of(ident, m.group(1)) if m else "")
        if not stamp:
            return None, "Unrecognized archived run identifier."
        season = m.group(1)
        if _season_status(season) in _RETRO_ACTIVE:
            return None, (f"{season} is replaying; stop it before deleting "
                          "its archived runs.")
        p = retro_seasons.RETRO_ROOT / ident
        base = retro_seasons.RETRO_ROOT
    elif kind == "report-archive":
        if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", ident or ""):
            return None, "Unrecognized report archive date."
        if _status.get("running"):
            return None, ("A console run is in progress and may be writing "
                          "the archive; stop it first.")
        p = APP_STATE / "archive" / ident
        base = APP_STATE / "archive"
    else:
        return None, "Unrecognized storage kind."
    # Containment by construction (separator-free identifiers). Not resolved
    # here: a symlinked season is legitimate (delete_tree removes the link),
    # but _storage_protected resolves, so a link into a protected tree fails.
    assert p.parent == Path(base), "storage target escaped its parent"
    if _storage_protected(p):
        return None, ("That tree is protected (the sealed validation "
                      "record and the hub clone are never deletable from "
                      "the interface).")
    if not (p.is_dir() or p.is_symlink()):
        return None, "Nothing is on disk under that name."
    return p, ""


@app.post("/storage/delete")
def storage_delete(request: Request, kind: str = Form(""),
                   ident: str = Form(""), confirm: str = Form("")):
    """Delete one storage entry permanently: validate, refuse busy or
    protected, then require the confirmation to name the entry."""
    from app.core import retro
    _invalidate_scans()
    p, why = _storage_target(kind, ident)
    if p is None:
        _flash(f"{why} Nothing was deleted.")
        return _back(request, "/storage")
    if confirm != ident:
        _flash("The deletion was not confirmed, so nothing was deleted.")
        return _back(request, "/storage")
    size_h = retro.human_bytes(retro.dir_size(p))
    try:
        retro.delete_tree(p)
    except Exception as e:
        _flash(f"Could not delete {ident}: {type(e).__name__}: "
               f"{str(e)[:160]}. Nothing else changed.")
        return _back(request, "/storage")
    _invalidate_scans()
    noun = {"workroot": "workroot", "retro-season": "retrospective season",
            "retro-archive": "archived retrospective run",
            "report-archive": "report archive"}.get(kind, "entry")
    tail = (" Its ledger row remains as the run's record."
            if kind == "workroot" else "")
    _flash(f"Deleted the {noun} {ident}: {size_h} freed.{tail}")
    return _back(request, "/storage")


@app.post("/storage/clear-workroots")
def storage_clear_workroots(request: Request, confirm: str = Form("")):
    """Delete every completed run's workroot (confirmation = the count
    seen). Live/protected checks repeat per directory; ledger rows stay."""
    from app.core import retro
    from app.core.runs import APP_STATE
    _invalidate_scans()
    items = _clearable_workroots()
    if not items:
        _flash("No completed run workroots are on disk to delete.")
        return _back(request, "/storage")
    if confirm != str(len(items)):
        _flash("The storage panel changed since this page was rendered "
               f"({len(items)} deletable workroot"
               f"{'' if len(items) == 1 else 's'} now). Nothing was "
               "deleted; review and confirm again.")
        return _back(request, "/storage")
    live = _live_workroot_ids()
    freed, n = 0, 0
    for it in items:
        p = APP_STATE / "workroots" / it["id"]
        # re-checked: a run claimed since the render keeps its workroot
        if it["id"] in live or _storage_protected(p) \
                or not (p.is_dir() or p.is_symlink()):
            continue
        try:
            size = retro.dir_size(p)
            retro.delete_tree(p)
            freed += size
            n += 1
        except Exception:
            continue          # one stuck tree must not sink the sweep
    _invalidate_scans()
    _flash(f"Deleted {n} completed run workroot{'' if n == 1 else 's'}: "
           f"{retro.human_bytes(freed)} freed. Every ledger row is kept "
           "and shows a dash for disk use.")
    return _back(request, "/storage")


# === Storage: reclaim (prune completed intermediates, compress samples) ===
# GET is a dry run by category; POST performs it behind a counts
# confirmation. Classification lives in app/core/reclaim.py; samples gzip
# losslessly with mtimes kept, so every score and export is reproducible.

def _reclaim_skips() -> tuple:
    """(season entry names, workroot names) the reclaim must not touch right
    now: seasons replaying or mid-finalize, and the active run's workroot."""
    skip_seasons = {s for s in retro_seasons._known_seasons()
                    if _season_status(s) in _RETRO_ACTIVE}
    for key, job in list(_results_jobs.items()):
        if job and not job["done"].is_set():
            skip_seasons.add(Path(key).name)
    return skip_seasons, set(_live_workroot_ids())


def _reclaim_survey() -> dict:
    from app.core import reclaim
    from app.core.runs import APP_STATE
    skip_seasons, skip_workroots = _reclaim_skips()
    return reclaim.survey(retro_seasons.RETRO_ROOT, APP_STATE / "workroots",
                          skip_seasons=skip_seasons,
                          skip_workroots=skip_workroots)


@app.get("/api/storage/reclaim")
def api_storage_reclaim():
    """Dry run: what a reclaim would free, by category (no side effects).
    'confirm' must match storage_reclaim's counts token."""
    from app.core import retro
    plan = _reclaim_survey()
    hb = retro.human_bytes
    cats = []
    if plan["week_bytes"]:
        cats.append({
            "label": "Completed-week fit intermediates",
            "bytes": plan["week_bytes"], "bytes_h": hb(plan["week_bytes"]),
            "detail": (f"{plan['weeks']} completed weeks across "
                       f"{len(plan['season_ids'])} season "
                       f"tree{'' if len(plan['season_ids']) == 1 else 's'}")})
    if plan["workroot_bytes"]:
        cats.append({
            "label": "Completed-run workroot intermediates",
            "bytes": plan["workroot_bytes"],
            "bytes_h": hb(plan["workroot_bytes"]),
            "detail": (f"{plan['workroots']} completed "
                       f"run{'' if plan['workroots'] == 1 else 's'}; "
                       "results, reports, and submissions are kept")})
    if plan["compress_files"]:
        cats.append({
            "label": "Stored-sample compression (lossless gzip)",
            "bytes": plan["est_compress_saved"],
            "bytes_h": hb(plan["est_compress_saved"]),
            "detail": (f"{plan['compress_files']} stored weeks, "
                       f"{hb(plan['compress_bytes'])} now; estimated "
                       f"{hb(plan['est_compress_saved'])} freed, every week "
                       "stays scoreable and playable")})
    counts = f"{plan['weeks']}/{plan['workroots']}/{plan['compress_files']}"
    return {"categories": cats, "total": plan["total_est"],
            "total_h": hb(plan["total_est"]), "confirm": counts}


@app.post("/storage/reclaim")
def storage_reclaim(request: Request, confirm: str = Form("")):
    """Perform the reclaim the dry run described (confirmation = its
    weeks/workroots/files counts). Busy and protection rules re-apply per
    entry."""
    from app.core import reclaim, retro
    from app.core.runs import APP_STATE
    _invalidate_scans()
    plan = _reclaim_survey()
    counts = f"{plan['weeks']}/{plan['workroots']}/{plan['compress_files']}"
    if plan["total_est"] <= 0 and plan["compress_files"] == 0:
        _flash("There is nothing to reclaim: no completed week or run "
               "carries intermediates and every stored week is already "
               "compressed.")
        return _back(request, "/storage")
    if confirm != counts:
        _flash("The storage panel changed since this report was made "
               "(a run finished or files moved). Nothing was deleted; "
               "review the reclaim report and confirm again.")
        return _back(request, "/storage")
    skip_seasons, skip_workroots = _reclaim_skips()
    out = reclaim.execute(retro_seasons.RETRO_ROOT, APP_STATE / "workroots",
                          skip_seasons=skip_seasons,
                          skip_workroots=skip_workroots)
    _invalidate_scans()
    hb = retro.human_bytes
    bits = []
    if out["week_bytes"]:
        bits.append(f"{hb(out['week_bytes'])} of fit intermediates from "
                    f"{out['weeks']} completed week"
                    f"{'' if out['weeks'] == 1 else 's'}")
    if out["workroot_bytes"]:
        bits.append(f"{hb(out['workroot_bytes'])} from "
                    f"{out['workroots']} completed run workroot"
                    f"{'' if out['workroots'] == 1 else 's'}")
    if out["compress_files"]:
        bits.append(f"{hb(out['compress_saved'])} by compressing "
                    f"{out['compress_files']} stored week"
                    f"{'' if out['compress_files'] == 1 else 's'} in place")
    _flash(f"Reclaimed {hb(out['total'])}: " + "; ".join(bits) + ". Every "
           "stored week, score, report, and submission file is kept; the "
           "sealed validation record and the hub clone were not touched.")
    return _back(request, "/storage")


# === Console controls: /run/stop, /api/busy, /data/pull, /freshness ===
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


@app.get("/api/busy")
def api_busy():
    """What would a click interrupt now? console_run: the running run's
    label (null when idle); retro: {season: status} for running, stopping
    or paused seasons (paused still holds the engine); phase: the console
    phase (the Update-data guard fires only on 'materializing'/'preparing',
    which read hub files). Seasons come from claims AND on-disk records, so
    a live replay never reads idle."""
    running = _status.get("running")
    live = {}
    for s in retro_seasons._known_seasons():
        st = _season_status(s)
        if st in _RETRO_ACTIVE:
            live[s] = st
    return {
        "console_run": ((_status.get("run_label") or str(running))
                        if running else None),
        "retro": live,
        "phase": _status.get("phase", "") or "",
        "sandbox": _sandbox_live() or None,
    }


@app.post("/data/pull")
def data_pull():
    """Explicit hub update -- looking never pulls; pulling is a button."""
    # server-side mirror of /api/busy under _engine_lock: refuse only while a
    # run starts or reads hub files (materializing/preparing)
    with _engine_lock:
        running = _status.get("running")
        phase = (_status.get("phase") or "").lower()
        if running and (running == "starting"
                        or "materializing" in phase
                        or "preparing" in phase):
            _flash("A run is reading the hub files right now ("
                   + (_status.get("run_label") or str(running))
                   + "). Updating data would change those files mid read; "
                   "nothing was pulled. Try again once fitting starts or "
                   "the run finishes.")
            return RedirectResponse("/data", status_code=303)
    ok, msg = state.data_mod.pull_hub()
    _invalidate_scans()
    if not ok:
        _flash("Updating the hub clone FAILED: "
               + (msg[:200] or "git exited nonzero with no message")
               + ". The local archive is unchanged; check the network and "
               "the hub clone, then try again.")
        return RedirectResponse("/data", status_code=303)
    vs = state.data_mod.vintages()
    from flubnf.settings import HUB as _H
    comp = (" · comparators: baseline "
            + ("ok" if (_H / "model-output/FluSight-baseline").is_dir() else "missing")
            + ", official ensemble "
            + ("ok" if (_H / "model-output/FluSight-ensemble").is_dir() else "missing"))
    _flash(f"{msg[:140]}" + (f" · latest vintage {vs[-1]}" if vs else "") + comp)
    return RedirectResponse("/data", status_code=303)


@app.post("/freshness", response_class=HTMLResponse)
def freshness(request: Request):
    f = state.data_mod.check_freshness()
    return templates.TemplateResponse(request, "data.html",
                                      _data_context(freshness=f))


# === Submission files (the forecast archive: pipeline.py) ===
def _registered_model_ids() -> set:
    """Hub model identities this project may write (directory names), from
    submit.MODEL_ABBR (checked against model-metadata/ by the suite)."""
    from app.core.submit import MODEL_ABBR, hub_model_id
    return {hub_model_id(k) for k in MODEL_ABBR}


def _modified_model_ids() -> set:
    """The non-hub names a run with modified model settings exports under
    (<hub id>-modified, app/core/knobs.py): downloadable, never submittable."""
    return {m + _knobs.MODIFIED_SUFFIX for m in _registered_model_ids()}


def _submission_files(d: Path) -> list:
    """Submission CSVs under a workroot/archive dir, each marked submittable
    iff its directory (the hub model id) is registered. Retired identities
    (NAU-Ensemble, NAU-PF-SIHRS) stay listed as the run's record but are not
    downloadable: the hub would reject them under genuine-looking names.
    A modified run's <hub id>-modified files are downloadable exports
    (`modified`), not submissions."""
    ok = _registered_model_ids()
    mod = _modified_model_ids()
    return [{"model": p.parent.name, "name": p.name, "path": str(p),
             "submittable": p.parent.name in ok,
             "modified": p.parent.name in mod}
            for p in sorted(Path(d).glob("submission/*/*.csv"))]


# === Run pages (/runs/{id}, report, download, rerun) -> run.html ===
@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: str):
    import json as _json
    from app.core.runs import APP_STATE, Ledger
    w = APP_STATE / "workroots" / run_id
    res = {}
    if (w / "results.json").is_file():
        res = _json.loads((w / "results.json").read_text())
    subs = _submission_files(w)
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
    return HTMLResponse(_report_for_serving(d))


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
    return _weekly_report_file(d, date or run_id)


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


# === Output (/output): submissions, downloads, weekly report -> output.html ===
PREVIEW_ROWS = 12


@app.get("/output", response_class=HTMLResponse)
def output_page(request: Request):
    import pandas as pd
    from app.core.runs import APP_STATE
    rid, res = shared._latest_results()
    files = []
    if rid:
        for entry in _submission_files(APP_STATE / "workroots" / rid):
            entry.update({"cols": [], "rows": [], "more": 0})
            try:
                df = pd.read_csv(entry["path"], dtype=str)
                entry["cols"] = list(df.columns)
                entry["rows"] = df.head(PREVIEW_ROWS).fillna("").values.tolist()
                entry["more"] = max(len(df) - PREVIEW_ROWS, 0)
            except Exception:
                pass
            files.append(entry)
    return templates.TemplateResponse(request, "output.html", {
        "active": "Output", "rid": rid,
        # the stored spec lets the label carry the research tag
        "label": _run_label(rid, (res or {}).get("spec", "")) if rid else "",
        "date": (res or {}).get("forecast_date", ""),
        "files": files,
        "archive_dates": list(reversed(_archive_dates())),
        "has_report": bool(rid and (APP_STATE / "workroots" / rid / "report.html").is_file())})


@app.get("/output/download")
def output_download(path: str):
    """Download a submission CSV. The file must be inside app state, and a
    submission/ file must sit under a registered hub model's directory (the
    listings' rule, enforced here for hand-edited URLs)."""
    from fastapi.responses import FileResponse
    from app.core.runs import APP_STATE
    from app.core import datasets as _datasets
    p = Path(path).resolve()
    if not (p.is_relative_to(APP_STATE.resolve()) and p.is_file()):
        return HTMLResponse("<p>file not found in app state</p>", status_code=404)
    if p.is_relative_to(Path(_datasets.ROOT).resolve()):
        # uploaded data is not served here (it may be private)
        return HTMLResponse("<p>file not found in app state</p>", status_code=404)
    if p.parent.parent.name == "submission" \
            and p.parent.name not in _registered_model_ids() \
            and p.parent.name not in _modified_model_ids():
        return HTMLResponse(
            f"<p>{p.parent.name} is not a registered hub model. This file "
            "was written under a retired identity and the hub would reject "
            "it, so it is not offered as a submission. Use Show in Finder "
            "to open it for reference.</p>", status_code=409)
    return FileResponse(p, filename=p.name, media_type="text/csv",
                        content_disposition_type="attachment")


@app.post("/output/reveal")
def output_reveal(path: str = Form(...)):
    """Show the file in Finder / Explorer (a local desktop app)."""
    import subprocess
    from app.core.runs import APP_STATE
    p = Path(path).resolve()
    # containment via is_relative_to, as in /output/download: a string-prefix
    # test would admit siblings such as app/state_defaults
    if p.is_relative_to(APP_STATE.resolve()) and p.exists():
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(p)])
        elif sys.platform == "win32":
            # one argv element: Explorer's /select, has odd comma quoting
            subprocess.Popen(["explorer", f"/select,{p}"])
        else:
            subprocess.Popen(["xdg-open", str(p.parent)])
    return RedirectResponse("/output", status_code=303)


#: report path -> builder-sources mtime of a failed rebuild: retry once per
#: builder change, never per request
_REPORT_REBUILD_FAILED: dict = {}


def _report_for_serving(dirpath: Path) -> str:
    """The stored weekly report, rebuilt in place from its inputs bundle
    when older than the builder sources (report_v2.builder_sources_mtime).
    Without a bundle, report_v2.legacy_theme_carry restyles at serve time
    (file untouched). Any failure serves the stored file: never a 500."""
    from app.core import report_v2
    f = Path(dirpath) / "report.html"
    text = f.read_text()
    try:
        src_m = report_v2.builder_sources_mtime()
        if f.stat().st_mtime >= src_m:
            return text                                    # fresh: verbatim
        b = Path(dirpath) / report_v2.BUNDLE_NAME
        if not b.is_file():
            return report_v2.legacy_theme_carry(text)
        if _REPORT_REBUILD_FAILED.get(str(f)) == src_m:
            return text
        try:
            import json as _json
            bundle = _json.loads(b.read_text())
            if bundle.get("version") not in \
                    report_v2.SUPPORTED_BUNDLE_VERSIONS:
                raise ValueError("unknown report bundle version "
                                 f"{bundle.get('version')!r}")
            report_v2.render_bundle(bundle, f)
            return f.read_text()
        except Exception:
            _REPORT_REBUILD_FAILED[str(f)] = src_m
            return text
    except Exception:
        return text


@app.get("/output/report", response_class=HTMLResponse)
def output_report(date: str = ""):
    """Latest run's report, or ?date=YYYY-MM-DD from the archive (both via
    _report_for_serving)."""
    import re
    from app.core.runs import APP_STATE
    if date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            return HTMLResponse("<p>Invalid date. Expected YYYY-MM-DD.</p>",
                                status_code=400)
        d = APP_STATE / "archive" / date
        if not (d / "report.html").is_file():
            return HTMLResponse(f"<p>No archived report for {date}.</p>")
        return HTMLResponse(_report_for_serving(d))
    rid, _ = shared._latest_results()
    d = APP_STATE / "workroots" / (rid or "")
    if not (d / "report.html").is_file():
        return HTMLResponse("<p>No report yet. Run the models first.</p>")
    return HTMLResponse(_report_for_serving(d))


def _weekly_report_name(date: str) -> str:
    """Saved weekly report name, dated (every run writes report.html)."""
    return f"FluBNF-weekly-report-{date}.html" if date \
        else "FluBNF-weekly-report.html"


def _weekly_report_file(dirpath: Path, date: str):
    """The weekly report as a download, refreshed first (same bytes as the
    page); missing -> 404."""
    from fastapi.responses import FileResponse
    f = Path(dirpath) / "report.html"
    if not f.is_file():
        return HTMLResponse("<p>No report to download.</p>", status_code=404)
    _report_for_serving(dirpath)
    return FileResponse(f, filename=_weekly_report_name(date),
                        media_type="text/html",
                        content_disposition_type="attachment")


@app.get("/output/report/download")
def output_report_download(date: str = ""):
    """/output/report's file, as a download."""
    import re
    from app.core.runs import APP_STATE
    if date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            return HTMLResponse("<p>Invalid date. Expected YYYY-MM-DD.</p>",
                                status_code=400)
        return _weekly_report_file(APP_STATE / "archive" / date, date)
    rid, res = shared._latest_results()
    return _weekly_report_file(APP_STATE / "workroots" / (rid or ""),
                               (res or {}).get("forecast_date", ""))


# === Sandbox (/sandbox): user models on the same engine -> sandbox.html ===
# app/core/sandbox.py; nothing here touches the ledger, Output, retro or seal.
from app.core import sandbox as sandbox_mod                      # noqa: E402


def _sandbox_busy_reason() -> str:
    """Why a sandbox fit may not start now ("" when the engine is free)."""
    if _status.get("running"):
        return "a console run is fitting"
    live = [x for x in retro_seasons._known_seasons()
            if _season_status(x) in _RETRO_ACTIVE]
    if live:
        return "a retrospective replay is running (" + ", ".join(live) + ")"
    return _sandbox_live_reason()


@app.middleware("http")
async def _sandbox_engine_guard(request: Request, call_next):
    """The other half of the two-way engine guard: a console run (/run) or
    a replay (/retro/run) is refused while a sandbox fit holds the engine,
    as those two refuse each other. Requests the same-host guard refuses
    pass through to it untouched."""
    path = request.url.path.rstrip("/")
    if request.method == "POST" and path in ("/run", "/retro/run"):
        origin = request.headers.get("origin")
        local = (_authority_hostname(request.headers.get("host", ""))
                 in _LOCAL_HOSTNAMES
                 and (origin is None
                      or _authority_hostname(origin) in _LOCAL_HOSTNAMES))
        # a plain read: an async middleware must not wait on _engine_lock
        live = _sandbox_live()
        if local and live:
            _flash(f"A sandbox fit holds the engine ({live}). Stop it from "
                   "the Sandbox tab first; nothing was started.")
            return RedirectResponse("/retro" if path == "/retro/run"
                                    else "/forecast", status_code=303)
    return await call_next(request)


def _sandbox_url(model: str = "", run: str = "") -> str:
    """The sandbox page with the model (and run) open."""
    from urllib.parse import quote
    q = []
    if run:
        q.append(f"run={quote(str(run))}")
    if model:
        q.append(f"model={quote(str(model))}")
    return "/sandbox" + ("?" + "&".join(q) if q else "")


def _sandbox_redirect(model: str = "", run: str = "") -> RedirectResponse:
    return RedirectResponse(_sandbox_url(model, run), status_code=303)


def _sandbox_run_dir(run_id: str) -> Path:
    return sandbox_mod.run_dir(run_id)


def _sandbox_save_posted(name: str, model_bngl: str, data_exp: str,
                         priors_conf: str) -> list:
    """Save the editor fields that were posted non-empty (a script or an
    alias posting none blanks nothing); the names of the files saved."""
    files = {f: v for f, v in (("model.bngl", model_bngl),
                               ("data.exp", data_exp),
                               ("priors.conf", priors_conf))
             if (v or "").strip()}
    if files:
        sandbox_mod.save_model(name, files)
    return sorted(files)


@app.get("/sandbox", response_class=HTMLResponse)
def sandbox_page(request: Request, run: str = "", model: str = "",
                 dataset: str = "", compare: str = ""):
    """The gallery (no model) or one model's workbench (?model=): the
    editor, its run settings, its runs and their results (with ?compare=
    a second run overlaid and diffed), its diagram."""
    live = _sandbox_status.get("running")
    models = sandbox_mod.list_models()
    editing = None
    if model:
        try:
            editing = {"name": sandbox_mod.check_name(model),
                       **sandbox_mod.read_model(model)}
        except Exception as e:
            _flash(str(e))
            model = ""
    all_runs = sandbox_mod.list_runs(live=live)
    last = {}
    for r in all_runs:
        last.setdefault(r.get("model"), r)
    runs = [r for r in all_runs if r.get("model") == model][:25] if model else []
    res = None
    try:
        if run:
            res = sandbox_mod.results(_sandbox_run_dir(run), live=live)
            if model and res["meta"].get("model") != model:
                res = None
        elif runs:
            res = sandbox_mod.results(sandbox_mod.RUNS / runs[0]["run_id"],
                                      live=live)
    except Exception as e:
        _flash(f"That sandbox run could not be read: {e}")
        res = None
    # a second run of the same model, overlaid and diffed against the open one
    cmp, diff = None, None
    if res and compare and compare != res["run_id"]:
        try:
            cmp = sandbox_mod.results(_sandbox_run_dir(compare), live=live)
            if cmp["meta"].get("model") != res["meta"].get("model"):
                raise sandbox_mod.SandboxError(
                    f"{compare} is a run of another model")
            diff = sandbox_mod.diff_runs(compare, res["run_id"])
        except Exception as e:
            _flash(f"Not compared: {e}")
            cmp, diff = None, None
    ctx = {"active": "Sandbox", "models": models, "last": last,
           "examples": sandbox_mod.list_examples(), "runs": runs,
           "res": res, "res_json": _script_json(res or {}),
           "cmp": cmp, "cmp_json": _script_json(cmp or {}), "diff": diff,
           "editing": editing, "busy": _sandbox_busy_reason(),
           "running_id": live,
           # the Oracle SIHRS start (the gallery's New model form)
           "vintages": sandbox_mod.vintages(),
           "locations": sandbox_mod.locations(),
           "datasets": sandbox_mod.dataset_choices()}
    if res:
        ctx["oracle"] = sandbox_mod.read_oracle(res["run_id"])
        ctx["oracle_gate"] = sandbox_mod.oracle_gate(res["run_id"])
        ctx["oracle_w_production"] = sandbox_mod.oracle_default_w()
        ctx["oracle_w"] = (ctx["oracle"] or {}).get(
            "w", ctx["oracle_w_production"])
    if editing:
        name = editing["name"]
        try:
            times = [r[0] for r in
                     sandbox_mod.read_exp(editing["data.exp"])["rows"]]
        except Exception:
            times = None
        try:
            settings = sandbox_mod.engine_settings(editing["priors.conf"],
                                                   times=times)
        except Exception:
            settings = []
        # the run form starts from this model's newest run, else a quick
        # check (a shipped start: its production seed, 4 forecast weeks)
        prev = runs[0] if runs else {}
        shipped = sandbox_mod.shipped_state(name, {
            f: editing[f] for f in sandbox_mod.REQUIRED})
        form = {"particles": int(prev.get("particles")
                                 or sandbox_mod.DRY_RUN_PARTICLES),
                "jitter": prev.get("jitter", 0.15),
                "forecast_weeks": prev.get("forecast_weeks", 4),
                "seed": prev.get("seed", shipped["info"].get("seed", 0)
                                 if shipped["shipped"] else 0)}
        ctx.update({
            "shipped": shipped,
            "info": sandbox_mod.read_info(name),
            "note": next((m["note"] for m in models if m["name"] == name), ""),
            "origin": next((m["origin"] for m in models if m["name"] == name), ""),
            "settings": settings, "form": form,
            "presets": {"quick": sandbox_mod.DRY_RUN_PARTICLES,
                        "full": sandbox_mod.FULL_FIT_PARTICLES},
            # seconds at the reference 10,000 particles; the page scales it
            "eta_full": round(sandbox_mod.eta_seconds(
                len(times or []), sandbox_mod.FULL_FIT_PARTICLES), 1),
            # the archive as a data source (empty lists with no hub)
            "locations": sandbox_mod.locations(),
            "vintages": sandbox_mod.vintages(),
            "data_range": sandbox_mod.default_range(sandbox_mod.vintages()),
            "data_source": sandbox_mod.read_data_source(name),
            # your own data: stored datasets, and an upload's refusal
            "datasets": sandbox_mod.dataset_choices(),
            "pick_dataset": dataset,
            "upload_report": _sandbox_upload_report.pop(name, None),
            "upload_mb": sandbox_mod.UPLOAD_MAX_BYTES // (1024 * 1024)})
    return templates.TemplateResponse(request, "sandbox.html", ctx)


@app.post("/sandbox/add-example")
def sandbox_add_example(request: Request, name: str = Form(...)):
    """Kept for scripts and old pages: an example under its own name."""
    try:
        sandbox_mod.add_example(name)
        _flash(f"Example {name} copied into the sandbox.")
        return _sandbox_redirect(name)
    except Exception as e:
        _flash(str(e))
        return _sandbox_redirect()


@app.post("/sandbox/new")
def sandbox_new(request: Request, name: str = Form(...),
                start: str = Form("skeleton"), location: str = Form(""),
                forecast_date: str = Form(""), season_start: str = Form(""),
                group: str = Form(""), as_of: str = Form("")):
    """A new model: the skeleton (fits as written), a copy of a shipped
    example (example:<name>) or of a sandbox model (copy:<name>), or the
    Oracle SIHRS filter as production builds it for one hub location and
    forecast date (shipped:sihrs) or one group of a stored dataset with a
    population (shipped:dataset:<id>, as of as_of)."""
    name = (name or "").strip()
    kind, _, what = (start or "skeleton").partition(":")
    try:
        if kind == "shipped" and what == "sihrs":
            sandbox_mod.from_shipped(name, location, forecast_date,
                                     season_start=season_start)
            _flash(f"{name}: the Oracle SIHRS filter for {location.strip()} "
                   f"as of {forecast_date.strip()}.")
        elif kind == "shipped" and what.startswith("dataset:"):
            sandbox_mod.from_shipped(name, group, as_of,
                                     season_start=season_start,
                                     dataset=what.split(":", 1)[1])
            _flash(f"{name}: the Oracle SIHRS filter for {group.strip()} "
                   f"as of {as_of.strip()}.")
        elif kind == "example":
            sandbox_mod.add_example(what, as_name=name)
            _flash(f"{name} copied from the example {what}.")
        elif kind == "copy":
            sandbox_mod.copy_model(what, name)
            _flash(f"{name} copied from {what}.")
        elif kind == "skeleton":
            sandbox_mod.new_model(name)
            _flash(f"{name} written from the skeleton.")
        else:
            raise sandbox_mod.SandboxError(f"{start!r} is not a way to start")
        return _sandbox_redirect(name)
    except Exception as e:
        _flash(str(e))
        return _sandbox_redirect(what if kind == "copy" else "")


@app.post("/sandbox/models/{name}/delete")
def sandbox_delete_model(name: str, confirm: str = Form("")):
    """Delete a model with its runs (never while one of them fits)."""
    if confirm != name:
        _flash("Not deleted: the confirmation did not name the model.")
        return _sandbox_redirect(name)
    try:
        n = sandbox_mod.delete_model(name, live=_sandbox_status.get("running"))
        _flash(f"Deleted {name}" + (f" and its {n} run{'' if n == 1 else 's'}"
                                    if n else "") + ".")
        return _sandbox_redirect()
    except Exception as e:
        _flash(str(e))
        return _sandbox_redirect(name)


@app.post("/sandbox/runs/{run_id}/delete")
def sandbox_delete_run(run_id: str, confirm: str = Form("")):
    """Delete one run folder (never the live fit)."""
    if confirm != run_id:
        _flash("Not deleted: the confirmation did not name the run.")
        return _sandbox_redirect()
    try:
        model = sandbox_mod.delete_run(run_id, live=_sandbox_status.get("running"))
        _flash(f"Deleted sandbox run {run_id}.")
        return _sandbox_redirect(model)
    except Exception as e:
        _flash(str(e))
        return _sandbox_redirect()


@app.post("/sandbox/models/{name}/save")
def sandbox_save(request: Request, name: str,
                 model_bngl: str = Form(""), data_exp: str = Form(""),
                 priors_conf: str = Form("")):
    try:
        sandbox_mod.save_model(name, {"model.bngl": model_bngl,
                                      "data.exp": data_exp,
                                      "priors.conf": priors_conf})
        _flash(f"Saved {name}.")
    except Exception as e:
        _flash(str(e))
    return _sandbox_redirect(name)


@app.post("/api/sandbox/models/{name}/check")
def api_sandbox_check(name: str, model_bngl: str = Form(""),
                      data_exp: str = Form(""), priors_conf: str = Form("")):
    """Check the posted editor text (each field falling back to the saved
    file) without the engine: JSON problems, warnings and facts."""
    try:
        files = sandbox_mod.read_model(name)
        for f, v in (("model.bngl", model_bngl), ("data.exp", data_exp),
                     ("priors.conf", priors_conf)):
            if (v or "").strip():
                files[f] = v.replace("\r\n", "\n")
        return sandbox_mod.check(files, work=sandbox_mod.SANDBOX / "check")
    except Exception as e:
        return JSONResponse({"ok": False, "problems": [str(e)[:1500]],
                             "warnings": [], "facts": {}}, status_code=200)


def _sandbox_fill_flash(info: dict) -> None:
    if info["asof"] == "dataset":
        what = f"dataset {info['dataset']['name']}"
    elif info["asof"] == "settled":
        what = "settled truth"
    else:
        what = f"vintage of {info['asof']}"
    msg = (f"data.exp filled: {info['location']}, {info['start']} to "
           f"{info['end']}, {what}, {info['rows']} weeks")
    if info["dropped"]:
        msg += f", {info['dropped']} missing weeks dropped"
    if info.get("population_set"):
        msg += f"; N set to {info['population_set']:,}"
    if info.get("kind") == "rate":
        msg += (" (rates, not counts: the default objfunc expects counts; "
                "set objfunc in priors.conf)")
    _flash(msg)


@app.post("/sandbox/models/{name}/fill-data")
def sandbox_fill_data(request: Request, name: str, location: str = Form(""),
                      start: str = Form(""), end: str = Form(""),
                      source: str = Form("settled"), group: str = Form(""),
                      model_bngl: str = Form(""), data_exp: str = Form(""),
                      priors_conf: str = Form(""), set_pop: str = Form("")):
    """data.exp from the hub archive (one location, settled truth or one
    vintage) or from a stored dataset (source=dataset:<id>, one group).
    Missing weeks dropped and counted, never imputed. The editor's other
    fields are saved first, so unsaved edits survive the fill (data.exp
    gives its header only). set_pop also sets the model's N to the
    location's population (refused for a model that derives i0 from N)."""
    pop = bool(set_pop)
    src = (source or "settled").strip()
    try:
        saved = _sandbox_save_posted(name, model_bngl, data_exp, priors_conf)
        if saved:
            _flash(f"Saved {', '.join(saved)} first.")
        if src.startswith("dataset:"):
            info = sandbox_mod.fill_data(name, (group or "").strip(),
                                         (start or "").strip(),
                                         (end or "").strip(),
                                         dataset=src.split(":", 1)[1],
                                         set_pop=pop)
        else:
            info = sandbox_mod.fill_data(
                name, (location or "").strip(), (start or "").strip(),
                (end or "").strip(), asof=None if src == "settled" else src,
                set_pop=pop)
        _sandbox_fill_flash(info)
    except Exception as e:
        _flash(str(e))
    return _sandbox_redirect(name)


#: an upload's refusal, shown inline in the Load data box on the next view
#: of that model (popped once shown)
_sandbox_upload_report: dict = {}

#: the request body cap: the CSV's own cap plus room for the editor text
#: that rides along in the same form
_SANDBOX_BODY_SLACK = 4 * 1024 * 1024


class _SandboxTooLarge(Exception):
    pass


async def _sandbox_capped_form(request: Request, cap: int):
    """The multipart form, refused before reading when Content-Length says
    it is over the cap, and cut off while reading past it (a chunked body
    has no length to trust)."""
    from starlette.requests import Request as _Req
    cl = request.headers.get("content-length", "")
    if cl.strip().isdigit() and int(cl) > cap:
        raise _SandboxTooLarge()
    seen = 0
    receive = request.receive

    async def capped():
        nonlocal seen
        msg = await receive()
        if msg.get("type") == "http.request":
            seen += len(msg.get("body", b"") or b"")
            if seen > cap:
                raise _SandboxTooLarge()
        return msg
    return await _Req(request.scope, capped).form(
        max_files=1, max_fields=40, max_part_size=_SANDBOX_BODY_SLACK)


@app.post("/sandbox/models/{name}/upload-data")
async def sandbox_upload_data(request: Request, name: str):
    """A CSV of your own (grouped date,target_group,value[,population] or
    hubverse), validated and stored through the dataset store, then loaded
    into data.exp when it holds one group (else the Load data box offers
    it to pick a group). The size cap holds before and while reading; the
    client's file name is never used as a path."""
    from starlette.concurrency import run_in_threadpool
    from starlette.datastructures import UploadFile
    cap = sandbox_mod.UPLOAD_MAX_BYTES
    try:
        sandbox_mod.check_name(name)
        form = await _sandbox_capped_form(request, cap + _SANDBOX_BODY_SLACK)
    except _SandboxTooLarge:
        _sandbox_upload_report[name] = {"problems": [
            f"The upload is larger than the {cap // (1024 * 1024)} MB limit; "
            "nothing was read past it or stored."]}
        return _sandbox_redirect(name)
    except Exception as e:
        _flash(f"The upload could not be read: {e}")
        return _sandbox_redirect(name if sandbox_mod.NAME_RE.match(name) else "")
    try:
        saved = await run_in_threadpool(
            _sandbox_save_posted, name, str(form.get("model_bngl") or ""),
            str(form.get("data_exp") or ""), str(form.get("priors_conf") or ""))
        if saved:
            _flash(f"Saved {', '.join(saved)} first.")
    except Exception as e:
        _flash(str(e))
        return _sandbox_redirect(name)
    up = form.get("csv")
    if not isinstance(up, UploadFile) or not up.filename:
        _sandbox_upload_report[name] = {"problems": ["Choose a CSV file to upload."]}
        return _sandbox_redirect(name)
    kind = str(form.get("kind") or "")          # '' = from the values
    try:
        ds = await run_in_threadpool(sandbox_mod.ingest_upload, up.file,
                                     up.filename, kind, cap)
    except sandbox_mod.UploadRefused as e:
        _sandbox_upload_report[name] = {"problems": e.problems or [str(e)]}
        return _sandbox_redirect(name)
    finally:
        await up.close()
    warn = list(ds.meta.get("warnings") or [])
    if len(ds.groups) == 1:
        try:
            info = await run_in_threadpool(sandbox_mod.fill_data, name,
                                           ds.groups[0], "", "",
                                           dataset=ds.id)
            _sandbox_fill_flash(info)
        except Exception as e:
            _flash(str(e))
    else:
        _flash(f"Stored {ds.name} ({len(ds.groups)} groups); pick a group "
               "under Load data.")
    if warn:
        _sandbox_upload_report[name] = {"problems": [], "warnings": warn}
    return RedirectResponse(_sandbox_url(name) + f"&dataset={ds.id}",
                            status_code=303)


def _sandbox_start(name: str, *, particles: int, jitter: float,
                   forecast_weeks: int, seed: int) -> RedirectResponse:
    """Claim the engine (under _engine_lock, before preparing), prepare the
    run, then fit it on a background thread. Stop during preparation
    cancels the run before the engine sees it."""
    with _engine_lock:
        why = _sandbox_busy_reason()
        if why:
            _flash(f"Not started: {why}. The sandbox waits for the engine.")
            return _sandbox_redirect(name)
        _sandbox_status.update(claim=name, cancel=False)
    try:
        workroot = sandbox_mod.prepare(name, particles=particles,
                                       jitter=jitter,
                                       forecast_weeks=forecast_weeks,
                                       seed=seed)
    except Exception as e:
        with _engine_lock:
            _sandbox_status.update(claim=None, cancel=False)
        _flash(f"Not started: {e}")
        return _sandbox_redirect(name)
    run_id = workroot.name
    with _engine_lock:
        cancelled = _sandbox_status.get("cancel")
        _sandbox_status.update(claim=None, cancel=False,
                               running=None if cancelled else run_id)
    if cancelled:
        sandbox_mod.mark(workroot, "stopped")
        _flash(f"Sandbox run {run_id} was stopped before it started.")
        return _sandbox_redirect(name, run_id)

    def _go():
        guard = pipeline._sleep_guard()  # a full fit must outlive the lid
        try:
            sandbox_mod.run(workroot)
        finally:
            if guard is not None:
                try:
                    guard.terminate()
                except Exception:
                    pass
            with _engine_lock:
                if _sandbox_status.get("running") == run_id:
                    _sandbox_status["running"] = None

    threading.Thread(target=_go, daemon=True, name=f"sandbox-{run_id}").start()
    _flash(f"Sandbox run {run_id} started with "
           f"{max(50, min(int(particles), 100_000))} particles.")
    return _sandbox_redirect(name, run_id)


@app.post("/sandbox/run")
def sandbox_run(request: Request, model: str = Form(...),
                particles: int = Form(sandbox_mod.DRY_RUN_PARTICLES),
                jitter: float = Form(0.15), forecast_weeks: int = Form(4),
                seed: int = Form(0)):
    """Kept for scripts and old pages: run a model's saved files."""
    return _sandbox_start(model, particles=particles, jitter=jitter,
                          forecast_weeks=forecast_weeks, seed=seed)


@app.post("/sandbox/models/{name}/run")
def sandbox_model_run(name: str, model_bngl: str = Form(""),
                      data_exp: str = Form(""), priors_conf: str = Form(""),
                      particles: int = Form(sandbox_mod.DRY_RUN_PARTICLES),
                      jitter: float = Form(0.15), forecast_weeks: int = Form(4),
                      seed: int = Form(0)):
    """Save and run: the posted editor fields are saved first (the run's
    workroot keeps its own copy), then the run starts as /sandbox/run's."""
    try:
        saved = _sandbox_save_posted(name, model_bngl, data_exp, priors_conf)
        if saved:
            _flash(f"Saved {name}.")
    except Exception as e:
        _flash(f"Not saved, not started: {e}")
        return _sandbox_redirect(name)
    return _sandbox_start(name, particles=particles, jitter=jitter,
                          forecast_weeks=forecast_weeks, seed=seed)


@app.post("/sandbox/runs/{run_id}/stop")
def sandbox_run_stop(run_id: str):
    """Stop the live fit named here (the STOP flag execute polls)."""
    model = ""
    try:
        d = _sandbox_run_dir(run_id)
        model = sandbox_mod.results(d)["meta"].get("model", "")
        with _engine_lock:
            live = _sandbox_status.get("running") == run_id
        if live:
            sandbox_mod.stop(d)
            _flash(f"Stopping sandbox run {run_id}; it ends at the next "
                   "safe point.")
        else:
            _flash(f"Sandbox run {run_id} is not fitting; nothing to stop.")
    except Exception as e:
        _flash(str(e))
    return _sandbox_redirect(model, run_id if model else "")


@app.post("/sandbox/stop")
def sandbox_stop():
    """Stop whatever the sandbox has on the engine (the guard modal's
    Stop): the live fit, or a run still being prepared."""
    with _engine_lock:
        running = _sandbox_status.get("running")
        if not running and _sandbox_status.get("claim"):
            _sandbox_status["cancel"] = True
    if running:
        try:
            sandbox_mod.stop(_sandbox_run_dir(running))
        except Exception:
            pass
    return _sandbox_redirect()


@app.get("/api/sandbox/models/{name}/contactmap")
def api_sandbox_contactmap(name: str):
    """The model's contact map as an inline SVG, drawn by BNG2.pl's
    visualize action on a copy of the model (no engine, no run); cached
    by the model text until it changes."""
    from app.core import contactmap
    try:
        files = sandbox_mod.read_model(name)
        bngl = files["model.bngl"]
        hit = sandbox_mod.cached_view(name, "contactmap", bngl)
        if hit is not None:
            return hit
        work = sandbox_mod.SANDBOX / "contactmap" / sandbox_mod.check_name(name)
        cm = contactmap.parse(contactmap.graphml_from_bngl(bngl, work))
        out = {"svg": contactmap.svg(cm), "molecules": len(cm["molecules"]),
               "bonds": len(cm["bonds"]), "graph": contactmap.contact_graph(cm)}
        sandbox_mod.store_view(name, "contactmap", bngl, out)
        return out
    except Exception as e:
        return JSONResponse({"error": str(e)[:1500]}, status_code=200)


@app.get("/api/sandbox/models/{name}/network")
def api_sandbox_network(name: str):
    """BNG2.pl's generated reaction network as inline SVG (generate-only
    copy, no run); too large -> counts and a note. "graph" always returned.
    Cached by the model text until it changes."""
    from app.core import contactmap
    try:
        files = sandbox_mod.read_model(name)
        bngl = files["model.bngl"]
        hit = sandbox_mod.cached_view(name, "network", bngl)
        if hit is not None:
            return hit
        work = sandbox_mod.SANDBOX / "contactmap" / sandbox_mod.check_name(name)
        net = contactmap.parse_net(contactmap.network_from_bngl(bngl, work))
        drawing = contactmap.svg_network(net)
        out = {"svg": drawing if drawing.startswith("<svg") else "",
               "species": len(net["species"]), "reactions": len(net["reactions"]),
               "graph": contactmap.network_graph(net)}
        if not out["svg"]:
            out["note"] = drawing
        sandbox_mod.store_view(name, "network", bngl, out)
        return out
    except Exception as e:
        return JSONResponse({"error": str(e)[:1500]}, status_code=200)


@app.get("/api/sandbox/runs/{run_id}")
def api_sandbox_run(run_id: str):
    try:
        return sandbox_mod.results(_sandbox_run_dir(run_id),
                                   live=_sandbox_status.get("running"))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=404)


def _sandbox_local_get(request: Request) -> bool:
    """A download is served only to a localhost Host (and Origin, when
    sent): GET stays open elsewhere, but a model or a run is the user's
    own files, not for a DNS-rebinding page to read."""
    origin = request.headers.get("origin")
    return (_authority_hostname(request.headers.get("host", ""))
            in _LOCAL_HOSTNAMES
            and (origin is None
                 or _authority_hostname(origin) in _LOCAL_HOSTNAMES))


def _sandbox_zip(data: bytes, filename: str):
    from fastapi.responses import Response
    return Response(data, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store"})


@app.get("/sandbox/models/{name}/download")
def sandbox_model_download(request: Request, name: str):
    """The model's three files and sidecars as a zip."""
    if not _sandbox_local_get(request):
        return PlainTextResponse("Refused: not a localhost request.\n",
                                 status_code=403)
    try:
        return _sandbox_zip(sandbox_mod.model_zip(name), f"{name}.zip")
    except Exception as e:
        return PlainTextResponse(f"{e}\n", status_code=404)


@app.get("/sandbox/runs/{run_id}/download")
def sandbox_run_download(request: Request, run_id: str):
    """A run's inputs, engine outputs and summary.csv as a zip."""
    if not _sandbox_local_get(request):
        return PlainTextResponse("Refused: not a localhost request.\n",
                                 status_code=403)
    try:
        return _sandbox_zip(sandbox_mod.run_zip(run_id), f"{run_id}.zip")
    except Exception as e:
        return PlainTextResponse(f"{e}\n", status_code=404)


@app.post("/sandbox/runs/{run_id}/oracle")
def sandbox_run_oracle(run_id: str, w: str = Form("")):
    """The production Oracle step on a finished run of an unedited Oracle
    SIHRS start, inside the run folder only (sandbox, not a submission):
    nothing reaches the ledger, the site, the archive or model-output."""
    model = ""
    try:
        model = str(sandbox_mod.results(_sandbox_run_dir(run_id))["meta"]
                    .get("model", ""))
        try:
            wv = float(w) if str(w).strip() else None
        except ValueError:
            raise sandbox_mod.SandboxError(f"w must be a number, not {w!r}")
        out = sandbox_mod.oracle_step(run_id, wv)
        _flash(f"Oracle step applied to {run_id} with w = {out['w']:g} "
               "(sandbox, not a submission).")
    except Exception as e:
        _flash(f"Oracle step not applied: {e}")
    return _sandbox_redirect(model, run_id if model else "")


def _sandbox_storage_line() -> dict:
    """The Storage panel's read-only sandbox line (kept out of its total:
    the sandbox's runs are deleted from the sandbox, not from there)."""
    from app.core import retro
    try:
        s = sandbox_mod.storage()
    except Exception:
        return {}
    return {**s, "size_h": retro.human_bytes(s["bytes"])} if s["bytes"] else {}


templates.env.globals["sandbox_storage"] = _sandbox_storage_line


# === Models (/models, /model/{name}) -> model.html ===
@app.get("/models", response_class=HTMLResponse)
def models_page(request: Request):
    """The Models tab, defaulting to the PF view; /model/<name> routes stay
    live (reports and bookmarks link them)."""
    return model_page(request, "pf")


@app.get("/model/{name}", response_class=HTMLResponse)
def model_page(request: Request, name: str):
    ot = _oracle_text
    rec = ot.RECORD
    blurbs = {
        "pf": ("Oracle SIHRS",
               "The SIHRS compartment model (Susceptible, Infected, "
               "Hospitalized, Recovered, with seasonal transmission and "
               "waning immunity, written in BNGL) is fitted each week by "
               "PyBNF's particle filter from August 1 through the newest week "
               "of NHSN admissions as archived on the forecast date. The "
               "Oracle step then gives each forecast sample path one donor "
               "growth path from an earlier season at the same calendar week, "
               "the calendar-donor principle the Groundhog uses, and grows it "
               "at the geometric mean of the two, propagated from the "
               "filter's own current state. The Groundhog applies donor "
               "growth ratios to the last observed count instead; the two are "
               "submitted as separate models and nothing is blended between "
               "them."),
        "analogue": ("Groundhog",
                     "The empirical model: it pools, across all states, the "
                     "weeks of earlier seasons within two epiweeks of the "
                     "forecast date and scales the latest value by the "
                     "quantiles of their growth to each horizon, with no "
                     "epidemic mechanism. Donors are NHSN admissions (2021-22 "
                     "excluded: the archive holds only its growth phase) and "
                     "a committed FluSurv-NET bank shrunk to the admissions "
                     "scale, at equal weight. Three-season relWIS vs the "
                     "FluSight baseline on 15,340 cells: 0.722, 0.653 and "
                     "0.651, pooled 0.666 (0.771 without the FluSurv-NET "
                     "donors)."),
        "pf2s": ("Two-strain SIHRS",
                 "A research variant, not a shipped model: influenza A and B "
                 "as independent SIHRS circuits whose admissions sum, fitted "
                 "to NHSN admissions and NREVSS typed positives. It scored "
                 "worse on the full grid (relWIS 0.719 against 0.704 for the "
                 "two-member blend it was tested in), so it is kept for "
                 "research runs only."),
    }
    # no page for the retired blend (LosAlamos_NAU-CModel_Flu, see ENGINES)
    # one-line summaries: the collapsed <details> summary on each model tab
    onelines = {
        "pf": ("The mechanistic model: the SIHRS compartment model fitted "
               "weekly by a particle filter, its forecast growth blended with "
               "donor growth from past seasons at the same calendar week."),
        "analogue": ("The empirical model: it scales the latest observation "
                     "by historical growth ratios from matching calendar "
                     "weeks, with banked FluSurv-NET donors."),
        "pf2s": ("A research variant, not shipped: influenza A and B as "
                 "parallel SIHRS circuits fitted to two data channels."),
    }
    # where each model tab points into the Methods page
    manchor = {"pf": "oracle", "analogue": "analogue",
               "pf2s": "two-strain"}
    if name not in blurbs:
        return HTMLResponse("unknown model", status_code=404)
    rid, res = shared._latest_results()
    fanq = {}
    if res and name in res.get("models", {}):
        fanq = {loc: qs for loc, qs in res["models"][name].items()
                if all(isinstance(v, dict) for v in qs.values())}
    # the member overlay belonged to the retired blend's page: always empty
    overlay = {}
    form = dict(_last_form) or {"forecast_date": _default_forecast_date(),
                                "locations": ["all"], "replicates": 3}
    # BNGL-backed models show their template source, read at render time
    bngl_files = {"pf": "SIHRS_pop_min.bngl",
                  "pf2s": "SIHRS_pop_2strain_min.bngl"}
    bngl_src, bngl_file = "", bngl_files.get(name, "")
    if bngl_file:
        try:
            bngl_src = (REPO / "flubnf" / "templates" / bngl_file).read_text(
                encoding="utf-8")
        except OSError:
            bngl_src, bngl_file = "", ""
    return templates.TemplateResponse(request, "model.html", {
        "active": "Models", "name": name,
        # title from the shared model-name map
        "title": templating._model_names().get(name, blurbs[name][0]),
        "blurb": blurbs[name][1],
        "model_names_json": _script_json(templating._model_names()),
        "member_colors_json": _script_json(_member_colors()),
        "oneline": onelines[name], "manchor": manchor[name],
        # the research run control (research_run.html) lives ONLY on the
        # two-strain view, never on the Forecast form
        "research_panel": name == "pf2s",
        "rid": rid,
        "label": _run_label(rid, (res or {}).get("spec", "")) if rid else "",
        "date": (res or {}).get("forecast_date", ""),
        "fanq_json": _script_json(fanq),
        "overlay_json": _script_json(overlay),
        "run_obs_json": _script_json((res or {}).get("observed", {})),
        "bngl_src": bngl_src, "bngl_file": bngl_file,
        "form": form, "status": _status})


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
