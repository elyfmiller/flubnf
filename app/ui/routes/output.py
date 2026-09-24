"""Output (GET /output): the latest run's submission files and their
download rules, reveal in the file manager, and the weekly report, served
as stored or rebuilt from its bundle when the report builder is newer.

The run pages (routes/forecast.py) list a run's files through
_submission_files and serve its report through _report_for_serving and
_weekly_report_file here. An APIRouter server.py includes.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.ui import shared
from app.ui.forms import _knobs
from app.ui.shared import _archive_dates, _run_label
from app.ui.templating import templates

router = APIRouter()


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


def _legacy_label(dir_name: str, d: Path) -> tuple:
    """(label, same model) for a folder written under a retired hub name
    (submit.LEGACY_DIRS): the current model's name when the run is that
    model (the Oracle step applied; the Groundhog with its donors), else
    what it was. Never the old name itself."""
    import json as _json
    from app.core.submit import LEGACY_DIRS, hub_model_id
    member = LEGACY_DIRS.get(dir_name)
    if member == "pf":
        from app.core import oracle as _oracle
        prov = _oracle.read_provenance(d) or {}
        if prov.get("applied"):
            return hub_model_id("pf"), True
        return "SIHRS filter, before the Oracle step", False
    if member == "analogue":
        try:
            spec = _json.loads((Path(d) / "results.json").read_text()
                               ).get("spec") or "{}"
            spec = _json.loads(spec) if isinstance(spec, str) else spec
            pools = ((spec or {}).get("extra") or {}).get("aux_pools")
        except Exception:
            pools = None
        if pools:
            return hub_model_id("analogue"), True
        return "Calendar analogue without donors", False
    if member == "blend":
        return "Retired blend of the two models", False
    return "Unregistered model name", False


def model_display(dir_name: str, d: Path) -> str:
    """How a submission folder's model is named on a page: registered and
    modified names as they are, a retired one through _legacy_label."""
    if dir_name in _registered_model_ids() or \
            dir_name in _modified_model_ids():
        return dir_name
    return _legacy_label(dir_name, d)[0]


def _submission_files(d: Path) -> list:
    """Submission CSVs under a workroot/archive dir, each marked submittable
    iff its directory (the hub model id) is registered. A folder an earlier
    version wrote under a retired hub name (submit.LEGACY_DIRS) is
    `archived`: kept as the run's record, named by the model it is
    (_legacy_label), never downloadable (the hub would reject the old name).
    A modified run's <hub id>-modified files are downloadable exports
    (`modified`), not submissions."""
    ok = _registered_model_ids()
    mod = _modified_model_ids()
    out = []
    for p in sorted(Path(d).glob("submission/*/*.csv")):
        name = p.parent.name
        entry = {"model": name, "name": p.name, "path": str(p),
                 "submittable": name in ok, "modified": name in mod,
                 "archived": False}
        if name not in ok and name not in mod:
            entry["model"], _same = _legacy_label(name, Path(d))
            entry["archived"] = True
        out.append(entry)
    return out


def _hub_status(path: str, today=None) -> dict:
    """One registered file's hub check for the page: {"ok", "text"}, the
    text one short line (app/core/hubcheck.summary; the window from
    tasks.json, the hub closing at 11 PM Eastern on its last day)."""
    import datetime as _dt
    from app.core import hubcheck
    s = hubcheck.summary(path)
    if not s["ok"]:
        n = len(s["problems"])
        return {"ok": False,
                "text": f"Fails {n} hub check{'s' if n != 1 else ''}: "
                        f"{s['problems'][0]}"}
    if not s["round"]:
        return {"ok": True,
                "text": f"Passes the hub's checks. {s['reference_date']} is "
                        "not a FluSight round, so this file is a record."}
    first, last = s["due"]
    today = today or _dt.date.today()
    if today > last:
        when = f"The window closed {last:%a %Y-%m-%d}."
    elif today < first:
        when = f"Due {first:%a %b %d} to {last:%a %b %d}, 11 PM ET."
    else:
        when = f"Due {last:%a %Y-%m-%d}, 11 PM ET."
    return {"ok": True, "text": f"Passes the hub's checks. {when}"}


def _reference_date(asof: str) -> str:
    """The hub reference date of a run's as-of (submit.hub_reference_date),
    "" when the as-of is unreadable."""
    from app.core.submit import hub_reference_date
    try:
        return str(hub_reference_date(asof).date()) if asof else ""
    except Exception:
        return ""


# === Output (/output): submissions, downloads, weekly report -> output.html ===
PREVIEW_ROWS = 12


def _run_data_source(rid) -> str:
    """The data file one run read, as the ledger outcome records it
    ("live target-data through ..." or "archived vintage ..."); "" for a run
    from before it was recorded, or no run."""
    if not rid:
        return ""
    import json as _json
    from app.core.data import source_phrase
    from app.core.runs import Ledger
    for r in Ledger().rows(200):
        if r.get("run_id") == rid:
            try:
                return source_phrase(
                    _json.loads(r.get("outcome") or "{}").get("data_source"))
            except (ValueError, TypeError, AttributeError):
                return ""
    return ""


@router.get("/output", response_class=HTMLResponse)
def output_page(request: Request):
    import pandas as pd
    from app.core.runs import APP_STATE
    rid, res = shared._latest_results()
    files = []
    if rid:
        for entry in _submission_files(APP_STATE / "workroots" / rid):
            entry.update({"cols": [], "rows": [], "more": 0})
            if entry["archived"]:
                files.append(entry)          # listed, never previewed
                continue
            if entry["submittable"]:
                entry["hub"] = _hub_status(entry["path"])
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
        # the file the run read ("live target-data through ..." or
        # "archived vintage ..."); "" for runs from before it was recorded
        "data_src": _run_data_source(rid),
        # the files are named by the reference date, a week after the data
        "ref": _reference_date((res or {}).get("forecast_date", "")),
        "files": files,
        "archive_dates": list(reversed(_archive_dates())),
        "has_report": bool(rid and (APP_STATE / "workroots" / rid / "report.html").is_file())})


def _dataset_workroot(p: Path, app_state: Path) -> bool:
    """Whether `p` lies in the workroot of a run on a custom dataset (its
    results.json names one): such files carry the uploaded data."""
    import json as _json
    try:
        rel = p.relative_to((app_state / "workroots").resolve())
    except ValueError:
        return False
    if len(rel.parts) < 2:
        return False
    try:
        res = _json.loads((app_state / "workroots" / rel.parts[0]
                           / "results.json").read_text())
    except Exception:
        return False
    return isinstance(res, dict) and bool(res.get("dataset"))


@router.get("/output/download")
def output_download(request: Request, path: str):
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
    if _dataset_workroot(p, APP_STATE):
        # a dataset run's exports carry the upload: localhost only, as the
        # dataset's own pages (datasets_ui.local_only)
        from app.ui import datasets_ui as _dsu
        refused = _dsu.local_only(request)
        if refused:
            return refused
    if p.parent.parent.name == "submission" \
            and p.parent.name not in _registered_model_ids() \
            and p.parent.name not in _modified_model_ids():
        return HTMLResponse(
            "<p>This folder is not a registered hub model: the file was "
            "written by an earlier version under a retired hub name and is "
            "kept as a record, not for submission. Use Show in Finder to "
            "open it for reference.</p>", status_code=409)
    return FileResponse(p, filename=p.name, media_type="text/csv",
                        content_disposition_type="attachment")


@router.post("/output/reveal")
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


@router.get("/output/report", response_class=HTMLResponse)
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


@router.get("/output/report/download")
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
