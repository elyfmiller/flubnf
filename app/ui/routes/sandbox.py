"""Sandbox (GET /sandbox): user models fitted on the production engine.

Also the sandbox's half of the two-way engine guard (_sandbox_engine_guard,
which server.py registers as the outermost middleware) and the Storage
panel's read-only sandbox line (_sandbox_storage_line, which server.py
registers as the sandbox_storage Jinja global). app/core/sandbox.py does
the work. An APIRouter server.py includes.
"""
from __future__ import annotations

import threading
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import (HTMLResponse, JSONResponse, PlainTextResponse,
                               RedirectResponse)

from app.core import sandbox as sandbox_mod
from app.ui import pipeline, retro_seasons
from app.ui.retro_seasons import _RETRO_ACTIVE, _season_status
from app.ui.shared import (_LOCAL_HOSTNAMES, _authority_hostname, _flash,
                           _sandbox_live, _sandbox_live_reason)
from app.ui.state import _engine_lock, _sandbox_status, _status
from app.ui.templating import _script_json, templates

router = APIRouter()


# === Sandbox (/sandbox): user models on the same engine -> sandbox.html ===
# app/core/sandbox.py; nothing here touches the ledger, Output, retro or seal.
def _sandbox_busy_reason() -> str:
    """Why a sandbox fit may not start now ("" when the engine is free)."""
    if _status.get("running"):
        return "a console run is fitting"
    live = [x for x in retro_seasons._known_seasons()
            if _season_status(x) in _RETRO_ACTIVE]
    if live:
        return "a retrospective replay is running (" + ", ".join(live) + ")"
    return _sandbox_live_reason()


# registered second by server.py (outermost: it wraps the same-host guard)
async def _sandbox_engine_guard(request: Request, call_next):
    """The other half of the two-way engine guard: a console run (/run) or
    a replay (/retro/run) is refused while a sandbox fit holds the engine,
    as those two refuse each other. Requests the same-host guard refuses
    pass through to it untouched."""
    path = request.url.path.rstrip("/")
    if request.method == "POST" and path in ("/run", "/retro/run"):
        origin = request.headers.get("origin")
        local = (_authority_hostname(request.headers.get("host", ""))
                 in _LOCAL_HOSTNAMES
                 and (origin is None
                      or _authority_hostname(origin) in _LOCAL_HOSTNAMES))
        # a plain read: an async middleware must not wait on _engine_lock
        live = _sandbox_live()
        if local and live:
            _flash(f"A sandbox fit holds the engine ({live}). Stop it from "
                   "the Sandbox tab first; nothing was started.")
            return RedirectResponse("/retro" if path == "/retro/run"
                                    else "/forecast", status_code=303)
    return await call_next(request)


def _sandbox_url(model: str = "", run: str = "") -> str:
    """The sandbox page with the model (and run) open."""
    from urllib.parse import quote
    q = []
    if run:
        q.append(f"run={quote(str(run))}")
    if model:
        q.append(f"model={quote(str(model))}")
    return "/sandbox" + ("?" + "&".join(q) if q else "")


def _sandbox_redirect(model: str = "", run: str = "") -> RedirectResponse:
    return RedirectResponse(_sandbox_url(model, run), status_code=303)


def _sandbox_run_dir(run_id: str) -> Path:
    return sandbox_mod.run_dir(run_id)


def _sandbox_save_posted(name: str, model_bngl: str, data_exp: str,
                         priors_conf: str) -> list:
    """Save the editor fields that were posted non-empty (a script or an
    alias posting none blanks nothing); the names of the files saved."""
    files = {f: v for f, v in (("model.bngl", model_bngl),
                               ("data.exp", data_exp),
                               ("priors.conf", priors_conf))
             if (v or "").strip()}
    if files:
        sandbox_mod.save_model(name, files)
    return sorted(files)


@router.get("/sandbox", response_class=HTMLResponse)
def sandbox_page(request: Request, run: str = "", model: str = "",
                 dataset: str = "", compare: str = ""):
    """The gallery (no model) or one model's workbench (?model=): the
    editor, its run settings, its runs and their results (with ?compare=
    a second run overlaid and diffed), its diagram."""
    live = _sandbox_status.get("running")
    models = sandbox_mod.list_models()
    editing = None
    if model:
        try:
            editing = {"name": sandbox_mod.check_name(model),
                       **sandbox_mod.read_model(model)}
        except Exception as e:
            _flash(str(e))
            model = ""
    all_runs = sandbox_mod.list_runs(live=live)
    last = {}
    for r in all_runs:
        last.setdefault(r.get("model"), r)
    runs = [r for r in all_runs if r.get("model") == model][:25] if model else []
    res = None
    try:
        if run:
            res = sandbox_mod.results(_sandbox_run_dir(run), live=live)
            if model and res["meta"].get("model") != model:
                res = None
        elif runs:
            res = sandbox_mod.results(sandbox_mod.RUNS / runs[0]["run_id"],
                                      live=live)
    except Exception as e:
        _flash(f"That sandbox run could not be read: {e}")
        res = None
    # a second run of the same model, overlaid and diffed against the open one
    cmp, diff = None, None
    if res and compare and compare != res["run_id"]:
        try:
            cmp = sandbox_mod.results(_sandbox_run_dir(compare), live=live)
            if cmp["meta"].get("model") != res["meta"].get("model"):
                raise sandbox_mod.SandboxError(
                    f"{compare} is a run of another model")
            diff = sandbox_mod.diff_runs(compare, res["run_id"])
        except Exception as e:
            _flash(f"Not compared: {e}")
            cmp, diff = None, None
    ctx = {"active": "Sandbox", "models": models, "last": last,
           "examples": sandbox_mod.list_examples(), "runs": runs,
           "res": res, "res_json": _script_json(res or {}),
           "cmp": cmp, "cmp_json": _script_json(cmp or {}), "diff": diff,
           "editing": editing, "busy": _sandbox_busy_reason(),
           "running_id": live,
           # the Oracle SIHRS start (the gallery's New model form)
           "vintages": sandbox_mod.vintages(),
           "locations": sandbox_mod.locations(),
           "datasets": sandbox_mod.dataset_choices()}
    if res:
        ctx["oracle"] = sandbox_mod.read_oracle(res["run_id"])
        ctx["oracle_gate"] = sandbox_mod.oracle_gate(res["run_id"])
        ctx["oracle_w_production"] = sandbox_mod.oracle_default_w()
        ctx["oracle_w"] = (ctx["oracle"] or {}).get(
            "w", ctx["oracle_w_production"])
    if editing:
        name = editing["name"]
        try:
            times = [r[0] for r in
                     sandbox_mod.read_exp(editing["data.exp"])["rows"]]
        except Exception:
            times = None
        try:
            settings = sandbox_mod.engine_settings(editing["priors.conf"],
                                                   times=times)
        except Exception:
            settings = []
        # the run form starts from this model's newest run, else a quick
        # check (a shipped start: its production seed, 4 forecast weeks)
        prev = runs[0] if runs else {}
        shipped = sandbox_mod.shipped_state(name, {
            f: editing[f] for f in sandbox_mod.REQUIRED})
        form = {"particles": int(prev.get("particles")
                                 or sandbox_mod.DRY_RUN_PARTICLES),
                "jitter": prev.get("jitter", 0.15),
                "forecast_weeks": prev.get("forecast_weeks", 4),
                "seed": prev.get("seed", shipped["info"].get("seed", 0)
                                 if shipped["shipped"] else 0)}
        ctx.update({
            "shipped": shipped,
            "info": sandbox_mod.read_info(name),
            "note": next((m["note"] for m in models if m["name"] == name), ""),
            "origin": next((m["origin"] for m in models if m["name"] == name), ""),
            "settings": settings, "form": form,
            "presets": {"quick": sandbox_mod.DRY_RUN_PARTICLES,
                        "full": sandbox_mod.FULL_FIT_PARTICLES},
            # seconds at the reference 10,000 particles; the page scales it
            "eta_full": round(sandbox_mod.eta_seconds(
                len(times or []), sandbox_mod.FULL_FIT_PARTICLES), 1),
            # the archive as a data source (empty lists with no hub)
            "locations": sandbox_mod.locations(),
            "vintages": sandbox_mod.vintages(),
            "data_range": sandbox_mod.default_range(sandbox_mod.vintages()),
            "data_source": sandbox_mod.read_data_source(name),
            # your own data: stored datasets, and an upload's refusal
            "datasets": sandbox_mod.dataset_choices(),
            "pick_dataset": dataset,
            "upload_report": _sandbox_upload_report.pop(name, None),
            "upload_mb": sandbox_mod.UPLOAD_MAX_BYTES // (1024 * 1024)})
    return templates.TemplateResponse(request, "sandbox.html", ctx)


@router.post("/sandbox/add-example")
def sandbox_add_example(request: Request, name: str = Form(...)):
    """Kept for scripts and old pages: an example under its own name."""
    try:
        sandbox_mod.add_example(name)
        _flash(f"Example {name} copied into the sandbox.")
        return _sandbox_redirect(name)
    except Exception as e:
        _flash(str(e))
        return _sandbox_redirect()


@router.post("/sandbox/new")
def sandbox_new(request: Request, name: str = Form(...),
                start: str = Form("skeleton"), location: str = Form(""),
                forecast_date: str = Form(""), season_start: str = Form(""),
                group: str = Form(""), as_of: str = Form("")):
    """A new model: the skeleton (fits as written), a copy of a shipped
    example (example:<name>) or of a sandbox model (copy:<name>), or the
    Oracle SIHRS filter as production builds it for one hub location and
    forecast date (shipped:sihrs) or one group of a stored dataset with a
    population (shipped:dataset:<id>, as of as_of)."""
    name = (name or "").strip()
    kind, _, what = (start or "skeleton").partition(":")
    try:
        if kind == "shipped" and what == "sihrs":
            sandbox_mod.from_shipped(name, location, forecast_date,
                                     season_start=season_start)
            _flash(f"{name}: the Oracle SIHRS filter for {location.strip()} "
                   f"as of {forecast_date.strip()}.")
        elif kind == "shipped" and what.startswith("dataset:"):
            sandbox_mod.from_shipped(name, group, as_of,
                                     season_start=season_start,
                                     dataset=what.split(":", 1)[1])
            _flash(f"{name}: the Oracle SIHRS filter for {group.strip()} "
                   f"as of {as_of.strip()}.")
        elif kind == "example":
            sandbox_mod.add_example(what, as_name=name)
            _flash(f"{name} copied from the example {what}.")
        elif kind == "copy":
            sandbox_mod.copy_model(what, name)
            _flash(f"{name} copied from {what}.")
        elif kind == "skeleton":
            sandbox_mod.new_model(name)
            _flash(f"{name} written from the skeleton.")
        else:
            raise sandbox_mod.SandboxError(f"{start!r} is not a way to start")
        return _sandbox_redirect(name)
    except Exception as e:
        _flash(str(e))
        return _sandbox_redirect(what if kind == "copy" else "")


@router.post("/sandbox/models/{name}/delete")
def sandbox_delete_model(name: str, confirm: str = Form("")):
    """Delete a model with its runs (never while one of them fits)."""
    if confirm != name:
        _flash("Not deleted: the confirmation did not name the model.")
        return _sandbox_redirect(name)
    try:
        n = sandbox_mod.delete_model(name, live=_sandbox_status.get("running"))
        _flash(f"Deleted {name}" + (f" and its {n} run{'' if n == 1 else 's'}"
                                    if n else "") + ".")
        return _sandbox_redirect()
    except Exception as e:
        _flash(str(e))
        return _sandbox_redirect(name)


@router.post("/sandbox/runs/{run_id}/delete")
def sandbox_delete_run(run_id: str, confirm: str = Form("")):
    """Delete one run folder (never the live fit)."""
    if confirm != run_id:
        _flash("Not deleted: the confirmation did not name the run.")
        return _sandbox_redirect()
    try:
        model = sandbox_mod.delete_run(run_id, live=_sandbox_status.get("running"))
        _flash(f"Deleted sandbox run {run_id}.")
        return _sandbox_redirect(model)
    except Exception as e:
        _flash(str(e))
        return _sandbox_redirect()


@router.post("/sandbox/models/{name}/save")
def sandbox_save(request: Request, name: str,
                 model_bngl: str = Form(""), data_exp: str = Form(""),
                 priors_conf: str = Form("")):
    try:
        sandbox_mod.save_model(name, {"model.bngl": model_bngl,
                                      "data.exp": data_exp,
                                      "priors.conf": priors_conf})
        _flash(f"Saved {name}.")
    except Exception as e:
        _flash(str(e))
    return _sandbox_redirect(name)


@router.post("/api/sandbox/models/{name}/check")
def api_sandbox_check(name: str, model_bngl: str = Form(""),
                      data_exp: str = Form(""), priors_conf: str = Form("")):
    """Check the posted editor text (each field falling back to the saved
    file) without the engine: JSON problems, warnings and facts."""
    try:
        files = sandbox_mod.read_model(name)
        for f, v in (("model.bngl", model_bngl), ("data.exp", data_exp),
                     ("priors.conf", priors_conf)):
            if (v or "").strip():
                files[f] = v.replace("\r\n", "\n")
        return sandbox_mod.check(files, work=sandbox_mod.SANDBOX / "check")
    except Exception as e:
        return JSONResponse({"ok": False, "problems": [str(e)[:1500]],
                             "warnings": [], "facts": {}}, status_code=200)


def _sandbox_fill_flash(info: dict) -> None:
    if info["asof"] == "dataset":
        what = f"dataset {info['dataset']['name']}"
    elif info["asof"] == "settled":
        what = "settled truth"
    else:
        what = f"vintage of {info['asof']}"
    msg = (f"data.exp filled: {info['location']}, {info['start']} to "
           f"{info['end']}, {what}, {info['rows']} weeks")
    if info["dropped"]:
        msg += f", {info['dropped']} missing weeks dropped"
    if info.get("population_set"):
        msg += f"; N set to {info['population_set']:,}"
    if info.get("kind") == "rate":
        msg += (" (rates, not counts: the default objfunc expects counts; "
                "set objfunc in priors.conf)")
    _flash(msg)


@router.post("/sandbox/models/{name}/fill-data")
def sandbox_fill_data(request: Request, name: str, location: str = Form(""),
                      start: str = Form(""), end: str = Form(""),
                      source: str = Form("settled"), group: str = Form(""),
                      model_bngl: str = Form(""), data_exp: str = Form(""),
                      priors_conf: str = Form(""), set_pop: str = Form("")):
    """data.exp from the hub archive (one location, settled truth or one
    vintage) or from a stored dataset (source=dataset:<id>, one group).
    Missing weeks dropped and counted, never imputed. The editor's other
    fields are saved first, so unsaved edits survive the fill (data.exp
    gives its header only). set_pop also sets the model's N to the
    location's population (refused for a model that derives i0 from N)."""
    pop = bool(set_pop)
    src = (source or "settled").strip()
    try:
        saved = _sandbox_save_posted(name, model_bngl, data_exp, priors_conf)
        if saved:
            _flash(f"Saved {', '.join(saved)} first.")
        if src.startswith("dataset:"):
            info = sandbox_mod.fill_data(name, (group or "").strip(),
                                         (start or "").strip(),
                                         (end or "").strip(),
                                         dataset=src.split(":", 1)[1],
                                         set_pop=pop)
        else:
            info = sandbox_mod.fill_data(
                name, (location or "").strip(), (start or "").strip(),
                (end or "").strip(), asof=None if src == "settled" else src,
                set_pop=pop)
        _sandbox_fill_flash(info)
    except Exception as e:
        _flash(str(e))
    return _sandbox_redirect(name)


@router.post("/sandbox/models/{name}/simulate-data")
def sandbox_simulate_data(name: str, model_bngl: str = Form(""),
                          data_exp: str = Form(""), priors_conf: str = Form(""),
                          seed: str = Form("")):
    """data.exp from the model itself: counts drawn around what the model
    gives at the values model.bngl writes, over data.exp's own weeks, so a
    fit can be seen to recover values that are known. The editor's text
    is saved first."""
    try:
        saved = _sandbox_save_posted(name, model_bngl, data_exp, priors_conf)
        if saved:
            _flash(f"Saved {', '.join(saved)} first.")
        s = int(seed) if str(seed).strip().isdigit() else 1
        f = sandbox_mod.simulate_data(name, seed=s)
        noise = (f"negative-binomial noise at r = {f['r']:g}" if f["r"]
                 else "Poisson noise")
        _flash(f"data.exp filled with {f['rows']} weeks of {f['column']} "
               "simulated from the model at the values written in "
               f"model.bngl, with {noise}: a fit should find values near "
               "them.")
    except Exception as e:
        _flash(f"Not simulated: {e}")
    return _sandbox_redirect(name)


#: an upload's refusal, shown inline in the Load data box on the next view
#: of that model (popped once shown)
_sandbox_upload_report: dict = {}

#: the request body cap: the CSV's own cap plus room for the editor text
#: that rides along in the same form
_SANDBOX_BODY_SLACK = 4 * 1024 * 1024


class _SandboxTooLarge(Exception):
    pass


async def _sandbox_capped_form(request: Request, cap: int):
    """The multipart form, refused before reading when Content-Length says
    it is over the cap, and cut off while reading past it (a chunked body
    has no length to trust)."""
    from starlette.requests import Request as _Req
    cl = request.headers.get("content-length", "")
    if cl.strip().isdigit() and int(cl) > cap:
        raise _SandboxTooLarge()
    seen = 0
    receive = request.receive

    async def capped():
        nonlocal seen
        msg = await receive()
        if msg.get("type") == "http.request":
            seen += len(msg.get("body", b"") or b"")
            if seen > cap:
                raise _SandboxTooLarge()
        return msg
    return await _Req(request.scope, capped).form(
        max_files=1, max_fields=40, max_part_size=_SANDBOX_BODY_SLACK)


@router.post("/sandbox/models/{name}/upload-data")
async def sandbox_upload_data(request: Request, name: str):
    """A CSV of your own (grouped date,target_group,value[,population] or
    hubverse), validated and stored through the dataset store, then loaded
    into data.exp when it holds one group (else the Load data box offers
    it to pick a group). The size cap holds before and while reading; the
    client's file name is never used as a path."""
    from starlette.concurrency import run_in_threadpool
    from starlette.datastructures import UploadFile
    cap = sandbox_mod.UPLOAD_MAX_BYTES
    try:
        sandbox_mod.check_name(name)
        form = await _sandbox_capped_form(request, cap + _SANDBOX_BODY_SLACK)
    except _SandboxTooLarge:
        _sandbox_upload_report[name] = {"problems": [
            f"The upload is larger than the {cap // (1024 * 1024)} MB limit; "
            "nothing was read past it or stored."]}
        return _sandbox_redirect(name)
    except Exception as e:
        _flash(f"The upload could not be read: {e}")
        return _sandbox_redirect(name if sandbox_mod.NAME_RE.match(name) else "")
    try:
        saved = await run_in_threadpool(
            _sandbox_save_posted, name, str(form.get("model_bngl") or ""),
            str(form.get("data_exp") or ""), str(form.get("priors_conf") or ""))
        if saved:
            _flash(f"Saved {', '.join(saved)} first.")
    except Exception as e:
        _flash(str(e))
        return _sandbox_redirect(name)
    up = form.get("csv")
    if not isinstance(up, UploadFile) or not up.filename:
        _sandbox_upload_report[name] = {"problems": ["Choose a CSV file to upload."]}
        return _sandbox_redirect(name)
    kind = str(form.get("kind") or "")          # '' = from the values
    try:
        ds = await run_in_threadpool(sandbox_mod.ingest_upload, up.file,
                                     up.filename, kind, cap)
    except sandbox_mod.UploadRefused as e:
        _sandbox_upload_report[name] = {"problems": e.problems or [str(e)]}
        return _sandbox_redirect(name)
    finally:
        await up.close()
    warn = list(ds.meta.get("warnings") or [])
    if len(ds.groups) == 1:
        try:
            info = await run_in_threadpool(sandbox_mod.fill_data, name,
                                           ds.groups[0], "", "",
                                           dataset=ds.id)
            _sandbox_fill_flash(info)
        except Exception as e:
            _flash(str(e))
    else:
        _flash(f"Stored {ds.name} ({len(ds.groups)} groups); pick a group "
               "under Load data.")
    if warn:
        _sandbox_upload_report[name] = {"problems": [], "warnings": warn}
    return RedirectResponse(_sandbox_url(name) + f"&dataset={ds.id}",
                            status_code=303)


def _sandbox_start(name: str, *, particles: int, jitter: float,
                   forecast_weeks: int, seed: int) -> RedirectResponse:
    """Claim the engine (under _engine_lock, before preparing), prepare the
    run, then fit it on a background thread. Stop during preparation
    cancels the run before the engine sees it."""
    with _engine_lock:
        why = _sandbox_busy_reason()
        if why:
            _flash(f"Not started: {why}. The sandbox waits for the engine.")
            return _sandbox_redirect(name)
        _sandbox_status.update(claim=name, cancel=False)
    try:
        workroot = sandbox_mod.prepare(name, particles=particles,
                                       jitter=jitter,
                                       forecast_weeks=forecast_weeks,
                                       seed=seed)
    except Exception as e:
        with _engine_lock:
            _sandbox_status.update(claim=None, cancel=False)
        _flash(f"Not started: {e}")
        return _sandbox_redirect(name)
    run_id = workroot.name
    with _engine_lock:
        cancelled = _sandbox_status.get("cancel")
        _sandbox_status.update(claim=None, cancel=False,
                               running=None if cancelled else run_id)
    if cancelled:
        sandbox_mod.mark(workroot, "stopped")
        _flash(f"Sandbox run {run_id} was stopped before it started.")
        return _sandbox_redirect(name, run_id)

    def _go():
        guard = pipeline._sleep_guard()  # a full fit must outlive the lid
        try:
            sandbox_mod.run(workroot)
        finally:
            if guard is not None:
                try:
                    guard.terminate()
                except Exception:
                    pass
            with _engine_lock:
                if _sandbox_status.get("running") == run_id:
                    _sandbox_status["running"] = None

    threading.Thread(target=_go, daemon=True, name=f"sandbox-{run_id}").start()
    _flash(f"Sandbox run {run_id} started with "
           f"{max(50, min(int(particles), 100_000))} particles.")
    return _sandbox_redirect(name, run_id)


@router.post("/sandbox/run")
def sandbox_run(request: Request, model: str = Form(...),
                particles: int = Form(sandbox_mod.DRY_RUN_PARTICLES),
                jitter: float = Form(0.15), forecast_weeks: int = Form(4),
                seed: int = Form(0)):
    """Kept for scripts and old pages: run a model's saved files."""
    return _sandbox_start(model, particles=particles, jitter=jitter,
                          forecast_weeks=forecast_weeks, seed=seed)


@router.post("/sandbox/models/{name}/run")
def sandbox_model_run(name: str, model_bngl: str = Form(""),
                      data_exp: str = Form(""), priors_conf: str = Form(""),
                      particles: int = Form(sandbox_mod.DRY_RUN_PARTICLES),
                      jitter: float = Form(0.15), forecast_weeks: int = Form(4),
                      seed: int = Form(0)):
    """Save and run: the posted editor fields are saved first (the run's
    workroot keeps its own copy), then the run starts as /sandbox/run's."""
    try:
        saved = _sandbox_save_posted(name, model_bngl, data_exp, priors_conf)
        if saved:
            _flash(f"Saved {name}.")
    except Exception as e:
        _flash(f"Not saved, not started: {e}")
        return _sandbox_redirect(name)
    return _sandbox_start(name, particles=particles, jitter=jitter,
                          forecast_weeks=forecast_weeks, seed=seed)


@router.post("/sandbox/runs/{run_id}/stop")
def sandbox_run_stop(run_id: str):
    """Stop the live fit named here (the STOP flag execute polls)."""
    model = ""
    try:
        d = _sandbox_run_dir(run_id)
        model = sandbox_mod.results(d)["meta"].get("model", "")
        with _engine_lock:
            live = _sandbox_status.get("running") == run_id
        if live:
            sandbox_mod.stop(d)
            _flash(f"Stopping sandbox run {run_id}; it ends at the next "
                   "safe point.")
        else:
            _flash(f"Sandbox run {run_id} is not fitting; nothing to stop.")
    except Exception as e:
        _flash(str(e))
    return _sandbox_redirect(model, run_id if model else "")


@router.post("/sandbox/stop")
def sandbox_stop():
    """Stop whatever the sandbox has on the engine (the guard modal's
    Stop): the live fit, or a run still being prepared."""
    with _engine_lock:
        running = _sandbox_status.get("running")
        if not running and _sandbox_status.get("claim"):
            _sandbox_status["cancel"] = True
    if running:
        try:
            sandbox_mod.stop(_sandbox_run_dir(running))
        except Exception:
            pass
    return _sandbox_redirect()


@router.get("/api/sandbox/models/{name}/contactmap")
def api_sandbox_contactmap(name: str):
    """The model's diagrams: "flow", the rules as arrows between molecule
    types (read from the text, no BNG2.pl), and the contact map BNG2.pl's
    visualize action draws on a copy of the model (no engine, no run).
    "sites": any molecule with components, the only models whose contact
    map and network say more than the flow. BNG2.pl's words come back as
    "error" beside the flow. Cached by the model text until it changes."""
    from app.core import contactmap
    try:
        files = sandbox_mod.read_model(name)
    except Exception as e:
        return JSONResponse({"error": str(e)[:1500]}, status_code=200)
    bngl = files["model.bngl"]
    hit = sandbox_mod.cached_view(name, "contactmap", bngl)
    if hit is not None and "flow" in hit:
        return hit
    try:
        flow = contactmap.rule_flow(bngl)
    except Exception:
        flow = None
    try:
        work = sandbox_mod.SANDBOX / "contactmap" / sandbox_mod.check_name(name)
        cm = contactmap.parse(contactmap.graphml_from_bngl(bngl, work))
    except Exception as e:
        return JSONResponse({"error": str(e)[:1500], "flow": flow}, status_code=200)
    out = {"svg": contactmap.svg(cm), "molecules": len(cm["molecules"]),
           "bonds": len(cm["bonds"]), "graph": contactmap.contact_graph(cm),
           "flow": flow, "sites": any(m["components"] for m in cm["molecules"])}
    sandbox_mod.store_view(name, "contactmap", bngl, out)
    return out


@router.get("/api/sandbox/models/{name}/network")
def api_sandbox_network(name: str):
    """BNG2.pl's generated reaction network as inline SVG (generate-only
    copy, no run); too large -> counts and a note. "graph" always returned.
    Cached by the model text until it changes."""
    from app.core import contactmap
    try:
        files = sandbox_mod.read_model(name)
        bngl = files["model.bngl"]
        hit = sandbox_mod.cached_view(name, "network", bngl)
        if hit is not None:
            return hit
        work = sandbox_mod.SANDBOX / "contactmap" / sandbox_mod.check_name(name)
        net = contactmap.parse_net(contactmap.network_from_bngl(bngl, work))
        drawing = contactmap.svg_network(net)
        out = {"svg": drawing if drawing.startswith("<svg") else "",
               "species": len(net["species"]), "reactions": len(net["reactions"]),
               "graph": contactmap.network_graph(net)}
        if not out["svg"]:
            out["note"] = drawing
        sandbox_mod.store_view(name, "network", bngl, out)
        return out
    except Exception as e:
        return JSONResponse({"error": str(e)[:1500]}, status_code=200)


@router.get("/api/sandbox/runs/{run_id}")
def api_sandbox_run(run_id: str):
    try:
        return sandbox_mod.results(_sandbox_run_dir(run_id),
                                   live=_sandbox_status.get("running"))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=404)


def _sandbox_local_get(request: Request) -> bool:
    """A download is served only to a localhost Host (and Origin, when
    sent): GET stays open elsewhere, but a model or a run is the user's
    own files, not for a DNS-rebinding page to read."""
    origin = request.headers.get("origin")
    return (_authority_hostname(request.headers.get("host", ""))
            in _LOCAL_HOSTNAMES
            and (origin is None
                 or _authority_hostname(origin) in _LOCAL_HOSTNAMES))


def _sandbox_zip(data: bytes, filename: str):
    from fastapi.responses import Response
    return Response(data, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store"})


@router.get("/sandbox/models/{name}/download")
def sandbox_model_download(request: Request, name: str):
    """The model's three files and sidecars as a zip."""
    if not _sandbox_local_get(request):
        return PlainTextResponse("Refused: not a localhost request.\n",
                                 status_code=403)
    try:
        return _sandbox_zip(sandbox_mod.model_zip(name), f"{name}.zip")
    except Exception as e:
        return PlainTextResponse(f"{e}\n", status_code=404)


@router.get("/sandbox/runs/{run_id}/download")
def sandbox_run_download(request: Request, run_id: str):
    """A run's inputs, engine outputs and summary.csv as a zip."""
    if not _sandbox_local_get(request):
        return PlainTextResponse("Refused: not a localhost request.\n",
                                 status_code=403)
    try:
        return _sandbox_zip(sandbox_mod.run_zip(run_id), f"{run_id}.zip")
    except Exception as e:
        return PlainTextResponse(f"{e}\n", status_code=404)


@router.post("/sandbox/runs/{run_id}/oracle")
def sandbox_run_oracle(run_id: str, w: str = Form("")):
    """The production Oracle step on a finished run of an unedited Oracle
    SIHRS start, inside the run folder only (sandbox, not a submission):
    nothing reaches the ledger, the site, the archive or model-output."""
    model = ""
    try:
        model = str(sandbox_mod.results(_sandbox_run_dir(run_id))["meta"]
                    .get("model", ""))
        try:
            wv = float(w) if str(w).strip() else None
        except ValueError:
            raise sandbox_mod.SandboxError(f"w must be a number, not {w!r}")
        out = sandbox_mod.oracle_step(run_id, wv)
        _flash(f"Oracle step applied to {run_id} with w = {out['w']:g} "
               "(sandbox, not a submission).")
    except Exception as e:
        _flash(f"Oracle step not applied: {e}")
    return _sandbox_redirect(model, run_id if model else "")


def _sandbox_storage_line() -> dict:
    """The Storage panel's read-only sandbox line (kept out of its total:
    the sandbox's runs are deleted from the sandbox, not from there)."""
    from app.core import retro
    try:
        s = sandbox_mod.storage()
    except Exception:
        return {}
    return {**s, "size_h": retro.human_bytes(s["bytes"])} if s["bytes"] else {}
