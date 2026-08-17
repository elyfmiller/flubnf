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
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

ENGINES = ("pf", "analogue", "einn", "amcmc")       # ascending cost order
_status: dict = {"running": None, "log": []}


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    vs = data_mod.vintages()
    return templates.TemplateResponse(request, "index.html", {
        "latest_vintage": vs[-1] if vs else "none",
        "n_vintages": len(vs),
        "engines": ENGINES,
        "status": _status,
        "ledger": Ledger().rows(10),
        "freshness": None,
    })


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
    })


def _run_pf(spec: RunSpec) -> None:
    from app.core.engines import pf as pf_engine
    ledger = Ledger()
    try:
        import bngsim_version_probe  # noqa: F401  (placeholder; versions via runner)
    except ImportError:
        pass
    run_id = ledger.open_run(spec, Path("pending"), {"engine": "pf"})
    workroot = lease_workroot(run_id)
    _status["running"] = f"pf:{run_id}"
    try:
        pf_engine.prepare(spec, workroot)
        status = pf_engine.execute(workroot)
        fails = {k: v for k, v in status.items() if v != "ok"}
        ledger.close_run(run_id, "failed" if fails else "ok",
                         {"cells": len(status), "failures": fails})
        _status["log"].append(f"{run_id}: {len(status)} cells, "
                              f"{len(fails)} failures")
    except Exception as e:
        ledger.close_run(run_id, "error", {"error": str(e)[:300]})
        _status["log"].append(f"{run_id}: ERROR {e}")
    finally:
        _status["running"] = None


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
    if engine == "pf":
        background.add_task(_run_pf, spec)
    else:
        _status["log"].append(f"{engine}: engine not wired yet")
    return RedirectResponse("/", status_code=303)
