"""Custom datasets in the console: upload, browse, forecast and replay.

Routes (an APIRouter included by app/ui/server.py; the same-host guard
covers every POST, and each GET that returns dataset content checks the
Host header too, since an upload may be private data):

  POST /data/datasets/check            check an upload without storing it:
                                       JSON with the result box's HTML (every
                                       problem, a column mapping, or a
                                       preview) for static/dataset_upload.js
  POST /data/datasets                  store an upload (size capped before
                                       and while parsing), then open it where
                                       `next` says: data, forecast or replay
  POST /data/datasets/{id}/delete      delete, with the name as confirmation
  POST /storage/datasets/{id}/delete   delete from the Storage tab, with its
                                       runs' workroots (the name confirms)
  POST /run/dataset                    a forecast on a dataset
  POST /retro/dataset/run              replay a week range on a dataset
  GET  /retro/dataset/{id}/{stamp}     one replay's results

and the context builders server.py calls when a page is opened with
`?source=<dataset id>` (Data, Forecast, /api/series). A dataset is never the
default source: every page and run opts in by naming it.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date as _date
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import (HTMLResponse, JSONResponse, PlainTextResponse,
                               RedirectResponse)
from markupsafe import Markup, escape
from starlette.concurrency import run_in_threadpool

from app.core.runs import GROUNDHOG_OWN_DATA
from app.ui import forms, pipeline, retro_seasons, shared, templating, versions
from app.ui import state as ui_state

router = APIRouter()

#: what the forecast form last held, per dataset (never the hub's _last_form)
_LAST: dict = {}
#: the replay a worker is running now: {"id", "stamp"} or {}
_REPLAY: dict = {}
#: what "Replay this" just stored, for the replay card it opens (one slot,
#: taken by the card's next render): {dataset id: {"text", "warnings"}}
_STORED: dict = {}

#: the Groundhog wherever it runs on a dataset (exported as FluBNF-Groundhog)
GROUNDHOG = GROUNDHOG_OWN_DATA
#: the dataset members as the Forecast form names them
ENGINE_NAMES = {"all": f"Both: plain SIHRS particle filter + {GROUNDHOG}",
                "pf": "plain SIHRS particle filter only",
                "analogue": f"{GROUNDHOG} only"}
#: the members as the Retrospective card's replay form names them
REPLAY_ENGINE_NAMES = {"analogue": f"{GROUNDHOG} only",
                       "all": f"{GROUNDHOG} and plain SIHRS particle filter"}
#: fan and table names on dataset pages
MEMBER_NAMES = {"pf": "plain SIHRS PF", "analogue": GROUNDHOG}
#: the upload body may exceed the file by the multipart framing and fields
FORM_SLACK = 64 * 1024
#: where a stored upload opens (the upload box's buttons post `next`)
NEXT_PAGES = ("data", "forecast", "replay")
#: groups drawn in an upload's preview (the rest are counted)
PREVIEW_GROUPS = 12
#: a preview sparkline's viewBox
SPARK_W, SPARK_H = 160, 40


def _S():
    from app.ui import server
    return server


def _D():
    from app.core import datasets
    return datasets


def local_only(request: Request):
    """403 unless the Host names this machine (a DNS-rebinding page cannot
    read uploaded data through a GET); None when fine."""
    if (shared._authority_hostname(request.headers.get("host", ""))
            not in shared._LOCAL_HOSTNAMES):
        return PlainTextResponse("Refused: the Host header does not name "
                                 "localhost.\n", status_code=403)
    return None


def get_dataset(ds_id):
    """The stored dataset, or None for a malformed or unknown id."""
    D = _D()
    if not D.valid_id(ds_id):
        return None
    try:
        return D.get(ds_id)
    except D.DatasetError:
        return None


def dataset_rows() -> list:
    """The Data tab's list: one row per stored dataset."""
    out = []
    try:
        items = _D().list_datasets()
    except Exception:
        return out
    for ds in items:
        m = ds.meta
        try:
            weeks = len(ds.weeks())
        except Exception:
            weeks = 0
        out.append({
            "id": ds.id, "name": ds.name, "groups": len(ds.groups),
            "group_names": ds.groups, "weeks": weeks,
            "first": m["date_range"][0], "last": m["date_range"][-1],
            "kind": ds.kind, "population": ds.has_population,
            "vintages": ds.has_as_of, "n_vintages": len(ds.vintages()),
            "national": ds.national_group, "pf": ds.pf_eligible,
            "format": m.get("format"), "target": m.get("target"),
            "warnings": m.get("warnings") or [],
            "busy": busy_with(ds.id)})
    return out


def max_mb() -> int:
    return _D().DEFAULT_LIMITS.max_bytes // (1024 * 1024)


def choices() -> list:
    """(id, name) for the data-source selectors; [] without datasets."""
    try:
        return [(ds.id, ds.name) for ds in _D().list_datasets()]
    except Exception:
        return []


def busy_with(ds_id: str) -> str:
    """Why a dataset cannot be deleted now ('' when it can): a console run
    or a replay is using it."""
    if (ui_state._status.get("running")
            and ui_state._status.get("dataset_id") == ds_id):
        return "a run on it is in progress"
    if _REPLAY.get("id") == ds_id:
        return "a replay on it is in progress"
    return ""


# ------------------------------------------------------------- Data tab

def data_context(ds, loc: str = "", vintage: str = "") -> dict:
    """The Data tab's browser for one dataset: the vintage-browser keys
    (data.html's chart and table) filled from the dataset, truncated at the
    chosen vintage so final data never shows later weeks."""
    ctx = {"ds": {"id": ds.id, "name": ds.name, "kind": ds.kind,
                  "vintage_true": ds.vintage_true,
                  "national": ds.national_group,
                  "unit": "count" if ds.kind == "count" else "value"},
           "view_note": ""}
    vs = ds.vintages()
    sel_v = vintage if vintage in vs else vs[-1]
    if vintage and sel_v != vintage:
        ctx["view_note"] = (f"No snapshot for {vintage}; showing the latest, "
                            f"{sel_v}.")
    names = ds.groups
    sel = loc if loc in names else (names[0] if names else "")
    s = ds.series(sel, sel_v if ds.vintage_true else None) if sel else {}
    dates, values = list(s.get("dates") or []), list(s.get("values") or [])
    ctx.update({
        "vintages": list(reversed(vs)), "sel_vintage": sel_v,
        "sel_loc": sel, "loc_names": names,
        "sel_summary": None, "series_n": len(dates),
        "series_table": list(zip(dates, values))[-12:][::-1],
        "peak": (max(zip(dates, values), key=lambda p: p[1])
                 if values else None),
        "series_json": (templating._script_json({"dates": dates,
                                                 "values": values})
                        if values else "null")})
    return ctx


async def _capped_form(request: Request, cap: int):
    """The multipart form, refused (None) when Content-Length already
    exceeds the cap and cut off while streaming when a chunked body does."""
    from starlette.formparsers import MultiPartParser

    class TooBig(Exception):
        pass

    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared = 0
    if declared > cap:
        return None

    async def stream():
        n = 0
        async for chunk in request.stream():
            n += len(chunk)
            if n > cap:
                raise TooBig()
            yield chunk
    try:
        parser = MultiPartParser(request.headers, stream(), max_files=1,
                                 max_fields=20)
        return await parser.parse()
    except TooBig:
        return None


def _render_data(request, _code: int = 200, **extra):
    """data.html with a refused store's report inline (not the one-slot
    flash); its result box says nothing was stored ("refused"), which a
    check, storing nothing by design, never says."""
    S = _S()
    up = extra.get("upload")
    if up and up.get("chk"):
        extra["upload"] = {**up, "chk": {**up["chk"], "refused": True}}
    ctx = S._data_context()
    ctx.update(extra)
    return templating.templates.TemplateResponse(request, "data.html", ctx,
                                                 status_code=_code)


# ------------------------------------------------ the upload box (one partial)

def _form_columns(form) -> dict:
    """The column mapping the result box posts (col_<role> = '#N')."""
    D = _D()
    return {r: str(form.get(f"col_{r}") or "").strip() for r in D.ROLES
            if str(form.get(f"col_{r}") or "").strip()}


def _sparkline(points, first: _date, last: _date, top: float) -> str:
    """SVG polyline points for one group's weeks on the shared date axis."""
    span = max((last - first).days, 1)
    pad = 2.0
    if len(points) > 400:                       # a long series, thinned
        step = len(points) / 400.0
        points = [points[int(i * step)] for i in range(400)] + [points[-1]]
    out = []
    for d, v in points:
        x = pad + (SPARK_W - 2 * pad) * (d - first).days / span
        y = SPARK_H - pad - ((SPARK_H - 2 * pad) * v / top if top > 0 else 0)
        out.append(f"{x:.1f},{y:.1f}")
    return " ".join(out)


def _preview(rep, kind: str) -> dict:
    """What a valid upload holds: counts and dates, the first rows as read,
    and a sparkline per group (the newest snapshot of each week)."""
    s = rep.summary
    newest = {}
    for a, name, _, d, v, _ in rep.records:
        if v is None:
            continue
        k = (name, d)
        if k not in newest or (a or _date.min) >= newest[k][0]:
            newest[k] = (a or _date.min, v)
    by = {}
    for (name, d), (_, v) in newest.items():
        by.setdefault(name, []).append((d, v))
    first = _date.fromisoformat(s["first"])
    last = _date.fromisoformat(s["last"])
    sparks = []
    for name in s["groups"][:PREVIEW_GROUPS]:
        pts = sorted(by.get(name, []))
        if not pts:
            continue
        top = max(v for _, v in pts)
        peak = max(pts, key=lambda p: p[1])
        sparks.append({"name": name, "points": _sparkline(pts, first, last,
                                                          top),
                       "label": f"{name}: {len(pts)} weeks, peak "
                                f"{peak[1]:,.6g} ({peak[0].isoformat()})"})
    return {"groups": s["groups"], "n_groups": len(s["groups"]),
            "more": max(0, len(s["groups"]) - PREVIEW_GROUPS),
            "first": s["first"], "last": s["last"], "weeks": s["weeks"],
            "rows": s["rows"], "kind": kind or s["inferred_kind"],
            "inferred": not kind, "population": s["has_population"],
            "snapshots": len(s["as_of"]), "national": s.get("national_group"),
            "target": s.get("target"),
            "read_as": f"{s['delimiter']}-separated, {s['encoding']}",
            "first_rows": s.get("first_rows") or [],
            # the file's own date column only when it differs from the week
            "dates_differ": any(r["date"] != r["week"]
                                for r in s.get("first_rows") or []),
            "sparks": sparks, "w": SPARK_W, "h": SPARK_H}


#: mapping-step problems shown in the problem box: a reason to choose (two
#: columns that could each be a role, a mapping that named nothing), never
#: a silent pick; a role no header matched is only asked for
MAPPING_PROBLEMS = ("ambiguous_columns", "column_unknown")


def _mapping_why(rep) -> list:
    """The mapping's own hint: one line naming the roles no header matched
    (the reasons to choose are problems, MAPPING_PROBLEMS)."""
    D = _D()
    if not rep.needs_mapping:
        return []
    unset = [r for r in D.REQUIRED
             if r not in rep.guess and r not in rep.ambiguous]
    out = []
    if unset:
        names = [f"the {r}" for r in unset]
        out.append("Choose the column that holds "
                   + (", ".join(names[:-1]) + " and " if len(names) > 1
                      else "") + names[-1] + ".")
    return out


#: a date in a problem or a notice (2024-03-16, or 2024-03-32 as written)
_DATE_TOKEN = re.compile(r"\d{4}-\d{1,2}-\d{1,2}")


def _whole_dates(text) -> Markup:
    """Problem or notice text, escaped, with each date kept on one line: at
    phone width a browser breaks it after a hyphen ('2024-03-' / '16')."""
    return Markup(_DATE_TOKEN.sub(lambda m: f'<span class="nw">{m[0]}</span>',
                                  str(escape(text))))


def check_view(rep, *, kind: str = "", columns=None) -> dict:
    """The result box's context (templates/_dataset_check.html) for one
    report: every problem grouped by kind, a column mapping when that is
    what is missing (instead of an error; two columns that could each be
    a role are also a problem, with its reason, and neither is picked),
    the target picker when a file holds several (a choice to make, not a
    problem; nothing is picked for the user), the notices, and a preview
    when it is valid."""
    D = _D()
    columns = columns or {}
    choose = len(rep.targets) > 1 and "target_required" in rep.codes
    mapping = None
    if rep.headers and (rep.needs_mapping or columns):
        labels = {"date": "Date", "group": "Group", "value": "Value",
                  "population": "Population"}
        mapping = {
            "headers": [(f"#{i + 1}", h) for i, h in enumerate(rep.headers)
                        if h],
            "why": _mapping_why(rep),
            "roles": [{"role": r, "label": labels[r],
                       "required": r in D.REQUIRED,
                       "value": columns.get(r) or rep.guess.get(r, "")}
                      for r in D.ROLES]}
    shown = [p for p in rep.problems
             if not (choose and p.code == "target_required")
             and (p.code in MAPPING_PROBLEMS or not rep.needs_mapping)]
    problems = [(k, [{"message": _whole_dates(p), "rows": list(p.rows)}
                     for p in ps])
                for k, ps in D.problem_groups(shown)]
    return {"ok": rep.ok, "problems": problems,
            "n": sum(len(ps) for _, ps in problems),
            "mapping": mapping, "needs_mapping": rep.needs_mapping,
            "notices": [_whole_dates(w) for w in rep.warnings],
            "targets": rep.targets if len(rep.targets) > 1 else [],
            "target": (rep.summary or {}).get("target") or "",
            "preview": _preview(rep, kind) if rep.ok and rep.summary else None}


def check_status(chk: dict) -> str:
    """The upload box's status line (role=status): what a check found, in
    a few words, read out instead of the whole result."""
    if chk.get("preview"):
        pv = chk["preview"]
        return (f"Ready to use: {pv['n_groups']} group"
                f"{'' if pv['n_groups'] == 1 else 's'}, {pv['weeks']} week"
                f"{'' if pv['weeks'] == 1 else 's'}.")
    n = chk.get("n") or 0
    if chk.get("needs_mapping"):
        return "Choose which column is which." + (
            f" {n} problem{'' if n == 1 else 's'} to fix." if n else "")
    if chk.get("targets") and not chk.get("target") and not n:
        return "Choose the target."
    return f"{n} problem{'' if n == 1 else 's'} to fix."


def _message_view(message: str) -> dict:
    """The result box for a refusal that is not about the file's content."""
    return {"ok": False, "problems": [("File", [{"message": message,
                                                 "rows": []}])],
            "n": 1, "mapping": None, "notices": [], "targets": [],
            "target": "", "preview": None}


def render_check(chk: dict, where: str = "data") -> str:
    """The result box's HTML (the same macro the pages render)."""
    tpl = templating.templates.get_template("_dataset_check.html")
    return str(tpl.module.result(chk, where))


def _kind_field(form):
    """The posted kind: '' = from the values; None = not a kind. A kind
    the upload box filled in from the values (kind_auto=1, never picked by
    hand) stays "from the values", as the CLI records it."""
    k = str(form.get("kind") or "").strip()
    if k not in ("",) + _D().KINDS:
        return None
    return "" if str(form.get("kind_auto") or "") == "1" else k


@router.post("/data/datasets/check")
async def check(request: Request):
    """Check one upload and store nothing: JSON with the result box's HTML
    and what the form needs (the inferred kind, the targets, whether a
    column mapping is asked for). A file with several targets shows the
    picker and no preview until one is chosen."""
    refused = local_only(request)
    if refused:
        return refused
    D = _D()
    where = str(request.query_params.get("where") or "data")
    where = where if where in NEXT_PAGES else "data"

    def answer(chk, code=200, **extra):
        return JSONResponse({"ok": chk["ok"], "html": render_check(chk, where),
                             "status": check_status(chk), **extra},
                            status_code=code)
    if not request.headers.get("content-type", "").startswith(
            "multipart/form-data"):
        return answer(_message_view("Expected a multipart/form-data upload."),
                      400)
    try:
        form = await _capped_form(request,
                                  D.DEFAULT_LIMITS.max_bytes + FORM_SLACK)
    except Exception:
        return answer(_message_view("The upload could not be read; choose "
                                    "the file again."), 400)
    if form is None:
        return answer(_message_view(
            f"The file is larger than the {max_mb()} MB limit; nothing was "
            "read."), 413)
    f = form.get("file")
    if f is None or not hasattr(f, "file") or not getattr(f, "filename", ""):
        return answer(_message_view("Choose a CSV file."), 400)
    kind = _kind_field(form)
    if kind is None:
        return answer(_message_view("Say whether the values are counts or "
                                    "rates."), 400)
    target = str(form.get("target") or "").strip() or None
    columns = _form_columns(form)
    try:
        def run():
            f.file.seek(0)
            return D.validate(f.file, kind=kind or None, target=target,
                              columns=columns)
        rep = await run_in_threadpool(run)
    finally:
        try:
            await f.close()
        except Exception:
            pass
    chk = check_view(rep, kind=kind, columns=columns)
    return answer(chk, inferred_kind=(rep.summary or {}).get("inferred_kind"),
                  target=target or "", targets=rep.targets,
                  needs_mapping=rep.needs_mapping,
                  # the name a store takes when none is typed
                  name=D.default_name(Path(str(f.filename)).name,
                                      rep.targets, target))


@router.post("/data/datasets")
async def upload(request: Request):
    """Validate and store one CSV, then open it where `next` says (the
    Data tab, the Forecast tab, or the Retrospective tab's replay card).
    Problems are shown inline on the Data tab (every one at once) and
    nothing is stored."""
    D = _D()
    cap = D.DEFAULT_LIMITS.max_bytes + FORM_SLACK
    ctype = request.headers.get("content-type", "")
    if not ctype.startswith("multipart/form-data"):
        return PlainTextResponse("Expected a multipart/form-data upload.\n",
                                 status_code=400)
    form = await _capped_form(request, cap)
    mb = D.DEFAULT_LIMITS.max_bytes // (1024 * 1024)
    if form is None:
        return _render_data(request, upload={
            "name": "", "kind": "", "chk": _message_view(
                f"The upload is larger than the {mb} MB limit; nothing was "
                "read or stored.")}, _code=413)
    f = form.get("file")
    name = str(form.get("name") or "").strip()
    kind = _kind_field(form)
    target = str(form.get("target") or "").strip() or None
    columns = _form_columns(form)
    nxt = str(form.get("next") or "data")
    back = {"name": name, "kind": kind or "", "target": target or ""}
    if f is None or not hasattr(f, "file") or not getattr(f, "filename", ""):
        return _render_data(request, upload={
            **back, "chk": _message_view("Choose a CSV file to upload.")},
            _code=400)
    fname = Path(str(f.filename)).name
    if kind is None:
        return _render_data(request, upload={
            **back, "chk": _message_view("Say whether the values are counts "
                                         "or rates.")}, _code=400)
    try:
        f.file.seek(0)
        ds = await run_in_threadpool(
            lambda: D.ingest(f.file, name[:80] or None, kind=kind or None,
                             target=target, filename=fname, columns=columns))
    except D.DatasetError as e:
        chk = (check_view(e.report, kind=kind, columns=columns)
               if e.report is not None else _message_view(str(e)))
        return _render_data(request, upload={**back, "chk": chk}, _code=422)
    finally:
        try:
            await f.close()
        except Exception:
            pass
    shared._invalidate_scans()
    warn = ds.meta.get("warnings") or []
    done = (f"Stored the dataset {ds.name}: {len(ds.groups)} group(s), "
            f"{len(ds.weeks())} week(s).")
    if nxt == "replay":
        # said in the replay card the page scrolls to, not at its top
        _STORED.clear()
        _STORED[ds.id] = {"text": done, "warnings": list(warn)}
        ui_state._status["log"].append(" ".join([done] + warn))
        return RedirectResponse(f"/retro?dataset={ds.id}#dataset-replay",
                                status_code=303)
    shared._flash(done + (" " + " ".join(warn) if warn else ""))
    if nxt == "forecast":
        return RedirectResponse(f"/forecast?source={ds.id}", status_code=303)
    return RedirectResponse(f"/data?source={ds.id}#datasets", status_code=303)


@router.post("/data/datasets/{ds_id}/delete")
def delete(request: Request, ds_id: str, confirm: str = Form("")):
    ds = get_dataset(ds_id)
    if ds is None:
        shared._flash("No such dataset; nothing was deleted.")
        return RedirectResponse("/data#datasets", status_code=303)
    why = busy_with(ds.id)
    if why:
        shared._flash(f"{ds.name} was not deleted: {why}.")
        return RedirectResponse("/data#datasets", status_code=303)
    if confirm != ds.name:
        shared._flash(f"Deleting {ds.name} was not confirmed; "
                      "nothing was deleted.")
        return RedirectResponse("/data#datasets", status_code=303)
    shared._flash(deleted_message(ds, *delete_everything(ds)))
    return RedirectResponse("/data#datasets", status_code=303)


def api_series(ds, locs: str) -> dict:
    """/api/series for a dataset: the newest data per group."""
    out = {}
    for n in [l for l in locs.split("|") if l][:8]:
        if n in ds.groups:
            out[n] = ds.series(n)
    return out


# ----------------------------------------------------------- Forecast tab

def _dataset_view(ds) -> dict:
    state = pipeline._pf_engine_state()
    return {"id": ds.id, "name": ds.name, "kind": ds.kind,
            "groups": ds.groups, "national": ds.national_group,
            "vintage_true": ds.vintage_true, "pf_eligible": ds.pf_eligible,
            "pf_state": state,
            "pf_ok": ds.pf_eligible and state == "ready",
            "pf_why": ("" if ds.pf_eligible and state == "ready" else
                       "the dataset needs counts and a population"
                       if not ds.pf_eligible else
                       "the particle-filter engine is not installed"
                       if state == "absent" else
                       "the particle-filter engine install is incomplete")}


def _ledger_for(ds_id: str, n: int = 5) -> list:
    """The newest ledger rows of runs on this dataset."""
    S = _S()
    out = []
    for r in S.Ledger().rows(200):
        try:
            x = (json.loads(r.get("spec") or "{}").get("extra") or {})
        except Exception:
            continue
        if (x.get("dataset") or {}).get("id") == ds_id:
            out.append(r)
            if len(out) >= n:
                break
    return out


def latest_results_for(ds_id: str):
    """(run_id, results) of the newest stored run on this dataset."""
    for f in shared._workroot_results():
        try:
            res = json.loads(f.read_text())
        except Exception:
            continue
        if (res.get("dataset") or {}).get("id") == ds_id:
            return f.parent.name, res
    return None, None


#: knobs a dataset form never shows or records: its FluSurv-NET box
#: decides the Groundhog's auxiliary bank
AUX_KEYS = ("groundhog.aux", "groundhog.aux_weight")
#: knobs that apply to counts alone (a rate dataset is never floored), with
#: the help their tip carries on a dataset
COUNT_ONLY = {"output.floor_lam": "Poisson noise floor so no cell is a "
                                  "point mass; applied to counts only."}
#: the members as a dataset panel's tips name them
PANEL_MEMBERS = {"pf": "plain SIHRS particle filter", "analogue": GROUNDHOG}
#: (title, tip) of a dataset panel's groups
PANEL_GROUPS = {
    "data": ("Fit window", "Which of the dataset's weeks the models see."),
    "fit": ("Particle filter (plain SIHRS)",
            "Settings of the fit itself; a change refits every group."),
    "groundhog": (GROUNDHOG, "The calendar analogue on your data's earlier "
                             "seasons; instant."),
    "output": ("Output", "Applied to the finished forecasts of counts."),
}
#: what the panel's "?" says a change does, on a run and on a replay
PANEL_ABOUT = {
    "forecast": ("Every value starts at the shipped model's. Changing any of "
                 "them marks the run modified wherever it appears, and its "
                 "export files are named <model>-modified."),
    "replay": ("Every value starts at the shipped model's. Changing any of "
               "them marks the replay modified wherever it is listed, and "
               "the values are recorded with it."),
}


def dataset_panel(panel, *, kind: str = "", where: str = "forecast",
                  prefix: str = "", engine: str = ""):
    """The Model settings panel (forms._knob_panel with PANEL_MEMBERS) as
    a dataset run or replay reads it: no Oracle step (it does not run on
    custom data), no auxiliary-bank rows, no hub-name override (there is
    none), the groups named as the members run on the data.

    `kind`: the dataset's kind; a rate dataset has no floor row, and ''
    (a form that picks among datasets) keeps it marked counts-only for the
    page to hide. `where`: "forecast" or "replay". `prefix` and `engine`:
    a second panel's id prefix and the id of its model select."""
    if not panel:
        return panel
    by_key = forms._knobs.BY_KEY
    groups = []
    for g in panel["groups"]:
        if g["id"] == "step":
            continue
        rows = []
        for r in g["rows"]:
            if r["key"] in AUX_KEYS:
                continue
            if r["key"] in COUNT_ONLY:
                if kind and kind != "count":
                    continue
                r = {**r, "only": "count", "tip": r["tip"].replace(
                    by_key[r["key"]].help, COUNT_ONLY[r["key"]])}
            rows.append(r)
        if not rows:
            continue
        title, tip = PANEL_GROUPS.get(g["id"], (g["title"], g["tip"]))
        groups.append({**g, "title": title, "tip": tip, "rows": rows,
                       "affects": " ".join(sorted(
                           {m for r in rows for m in r["affects"].split()}))})
    modified = any(r["value"].strip() not in ("", r["default"])
                   for g in groups for r in g["rows"] if not r["later"])
    return {**panel, "groups": groups, "modified": modified,
            "override": False, "about": PANEL_ABOUT[where],
            "scope": panel["scope"] if where == "forecast"
            else "dataset-replay",
            "prefix": prefix, "engine": engine}


def knob_values(ds, knob_fields, knobs_json) -> dict:
    """The knob channel's raw values as a dataset form posts them, less
    what a dataset never records: the auxiliary-bank knobs, and the
    counts-only knobs on a rate dataset."""
    return {k: v for k, v in forms._knob_raw(knob_fields or {},
                                             knobs_json).items()
            if k not in AUX_KEYS
            and not (k in COUNT_ONLY and ds.kind != "count")}


def forecast_page(request: Request, ds):
    """The Forecast tab with a dataset as the data source: forecast.html
    with the dataset's groups, weeks, fans and runs."""
    S = _S()
    from app.core.runs import spec_settings
    view = _dataset_view(ds)
    dates = ds.forecast_dates()
    newest = dates[-1] if dates else ""
    form = dict(_LAST.get(ds.id) or {
        "forecast_date": newest, "locations": ["all"],
        "engine": "all" if view["pf_ok"] else "analogue",
        "weeks_to_drop": 0, "replicates": 3, "season_start": "",
        "flusurv": False})
    rid, res = latest_results_for(ds.id)
    fanq = {}
    if res:
        # the stored convention, as the hub's forecast_page passes it: the
        # fan script places stored horizon h at the as-of + 7h
        for m, md in (res.get("models") or {}).items():
            good = {n: qs for n, qs in md.items()
                    if isinstance(qs, dict)
                    and all(isinstance(v, dict) for v in qs.values())}
            if good:
                fanq[m] = good
    sel = [g for g in form["locations"] if g in ds.groups][:8] or ds.groups[:1]
    series = {n: ds.series(n) for n in sel}
    rows = _ledger_for(ds.id)
    for r in rows:
        r["label"] = shared._run_label(r["run_id"], r.get("spec", ""))
        r["modified"] = S._runs.is_modified(r.get("spec", ""))
        r["chips"] = outcome_chips(r.get("outcome", ""))
        r["settings"] = spec_settings(r.get("spec", ""))
        r["has_report"] = False
        if r["status"] == "running" and not (
                ui_state._status.get("running") or "").endswith(r["run_id"]):
            r["status"] = "interrupted"
    anchor, _ = forms.resolve_anchor(form.get("forecast_date", ""), dates)
    ok = anchor in dates
    note = (f"Anchor week: {anchor}." if ok
            else "No week of this dataset on or before that date.")
    return templating.templates.TemplateResponse(request, "forecast.html", {
        "active": "Forecast", "engines": ui_state.ENGINES,
        "status": ui_state._status,
        "ledger": rows, "all_locs": ds.groups,
        "vintage_dates": list(reversed(dates)), "anchor_note": note,
        "default_date": newest, "locations_error": "", "form": form,
        "knob_panel": dataset_panel(
            forms._knob_panel("forecast", form, names=PANEL_MEMBERS),
            kind=ds.kind),
        "elapsed0": shared._console_elapsed(),
        "series_json": templating._script_json(series),
        "fanq_json": templating._script_json(fanq),
        "model_names_json": templating._script_json(
            {**templating._model_names(), **MEMBER_NAMES}),
        "member_colors_json": templating._script_json(
            templating._member_colors()),
        "season_colors_json": templating._script_json(
            templating._season_colors()),
        "run_obs_json": templating._script_json(
            (res or {}).get("observed", {})),
        "fc_date": (res or {}).get("forecast_date", ""),
        "fc_run": rid or "",
        "dataset": view, "source_choices": choices(),
        "engine_names": ENGINE_NAMES})


def outcome_chips(outcome_json) -> str:
    """A dataset run's ledger chips: fixed phrases and numbers only; relWIS
    always names the in-house persistence baseline."""
    from app.core.custom_run import BASELINE
    try:
        o = (json.loads(outcome_json) if isinstance(outcome_json, str)
             else outcome_json) or {}
    except Exception:
        return ""
    bits = []
    if "pf_cells" in o:
        n = int(o["pf_cells"])
        bits.append(f"PF {n} fit{'s' if n != 1 else ''}")
    if o.get("pf_failures"):
        nf = len(o["pf_failures"])
        bits.append(f'<span class="bad">{nf} failure{"s" if nf != 1 else ""}'
                    '</span>')
    if o.get("exports"):
        n = len(o["exports"])
        bits.append(f"{n} export file{'s' if n != 1 else ''}")
    for m, sc in sorted((o.get("custom_scores") or {}).items()):
        v = sc.get("relwis")
        if v is None:
            continue
        cells = int(sc.get("cells") or 0)
        bits.append(f'{MEMBER_NAMES.get(m, m)} relWIS <span class="relwis '
                    f'{"ok" if float(v) < 1 else "bad"}">{float(v):.3f}</span>'
                    f" vs {BASELINE} ({cells} cell{'s' if cells != 1 else ''})")
    if o.get("error"):
        bits.append('<span class="bad">failed</span>; the full error is on '
                    'the run page')
    return " · ".join(bits)


async def _knob_fields(request: Request) -> dict:
    """The Model settings panel's knob.<key> fields (forms._knob_form)."""
    return await forms._knob_form(request)


@router.post("/run/dataset")
def run_dataset(request: Request, background: BackgroundTasks,
                dataset: str = Form(...),
                forecast_date: str = Form(...),
                locations: list = Form([]),
                engine: str = Form("analogue"),
                mode: str = Form("realtime"),
                flusurv: str = Form(""),
                weeks_to_drop: int = Form(0),
                replicates: int = Form(3),
                particles: int = Form(10_000),
                season_start: str = Form(""),
                drop_same_day: int = Form(0),
                knob_fields: dict = Depends(_knob_fields),
                knobs: str = Form("")):
    """Start a forecast on a dataset (the Forecast tab's dataset form)."""
    return _start_run(request, background, dataset, forecast_date,
                      locations, engine, mode, flusurv, weeks_to_drop,
                      replicates, particles, season_start, drop_same_day,
                      knobs, knob_fields)


def _start_run(request, background, ds_id, forecast_date, locations, engine,
               mode, flusurv, weeks_to_drop, replicates, particles,
               season_start, drop_same_day, knobs_json, knob_fields=None):
    from app.core.runs import RunSpec, spec_settings
    ds = get_dataset(ds_id)
    if ds is None:
        shared._flash("That dataset no longer exists. Nothing was run.")
        return RedirectResponse("/forecast", status_code=303)
    here = f"/forecast?source={ds.id}"
    dates = ds.forecast_dates()
    fd = forms._str_field(forecast_date).strip()
    pick, _ = forms.resolve_anchor(fd, dates)
    fd = pick or fd
    if fd not in dates:
        earlier = [d for d in dates if d <= fd]
        near = earlier[-1] if earlier else (dates[0] if dates else "")
        shared._flash(
            f"{ds.name} holds no week {fd} to forecast from."
            + (f" Nearest earlier week: {near}." if earlier else
               f" Its first forecastable week is {near}." if near else ""))
        return RedirectResponse(here, status_code=303)
    if engine not in ENGINE_NAMES:
        shared._flash(f"'{engine}' is not a model choice. Nothing was run.")
        return RedirectResponse(here, status_code=303)
    view = _dataset_view(ds)
    if engine in ("all", "pf") and not view["pf_ok"]:
        shared._flash(f"The plain SIHRS particle filter cannot run on "
                      f"{ds.name}: {view['pf_why']}. Choose {GROUNDHOG} "
                      "only. Nothing was run.")
        return RedirectResponse(here, status_code=303)
    groups = [x.strip() for l in locations for x in str(l).split("|")
              if x.strip()]
    if any(g.lower() == "all" for g in groups):
        groups = list(ds.groups)
    unknown = [g for g in groups if g not in ds.groups]
    groups = [g for g in ds.groups if g in groups]      # dataset order
    if unknown:
        shared._flash(f"Not groups of {ds.name}: {', '.join(unknown[:5])}. "
                      "Nothing was run.")
        return RedirectResponse(here, status_code=303)
    if not groups:
        shared._flash("Select at least one group. Nothing was run.")
        return RedirectResponse(here, status_code=303)
    want_fs = forms._str_field(flusurv).lower() in ("1", "on", "true", "yes")
    season_start = forms._str_field(season_start).strip()
    kraw = knob_values(ds, knob_fields, knobs_json)
    _LAST[ds.id] = {"forecast_date": fd, "locations": groups
                    if len(groups) < len(ds.groups) else ["all"],
                    "engine": engine, "weeks_to_drop": weeks_to_drop,
                    "replicates": replicates, "particles": particles,
                    "season_start": season_start,
                    "drop_same_day": forms._int_field(drop_same_day),
                    "flusurv": want_fs,
                    "knobs": {k: v for k, v in kraw.items()
                              if isinstance(v, str)}}
    try:
        nd = forms._knobs.resolve(
            kraw, engine, scope="forecast", forecast_date=fd,
            oracle_step=False,
            legacy={"particles": particles, "replicates": replicates,
                    "season_start": season_start,
                    "weeks_to_drop": weeks_to_drop,
                    "drop_same_day": bool(forms._int_field(drop_same_day))})
        mode = "realtime" if fd == dates[-1] else "vintage"
        extra = {"mode": mode, "oracle": "none", "dataset": ds.ref(),
                 "dataset_final": not ds.vintage_true}
        if want_fs:
            from app.core.engines import analogue as _an
            fn = _an.aux_preset("flusurv")
            extra["aux_pools"] = fn(None, 0, None)["aux_pools"]
            extra["analogue_aux"] = fn.__name__.split(":", 1)[1]
        forms._knobs.write_extra(nd, extra)
    except ValueError as e:
        shared._flash(f"Model settings: {e}. Nothing was run.")
        return RedirectResponse(here, status_code=303)
    kspec = forms._knobs.spec_fields(nd)
    with ui_state._engine_lock:
        if ui_state._status.get("running"):
            shared._flash("A run is already in progress; not starting "
                          "another.")
            return RedirectResponse(here + "#results", status_code=303)
        live = sorted(x for x in retro_seasons._known_seasons()
                      if retro_seasons._season_status(x)
                      in retro_seasons._RETRO_ACTIVE)
        if live:
            shared._flash("A retrospective replay holds the engine ("
                          + ", ".join(live) + "). Stop or pause it from the "
                          "Retrospective tab first; nothing was run.")
            return RedirectResponse(here, status_code=303)
        ui_state._status["running"] = "starting"
        ui_state._status["dataset_id"] = ds.id
        shared._invalidate_scans()
        ui_state._status["started_utc"] = time.time()
        ui_state._status["run_label"] = f"{fd} · {ds.name} · queued"
    spec = RunSpec(engine=engine, forecast_date=fd, locations=groups,
                   season_start=kspec.get("season_start", ""),
                   weeks_to_drop=int(kspec.get("weeks_to_drop", 0)),
                   drop_same_day=bool(kspec.get("drop_same_day", False)),
                   replicates=int(kspec.get("replicates", RunSpec.replicates)),
                   particles=int(kspec.get("particles", RunSpec.particles)),
                   **({"jitter": float(kspec["jitter"])}
                      if "jitter" in kspec else {}),
                   extra=extra)
    ui_state._status["workroot"] = None
    ui_state._status["expected_total"] = (len(groups) * spec.replicates
                                          if engine in ("all", "pf") else None)
    ui_state._status["settings"] = spec_settings(spec)
    background.add_task(run_worker, spec)
    return RedirectResponse(here + "#results", status_code=303)


def run_worker(spec) -> None:
    """The dataset run: _run_all's claim, ledger, lease and release around
    custom_run.run (hub-only steps are not in it)."""
    from app.core import custom_run
    from app.core.runs import Ledger, lease_workroot, spec_settings
    ledger = Ledger()
    run_id = None
    outcome: dict = {}
    guard = pipeline._sleep_guard()
    if not ui_state._status.get("started_utc"):
        ui_state._status["started_utc"] = time.time()
    ref = (spec.extra or {}).get("dataset") or {}
    ui_state._status["run_label"] = (
        f"{spec.forecast_date} · {ref.get('name', '')}"
        f" · {len(spec.locations)} group(s)")
    ui_state._status["settings"] = spec_settings(spec)
    ui_state._status["dataset_id"] = ref.get("id")
    try:
        ds = _D().from_spec(spec)
        run_id = ledger.open_run(
            spec, Path("pending"),
            versions._engine_versions_for_ledger("pf,analogue"))
        workroot = lease_workroot(run_id)
        ledger.set_workroot(run_id, workroot)
        ui_state._status["running"] = f"dataset:{run_id}"
        ui_state._status["workroot"] = str(workroot)
        state = (pipeline._pf_engine_state() if spec.engine in ("all", "pf")
                 else "absent")
        outcome, fails = custom_run.run(spec, ds, workroot,
                                        phase=shared._phase, pf_state=state)
        ledger.close_run(run_id, "partial" if fails else "ok", outcome)
        if not fails:
            try:
                from app.core import reclaim
                reclaim.prune_workroot(workroot)
            except Exception:
                pass
        ui_state._status["log"].append(
            f"{run_id}: dataset {ref.get('name')} done")
    except Exception as e:
        from app.core.engines.pf import RunStopped
        if run_id is None:
            ui_state._status["log"].append(f"run setup failed: {str(e)[:200]}")
            shared._flash(f"The run on {ref.get('name', 'the dataset')} "
                          f"could not start: {str(e)[:200]}")
        elif isinstance(e, (RunStopped, custom_run.Stopped)):
            ledger.close_run(run_id, "stopped", outcome)
        else:
            ledger.close_run(run_id, "error",
                             {"error": str(e)[:300], **outcome})
            ui_state._status["log"].append(f"{run_id}: ERROR {e}")
    finally:
        if guard is not None:
            try:
                guard.terminate()
            except Exception:
                pass
        shared._invalidate_scans()
        for k in ("running", "workroot", "expected_total", "started_utc",
                  "dataset_id"):
            ui_state._status[k] = None
        ui_state._status["phase"] = ""
        ui_state._status["settings"] = []
        ui_state._status["run_label"] = ""


def run_page_extra(workroot: Path, res: dict) -> dict:
    """run.html's dataset block: exports, fans and member names."""
    from app.core import custom_run
    from app.core.horizons import models_to_canonical
    fd = str(res.get("forecast_date", ""))
    after = {}
    ds = get_dataset((res.get("dataset") or {}).get("id"))
    if ds is not None and fd:
        # what the dataset holds after the as-of, five weeks out (if any)
        import datetime as _dt
        try:
            lim = (_dt.date.fromisoformat(fd)
                   + _dt.timedelta(days=35)).isoformat()
            for n in (res.get("observed") or {}):
                s = ds.series(n)
                after[n] = [[d, v] for d, v in zip(s["dates"], s["values"])
                            if fd < d <= lim]
        except Exception:
            after = {}
    return {"dataset": res.get("dataset"),
            "dataset_members": MEMBER_NAMES,
            "exports": custom_run.export_files(workroot),
            "fans_json": templating._script_json({
                "models": models_to_canonical(res.get("models") or {}),
                "observed": res.get("observed") or {},
                "after": after, "date": fd, "names": MEMBER_NAMES,
                "colors": templating._member_colors()})}


# ----------------------------------------------------------- Storage tab

def spec_dataset(spec) -> str:
    """The id of the dataset a run's spec (a ledger row's JSON) names; ''
    for a hub run or an unreadable spec."""
    try:
        d = json.loads(spec) if isinstance(spec, str) else (spec or {})
        ref = (d.get("extra") or {}).get("dataset") or {}
        return str(ref.get("id") or "") if isinstance(ref, dict) else ""
    except Exception:
        return ""


def storage_rows(workroots: list) -> list:
    """The Storage tab's rows for the stored datasets, newest first: each
    one's size with everything it holds (the upload, its replays, its runs'
    workroots) and the parts ("parts": the upload's data, replays and runs,
    each only when there are replays or runs to set it apart from; "goes":
    what a delete takes with it, '' for the upload alone). `workroots`: the
    panel's workroot rows, each with "bytes" and the "dataset" its spec
    names; a row on a stored dataset gets "dataset_name". "own_bytes" (the
    upload and replays) is what the panel's total adds: the runs are
    counted there as workroots."""
    from app.core import custom_retro as CX
    from app.core import retro
    S = _S()
    try:
        items = _D().list_datasets()
    except Exception:
        return []
    out = []
    for ds in items:
        own = S._tree_size(str(ds.path))
        rep = S._tree_size(str(CX.replay_root(ds)))
        runs = [w for w in workroots if w.get("dataset") == ds.id]
        for w in runs:
            w["dataset_name"] = ds.name
        run_b = sum(int(w.get("bytes") or 0) for w in runs)
        n_rep = len(CX.list_replays(ds))
        n_run = len(runs)
        # no "0 replays 0 B": a part shows only when it holds something
        parts, goes = [], []
        if n_rep or n_run:
            parts.append(f"data {retro.human_bytes(own - rep)}")
        if n_rep:
            parts.append(f"{n_rep} replay{'' if n_rep == 1 else 's'} "
                         f"{retro.human_bytes(rep)}")
            goes.append(f"its {n_rep} replay{'' if n_rep == 1 else 's'}")
        if n_run:
            parts.append(f"{n_run} run{'' if n_run == 1 else 's'} "
                         f"{retro.human_bytes(run_b)}")
            goes.append(f"its {n_run} run workroot"
                        f"{'' if n_run == 1 else 's'}")
        out.append({"id": ds.id, "name": ds.name, "own_bytes": own,
                    "bytes": own + run_b,
                    "size_h": retro.human_bytes(own + run_b),
                    "data_h": retro.human_bytes(own - rep),
                    "replays": n_rep, "replays_h": retro.human_bytes(rep),
                    "runs": n_run, "runs_h": retro.human_bytes(run_b),
                    "parts": parts,
                    "goes": ("With it go " + " and ".join(goes)
                             + ("; the runs' ledger rows are kept."
                                if n_run else ".")) if goes else "",
                    "busy": busy_with(ds.id)})
    return out


def delete_everything(ds) -> tuple:
    """Delete a dataset with everything its Storage size counts: the upload,
    its replays and its runs' workroots (their ledger rows are kept, as a
    workroot delete keeps them). Both delete routes use this, so the Data
    and Storage tabs free the same bytes. Returns (freed, gone, kept)."""
    S = _S()
    from app.core import retro
    freed, gone, kept = 0, 0, 0
    for w in S._storage_inventory()["workroots"]:
        if w.get("dataset") != ds.id:
            continue
        # the workroot delete's own checks: never a live or protected tree
        p, _why = S._storage_target("workroot", w["id"])
        if p is None:
            kept += 1
            continue
        try:
            size = retro.dir_size(p)
            retro.delete_tree(p)
            freed, gone = freed + size, gone + 1
        except Exception:
            kept += 1
    freed += retro.dir_size(ds.path)
    _D().delete(ds.id)
    _LAST.pop(ds.id, None)
    shared._invalidate_scans()
    return freed, gone, kept


def deleted_message(ds, freed: int, gone: int, kept: int) -> str:
    from app.core import retro
    return (f"Deleted the dataset {ds.name}, its replays and {gone} run "
            f"workroot{'' if gone == 1 else 's'}: "
            f"{retro.human_bytes(freed)} freed. The runs' ledger rows are "
            "kept."
            + (f" {kept} run workroot{'' if kept == 1 else 's'} could not "
               "be deleted and stay under Run workroots." if kept else ""))


@router.post("/storage/datasets/{ds_id}/delete")
def storage_delete(request: Request, ds_id: str, confirm: str = Form("")):
    """Delete a dataset from the Storage tab with everything its size there
    counts: the upload, its replays and its runs' workroots (their ledger
    rows are kept, as a workroot delete keeps them). The name confirms it;
    refused while a run or replay uses it."""
    back = shared._back(request, "/storage")
    shared._invalidate_scans()
    ds = get_dataset(ds_id)
    if ds is None:
        shared._flash("No such dataset; nothing was deleted.")
        return back
    why = busy_with(ds.id)
    if why:
        shared._flash(f"{ds.name} was not deleted: {why}.")
        return back
    if confirm != ds.name:
        shared._flash(f"Deleting {ds.name} was not confirmed; nothing was "
                      "deleted.")
        return back
    shared._flash(deleted_message(ds, *delete_everything(ds)))
    return back


# -------------------------------------------------------- Retrospective

#: a replay's default weeks: the flu-season months (October to June)
REPLAY_MONTHS = (10, 11, 12, 1, 2, 3, 4, 5, 6)


def replay_window(dates: list) -> tuple:
    """(first, last) a replay offers by default: the flu-season weeks
    (October to June) of the newest season (August to July) holding 8 or
    more of them, so a summer tail is never the default; the whole range
    when the data span one season or no season holds 8 such weeks."""
    if not dates:
        return "", ""

    def season(d):
        y, m = int(d[:4]), int(d[5:7])
        return y if m >= 8 else y - 1
    if len({season(d) for d in dates}) < 2:
        return dates[0], dates[-1]
    by = {}
    for d in dates:
        if int(d[5:7]) in REPLAY_MONTHS:
            by.setdefault(season(d), []).append(d)
    for k in sorted(by, reverse=True):
        if len(by[k]) >= 8:
            return by[k][0], by[k][-1]
    return dates[0], dates[-1]


def retro_context(selected: str = "") -> dict:
    """The Retrospective tab's own-data card: datasets and their replays
    (kept in their own card, never beside the hub seasons); ``selected``
    names the dataset the card opens on (an upload's "Replay this"), whose
    store confirmation and notices the card shows once ("stored")."""
    from app.core import custom_retro as CX
    out = []
    try:
        items = _D().list_datasets()
    except Exception:
        items = []
    for ds in items:
        reps = []
        for stamp, meta in CX.list_replays(ds)[:6]:
            st = meta.get("status") or "unknown"
            if st == "running" and _REPLAY.get("stamp") != stamp:
                st = "interrupted"
            summ = meta.get("summary") or {}
            rels = {m: (s.get("pooled") or {}).get("relwis")
                    for m, s in summ.items()}
            reps.append({"stamp": stamp, "status": st,
                         "kind": meta.get("replay_kind", ""),
                         "modified": bool(meta.get("knobs")),
                         "first": meta.get("first"), "last": meta.get("last"),
                         "done": meta.get("weeks_completed", 0),
                         "total": meta.get("total_weeks", 0),
                         "rels": {m: v for m, v in rels.items()
                                  if v is not None}})
        dates = ds.forecast_dates()
        w0, w1 = replay_window(dates)
        out.append({"id": ds.id, "name": ds.name, "groups": ds.groups,
                    "vintage_true": ds.vintage_true, "pf": ds.pf_eligible,
                    "kind": ds.kind,
                    "first": dates[0] if dates else "",
                    "last": dates[-1] if dates else "",
                    "default_first": w0, "default_last": w1,
                    "dates": dates, "replays": reps})
    # the Model settings panel of the card's form: a second panel on the
    # page (ids prefixed), following the card's own model select; the
    # counts-only rows hide for a rate dataset (the card sets its kind)
    sel = selected if any(d["id"] == selected for d in out) else ""
    stored = _STORED.pop(sel, None) if sel else None
    if stored:
        stored = {"text": stored["text"],
                  "warnings": [_whole_dates(w) for w in stored["warnings"]]}
    panel = (dataset_panel(forms._knob_panel("forecast",
                                             names=PANEL_MEMBERS),
                           where="replay", prefix="dsr-",
                           engine="dsr-engine") if out else None)
    return {"dataset_replay": {"datasets": out,
                               "pf_state": pipeline._pf_engine_state(),
                               "running": dict(_REPLAY),
                               "names": MEMBER_NAMES,
                               "engine_names": REPLAY_ENGINE_NAMES,
                               "knob_panel": panel,
                               "selected": sel,
                               "stored": stored}}


@router.post("/retro/dataset/run")
def replay_start(background: BackgroundTasks, dataset: str = Form(...),
                 first: str = Form(""), last: str = Form(""),
                 groups: list = Form([]), engine: str = Form("analogue"),
                 weeks_to_drop: str = Form(""), flusurv: str = Form(""),
                 particles: str = Form(""), replicates: str = Form(""),
                 season_start: str = Form(""), drop_same_day: str = Form(""),
                 knob_fields: dict = Depends(_knob_fields),
                 knobs: str = Form("")):
    """Replay a week range of a dataset (the Retrospective tab's card),
    with the Model settings panel's values (dataset_panel): resolved as a
    dataset run resolves them, recorded with the replay when any is off
    the shipped value, and none that does not apply."""
    from app.core import custom_retro as CX
    back = RedirectResponse("/retro#dataset-replay", status_code=303)
    ds = get_dataset(dataset)
    if ds is None:
        shared._flash("That dataset no longer exists. Nothing was started.")
        return back
    if engine not in CX.ENGINES:
        shared._flash(f"Choose {GROUNDHOG} only, or {GROUNDHOG} and the plain "
                      "SIHRS particle filter. Nothing was started.")
        return back
    if engine == "all" and not (ds.pf_eligible
                                and pipeline._pf_engine_state() == "ready"):
        shared._flash(f"The plain SIHRS particle filter cannot replay "
                      f"{ds.name}: {_dataset_view(ds)['pf_why']}. Nothing "
                      "was started.")
        return back
    weeks = CX.weeks_between(ds, forms._str_field(first).strip(),
                             forms._str_field(last).strip())
    if not weeks:
        shared._flash(f"No weeks of {ds.name} fall in that range. Nothing was "
                      "started.")
        return back
    pick = [g for g in groups if g in ds.groups]
    if not pick or "all" in groups:
        pick = list(ds.groups)
    # the panel's values: the older field names ride as legacy fields; a
    # fixed season start must precede every replayed week (check_dates)
    legacy = {f: forms._str_field(v).strip() for f, v in (
        ("particles", particles), ("replicates", replicates),
        ("season_start", season_start), ("weeks_to_drop", weeks_to_drop),
        ("drop_same_day", drop_same_day)) if forms._str_field(v).strip()}
    try:
        nd = forms._knobs.resolve(
            knob_values(ds, knob_fields, knobs), engine, scope="forecast",
            forecast_date=weeks[0], oracle_step=False, legacy=legacy,
            check_dates=tuple(weeks[-1:]))
        extra = {}
        if forms._str_field(flusurv).lower() in ("1", "on", "true", "yes"):
            from app.core.engines import analogue as _an
            fn = _an.aux_preset("flusurv")
            extra = {"aux_pools": fn(None, 0, None)["aux_pools"],
                     "analogue_aux": fn.__name__.split(":", 1)[1]}
        forms._knobs.write_extra(nd, extra)
    except ValueError as e:                  # KnobError is a ValueError
        shared._flash(f"Model settings: {e}. Nothing was started.")
        return back
    kspec = forms._knobs.spec_fields(nd)
    k = int(kspec.pop("weeks_to_drop", 0))
    with ui_state._engine_lock:
        if ui_state._status.get("running") or _REPLAY:
            shared._flash("A run or replay holds the engine; wait for it "
                          "or stop it first. Nothing was started.")
            return back
        live = sorted(x for x in retro_seasons._known_seasons()
                      if retro_seasons._season_status(x)
                      in retro_seasons._RETRO_ACTIVE)
        if live:
            shared._flash("A season replay holds the engine ("
                          + ", ".join(live) + "); stop or pause it first. "
                          "Nothing was started.")
            return back
        stamp = CX.new_stamp(ds)
        _REPLAY.update({"id": ds.id, "stamp": stamp})
        ui_state._status["running"] = f"dataset-replay:{stamp}"
        ui_state._status["dataset_id"] = ds.id
        ui_state._status["started_utc"] = time.time()
        ui_state._status["run_label"] = (f"replay of {ds.name}: {weeks[0]} to "
                                         f"{weeks[-1]} · queued")
        ui_state._status["settings"] = []
        ui_state._status["workroot"] = None
        ui_state._status["expected_total"] = None
    # knob keywords only when set: a shipped replay's call is as before
    background.add_task(replay_worker, ds.id, stamp, weeks, pick, engine, k,
                        extra, **kspec)
    return RedirectResponse(f"/retro/dataset/{ds.id}/{stamp}",
                            status_code=303)


def replay_worker(ds_id, stamp, weeks, groups, engine, k, extra,
                  **kspec) -> None:
    """One dataset replay (custom_retro.run) holding the engine claim;
    `kspec`: the knobs' RunSpec fields (particles, replicates, jitter,
    season_start, drop_same_day), only those set."""
    from app.core import custom_retro as CX
    guard = pipeline._sleep_guard()
    try:
        ds = _D().get(ds_id)
        out = CX.replay_dir(ds, stamp)
        state = pipeline._pf_engine_state() if engine == "all" else "absent"

        def progress(asof, i, n):
            ui_state._status["phase"] = f"replayed {asof} ({i} of {n} weeks)"
            ui_state._status["run_label"] = (
                f"replay of {ds.name}: week {i} of {n}")

        def on_wr(wr):
            ui_state._status["workroot"] = str(wr)
        stop = out / "STOP"
        CX.run(ds, weeks, groups, engine=engine, weeks_to_drop=k,
               extra=extra, out_dir=out, pf_state=state, progress=progress,
               stop_file=stop, on_workroot=on_wr, **kspec)
    except Exception as e:
        ui_state._status["log"].append(f"dataset replay {stamp}: ERROR {e}")
    finally:
        if guard is not None:
            try:
                guard.terminate()
            except Exception:
                pass
        _REPLAY.clear()
        shared._invalidate_scans()
        for key in ("running", "workroot", "expected_total", "started_utc",
                    "dataset_id"):
            ui_state._status[key] = None
        ui_state._status["phase"] = ""
        ui_state._status["run_label"] = ""


@router.post("/retro/dataset/{ds_id}/{stamp}/stop")
def replay_stop(ds_id: str, stamp: str):
    from app.core import custom_retro as CX
    ds = get_dataset(ds_id)
    if ds is not None and CX.valid_stamp(stamp) and \
            _REPLAY.get("stamp") == stamp:
        (CX.replay_dir(ds, stamp) / "STOP").touch()
        w = ui_state._status.get("workroot")
        if w:
            (Path(w) / "STOP").touch()
    return RedirectResponse(f"/retro/dataset/{ds_id}/{stamp}",
                            status_code=303)


@router.get("/retro/dataset/{ds_id}/{stamp}", response_class=HTMLResponse)
def replay_page(request: Request, ds_id: str, stamp: str, h: str = "0"):
    """One dataset replay: pooled relWIS vs the persistence baseline (named),
    the national group beside it, WIS by horizon and group, coverage, and a
    fan-over-time per group at one horizon."""
    refused = local_only(request)
    if refused:
        return refused
    from app.core import custom_retro as CX
    from app.core import horizons as hz
    ds = get_dataset(ds_id)
    if ds is None or not CX.valid_stamp(stamp) \
            or not CX.replay_dir(ds, stamp).is_dir():
        return HTMLResponse("<p>No such replay.</p>", status_code=404)
    meta, fc, cells, cov = CX.load(CX.replay_dir(ds, stamp))
    status = meta.get("status") or "unknown"
    live = _REPLAY.get("stamp") == stamp
    if status == "running" and not live:
        status = "interrupted"
    h = h if h in hz.HORIZONS else "0"
    # per group: the final series, and each week's forecast at horizon h
    fans = {}
    for g in (meta.get("groups") or []):
        s = ds.series(g)
        per = {}
        for m in ("analogue", "pf"):
            pts = []
            for asof, mm in sorted(fc.items()):
                q = ((mm.get(m) or {}).get(g) or {}).get(h)
                if not q:
                    continue
                lv = {float(L): v for L, v in q.items()}
                import pandas as _pd
                end = (_pd.Timestamp(asof)
                       + _pd.Timedelta(days=7 * (int(h) + 1))).date()
                pts.append([end.isoformat(), lv.get(0.5), lv.get(0.25),
                            lv.get(0.75), lv.get(0.025), lv.get(0.975)])
            if pts:
                per[m] = pts
        fans[g] = {"series": s, "fc": per}
    summ = meta.get("summary") or {}
    abst = meta.get("abstained") or {}
    pf = meta.get("pf") or ("not run: " + meta["pf_skipped"]
                            if meta.get("pf_skipped") else "not run")
    settings = [
        ("data", f"{ds.name} ({meta.get('replay_kind', '')})"),
        ("weeks", f"{meta.get('total_weeks', 0)} ({meta.get('first')} to "
                  f"{meta.get('last')})"),
        ("groups", ", ".join(meta.get("groups") or [])),
        # the donors (a replay recorded before the own-data label
        # carries only the full label)
        (GROUNDHOG, meta.get("analogue_donors") or meta.get("analogue")
         or ""),
        ("particle filter", pf),
        ("weeks dropped", str(meta.get("weeks_to_drop", 0))),
        ("baseline", meta.get("baseline") or "")]
    if meta.get("knobs"):
        # recorded only off the shipped values, as a hub replay's is
        try:
            K = forms._knobs
            settings.append(("model settings",
                             K.label(K.from_record(meta["knobs"]))))
        except Exception:
            settings.append(("model settings",
                             "modified (unreadable record)"))
    return templating.templates.TemplateResponse(request, "retro_dataset.html", {
        "active": "Retrospective", "ds": ds, "stamp": stamp, "meta": meta,
        "status": status, "live": live, "h": h,
        "horizons": list(hz.HORIZONS), "summary": summ,
        "abstained": {m: sum(len(v) for v in d.values())
                      for m, d in abst.items()},
        "member_names": MEMBER_NAMES, "settings": settings,
        "fans_json": templating._script_json(fans),
        "names_json": templating._script_json(MEMBER_NAMES),
        "member_colors_json": templating._script_json(
            templating._member_colors())})
