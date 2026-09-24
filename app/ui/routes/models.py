"""Models (GET /models, GET /model/{name}): one page per shipped model and
the two-strain research view, with the model's BNGL template source and the
latest run's fans. An APIRouter server.py includes.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core import oracle_text as _oracle_text
from app.ui import shared, templating
from app.ui.forms import _default_forecast_date
from app.ui.shared import _run_label
from app.ui.state import REPO, _last_form, _status
from app.ui.templating import _member_colors, _script_json, templates

router = APIRouter()


# === Models (/models, /model/{name}) -> model.html ===
@router.get("/models", response_class=HTMLResponse)
def models_page(request: Request):
    """The Models tab, defaulting to the PF view; /model/<name> routes stay
    live (reports and bookmarks link them)."""
    return model_page(request, "pf")


@router.get("/model/{name}", response_class=HTMLResponse)
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
    # short phrases: the collapsed <details> summary on each model tab (the
    # full description, the blurb, opens beneath it)
    onelines = {
        "pf": ("Mechanistic: a compartment model fitted weekly, blended "
               "with past seasons' growth"),
        "analogue": ("Empirical: the latest count scaled by past seasons' "
                     "growth at this calendar week"),
        "pf2s": "Research only: influenza A and B as two SIHRS circuits",
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
