"""Methods (GET /methods): the methodology reference page. An APIRouter
server.py includes."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.ui.templating import templates
from app.ui.versions import VERSIONS

router = APIRouter()


def settings_reference() -> list:
    """The Forecast tab's Model settings as a reference, in the panel's own
    groups and order (knobs.panel): per group its title, what a change
    costs, and per setting what it does, its range and its default, the
    longer note and whether it is coming later. Methods' "Model settings"
    card (the panel itself carries no explanations)."""
    from app.core import knobs as K
    groups = []
    for g in K.panel("forecast")["groups"]:
        rows = []
        for r in g["rows"]:
            k = K.BY_KEY[r["key"]]
            unit = f" {k.unit}" if k.unit and k.kind in ("int", "float") else ""
            # a choice reads as its option does (a seed, no separators)
            dflt = (str(k.default) if k.kind == "choice"
                    else r["placeholder"].removeprefix("default: "))
            rows.append({
                "key": k.key, "label": r["label"], "help": k.help,
                "note": k.note, "range": k.range_text() + unit,
                "default": dflt or "August 1 of the forecast's season",
                "later": r["later"], "optional": r["optional"]})
        groups.append({"id": g["id"], "title": g["title"], "cost": g["tip"],
                       "rows": rows})
    return groups


# === Methods (/methods) -> methods.html ===
@router.get("/methods", response_class=HTMLResponse)
def methods_page(request: Request):
    """Methodology reference: the SIHRS compartment model, the fitting
    machinery, the Oracle step, the Groundhog, the Model settings, and the
    data and verification policies."""
    return templates.TemplateResponse(request, "methods.html", {
        "active": "Methods", "versions": VERSIONS,
        "settings_ref": settings_reference()})
