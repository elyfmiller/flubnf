"""Forecast (GET /forecast): the form, POST /run and the builders of its
spec, the stop button, the run pages and the forecast APIs.

POST /run (run_models) validates the form and the model settings, claims
the engine under _engine_lock and schedules pipeline._run_all. The run
pages (GET /runs/{id}, its report and download) read a run's files and
report through routes/output.py; POST /runs/{id}/rerun re-enters
run_models with the recorded spec. GET /api/series feeds the data panel,
GET /api/progress the progress bar. An APIRouter server.py includes after
storage's, so POST /runs/clear stays ahead of GET /runs/{run_id}.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core import runs as _runs
from app.core.runs import (Ledger, RunSpec, results_html, results_tip,
                           spec_settings, version_pairs)
from app.ui import pipeline, retro_seasons, shared, state, templating
from app.ui.forms import (_default_forecast_date, _gap_form, _int_field,
                          _knob_form, _knob_panel, _knob_raw, _knobs,
                          _str_field, resolve_anchor)
from app.ui.retro_seasons import _RETRO_ACTIVE, _season_status
from app.ui.routes import data as data_routes
from app.ui.routes import output as output_routes
from app.ui.shared import (_back, _console_elapsed, _flash,
                           _invalidate_scans, _outcome_chips, _run_label,
                           _sandbox_live_reason)
from app.ui.state import ENGINES, _engine_lock, _last_form, _status
from app.ui.templating import (_member_colors, _script_json, _season_colors,
                               templates)

router = APIRouter()


#: Statuses offered the one-click re-run. Console fits hold no checkpoint, so
#: it is a FRESH run with the recorded settings (never worded "resume").
RERUN_STATUSES = ("stopped", "error", "failed", "interrupted", "partial")


# === Forecast (/forecast) -> forecast.html ===
@router.get("/forecast", response_class=HTMLResponse)
def forecast_page(request: Request, source: str = "", tab: str = ""):
    # a custom dataset as the data source: opt-in per page (app/ui/datasets_ui.py).
    # tab=own is the "Your data" tab: the first stored dataset, or with none
    # the upload box alone
    from app.ui import datasets_ui as _dsu
    own_tab = tab == "own" and not source
    if own_tab:
        first = _dsu.choices()
        if first:
            return RedirectResponse(f"/forecast?source={first[0][0]}",
                                    status_code=303)
    if source:
        ds = _dsu.get_dataset(source)
        if ds is not None:
            return _dsu.forecast_page(request, ds)
        _flash("That dataset is not stored; showing the FluSight hub.")
    import pandas as pd
    from flubnf.settings import load_locations
    # a missing state list must be visible: without it runs cover all 52
    locations_error = ""
    try:
        _l = load_locations()
        all_locs = list(_l.location_name[(_l.location.str.len() == 2)
                                         & (_l.abbreviation != "US")])
    except Exception as e:
        all_locs = []
        locations_error = (f"State list unavailable ({type(e).__name__}); "
                           "runs will cover all 53 jurisdictions.")
    # the default run is the full hub submission: "all" is the 53, the 52
    # jurisdictions AND US national (US stays ticked with it, so a custom
    # pick starts with US in; the user unticks it to leave it out)
    form = dict(_last_form) or {"forecast_date": _default_forecast_date(),
                                "locations": ["all"],
                                "engine": "all",
                                "weeks_to_drop": 0, "weeks_to_nowcast": 0,
                                "replicates": 3, "members": 2, "season_start": ""}
    rid, res = shared._latest_results()
    # data panel: latest-vintage series for the selected locations (visible
    # before any run); seeded with US national, the panel's default
    import json as _json
    from app.core import us_national as _usn
    sel = [US_CHOICE] + [l for l in form["locations"]
                         if l != "all" and not _usn.is_us(l)]
    us_checked = any(_usn.is_us(l) or str(l).lower() == "all"
                     for l in form["locations"] or [])
    series = {}
    try:
        tdf = data_routes._vintage_frame(str(state.data_mod.newest_path()))
        n2f_ = dict(zip(_l.location_name, _l.location.str.zfill(2)))
        n2f_["US (national)"] = "US"
        for loc in sel[:8]:
            g = tdf[tdf.location == n2f_.get(loc, "")].sort_values("date")
            g = g[pd.to_numeric(g.value, errors="coerce").notna()]
            series[loc] = {"dates": [str(d)[:10] for d in g.date],
                           "values": [float(v) for v in g.value]}
    except Exception:
        pass
    fanq = {}
    # fans: the latest STORED run's models (no session gate: they survive a
    # restart; the card title names the run's date)
    if res:
        for mname, md in res["models"].items():
            good = {loc: qs for loc, qs in md.items()
                    if all(isinstance(v, dict) for v in qs.values())}
            if good:
                fanq[mname] = good
        # the shipped models only: a legacy run's retired blend is not drawn
        from app.core.report_v2 import toggle_models
        fanq = {m: fanq[m] for m in toggle_models(fanq)}
    # the FluSight hub's own forecasts for the same week (a vintage run's
    # comparison; none recorded = no toggle)
    official = _official_overlay(
        (res or {}).get("forecast_date", ""),
        sorted({l for qs in fanq.values() for l in qs}))
    # the hub view's latest-run card never shows a run on a custom dataset
    # (filtered in the query: many dataset runs never hide the hub's)
    ledger_rows = Ledger().rows(5, hub_only=True)
    for r in ledger_rows:
        r["label"] = _run_label(r["run_id"], r.get("spec", ""))
        r["modified"] = _runs.is_modified(r.get("spec", ""))
        r["chips"] = _outcome_chips(r.get("outcome", ""))
        r["settings"] = spec_settings(r.get("spec", ""), r.get("outcome", ""))
        # the latest-run card links the weekly report when one exists
        try:
            r["has_report"] = bool(_json.loads(r.get("outcome")
                                               or "{}").get("report"))
        except Exception:
            r["has_report"] = False
        if r["status"] == "running" and not (_status.get("running") or "").endswith(r["run_id"]):
            r["status"] = "interrupted"
    # archived Saturdays, newest first, for the form's picker (the native
    # date popup fails in some webviews); str() because the list is
    # serialised into the page and date objects would break the render
    try:
        vintage_dates = [str(v) for v in
                         reversed(state.data_mod.available_weeks())]
    except Exception:
        vintage_dates = []
    # the live file's newest week when the archive does not hold it yet: a
    # real-time run reads target-data directly (the anchor line says so)
    try:
        _vs = set(state.data_mod.vintages())
        live_only = next((v for v in vintage_dates[:1] if v not in _vs), "")
    except Exception:
        live_only = ""
    # ascending, as resolve_anchor reads it (the picker lists newest first)
    _anchor, _ = resolve_anchor(form.get("forecast_date", ""),
                                sorted(vintage_dates))
    anchor_note = ((f"Anchor week: {_anchor}"
                    + (LIVE_ONLY_NOTE if _anchor == live_only else ".")
                    ) if _anchor else "No archived week on or before that date.")
    # the newest week's reporting, under the anchor line while the anchor
    # is that week (the Data tab's check, app/core/reported.py)
    from app.ui.routes.data import _newest_report
    newest_report = _newest_report()
    # the per-state choices for that week (the Data issues box)
    data_issues, data_issues_sha = _data_issues_context(newest_report, form)
    return templates.TemplateResponse(request, "forecast.html", {
        "active": "Forecast", "engines": ENGINES, "status": _status,
        "ledger": ledger_rows, "all_locs": all_locs,
        "vintage_dates": vintage_dates, "anchor_note": anchor_note,
        "newest_report": newest_report, "anchor_week": _anchor or "",
        "data_issues": data_issues, "data_issues_sha": data_issues_sha,
        "live_only": live_only, "live_only_note": LIVE_ONLY_NOTE,
        "default_date": _default_forecast_date(),
        "locations_error": locations_error, "form": form,
        "us_choice": US_CHOICE, "us_checked": us_checked,
        "official_json": _script_json(official),
        "knob_panel": _knob_panel("forecast", form),
        "elapsed0": _console_elapsed(),
        "series_json": _script_json(series), "fanq_json": _script_json(fanq),
        "model_names_json": _script_json(templating._model_names()),
        "member_colors_json": _script_json(_member_colors()),
        "season_colors_json": _script_json(_season_colors()),
        "run_obs_json": _script_json((res or {}).get("observed", {})),
        "fc_date": (res or {}).get("forecast_date", ""),
        "dataset": None, "source_choices": _dsu.choices(), "own_tab": own_tab})


#: the national checkbox's value (the data panel's name for the series)
US_CHOICE = "US (national)"


# === The Data issues box (app/core/reported.py, app/core/missing.py) ===

#: the "Apply to all zero states" select's labels, one per choice
_ALL_TEXT = {"abstain": "Groundhog: no forecast",
             "level": "Groundhog: level (mean of last 4 weeks)",
             "extend": "Groundhog: extend the last positive week",
             "blend": "Groundhog: blend of level and extend",
             "set_aside": "Both models from the week before",
             "omit": "Leave out of both files"}


def _source_sha(week: str) -> str:
    """The sha256 of the file a real-time run anchored on `week` reads;
    "" when it cannot be read."""
    try:
        path, _kind = state.data_mod.observed_source(week, "realtime")
        return state.data_mod.file_sha256(path)
    except Exception:
        return ""


def _data_issues_context(rep, form) -> tuple:
    """(the Data issues box's context, the data file's sha256) for the
    Forecast form, or (None, "") when the newest week has no zero,
    collapsed or unreported state (the green line stays). `form` (the last
    form) may hold data_choices = {week: {fips: choice}} to preselect."""
    if rep is None or rep.clean:
        return None, ""
    from app.core import missing as MS
    from app.core import reported as _rep
    rows = _rep.box_rows(rep)
    prior = ((form or {}).get("data_choices") or {}).get(rep.week) or {}
    facts = " ".join(f for f, on in ((_rep.ZERO_FACT, rep.zeros),
                                     (_rep.COLLAPSED_FACT, rep.collapsed)) if on)
    zero_opts = {v for r in rows if r["issue"] == "zero" for v, _ in r["options"]}
    all_options = [(c, _ALL_TEXT[c]) for c in MS.ZERO_CHOICES if c in zero_opts]
    return ({"week": rep.week, "rows": rows, "prior": prior, "facts": facts,
             "all_options": all_options}, _source_sha(rep.week))


def _data_choices(forecast_date: str, newest, engine: str, locs: list,
                  gap_fields: dict, nd: dict, prior=None) -> tuple:
    """The per-state choices of a run: (the data_choices record or None,
    the location list with the states left out removed, a refusal or "").

    `gap_fields` are the box's gap.<fips> values (gap._sha the file they
    were made on); `prior` a recorded data_choices (a re-run) whose states
    supply a choice where the form gives none. The real-time week only
    (v1): on an older week a prior record for that week passes through
    verbatim (the engines match its set-asides against the data) and the
    form's fields are ignored. Refuses when the data changed since the box
    was built, when a choice is not one the state was offered, and when a
    zero state has no choice while the Groundhog runs without the
    run-wide rule (groundhog.zero_anchor)."""
    from app.core import missing as MS
    from app.core import reported as _rep
    locs = list(locs)
    if not newest or forecast_date != newest:
        if isinstance(prior, dict) and prior.get("week") == forecast_date \
                and prior.get("states"):
            omitted = {l for l, st in prior["states"].items()
                       if str((st or {}).get("choice")) == "omit"}
            return prior, [l for l in locs if l not in omitted], ""
        return None, locs, ""
    rep = data_routes._newest_report()
    if rep is None or rep.clean:
        return None, locs, ""
    gap_fields = dict(gap_fields or {})
    sha = _source_sha(rep.week)
    posted = gap_fields.pop("_sha", "")
    if posted and sha and posted != sha:
        return None, locs, (
            "The hub data changed since the Forecast tab was loaded, so the "
            "choices in Data issues may no longer fit it. Reload the tab and "
            "choose again.")
    prior_states = (prior or {}).get("states") if isinstance(prior, dict) else {}
    prior_states = prior_states if isinstance(prior_states, dict) else {}
    rows = {r["fips"]: r for r in _rep.box_rows(rep)}
    groundhog = engine in ("all", "analogue")
    knob = MS.zero_anchor_of({"knobs": nd})
    states, missing = {}, []
    in_run = set(locs)
    for g in rep.gaps:
        if g.location not in in_run:
            continue
        r = rows[g.fips]
        offered = dict(r["options"])
        choice = gap_fields.get(g.fips)
        if choice is None:
            choice = str((prior_states.get(g.location) or {}).get("choice")
                         or "")
        if choice and choice not in offered:
            return None, locs, (f"Data issues: {g.location}: '{choice}' is "
                                f"not one of {', '.join(offered)}.")
        if not choice:
            if g.reason == "zero" and groundhog and not knob:
                missing.append(g.location)
            continue                 # the default (keep, carry) or the knob
        if choice == r["default"]:
            continue                 # a default choice is not recorded
        entry = {"issue": g.reason, "what": g.what(), "choice": choice,
                 "week": rep.week,
                 "reported": (r["aside"] if choice == "set_aside"
                              else r["reported"])}
        if choice == "set_aside":
            aside = {w for w, _ in r["aside"]}
            before = [w for w, _ in r["reported"] if w not in aside]
            entry["from_week"] = before[-1] if before else ""
        elif choice in MS.ZERO_ANCHOR_RULES:
            entry["from_week"] = rep.week
        states[g.location] = entry
    if missing:
        n = len(missing)
        return None, locs, (f"{n} state{'s' if n != 1 else ''} read 0 for "
                            f"{rep.week}; choose what the Groundhog does "
                            "with each in Data issues.")
    omitted = {l for l, st in states.items() if st["choice"] == "omit"}
    kept = [l for l in locs if l not in omitted]
    if not states:
        return None, kept, ""
    return {"week": rep.week, "source_sha256": sha, "states": states}, kept, ""


def _location_list(locations: list) -> list:
    """The run's location names from the form's list: "all" is the hub's
    53 (the 52 jurisdictions and US national, fitted directly); a custom
    pick fits US only when it is ticked."""
    from app.core import us_national as _usn
    picked = _usn.state_names(locations)
    want_all = "all" in [l.lower() for l in picked]
    want_us = want_all or any(_usn.is_us(l) for l in locations)
    if want_all:
        _l = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
        locs_list = list(_l.location_name[(_l.location.str.len() == 2)
                                          & (_l.abbreviation != "US")])
    else:
        locs_list = list(picked)
    if want_us:
        # a re-run keeps its recorded spelling; the form's box becomes "US"
        spelled = ([l for l in locations if _usn.is_us(l)] or ["US"])[0]
        locs_list.append("US" if spelled == US_CHOICE else spelled)
    return locs_list

#: the anchor line's ending for a week only the live target file holds
LIVE_ONLY_NOTE = " (new data, not archived yet: read from target-data)."


def _official_overlay(fc_date: str, locs: list) -> dict:
    """{model: {loc: {h: {level: value}}}}: FluSight-ensemble's and
    FluSight-baseline's recorded forecasts for a run's forecast date, keyed
    like the run's own fans (physical horizons "1".."4", string levels).

    The Retrospective's reader (playback._official_quantiles, the frozen
    join reference_date = forecast date + 7); {} when the date has no hub
    file, the clone lacks model-output, or anything fails to parse."""
    if not fc_date or not locs:
        return {}
    try:
        from app.core import playback
        from app.core import us_national as _usn
        from flubnf.settings import load_locations
        present = playback._official_files_present(fc_date)
        if not present:
            return {}
        _l = load_locations()
        n2f = dict(zip(_l.location_name, _l.location.str.zfill(2)))
        f2n = {}
        for name in locs:
            fips = "US" if _usn.is_us(name) else n2f.get(name)
            if fips:
                f2n[fips] = name
        out = {}
        for model in present:
            q = playback._official_quantiles(model, fc_date, f2n) or {}
            got = {loc: {str(int(h) + 1): {str(lv): float(v)
                                          for lv, v in lvls.items()}
                         for h, lvls in hs.items()}
                   for loc, hs in q.items() if hs}
            if got:
                out[model] = got
        return out
    except Exception:
        return {}


# === Console controls: /run/stop (the rest: routes/shell.py, data.py) ===
@router.post("/run/stop")
def run_stop():
    _invalidate_scans()
    with _engine_lock:
        w = _status.get("workroot")
        running = _status.get("running") or ""
        if running and not w:
            # still starting (no workroot yet): the worker reads this once
            # it has one and ends the run as stopped before any fit; the
            # claim is kept until the run really ends
            _status["stop_requested"] = True
            _status["phase"] = "stopping…"
    if w and running:
        (Path(w) / "STOP").touch()
        if (Path(w) / "pf2s").is_dir():        # the two-strain pass polls its
            (Path(w) / "pf2s" / "STOP").touch()  # own subdir for the flag
        _status["phase"] = "stopping…"
    return RedirectResponse("/forecast#results", status_code=303)


# === Run pages (/runs/{id}, report, download, rerun) -> run.html ===
@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: str):
    import json as _json
    from app.core.runs import APP_STATE, Ledger
    import html as _html
    w = APP_STATE / "workroots" / run_id
    # an unknown id (no ledger row, no workroot) is a 404, never an empty
    # run page; "." and ".." never name a run
    if run_id in (".", "..") or not (Ledger().row(run_id) or w.is_dir()):
        return HTMLResponse(
            f"<!doctype html><title>No such run</title><p>No run "
            f"<code>{_html.escape(run_id)}</code> is recorded here. "
            "<a href=\"/runs\">Storage</a> lists the runs.</p>",
            status_code=404)
    res = {}
    if (w / "results.json").is_file():
        res = _json.loads((w / "results.json").read_text())
    subs = output_routes._submission_files(w)
    report = (w / "report.html").name if (w / "report.html").is_file() else None
    status, err, spec_json = "", "", ""
    o = {}
    sub_errors: dict = {}
    pf_failures: dict = {}
    step_errors: dict = {}
    ens_analogue_only: list = []
    ens_withheld = ""
    row_sha, row_engine_versions = "", {}
    # the run's own row, however many runs came after it
    r = Ledger().row(run_id)
    if r:
        status = r.get("status", "")
        spec_json = r.get("spec", "") or ""
        row_sha = r.get("flubnf_sha", "") or ""
        try:
            ev = _json.loads(r.get("engine_versions") or "{}")
            row_engine_versions = ev if isinstance(ev, dict) else {}
        except Exception:
            row_engine_versions = {}
        try:
            o = _json.loads(r.get("outcome") or "{}")
            err = o.get("error", "")
            sub_errors = o.get("submission_errors", {}) or {}
            # failures and step errors in full (the chips only count them)
            pf_failures = o.get("pf_failures", {}) or {}
            step_errors = {k: str(o[k]) for k in
                           ("score_error", "archive_error",
                            "report_inputs_error", "report_error")
                           if o.get(k)}
        except Exception:
            err = ""
    # each file's location coverage and why any location is missing
    if not res.get("dataset"):
        output_routes._attach_coverage(subs, o, spec_json or res.get("spec"))
    # a 'running' row with no live worker = the app was closed mid-run
    if status == "running" and not (_status.get("running") or "").endswith(run_id):
        status = "interrupted"
    # settings, build and engine versions all from the ledger row: "Produced
    # by" must never print this process's build. Names-only engine_versions
    # rows yield an app-build-only block (version_pairs omits unknowns).
    from app.core.runs import is_research
    dsx = {}
    if res.get("dataset"):
        # a run on a custom dataset: exports (never submissions) and fans;
        # (its data is the upload's; shared._same_host_guard keeps it local)
        from app.ui import datasets_ui as _dsu
        dsx = _dsu.run_page_extra(w, res)
    return templates.TemplateResponse(request, "run.html", {
        **dsx,
        "active": "Storage", "run_id": run_id, "status": status, "error": err,
        "results": results_html(o, spec_json, heading=False),
        "results_tip": results_tip(spec_json),
        # the page shows a research badge, so the label stays untagged
        "label": _run_label(run_id, spec_json, tag=False),
        "research": is_research(spec_json),
        "modified": _runs.is_modified(spec_json),
        "override": _knobs.override_reason(spec_json),
        # a legacy run's retired blend is not shown
        # a model that fitted no location (the PF in a Groundhog-only run)
        # gets no empty table
        "models": {m: v for m, v in (res.get("models") or {}).items()
                   if v and m not in _report_v2_retired()},
        "settings": spec_settings(spec_json, o),
        "versions": version_pairs(row_sha, row_engine_versions),
        "can_rerun": (bool(spec_json) and status in RERUN_STATUSES
                      and not dsx),
        "pf_failures": pf_failures, "step_errors": step_errors,
        # a refusal recorded under a retired hub name reads as its model
        "subs": subs,
        "sub_errors": {output_routes.model_display(m, w): why
                       for m, why in sub_errors.items()},
        "report": report})


@router.get("/runs/{run_id}/report", response_class=HTMLResponse)
def run_report(run_id: str):
    from app.core.runs import APP_STATE
    d = APP_STATE / "workroots" / run_id
    if not (d / "report.html").is_file():
        return HTMLResponse("<p>no report for this run</p>")
    # rebuilt if stale, as /output/report
    return HTMLResponse(output_routes._report_for_serving(d))


@router.get("/runs/{run_id}/report/download")
def run_report_download(run_id: str):
    """Save this run's weekly report, named for the run's forecast date."""
    from app.core.runs import APP_STATE
    d = APP_STATE / "workroots" / run_id
    date = ""
    try:
        import json as _json
        date = _json.loads((d / "results.json").read_text()).get(
            "forecast_date", "")
    except Exception:
        pass                 # no results.json yet: fall back to the run id
    return output_routes._weekly_report_file(d, date or run_id)


@router.post("/runs/{run_id}/rerun")
def run_rerun(request: Request, background: BackgroundTasks, run_id: str):
    """Re-run a recorded console run: a FRESH run (no checkpoint) with the
    row's exact spec through the /run path (its vintage and busy checks);
    refuses if that path cannot reproduce the spec verbatim."""
    import json as _json
    from dataclasses import asdict as _asdict
    from datetime import date as _date
    row = Ledger().row(run_id)
    try:
        d = _json.loads((row or {}).get("spec") or "")
    except (ValueError, TypeError):
        d = None
    if not isinstance(d, dict) or not d.get("forecast_date"):
        _flash("That run's settings were not recorded, so it cannot be "
               "re-run from here. Set the run up on the Forecast form "
               "instead. Nothing was started.")
        return _back(request, "/forecast")
    members = 3 if (d.get("extra") or {}).get("members") == 3 else 2
    locs = [str(l) for l in (d.get("locations") or [])]
    # aux pools re-run their preset (name before the digest tag); none = bare
    _x = d.get("extra") if isinstance(d.get("extra"), dict) else {}
    aux = (str(_x.get("analogue_aux") or "").split("+", 1)[0]
           if _x.get("aux_pools") else "")
    # likewise a plain-filter row re-runs the plain filter
    oracle = "none" if str(_x.get("oracle") or "") == "none" else None
    # model knobs re-run from the row's own record; an override is never
    # inherited (a fresh decision each time), so it is left out of the
    # comparison and the re-run exports under the non-hub name
    _rec = _knobs.record_of(d)
    had_override = bool(_knobs.override_reason(d))
    if had_override:
        d["extra"].pop(_knobs.OVERRIDE_KEY, None)
    try:
        _nd = _knobs.from_record(_rec)
        _cx = _run_extra(members, _spec_mode(d),
                         _knobs.aux_choice(_nd, aux),
                         oracle)
        _knobs.write_extra(_nd, _cx)
        # the per-state data choices (app/core/missing.py) re-run as
        # recorded; the engines match each set-aside against the data
        _dc = _x.get("data_choices")
        if isinstance(_dc, dict) and _dc:
            _cx["data_choices"] = _dc
    except ValueError:
        _flash("This run's recorded model settings are not readable, so it "
               "cannot be re-run from here. Nothing was started.")
        return _back(request, "/forecast")
    # what /run would build, compared field by field with the stored spec
    candidate = RunSpec(
        engine=str(d.get("engine") or ""),
        forecast_date=str(d.get("forecast_date") or ""),
        season_start=str(d.get("season_start") or ""),
        locations=locs,
        weeks_to_drop=int(d.get("weeks_to_drop") or 0),
        weeks_to_nowcast=int(d.get("weeks_to_nowcast") or 0),
        # pre-nowcast-rule rows kept the same-day week: reproduce, not default
        drop_same_day=bool(d.get("drop_same_day", False)),
        replicates=int(d.get("replicates") or 3),
        particles=int(d.get("particles") or 10_000),
        jitter=float(d.get("jitter", RunSpec.jitter)),
        extra=_cx)
    # a row recorded before the mode existed reads as a real-time run
    if isinstance(d.get("extra"), dict):
        d["extra"].setdefault("mode", "realtime")
    else:
        d["extra"] = {"mode": "realtime"}
    recon = _asdict(candidate)
    off = [k for k in sorted(d) if recon.get(k) != d[k]]
    try:
        if _date.fromisoformat(candidate.forecast_date).weekday() != 5:
            off.append("forecast_date")   # /run would snap it: not verbatim
    except ValueError:
        off.append("forecast_date")
    if not (1_000 <= candidate.particles <= 100_000):
        off.append("particles")           # /run would refuse it
    if (candidate.jitter != RunSpec.jitter
            and "pf.jitter" not in _rec):
        off.append("jitter")              # only the knob channel sets it
    if off:
        _flash("This run's recorded settings cannot be reproduced from the "
               "console path (" + ", ".join(dict.fromkeys(off)) + " differ "
               "from what the form would run), so nothing was started. "
               "Re-run it from a script using its ledger row.")
        return _back(request, "/forecast")
    if had_override:
        _flash("The earlier run exported under the hub names by override; "
               "an override is never carried over, so this re-run's files "
               "carry the non-hub name.")
    return run_models(request, background,
                      forecast_date=candidate.forecast_date,
                      locations=locs,
                      weeks_to_drop=candidate.weeks_to_drop,
                      weeks_to_nowcast=candidate.weeks_to_nowcast,
                      replicates=candidate.replicates,
                      season_start=candidate.season_start,
                      engine=candidate.engine,
                      members=members,
                      particles=candidate.particles,
                      mode=_spec_mode(d),
                      drop_same_day=1 if candidate.drop_same_day else 0,
                      aux=aux, oracle=oracle,
                      knob_fields={},
                      knobs=(_json.dumps(_rec) if _rec else ""),
                      submit_modified="", modified_reason="",
                      gap_fields={},
                      data_choices=(_json.dumps(_cx["data_choices"])
                                    if _cx.get("data_choices") else ""))


# === Forecast APIs: /api/series, /api/progress ===
@router.get("/api/series")
def api_series(request: Request, locs: str = "", source: str = ""):
    """Data-panel series for the checked locations (live, before any run);
    `source` = a custom dataset's id (its groups' newest data)."""
    if source:
        from app.ui import datasets_ui as _dsu
        ds = _dsu.get_dataset(source)
        return _dsu.api_series(ds, locs) if ds is not None else {}
    import pandas as pd
    sel = [l for l in locs.split("|") if l][:8] or ["Ohio"]
    out = {}
    try:
        _l = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
        n2f_ = dict(zip(_l.location_name, _l.location.str.zfill(2)))
        n2f_["US (national)"] = "US"
        tdf = pd.read_csv(state.data_mod.newest_path(),
                          dtype={"location": str})
        tdf["location"] = tdf["location"].str.zfill(2)
        for loc in sel:
            g = tdf[tdf.location == n2f_.get(loc, "")].sort_values("date")
            g = g[pd.to_numeric(g.value, errors="coerce").notna()]
            out[loc] = {"dates": [str(d)[:10] for d in g.date],
                        "values": [float(v) for v in g.value]}
    except Exception:
        pass
    return out


@router.get("/api/progress")
def api_progress():
    import glob
    import json as _json
    import time as _time
    w = _status.get("workroot")
    out = {"running": bool(_status.get("running")),
           "phase": _status.get("phase", ""),
           "label": _status.get("run_label", ""),
           # anchors for the browser's own ticking clock
           "started_utc": _status.get("started_utc"),
           "elapsed_s": _console_elapsed(),
           # (label, value) pairs for a client that arrived mid-run
           "settings": list(_status.get("settings") or [])}
    if w:
        done = total = 0
        t0 = None
        # pf_status*.json.prog: the pre-shard merged name and per-shard files
        # (the workroot escaped: a Windows path may hold [ or ])
        ew = glob.escape(w)
        for f in (glob.glob(ew + "/pf_status*.json.prog")
                  + glob.glob(ew + "/pf2s/pf_status*.json.prog")):
            try:
                d = _json.loads(open(f).read())
                done += d["done"]; total += d["total"]
                t0 = min(t0 or d["t0"], d["t0"])
            except Exception:
                pass
        # stable denominator from the claim; shard totals grow toward it
        total = max(total, int(_status.get("expected_total") or 0))
        out["done"], out["total"] = done, total
        if done and total and t0:
            rate = (_time.time() - t0) / done
            out["eta_s"] = int(rate * (total - done))
    elif _status.get("expected_total"):
        # run claimed but workroot not created yet: report 0/N, not silence
        out["done"], out["total"] = 0, int(_status["expected_total"])
    return out


def _scope_label(locs) -> str:
    """The progress label's scope: '3 state(s)', '3 state(s) + US',
    'all 53 jurisdictions' (the form's "all": the 52 and US) or
    'US only'."""
    from app.core import us_national as _usn
    n = len(_usn.state_names(locs))
    us = len(locs) > n
    if not n:
        return "US only" if us else "0 state(s)"
    if n == 52 and us:
        return "all 53 jurisdictions"
    return f"{n} state(s)" + (" + US" if us else "")


def _run_extra(members: int, mode: str, aux: str | None = None,
               oracle: str | None = None) -> dict:
    """spec.extra for a console run: form mode, members=3 research flag,
    Groundhog aux pools (recorded in the spec so it replays), Oracle switch.

    aux: None = shipped (analogue.SHIPPED_AUX, digests recorded), a preset
    name, or "" = bare analogue (research; file withheld).
    oracle: None = shipped Oracle SIHRS, "none" = plain filter (research;
    file withheld); anything else raises."""
    from app.core.engines import analogue as _an
    mode = mode if mode in ("realtime", "vintage") else "realtime"
    extra = {"mode": mode}
    if members == 3:
        extra["members"] = 3
    name = _an.SHIPPED_AUX if aux is None else str(aux)
    if name:
        fn = _an.aux_preset(name)                # unknown name raises here
        extra["aux_pools"] = fn(None, 0, None)["aux_pools"]
        extra["analogue_aux"] = fn.__name__.split(":", 1)[1]
    if oracle is not None and str(oracle) != "":
        if str(oracle) != "none":
            raise ValueError(f"oracle must be 'none' (the plain filter, a "
                             f"research run) or absent, not {oracle!r}")
        extra["oracle"] = "none"
    return extra


def _knob_run_parts(kraw: dict, engine: str, forecast_date: str,
                    members: int, mode: str, aux, oracle, *, legacy: dict,
                    override: bool = False, reason: str = "") -> tuple:
    """(non-default knob values, spec.extra) for a console run; raises
    KnobError/ValueError on anything refused. Knobs that do not apply to
    the engine (or the Oracle step when it is off) are dropped, never
    recorded. No knob off shipped -> exactly today's extra."""
    eng = engine if engine in _knobs.ENGINE_MEMBERS else "all"
    step = str(oracle or "") != "none"
    nd = _knobs.resolve(kraw, eng, scope="forecast",
                        forecast_date=forecast_date, oracle_step=step,
                        legacy=legacy, two_strain=(members == 3))
    if "groundhog.aux" in nd and aux is not None:
        want = _knobs.aux_choice(nd, None)
        if str(aux) != want:
            raise _knobs.KnobError(
                f"groundhog.aux: the form gives two donor banks "
                f"({aux or 'none'} and {want or 'none'}); give one")
    if override and nd and not reason:
        raise _knobs.KnobError(
            "exporting under the hub names needs a reason; type one, or "
            "untick the box to export under the non-hub name")
    extra = _run_extra(members, mode, _knobs.aux_choice(nd, aux), oracle)
    _knobs.write_extra(nd, extra, override=(reason if override else ""))
    return nd, extra


def _spec_mode(d: dict) -> str:
    extra = d.get("extra") if isinstance(d.get("extra"), dict) else {}
    m = str(extra.get("mode") or "realtime")
    return m if m in ("realtime", "vintage") else "realtime"


def _report_v2_retired() -> tuple:
    """report_v2.RETIRED_MODELS, imported lazily (report_v2 pulls plotly)."""
    from app.core.report_v2 import RETIRED_MODELS
    return RETIRED_MODELS


# === Forecast: POST /run (form and rerun entry to _run_all) ===
@router.post("/run")
def run_models(request: Request,
               background: BackgroundTasks,
               forecast_date: str = Form(""),
               locations: list = Form([]),
               weeks_to_drop: int = Form(0),
               weeks_to_nowcast: int = Form(0),
               replicates: int = Form(3),
               engine: str = Form("all"),
               members: int = Form(2),
               particles: int = Form(10_000),
               season_start: str = Form(""),   # blank = Aug 1 of the season
               mode: str = Form("realtime"),   # recorded: vintage or real-time
               # re-run-only fields (not on the form): None/0 = today's
               # shipped config; /runs/{id}/rerun passes the row's values
               drop_same_day: int = Form(0),
               aux: str | None = Form(None),    # Groundhog donors; "" = bare
               oracle: str | None = Form(None),  # "none" = plain filter
               # the Model settings panel (app/core/knobs.py): knob.<key>
               # fields, or one JSON dict (the re-run path); the override
               # exports a modified run under the hub names, with a reason
               knob_fields: dict = Depends(_knob_form),
               knobs: str = Form(""),
               submit_modified: str = Form(""),
               modified_reason: str = Form(""),
               # the Data issues box (templates/_data_issues.html): gap.<fips>
               # fields, or the recorded data_choices JSON (the re-run path)
               gap_fields: dict = Depends(_gap_form),
               data_choices: str = Form("")):
    # non-Saturdays snap via resolve_anchor; a typed Saturday is honoured or
    # refused below (never re-aimed)
    from datetime import date as _date
    forecast_date = _str_field(forecast_date).strip()
    try:
        _d = _date.fromisoformat(forecast_date)
    except ValueError:
        # a blank or typed non-date (the model page's text field) is said
        # as such, never "no data for <text> yet"
        _flash(f"'{forecast_date}' is not a date; give one as YYYY-MM-DD. "
               "Nothing was run." if forecast_date else
               "Give a forecast date. Nothing was run.")
        return _back(request, "/forecast")
    typed_day = forecast_date
    if _d.weekday() != 5:
        # the form already shows this anchor; no banner
        _pick, _ = resolve_anchor(forecast_date)
        forecast_date = _pick or forecast_date
    # refused before any notice about the anchor or the settings
    if engine not in ENGINES:
        _flash(f"'{engine}' is not one of the available engines. "
               "Nothing was run.")
        return _back(request, "/forecast")
    # an unknown mode reads as the pill's default, so the anchor rule below
    # records what the run reads (never "realtime" on an archived week)
    mode = mode if mode in ("realtime", "vintage") else "realtime"
    # the newest week any hub file holds: a run anchored there is real-time
    # and may read the live target file (app.core.data.observed_source)
    try:
        newest = state.data_mod.newest_week()
    except Exception:
        newest = None
    try:
        state.data_mod.observed_source(
            forecast_date,
            "realtime" if forecast_date == newest else "vintage")
    except Exception as _src_err:
        live_wk = None
        try:
            live_wk = state.data_mod.live_newest_week()
        except Exception:
            pass
        if live_wk and forecast_date > live_wk:
            # the as-of is past every week the hub holds: no data yet
            if _last_form:
                _last_form["forecast_date"] = newest or live_wk
            _flash(f"No data for {forecast_date} yet: the hub's target data "
                   f"ends at {live_wk}. Update data on the Data tab, or "
                   f"forecast from {live_wk}. Nothing was run.")
            return _back(request, "/forecast")
        # archive gaps are real (holiday weeks): suggest the nearest EARLIER
        # vintage only; a later one would leak hindsight
        vs = state.data_mod.vintages()
        earlier = [v for v in vs if v <= forecast_date]
        near = max(earlier) if earlier else (min(vs) if vs else None)
        if near and _last_form:
            _last_form["forecast_date"] = near
        if not vs:
            _flash(f"No archived data for {forecast_date}. Pull the "
                   "FluSight hub on the Data tab first.")
        elif earlier:
            _flash(f"The FluSight hub archived no data snapshot dated "
                   f"{forecast_date}; such gaps are real, usually holiday "
                   "weeks. The graphs still show a point at that date "
                   "because they draw today's settled data, which was not "
                   "yet reported on the day itself. Nearest earlier "
                   f"archived Saturday: {near}. A later one would leak a "
                   "week of hindsight, so it is not offered.")
        else:
            _flash(f"No archived data for {forecast_date}; the archive "
                   f"starts at {near}.")
        return _back(request, "/forecast")
    # A direct call (rerun) may pass Form default objects: read them as blank
    season_start = _str_field(season_start).strip()
    # the page fills Season start with August 1 of the TYPED day's season;
    # when the day snapped back across August 1 (a September day anchors on
    # July's data) that fill is not a choice: the anchor's default applies
    from app.core.runs import default_season_start as _dss
    if (season_start and typed_day != forecast_date
            and season_start == _dss(typed_day)
            and season_start != _dss(forecast_date)):
        season_start = ""
    try:
        kraw = _knob_raw(knob_fields, knobs)
    except ValueError as e:                  # KnobError is a ValueError
        _flash(f"Model settings: {e}. Nothing was run.")
        return _back(request, "/forecast")
    override =_str_field(submit_modified).lower() in ("1", "on", "true", "yes")
    reason = _str_field(modified_reason).strip()
    _last_form.update({"forecast_date": forecast_date, "locations": locations,
                       "engine": engine, "weeks_to_drop": weeks_to_drop,
                       "weeks_to_nowcast": weeks_to_nowcast,
                       "replicates": replicates, "members": members,
                       "season_start": season_start,
                       "particles": particles,
                       "drop_same_day": _int_field(drop_same_day),
                       "knobs": {k: v for k, v in kraw.items()
                                 if isinstance(v, str)},
                       "submit_modified": override,
                       "modified_reason": reason})
    # the Data issues choices come back on the form, keyed by their week
    if isinstance(gap_fields, dict) and newest:
        _last_form["data_choices"] = {
            newest: {k: v for k, v in gap_fields.items()
                     if k != "_sha" and isinstance(v, str) and v}}
    # model settings, validated BEFORE the engine is claimed: a refusal
    # starts nothing. The legacy fields (season start, weeks to drop,
    # replicates, particles, same-day week) set their knob; a value outside
    # a knob's range is refused, never clamped.
    try:
        nd, extra = _knob_run_parts(
            kraw, engine, forecast_date, members, mode, aux, oracle,
            legacy={"particles": particles, "replicates": replicates,
                    "season_start": season_start,
                    "weeks_to_drop": weeks_to_drop,
                    "drop_same_day": bool(_int_field(drop_same_day))},
            override=override, reason=reason)
    except ValueError as e:                  # KnobError is a ValueError
        _flash(f"Model settings: {e}. Nothing was run.")
        return _back(request, "/forecast")
    kspec = _knobs.spec_fields(nd)
    season_start = kspec.get("season_start", "")
    weeks_to_drop = int(kspec.get("weeks_to_drop", 0))
    replicates = int(kspec.get("replicates", RunSpec.replicates))
    particles = int(kspec.get("particles", RunSpec.particles))
    # checkboxes arrive as a list, text inputs as comma-separated strings
    locations = [x.strip() for l in locations
                 for x in str(l).split(",") if x.strip()]
    if not locations:
        _flash("Select at least one location, or all 53 jurisdictions. "
               "Nothing was run.")
        return _back(request, "/forecast")
    try:
        locs_list = _location_list(locations)
    except Exception as e:
        _flash(f"The state list could not be read ({type(e).__name__}). "
               "Nothing was run.")
        return _back(request, "/forecast")
    # the per-state data choices (the Data issues box, or a re-run's
    # record): refused BEFORE the engine is claimed when a zero state has no
    # choice, when a choice is not one offered, or when the data changed
    import json as _json
    try:
        _prior = (_json.loads(data_choices)
                  if _str_field(data_choices).strip() else None)
        if _prior is not None and not isinstance(_prior, dict):
            raise ValueError("not a dictionary")
    except ValueError:
        _flash("The recorded data choices are not readable. Nothing was run.")
        return _back(request, "/forecast")
    _dc, locs_list, _why = _data_choices(forecast_date, newest, engine,
                                         locs_list, gap_fields, nd, _prior)
    if _why:
        _flash(f"{_why} Nothing was run.")
        return _back(request, "/forecast")
    if _dc:
        extra["data_choices"] = _dc
    if not locs_list:
        _flash("Every selected location was left out in Data issues. "
               "Nothing was run.")
        return _back(request, "/forecast")
    # busy check + claim under _engine_lock (see its comment)
    with _engine_lock:
        if _status.get("running"):
            _status["log"].append("A run is already in progress; not starting another.")
            return RedirectResponse("/forecast#results", status_code=303)
        live_retro = sorted(x for x in retro_seasons._known_seasons()
                            if _season_status(x) in _RETRO_ACTIVE)
        if live_retro:
            _flash("A retrospective replay holds the engine ("
                   + ", ".join(live_retro) + "). Stop or pause it from the "
                   "Retrospective tab first; nothing was run.")
            return _back(request, "/forecast")
        sb = _sandbox_live_reason()
        if sb:
            _flash(f"Not run: {sb}. Stop it from the Sandbox first.")
            return _back(request, "/forecast")
        # background tasks fire after the redirect: claim NOW so the landing
        # page shows the run
        _status["running"] = "starting"
        _status.pop("stop_requested", None)
        _invalidate_scans()
        _status["started_utc"] = __import__("time").time()
        _status["run_label"] = f"{forecast_date} · queued"
    queued = False
    try:
        _status["run_label"] = f"{forecast_date} · {_scope_label(locs_list)} · queued"
        # progress denominator known now (shards grow toward it); clear the old
        # workroot so its .prog files never show. The analogue alone gets none.
        _status["workroot"] = None
        _status["expected_total"] = (len(locs_list) * int(replicates)
                                     * (2 if members == 3 else 1)
                                     if engine in ("all", "pf") else None)
        # particles, replicates and weeks to drop were range-checked as knobs
        # above (refused, never clamped: replicates = 0 once ran zero fits)
        # mode follows the anchor: real-time means the newest week the hub
        # holds (the live target file's, when the archive has not caught up)
        if newest and mode == "realtime" and forecast_date != newest:
            mode = "vintage"
            extra["mode"] = mode
            _flash(f"Anchored on the archived week {forecast_date}, not the "
                   f"newest week ({newest}): recorded as a vintage run.")
        elif newest and forecast_date == newest and mode != "realtime":
            # the newest week IS real-time data whatever the pill said; recorded
            # so, which lets the run read the live file when it is not archived
            mode = "realtime"
            extra["mode"] = mode
        spec = RunSpec(engine=engine, forecast_date=forecast_date,
                       locations=locs_list,
                       season_start=season_start,
                       weeks_to_drop=weeks_to_drop,
                       weeks_to_nowcast=weeks_to_nowcast,
                       drop_same_day=bool(kspec.get("drop_same_day", False)),
                       replicates=replicates,
                       particles=particles,
                       **({"jitter": float(kspec["jitter"])}
                          if "jitter" in kspec else {}),
                       extra=extra)

        if engine in ("all", "pf", "analogue"):
            # 'analogue' = the same pipeline with the PF block skipped
            background.add_task(pipeline._run_all, spec)
            queued = True
        else:
            _flash(f"'{engine}' is not one of the available engines. "
                   "Nothing was run.")
    finally:
        if not queued:
            # nothing will run (unknown engine, or a failure before the
            # task was queued): release the claim rather than wedge the
            # console; Stop does not release a "starting" claim
            _status["running"] = None
            _status["run_label"] = ""
            _status["expected_total"] = None
            _status["started_utc"] = None
    return RedirectResponse("/forecast#results", status_code=303)
