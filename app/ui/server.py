"""FastAPI operations console -- landing, freshness, settings, run, tabs.

Server-rendered (locked decision: FastAPI + templates, no build chain).
Run:  .venv/bin/uvicorn app.ui.server:app --port 8710
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from fastapi import BackgroundTasks, FastAPI, Form, Request     # noqa: E402
from fastapi.responses import HTMLResponse, RedirectResponse    # noqa: E402
from fastapi.templating import Jinja2Templates                  # noqa: E402

from app.core import data as data_mod                           # noqa: E402
from app.core.runs import Ledger, RunSpec, lease_workroot       # noqa: E402

app = FastAPI(title="FluBNF")
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")),
          name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["pop_flash"] = lambda: _status.pop("flash", None)

ENGINES = ("all", "pf", "amcmc")     # "all" = pf + analogue + ensemble
_status: dict = {"running": None, "log": []}
_last_form: dict = {}


def _component_versions() -> dict:
    """Installed versions of the components named in user-facing copy,
    resolved once per process at import. Console packages come from this
    interpreter (importlib.metadata); pybnf and bngsim from the engine venv's
    interpreter; BioNetGen from the VERSION file beside BNG2.pl. Anything
    unresolvable reports 'not installed' instead of raising."""
    from importlib.metadata import PackageNotFoundError, version
    out = {}
    for pkg in ("fastapi", "jinja2", "plotly", "pandas", "numpy"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = "not installed"
    out["bionetgen"] = "not installed"
    try:
        from flubnf.settings import BNG
        vf = Path(BNG).parent / "VERSION"
        if vf.is_file():
            out["bionetgen"] = vf.read_text().strip()
        elif Path(BNG).exists():
            out["bionetgen"] = "installed"
    except Exception:
        pass
    out["pybnf"] = out["bngsim"] = "not installed"
    try:
        import json as _json
        import subprocess
        from flubnf.settings import PY_ENGINE
        if Path(PY_ENGINE).exists():
            code = ("import json\n"
                    "from importlib.metadata import version\n"
                    "d = {}\n"
                    "for p in ('pybnf', 'bngsim'):\n"
                    "    try: d[p] = version(p)\n"
                    "    except Exception: d[p] = 'not installed'\n"
                    "print(json.dumps(d))")
            r = subprocess.run([str(PY_ENGINE), "-c", code],
                               capture_output=True, text=True, timeout=15)
            out.update(_json.loads(r.stdout.strip() or "{}"))
    except Exception:
        pass
    return out


VERSIONS = _component_versions()


def _default_forecast_date() -> str:
    """Latest Saturday, clamped to the latest ARCHIVED vintage -- during the
    off-season the hub stops publishing, and a default that points at a
    nonexistent vintage greets the user with an error (laptop field test,
    2026-08-18)."""
    import datetime as dt
    d = dt.date.today()
    sat = str(d - dt.timedelta(days=(d.weekday() - 5) % 7))
    vs = data_mod.vintages()
    return min(sat, vs[-1]) if vs else sat


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """PyBNF brand kit favicon (the small-size mark, loop omitted per the
    kit's minimum-size rule)."""
    from fastapi.responses import FileResponse
    ico = Path(__file__).parent / "static" / "brand" / "favicon.ico"
    return FileResponse(ico, media_type="image/x-icon")


def _outlook_cards(res: dict | None) -> dict:
    """fips -> hover card for svg_map, colored by the latest run's categorical
    outlook (ensemble if present, else pf). States without results -- and the
    no-results-at-all case -- get empty cards, so the caller always renders the
    full silhouette."""
    import pandas as pd
    from app.core.report import categorical_probs
    from app.core.report_v2 import CATS
    _l = pd.read_csv(__import__("flubnf.settings",
                                fromlist=["LOCATIONS"]).LOCATIONS, dtype=str)
    n2f = dict(zip(_l.location_name, _l.location.str.zfill(2)))
    n2a = dict(zip(_l.location_name, _l.abbreviation))
    n2p = dict(zip(_l.location_name, _l.population.astype(float)))
    models = (res or {}).get("models", {})
    picked = models.get("ensemble") or models.get("pf") or {}
    observed = (res or {}).get("observed", {})
    cards = {}
    for loc, qd in picked.items():
        fips = n2f.get(loc, "")
        q1 = (qd or {}).get("1")
        obs = observed.get(loc) or []
        # tolerate the pre-quantile results schema (medians-only floats)
        if len(fips) != 2 or not isinstance(q1, dict) or not obs:
            continue
        lo = float(obs[-1][1])
        vals = [float(v) for v in q1.values()]
        probs = categorical_probs(vals, lo, int(n2p[loc]), 1)
        med1 = float(q1.get("0.5", vals[len(vals) // 2]))
        hover = (f"<b>{loc}</b><br>current: {lo:.0f}"
                 f"<br>1-wk median: {med1:.0f}<br>" +
                 "<br>".join(f"{c.replace('_',' ')}: {probs.get(c,0):.0%}"
                             for c in CATS))
        cards[fips] = {"probs": probs, "name": loc, "abbr": n2a.get(loc, ""),
                       "fips": fips, "hover_html": hover}
    for name, fips in n2f.items():
        if len(fips) == 2:
            cards.setdefault(fips, {"name": name, "abbr": n2a.get(name, ""),
                                    "fips": fips})
    return cards


def _diagram_data(res: dict | None) -> dict:
    """Annotation feed for the home page's interactive SIHRS diagram: per
    location, the latest run's fitted-parameter posterior medians (harvested
    into results.json at run time), the last observed admissions point, and
    the 1-week median from the same model the outlook cards use. Empty when
    no run exists; the diagram then renders unannotated with a hint."""
    out = {"date": "", "has_pf2s": False, "locations": {}, "order": []}
    if not res:
        return out
    try:
        out["date"] = res.get("forecast_date", "") or ""
        params = res.get("params") or {}
        pf_p = params.get("pf") or {}
        p2_p = params.get("pf2s") or {}
        models = res.get("models") or {}
        out["has_pf2s"] = bool(p2_p) or bool(models.get("pf2s"))
        observed = res.get("observed") or {}
        picked = models.get("ensemble") or models.get("pf") or {}
        for loc in set(pf_p) | set(p2_p) | set(observed) | set(picked):
            e = {}
            if isinstance(pf_p.get(loc), dict) and pf_p[loc]:
                e["pf"] = pf_p[loc]
            if isinstance(p2_p.get(loc), dict) and p2_p[loc]:
                e["pf2s"] = p2_p[loc]
            obs = observed.get(loc) or []
            if obs:
                e["obs"] = obs[-1]
            q1 = (picked.get(loc) or {}).get("1")
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


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    try:
        _, res = _latest_results()
    except Exception:
        res = None
    # a real map as the hero graphic: latest run's outlook if one exists,
    # otherwise the empty-country silhouette
    map_svg, outlook_date = "", ""
    try:
        from app.core.usmap import svg_map
        cards = {}
        try:
            cards = _outlook_cards(res)
            if any(c.get("probs") for c in cards.values()):
                outlook_date = (res or {}).get("forecast_date", "")
        except Exception:
            pass                      # no LOCATIONS/hub -> bare silhouette
        with_data = {c["abbr"] for c in cards.values() if c.get("probs")}
        map_svg = ("<div style='max-width:880px;margin:0 auto'>"
                   "<script>window.MAP_LINK='/output/report';</script>"
                   + svg_map(cards, clickable=with_data) + "</div>")
    except Exception:
        pass
    return templates.TemplateResponse(request, "home.html", {
        "active": "Home", "map_svg": map_svg, "outlook_date": outlook_date,
        "versions": VERSIONS, "diagram": _diagram_data(res),
        "missing": __import__("flubnf.settings", fromlist=["check"]).check(verbose=False)})


@app.get("/methods", response_class=HTMLResponse)
def methods_page(request: Request):
    """Methodology reference: the SIHRS model, the fitting machinery, the
    ensemble, and the data and verification policies."""
    return templates.TemplateResponse(request, "methods.html", {
        "active": "Methods", "versions": VERSIONS})


@app.get("/forecast", response_class=HTMLResponse)
def forecast_page(request: Request):
    import pandas as pd
    from flubnf.settings import LOCATIONS
    try:
        _l = pd.read_csv(LOCATIONS, dtype=str)
        all_locs = list(_l.location_name[(_l.location.str.len() == 2)
                                         & (_l.abbreviation != "US")])
    except Exception:
        all_locs = []
    form = dict(_last_form) or {"forecast_date": _default_forecast_date(),
                                "locations": ["all"], "engine": "all",
                                "weeks_to_drop": 0, "weeks_to_nowcast": 0,
                                "replicates": 3, "members": 2}
    rid, res = _latest_results()
    # data panel: full series for the CURRENTLY SELECTED locations, straight
    # from the latest vintage -- visible before any run (deciding what to
    # drop requires seeing the data)
    import json as _json
    # the data panel's own dropdown defaults to US national -- seed it so the
    # panel paints without a fetch; form locations stay seeded for the fans
    sel = ["US (national)"] + [l for l in form["locations"] if l != "all"]
    series = {}
    try:
        vs = data_mod.vintages()
        tdf = pd.read_csv(data_mod.vintage_path(vs[-1]), dtype={"location": str})
        tdf["location"] = tdf["location"].str.zfill(2)
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
    if res and _status.get("session_ran"):
        for mname, md in res["models"].items():
            good = {loc: qs for loc, qs in md.items()
                    if all(isinstance(v, dict) for v in qs.values())}
            if good:
                fanq[mname] = good
    ledger_rows = Ledger().rows(5)
    for r in ledger_rows:
        r["label"] = _run_label(r["run_id"], r.get("spec", ""))
        r["chips"] = _outcome_chips(r.get("outcome", ""))
        if r["status"] == "running" and not (_status.get("running") or "").endswith(r["run_id"]):
            r["status"] = "interrupted"
    return templates.TemplateResponse(request, "forecast.html", {
        "active": "Forecast", "engines": ENGINES, "status": _status,
        "ledger": ledger_rows, "all_locs": all_locs, "form": form,
        "series_json": _json.dumps(series), "fanq_json": _json.dumps(fanq),
        "run_obs_json": _json.dumps((res or {}).get("observed", {})),
        "fc_date": (res or {}).get("forecast_date", "")})


@app.get("/data", response_class=HTMLResponse)
def data_page(request: Request):
    vs = data_mod.vintages()
    return templates.TemplateResponse(request, "data.html", {
        "active": "Data", "latest_vintage": vs[-1] if vs else "none",
        "n_vintages": len(vs), "freshness": None})


@app.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request):
    rows = Ledger().rows(50)
    for r in rows:
        r["label"] = _run_label(r["run_id"], r.get("spec", ""))
        r["chips"] = _outcome_chips(r.get("outcome", ""))
        # a 'running' row with no live worker = the app was closed mid-run
        if r["status"] == "running" and not (_status.get("running") or "").endswith(r["run_id"]):
            r["status"] = "interrupted"
    return templates.TemplateResponse(request, "runs.html", {
        "active": "Runs", "ledger": rows})


@app.post("/run/stop")
def run_stop():
    w = _status.get("workroot")
    running = _status.get("running") or ""
    if w and running.startswith("amcmc"):
        # the adaptive-MCMC engine runs as one subprocess and ignores STOP
        # files -- say so instead of letting the button silently no-op
        _status["phase"] = ("Adaptive MCMC cannot be stopped mid-run. "
                            "It finishes on its own and records its result.")
    elif w and running:
        (Path(w) / "STOP").touch()
        if (Path(w) / "pf2s").is_dir():        # the two-strain pass polls its
            (Path(w) / "pf2s" / "STOP").touch()  # own subdir for the flag
        _status["phase"] = "stopping…"
    elif running == "starting" and not w:
        # a claim with no worker behind it (engine setup never happened) --
        # release it so one stray click doesn't wedge the console
        _status["running"] = None
        _status["run_label"] = ""
        _status["expected_total"] = None
        _status["phase"] = ""
    return RedirectResponse("/forecast#results", status_code=303)


@app.get("/api/busy")
def api_busy():
    """Per-button guard support: what would a click interrupt right now?
    console_run is the running console run's label (null when idle), retro
    maps season to status for seasons currently running or stopping, and
    phase is the console run's current phase string. The Update-data guard
    fires only while the phase contains 'materializing' or 'preparing':
    those phases read hub files that a pull mutates, whereas a pull during
    pure fitting is safe."""
    running = _status.get("running")
    return {
        "console_run": ((_status.get("run_label") or str(running))
                        if running else None),
        "retro": {s: st for s, st in _retro_status.items()
                  if st in ("running", "stopping")},
        "phase": _status.get("phase", "") or "",
    }


@app.post("/data/pull")
def data_pull():
    """Explicit hub update -- looking never pulls; pulling is a button."""
    msg = data_mod.pull_hub()
    vs = data_mod.vintages()
    from flubnf.settings import HUB as _H
    comp = (" · comparators: baseline "
            + ("ok" if (_H / "model-output/FluSight-baseline").is_dir() else "missing")
            + ", official ensemble "
            + ("ok" if (_H / "model-output/FluSight-ensemble").is_dir() else "missing"))
    _flash(f"{msg[:140]}" + (f" · latest vintage {vs[-1]}" if vs else "") + comp)
    return RedirectResponse("/data", status_code=303)


@app.post("/freshness", response_class=HTMLResponse)
def freshness(request: Request):
    f = data_mod.check_freshness()
    vs = data_mod.vintages()
    return templates.TemplateResponse(request, "data.html", {
        "active": "Data", "latest_vintage": vs[-1] if vs else "none",
        "n_vintages": len(vs), "freshness": f})


def _phase(msg):
    _status["phase"] = msg


def _flash(msg: str) -> None:
    """Human-voiced notice for the next page the user sees; the log keeps
    the permanent record."""
    _status["flash"] = msg
    _status["log"].append(msg)


def _back(request: Request, fallback: str) -> RedirectResponse:
    """Redirect to the page the form was posted from (validated local path),
    so a button never yanks the user off the page they were on."""
    from urllib.parse import urlsplit
    path = urlsplit(request.headers.get("referer", "")).path
    ok = path.startswith("/") and not path.startswith("//")
    return RedirectResponse(path if ok else fallback, status_code=303)


def _harvest_params(workroot: Path) -> dict:
    """Per-location posterior medians of the fitted PF parameters, pooled
    across replicates (every params_<rep>.txt under each cell's
    out/Results/A_MCMC/Runs). Feeds the interactive model diagram.
    Non-fatal by design: an unreadable cell is skipped, and a location with
    no readable params files is simply absent from the result."""
    import json as _json
    import numpy as _np
    try:
        cells = _json.loads((workroot / "cells.json").read_text())
    except Exception:
        return {}
    pooled: dict = {}
    for c in cells:
        try:
            loc = c["location"]
            runs = Path(c["dir"]) / "out" / "Results" / "A_MCMC" / "Runs"
            for pfile in sorted(runs.glob("params_*.txt")):
                with open(pfile) as fh:
                    names = fh.readline().replace("#", " ").split()
                arr = _np.atleast_2d(_np.loadtxt(str(pfile), skiprows=1))
                if arr.size == 0 or arr.shape[1] != len(names):
                    continue
                for j, name in enumerate(names):
                    col = arr[:, j]
                    col = col[_np.isfinite(col)]
                    if col.size:
                        pooled.setdefault(loc, {}).setdefault(
                            name.removesuffix("__FREE"), []).append(col)
        except Exception:
            continue
    return {loc: {name: float(_np.median(_np.concatenate(chunks)))
                  for name, chunks in by_name.items()}
            for loc, by_name in pooled.items()}


def _sleep_guard():
    """Hold macOS awake while a long background run works: spawn
    `caffeinate -i -w <this pid>`, which blocks idle sleep until this
    process exits. Returns the Popen for the caller to terminate() when the
    work ends, or None off macOS or on any spawn failure -- no run may ever
    depend on the guard (overnight laptop retrospectives die to closed-lid
    or idle sleep otherwise)."""
    import os
    import subprocess
    if sys.platform != "darwin":
        return None
    try:
        return subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except Exception:
        return None


def _run_all(spec: RunSpec) -> None:
    """The competition path: engines in ascending cost, then ensemble,
    submissions, and the weekly report. Every step lands in ONE workroot and
    ONE ledger row."""
    import pandas as pd
    from app.core import ensemble as ens
    from app.core import scoring
    from app.core.engines import analogue as an_engine
    from app.core.engines import pf as pf_engine
    from app.core.submit import (quantile_rows, rows_from_quantiles,
                                 write_submission)

    ledger = Ledger()
    run_id = None
    outcome = {}
    guard = _sleep_guard()          # macOS: no idle sleep mid-run
    n_states = sum(1 for l in spec.locations
                   if str(l).upper() not in ("US", "US (NATIONAL)"))
    _status["run_label"] = (
        f"{spec.forecast_date} · {n_states} state(s) + US"
        if n_states < len(spec.locations)
        else f"{spec.forecast_date} · {len(spec.locations)} location(s)")
    try:
        # setup INSIDE the try: a failed ledger insert or workroot lease must
        # release the running claim in the finally, not wedge it until restart
        run_id = ledger.open_run(spec, Path("pending"), {"engines": "pf,analogue"})
        workroot = lease_workroot(run_id)
        _status["running"] = f"all:{run_id}"
        _status["workroot"] = str(workroot)
        # 1. PF (primary) -- gracefully absent on Tier-A machines (no engine
        # venv): the run proceeds with the analogue and says so, rather than
        # erroring on the first click of a fresh install.
        from flubnf.settings import PY_ENGINE, PYBNF
        fails = {}
        # observed admissions per location (vintage-true) -- used by the
        # output floor, the report's state pages, and the run page
        obs = {}
        try:
            from flubnf.settings import LOCATIONS as _LOCCSV
            from app.core.data import vintage_path as _vpo
            _lo = pd.read_csv(_LOCCSV, dtype=str)
            _n2fo = dict(zip(_lo.location_name, _lo.location.str.zfill(2)))
            tdf = pd.read_csv(_vpo(spec.forecast_date),
                              dtype={"location": str})
            tdf["location"] = tdf["location"].str.zfill(2)
            import numpy as _npo
            for loc in spec.locations:
                g = tdf[tdf.location == _n2fo.get(loc, "")].sort_values("date").tail(15)
                obs[loc] = [[str(r.date)[:10], float(r.value)]
                            for r in g.itertuples()
                            if _npo.isfinite(r.value)]
        except Exception:
            pass
        pf_samples = {}
        params: dict = {}     # fitted-parameter medians per member/location
        if spec.engine in ("all", "pf") and PY_ENGINE.exists() and PYBNF.exists():
            _phase("materializing models (BNG network generation)")
            pf_engine.prepare(spec, workroot)
            _phase(f"filtering {len(spec.locations)} location(s) × "
                   f"{spec.replicates} replicate(s)")
            status = pf_engine.execute(workroot)
            fails = {k: v for k, v in status.items() if v != "ok"}
            outcome["pf_cells"] = len(status)
            outcome["pf_failures"] = fails
            pf_samples = pf_engine.collect(workroot)
            try:
                params["pf"] = _harvest_params(workroot)
            except Exception:
                pass          # the diagram goes without; the forecast stands
            # output floor: no cell leaves as a point mass (see app/core/floor.py)
            from app.core.floor import floor_samples
            pf_samples = {loc: floor_samples(
                              s, loc, spec.forecast_date,
                              recent=[v for _, v in obs.get(loc, [])])
                          for loc, s in pf_samples.items()}
        else:
            outcome["pf_skipped"] = ("analogue-only run"
                                     if spec.engine == "analogue"
                                     else "engine venv not installed (Tier A)")
            (workroot / "cells.json").write_text("[]")
        # 1b. optional third member: the two-strain SIHRS (panel-validated).
        # Same engine, spec.extra variant switch, sibling subdir of the SAME
        # workroot so the run stays one ledger row and one archive entry.
        pf2s_samples = {}
        if ((spec.extra or {}).get("members") == 3
                and spec.engine in ("all", "pf")
                and PY_ENGINE.exists() and PYBNF.exists()):
            from dataclasses import replace as _dc_replace
            spec2s = _dc_replace(spec, extra={**(spec.extra or {}),
                                              "variant": "2strain"})
            w2 = workroot / "pf2s"
            w2.mkdir()
            _phase("materializing the two-strain member (BNG network generation)")
            pf_engine.prepare(spec2s, w2)
            _phase(f"fitting the two-strain member: {len(spec.locations)} "
                   f"location(s) × {spec.replicates} replicate(s)")
            status2s = pf_engine.execute(w2)
            fails2s = {k: v for k, v in status2s.items() if v != "ok"}
            outcome["pf2s_cells"] = len(status2s)
            outcome["pf2s_failures"] = fails2s
            fails.update({f"pf2s:{k}": v for k, v in fails2s.items()})
            pf2s_samples = pf_engine.collect(w2)
            try:
                params["pf2s"] = _harvest_params(w2)
            except Exception:
                pass
            from app.core.floor import floor_samples as _floor2s
            pf2s_samples = {loc: _floor2s(
                                s, loc, spec.forecast_date,
                                recent=[v for _, v in obs.get(loc, [])])
                            for loc, s in pf2s_samples.items()}
        _phase("consulting the calendar analogue")
        from app.core.floor import floor_quantiles
        an_q = {loc: floor_quantiles(q) for loc, q in an_engine.run(spec).items()}
        # 3. ensemble (vincentize: equal weights, never fitted)
        import pandas as _pd
        _l = _pd.read_csv(__import__("flubnf.settings", fromlist=["LOCATIONS"]).LOCATIONS, dtype=str)
        n2f_pre = dict(zip(_l.location_name, _l.location.str.zfill(2)))
        members_by_loc = {}
        for loc in spec.locations:
            m = {}
            if loc in pf_samples:
                m["pf"] = ens.member_quantiles_from_samples(pf_samples[loc])
            if loc in an_q:
                m["analogue"] = an_q[loc]
            if loc in pf2s_samples:
                m["pf2s"] = ens.member_quantiles_from_samples(pf2s_samples[loc])
            if m:
                # equal, never-fitted weights at every member count: 50/50
                # for the two-member blend, equal thirds with the two-strain
                # member (the sealed recipe; fitting the weights scored
                # worse, pooled relWIS 0.717 against 0.704)
                members_by_loc[loc] = ens.vincentize(
                    m, weights=ens.equal_weights(m),
                    location_fips=n2f_pre.get(loc, ''))
        _phase("vincentizing the ensemble and writing submissions")
        # 4. submissions (identity in the path)
        locs = pd.read_csv(__import__("flubnf.settings",
                                      fromlist=["LOCATIONS"]).LOCATIONS,
                           dtype=str)
        n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
        subs = {}
        for model_id, rows in (
            ("PF-SIHRS", [r for loc, s in pf_samples.items()
                          for r in quantile_rows(s, n2f[loc], spec.forecast_date)]),
            ("Ensemble", [r for loc, q in members_by_loc.items()
                          for r in rows_from_quantiles(q, n2f[loc],
                                                       spec.forecast_date)]),
        ):
            if rows:
                subs[model_id] = str(write_submission(
                    rows, model_id, "NAU", spec.forecast_date,
                    workroot / "submission"))
        outcome["submissions"] = subs
        # 5. retrospective scoring (populates once truth exists). Contained:
        # a scoring hiccup must never erase the forecast itself -- results.json
        # and the archive land after this point (same pattern as step 5b).
        df = pd.DataFrame()
        try:
            truth, name2fips = scoring.load_truth()
            df = scoring.score_samples(pf_samples, spec.forecast_date,
                                       name2fips, truth)
            if not df.empty:
                outcome["pf_relwis"] = round(float(df.wis.sum() / df.base_wis.sum()), 3)
            df.to_json(workroot / "scores_pf.json")
        except Exception as e:
            outcome["score_error"] = str(e)[:200]
        # 5b. weekly report: map + hover cards + WIS card (fans arrive with
        # the per-state drill-down pages; keep the report honest meanwhile)
        try:
            from app.core.report import categorical_probs
            from app.core.report_v2 import CATS, build_report
            from app.core.scoring import summary_table_html
            n2a = dict(zip(locs.location_name, locs.abbreviation))
            n2p = dict(zip(locs.location_name,
                           locs.population.astype(float)))
            cards = {}
            for loc, s in pf_samples.items():
                import numpy as _np
                med1 = float(_np.median(_np.asarray(s["1"], float)))
                lo = next(c["last_observed"] for c in
                          __import__("json").loads(
                              (workroot / "cells.json").read_text())
                          if c["location"] == loc)
                probs = categorical_probs(s["1"], lo, int(n2p[loc]), 1)
                hover = (f"<b>{loc}</b><br>current: {lo:.0f}"
                         f"<br>1-wk median: {med1:.0f}<br>" +
                         "<br>".join(f"{c.replace('_',' ')}: "
                                     f"{probs.get(c,0):.0%}" for c in CATS))
                cards[n2a[loc]] = {"probs": probs, "name": loc,
                                   "abbr": n2a[loc], "fips": n2f[loc],
                                   "hover_html": hover}
            for name, abbr in n2a.items():
                cards.setdefault(abbr, {"name": name, "abbr": abbr,
                                        "fips": n2f.get(name, "")})
            wis_html = ("<div class='card'><h2>forecast accuracy "
                        "(retrospective)</h2>" + summary_table_html(df)
                        + "</div>")
            # state pages: fan + categorical bar + recent-data table per location
            from app.core.report_v2 import cat_bar, fan_figure
            # settled outcomes for backdated runs: the LATEST vintage's values
            # past the forecast origin, framed to the 4-week horizon
            settled_by_loc = {}
            try:
                _vs_all = data_mod.vintages()
                if _vs_all and _vs_all[-1] > spec.forecast_date:
                    from datetime import date as _sd, timedelta as _st
                    _lim = (_sd.fromisoformat(spec.forecast_date)
                            + _st(days=35)).isoformat()
                    ldf = pd.read_csv(data_mod.vintage_path(_vs_all[-1]),
                                      dtype={"location": str})
                    ldf["location"] = ldf["location"].str.zfill(2)
                    for loc in spec.locations:
                        g = ldf[(ldf.location == n2f.get(loc, "")) &
                                (ldf.date > spec.forecast_date) &
                                (ldf.date <= _lim)].sort_values("date")
                        pts = [(str(r.date)[:10], float(r.value))
                               for r in g.itertuples()
                               if pd.notna(r.value)]
                        if pts:
                            settled_by_loc[loc] = pts
            except Exception:
                settled_by_loc = {}
            details = {}
            for loc, s in pf_samples.items():
                fips_l = n2f.get(loc, "")
                obs_pairs = (obs.get(loc) or [])[-12:]
                from datetime import date as _dd, timedelta as _tdd
                o_t = [d for d, _ in obs_pairs]
                o_v = [v for _, v in obs_pairs]
                _base = (_dd.fromisoformat(o_t[-1]) if o_t
                         else _dd.fromisoformat(spec.forecast_date))
                f_t = [(_base + _tdd(days=7 * h)).isoformat()
                       for h in (1, 2, 3, 4)]
                samples_h = {f_t[h - 1]: s[str(h)] for h in (1, 2, 3, 4)}
                try:
                    fan = fan_figure(o_t, o_v, f_t, samples_h,
                                     title=f"{loc}: weekly admissions",
                                     settled=settled_by_loc.get(loc))
                    lo_l = o_v[-1] if o_v else 0.0
                    import numpy as _np3
                    probs_l = categorical_probs(
                        _np3.asarray(s["1"], float), lo_l,
                        int(n2p.get(loc, 1e6)), 1)
                    key = "US" if fips_l == "US" else n2a.get(loc, loc)
                    meds = [float(_np3.median(_np3.asarray(s[str(h)], float)))
                            for h in (1, 2, 3, 4)]
                    note = ("Off-season: the model finds no sustained "
                            "transmission. This forecast reflects the recent "
                            "reporting background, not epidemic growth."
                            if max(meds) <= 2 else "")
                    details[key] = {
                        "name": "United States" if fips_l == "US" else loc,
                        "note": note,
                        "fan": fan, "cat": cat_bar(probs_l),
                        "table_rows": [(d, v) for d, v in obs_pairs[-6:]]}
                except Exception:
                    continue
            nat_html = ""
            try:
                from app.core.usmap import national_svg
                us_names = [n for n in pf_samples if n2f.get(n) == "US"] or                            [n for n in pf_samples if "US" in n or "national" in n.lower()]
                if us_names:
                    un = us_names[0]
                    import numpy as _np2
                    arr = _np2.asarray(pf_samples[un]["1"], float)
                    lo_us = next((c["last_observed"] for c in
                                  __import__("json").loads(
                                      (workroot / "cells.json").read_text())
                                  if c["location"] == un), 0.0)
                    us_pop = float(_l0 := 340_000_000)
                    probs_us = categorical_probs(arr, lo_us, int(us_pop), 1)
                    hover_us = ("<b>United States</b><br>current: "
                                f"{lo_us:.0f}<br>1-wk median: "
                                f"{float(_np2.median(arr)):.0f}")
                    nat_html = national_svg({"probs": probs_us,
                                             "name": "United States",
                                             "abbr": "US", "fips": "US",
                                             "hover_html": hover_us})
            except Exception:
                nat_html = ""
            us_d = details.get("US", {})
            build_report(spec.forecast_date, cards, details,
                         {"fan": us_d.get("fan"), "acc": None,
                          "note": us_d.get("note", ""),
                          "summary_html": wis_html},
                         workroot / "report.html",
                         national_map_html=nat_html)
            outcome["report"] = str(workroot / "report.html")
        except Exception as e:
            outcome["report_error"] = str(e)[:200]
        # 6. results index for the run page
        import json as _json
        import numpy as _np
        def _qs_from_samples(s):
            out = {}
            for h in ("1", "2", "3", "4"):
                a = _np.asarray(s.get(h, []), float); a = a[_np.isfinite(a)]
                if a.size:
                    out[h] = {q: float(_np.quantile(a, float(q)))
                              for q in ("0.1", "0.25", "0.5", "0.75", "0.9")}
            return out
        def _qs_from_q(qd):
            return {h: {q: qd[h][float(q)]
                        for q in ("0.1", "0.25", "0.5", "0.75", "0.9")}
                    for h in qd}
        import os as _os
        _tmp = workroot / "results.json.tmp"
        _tmp.write_text(_json.dumps({
            "spec": spec.to_json(), "forecast_date": spec.forecast_date,
            "observed": obs,
            "params": params,
            "models": {
                "pf": {loc: _qs_from_samples(s) for loc, s in pf_samples.items()},
                "analogue": {loc: _qs_from_q(q) for loc, q in an_q.items()},
                **({"pf2s": {loc: _qs_from_samples(s)
                             for loc, s in pf2s_samples.items()}}
                   if pf2s_samples else {}),
                "ensemble": {loc: _qs_from_q(q) for loc, q in members_by_loc.items()},
            }}))
        _os.replace(_tmp, workroot / "results.json")   # readers never see a half-write
        # 7. forecast archive: one folder per forecast_date, latest run wins
        try:
            outcome["archived"] = _archive_run(workroot, spec.forecast_date)
        except Exception as e:
            outcome["archive_error"] = str(e)[:200]
        _status["session_ran"] = run_id
        ledger.close_run(run_id, "failed" if fails else "ok", outcome)
        _status["log"].append(
            f"{run_id}: pf {len(pf_samples)} loc, analogue {len(an_q)}, "
            + (f"pf2s {len(pf2s_samples)}, " if pf2s_samples else "")
            + f"ensemble {len(members_by_loc)}"
            + (f", relWIS {outcome['pf_relwis']}" if "pf_relwis" in outcome else ""))
    except Exception as e:
        from app.core.engines.pf import RunStopped
        if run_id is None:
            _status["log"].append(f"run setup failed: {str(e)[:200]}")
        elif isinstance(e, RunStopped):
            ledger.close_run(run_id, "stopped", outcome)
            _status["log"].append("run stopped by user")
        else:
            ledger.close_run(run_id, "error", {"error": str(e)[:300], **outcome})
            _status["log"].append(f"{run_id}: ERROR {e}")
    finally:
        if guard is not None:
            try:
                guard.terminate()
            except Exception:
                pass
        _status["running"] = None
        _status["phase"] = ""
        _status["workroot"] = None
        _status["run_label"] = ""
        _status["expected_total"] = None


def _archive_run(workroot: Path, forecast_date: str) -> str:
    """Copy the run's deliverables to app/state/archive/<forecast_date>/,
    replacing any earlier archive for the same date."""
    import shutil
    from app.core.runs import APP_STATE
    arch = APP_STATE / "archive" / forecast_date
    if arch.exists():
        shutil.rmtree(arch)
    arch.mkdir(parents=True)
    for name in ("results.json", "report.html"):
        if (workroot / name).is_file():
            shutil.copy2(workroot / name, arch / name)
    if (workroot / "submission").is_dir():
        shutil.copytree(workroot / "submission", arch / "submission")
    return str(arch)


def _archive_dates() -> list:
    import re
    from app.core.runs import APP_STATE
    root = APP_STATE / "archive"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name))


@app.get("/api/archive/dates")
def api_archive_dates():
    return _archive_dates()


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: str):
    import json as _json
    from app.core.runs import APP_STATE, Ledger
    w = APP_STATE / "workroots" / run_id
    res = {}
    if (w / "results.json").is_file():
        res = _json.loads((w / "results.json").read_text())
    subs = [{"model": p.parent.name, "file": p.name, "abs": str(p)}
            for p in sorted(w.glob("submission/*/*.csv"))]
    report = (w / "report.html").name if (w / "report.html").is_file() else None
    status, err = "", ""
    for r in Ledger().rows(200):
        if r.get("run_id") == run_id:
            status = r.get("status", "")
            try:
                err = _json.loads(r.get("outcome") or "{}").get("error", "")
            except Exception:
                err = ""
            break
    return templates.TemplateResponse(request, "run.html", {
        "active": "Runs", "run_id": run_id, "status": status, "error": err,
        "label": _run_label(run_id), "models": res.get("models", {}),
        "subs": subs, "report": report})


@app.get("/runs/{run_id}/report", response_class=HTMLResponse)
def run_report(run_id: str):
    from app.core.runs import APP_STATE
    f = APP_STATE / "workroots" / run_id / "report.html"
    return HTMLResponse(f.read_text() if f.is_file()
                        else "<p>no report for this run</p>")


@app.get("/api/series")
def api_series(locs: str = ""):
    """Data-panel series for arbitrary locations -- lets the checkboxes drive
    the plots live instead of waiting for a Run click."""
    import json as _json
    import pandas as pd
    sel = [l for l in locs.split("|") if l][:8] or ["Ohio"]
    out = {}
    try:
        _l = pd.read_csv(__import__("flubnf.settings",
                                    fromlist=["LOCATIONS"]).LOCATIONS, dtype=str)
        n2f_ = dict(zip(_l.location_name, _l.location.str.zfill(2)))
        n2f_["US (national)"] = "US"
        vs = data_mod.vintages()
        tdf = pd.read_csv(data_mod.vintage_path(vs[-1]), dtype={"location": str})
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
           "label": _status.get("run_label", "")}
    if w:
        done = total = 0
        t0 = None
        for f in (glob.glob(w + "/status_*.json.prog")
                  + glob.glob(w + "/pf_status.json.prog")
                  + glob.glob(w + "/pf2s/pf_status.json.prog")):
            try:
                d = _json.loads(open(f).read())
                done += d["done"]; total += d["total"]
                t0 = min(t0 or d["t0"], d["t0"])
            except Exception:
                pass
        # stable denominator claimed at run start (locations x replicates);
        # discovered shard totals only ever grow toward it
        total = max(total, int(_status.get("expected_total") or 0))
        out["done"], out["total"] = done, total
        if done and total and t0:
            rate = (_time.time() - t0) / done
            out["eta_s"] = int(rate * (total - done))
    elif _status.get("expected_total"):
        # run claimed but workroot not created yet: report 0/N, not silence
        out["done"], out["total"] = 0, int(_status["expected_total"])
    return out


def _run_label(run_id: str, spec_json: str = "") -> str:
    """Humans read dates, not hashes: '2026-07-04 · Aug 18 09:31'."""
    import json as _json
    when = f"{run_id[4:6]}-{run_id[6:8]} {run_id[9:11]}:{run_id[11:13]}"
    try:
        s = _json.loads(spec_json)
        return f"{s.get('forecast_date','run')} · {when}"
    except Exception:
        return when


def _outcome_chips(outcome_json: str) -> str:
    import json as _json
    try:
        o = _json.loads(outcome_json) if isinstance(outcome_json, str) else outcome_json
    except Exception:
        return ""
    bits = []
    if "pf_cells" in o:
        n = o["pf_cells"]
        bits.append(f"PF {n} fit{'s' if n != 1 else ''}")
    if o.get("pf_failures"): bits.append(f"{len(o['pf_failures'])} failures")
    if o.get("pf_skipped"): bits.append("PF skipped (no engine)")
    if o.get("submissions"): bits.append(f"{len(o['submissions'])} submissions")
    if o.get("report"): bits.append("report ✓")
    if o.get("pf_relwis"): bits.append(f"relWIS {o['pf_relwis']}")
    if o.get("error"): bits.append("error: " + str(o["error"])[:80])
    return " · ".join(bits)


def _latest_results():
    import json as _json
    from app.core.runs import APP_STATE
    # newest first; a half-written or corrupt results.json falls back to the
    # next run instead of turning five routes into a 500
    for f in sorted((APP_STATE / "workroots").glob("*/results.json"),
                    reverse=True):
        try:
            return f.parent.name, _json.loads(f.read_text())
        except (_json.JSONDecodeError, OSError):
            continue
    return None, None


def _fan_svg(observed, qs):
    """Tiny inline SVG: observed tail + forecast fan (10-90, 25-75, median)."""
    # tolerate the pre-quantile results schema (medians-only floats)
    if not qs or not all(isinstance(v, dict) and "0.9" in v for v in qs.values()):
        return ""
    obs_v = [v for _, v in observed][-10:] if observed else []
    hs = sorted(qs, key=int)
    hi = max([qs[h]["0.9"] for h in hs] + obs_v + [1.0])
    W, H, n_obs = 320, 90, len(obs_v)
    n = n_obs + len(hs)
    def x(i): return 10 + i * (W - 20) / max(n - 1, 1)
    def y(v): return H - 10 - (v / hi) * (H - 22)
    def pts(seq): return " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in seq)
    band = lambda lo_k, hi_k, op: (
        f'<polygon fill="var(--gold-bright)" fill-opacity="{op}" points="'
        + pts([(n_obs - 1 + k + 1, qs[h][hi_k]) for k, h in enumerate(hs)])
        + " " + pts(reversed([(n_obs - 1 + k + 1, qs[h][lo_k])
                              for k, h in enumerate(hs)])) + '"/>')
    parts = [f'<svg viewBox="0 0 {W} {H}" style="width:100%;max-width:{W}px">']
    if obs_v:
        parts.append(f'<polyline fill="none" stroke="var(--ink)" stroke-width="1.6" '
                     f'points="{pts(list(enumerate(obs_v)))}"/>')
    parts += [band("0.1", "0.9", 0.18), band("0.25", "0.75", 0.35)]
    parts.append('<polyline fill="none" stroke="var(--gold)" stroke-width="2" points="'
                 + pts([(n_obs - 1 + k + 1, qs[h]["0.5"]) for k, h in enumerate(hs)]) + '"/>')
    parts.append('</svg>')
    return "".join(parts)


PREVIEW_ROWS = 12


@app.get("/output", response_class=HTMLResponse)
def output_page(request: Request):
    import pandas as pd
    from app.core.runs import APP_STATE
    rid, res = _latest_results()
    files = []
    if rid:
        w = APP_STATE / "workroots" / rid
        for f in sorted(w.glob("submission/*/*.csv")):
            entry = {"model": f.parent.name, "name": f.name, "path": str(f),
                     "cols": [], "rows": [], "more": 0}
            try:
                df = pd.read_csv(f, dtype=str)
                entry["cols"] = list(df.columns)
                entry["rows"] = df.head(PREVIEW_ROWS).fillna("").values.tolist()
                entry["more"] = max(len(df) - PREVIEW_ROWS, 0)
            except Exception:
                pass
            files.append(entry)
    return templates.TemplateResponse(request, "output.html", {
        "active": "Output", "rid": rid,
        "label": _run_label(rid) if rid else "",
        "date": (res or {}).get("forecast_date", ""),
        "has_ensemble": bool((res or {}).get("models", {}).get("ensemble")),
        "files": files,
        "archive_dates": list(reversed(_archive_dates())),
        "has_report": bool(rid and (APP_STATE / "workroots" / rid / "report.html").is_file())})


@app.get("/output/download")
def output_download(path: str):
    """Hand the submission CSV to the browser as a real download."""
    from fastapi.responses import FileResponse
    from app.core.runs import APP_STATE
    p = Path(path).resolve()
    if p.is_relative_to(APP_STATE.resolve()) and p.is_file():   # stay inside our state
        return FileResponse(p, filename=p.name, media_type="text/csv",
                            content_disposition_type="attachment")
    return HTMLResponse("<p>file not found in app state</p>", status_code=404)


@app.post("/output/reveal")
def output_reveal(path: str = Form(...)):
    """Local desktop app: show the file in Finder rather than fake a download."""
    import subprocess
    from app.core.runs import APP_STATE
    p = Path(path).resolve()
    if str(APP_STATE.resolve()) in str(p) and p.exists():   # stay inside our state
        subprocess.Popen(["open", "-R", str(p)])
    return RedirectResponse("/output", status_code=303)


@app.get("/output/report", response_class=HTMLResponse)
def output_report(date: str = ""):
    """Latest run's report by default; ?date=YYYY-MM-DD serves the archive."""
    import re
    from app.core.runs import APP_STATE
    if date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            return HTMLResponse("<p>Invalid date. Expected YYYY-MM-DD.</p>",
                                status_code=400)
        f = APP_STATE / "archive" / date / "report.html"
        return HTMLResponse(f.read_text() if f.is_file()
                            else f"<p>No archived report for {date}.</p>")
    rid, _ = _latest_results()
    f = APP_STATE / "workroots" / (rid or "") / "report.html"
    return HTMLResponse(f.read_text() if f.is_file()
                        else "<p>No report yet. Run the models first.</p>")


@app.get("/model/{name}", response_class=HTMLResponse)
def model_page(request: Request, name: str):
    blurbs = {
        "pf": ("PF-SIHRS",
               "The mechanistic member. It assumes influenza moves people "
               "through Susceptible, Infected, Hospitalized, and Recovered "
               "compartments, with seasonally varying transmission and "
               "immunity that wanes back to susceptibility. The model is "
               "written in BNGL and fitted by PyBNF's sequential particle "
               "filter on the bngsim engine: each week, 10,000 candidate "
               "epidemics per state are reweighted by how well they explain "
               "the newest hospital admissions, and their spread is the "
               "forecast uncertainty. It fits weekly NHSN admissions exactly "
               "as archived on each forecast date. Measured three-season "
               "retrospective relWIS against the FluSight baseline "
               "(values below 1 beat it): 1.023 in 2023-24, 0.636 in "
               "2024-25, 0.825 in 2025-26."),
        "analogue": ("Calendar analogue",
                     "The empirical member. It assumes the current season "
                     "will resemble past seasons at the same point in the "
                     "calendar: for each forecast it pools, across all "
                     "states, the weeks from strictly earlier seasons that "
                     "fall within two calendar weeks of the forecast date, "
                     "measures the growth from each of those weeks to the "
                     "target horizon, and scales the latest observed value "
                     "by the quantiles of those growth ratios. No "
                     "epidemiological mechanism is involved. It uses the "
                     "archive of weekly NHSN admissions and nothing else. "
                     "It is difficult to beat at one week ahead and anchors "
                     "the ensemble when a season behaves unusually. "
                     "Measured three-season retrospective relWIS: 1.105 in "
                     "2023-24, 0.835 in 2024-25, 0.641 in 2025-26."),
        "pf2s": ("Two-strain SIHRS",
                 "The panel-validated candidate member. It models influenza "
                 "A and influenza B as independent SIHRS circuits, each with "
                 "its own seasonally varying transmission, and reports "
                 "admissions as the sum of the two. Fitting uses two data "
                 "channels, both vintage-true: weekly NHSN hospital "
                 "admissions, and NREVSS typed positives entering the "
                 "likelihood as binomial counts of influenza A among typed "
                 "specimens. The initial A/B mix at the season start comes "
                 "from the same typed surveillance series. Measured "
                 "state-panel relWIS across the three replayed seasons: "
                 "0.849 in 2023-24, 0.554 in 2024-25, 0.685 in 2025-26; on "
                 "turning-point weeks it scores 1.039 against 1.122 for the "
                 "single-strain filter. It runs alongside the validated pair "
                 "as an optional third member with equal weights; the "
                 "default submission ensemble remains the two-member blend "
                 "while full-grid validation is in progress."),
        "ensemble": ("Ensemble",
                     "The submitted forecast. It averages the members' "
                     "forecast quantiles with equal, unfitted weights: "
                     "50/50 across the particle filter and the analogue, "
                     "equal thirds when the two-strain member joins. "
                     "Fitting the weights on held-out seasons was evaluated "
                     "and scored worse than the equal blend (pooled relWIS "
                     "0.717 against 0.704), so no weight is tuned. The "
                     "members' errors disagree in useful ways: the blend "
                     "beats the baseline in all three replayed seasons, "
                     "which neither member does alone. Measured "
                     "three-season retrospective relWIS: 0.848 in 2023-24, "
                     "0.651 in 2024-25, 0.691 in 2025-26; pooled 0.704."),
    }
    # one-line summaries: the collapsed <details> summary on each model tab
    onelines = {
        "pf": ("The mechanistic member: an SIHRS compartmental model fitted "
               "weekly by a sequential particle filter."),
        "analogue": ("The empirical member: it scales the latest observation "
                     "by historical growth ratios from matching calendar "
                     "weeks."),
        "pf2s": ("The candidate member: influenza A and B as parallel SIHRS "
                 "circuits fitted to two data channels."),
        "ensemble": ("The submitted forecast: an equal-weight quantile "
                     "average of the member forecasts."),
    }
    # where each model tab points into the Methods page
    manchor = {"pf": "fitting", "analogue": "analogue",
               "pf2s": "two-strain", "ensemble": "ensemble"}
    if name not in blurbs:
        return HTMLResponse("unknown model", status_code=404)
    rid, res = _latest_results()
    fans = {}
    if res and name in res.get("models", {}):
        for loc, qs in res["models"][name].items():
            fans[loc] = _fan_svg(res.get("observed", {}).get(loc, []), qs)
    fanq = {}
    if res and name in res.get("models", {}):
        fanq = {loc: qs for loc, qs in res["models"][name].items()
                if all(isinstance(v, dict) for v in qs.values())}
    # ensemble page: member medians for the raw-member overlay on the fan
    overlay = {}
    if name == "ensemble" and res:
        for m, md in (res.get("models") or {}).items():
            if m == "ensemble":
                continue
            for loc, qs in md.items():
                if all(isinstance(v, dict) for v in qs.values()):
                    meds = {h: v.get("0.5") for h, v in qs.items()
                            if isinstance(v, dict) and v.get("0.5") is not None}
                    if meds:
                        overlay.setdefault(m, {})[loc] = meds
    form = dict(_last_form) or {"forecast_date": _default_forecast_date(),
                                "locations": ["all"], "replicates": 3}
    return templates.TemplateResponse(request, "model.html", {
        "active": blurbs[name][0], "name": name,
        "title": blurbs[name][0], "blurb": blurbs[name][1],
        "oneline": onelines[name], "manchor": manchor[name],
        "rid": rid, "label": _run_label(rid) if rid else "",
        "date": (res or {}).get("forecast_date", ""),
        "fanq_json": __import__("json").dumps(fanq),
        "overlay_json": __import__("json").dumps(overlay),
        "run_obs_json": __import__("json").dumps((res or {}).get("observed", {})),
        "form": form, "status": _status})


@app.post("/model/ensemble/generate")
def generate_ensemble(request: Request):
    """(Re)blend from the latest run's stored member outputs -- no engine rerun."""
    import json as _json
    import os as _os
    from app.core import ensemble as ens
    from app.core.runs import APP_STATE
    from app.core.submit import rows_from_quantiles, write_submission
    rid, res = _latest_results()
    if not res:
        _flash("Nothing to blend yet. Run the models first.")
        return _back(request, "/model/ensemble")
    import pandas as pd
    locs = pd.read_csv(__import__("flubnf.settings",
                                  fromlist=["LOCATIONS"]).LOCATIONS, dtype=str)
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    blended, sub_rows = {}, []
    for loc in (set(res["models"].get("pf", {}))
                | set(res["models"].get("analogue", {}))
                | set(res["models"].get("pf2s", {}))):
        members = {}
        for m in ("pf", "analogue", "pf2s"):
            qd = res["models"].get(m, {}).get(loc)
            if qd:
                members[m] = {h: {float(q): v for q, v in qs.items()}
                              for h, qs in qd.items()}
        if members:
            # equal, never-fitted weights, matching the live run's blend
            b = ens.vincentize(members,
                               weights=ens.equal_weights(members),
                               location_fips=n2f.get(loc, ""))
            blended[loc] = {h: {q: b[h][float(q)]
                                for q in ("0.1", "0.25", "0.5", "0.75", "0.9")}
                            for h in b}
            if n2f.get(loc):
                sub_rows += rows_from_quantiles(b, n2f[loc], res["forecast_date"])
    res["models"]["ensemble"] = blended
    rp = APP_STATE / "workroots" / rid / "results.json"
    _tmp = rp.parent / "results.json.tmp"
    _tmp.write_text(_json.dumps(res))
    _os.replace(_tmp, rp)             # readers never see a half-write
    note = f"Ensemble re-blended for {len(blended)} location(s)"
    # the Output checklist points at this CSV -- write it, and be honest that
    # a re-blend from stored results carries the 5 display quantiles, not the
    # hub's full 23 (only a full run has the member samples for all 23)
    if sub_rows:
        try:
            write_submission(sub_rows, "Ensemble", "NAU", res["forecast_date"],
                             APP_STATE / "workroots" / rid / "submission")
            note += (" · submission CSV written from the 5 stored "
                     "quantiles; a full run writes all 23 hub quantiles")
        except Exception as e:
            note += f" · submission CSV skipped: {str(e)[:120]}"
    _flash(note)
    return _back(request, "/model/ensemble")


RETRO_ROOT = Path(__file__).resolve().parents[1] / "state" / "retro"
RETRO_SEAL = Path(__file__).resolve().parents[1] / "state" / "retro_seal"


def _season_root(season: str) -> tuple:
    """(root, is_seal): a season may live under the app's retro root or the
    full-grid seal root; show whichever has more completed weeks so flagship
    validation runs are never invisible in the app."""
    def _done(r):
        return len(list((r / "weeks").glob("*/samples.json"))) if r.exists() else 0
    app_root, seal_root = RETRO_ROOT / season, RETRO_SEAL / season
    if _done(seal_root) > _done(app_root):
        return seal_root, True
    return app_root, False
_retro_status: dict = {}
_retro_stop: set = set()


class _RetroStopRequested(Exception):
    """Raised inside the season worker between weeks when a stop was asked."""


def _retro_state_names() -> list:
    """State list for the retro config form. Falls back to the packaged
    locations table when the hub is not cloned yet (fresh machine, CI), so
    the page renders instead of erroring before setup."""
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


@app.get("/retro", response_class=HTMLResponse)
def retro_index(request: Request):
    from app.core.retro import available_seasons, season_vintages
    seasons = []
    for s in available_seasons():
        total = len(season_vintages(s))
        root, is_seal = _season_root(s)
        done = len(list((root / "weeks").glob("*/samples.json"))) if root.exists() else 0
        seasons.append({"name": s, "total": total, "done": done,
                        "seal": is_seal,
                        "running": _retro_status.get(s) in ("running",
                                                            "stopping"),
                        "scored": (root / "scores.json").exists()})
    from flubnf.settings import PY_ENGINE, PYBNF
    return templates.TemplateResponse(request, "retro.html",
                                      {"active": "Retrospective", "seasons": seasons,
                                       "state_names": _retro_state_names(),
                                       "engine_ok": PY_ENGINE.exists()
                                       and PYBNF.exists()})


def _retro_bg(season: str, locations: list, width: int,
              replicates: int = 3, particles: int = 10_000):
    from app.core import retro
    _retro_status[season] = "running"
    _retro_stop.discard(season)     # no stale stop flag from a past run
    guard = _sleep_guard()          # overnight replays must outlive the lid
    try:
        root = RETRO_ROOT / season

        def _tick(_asof):
            # run_season calls this after every week: the clean stop point.
            # Completed weeks are on disk and a restarted replay skips them.
            if season in _retro_stop:
                raise _RetroStopRequested()
        retro.run_season(root, season, locations, replicates=replicates,
                         particles=particles, width=width, progress=_tick)
        # equal, never-fitted member weights (the sealed recipe)
        df = retro.score_season(root, season,
                                ensemble_weights={"pf": 0.5, "analogue": 0.5})
        df.to_json(root / "scores.json")
        _retro_status[season] = "done"
    except _RetroStopRequested:
        # completed weeks stay; the results page scores whatever exists
        _retro_status[season] = "stopped"
    except Exception as e:
        _retro_status[season] = f"error: {str(e)[:150]}"
    finally:
        _retro_stop.discard(season)
        if guard is not None:
            try:
                guard.terminate()
            except Exception:
                pass


@app.post("/retro/stop")
def retro_stop():
    """Ask every running season replay to stop after its current week.
    Completed weeks stay on disk; a restarted replay resumes where this one
    left off (a completed week is never redone)."""
    stopping = []
    for season, st in list(_retro_status.items()):
        if st == "running":
            _retro_stop.add(season)
            _retro_status[season] = "stopping"
            stopping.append(season)
    if stopping:
        _flash("Stopping " + ", ".join(sorted(stopping)) + " after the "
               "current week. Completed weeks are kept; the replay resumes "
               "from there next time.")
    return RedirectResponse("/retro", status_code=303)


@app.post("/retro/run")
def retro_run(background: BackgroundTasks, season: str = Form(...),
              locations: str = Form("panel6"),
              custom_locations: list = Form([]),
              particles: int = Form(10_000),
              replicates: int = Form(3),
              width: int = Form(4),
              engine: str = Form("pf")):
    from app.core.retro import available_seasons
    if _retro_status.get(season) in ("running", "stopping"):
        _flash(f"{season} is already replaying. One season worker runs at a time.")
        return RedirectResponse("/retro", status_code=303)
    if season not in available_seasons():
        _flash(f"Season {season} is not available. A season appears once its "
               "vintage archive exists.")
        return RedirectResponse("/retro", status_code=303)
    if engine != "pf":
        # pf2s slots in HERE later: accept engine == "pf2s", thread a
        # {"variant": "2strain"} extra through retro.run_week's RunSpec, and
        # collect the member alongside pf in samples.json.
        _flash("Only the PF engine preset is available for retrospectives "
               "at present.")
        return RedirectResponse("/retro", status_code=303)
    all_states = _retro_state_names()
    if locations == "all":
        names = all_states
    elif locations == "custom":
        names = [n for n in custom_locations if n in set(all_states)]
        if not names:
            _flash("Custom scope selected but no locations were checked. "
                   "Check at least one state and try again.")
            return RedirectResponse("/retro", status_code=303)
    else:
        names = ["Alaska", "New York", "Wyoming", "Pennsylvania",
                 "Vermont", "California"]
    # keep the knobs inside what the machine survives (budget: 0.45 fits/min)
    particles = max(1_000, min(int(particles), 100_000))
    replicates = max(1, min(int(replicates), 10))
    width = max(1, min(int(width), 16))
    # claim inside the request, not the background task, so a double submit
    # can't race two season workers over the same tree
    _retro_status[season] = "running"
    background.add_task(_retro_bg, season, names, width, replicates, particles)
    return RedirectResponse("/retro", status_code=303)


@app.get("/retro/{season}", response_class=HTMLResponse)
def retro_results(request: Request, season: str, week: str = ""):
    import json as _json
    import numpy as np
    import pandas as pd
    from app.core import retro
    root, _is_seal = _season_root(season)
    weeks = sorted(p.parent.name for p in (root / "weeks").glob("*/samples.json"))
    if not weeks:
        # a raw unthemed dead-end helps nobody: back to the season list,
        # which already knows how to show a 0-weeks season
        _flash(f"{season}: no completed weeks yet. Start the replay and "
               "check back shortly.")
        return RedirectResponse("/retro", status_code=303)
    sf = root / "scores.json"
    score_error = ""
    def _stored_empty():
        try:
            import pandas as _p
            d = _p.read_json(sf)
            return d.empty or "model" not in d.columns
        except Exception:
            return True
    try:
        # Rescore when stale, when asked (?rescore=1), or when the stored file
        # is EMPTY: an early failed run writes an empty scores.json whose
        # fresh mtime would otherwise block rescoring forever (seen in the
        # field on the first laptop retrospective).
        if (not sf.exists() or request.query_params.get("rescore")
                or _stored_empty()
                or sf.stat().st_mtime < max(
                (root / "weeks" / w / "samples.json").stat().st_mtime for w in weeks)):
            retro.score_season(
                root, season,
                ensemble_weights={"pf": 0.5, "analogue": 0.5}).to_json(sf)
    except Exception as e:
        # A hidden failure here once masqueraded as "truth not settled" on a
        # fresh laptop. Show the truth: what broke, so it can be fixed.
        score_error = f"{type(e).__name__}: {str(e)[:220]}"
    try:
        df = pd.read_json(sf) if sf.exists() else pd.DataFrame()
    except Exception:
        df = pd.DataFrame()
    heads, curve, states = {}, [], []
    scoreable = (not df.empty) and ("model" in df.columns)
    if scoreable:
        for m in ("pf", "analogue", "ensemble"):
            g = df[df.model == m]
            if len(g):
                heads[m] = g.wis.sum() / g.base_wis.sum()
        for a in sorted(df["asof"].unique()):
            g = df[(df.model == "ensemble") & (df["asof"] <= a)]
            if len(g):
                curve.append((str(a)[:10], g.wis.sum() / g.base_wis.sum()))
        for loc in sorted(df.location.unique()):
            row = {"name": loc}
            for m in ("pf", "analogue", "ensemble"):
                g = df[(df.model == m) & (df.location == loc)]
                row[m] = g.wis.sum() / g.base_wis.sum() if len(g) else None
            states.append(row)
    wk = week if week in weeks else weeks[-1]
    d = _json.loads((root / "weeks" / wk / "samples.json").read_text())
    from app.core.report import categorical_probs
    from app.core.report_v2 import CATS
    from app.core.usmap import svg_map
    locs = pd.read_csv(__import__("flubnf.settings",
                                  fromlist=["LOCATIONS"]).LOCATIONS, dtype=str)
    n2a = dict(zip(locs.location_name, locs.abbreviation))
    n2p = dict(zip(locs.location_name, locs.population.astype(float)))
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    cards = {}
    for loc, s in d["pf"].items():
        arr = np.asarray(s["1"], float)
        origin = np.asarray(s["0"], float)
        lo = float(np.median(origin[np.isfinite(origin)]))
        probs = categorical_probs(arr, lo, int(n2p[loc]), 1)
        hover = (f"<b>{loc}</b><br>1-wk median: "
                 f"{float(np.median(arr[np.isfinite(arr)])):.0f}<br>" +
                 "<br>".join(f"{c.replace('_',' ')}: {probs.get(c,0):.0%}"
                             for c in CATS))
        cards[n2f[loc]] = {"probs": probs, "name": loc, "abbr": n2a[loc],
                           "fips": n2f[loc], "hover_html": hover}
    for name, abbr in n2a.items():
        cards.setdefault(n2f.get(name, name), {"name": name, "abbr": abbr,
                                               "fips": n2f.get(name, "")})
    map_html = svg_map(cards)
    if not scoreable and not score_error:
        # scored zero cells with no exception: diagnose WHICH input is empty
        try:
            import json as _dj
            from datetime import date as _dd, timedelta as _dt
            from app.core.scoring import load_truth as _lt
            truth_d, n2f_d = _lt()
            season_dates = {w for w in weeks}
            t_rows = sum(1 for (f, d) in truth_d
                         if any(str(d.date()) > w for w in list(season_dates)[:1]))
            d0 = _dj.loads((root / "weeks" / weeks[len(weeks)//2] / "samples.json").read_text())
            import numpy as _dn
            pos_med = sum(1 for loc, sm in d0.get("pf", {}).items()
                          for h in ("1",)
                          if _dn.median(_dn.asarray(sm[h], float)) > 0)
            # walk ONE cell through every scoring step and name its killer
            import traceback as _tb
            import pandas as _dp
            from app.core import ensemble as _de
            from app.core.scoring import _baseline_cells as _dbc
            from flubnf.wis import wis as _dwis
            wk_mid = weeks[len(weeks)//2]
            loc0 = sorted(d0.get("pf", {}))[0]
            fips0 = n2f_d.get(loc0)
            T0 = _dp.Timestamp(d0["asof"])
            q0 = _de.member_quantiles_from_samples(d0["pf"][loc0]).get("1", {})
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
        except Exception as pe:
            probe = f"diagnostic probe failed: {type(pe).__name__}: {str(pe)[:120]}"
        score_error = "scored zero cells with no exception. " + probe
    if not scoreable and score_error:
        map_html = ("<p class='hint'>Scoring failed: <code>"
                    + score_error + "</code>. The fitted forecasts below are "
                    "intact; fix the scoring input (usually the FluSight hub "
                    "clone, via the Data tab) and reload this page.</p>")
    elif not scoreable:
        map_html = ("<p class='hint'>No scoreable weeks yet. Truth for "
                    "these forecast dates has not settled, so relWIS arrives "
                    "later; the weekly maps below are available now.</p>") + map_html
    return templates.TemplateResponse(request, "retro_season.html", {
        "active": "Retrospective", "season": season, "heads": heads, "curve": curve, "states": states,
        "weeks": weeks, "week": wk, "map_html": map_html,
        "n_weeks": len(weeks) if scoreable else 0, "score_error": score_error})


@app.get("/api/retro/{season}/playback/{asof}")
def api_retro_playback(season: str, asof: str):
    """One stored retrospective week as a playback payload: member and
    ensemble quantile fans, settled truth, the CDC's submitted comparators,
    and running relWIS stats. Cached under <season_root>/playback_cache/."""
    from fastapi.responses import PlainTextResponse
    from app.core import playback
    root, _is_seal = _season_root(season)
    try:
        return playback.build_week(root, season, asof)
    except playback.UnknownWeek as e:
        return PlainTextResponse(str(e), status_code=404)


@app.get("/retro/{season}/report")
def retro_season_report(season: str):
    """Generate (cached by mtime) and download the self-contained season
    report: the season player with every week's data embedded, one HTML
    file, no server needed."""
    from fastapi.responses import FileResponse, PlainTextResponse
    from app.core import playback, report_season
    root, _is_seal = _season_root(season)
    try:
        p = report_season.build_season_report(root, season)
    except playback.UnknownWeek as e:
        return PlainTextResponse(str(e), status_code=404)
    return FileResponse(p, filename=p.name, media_type="text/html",
                        content_disposition_type="attachment")


@app.get("/api/retro/{season}/report_path")
def api_retro_report_path(season: str):
    """Build the season report if absent (same builder as the download
    route, cached by mtime) and return its absolute path. The results
    page's Reveal-in-Finder button feeds this path to /output/reveal, the
    belt-and-braces route for the native window."""
    from fastapi.responses import PlainTextResponse
    from app.core import playback, report_season
    root, _is_seal = _season_root(season)
    try:
        p = report_season.build_season_report(root, season)
    except playback.UnknownWeek as e:
        return PlainTextResponse(str(e), status_code=404)
    return {"path": str(p)}


@app.post("/run")
def run_models(request: Request,
               background: BackgroundTasks,
               forecast_date: str = Form(...),
               locations: list = Form([]),
               weeks_to_drop: int = Form(0),
               weeks_to_nowcast: int = Form(0),
               replicates: int = Form(3),
               engine: str = Form("all"),
               members: int = Form(2)):
    # the pipeline's contract is Saturdays with an archived vintage; hold
    # the user to it kindly instead of failing three phases into the run
    from datetime import date as _date, timedelta as _td
    try:
        _d = _date.fromisoformat(forecast_date)
        if _d.weekday() != 5:
            _d -= _td(days=(_d.weekday() - 5) % 7)
            _flash(f"Snapped {forecast_date} to Saturday {_d}. Forecasts "
                   "align to FluSight's weekly cadence.")
            forecast_date = _d.isoformat()
    except ValueError:
        pass
    try:
        data_mod.vintage_path(forecast_date)
    except Exception:
        vs = data_mod.vintages()
        near = min(vs, key=lambda v: abs(_date.fromisoformat(v) - _date.fromisoformat(forecast_date))) if vs else None
        _flash(f"No archived data for {forecast_date}."
               + (f" Nearest available: {near}." if near else
                  " Pull the FluSight hub on the Data tab first."))
        return _back(request, "/forecast")
    _last_form.update({"forecast_date": forecast_date, "locations": locations,
                       "engine": engine, "weeks_to_drop": weeks_to_drop,
                       "weeks_to_nowcast": weeks_to_nowcast,
                       "replicates": replicates, "members": members})
    # checkboxes arrive as a list, the model pages' text input as one
    # comma-separated string inside it -- flatten both to clean names
    locations = [x.strip() for l in locations
                 for x in str(l).split(",") if x.strip()]
    if not locations:
        # nothing checked used to silently run Ohio -- ask instead
        _flash("Select at least one location, or all 52 jurisdictions. "
               "Nothing was run.")
        return _back(request, "/forecast")
    if _status.get("running"):
        _status["log"].append("A run is already in progress; not starting another.")
        return RedirectResponse("/forecast#results", status_code=303)
    # BackgroundTasks fire AFTER the redirect renders; claim the running slot
    # NOW so the page the user lands on shows the run (double-click race,
    # laptop field test 2026-08-18)
    _status["running"] = "starting"
    _status["run_label"] = f"{forecast_date} · queued"
    if "all" in [l.lower() for l in locations]:
        import pandas as _pd
        _l = _pd.read_csv(__import__("flubnf.settings",
                                     fromlist=["LOCATIONS"]).LOCATIONS, dtype=str)
        locs_list = list(_l.location_name[(_l.location.str.len() == 2)
                                          & (_l.abbreviation != "US")])
        us = _l.location_name[_l.abbreviation == "US"]
        if len(us):
            locs_list.append(str(us.iloc[0]))   # national, fitted directly
    else:
        locs_list = list(locations)
    if not any(str(l).upper() in ("US", "US (NATIONAL)") for l in locs_list):
        locs_list.append("US")   # national fitted directly, always
    # the label owns the arithmetic: N states the user picked, plus the
    # national fit we always add -- no phantom extra location in the count
    n_states = sum(1 for l in locs_list
                   if str(l).upper() not in ("US", "US (NATIONAL)"))
    _status["run_label"] = f"{forecast_date} · {n_states} state(s) + US · queued"
    # honest progress: the denominator (locations x replicates) is known NOW,
    # from the spec -- shard .prog files only ever grow toward it, so pct can
    # never regress when a late shard registers. Also drop the previous run's
    # workroot so its finished .prog files never flash as this run's progress.
    # Engines without per-fit shards (amcmc, analogue) get NO denominator:
    # /api/progress then reports the phase instead of fabricating 0/N.
    _status["workroot"] = None
    _status["expected_total"] = (len(locs_list) * int(replicates)
                                 * (2 if members == 3 else 1)
                                 if engine in ("all", "pf") else None)
    spec = RunSpec(engine=engine, forecast_date=forecast_date,
                   locations=locs_list,
                   weeks_to_drop=weeks_to_drop,
                   weeks_to_nowcast=weeks_to_nowcast,
                   replicates=replicates,
                   extra={"members": 3} if members == 3 else {})
    if engine in ("all", "pf", "analogue"):
        # 'analogue' rides the same pipeline with the PF block skipped --
        # the model page's "Run Calendar analogue only" button posts it
        background.add_task(_run_all, spec)
    elif engine == "amcmc":
        from app.core.engines import amcmc as am_engine
        def _bg():
            ledger = Ledger()
            rid = None
            try:
                rid = ledger.open_run(spec, Path("pending"), {"engine": "amcmc"})
                _status["running"] = f"amcmc:{rid}"
                w = lease_workroot(rid)
                _status["workroot"] = str(w)
                _status["phase"] = ("Adaptive MCMC: this engine does not "
                                    "report per-fit progress.")
                out = am_engine.execute(spec, w)
                n_ok = sum(1 for r in out["records"] if r.get("ok"))
                ledger.close_run(rid, "ok", {"ok_states": n_ok})
            except Exception as e:
                if rid is not None:
                    ledger.close_run(rid, "error", {"error": str(e)[:300]})
                _status["log"].append(f"adaptive MCMC run failed: {str(e)[:200]}")
            finally:
                _status["running"] = None
                _status["workroot"] = None
                _status["phase"] = ""
                _status["run_label"] = ""
                _status["expected_total"] = None
        background.add_task(_bg)
    else:
        # an engine we don't know: release the claim instead of wedging the
        # console until restart, and say so
        _status["running"] = None
        _status["run_label"] = ""
        _status["expected_total"] = None
        _flash(f"'{engine}' is not one of the available engines. "
               "Nothing was run.")
    return RedirectResponse("/forecast#results", status_code=303)
