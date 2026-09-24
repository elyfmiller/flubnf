"""Output (GET /output): the forecasts run so far, one card per forecast
date, newest first, each model's hub-format CSV from the run the date
shows (app/core/archive_record.choose), the own-data runs' exports,
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


def _member_of(dir_name: str) -> str:
    """The member key ("pf", "analogue") of a registered or modified
    submission folder; "" for anything else."""
    from app.core.submit import MODEL_ABBR, hub_model_id
    for k in MODEL_ABBR:
        if dir_name in (hub_model_id(k),
                        hub_model_id(k) + _knobs.MODIFIED_SUFFIX):
            return k
    return ""


def _attach_coverage(files: list, outcome: dict, spec) -> None:
    """Each registered or modified file's `cov` (app/core/coverage.py):
    how many of the run's requested locations it holds, and why the
    others are missing. Left out when the run's record cannot say."""
    import json as _json
    import pandas as pd
    from app.core import coverage
    try:
        sp = _json.loads(spec) if isinstance(spec, str) else (spec or {})
        requested = list((sp or {}).get("locations") or [])
    except (ValueError, TypeError):
        requested = []
    if not requested:
        return
    try:
        from flubnf.settings import load_locations
        locs = load_locations()
        f2n = dict(zip(locs.location.astype(str).str.zfill(2),
                       locs.location_name))
        total = len(locs)
    except Exception:
        return
    for entry in files:
        member = _member_of(entry.get("model", ""))
        if entry.get("archived") or not member:
            continue
        try:
            codes = pd.read_csv(entry["path"], dtype=str,
                                usecols=["location"]).location
        except Exception:
            continue
        present = {f2n.get(str(c).zfill(2), str(c)) for c in set(codes)}
        entry["cov"] = coverage.file_coverage(
            outcome or {}, member, entry["model"], requested, present,
            hub_total=total)


#: the hub's clock: the window closes at this hour, Eastern, on its last day
HUB_CLOSE_HOUR = 23


def _eastern(now):
    """An aware datetime as US Eastern wall time (EST/EDT). zoneinfo when
    the tz database is there; else the US rule (EDT from 2 AM on March's
    second Sunday to 2 AM on November's first), which is what it holds."""
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        return now.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        pass
    utc = now.astimezone(_dt.timezone.utc).replace(tzinfo=None)

    def _sunday(year, month, n):
        d = _dt.datetime(year, month, 1)
        return d + _dt.timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))
    y = utc.year
    start = _sunday(y, 3, 2) + _dt.timedelta(hours=2 + 5)    # 2 AM EST
    end = _sunday(y, 11, 1) + _dt.timedelta(hours=2 + 4)     # 2 AM EDT
    off = -4 if start <= utc < end else -5
    return (utc + _dt.timedelta(hours=off)).replace(
        tzinfo=_dt.timezone(_dt.timedelta(hours=off)))


def _window_text(due, today=None, now=None) -> str:
    """The hub's window for a round, one sentence: due (from/by, 11 PM
    Eastern on the last day) or closed. `due` is (first, last) dates. The
    clock is Eastern time, not the machine's: `now` (an aware datetime,
    default the current time) or, for a whole-day answer, `today`."""
    import datetime as _dt
    first, last = due
    if today is None:
        et = _eastern(now or _dt.datetime.now(_dt.timezone.utc))
        today = et.date()
        if today == last and et.hour >= HUB_CLOSE_HOUR:
            today = last + _dt.timedelta(days=1)     # closed at 11 PM ET
    if today > last:
        return f"The window closed {last:%a %Y-%m-%d}."
    if today < first:
        return f"Due {first:%a %b %d} to {last:%a %b %d}, 11 PM ET."
    return f"Due {last:%a %Y-%m-%d}, 11 PM ET."


def _date_window(ref: str, today=None, now=None) -> str:
    """A forecast date's one line: its window, or that the reference date
    is not a FluSight round (hub-config/tasks.json, vendored)."""
    from app.core import hubcheck
    try:
        rounds = hubcheck.vendored_rules()["rounds"]
        if ref not in rounds:
            return f"{ref} is not a FluSight round, so its files are a record."
        return _window_text(hubcheck.submission_window(ref),
                            today=today, now=now)
    except Exception:
        return ""


#: (path, mtime_ns, size) -> hubcheck.summary; a file is checked once
_CHECKED: dict = {}


def _check_line(path: str) -> dict:
    """One file's hub checks in a few words: {"ok", "text"} ("Passes the
    hub's checks" or "Fails N hub checks: <first>"), cached per file
    version."""
    from app.core import hubcheck
    try:
        st = Path(path).stat()
        key = (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        key = None
    s = _CHECKED.get(key) if key else None
    if s is None:
        s = hubcheck.summary(path)
        if key:
            if len(_CHECKED) > 512:
                _CHECKED.clear()
            _CHECKED[key] = s
    if s["ok"]:
        return {"ok": True, "text": "Passes the hub's checks"}
    n = len(s["problems"])
    return {"ok": False, "text": f"Fails {n} hub check{'s' if n != 1 else ''}: "
                                 f"{s['problems'][0]}"}


def _reference_date(asof: str) -> str:
    """The hub reference date of a run's as-of (submit.hub_reference_date),
    "" when the as-of is unreadable."""
    from app.core.submit import hub_reference_date
    try:
        return str(hub_reference_date(asof).date()) if asof else ""
    except Exception:
        return ""


# === Output (/output): forecasts by date, own-data exports, report ===


def _run_data_source(rid) -> str:
    """The data file one run read, as the ledger outcome records it
    ("live target-data through ..." or "archived vintage ..."); "" for a run
    from before it was recorded, or no run."""
    if not rid:
        return ""
    import json as _json
    from app.core.data import source_phrase
    from app.core.runs import Ledger
    r = Ledger().row(rid)
    if r:
        try:
            return source_phrase(
                _json.loads(r.get("outcome") or "{}").get("data_source"))
        except (ValueError, TypeError, AttributeError):
            return ""
    return ""


def _read_json(p: Path):
    import json as _json
    try:
        d = _json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def _file_complete(row, model_dir: str) -> bool:
    """Whether one run's file for a model counts as complete: the run
    finished ok and wrote the file whole (no location dropped, no error
    for it). A workroot without a ledger row counts as complete, as an
    archive from before its record does."""
    import json as _json
    if row is None:
        return True
    if row.get("status") != "ok":
        return False
    try:
        o = _json.loads(row.get("outcome") or "{}")
    except (ValueError, TypeError):
        o = {}
    o = o if isinstance(o, dict) else {}
    return not ((o.get("submission_dropped") or {}).get(model_dir)
                or (o.get("submission_errors") or {}).get(model_dir))


def _hub_candidates(app_state: Path, ledger) -> tuple:
    """(hub candidates, own-data runs). A hub candidate is one run's file
    for one registered or -modified model: {"asof", "dir", "run_id",
    "path", "complete", "row", "spec", "wr"}; research runs and folders
    under retired names are left out (they stay on disk and in Storage).
    Files an archive folder holds count too when their run's workroot is
    gone. Own-data runs: [{"run_id", "res", "wr"}]."""
    from app.core import archive_record as _ar
    from app.core.runs import is_research
    listed = _registered_model_ids() | _modified_model_ids()
    cands, own, seen = [], [], set()
    for f in shared._workroot_results():
        res = _read_json(f)
        if res is None:
            continue
        wr = f.parent
        if res.get("dataset"):
            own.append({"run_id": wr.name, "res": res, "wr": wr})
            continue
        if res.get("research") or is_research(res.get("spec", "")):
            continue
        asof = str(res.get("forecast_date") or "")
        row = ledger.row(wr.name) if ledger else None
        seen.add(wr.name)
        for p in sorted(wr.glob("submission/*/*.csv")):
            if p.parent.name not in listed or not asof:
                continue
            cands.append({"asof": asof, "dir": p.parent.name,
                          "run_id": wr.name, "path": str(p),
                          "complete": _file_complete(row, p.parent.name),
                          "row": row, "spec": res.get("spec", ""),
                          "wr": wr})
    for date in shared._archive_dates():
        d = app_state / "archive" / date
        rec = _ar.read_record(d) or {}
        rid = str(rec.get("run_id") or "")
        if rid and rid in seen:
            continue            # the run's own folder is listed above
        res = _read_json(d / "results.json") or {}
        for p in sorted(d.glob("submission/*/*.csv")):
            if p.parent.name not in listed:
                continue
            cands.append({"asof": date, "dir": p.parent.name,
                          "run_id": rid, "path": str(p),
                          "complete": bool(rec.get("complete", True)),
                          "row": ledger.row(rid) if (ledger and rid) else None,
                          "spec": res.get("spec", ""), "wr": d})
    return cands, own


def _file_entry(c: dict) -> dict:
    """A chosen candidate as the page shows it."""
    import json as _json
    name = c["dir"]
    modified = name in _modified_model_ids()
    e = {"model": name[:-len(_knobs.MODIFIED_SUFFIX)] if modified else name,
         "dir": name, "name": Path(c["path"]).name, "path": c["path"],
         "modified": modified, "run_id": c["run_id"],
         "run_when": (_run_label(c["run_id"], "", tag=False).split(" · ")[-1]
                      if c["run_id"] else ""),
         "complete": c["complete"]}
    if not modified:
        e["check"] = _check_line(c["path"])
    try:
        o = _json.loads((c.get("row") or {}).get("outcome") or "{}")
    except (ValueError, TypeError):
        o = {}
    tmp = [{"model": name, "path": c["path"]}]
    _attach_coverage(tmp, o if isinstance(o, dict) else {}, c.get("spec"))
    e["cov"] = tmp[0].get("cov")
    return e


def _member_order(dir_name: str) -> int:
    from app.core.submit import MODEL_ABBR
    return list(MODEL_ABBR).index(_member_of(dir_name)) \
        if _member_of(dir_name) in MODEL_ABBR else 99


def forecast_dates(today=None, now=None) -> tuple:
    """(dates, own) for the Output page. dates: newest forecast date first,
    each {"asof", "ref", "window", "files": the hub-named file per model,
    "modified": the -modified file per model}; each file from the run
    archive_record.choose picks among the runs that wrote one for the date.
    own: the own-data runs, newest first, with their exports."""
    from app.core import archive_record as _ar
    from app.core import custom_run
    from app.core.runs import APP_STATE, Ledger
    try:
        ledger = Ledger()
    except Exception:
        ledger = None
    cands, own_runs = _hub_candidates(APP_STATE, ledger)
    by = {}
    for c in cands:
        by.setdefault(c["asof"], {}).setdefault(c["dir"], []).append(c)
    dates = []
    for asof in sorted(by, reverse=True):
        ref = _reference_date(asof)
        files, modified = [], []
        for d in sorted(by[asof], key=lambda d: (_member_order(d), d)):
            e = _file_entry(_ar.choose(by[asof][d]))
            (modified if e["modified"] else files).append(e)
        dates.append({"asof": asof, "ref": ref or asof,
                      "window": _date_window(ref, today=today, now=now)
                      if ref else "",
                      # the data the shown files' runs read, once each
                      "data_src": list(dict.fromkeys(
                          x for x in (_run_data_source(e["run_id"])
                                      for e in files + modified) if x)),
                      "files": files, "modified": modified})
    own = []
    for r in own_runs:
        res = r["res"]
        ds = res.get("dataset") or {}
        exports = custom_run.export_files(r["wr"])
        if not exports:
            continue
        own.append({"run_id": r["run_id"],
                    "asof": str(res.get("forecast_date") or ""),
                    "dataset": str(ds.get("name") or ds.get("id") or "dataset"),
                    "run_when": _run_label(r["run_id"], "", tag=False
                                           ).split(" · ")[-1],
                    "files": exports})
    return dates, own


@router.get("/output", response_class=HTMLResponse)
def output_page(request: Request):
    from app.core.runs import APP_STATE
    rid, res = shared._latest_results()
    dates, own = forecast_dates()
    return templates.TemplateResponse(request, "output.html", {
        "active": "Output", "rid": rid,
        "dates": dates, "own": own,
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
    try:
        p = Path(path).resolve()
    except (OSError, ValueError):       # a NUL byte or an unusable name
        return HTMLResponse("<p>file not found in app state</p>", status_code=404)
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
            "kept on disk as a record, not for submission; Storage lists "
            "its run folder.</p>", status_code=409)
    return FileResponse(p, filename=p.name, media_type="text/csv",
                        content_disposition_type="attachment")


@router.post("/output/reveal")
def output_reveal(path: str = Form(...)):
    """Show the file in Finder / Explorer (a local desktop app)."""
    import subprocess
    from app.core.runs import APP_STATE
    try:
        p = Path(path).resolve()
    except (OSError, ValueError):       # a NUL byte or an unusable name
        return RedirectResponse("/output", status_code=303)
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
