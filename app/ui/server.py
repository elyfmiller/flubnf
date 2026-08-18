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
_last_form: dict = {}


def _default_forecast_date() -> str:
    """Latest Saturday, clamped to the latest ARCHIVED vintage — during the
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
    from fastapi.responses import Response
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>"
           "<rect width='16' height='16' rx='3' fill='#003466'/>"
           "<text x='8' y='12' text-anchor='middle' font-size='11' "
           "fill='#ffc72c' font-family='sans-serif' font-weight='bold'>F</text></svg>")
    return Response(svg, media_type="image/svg+xml")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", {
        "active": "Home",
        "missing": __import__("flubnf.settings", fromlist=["check"]).check(verbose=False)})


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
                                "locations": ["Ohio"], "engine": "all",
                                "weeks_to_drop": 0, "weeks_to_nowcast": 0,
                                "replicates": 3}
    rid, res = _latest_results()
    # data panel: full series for the CURRENTLY SELECTED locations, straight
    # from the latest vintage -- visible before any run (deciding what to
    # drop requires seeing the data)
    import json as _json
    sel = [l for l in form["locations"] if l != "all"] or ["Ohio"]
    series = {}
    try:
        vs = data_mod.vintages()
        tdf = pd.read_csv(data_mod.vintage_path(vs[-1]), dtype={"location": str})
        tdf["location"] = tdf["location"].str.zfill(2)
        n2f_ = dict(zip(_l.location_name, _l.location.str.zfill(2)))
        for loc in sel[:8]:
            g = tdf[tdf.location == n2f_.get(loc, "")].sort_values("date")
            g = g[pd.to_numeric(g.value, errors="coerce").notna()]
            series[loc] = {"dates": [str(d)[:10] for d in g.date],
                           "values": [float(v) for v in g.value]}
    except Exception:
        pass
    fanq = {}
    if res:
        m = res["models"].get("ensemble") or res["models"].get("pf") or {}
        fanq = {loc: qs for loc, qs in m.items()
                if all(isinstance(v, dict) for v in qs.values())}
    ledger_rows = Ledger().rows(5)
    for r in ledger_rows:
        r["label"] = _run_label(r["run_id"], r.get("spec", ""))
        r["chips"] = _outcome_chips(r.get("outcome", ""))
        if r["status"] == "running" and not _status.get("running", "").endswith(r["run_id"]):
            r["status"] = "interrupted"
    return templates.TemplateResponse(request, "forecast.html", {
        "active": "Forecast", "engines": ENGINES, "status": _status,
        "ledger": ledger_rows, "all_locs": all_locs, "form": form,
        "series_json": _json.dumps(series), "fanq_json": _json.dumps(fanq),
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
        if r["status"] == "running" and not _status.get("running", "").endswith(r["run_id"]):
            r["status"] = "interrupted"
    return templates.TemplateResponse(request, "runs.html", {
        "active": "Runs", "ledger": rows})


@app.post("/data/pull")
def data_pull():
    """Explicit hub update -- looking never pulls; pulling is a button."""
    msg = data_mod.pull_hub()
    _status["log"].append(f"data pull: {msg[:120]}")
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
    _status["workroot"] = str(workroot)
    _status["run_label"] = f"{spec.forecast_date} · {len(spec.locations)} location(s)"
    outcome = {}
    try:
        # 1. PF (primary) -- gracefully absent on Tier-A machines (no engine
        # venv): the run proceeds with the analogue and says so, rather than
        # erroring on the first click of a fresh install.
        from flubnf.settings import PY_ENGINE, PYBNF
        fails = {}
        pf_samples = {}
        if PY_ENGINE.exists() and PYBNF.exists():
            _phase("materializing models (BNG network generation)")
            pf_engine.prepare(spec, workroot)
            _phase(f"filtering {len(spec.locations)} location(s) × "
                   f"{spec.replicates} replicate(s)")
            status = pf_engine.execute(workroot)
            fails = {k: v for k, v in status.items() if v != "ok"}
            outcome["pf_cells"] = len(status)
            outcome["pf_failures"] = fails
            pf_samples = pf_engine.collect(workroot)
        else:
            outcome["pf_skipped"] = "engine venv not installed (Tier A)"
            (workroot / "cells.json").write_text("[]")
        _phase("consulting the calendar analogue")
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
        import numpy as _np
        from app.core.data import vintage_path as _vp
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
        obs = {}
        try:
            tdf = pd.read_csv(_vp(spec.forecast_date), dtype={"location": str})
            tdf["location"] = tdf["location"].str.zfill(2)
            f2n = {v: k for k, v in n2f.items()}
            for loc in spec.locations:
                fips = n2f.get(loc)
                g = tdf[tdf.location == fips].sort_values("date").tail(15)
                obs[loc] = [[str(r.date)[:10], float(r.value)]
                            for r in g.itertuples()
                            if _np.isfinite(r.value)]
        except Exception:
            pass
        (workroot / "results.json").write_text(_json.dumps({
            "spec": spec.to_json(), "forecast_date": spec.forecast_date,
            "observed": obs,
            "models": {
                "pf": {loc: _qs_from_samples(s) for loc, s in pf_samples.items()},
                "analogue": {loc: _qs_from_q(q) for loc, q in an_q.items()},
                "ensemble": {loc: _qs_from_q(q) for loc, q in members_by_loc.items()},
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
        _status["phase"] = ""


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
        "active": "Runs", "run_id": run_id,
        "label": _run_label(run_id), "models": res.get("models", {}),
        "subs": subs, "report": report})


@app.get("/runs/{run_id}/report", response_class=HTMLResponse)
def run_report(run_id: str):
    from app.core.runs import APP_STATE
    f = APP_STATE / "workroots" / run_id / "report.html"
    return HTMLResponse(f.read_text() if f.is_file()
                        else "<p>no report for this run</p>")


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
        for f in glob.glob(w + "/status_*.json.prog") + glob.glob(w + "/pf_status.json.prog"):
            try:
                d = _json.loads(open(f).read())
                done += d["done"]; total += d["total"]
                t0 = min(t0 or d["t0"], d["t0"])
            except Exception:
                pass
        out["done"], out["total"] = done, total
        if done and total and t0:
            rate = (_time.time() - t0) / done
            out["eta_s"] = int(rate * (total - done))
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
    if "pf_cells" in o: bits.append(f"PF {o['pf_cells']} cells")
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
    roots = sorted((APP_STATE / "workroots").glob("*/results.json"))
    if not roots:
        return None, None
    rid = roots[-1].parent.name
    return rid, _json.loads(roots[-1].read_text())


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


@app.get("/model/{name}", response_class=HTMLResponse)
def model_page(request: Request, name: str):
    blurbs = {
        "pf": ("PF-SIHRS", "Sequential particle filter over the SIHRS model: "
               "10,000 particles per replicate, Liu-West jitter, systematic "
               "resampling. The primary engine (relWIS 0.675 ± 0.012)."),
        "analogue": ("Calendar analogue", "Empirical donor distribution from "
                     "matching calendar weeks of past seasons (relWIS ~0.81 "
                     "full-grid; strongest at short horizons)."),
        "ensemble": ("Ensemble", "Vincentized blend of PF-SIHRS and the "
                     "analogue with per-horizon weights frozen pre-season "
                     "(PF share 0.4→0.8 by horizon; LOSO 0.717)."),
    }
    if name not in blurbs:
        return HTMLResponse("unknown model", status_code=404)
    rid, res = _latest_results()
    fans = {}
    if res and name in res.get("models", {}):
        for loc, qs in res["models"][name].items():
            fans[loc] = _fan_svg(res.get("observed", {}).get(loc, []), qs)
    return templates.TemplateResponse(request, "model.html", {
        "active": blurbs[name][0], "name": name,
        "title": blurbs[name][0], "blurb": blurbs[name][1],
        "rid": rid, "date": (res or {}).get("forecast_date", ""),
        "fans": fans, "status": _status})


@app.post("/model/ensemble/generate")
def generate_ensemble():
    """(Re)blend from the latest run's stored member outputs — no engine rerun."""
    import json as _json
    from app.core import ensemble as ens
    from app.core.runs import APP_STATE
    rid, res = _latest_results()
    if not res:
        _status["log"].append("ensemble: no run to blend")
        return RedirectResponse("/model/ensemble", status_code=303)
    import pandas as pd
    locs = pd.read_csv(__import__("flubnf.settings",
                                  fromlist=["LOCATIONS"]).LOCATIONS, dtype=str)
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    blended = {}
    for loc in set(res["models"].get("pf", {})) | set(res["models"].get("analogue", {})):
        members = {}
        for m in ("pf", "analogue"):
            qd = res["models"].get(m, {}).get(loc)
            if qd:
                members[m] = {h: {float(q): v for q, v in qs.items()}
                              for h, qs in qd.items()}
        if members:
            b = ens.vincentize(members, location_fips=n2f.get(loc, ""))
            blended[loc] = {h: {q: b[h][float(q)]
                                for q in ("0.1", "0.25", "0.5", "0.75", "0.9")}
                            for h in b}
    res["models"]["ensemble"] = blended
    (APP_STATE / "workroots" / rid / "results.json").write_text(_json.dumps(res))
    _status["log"].append(f"ensemble re-blended for {len(blended)} location(s)")
    return RedirectResponse("/model/ensemble", status_code=303)


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
                                      {"active": "Retrospective", "seasons": seasons,
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
        "active": "Retrospective", "season": season, "heads": heads, "curve": curve, "states": states,
        "weeks": weeks, "week": wk, "map_html": svg_map(cards),
        "n_weeks": len(weeks)})


@app.post("/run")
def run_models(background: BackgroundTasks,
               forecast_date: str = Form(...),
               locations: list = Form(["Ohio"]),
               weeks_to_drop: int = Form(0),
               weeks_to_nowcast: int = Form(0),
               replicates: int = Form(3),
               engine: str = Form("all")):
    _last_form.update({"forecast_date": forecast_date, "locations": locations,
                       "engine": engine, "weeks_to_drop": weeks_to_drop,
                       "weeks_to_nowcast": weeks_to_nowcast,
                       "replicates": replicates})
    if "all" in [l.lower() for l in locations]:
        import pandas as _pd
        _l = _pd.read_csv(__import__("flubnf.settings",
                                     fromlist=["LOCATIONS"]).LOCATIONS, dtype=str)
        locs_list = list(_l.location_name[(_l.location.str.len() == 2)
                                          & (_l.abbreviation != "US")])
    else:
        locs_list = [l for l in locations if l.strip()]
    spec = RunSpec(engine=engine, forecast_date=forecast_date,
                   locations=locs_list,
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
    return RedirectResponse("/forecast", status_code=303)
