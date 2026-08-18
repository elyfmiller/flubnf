"""FastAPI operations console — landing, freshness, settings, run, tabs.

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

ENGINES = ("all", "pf", "amcmc")     # "all" = pf + analogue + ensemble
_status: dict = {"running": None, "log": []}


def _latest_saturday() -> str:
    import datetime as dt
    d = dt.date.today()
    return str(d - dt.timedelta(days=(d.weekday() - 5) % 7))


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    from fastapi.responses import Response
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>"
           "<rect width='16' height='16' rx='3' fill='#003466'/>"
           "<text x='8' y='12' text-anchor='middle' font-size='11' "
           "fill='#ffc72c' font-family='sans-serif' font-weight='bold'>F</text></svg>")
    return Response(svg, media_type="image/svg+xml")


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    vs = data_mod.vintages()
    return templates.TemplateResponse(request, "index.html", {
        "latest_vintage": vs[-1] if vs else "none",
        "default_date": _latest_saturday(),
        "n_vintages": len(vs),
        "engines": ENGINES,
        "status": _status,
        "ledger": Ledger().rows(10),
        "freshness": None,
        "missing": __import__("flubnf.settings", fromlist=["check"]).check(verbose=False),
    })


@app.post("/data/pull")
def data_pull():
    """Explicit hub update -- looking never pulls; pulling is a button."""
    msg = data_mod.pull_hub()
    _status["log"].append(f"data pull: {msg[:120]}")
    return RedirectResponse("/", status_code=303)


@app.post("/freshness", response_class=HTMLResponse)
def freshness(request: Request):
    f = data_mod.check_freshness()
    vs = data_mod.vintages()
    return templates.TemplateResponse(request, "index.html", {
        "latest_vintage": vs[-1] if vs else "none",
        "n_vintages": len(vs),
        "engines": ENGINES,
        "status": _status,
        "ledger": Ledger().rows(10),
        "freshness": f,
        "default_date": _latest_saturday(),
        "missing": __import__("flubnf.settings", fromlist=["check"]).check(verbose=False),
    })


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
    run_id = ledger.open_run(spec, Path("pending"), {"engines": "pf,analogue"})
    workroot = lease_workroot(run_id)
    _status["running"] = f"all:{run_id}"
    outcome = {}
    try:
        # 1. PF (primary) -- gracefully absent on Tier-A machines (no engine
        # venv): the run proceeds with the analogue and says so, rather than
        # erroring on the first click of a fresh install.
        from flubnf.settings import PY_ENGINE, PYBNF
        fails = {}
        pf_samples = {}
        if PY_ENGINE.exists() and PYBNF.exists():
            pf_engine.prepare(spec, workroot)
            status = pf_engine.execute(workroot)
            fails = {k: v for k, v in status.items() if v != "ok"}
            outcome["pf_cells"] = len(status)
            outcome["pf_failures"] = fails
            pf_samples = pf_engine.collect(workroot)
        else:
            outcome["pf_skipped"] = "engine venv not installed (Tier A)"
            (workroot / "cells.json").write_text("[]")
        # 2. analogue (instant)
        an_q = an_engine.run(spec)
        # 3. ensemble (vincentize, frozen per-horizon/per-state weights)
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
            if m:
                members_by_loc[loc] = ens.vincentize(m, location_fips=n2f_pre.get(loc, ''))
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
        # 5. retrospective scoring (populates once truth exists)
        truth, name2fips = scoring.load_truth()
        df = scoring.score_samples(pf_samples, spec.forecast_date,
                                   name2fips, truth)
        if not df.empty:
            outcome["pf_relwis"] = round(float(df.wis.sum() / df.base_wis.sum()), 3)
        df.to_json(workroot / "scores_pf.json")
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
            build_report(spec.forecast_date, cards, {},
                         {"fan": None, "acc": None,
                          "summary_html": wis_html},
                         workroot / "report.html")
            outcome["report"] = str(workroot / "report.html")
        except Exception as e:
            outcome["report_error"] = str(e)[:200]
        # 6. results index for the run page
        import json as _json
        (workroot / "results.json").write_text(_json.dumps({
            "spec": spec.to_json(), "models": {
                "pf": {loc: {h: float(pd.Series(s[h]).median())
                             for h in ("1", "2", "3", "4")}
                       for loc, s in pf_samples.items()},
                "analogue": {loc: {h: q[h][0.5] for h in q}
                             for loc, q in an_q.items()},
                "ensemble": {loc: {h: q[h][0.5] for h in q}
                             for loc, q in members_by_loc.items()},
            }}))
        ledger.close_run(run_id, "failed" if fails else "ok", outcome)
        _status["log"].append(
            f"{run_id}: pf {len(pf_samples)} loc, analogue {len(an_q)}, "
            f"ensemble {len(members_by_loc)}"
            + (f", relWIS {outcome['pf_relwis']}" if "pf_relwis" in outcome else ""))
    except Exception as e:
        ledger.close_run(run_id, "error", {"error": str(e)[:300], **outcome})
        _status["log"].append(f"{run_id}: ERROR {e}")
    finally:
        _status["running"] = None


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: str):
    import json as _json
    from app.core.runs import APP_STATE
    w = APP_STATE / "workroots" / run_id
    res = {}
    if (w / "results.json").is_file():
        res = _json.loads((w / "results.json").read_text())
    subs = sorted(str(p.relative_to(w)) for p in w.glob("submission/*/*.csv"))
    report = (w / "report.html").name if (w / "report.html").is_file() else None
    return templates.TemplateResponse(request, "run.html", {
        "run_id": run_id, "models": res.get("models", {}),
        "subs": subs, "report": report})


@app.get("/runs/{run_id}/report", response_class=HTMLResponse)
def run_report(run_id: str):
    from app.core.runs import APP_STATE
    f = APP_STATE / "workroots" / run_id / "report.html"
    return HTMLResponse(f.read_text() if f.is_file()
                        else "<p>no report for this run</p>")


RETRO_ROOT = Path(__file__).resolve().parents[1] / "state" / "retro"
_retro_status: dict = {}


@app.get("/retro", response_class=HTMLResponse)
def retro_index(request: Request):
    from app.core.retro import SEASON_BOUNDS, season_vintages
    seasons = []
    for s in SEASON_BOUNDS:
        total = len(season_vintages(s))
        root = RETRO_ROOT / s
        done = len(list((root / "weeks").glob("*/samples.json"))) if root.exists() else 0
        seasons.append({"name": s, "total": total, "done": done,
                        "running": _retro_status.get(s) == "running",
                        "scored": (root / "scores.json").exists()})
    from flubnf.settings import PY_ENGINE, PYBNF
    return templates.TemplateResponse(request, "retro.html",
                                      {"seasons": seasons,
                                       "engine_ok": PY_ENGINE.exists()
                                       and PYBNF.exists()})


def _retro_bg(season: str, locations: list, width: int):
    from app.core import retro
    _retro_status[season] = "running"
    try:
        root = RETRO_ROOT / season
        retro.run_season(root, season, locations, width=width)
        df = retro.score_season(root, season)
        df.to_json(root / "scores.json")
        _retro_status[season] = "done"
    except Exception as e:
        _retro_status[season] = f"error: {str(e)[:150]}"


@app.post("/retro/run")
def retro_run(background: BackgroundTasks, season: str = Form(...),
              locations: str = Form("panel6"), width: int = Form(4)):
    import pandas as pd
    from flubnf.settings import LOCATIONS
    if locations == "all":
        locs = pd.read_csv(LOCATIONS, dtype=str)
        names = list(locs.location_name[(locs.location.str.len() == 2)
                                        & (locs.abbreviation != "US")])
    else:
        names = ["Alaska", "New York", "Wyoming", "Pennsylvania",
                 "Vermont", "California"]
    background.add_task(_retro_bg, season, names, width)
    return RedirectResponse("/retro", status_code=303)


@app.get("/retro/{season}", response_class=HTMLResponse)
def retro_results(request: Request, season: str, week: str = ""):
    import json as _json
    import numpy as np
    import pandas as pd
    from app.core import retro
    root = RETRO_ROOT / season
    weeks = sorted(p.parent.name for p in (root / "weeks").glob("*/samples.json"))
    if not weeks:
        return HTMLResponse("<p style='color:#e9ecf2;background:#0a1626;"
                            "padding:2rem'>no completed weeks yet</p>")
    sf = root / "scores.json"
    if not sf.exists() or sf.stat().st_mtime < max(
            (root / "weeks" / w / "samples.json").stat().st_mtime for w in weeks):
        retro.score_season(root, season).to_json(sf)
    df = pd.read_json(sf)
    heads, curve = {}, []
    for m in ("pf", "analogue", "ensemble"):
        g = df[df.model == m]
        if len(g):
            heads[m] = g.wis.sum() / g.base_wis.sum()
    for a in sorted(df["asof"].unique()):
        g = df[(df.model == "ensemble") & (df["asof"] <= a)]
        if len(g):
            curve.append((str(a)[:10], g.wis.sum() / g.base_wis.sum()))
    states = []
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
    return templates.TemplateResponse(request, "retro_season.html", {
        "season": season, "heads": heads, "curve": curve, "states": states,
        "weeks": weeks, "week": wk, "map_html": svg_map(cards),
        "n_weeks": len(weeks)})


@app.post("/run")
def run_models(background: BackgroundTasks,
               forecast_date: str = Form(...),
               locations: str = Form("Ohio"),
               weeks_to_drop: int = Form(0),
               weeks_to_nowcast: int = Form(0),
               replicates: int = Form(3),
               engine: str = Form("pf")):
    spec = RunSpec(engine=engine, forecast_date=forecast_date,
                   locations=[l.strip() for l in locations.split(",") if l.strip()],
                   season_start="2025-08-01",
                   weeks_to_drop=weeks_to_drop,
                   weeks_to_nowcast=weeks_to_nowcast,
                   replicates=replicates)
    if engine in ("all", "pf"):
        background.add_task(_run_all, spec)
    elif engine == "amcmc":
        from app.core.engines import amcmc as am_engine
        def _bg():
            ledger = Ledger()
            rid = ledger.open_run(spec, Path("pending"), {"engine": "amcmc"})
            w = lease_workroot(rid)
            try:
                out = am_engine.execute(spec, w)
                n_ok = sum(1 for r in out["records"] if r.get("ok"))
                ledger.close_run(rid, "ok", {"ok_states": n_ok})
            except Exception as e:
                ledger.close_run(rid, "error", {"error": str(e)[:300]})
        background.add_task(_bg)
    else:
        _status["log"].append(f"{engine}: engine not wired yet")
    return RedirectResponse("/", status_code=303)
