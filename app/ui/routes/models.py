"""Models (GET /models, GET /model/{name}): one page per shipped model and
the two-strain research view, with the model's BNGL template source and the
latest run's fans. An APIRouter server.py includes.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from markupsafe import Markup

from app.core import oracle_text as ot
from app.ui import shared, templating
from app.ui.forms import _default_forecast_date
from app.ui.shared import _run_label
from app.ui.state import REPO, _last_form, _status
from app.ui.templating import _member_colors, _script_json, templates

router = APIRouter()

# Each page's header, per model: the kind and status badges beside the
# name, the one line under it (the collapsed-summary phrase this page
# always had, its "Kind:" lead now the badge), two facts from the
# description as labelled values, and the full description, which opens
# beneath in a fold. The relWIS record the descriptions used to end on is
# _record's.
HEADERS = {
    "pf": {
        "kind": "Mechanistic", "research": False,
        "tagline": ("A compartment model fitted weekly, blended with past "
                    "seasons' growth"),
        "facts": [("Fitted to", "NHSN admissions, from August 1"),
                  ("Fitted by", "PyBNF's particle filter, each week")],
        "blurb": ("The SIHRS compartment model (Susceptible, Infected, "
                  "Hospitalized, Recovered, with seasonal transmission and "
                  "waning immunity, written in BNGL) is fitted each week by "
                  "PyBNF's particle filter from August 1 through the newest "
                  "week of NHSN admissions as archived on the forecast date. "
                  "The Oracle step then gives each forecast sample path one "
                  "donor growth path from an earlier season at the same "
                  "calendar week, the calendar-donor principle the Groundhog "
                  "uses, and grows it at the geometric mean of the two, "
                  "propagated from the filter's own current state. The "
                  "Groundhog applies donor growth ratios to the last observed "
                  "count instead; the two are submitted as separate models "
                  "and nothing is blended between them."),
    },
    "analogue": {
        "kind": "Empirical", "research": False,
        "tagline": ("The latest count scaled by past seasons' growth at this "
                    "calendar week"),
        "facts": [("Donors", "NHSN admissions and FluSurv-NET, equal weight"),
                  ("Matched on", "calendar week, within two epiweeks")],
        "blurb": ("The empirical model: it pools, across all states, the "
                  "weeks of earlier seasons within two epiweeks of the "
                  "forecast date and scales the latest value by the "
                  "quantiles of their growth to each horizon, with no "
                  "epidemic mechanism. Donors are NHSN admissions (2021-22 "
                  "excluded: the archive holds only its growth phase) and a "
                  "committed FluSurv-NET bank shrunk to the admissions "
                  "scale, at equal weight."),
    },
    "pf2s": {
        "kind": "Mechanistic", "research": True,
        "tagline": "Influenza A and B as two SIHRS circuits",
        "facts": [("Fitted to", "NHSN admissions and NREVSS typed positives"),
                  ("Circuits", "influenza A and B, independent")],
        "blurb": ("A research variant, not a shipped model: influenza A and "
                  "B as independent SIHRS circuits whose admissions sum, "
                  "fitted to NHSN admissions and NREVSS typed positives."),
    },
}
# no page for the retired blend (LosAlamos_NAU-CModel_Flu, see ENGINES)

#: relWIS bars run from 0 to this; the FluSight baseline (1.0) sits inside
RECORD_AXIS = 1.2


def _record(name: str) -> dict:
    """The model's relWIS record, for the header: the bars (this model
    against its comparison, drawn against the baseline at 1.0), the facts
    beside them, and the sentences they come from, word for word, for the
    Record toggletip. The Oracle SIHRS figures are oracle_text's."""
    fmt = ot.fmt
    if name == "pf":
        both, y23, three = (ot.RECORD["both"], ot.RECORD["2023-24"],
                            ot.RECORD["three"])
        bars = [("Oracle SIHRS", both["oracle"], True),
                ("Plain filter", both["filter"], False)]
        facts = [("Cells", ot.cells(both["cells"])),
                 ("Seasons", "2024-25 and 2025-26")]
        lines = [
            (f"relWIS vs the FluSight baseline (below 1 beats it): "
             f"{fmt(both['oracle'])} against the plain filter's "
             f"{fmt(both['filter'])} on the same {ot.cells(both['cells'])} "
             f"cells of 2024-25 and 2025-26."),
            Markup("{} against {} in 2023-24 and {} against {} over three "
                   "seasons, a frozen-specification replication whose "
                   "prospective test is the 2026-27 season "
                   '(<a href="/methods#oracle">Methods</a>).').format(
                fmt(y23["oracle"]), fmt(y23["filter"]),
                fmt(three["oracle"]), fmt(three["filter"]))]
        return _bars({"bars": bars, "facts": facts, "lines": lines})
    if name == "analogue":
        seasons = [("2023-24", 0.722), ("2024-25", 0.653),
                   ("2025-26", 0.651)]
        pooled, bare, cells = 0.666, 0.771, "15,340"
        return _bars({
            "bars": [("Groundhog, pooled", pooled, True),
                     ("Without FluSurv-NET donors", bare, False)],
            "facts": [(s, fmt(v)) for s, v in seasons] + [("Cells", cells)],
            "lines": [
                (f"Three-season relWIS vs the FluSight baseline on {cells} "
                 f"cells: {fmt(seasons[0][1])}, {fmt(seasons[1][1])} and "
                 f"{fmt(seasons[2][1])}, pooled {fmt(pooled)} ({fmt(bare)} "
                 f"without the FluSurv-NET donors).")]})
    two, blend = 0.719, 0.704
    return _bars({
        "bars": [("Two-strain SIHRS", two, True),
                 ("Two-member blend", blend, False)],
        "facts": [], "worse": True,
        "lines": [
            (f"It scored worse on the full grid (relWIS {fmt(two)} against "
             f"{fmt(blend)} for the two-member blend it was tested in), so "
             f"it is kept for research runs only.")]})


def _bars(rec: dict) -> dict:
    """Bar widths and the baseline's place, as percentages of the axis.
    The sentences are this module's own text and numbers: safe markup, so
    an apostrophe reads as typed in the page source too."""
    rec["lines"] = [Markup(x) for x in rec["lines"]]
    rec["bars"] = [{"label": lab, "text": ot.fmt(v), "this": this,
                    "pct": round(100 * min(v, RECORD_AXIS) / RECORD_AXIS, 1)}
                   for lab, v, this in rec["bars"]]
    rec["one"] = round(100 / RECORD_AXIS, 1)
    return rec


# === Models (/models, /model/{name}) -> model.html ===
@router.get("/models", response_class=HTMLResponse)
def models_page(request: Request):
    """The Models tab, defaulting to the PF view; /model/<name> routes stay
    live (reports and bookmarks link them)."""
    return model_page(request, "pf")


@router.get("/model/{name}", response_class=HTMLResponse)
def model_page(request: Request, name: str):
    # where each model tab points into the Methods page
    manchor = {"pf": "oracle", "analogue": "analogue",
               "pf2s": "two-strain"}
    if name not in HEADERS:
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
    header = HEADERS[name]
    return templates.TemplateResponse(request, "model.html", {
        "active": "Models", "name": name,
        # title from the shared model-name map
        "title": templating._model_names().get(name, name),
        "header": header, "record": _record(name),
        "model_names_json": _script_json(templating._model_names()),
        "member_colors_json": _script_json(_member_colors()),
        "manchor": manchor[name],
        # the research run control (research_run.html) lives ONLY on the
        # two-strain view, never on the Forecast form
        "research_panel": header["research"],
        "rid": rid,
        # the run's clock time (its id); the forecast date is `date`
        "run_when": _run_label(rid) if rid else "",
        "date": (res or {}).get("forecast_date", ""),
        "fanq_json": _script_json(fanq), "has_fans": bool(fanq),
        "overlay_json": _script_json(overlay),
        "run_obs_json": _script_json((res or {}).get("observed", {})),
        "bngl_src": bngl_src, "bngl_file": bngl_file,
        "bngl_lines": len(bngl_src.splitlines()),
        "form": form, "status": _status})
