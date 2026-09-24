"""Custom datasets in the console: upload, browse, forecast and replay.

Routes (an APIRouter included by app/ui/server.py; the same-host guard
covers every POST, and each GET that returns dataset content checks the
Host header too, since an upload may be private data):

  POST /data/datasets                  multipart upload (size capped before
                                       and while parsing)
  POST /data/datasets/{id}/delete      delete, with the name as confirmation
  POST /run/dataset                    a forecast on a dataset
  POST /retro/dataset/run              replay a week range on a dataset
  GET  /retro/dataset/{id}/{stamp}     one replay's results

and the context builders server.py calls when a page is opened with
`?source=<dataset id>` (Data, Forecast, /api/series). A dataset is never the
default source: every page and run opts in by naming it.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import (HTMLResponse, PlainTextResponse,
                               RedirectResponse)

router = APIRouter()

#: what the forecast form last held, per dataset (never the hub's _last_form)
_LAST: dict = {}
#: the replay a worker is running now: {"id", "stamp"} or {}
_REPLAY: dict = {}

#: the dataset members as the Forecast form names them
ENGINE_NAMES = {"all": "Both (plain SIHRS particle filter + Groundhog)",
                "pf": "plain SIHRS particle filter only",
                "analogue": "Groundhog only"}
#: fan and table names on dataset pages
MEMBER_NAMES = {"pf": "plain SIHRS PF", "analogue": "Groundhog"}
#: the upload body may exceed the file by the multipart framing and fields
FORM_SLACK = 64 * 1024


def _S():
    from app.ui import server
    return server


def _D():
    from app.core import datasets
    return datasets


def local_only(request: Request):
    """403 unless the Host names this machine (a DNS-rebinding page cannot
    read uploaded data through a GET); None when fine."""
    S = _S()
    if (S._authority_hostname(request.headers.get("host", ""))
            not in S._LOCAL_HOSTNAMES):
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
    S = _S()
    if S._status.get("running") and S._status.get("dataset_id") == ds_id:
        return "a run on it is in progress"
    if _REPLAY.get("id") == ds_id:
        return "a replay on it is in progress"
    return ""


# ------------------------------------------------------------- Data tab

def data_context(ds, loc: str = "", vintage: str = "") -> dict:
    """The Data tab's browser for one dataset: the vintage-browser keys
    (data.html's chart and table) filled from the dataset, truncated at the
    chosen vintage so final data never shows later weeks."""
    S = _S()
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
        "series_json": (S._script_json({"dates": dates, "values": values})
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
    """data.html with the upload's report inline (not the one-slot flash)."""
    S = _S()
    ctx = S._data_context()
    ctx.update(extra)
    return S.templates.TemplateResponse(request, "data.html", ctx,
                                        status_code=_code)


@router.post("/data/datasets")
async def upload(request: Request):
    """Validate and store one CSV. Problems are shown inline on the Data
    tab (every one at once) and nothing is stored."""
    S, D = _S(), _D()
    cap = D.DEFAULT_LIMITS.max_bytes + FORM_SLACK
    ctype = request.headers.get("content-type", "")
    if not ctype.startswith("multipart/form-data"):
        return PlainTextResponse("Expected a multipart/form-data upload.\n",
                                 status_code=400)
    form = await _capped_form(request, cap)
    mb = D.DEFAULT_LIMITS.max_bytes // (1024 * 1024)
    if form is None:
        return _render_data(request, upload={
            "name": "", "problems": [f"The upload is larger than the {mb} MB "
                                     "limit; nothing was read or stored."],
            "warnings": []}, _code=413)
    f = form.get("file")
    name = str(form.get("name") or "").strip()
    kind = str(form.get("kind") or "")
    sunday = str(form.get("sunday") or "") in ("1", "on", "true")
    target = str(form.get("target") or "").strip() or None
    back = {"name": name, "kind": kind, "sunday": sunday, "target": target or ""}
    if f is None or not hasattr(f, "file") or not getattr(f, "filename", ""):
        return _render_data(request, upload={
            **back, "problems": ["Choose a CSV file to upload."],
            "warnings": []}, _code=400)
    fname = Path(str(f.filename)).name
    if not name:
        name = Path(fname).stem or "dataset"
    if kind not in D.KINDS:
        return _render_data(request, upload={
            **back, "problems": ["Say whether the values are counts or "
                                 "rates."], "warnings": []}, _code=400)
    try:
        f.file.seek(0)
        ds = D.ingest(f.file, name[:80], kind=kind, week_start_sunday=sunday,
                      target=target, filename=fname)
    except D.DatasetError as e:
        f.file.seek(0)
        targets = []
        if any(p.code == "target_required" for p in e.problems):
            targets = _targets_in(f.file)
        return _render_data(request, upload={
            **back, "problems": [str(p) for p in e.problems] or [str(e)],
            "warnings": [], "targets": targets}, _code=422)
    finally:
        try:
            await f.close()
        except Exception:
            pass
    S._invalidate_scans()
    warn = ds.meta.get("warnings") or []
    S._flash(f"Stored the dataset {ds.name}: {len(ds.groups)} group(s), "
             f"{len(ds.weeks())} week(s)."
             + (" " + " ".join(warn) if warn else ""))
    return RedirectResponse(f"/data?source={ds.id}#datasets", status_code=303)


def _targets_in(fh) -> list:
    """The target names a multi-target file holds (for the form's picker)."""
    import csv
    import io
    try:
        text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
        r = csv.reader(text)
        head = [h.strip().lower() for h in next(r)]
        i = head.index("target")
        seen = []
        for n, row in enumerate(r):
            if n > 2_000_000:
                break
            if len(row) > i and row[i].strip() and row[i].strip() not in seen:
                seen.append(row[i].strip())
                if len(seen) > 20:
                    break
        text.detach()
        return seen
    except Exception:
        return []


@router.post("/data/datasets/{ds_id}/delete")
def delete(request: Request, ds_id: str, confirm: str = Form("")):
    S, D = _S(), _D()
    ds = get_dataset(ds_id)
    if ds is None:
        S._flash("No such dataset; nothing was deleted.")
        return RedirectResponse("/data#datasets", status_code=303)
    why = busy_with(ds.id)
    if why:
        S._flash(f"{ds.name} was not deleted: {why}.")
        return RedirectResponse("/data#datasets", status_code=303)
    if confirm != ds.name:
        S._flash(f"Deleting {ds.name} was not confirmed; nothing was deleted.")
        return RedirectResponse("/data#datasets", status_code=303)
    D.delete(ds.id)
    _LAST.pop(ds.id, None)
    S._invalidate_scans()
    S._flash(f"Deleted the dataset {ds.name}, with its replays. Runs made "
             "from it keep their results but cannot be re-run.")
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
    S = _S()
    state = S._pf_engine_state()
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
    for f in _S()._workroot_results():
        try:
            res = json.loads(f.read_text())
        except Exception:
            continue
        if (res.get("dataset") or {}).get("id") == ds_id:
            return f.parent.name, res
    return None, None


def panel_for_dataset(panel):
    """The Model settings panel as a dataset run reads it: no Oracle step
    (it does not run on custom data), no auxiliary-bank rows (the form's
    FluSurv-NET box decides), no hub-name override (there is none)."""
    if not panel:
        return panel
    p = dict(panel)
    groups = []
    for g in p["groups"]:
        if g["id"] == "step":
            continue
        rows = [r for r in g["rows"]
                if r["key"] not in ("groundhog.aux", "groundhog.aux_weight")]
        if rows:
            groups.append({**g, "rows": rows})
    p["groups"] = groups
    p["override"] = False
    return p


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
        r["label"] = S._run_label(r["run_id"], r.get("spec", ""))
        r["modified"] = S._runs.is_modified(r.get("spec", ""))
        r["chips"] = outcome_chips(r.get("outcome", ""))
        r["settings"] = spec_settings(r.get("spec", ""))
        r["has_report"] = False
        if r["status"] == "running" and not (
                S._status.get("running") or "").endswith(r["run_id"]):
            r["status"] = "interrupted"
    anchor, _ = S.resolve_anchor(form.get("forecast_date", ""), dates)
    ok = anchor in dates
    note = (f"Anchor week: {anchor}." if ok
            else "No week of this dataset on or before that date.")
    return S.templates.TemplateResponse(request, "forecast.html", {
        "active": "Forecast", "engines": S.ENGINES, "status": S._status,
        "ledger": rows, "all_locs": ds.groups,
        "vintage_dates": list(reversed(dates)), "anchor_note": note,
        "default_date": newest, "locations_error": "", "form": form,
        "knob_panel": panel_for_dataset(S._knob_panel("forecast", form)),
        "elapsed0": S._console_elapsed(),
        "series_json": S._script_json(series),
        "fanq_json": S._script_json(fanq),
        "model_names_json": S._script_json(
            {**S._model_names(), **MEMBER_NAMES}),
        "member_colors_json": S._script_json(S._member_colors()),
        "season_colors_json": S._script_json(S._season_colors()),
        "run_obs_json": S._script_json((res or {}).get("observed", {})),
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
    """The Model settings panel's knob.<key> fields (server._knob_form)."""
    return await _S()._knob_form(request)


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
    S = _S()
    from app.core.runs import RunSpec, spec_settings
    ds = get_dataset(ds_id)
    if ds is None:
        S._flash("That dataset no longer exists. Nothing was run.")
        return RedirectResponse("/forecast", status_code=303)
    here = f"/forecast?source={ds.id}"
    dates = ds.forecast_dates()
    fd = S._str_field(forecast_date).strip()
    pick, _ = S.resolve_anchor(fd, dates)
    fd = pick or fd
    if fd not in dates:
        earlier = [d for d in dates if d <= fd]
        near = earlier[-1] if earlier else (dates[0] if dates else "")
        S._flash(f"{ds.name} holds no week {fd} to forecast from."
                 + (f" Nearest earlier week: {near}." if earlier else
                    f" Its first forecastable week is {near}." if near else ""))
        return RedirectResponse(here, status_code=303)
    if engine not in ENGINE_NAMES:
        S._flash(f"'{engine}' is not a model choice. Nothing was run.")
        return RedirectResponse(here, status_code=303)
    view = _dataset_view(ds)
    if engine in ("all", "pf") and not view["pf_ok"]:
        S._flash(f"The plain SIHRS particle filter cannot run on {ds.name}: "
                 f"{view['pf_why']}. Choose the Groundhog. Nothing was run.")
        return RedirectResponse(here, status_code=303)
    groups = [x.strip() for l in locations for x in str(l).split("|")
              if x.strip()]
    if any(g.lower() == "all" for g in groups):
        groups = list(ds.groups)
    unknown = [g for g in groups if g not in ds.groups]
    groups = [g for g in ds.groups if g in groups]      # dataset order
    if unknown:
        S._flash(f"Not groups of {ds.name}: {', '.join(unknown[:5])}. "
                 "Nothing was run.")
        return RedirectResponse(here, status_code=303)
    if not groups:
        S._flash("Select at least one group. Nothing was run.")
        return RedirectResponse(here, status_code=303)
    want_fs = S._str_field(flusurv).lower() in ("1", "on", "true", "yes")
    season_start = S._str_field(season_start).strip()
    kraw = {k: v for k, v in S._knob_raw(knob_fields or {},
                                         knobs_json).items()
            if k not in ("groundhog.aux", "groundhog.aux_weight")}
    _LAST[ds.id] = {"forecast_date": fd, "locations": groups
                    if len(groups) < len(ds.groups) else ["all"],
                    "engine": engine, "weeks_to_drop": weeks_to_drop,
                    "replicates": replicates, "particles": particles,
                    "season_start": season_start,
                    "drop_same_day": S._int_field(drop_same_day),
                    "flusurv": want_fs,
                    "knobs": {k: v for k, v in kraw.items()
                              if isinstance(v, str)}}
    try:
        nd = S._knobs.resolve(
            kraw, engine, scope="forecast", forecast_date=fd,
            oracle_step=False,
            legacy={"particles": particles, "replicates": replicates,
                    "season_start": season_start,
                    "weeks_to_drop": weeks_to_drop,
                    "drop_same_day": bool(S._int_field(drop_same_day))})
        mode = "realtime" if fd == dates[-1] else "vintage"
        extra = {"mode": mode, "oracle": "none", "dataset": ds.ref(),
                 "dataset_final": not ds.vintage_true}
        if want_fs:
            from app.core.engines import analogue as _an
            fn = _an.aux_preset("flusurv")
            extra["aux_pools"] = fn(None, 0, None)["aux_pools"]
            extra["analogue_aux"] = fn.__name__.split(":", 1)[1]
        S._knobs.write_extra(nd, extra)
    except ValueError as e:
        S._flash(f"Model settings: {e}. Nothing was run.")
        return RedirectResponse(here, status_code=303)
    kspec = S._knobs.spec_fields(nd)
    with S._engine_lock:
        if S._status.get("running"):
            S._flash("A run is already in progress; not starting another.")
            return RedirectResponse(here + "#results", status_code=303)
        live = sorted(x for x in S._known_seasons()
                      if S._season_status(x) in S._RETRO_ACTIVE)
        if live:
            S._flash("A retrospective replay holds the engine ("
                     + ", ".join(live) + "). Stop or pause it from the "
                     "Retrospective tab first; nothing was run.")
            return RedirectResponse(here, status_code=303)
        S._status["running"] = "starting"
        S._status["dataset_id"] = ds.id
        S._invalidate_scans()
        S._status["started_utc"] = time.time()
        S._status["run_label"] = f"{fd} · {ds.name} · queued"
    spec = RunSpec(engine=engine, forecast_date=fd, locations=groups,
                   season_start=kspec.get("season_start", ""),
                   weeks_to_drop=int(kspec.get("weeks_to_drop", 0)),
                   drop_same_day=bool(kspec.get("drop_same_day", False)),
                   replicates=int(kspec.get("replicates", RunSpec.replicates)),
                   particles=int(kspec.get("particles", RunSpec.particles)),
                   **({"jitter": float(kspec["jitter"])}
                      if "jitter" in kspec else {}),
                   extra=extra)
    S._status["workroot"] = None
    S._status["expected_total"] = (len(groups) * spec.replicates
                                   if engine in ("all", "pf") else None)
    S._status["settings"] = spec_settings(spec)
    background.add_task(run_worker, spec)
    return RedirectResponse(here + "#results", status_code=303)


def run_worker(spec) -> None:
    """The dataset run: _run_all's claim, ledger, lease and release around
    custom_run.run (hub-only steps are not in it)."""
    S = _S()
    from app.core import custom_run
    from app.core.runs import Ledger, lease_workroot, spec_settings
    ledger = Ledger()
    run_id = None
    outcome: dict = {}
    guard = S._sleep_guard()
    if not S._status.get("started_utc"):
        S._status["started_utc"] = time.time()
    ref = (spec.extra or {}).get("dataset") or {}
    S._status["run_label"] = (f"{spec.forecast_date} · {ref.get('name', '')}"
                              f" · {len(spec.locations)} group(s)")
    S._status["settings"] = spec_settings(spec)
    S._status["dataset_id"] = ref.get("id")
    try:
        ds = _D().from_spec(spec)
        run_id = ledger.open_run(spec, Path("pending"),
                                 S._engine_versions_for_ledger("pf,analogue"))
        workroot = lease_workroot(run_id)
        ledger.set_workroot(run_id, workroot)
        S._status["running"] = f"dataset:{run_id}"
        S._status["workroot"] = str(workroot)
        state = (S._pf_engine_state() if spec.engine in ("all", "pf")
                 else "absent")
        outcome, fails = custom_run.run(spec, ds, workroot, phase=S._phase,
                                        pf_state=state)
        ledger.close_run(run_id, "partial" if fails else "ok", outcome)
        if not fails:
            try:
                from app.core import reclaim
                reclaim.prune_workroot(workroot)
            except Exception:
                pass
        S._status["log"].append(f"{run_id}: dataset {ref.get('name')} done")
    except Exception as e:
        from app.core.engines.pf import RunStopped
        if run_id is None:
            S._status["log"].append(f"run setup failed: {str(e)[:200]}")
            S._flash(f"The run on {ref.get('name', 'the dataset')} could not "
                     f"start: {str(e)[:200]}")
        elif isinstance(e, (RunStopped, custom_run.Stopped)):
            ledger.close_run(run_id, "stopped", outcome)
        else:
            ledger.close_run(run_id, "error",
                             {"error": str(e)[:300], **outcome})
            S._status["log"].append(f"{run_id}: ERROR {e}")
    finally:
        if guard is not None:
            try:
                guard.terminate()
            except Exception:
                pass
        S._invalidate_scans()
        for k in ("running", "workroot", "expected_total", "started_utc",
                  "dataset_id"):
            S._status[k] = None
        S._status["phase"] = ""
        S._status["settings"] = []
        S._status["run_label"] = ""


def run_page_extra(workroot: Path, res: dict) -> dict:
    """run.html's dataset block: exports, fans and member names."""
    from app.core import custom_run
    from app.core.horizons import models_to_canonical
    S = _S()
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
            "fans_json": S._script_json({
                "models": models_to_canonical(res.get("models") or {}),
                "observed": res.get("observed") or {},
                "after": after, "date": fd, "names": MEMBER_NAMES,
                "colors": S._member_colors()})}


# -------------------------------------------------------- Retrospective

def retro_context() -> dict:
    """The Retrospective tab's own-data card: datasets and their replays
    (kept in their own card, never beside the hub seasons)."""
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
                         "first": meta.get("first"), "last": meta.get("last"),
                         "done": meta.get("weeks_completed", 0),
                         "total": meta.get("total_weeks", 0),
                         "rels": {m: v for m, v in rels.items()
                                  if v is not None}})
        dates = ds.forecast_dates()
        out.append({"id": ds.id, "name": ds.name, "groups": ds.groups,
                    "vintage_true": ds.vintage_true, "pf": ds.pf_eligible,
                    "first": dates[0] if dates else "",
                    "last": dates[-1] if dates else "",
                    "dates": dates, "replays": reps})
    return {"dataset_replay": {"datasets": out,
                               "pf_state": _S()._pf_engine_state(),
                               "running": dict(_REPLAY)}}


@router.post("/retro/dataset/run")
def replay_start(background: BackgroundTasks, dataset: str = Form(...),
                 first: str = Form(""), last: str = Form(""),
                 groups: list = Form([]), engine: str = Form("analogue"),
                 weeks_to_drop: int = Form(0), flusurv: str = Form("")):
    """Replay a week range of a dataset (the Retrospective tab's card)."""
    S = _S()
    from app.core import custom_retro as CX
    ds = get_dataset(dataset)
    if ds is None:
        S._flash("That dataset no longer exists. Nothing was started.")
        return RedirectResponse("/retro#dataset-replay", status_code=303)
    if engine not in CX.ENGINES:
        S._flash("Choose the Groundhog, or the Groundhog with the plain SIHRS "
                 "particle filter (plain). Nothing was started.")
        return RedirectResponse("/retro#dataset-replay", status_code=303)
    if engine == "all" and not (ds.pf_eligible
                                and S._pf_engine_state() == "ready"):
        S._flash(f"The plain SIHRS particle filter cannot replay {ds.name}: "
                 f"{_dataset_view(ds)['pf_why']}. Nothing was started.")
        return RedirectResponse("/retro#dataset-replay", status_code=303)
    weeks = CX.weeks_between(ds, S._str_field(first).strip(),
                             S._str_field(last).strip())
    if not weeks:
        S._flash(f"No weeks of {ds.name} fall in that range. Nothing was "
                 "started.")
        return RedirectResponse("/retro#dataset-replay", status_code=303)
    pick = [g for g in groups if g in ds.groups]
    if not pick or "all" in groups:
        pick = list(ds.groups)
    k = S._int_field(weeks_to_drop)
    if not 0 <= k <= 4:
        S._flash("Weeks to drop must be 0 to 4. Nothing was started.")
        return RedirectResponse("/retro#dataset-replay", status_code=303)
    extra = {}
    if S._str_field(flusurv).lower() in ("1", "on", "true", "yes"):
        from app.core.engines import analogue as _an
        fn = _an.aux_preset("flusurv")
        extra = {"aux_pools": fn(None, 0, None)["aux_pools"],
                 "analogue_aux": fn.__name__.split(":", 1)[1]}
    with S._engine_lock:
        if S._status.get("running") or _REPLAY:
            S._flash("A run or replay holds the engine; wait for it or stop "
                     "it first. Nothing was started.")
            return RedirectResponse("/retro#dataset-replay", status_code=303)
        live = sorted(x for x in S._known_seasons()
                      if S._season_status(x) in S._RETRO_ACTIVE)
        if live:
            S._flash("A season replay holds the engine (" + ", ".join(live)
                     + "); stop or pause it first. Nothing was started.")
            return RedirectResponse("/retro#dataset-replay", status_code=303)
        stamp = CX.new_stamp(ds)
        _REPLAY.update({"id": ds.id, "stamp": stamp})
        S._status["running"] = f"dataset-replay:{stamp}"
        S._status["dataset_id"] = ds.id
        S._status["started_utc"] = time.time()
        S._status["run_label"] = (f"replay of {ds.name}: {weeks[0]} to "
                                  f"{weeks[-1]} · queued")
        S._status["settings"] = []
        S._status["workroot"] = None
        S._status["expected_total"] = None
    background.add_task(replay_worker, ds.id, stamp, weeks, pick, engine, k,
                        extra)
    return RedirectResponse(f"/retro/dataset/{ds.id}/{stamp}",
                            status_code=303)


def replay_worker(ds_id, stamp, weeks, groups, engine, k, extra) -> None:
    S = _S()
    from app.core import custom_retro as CX
    guard = S._sleep_guard()
    try:
        ds = _D().get(ds_id)
        out = CX.replay_dir(ds, stamp)
        state = S._pf_engine_state() if engine == "all" else "absent"

        def progress(asof, i, n):
            S._status["phase"] = f"replayed {asof} ({i} of {n} weeks)"
            S._status["run_label"] = (f"replay of {ds.name}: week {i} of {n}")

        def on_wr(wr):
            S._status["workroot"] = str(wr)
        stop = out / "STOP"
        CX.run(ds, weeks, groups, engine=engine, weeks_to_drop=k,
               extra=extra, out_dir=out, pf_state=state, progress=progress,
               stop_file=stop, on_workroot=on_wr)
    except Exception as e:
        S._status["log"].append(f"dataset replay {stamp}: ERROR {e}")
    finally:
        if guard is not None:
            try:
                guard.terminate()
            except Exception:
                pass
        _REPLAY.clear()
        S._invalidate_scans()
        for key in ("running", "workroot", "expected_total", "started_utc",
                    "dataset_id"):
            S._status[key] = None
        S._status["phase"] = ""
        S._status["run_label"] = ""


@router.post("/retro/dataset/{ds_id}/{stamp}/stop")
def replay_stop(ds_id: str, stamp: str):
    from app.core import custom_retro as CX
    ds = get_dataset(ds_id)
    if ds is not None and CX.valid_stamp(stamp) and \
            _REPLAY.get("stamp") == stamp:
        (CX.replay_dir(ds, stamp) / "STOP").touch()
        w = _S()._status.get("workroot")
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
    S = _S()
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
        ("Groundhog", meta.get("analogue") or ""),
        ("particle filter", pf),
        ("weeks dropped", str(meta.get("weeks_to_drop", 0))),
        ("baseline", meta.get("baseline") or "")]
    return S.templates.TemplateResponse(request, "retro_dataset.html", {
        "active": "Retrospective", "ds": ds, "stamp": stamp, "meta": meta,
        "status": status, "live": live, "h": h,
        "horizons": list(hz.HORIZONS), "summary": summ,
        "abstained": {m: sum(len(v) for v in d.values())
                      for m, d in abst.items()},
        "member_names": MEMBER_NAMES, "settings": settings,
        "fans_json": S._script_json(fans),
        "names_json": S._script_json(MEMBER_NAMES),
        "member_colors_json": S._script_json(S._member_colors())})
