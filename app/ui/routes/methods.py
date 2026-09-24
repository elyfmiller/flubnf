"""Methods (GET /methods): the methodology reference page. An APIRouter
server.py includes."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.ui.templating import templates
from app.ui.versions import VERSIONS

router = APIRouter()


# === Methods (/methods) -> methods.html ===
@router.get("/methods", response_class=HTMLResponse)
def methods_page(request: Request):
    """Methodology reference: the SIHRS compartment model, the fitting
    machinery, the Oracle step, the Groundhog, and the data and verification
    policies."""
    return templates.TemplateResponse(request, "methods.html", {
        "active": "Methods", "versions": VERSIONS})
