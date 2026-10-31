"""Sandbox (GET /sandbox): user models fitted on the production engine.

Also the sandbox's half of the two-way engine guard (_sandbox_engine_guard,
which server.py registers as the outermost middleware) and the Storage
panel's read-only sandbox line (_sandbox_storage_line, which server.py
registers as the sandbox_storage Jinja global). app/core/sandbox.py does
the work. An APIRouter server.py includes.

Sections: the engine guard and busy reason; redirects and the posted
editor; the page (GET /sandbox); models (new, save, delete, check,
register); data.exp (fill, simulate, upload); runs (start, stop); the
diagram API and the run poll; downloads; the Oracle step; experiments
(start, the compare page and its JSON, delete; app/core/experiments.py
does the work); the Storage line.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import (HTMLResponse, JSONResponse, PlainTextResponse,
                               RedirectResponse)

from app.core import sandbox as sandbox_mod
from app.ui import pipeline, retro_seasons
from app.ui.retro_seasons import _RETRO_ACTIVE, _season_status
from app.ui.routes.data import _wants_json
from app.ui.shared import (_LOCAL_HOSTNAMES, _authority_hostname,
                           _experiment_live, _flash, _invalidate_scans,
                           _sandbox_live, _sandbox_live_reason)
from app.ui.state import _engine_lock, _sandbox_status, _status
from app.ui.templating import _script_json, templates
from app.ui.versions import RUNNING_SHA

router = APIRouter()


# ------------------------------------------ the engine guard and busy reason
# Nothing here touches the ledger, Output, retro or seal.

def _sandbox_busy_reason() -> str:
    """Why a sandbox fit may not start now ("" when the engine is free)."""
    # a Groundhog-only run fits nothing, but it holds the console's one run
    # slot all the same: said as a run, not a fit
    if _status.get("running"):
        return "a console run is in progress"
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
            # one run at a time, whatever the model: a Groundhog-only run
            # needs no engine, so the refusal claims none
            _flash(f"Not started: a sandbox fit is running ({live}); one run "
                   "at a time.", "warn",
                   detail="Stop it from the Sandbox tab first.")
            return RedirectResponse("/retro" if path == "/retro/run"
                                    else "/forecast", status_code=303)
    return await call_next(request)


# ------------------------------------------ redirects and the posted editor

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


# ------------------------------------------------------ the page (GET)

#: the start the New model form offers first
FIRST_START = "sir_example"


#: the New model form a refusal sends back (one-shot, read by the page)
_sandbox_new_refused: dict = {}


def _free_name(stem: str, taken: set) -> str:
    """The first of stem_1, stem_2, ... that no model has: the name the
    New model form fills in, so a first visit need not invent one."""
    n = 1
    while f"{stem}_{n}" in taken:
        n += 1
    return f"{stem}_{n}"


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
            _not_done("Not opened", e)
            model = ""
    all_runs = sandbox_mod.list_runs(live=live)
    # this computer's speed, from its last finished fit of any model
    ratio = sandbox_mod.eta_ratio(all_runs)
    last = {}
    for r in all_runs:
        last.setdefault(r.get("model"), r)
    runs = [r for r in all_runs if r.get("model") == model] if model else []
    res = None
    try:
        if run:
            res = sandbox_mod.results(sandbox_mod.run_dir(run), live=live)
            if model and res["meta"].get("model") != model:
                res = None
    except Exception as e:
        _flash(f"Could not read that sandbox run: {e}", "error")
        res = None
    # no run named, or one this model cannot show (another model's, or
    # gone): its newest run, never "No runs yet" beside a list of runs
    if res is None and runs:
        try:
            res = sandbox_mod.results(sandbox_mod.RUNS / runs[0]["run_id"],
                                      live=live)
        except Exception as e:
            _flash(f"Could not read that sandbox run: {e}", "error")
            res = None
    # a second run of the same model, overlaid and diffed against the open one
    cmp, diff = None, None
    if res and compare and compare != res["run_id"]:
        try:
            cmp = sandbox_mod.results(sandbox_mod.run_dir(compare), live=live)
            if cmp["meta"].get("model") != res["meta"].get("model"):
                raise sandbox_mod.SandboxError(
                    f"{compare} is a run of another model")
            diff = sandbox_mod.diff_runs(compare, res["run_id"])
        except Exception as e:
            _not_done("Not compared", e)
            cmp, diff = None, None
    examples = sandbox_mod.list_examples()
    taken = {m["name"] for m in models}
    # the gallery's Experiments card: its choices and the experiments here
    exp = None
    if not editing:
        try:
            exp = _experiment_gallery()
        except Exception as e:
            _flash(f"Experiments could not be listed: {e}", "error")
    ctx = {"active": "Sandbox", "models": models, "last": last,
           # the simplest example first: a first visit starts from it
           "examples": sorted((e for e in examples
                               if not e.endswith("_template")),
                              key=lambda e: (e != FIRST_START, e)),
           "templates": [e for e in examples if e.endswith("_template")],
           "example_notes": {e: sandbox_mod.example_note(e) for e in examples},
           "example_names": {e: _free_name(e, taken)
                             for e in examples + ["skeleton", "variant"]},
           "copy_names": {m: _free_name(m + "_copy", taken) for m in taken},
           # a refused New model form comes back as it was posted (SB-09)
           "new_form": _sandbox_new_refused.pop("form", {}),
           "runs": runs,
           "res": res, "res_json": _script_json(res or {}),
           "cmp": cmp, "cmp_json": _script_json(cmp or {}), "diff": diff,
           "editing": editing, "busy": _sandbox_busy_reason(),
           # why this computer cannot fit yet, said before a run is tried
           "machine": (sandbox_mod.split_reason(sandbox_mod.machine_problem())
                       if editing else ("", "")),
           "running_id": live,
           # the Oracle SIHRS start (the gallery's New model form)
           "vintages": sandbox_mod.vintages(),
           "locations": sandbox_mod.locations(),
           "datasets": sandbox_mod.dataset_choices(),
           "exp": exp}
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
        # the run form starts from this model's newest run, else the full
        # fit: a first run should give estimates, and a quick check's 200
        # particles often collapse on a real prior (a shipped start: its
        # production seed, 4 forecast weeks)
        prev = runs[0] if runs else {}
        shipped = sandbox_mod.shipped_state(name, {
            f: editing[f] for f in sandbox_mod.REQUIRED})
        form = {"particles": int(prev.get("particles")
                                 or sandbox_mod.FULL_FIT_PARTICLES),
                "jitter": prev.get("jitter", 0.15),
                "forecast_weeks": prev.get("forecast_weeks", 4),
                "seed": prev.get("seed", shipped["info"].get("seed", 0)
                                 if shipped["shipped"] else 0)}
        n_obs = len(times or [])
        ctx.update({
            "shipped": shipped,
            "info": sandbox_mod.read_info(name),
            "origin": next((m["origin"] for m in models if m["name"] == name), ""),
            "settings": settings, "form": form,
            "presets": {"quick": sandbox_mod.DRY_RUN_PARTICLES,
                        "full": sandbox_mod.FULL_FIT_PARTICLES},
            # (low, high) seconds at the reference 10,000 particles, which
            # the page scales; the words for the form's own count
            "eta_full": sandbox_mod.eta_span(
                n_obs, sandbox_mod.FULL_FIT_PARTICLES, ratio),
            "eta_text": sandbox_mod.eta_words(*sandbox_mod.eta_span(
                n_obs, form["particles"], ratio)),
            "fitting": _sandbox_fitting(live, name, ratio),
            # the archive as a data source (empty lists with no hub)
            "locations": sandbox_mod.locations(),
            "vintages": sandbox_mod.vintages(),
            "data_range": sandbox_mod.default_range(sandbox_mod.vintages()),
            "data_source": sandbox_mod.read_data_source(name),
            # N written as a placeholder: every run fills it, so Load data
            # offers no Set N
            "n_placeholder": sandbox_mod.placeholder_n(editing["model.bngl"]),
            # your own data: stored datasets, and an upload's refusal
            "datasets": sandbox_mod.dataset_choices(),
            "pick_dataset": dataset,
            "upload_max": sandbox_mod.UPLOAD_MAX_BYTES,
            "upload_report": _sandbox_upload_report.pop(name, None)})
    return templates.TemplateResponse(request, "sandbox.html", ctx)


def _sandbox_fitting(live, name: str, ratio) -> dict | None:
    """The live fit when it is a run of this model, else None: its start,
    its estimate for its own rows and particles, and the words the page
    shows now (sandbox.js counts them up from the start)."""
    meta = sandbox_mod.run_meta(live)
    if meta.get("model") != name:
        return None
    try:
        n_obs = int(meta.get("n_obs") or len(meta.get("observed") or []))
        low, high = sandbox_mod.eta_span(n_obs, int(meta["particles"]), ratio)
    except (KeyError, TypeError, ValueError):
        low = high = 0.0                        # no estimate: the time only
    elapsed = sandbox_mod.run_elapsed(meta)
    return {"run_id": str(live), "started": str(meta.get("started_utc", "")),
            "low": low, "high": high, "slow_after": sandbox_mod.slow_after(high),
            "line": sandbox_mod.fitting_line(elapsed, low, high),
            "button": f"Fitting… {sandbox_mod.clock(elapsed)}"}


def _not_done(lead: str, e: Exception) -> None:
    """Flash a sandbox action that did not happen, `lead` first ("Not
    saved"): a SandboxError is a refusal (warn), anything else a failure
    (error). A long reason's first line (or first sentence) is the notice,
    the rest its tip, so a remedy at the end is never cut off."""
    notice, tip = sandbox_mod.split_reason(str(e))
    _flash(f"{lead}: {notice}",
           "warn" if isinstance(e, sandbox_mod.SandboxError) else "error",
           detail=tip)


# -------------------------------------------------------------- models

@router.post("/sandbox/add-example")
def sandbox_add_example(request: Request, name: str = Form(...)):
    """Kept for scripts and old pages: an example under its own name."""
    try:
        sandbox_mod.add_example(name)
        _flash(f"Example {name} copied into the sandbox.", "ok")
        return _sandbox_redirect(name)
    except Exception as e:
        _not_done("Not copied", e)
        return _sandbox_redirect()


@router.post("/sandbox/new")
def sandbox_new(request: Request, name: str = Form(...),
                start: str = Form("skeleton"), location: str = Form(""),
                forecast_date: str = Form(""), season_start: str = Form(""),
                group: str = Form(""), as_of: str = Form("")):
    """A new model: the skeleton (fits as written), a copy of a shipped
    example (example:<name>) or of a sandbox model (copy:<name>), the
    Oracle SIHRS filter as production builds it for one hub location and
    forecast date (shipped:sihrs) or one group of a stored dataset with a
    population (shipped:dataset:<id>, as of as_of), or the Oracle SIHRS
    template for replays, its placeholders kept, with one hub location's
    data as of forecast_date (template:sihrs)."""
    # a space reads as part of a name; the folder takes _ for it
    name = re.sub(r"\s+", "_", (name or "").strip())
    kind, _, what = (start or "skeleton").partition(":")
    try:
        if kind == "shipped" and what == "sihrs":
            sandbox_mod.from_shipped(name, location, forecast_date,
                                     season_start=season_start)
            _flash(f"{name}: the Oracle SIHRS filter for {location.strip()} "
                   f"as of {forecast_date.strip()}.", "ok")
        elif kind == "shipped" and what.startswith("dataset:"):
            sandbox_mod.from_shipped(name, group, as_of,
                                     season_start=season_start,
                                     dataset=what.split(":", 1)[1])
            _flash(f"{name}: the Oracle SIHRS filter for {group.strip()} "
                   f"as of {as_of.strip()}.", "ok")
        elif kind == "template" and what == "sihrs":
            sandbox_mod.from_shipped(name, location, forecast_date,
                                     season_start=season_start, template=True)
            _flash(f"{name}: the Oracle SIHRS template, with data for "
                   f"{location.strip()} as of {forecast_date.strip()}.", "ok")
        elif kind == "example":
            sandbox_mod.add_example(what, as_name=name)
            _flash(f"{name} copied from the example {what}.", "ok")
        elif kind == "copy":
            sandbox_mod.copy_model(what, name)
            _flash(f"{name} copied from {what}.", "ok")
        elif kind == "skeleton":
            sandbox_mod.new_model(name)
            _flash(f"{name} written from the skeleton.", "ok")
        else:
            raise sandbox_mod.SandboxError(f"{start!r} is not a way to start")
        return _sandbox_redirect(name)
    except Exception as e:
        _not_done("Not created", e)
        if kind != "copy":
            _sandbox_new_refused["form"] = {
                "name": name, "start": start, "location": location,
                "forecast_date": forecast_date, "season_start": season_start,
                "group": group, "as_of": as_of}
        return _sandbox_redirect(what if kind == "copy" else "")


@router.post("/sandbox/models/{name}/delete")
def sandbox_delete_model(name: str, confirm: str = Form("")):
    """Delete a model with its runs (never while one of them fits)."""
    if confirm != name:
        _flash("Not deleted: the confirmation did not name the model.",
               "warn")
        return _sandbox_redirect(name)
    try:
        n = sandbox_mod.delete_model(name, live=_sandbox_status.get("running"))
        _flash(f"Deleted {name}" + (f" and its {n} run{'' if n == 1 else 's'}"
                                    if n else "") + ".", "ok")
        return _sandbox_redirect()
    except Exception as e:
        _not_done("Not deleted", e)
        return _sandbox_redirect(name)


@router.post("/sandbox/runs/{run_id}/delete")
def sandbox_delete_run(run_id: str, confirm: str = Form("")):
    """Delete one run folder (never the live fit)."""
    if confirm != run_id:
        _flash("Not deleted: the confirmation did not name the run.", "warn")
        return _sandbox_redirect()
    try:
        model = sandbox_mod.delete_run(run_id, live=_sandbox_status.get("running"))
        _flash(f"Deleted sandbox run {run_id}.", "ok")
        return _sandbox_redirect(model)
    except Exception as e:
        _not_done("Not deleted", e)
        return _sandbox_redirect()


@router.post("/sandbox/models/{name}/save")
def sandbox_save(request: Request, name: str,
                 model_bngl: str = Form(""), data_exp: str = Form(""),
                 priors_conf: str = Form("")):
    try:
        sandbox_mod.save_model(name, {"model.bngl": model_bngl,
                                      "data.exp": data_exp,
                                      "priors.conf": priors_conf})
        _flash(f"Saved {name}.", "ok")
    except Exception as e:
        _not_done("Not saved", e)
    return _sandbox_redirect(name)


@router.post("/api/sandbox/models/{name}/check")
def api_sandbox_check(name: str, model_bngl: str = Form(""),
                      data_exp: str = Form(""), priors_conf: str = Form("")):
    """Check the posted editor text (each field falling back to the saved
    file) without the engine: JSON problems, warnings, facts and their
    codes (app/core/problem_codes.py), and, for a model that keeps
    placeholders, whether it is ready for replays."""
    try:
        files = sandbox_mod.read_model(name)
        for f, v in (("model.bngl", model_bngl), ("data.exp", data_exp),
                     ("priors.conf", priors_conf)):
            if (v or "").strip():
                files[f] = v.replace("\r\n", "\n")
        return sandbox_mod.check(files, work=sandbox_mod.SANDBOX / "check",
                                 name=name)
    except Exception as e:
        from app.core.problem_codes import finding
        said = str(e)[:1500]
        return JSONResponse({"ok": False, "problems": [said],
                             "warnings": [], "facts": {},
                             "codes": [finding("CHECK_FAILED", said)]},
                            status_code=200)


#: one Register at a time in this console: a double click registers once
#: (library.register takes no lock; test_library.py pins two processes
#: getting distinct versions)
_sandbox_register_lock = threading.Lock()


@router.post("/sandbox/models/{name}/register")
def sandbox_register(name: str, model_bngl: str = Form(""),
                     data_exp: str = Form(""), priors_conf: str = Form("")):
    """Register for replays: the posted editor fields are saved first (as
    Save and run's), then the saved model.bngl and priors.conf are frozen
    as the library's next version of this name (library.register), or
    named as the version that already holds them. Refused in words, each
    finding with its code. A name that is not exactly a Sandbox model's
    saves nothing. Redirects to the model."""
    from app.core import library
    from app.core.problem_codes import Refusal
    models = sandbox_mod.MODELS
    # the exact name before anything is saved: where folders ignore case,
    # BETA would save into beta's folder
    if not (models.is_dir() and name in {p.name for p in models.iterdir()}):
        _flash(f"Not registered: no Sandbox model is named {name!r} "
               "(letter case counts).", "warn")
        return _sandbox_redirect()
    with _sandbox_register_lock:
        try:
            if _sandbox_save_posted(name, model_bngl, data_exp, priors_conf):
                _flash(f"Saved {name}.", "ok")
        except Exception as e:
            _not_done("Not saved, not registered", e)
            return _sandbox_redirect(name)
        try:
            r = library.register(name)
        except Refusal as e:
            # the problems first, each with its code; the rest in the "?"
            found = ([f for f in e.findings if f["tier"] == "problem"]
                     + [f for f in e.findings if f["tier"] != "problem"])
            _not_done("Not registered", sandbox_mod.SandboxError(
                "\n".join(f"{f['text']} ({f['code']})" for f in found)))
            return _sandbox_redirect(name)
        except Exception as e:                    # the computer, not the model
            _not_done("Not registered", e)
            return _sandbox_redirect(name)
    s = library.short(r["fingerprint"])
    notes = "; ".join(f"{f['text']} ({f['code']})" for f in r["findings"])
    _flash(f"Registered {r['ref']} ({s})." if r["new"] else
           f"{r['ref']} already holds these files ({s}); nothing new was "
           "registered.", "ok",
           detail=f"Worth a look: {notes}" if notes else "")
    return _sandbox_redirect(name)


# ------------------------------------------------------------ data.exp

def _sandbox_fill_flash(info: dict) -> None:
    if info["asof"] == "dataset":
        what = f"dataset {info['dataset']['name']}"
    elif info["asof"] == "settled":
        what = "settled truth"
    else:
        what = f"vintage of {info['asof']}"
    # a file with no group column says so, so a date,count file read as
    # one series is not a surprise
    one = " (one series)" if info.get("one_series") else ""
    # the weeks loaded, not the range asked for
    wk = info.get("dates") or [info["start"], info["end"]]
    msg = (f"data.exp filled: {info['rows']} weeks of {info['location']}"
           f"{one}, {wk[0]} to {wk[-1]}.")
    detail = f"Source: {what}."
    if info["dropped"]:
        detail += f" {info['dropped']} missing weeks dropped."
    if info.get("population_set"):
        detail += f" N set to {info['population_set']:,}."
    rate = info.get("kind") == "rate"
    if rate:
        # to act on: said on the line, the why in the tip
        msg += " Rates: set objfunc in priors.conf."
        detail += " The default objfunc expects counts."
    _flash(msg, "warn" if rate else "ok", detail=detail)


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
            _flash(f"Saved {', '.join(saved)} first.", "ok")
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
        _not_done("Not filled", e)
    return _sandbox_redirect(name)


@router.post("/sandbox/models/{name}/simulate-data")
def sandbox_simulate_data(name: str, model_bngl: str = Form(""),
                          data_exp: str = Form(""), priors_conf: str = Form(""),
                          sim_seed: str = Form("")):
    """data.exp from the model itself: counts drawn around what the model
    gives at the values model.bngl writes, over data.exp's own weeks, so a
    fit can be seen to recover values that are known. The editor's text
    is saved first."""
    try:
        saved = _sandbox_save_posted(name, model_bngl, data_exp, priors_conf)
        if saved:
            _flash(f"Saved {', '.join(saved)} first.", "ok")
        s = int(sim_seed) if str(sim_seed).strip().isdigit() else 1
        f = sandbox_mod.simulate_data(name, seed=s)
        noise = (f"negative-binomial noise at r = {f['r']:g}" if f["r"]
                 else "Poisson noise")
        # what a fit on them should find is the Simulate button's tip
        _flash(f"data.exp filled with {f['rows']} simulated weeks of "
               f"{f['column']}.", "ok",
               detail=f"Drawn from the model at the values written in "
               f"model.bngl, with {noise}.")
    except Exception as e:
        _not_done("Not simulated", e)
    return _sandbox_redirect(name)


#: an upload's refusal or notes, shown inline in the Load data box on the
#: next view of that model (popped once shown)
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
    """A CSV of your own (grouped date,target_group,value[,population],
    hubverse, or date,count read as one series named after the file),
    validated and stored through the dataset store, then loaded into
    data.exp when it holds one group (else the Load data box offers it to
    pick a group). The size cap holds before and while reading; the
    client's file name is never used as a path."""
    from starlette.concurrency import run_in_threadpool
    from starlette.datastructures import UploadFile
    cap = sandbox_mod.UPLOAD_MAX_BYTES
    try:
        sandbox_mod.check_name(name)
        form = await _sandbox_capped_form(request, cap + _SANDBOX_BODY_SLACK)
    except _SandboxTooLarge:
        # the editor's text rode in the same body: it was not saved either
        _sandbox_upload_report[name] = {"problems": [
            f"The upload is larger than the {cap // (1024 * 1024)} MB limit; "
            "nothing was read past it or stored, and unsaved edits in the "
            "editor were not saved."]}
        return _sandbox_redirect(name)
    except Exception as e:
        _flash(f"Could not read the upload: {e}", "error")
        return _sandbox_redirect(name if sandbox_mod.NAME_RE.match(name) else "")
    try:
        saved = await run_in_threadpool(
            _sandbox_save_posted, name, str(form.get("model_bngl") or ""),
            str(form.get("data_exp") or ""), str(form.get("priors_conf") or ""))
        if saved:
            _flash(f"Saved {', '.join(saved)} first.", "ok")
    except Exception as e:
        _not_done("Not saved", e)
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
            info["one_series"] = bool((ds.meta.get("columns") or {})
                                      .get("series"))
            _sandbox_fill_flash(info)
        except Exception as e:
            _not_done(f"Stored {ds.name}; data.exp not filled", e)
    else:
        _flash(f"Stored {ds.name} ({len(ds.groups)} groups); pick one "
               "under Load data.", "ok")
    if warn:
        _sandbox_upload_report[name] = {"problems": [], "warnings": warn}
    return RedirectResponse(_sandbox_url(name) + f"&dataset={ds.id}",
                            status_code=303)


# ---------------------------------------------------------------- runs

def _sandbox_start(name: str, *, particles: int, jitter: float,
                   forecast_weeks: int, seed: int) -> RedirectResponse:
    """Claim the engine (under _engine_lock, before preparing), prepare the
    run, then fit it on a background thread. Stop during preparation
    cancels the run before the engine sees it."""
    with _engine_lock:
        why = _sandbox_busy_reason()
        if why:
            _flash(f"Not started: {why}.", "warn",
                   detail="The sandbox waits for the engine.")
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
        _not_done("Not started", e)
        return _sandbox_redirect(name)
    run_id = workroot.name
    with _engine_lock:
        cancelled = _sandbox_status.get("cancel")
        _sandbox_status.update(claim=None, cancel=False,
                               running=None if cancelled else run_id)
    if cancelled:
        sandbox_mod.mark(workroot, "stopped")
        _flash(f"Sandbox run {run_id} was stopped before it started.",
               "warn")
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
           f"{max(50, min(int(particles), 100_000))} particles.", "ok")
    return _sandbox_redirect(name, run_id)


def _run_settings(particles: str, jitter: str, forecast_weeks: str,
                  seed: str) -> dict:
    """The run form's four settings as typed: '1e4' is 10,000 particles.
    A value that is not a number, or not whole where a count is meant, is
    refused in words (a page, never the raw validation JSON that would
    leave the window with no way back)."""
    def num(label: str, v: str, whole: bool):
        text = str(v).strip()
        try:
            x = float(text)
        except ValueError:
            raise sandbox_mod.SandboxError(
                f"{label} {text!r} is not a number") from None
        if x != x or x in (float("inf"), float("-inf")):
            raise sandbox_mod.SandboxError(f"{label} {text!r} is not a number")
        if whole:
            if not x.is_integer():
                raise sandbox_mod.SandboxError(
                    f"{label} {text!r} is not a whole number")
            return int(x)
        return x
    return {"particles": num("particles", particles, True),
            "jitter": num("jitter", jitter, False),
            "forecast_weeks": num("forecast weeks", forecast_weeks, True),
            "seed": num("seed", seed, True)}


@router.post("/sandbox/run")
def sandbox_run(request: Request, model: str = Form(...),
                particles: str = Form(str(sandbox_mod.DRY_RUN_PARTICLES)),
                jitter: str = Form("0.15"), forecast_weeks: str = Form("4"),
                seed: str = Form("0")):
    """Kept for scripts and old pages: run a model's saved files."""
    try:
        kw = _run_settings(particles, jitter, forecast_weeks, seed)
    except sandbox_mod.SandboxError as e:
        _not_done("Not started", e)
        return _sandbox_redirect(model)
    return _sandbox_start(model, **kw)


@router.post("/sandbox/models/{name}/run")
def sandbox_model_run(name: str, model_bngl: str = Form(""),
                      data_exp: str = Form(""), priors_conf: str = Form(""),
                      particles: str = Form(str(sandbox_mod.DRY_RUN_PARTICLES)),
                      jitter: str = Form("0.15"), forecast_weeks: str = Form("4"),
                      seed: str = Form("0")):
    """Save and run: the posted editor fields are saved first (the run's
    workroot keeps its own copy), then the run starts as /sandbox/run's.
    A run setting refused in words still leaves the edits saved."""
    try:
        saved = _sandbox_save_posted(name, model_bngl, data_exp, priors_conf)
        if saved:
            _flash(f"Saved {name}.", "ok")
    except Exception as e:
        _not_done("Not saved, not started", e)
        return _sandbox_redirect(name)
    try:
        kw = _run_settings(particles, jitter, forecast_weeks, seed)
    except sandbox_mod.SandboxError as e:
        _not_done("Not started", e)
        return _sandbox_redirect(name)
    return _sandbox_start(name, **kw)


@router.post("/sandbox/runs/{run_id}/stop")
def sandbox_run_stop(run_id: str):
    """Stop the live fit named here (the STOP flag execute polls)."""
    model = ""
    try:
        d = sandbox_mod.run_dir(run_id)
        model = sandbox_mod.results(d)["meta"].get("model", "")
        with _engine_lock:
            live = _sandbox_status.get("running") == run_id
        if live:
            sandbox_mod.stop(d)
            _flash(f"Stopping sandbox run {run_id} at the next safe point.",
                   "ok")
        else:
            _flash(f"Nothing to stop: sandbox run {run_id} is not fitting.",
                   "warn")
    except Exception as e:
        _not_done("Not stopped", e)
    return _sandbox_redirect(model, run_id if model else "")


@router.post("/sandbox/stop")
def sandbox_stop(request: Request, experiment: str = Form("")):
    """Stop whatever the sandbox has on the engine (the guard modal's
    Stop, posted with no body): the live fit, a run still being prepared,
    or the live experiment (its claim's cancel, checked before every week,
    and STOP in its folder, which the replay polls between fits). An
    experiment's page posts experiment=<id>: that experiment alone is
    stopped, never a fit; its Stop says what it did (JSON when asked), and
    also reaches a folder another process replays."""
    with _engine_lock:
        running = None if experiment else _sandbox_status.get("running")
        if (not experiment and not running
                and _sandbox_status.get("claim")):
            _sandbox_status["cancel"] = True
        claim = _sandbox_status.get("experiment")
        eid = experiment or (claim or {}).get("id") or ""
        ours = bool(claim) and claim["id"] == eid
        if ours:
            claim["cancel"] = True
    if running:
        try:
            sandbox_mod.stop(sandbox_mod.run_dir(running))
        except Exception:
            pass
    asked, folder = ours, None
    if eid:
        from app.core import experiments as X
        from app.core import retro
        folder = X.find(eid)
        if folder is not None and (ours or X.status(folder)["status"]
                                   in retro.ACTIVE_STATUSES):
            retro.request_stop(folder)      # never creates a folder
            asked = True
    if not experiment:
        return _sandbox_redirect()
    to = (f"/sandbox/experiments/{eid}" if folder is not None or ours
          else "/sandbox")
    if asked:
        return _experiment_answer(
            _wants_json(request), ok=True, eid=eid, to=to,
            text=f"Stopping {eid} after the fits in flight; finished weeks "
            "are kept.")
    return _experiment_answer(_wants_json(request), ok=False, eid=eid,
                              text=f"Nothing to stop: {eid} is not "
                              "replaying.", kind="warn", to=to)


# ------------------------------------- the diagram API and the run poll

@router.get("/api/sandbox/models/{name}/contactmap")
def api_sandbox_contactmap(name: str):
    """The model's diagrams: "flow", the rules as arrows between molecule
    types (read from the text, no BNG2.pl), and the contact map BNG2.pl's
    visualize action draws on a copy of the model (no engine, no run).
    "sites": any molecule with components, the only models whose contact
    map and network say more than the flow. BNG2.pl's words come back as
    "error" beside the flow. Cached by the model text until it changes. A
    model that keeps placeholders is drawn with the sample values in them
    (sandbox_data.filled_bngl; no value reaches a drawing)."""
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
        cm = contactmap.parse(contactmap.graphml_from_bngl(
            sandbox_mod.filled_bngl(name, files, sample=True)[0], work))
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
    Cached by the model text until it changes; a model that keeps
    placeholders is generated with the sample values in them."""
    from app.core import contactmap
    try:
        files = sandbox_mod.read_model(name)
        bngl = files["model.bngl"]
        hit = sandbox_mod.cached_view(name, "network", bngl)
        if hit is not None:
            return hit
        work = sandbox_mod.SANDBOX / "contactmap" / sandbox_mod.check_name(name)
        net = contactmap.parse_net(contactmap.network_from_bngl(
            sandbox_mod.filled_bngl(name, files, sample=True)[0], work))
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


def _json_finite(obj):
    """obj with every NaN or infinite float as None: JSON has no NaN, and
    a data.exp row written NaN (a missing week) or an all-NaN trajectory
    column would otherwise fail the response."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_finite(v) for v in obj]
    return obj


@router.get("/api/sandbox/runs/{run_id}")
def api_sandbox_run(run_id: str):
    try:
        res = sandbox_mod.results(sandbox_mod.run_dir(run_id),
                                  live=_sandbox_status.get("running"))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return _json_finite(res)


# ----------------------------------------------------------- downloads

def _sandbox_same_origin_get(request: Request) -> bool:
    """A download GET whose Origin, when sent, names localhost. The
    middleware (shared._same_host_guard) already refuses a foreign Host on
    every request but checks Origin only on POST/PUT/DELETE; a model or a
    run is the user's own files, so a download also refuses a foreign
    Origin."""
    origin = request.headers.get("origin")
    return origin is None or _authority_hostname(origin) in _LOCAL_HOSTNAMES


def _sandbox_zip(data: bytes, filename: str):
    from fastapi.responses import Response
    return Response(data, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store"})


@router.get("/sandbox/models/{name}/download")
def sandbox_model_download(request: Request, name: str):
    """The model's three files and sidecars as a zip."""
    if not _sandbox_same_origin_get(request):
        return PlainTextResponse("Refused: not a localhost request.\n",
                                 status_code=403)
    try:
        return _sandbox_zip(sandbox_mod.model_zip(name), f"{name}.zip")
    except Exception as e:
        return PlainTextResponse(f"{e}\n", status_code=404)


@router.get("/sandbox/runs/{run_id}/download")
def sandbox_run_download(request: Request, run_id: str):
    """A run's inputs, engine outputs and summary.csv as a zip."""
    if not _sandbox_same_origin_get(request):
        return PlainTextResponse("Refused: not a localhost request.\n",
                                 status_code=403)
    try:
        return _sandbox_zip(sandbox_mod.run_zip(run_id), f"{run_id}.zip")
    except Exception as e:
        return PlainTextResponse(f"{e}\n", status_code=404)


# ----------------------------------------------------- the Oracle step

@router.post("/sandbox/runs/{run_id}/oracle")
def sandbox_run_oracle(run_id: str, w: str = Form("")):
    """The production Oracle step on a finished run of an unedited Oracle
    SIHRS start, inside the run folder only (sandbox, not a submission):
    nothing reaches the ledger, the site, the archive or model-output."""
    model = ""
    try:
        model = str(sandbox_mod.results(sandbox_mod.run_dir(run_id))["meta"]
                    .get("model", ""))
        try:
            wv = float(w) if str(w).strip() else None
        except ValueError:
            raise sandbox_mod.SandboxError(f"w must be a number, not {w!r}")
        out = sandbox_mod.oracle_step(run_id, wv)
        _flash(f"Oracle step applied to {run_id} with w = {out['w']:g}.",
               "ok", detail="A sandbox result, not a submission.")
    except Exception as e:
        _not_done("Oracle step not applied", e)
    return _sandbox_redirect(model, run_id if model else "")


# --------------------------------------------------------- experiments
# One model replayed over one season at a preset size and compared with
# the shipped replay (app/core/experiments.py): the gallery's Experiments
# card starts one, its page shows it running, then its summary.json. It
# holds the engine through _sandbox_status["experiment"], so every guard
# that reads _sandbox_live_reason refuses while it replays; Stop is
# /sandbox/stop's. Its imports stay inside the functions: the core
# modules load pandas, which the server's import must not.

#: one scoring job per experiment: the segment end's, or a view's when
#: experiments.stale() names a reason; registered under _engine_lock with
#: the claim, so a Start and a scoring never write one folder at once
_experiment_scores: dict = {}
#: a view waits this long for its scoring job, as the season page waits
#: for its finalize (routes/retro.py _RESULTS_GRACE_S)
_SCORE_GRACE_S = 1.5

#: the Experiments form a refusal sends back (one-shot, read by the gallery)
_experiment_refused_form: dict = {}


async def _experiment_form(request: Request) -> dict:
    """Every posted field, its value stripped; a blank one is left out, so
    it takes its default. The Oracle step's on or off reads as true or
    false (any other word passes as text). A field sent twice is a list
    and a file None: experiments.validate refuses each in words
    (FIELD_TYPE), and a field the page lacks (particles=200) with
    FIELD_UNKNOWN, where Form() parameters would drop it unseen."""
    try:
        form = await request.form()
    except Exception:
        return {}
    words = {"on": True, "true": True, "1": True,
             "off": False, "false": False, "0": False}
    sent: dict = {}
    for k, v in form.multi_items():
        sent.setdefault(k, []).append(v.strip() if isinstance(v, str)
                                      else None)
    out = {}
    for k, vs in sent.items():
        if len(vs) > 1:
            out[k] = vs
        elif vs[0] is None:
            out[k] = None
        elif vs[0]:
            out[k] = (words.get(vs[0].lower(), vs[0]) if k == "oracle"
                      else vs[0])
    return out


def _experiment_answer(as_json: bool, *, ok: bool, eid, text: str,
                       kind: str = "ok", detail: str = "",
                       to: str = "/sandbox", codes=None, **extra):
    """An experiment action's answer: JSON when asked ({"ok", "id",
    "text"}, "codes" when given, and `extra`), never a flash (it would
    wait for the next page); else the notice, its detail in the "?", and
    a 303 to `to`."""
    if as_json:
        body = {"ok": ok, "id": eid, **extra, "text": text}
        if codes is not None:
            body["codes"] = list(codes)
        return JSONResponse(_json_finite(body))
    _flash(text, kind, detail=detail)
    return RedirectResponse(to, status_code=303)


def _experiment_start(raw: dict, as_json: bool):
    """Start (or resume) the experiment the four choices name: the
    settings read (nothing claimed or written on a refusal); one whose
    every week is stored answered as complete; the engine claimed under
    _engine_lock, refused (MACHINE) while any other run holds it or with
    no particle-filter engine here; the preflight (the plan, the bank,
    the engine build at a resume) outside the lock; a Stop meanwhile
    answered as a start that never began; then the replay on a
    background thread (_experiment_go), as the Sandbox starts a fit. A
    refusal goes back to the experiment's page when it has one, else to
    the gallery, whose form comes back as posted."""
    from app.core import experiments as X
    from app.core.problem_codes import Refusal, finding
    eid = None

    def refused(found):
        found = ([f for f in found if f["tier"] != "warning"]
                 + [f for f in found if f["tier"] == "warning"])
        said = [f"{f['text']} ({f['code']})" for f in found]
        to = (f"/sandbox/experiments/{eid}" if eid and X.find(eid)
              else "/sandbox")
        if as_json:
            return _experiment_answer(
                True, ok=False, eid=eid, text=f"Not started: {said[0]}.",
                codes=found, url=None, started=False)
        if to == "/sandbox":
            def posted(k, default=""):
                return raw.get(k) if isinstance(raw.get(k), str) else default
            oracle = raw.get("oracle")
            _experiment_refused_form["form"] = {
                "model": posted("model"), "season": posted("season"),
                "size": posted("size", X.DEFAULT_SIZE),
                "oracle": (oracle if isinstance(oracle, bool)
                           else posted("model") in X.ORACLE_ON_BY_DEFAULT)}
        # the problems first, each with its code; the rest in the "?"
        _not_done("Not started", sandbox_mod.SandboxError(
            "\n".join([said[0] + "."] + said[1:])))
        return RedirectResponse(to, status_code=303)

    try:
        s = X.read(raw)
        eid = X.experiment_id(s)
    except Refusal as e:
        return refused(e.findings)
    page = f"/sandbox/experiments/{eid}"

    def complete():
        return _experiment_answer(
            as_json, ok=True, eid=eid, kind="info", to=page, codes=[],
            text=f"{eid} is complete: every week is stored, nothing to fit.",
            url=page, started=False, resumed=False, complete=True)
    folder = X.find(eid)
    if folder is not None and X.status(folder)["complete"]:
        return complete()
    with _engine_lock:
        why = _sandbox_busy_reason()
        engine = "" if why else pipeline._pf_engine_state()
        claim = None
        if not why and engine == "ready":
            claim = {"id": eid, "settings": s, "cancel": False}
            _sandbox_status["experiment"] = claim
    if why:
        return refused([finding("MACHINE", f"{why}: one run at a time")])
    if claim is None:
        return refused([finding(
            "MACHINE", "an experiment needs the particle-filter engine, "
            + pipeline._pf_engine_missing(engine))])

    def release():
        with _engine_lock:
            if _sandbox_status.get("experiment") is claim:
                _sandbox_status["experiment"] = None
    try:
        p = X.preflight(s, retro_root=retro_seasons.RETRO_ROOT)
    except Refusal as e:
        release()
        return refused(e.findings)
    except Exception as e:                      # the computer, not the model
        release()
        return refused([finding("MACHINE", str(e)[:300])])
    if p["complete"]:
        release()
        return complete()
    # Stop pressed during the preflight: nothing started, nothing fitted
    with _engine_lock:
        cancelled = bool(claim.get("cancel"))
        if cancelled and _sandbox_status.get("experiment") is claim:
            _sandbox_status["experiment"] = None
    if cancelled:
        return _experiment_answer(
            as_json, ok=False, eid=eid, kind="warn", codes=[],
            text=f"{eid} was stopped before it started.",
            to=page if X.find(eid) else "/sandbox", url=None, started=False)
    threading.Thread(target=_experiment_go, args=(eid, s, claim),
                     daemon=True, name=f"experiment-{eid}").start()
    ref, weeks, done = p["reference"], len(p["weeks"]), p["weeks_done"]
    if p["resume"]:
        text = f"Resumed {eid}: {done} of {weeks} weeks were stored already."
    else:
        text = (f"Started {eid}: {weeks} weeks of {p['season']}, "
                f"{len(p['locations'])} locations.")
    notes = []
    if ref is not None:
        notes.append(f"Compared with the shipped replay of {p['season']} ("
                     + ("the Oracle SIHRS" if ref["member"] == "pf"
                        else "the Liu-West filter alone")
                     + ") on the cells both score.")
    else:
        # nothing to compare with leads; a resume's count goes to the "?"
        if p["resume"]:
            notes.append(f"{done} of {weeks} weeks were stored already.")
        text = (f"{'Resumed' if p['resume'] else 'Started'} {eid}; nothing "
                "to compare it with.")
    for f in p["findings"]:
        said = f"{f['text']} ({f['code']})"
        notes.append(said if f["code"] == "NO_REFERENCE"
                     else f"Worth a look: {said}")
    plan = {k: p[k] for k in ("model", "model_fingerprint", "experiment",
                              "season", "size", "oracle", "locations",
                              "weeks", "replicates", "particles")}
    plan["reference"] = None if ref is None else {
        "member": ref["member"], "root": X._repo_path(ref["root"]),
        "started_utc": ref["started_utc"]}
    return _experiment_answer(
        as_json, ok=True, eid=eid, text=text, to=page,
        kind="ok" if ref is not None else "warn", detail=" ".join(notes),
        codes=p["findings"], url=page, started=True, resumed=p["resume"],
        complete=False, plan=plan)


@router.post("/sandbox/experiments")
def sandbox_experiment_start(request: Request,
                             raw: dict = Depends(_experiment_form)):
    """Start or resume an experiment: model, season, and optionally size
    and oracle (on or off), the four choices the gallery's Experiments
    card offers, and nothing else. A 303 to its page, or JSON with
    Accept: application/json (always 200, as Check answers)."""
    return _experiment_start(raw, _wants_json(request))


def _experiment_go(eid: str, settings: dict, claim: dict) -> None:
    """One experiment segment on this console: the sleep guard held, a
    pending scoring of the folder waited for, the replay run, the claim
    released the moment it returns, then summary.json scored off the
    engine as the folder's one job."""
    from app.core import experiments as X
    from app.core import retro
    from app.core.problem_codes import Refusal
    folder = X.root() / eid
    guard = pipeline._sleep_guard()     # a full replay must outlive the lid
    before = X.finished_mark(folder)
    job = None
    try:
        pending = _experiment_scores.get(eid)
        if pending and not pending["done"].is_set():
            pending["done"].wait()      # a rescore of this folder ends first

        def cancelled():
            return bool(claim.get("cancel"))
        if not cancelled():
            X.replay(settings, retro_root=retro_seasons.RETRO_ROOT,
                     cancelled=cancelled)
    except (retro.SeasonStopped, retro.EngineBuildChanged):
        pass                            # the run record says stopped
    except retro.ResumeMismatch as e:   # and its other kinds
        _flash(f"{eid} was not resumed: "
               f"{sandbox_mod.split_reason(str(e))[0]}", "warn",
               detail="Delete the experiment on its page to replay it here.")
    except Refusal as e:                # the model changed since preflight
        f = e.findings[0]
        _flash(f"{eid} did not run: {f['text']} ({f['code']}).", "warn")
    except Exception as e:
        _flash(f"{eid} did not run: {str(e)[:200]}", "error")
    finally:
        if folder.is_dir():
            retro.clear_flags(folder)   # a leftover STOP would stop the next
        if guard is not None:
            try:
                guard.terminate()
            except Exception:
                pass
        with _engine_lock:
            if X.segment_ended(folder, before):
                job = _score_job(eid, "the segment ended", RUNNING_SHA)
            if _sandbox_status.get("experiment") is claim:
                _sandbox_status["experiment"] = None
        _invalidate_scans()
        if job:
            job["thread"].start()


def _score_job(eid: str, why: str, build: str | None) -> dict:
    """A new scoring job ({"why", "error", "done", "t0", "thread"}),
    registered, its thread not yet started. The caller holds _engine_lock
    and starts job["thread"] after releasing it. The thread runs
    experiments.score(root()/eid, retro_root=RETRO_ROOT,
    flubnf_build=build), keeps str(e)[:300] of any failure, invalidates
    the cached scans and sets done."""
    from app.core import experiments as X
    job = {"why": why, "error": "", "done": threading.Event(),
           "t0": time.time()}

    def _go():
        try:
            X.score(X.root() / eid, retro_root=retro_seasons.RETRO_ROOT,
                    flubnf_build=build)
        except Exception as e:
            job["error"] = str(e)[:300]
        finally:
            _invalidate_scans()
            job["done"].set()
    job["thread"] = threading.Thread(target=_go, daemon=True,
                                     name=f"experiment-score-{eid}")
    _experiment_scores[eid] = job
    return job


def _experiment_scoring(eid: str) -> dict | None:
    """A view's scoring: the job running for this experiment, else a new
    one (flubnf_build None: the build that ran is kept) when
    experiments.stale() names a reason and no claim here names eid; None
    when there is nothing to score. stale() is read before the lock."""
    from app.core import experiments as X
    job = _experiment_scores.get(eid)
    if job and not job["done"].is_set():
        return job
    folder = X.find(eid)
    why = X.stale(folder) if folder is not None else ""
    if not why:
        return None
    with _engine_lock:
        job = _experiment_scores.get(eid)
        if job and not job["done"].is_set():
            return job
        if _experiment_live() == eid:
            return None
        job = _score_job(eid, why, None)
    job["thread"].start()
    return job


def _experiment_line(st: dict, claimed: bool) -> str:
    """The running card's one line: starting, stopping, paused, or the
    week under way, its fits, the time so far and, once a week is timed,
    about how long is left; "" otherwise."""
    from app.core import retro
    state = st["status"]
    if claimed and state not in retro.ACTIVE_STATUSES:
        return "Starting…"
    so_far = f"{sandbox_mod.clock(st['elapsed_s'])} so far"
    if state == "stopping":
        return f"Stopping after the fits in flight · {so_far}"
    if state == "paused":
        return f"Paused · {so_far}"
    if state != "running":
        return ""
    line = (f"{st['week']}: {st['fits_done']} of {st['fits_total']} fits · "
            f"{so_far}" if st["week"] else so_far)
    if st["eta_s"] is not None:
        line += f" · about {sandbox_mod.clock(st['eta_s'])} left"
    return line


def _experiment_badge(st: dict, claimed: bool) -> tuple:
    """(state, words) of an experiment's badge: starting, running,
    stopping, paused, stopped or interrupted (with the weeks stored when
    not every one is), done, error, or not started."""
    from app.core import retro
    state = st["status"]
    part = ("" if st["complete"]
            else f" · {st['weeks_done']} of {st['weeks_total']} weeks")
    if claimed and state not in retro.ACTIVE_STATUSES:
        return ("pending", "starting")
    if state in ("running", "stopping"):
        return ("pending", state)
    if state == "paused":
        return ("warn", "paused")
    if state in ("stopped", "interrupted"):
        return ("warn", state + part)
    if state == "done":
        return ("ok", "done") if st["complete"] else ("warn", "done" + part)
    if state == "error":
        return ("error", "error")
    return ("neutral", state or "not started")


def _experiment_gallery() -> dict:
    """The Experiments card: the models a replay can name (each with its
    Oracle step default), the seasons newest first, the form's choices (a
    refused form as posted, one-shot; else the newest intact registered
    version, the season with a shipped replay to compare with, smoke and
    the model's Oracle default), and a row per experiment: its badge and
    its figures as last scored (never checked for staleness here)."""
    from app.core import experiments as X
    from app.core import library, retro
    models = [{**m, "oracle": m["ref"] in X.ORACLE_ON_BY_DEFAULT}
              for m in library.list_models()]
    pick = _experiment_refused_form.pop("form", None)
    if not pick:
        # the newest registration; of two in one second, the later listed
        mine = [m for m in reversed(models)
                if not m["shipped"] and m["intact"]]
        newest = max(mine, key=lambda m: str(m["registered_utc"] or ""),
                     default=None)
        ref = newest["ref"] if newest else "sihrs"
        pick = {"model": ref,
                "season": X.default_season(retro_seasons.RETRO_ROOT),
                "size": X.DEFAULT_SIZE,
                "oracle": ref in X.ORACLE_ON_BY_DEFAULT}
    live = _experiment_live()
    rows = [{"id": r["id"],
             "badge": _experiment_badge(r["status"], r["id"] == live),
             "fig": X.figures((r["summary"] or {}).get("overall"))}
            for r in X.list_experiments()]
    return {"models": models,
            "seasons": sorted(retro.available_seasons(), reverse=True),
            "pick": pick, "rows": rows}


def _experiment_view(eid: str) -> dict | None:
    """What an experiment's page and its JSON show, or None when eid names
    no experiment: its folder (find), or this console's claim alone while
    the preflight runs (no folder yet); its four choices; where its replay
    stands (status, with the claim over it: the line and the badge); its
    scoring (a view's rescore when stale() names a reason, waited for up
    to _SCORE_GRACE_S); and summary.json as read, every figure through
    experiments.figures."""
    from app.core import experiments as X
    from app.core import library, retro
    from app.core.problem_codes import Refusal
    from app.core.us_national import is_us
    folder = X.find(eid)
    with _engine_lock:
        claim = _sandbox_status.get("experiment")
    claimed = bool(claim) and claim["id"] == eid
    if folder is None and not claimed:
        return None
    try:
        settings = (X.read(folder / X.SETTINGS) if folder is not None
                    else dict(claim["settings"]))
    except Refusal:
        return None                             # changed since find
    st = X.status(X.root() / eid)
    live = claimed or st["status"] in retro.ACTIVE_STATUSES
    job = _experiment_scoring(eid) if folder is not None else None
    if job is not None:
        job["done"].wait(_SCORE_GRACE_S)
    pending = job is not None and not job["done"].is_set()
    scoring = {"pending": pending, "why": job["why"] if pending else "",
               "error": "" if pending or job is None else job["error"]}
    summary, problem = None, ""
    path = X.root() / eid / X.SUMMARY
    if folder is not None and path.is_file():
        try:
            summary = X.read_summary(path)
        except Refusal:                         # FORMAT_UNKNOWN
            try:
                v = json.loads(path.read_text(encoding="utf-8")).get(
                    "format_version")
            except (OSError, ValueError, AttributeError, RecursionError):
                v = None
            problem = (f"summary.json was written by a newer FluBNF "
                       f"(format_version {v}); this one reads "
                       f"{X.SUMMARY_VERSION} only."
                       if type(v) is int and v > X.SUMMARY_VERSION
                       else "summary.json cannot be read")
        except (OSError, ValueError, RecursionError):
            problem = "summary.json cannot be read"
    figs = words = None
    if summary is not None:
        def groups(key):
            g = summary.get(key)
            return [(k, X.figures(v)) for k, v in g.items()] if isinstance(
                g, dict) else []
        figs = {"overall": X.figures(summary.get("overall")),
                "us": X.figures(summary.get("us")),
                "by_location": groups("by_location"),
                "by_week": groups("by_week"),
                "by_horizon": groups("by_horizon")}
        ran = summary.get("ran") if isinstance(summary.get("ran"),
                                               dict) else {}
        try:
            disk = retro.human_bytes(int(ran.get("disk_bytes") or 0))
        except (TypeError, ValueError):
            disk = ""
        # US planned and a shipped side, yet no US compared: not like for
        # like (us_national.us_step_week), said in a line under the table
        words = {"disk": disk,
                 "engine": retro._build_label(ran.get("engine_build")),
                 "us_na": (isinstance(summary.get("shipped"), dict)
                           and summary.get("us") is None
                           and any(is_us(x) for x in
                                   ran.get("locations") or ()))}
    meta = X._meta(X.root() / eid)
    rs = meta.get("settings") if isinstance(meta.get("settings"),
                                            dict) else {}
    record = None
    if rs.get("experiment"):
        try:
            record = {"short": library.short(str(rs.get("model_fingerprint")
                                                 or "")),
                      "locations": len(rs.get("locations") or ()),
                      "weeks": len(rs.get("weeks") or ()),
                      "replicates": int(rs.get("replicates") or 0)}
        except (TypeError, ValueError):
            record = None
    return {"id": eid, "settings": settings, "folder": folder is not None,
            "claimed": claimed, "live": live, "status": st,
            "line": _experiment_line(st, claimed),
            "badge": _experiment_badge(st, claimed), "scoring": scoring,
            "summary": summary, "figures": figs, "problem": problem,
            "words": words, "record": record}


@router.get("/sandbox/experiments/{eid}", response_class=HTMLResponse)
def sandbox_experiment_page(request: Request, eid: str):
    """One experiment: its choices, its replay while it runs (the weeks,
    the line, Stop), its state and Resume, and its scores against the
    shipped replay, read from summary.json only (rescored first when
    stale() names a reason); Delete when it is idle."""
    view = _experiment_view(eid)
    if view is None:
        _flash(f"Not opened: no experiment is named '{eid}'.", "warn")
        return RedirectResponse("/sandbox", status_code=303)
    return templates.TemplateResponse(request, "sandbox_experiment.html",
                                      {"active": "Sandbox", **view})


@router.get("/api/sandbox/experiments/{eid}")
def api_sandbox_experiment(eid: str):
    """One experiment as JSON (its page's poll, and agents): its choices,
    live and claimed, status with the page's line, scoring, summary.json
    as read and its overall and US figures; 404 when unknown. A stale
    summary is rescored here as on the page."""
    view = _experiment_view(eid)
    if view is None:
        return JSONResponse({"error": f"no experiment is named '{eid}'"},
                            status_code=404)
    figs = view["figures"]
    return _json_finite({
        "id": eid, "settings": view["settings"], "live": view["live"],
        "claimed": view["claimed"],
        "status": {**view["status"], "line": view["line"]},
        "scoring": view["scoring"], "summary": view["summary"],
        "figures": (None if figs is None
                    else {"overall": figs["overall"], "us": figs["us"]}),
        "problem": view["problem"]})


@router.post("/sandbox/experiments/{eid}/delete")
def sandbox_experiment_delete(request: Request, eid: str,
                              confirm: str = Form("")):
    """Delete an experiment's folder (the library keeps the model); never
    while it replays or is being scored. The confirmation names it."""
    from app.core import experiments as X
    from app.core import retro
    as_json = _wants_json(request)
    back = f"/sandbox/experiments/{eid}"
    if confirm != eid:
        return _experiment_answer(
            as_json, ok=False, eid=eid, kind="warn", codes=[],
            text="Not deleted: the confirmation did not name the experiment.",
            to=back if X.find(eid) else "/sandbox")
    try:
        # under the lock, as a season tree is discarded: no Start or
        # scoring can claim the folder meanwhile
        with _engine_lock:
            job = _experiment_scores.get(eid)
            if job and not job["done"].is_set():
                raise sandbox_mod.SandboxError(
                    f"{eid} is being scored; delete it once that is done")
            n = X.delete(eid, live=_experiment_live())
            _experiment_scores.pop(eid, None)
    except Exception as e:
        if as_json:
            return _experiment_answer(
                True, ok=False, eid=eid, codes=[],
                text=f"Not deleted: {sandbox_mod.split_reason(str(e))[0]}")
        _not_done("Not deleted", e)
        return RedirectResponse(back if X.find(eid) else "/sandbox",
                                status_code=303)
    _invalidate_scans()
    return _experiment_answer(
        as_json, ok=True, eid=eid, to="/sandbox", freed=n,
        text=f"Deleted {eid}; {retro.human_bytes(n)} freed.")


# ---------------------------------------------------- the Storage line

def _sandbox_storage_line() -> dict:
    """The Storage panel's read-only sandbox line (kept out of its total:
    the sandbox's runs are deleted from the sandbox, not from there)."""
    from app.core import retro
    try:
        s = sandbox_mod.storage()
    except Exception:
        return {}
    return {**s, "size_h": retro.human_bytes(s["bytes"])} if s["bytes"] else {}
