"""Storage (GET /storage, alias GET /runs): the disk inventory, the run
ledger, and delete, clear and reclaim.

An APIRouter server.py includes before the forecast routes, so POST
/runs/clear stays ahead of GET /runs/{run_id}: the first route a path
matches names the Allow header of a wrong-method request. datasets_ui reads
_storage_inventory, _storage_target and _tree_size here.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.core import runs as _runs
from app.core import ttlcache
from app.core.runs import Ledger
from app.ui import retro_seasons
from app.ui.retro_prep import _results_jobs
from app.ui.retro_seasons import (_RETRO_ACTIVE, _sealed_roots,
                                  _season_status, _valid_season)
from app.ui.shared import (_back, _flash, _invalidate_scans, _outcome_items,
                           _run_label, _scan_archive_dates)
from app.ui.state import _status
from app.ui.templating import templates

router = APIRouter()


# === Storage (/storage, /runs): inventory, delete, clear, reclaim -> runs.html ===
# The sealed records and the hub clone are never deletable (no control, and
# refused again on POST); running/paused trees are refused server-side.
# Every destructive POST requires a confirmation naming exactly what the
# user saw (name or count); a stale confirmation deletes nothing. On the
# runner computer's main console (the students' Mac Studio) the panel also
# lists the students' experiments, outside the total, each deletable when
# the runner is not replaying it (app/core/runner.py, imported inside the
# functions). The engine's compiled-model cache is listed outside the total
# too, cleared (here or by Reclaim) only while no engine job runs.

@ttlcache.ttl_cache(ttl_s=60.0)
def _tree_size(path: str) -> int:
    from app.core import retro
    return retro.dir_size(Path(path))


def _storage_protected(p: Path) -> bool:
    """True when a path lies inside a sealed record or the hub clone, or
    anything else reclaim protects (FLUBNF_PROTECT_ROOTS): one barrier for
    Delete, Delete all and Reclaim, and for Retrospective's two deletes (an
    archived run's Delete, the Run form's discard)."""
    from app.core import reclaim
    from flubnf.settings import HUB
    if reclaim.is_protected(p):
        return True
    # the same comparison (another spelling of a root matches; an
    # unresolvable path is refused, never guessed)
    return reclaim.inside_any(
        p, [base for base, _ in _sealed_roots()] + [HUB])


#: a dataset run's export folder in its workroot (custom_run.EXPORT_DIR,
#: named here so the Storage page does not load that module's science
#: imports; test_s3b_storage holds the two equal)
_EXPORT_DIR = "export"


def _workroot_files(p: Path) -> str:
    """What a workroot's Delete takes with it beyond the working files, in
    the delete hint's words ("report and submission files", "report",
    "export files"); "" when it holds none (a stopped run may have written
    neither)."""
    have = []
    if (p / "report.html").is_file():
        have.append("report")
    for sub, words in (("submission", "submission files"),
                       (_EXPORT_DIR, "export files")):
        if next(p.glob(f"{sub}/*/*.csv"), None) is not None:
            have.append(words)
    if len(have) > 2:
        return ", ".join(have[:-1]) + " and " + have[-1]
    return " and ".join(have)


def _live_workroot_ids() -> set:
    """Workroot directory names a worker may be writing into right now."""
    out = set()
    running = _status.get("running") or ""
    if running and ":" in running:
        out.add(running.split(":", 1)[1])
    w = _status.get("workroot")
    if w:
        out.add(Path(w).name)
    return out


def _may_archive() -> bool:
    """Whether the console run in progress can write a report archive, by
    the pipeline's own archive step (pipeline.py, step 7): it skips a
    one-model run, a research run and a modified run whose files carry the
    non-hub name; every other run reaches _archive_run, a vintage run and a
    modified run exported under the hub names included. A dataset run or
    replay never reaches it. A run still starting may."""
    from app.core.knobs import hub_names
    from app.core.runs import is_research
    running = _status.get("running") or ""
    if not running:
        return False
    kind, _sep, rid = running.partition(":")
    if kind in ("dataset", "dataset-replay"):
        return False
    if not rid:
        return True
    try:
        row = Ledger().row(rid) or {}
    except Exception:
        return True
    spec = row.get("spec") or ""
    # the step's own three skips, in its order; a vintage run is not one
    # (_archive_run writes it when the date holds no real-time run)
    return (not is_research(spec) and hub_names(spec)
            and str(_spec_of(spec).get("engine") or "all")
            not in ("analogue", "pf"))


def _archiving_date() -> str | None:
    """The forecast date whose report archive the run in progress may be
    writing: None when it can write none (_may_archive), "" when it may
    but its date is unknown (every archive is then held)."""
    if not _may_archive():
        return None
    import json
    for w in _live_workroot_ids():
        try:
            spec = Ledger().row(w)["spec"]
            spec = json.loads(spec) if isinstance(spec, str) else spec
            return str(spec.get("forecast_date") or "")
        except Exception:                # no row yet, or an odd one
            continue
    return ""


def _local_when(stamp: str) -> str:
    """An archive's stamp ('20261025T191800Z', UTC) in this computer's
    time, as the workroot rows' run times read ('2026-10-25 12:18'), so
    the two on one page compare; an unreadable stamp as stamp_human says
    it."""
    from datetime import datetime, timezone
    from app.core import retro
    try:
        t = datetime.strptime((stamp or "").split("-")[0], "%Y%m%dT%H%M%SZ")
    except ValueError:
        return retro.stamp_human(stamp)
    return t.replace(tzinfo=timezone.utc).astimezone().strftime(
        "%Y-%m-%d %H:%M")


def _busy_why(kind: str, ident: str, status: str = "") -> str:
    """Why one storage entry cannot be deleted right now, in the words the
    refused POST flashes; the page shows the same sentence as its disabled
    Delete button's reason."""
    if kind == "workroot":
        return (f"The run {ident} is active; its workroot cannot be deleted "
                "while it runs.")
    if kind == "retro-season":
        return f"{ident} is replaying (status: {status}); stop it first."
    if kind == "retro-archive":
        return (f"{ident} is replaying; stop it before deleting its archived "
                "runs.")
    if kind == "engine-cache":
        # `ident` is the reason (reclaim.codegen_cache_refusal's words)
        return (f"The engine cache is kept while the engine runs ({ident}); "
                "it can be cleared once the engine is idle.")
    return ("A console run is in progress and may be writing the archive; "
            "stop it first.")


def _engine_busy_reason() -> str:
    """Why this console's engine is in use ("" when idle): a console run
    (a dataset run or replay included), a season replay, a Sandbox fit or
    experiment. The Sandbox's Start reads the same reason."""
    from app.ui.routes.sandbox import _sandbox_busy_reason
    return _sandbox_busy_reason()


def _engine_cache_row() -> dict | None:
    """The engine cache's row (bngsim's compiled models, in the state
    folder: reclaim.codegen_cache_dir): its size, and while an engine job
    runs here or in another process, busy with why. None when there is
    none on disk. Listed outside the total: a cache, not a record.
    "protected" when the folder lies in a protected tree (no Delete, and
    Reclaim leaves it out); "linked", the folder a linked cache leads to,
    sized there and never cleared here; "old", bngsim's own folder
    (pf.BNGSIM_OWN_CACHE, where the engine kept them before they moved to
    the state folder) when it is still on disk: FluBNF leaves it where it
    is, since other programs may share it, and the row says so."""
    from app.core import reclaim, retro
    from app.core.engines import pf
    entries = reclaim.codegen_cache_entries()
    link = reclaim.codegen_cache_link()
    if not entries and link is None:
        return None
    d = reclaim.codegen_cache_dir()
    size = sum(_tree_size(str(p)) for p in entries)
    if link is not None and link.is_dir():
        size += _tree_size(str(link))
    protected = _storage_protected(d)
    why = ("" if protected or not entries
           else reclaim.codegen_cache_refusal(_engine_busy_reason()))
    try:
        old = Path(pf.BNGSIM_OWN_CACHE).expanduser().is_dir()
    except (OSError, RuntimeError):
        old = False
    return {"id": d.name, "bytes": size,
            "size_h": retro.human_bytes(size), "busy": bool(why),
            "why": _busy_why("engine-cache", why) if why else "",
            "protected": protected,
            "linked": str(link) if link is not None else "",
            "old": pf.BNGSIM_OWN_CACHE if old else ""}


def _engine_cache_clearable() -> bool:
    """Whether Storage's Delete and Reclaim may offer the cache at all:
    something of it on disk (a link is never followed) outside every
    protected tree. Busy is asked apart, since it passes."""
    from app.core import reclaim
    return bool(reclaim.codegen_cache_entries()) and not _storage_protected(
        reclaim.codegen_cache_dir())


# the panel's counted categories, in page order: (key, label)
_CATEGORIES = (("workroots", "Run workroots"),
               ("retro", "Retrospective seasons"),
               ("retro_archives", "Archived retrospective runs"),
               ("report_archives", "Report archives"),
               ("datasets", "Dataset uploads and replays"))


def _students_here() -> bool:
    """Whether this is the runner computer's main console: the computer
    has a runner (~/Students/.runner) and this console's Sandbox is not
    in ~/Students (a student's folder, or a clone there the runner does
    not take, such as one named jane.doe). Only here does Storage list
    the students' experiments, and delete one. One failed stat off the
    runner."""
    from app.core import runner
    from app.core import sandbox as sb
    return (runner.state_dir().is_dir()
            and not runner._in_students(sb.SANDBOX))


def _student_experiments() -> dict:
    """The Student experiments section: runner.storage's rows (sized
    through _tree_size's cache) and its runner line, each row with the
    badge its student's card shows (routes/sandbox._experiment_badge)."""
    from app.core import runner
    from app.ui.routes.sandbox import _experiment_badge, _runner_job
    su = runner.storage(size=lambda p: _tree_size(str(p)))
    state = runner.read_state()
    for r in su["rows"]:
        held = ("runner" if _runner_job(state, r["folder"]) == r["id"]
                else False)
        r["badge"] = _experiment_badge(r["status"], held, r["queued"],
                                       r["refused"])
    return su


def _spec_of(spec) -> dict:
    """A ledger spec (JSON text or dict) as a dict; {} when unreadable."""
    import json as _json
    try:
        d = _json.loads(spec) if isinstance(spec, str) else spec
    except (ValueError, TypeError):
        return {}
    return d if isinstance(d, dict) else {}


def _round_label(spec, fallback: str) -> str:
    """A hub forecast run's row label by its round, as Output heads its
    cards: "Round 2026-10-10 (as of 2026-10-03)"; `fallback` (run_display's
    words) for a retrospective fit, a run on your own data or an
    unrecorded run."""
    from app.ui.routes.output import _reference_date
    d = _spec_of(spec)
    extra = d.get("extra") if isinstance(d.get("extra"), dict) else {}
    asof = str(d.get("forecast_date") or "").strip()
    if not asof or str(d.get("engine")) == "retro" or extra.get("dataset"):
        return fallback
    ref = _reference_date(asof)
    return f"Round {ref} (as of {asof})" if ref else fallback


def _ledger_parts(run_id: str, spec) -> list:
    """A ledger row's label in its parts, each kept whole on a narrow
    screen: ["as of 2026-10-03", "run 10-05 14:31:07"] (the run's local
    start, from its id, as every run label reads it); just the run's time
    when the spec names no date."""
    asof = str(_spec_of(spec).get("forecast_date") or "").strip()
    when = (f"run {_run_label(run_id, '', tag=False)}"
            if _runs.is_run_id(run_id) else run_id)
    return ([f"as of {asof}"] if asof else []) + [when]


def _storage_inventory() -> dict:
    """Storage panel rows with sizes: workroots, live retro seasons, retro
    archives, report archives, your datasets (each with a busy flag and,
    when busy, "why" it cannot be deleted; all but a dataset with a
    "protected" flag, whose row has no Delete), plus the protected trees
    (no controls). total_bytes/total_h sum the managed categories only, each
    byte once: a dataset adds its own folder (the upload and its replays),
    its runs being counted as workroots. "cats" splits that total by
    category (the page's composition bar and legend). "students" holds
    the students' experiments on the runner computer's main console
    (_students_here), outside the total; None everywhere else.
    "engine_cache" is the engine's compiled-model cache (_engine_cache_row),
    outside the total too; None when there is none. "engine_cache_warning"
    is what the runners said when they could not write its folder
    (pf.codegen_cache_warning), "" otherwise."""
    import re as _re
    from app.core import retro
    from app.core.runs import APP_STATE, is_research, run_display
    from app.ui import datasets_ui as _dsu
    from flubnf.settings import HUB
    inv = {"workroots": [], "retro": [], "retro_archives": [],
           "report_archives": [], "datasets": [], "protected": [],
           "total_bytes": 0, "total_h": ""}
    live_ids = _live_workroot_ids()
    # ledger rows label each workroot; one without a row reads as unrecorded
    try:
        led_rows = {r["run_id"]: r for r in Ledger().rows(100_000)}
    except Exception:
        led_rows = {}
    wr = APP_STATE / "workroots"
    if wr.is_dir():
        for p in sorted((d for d in wr.iterdir() if d.is_dir()),
                        key=lambda d: d.name, reverse=True):
            size = _tree_size(str(p))
            inv["total_bytes"] += size
            row = led_rows.get(p.name) or {}
            disp = run_display(p.name, row.get("spec"),
                               row.get("created_utc"))
            # the ledger's status, as the ledger table reads it: a
            # 'running' row with no live worker was closed mid-run
            st = str(row.get("status") or "")
            if st == "running" and p.name not in live_ids:
                st = "interrupted"
            inv["workroots"].append({
                "id": p.name, "size_h": retro.human_bytes(size),
                "label": _round_label(row.get("spec"), disp["what"]),
                # the run's time as the ledger row and every label read it
                "status": st,
                "when": (_run_label(p.name, "", tag=False)
                         if _runs.is_run_id(p.name) else disp["when"]),
                "scope": disp["scope"], "recorded": disp["recorded"],
                "research": is_research(row.get("spec", "")),
                "modified": _runs.is_modified(row.get("spec", "")),
                "busy": p.name in live_ids,
                "protected": _storage_protected(p),
                # what its delete hint says goes with it (_workroot_files)
                "files": _workroot_files(p),
                "why": (_busy_why("workroot", p.name)
                        if p.name in live_ids else ""),
                # for the dataset rows: the run's size and its dataset
                "bytes": size, "dataset": _dsu.spec_dataset(row.get("spec"))})
    if retro_seasons.RETRO_ROOT.is_dir():
        for p in sorted(retro_seasons.RETRO_ROOT.iterdir()):
            if not p.is_dir() and not p.is_symlink():
                continue
            if _valid_season(p.name):
                st = _season_status(p.name)
                size = _tree_size(str(p))
                inv["total_bytes"] += size
                inv["retro"].append({
                    "id": p.name, "size_h": retro.human_bytes(size),
                    "bytes": size, "status": st,
                    "busy": st in _RETRO_ACTIVE,
                    "protected": _storage_protected(p),
                    "why": (_busy_why("retro-season", p.name, st)
                            if st in _RETRO_ACTIVE else "")})
                continue
            m = _re.match(r"(\d{4}-\d{2})", p.name)
            if m and retro.archive_stamp_of(p.name, m.group(1)):
                season = m.group(1)
                stamp = retro.archive_stamp_of(p.name, season)
                size = _tree_size(str(p))
                inv["total_bytes"] += size
                from app.core import replay_bundle
                inv["retro_archives"].append({
                    "id": p.name, "season": season, "stamp": stamp,
                    "when": _local_when(stamp),
                    # a replay imported from another machine
                    # ("imported from <host> on <date>"), else ""
                    "imported": replay_bundle.imported_label(p),
                    "size_h": retro.human_bytes(size), "bytes": size,
                    "busy": _season_status(season) in _RETRO_ACTIVE,
                    "protected": _storage_protected(p),
                    "why": _busy_why("retro-archive", season)})
    # held only while the run in progress can write a report archive, and
    # then only its own date's
    run_fd = _archiving_date()
    arch = APP_STATE / "archive"
    for d in reversed(_scan_archive_dates(arch)):
        size = _tree_size(str(arch / d))
        inv["total_bytes"] += size
        inv["report_archives"].append({
            "id": d, "size_h": retro.human_bytes(size), "bytes": size,
            # its round, as the workroot rows above name it
            "label": _round_label({"forecast_date": d}, d),
            # the Output tab serves an archived report by its date
            "report": (arch / d / "report.html").is_file(),
            "busy": run_fd is not None and run_fd in ("", d),
            "protected": _storage_protected(arch / d),
            "why": _busy_why("report-archive", d)})
    inv["datasets"] = _dsu.storage_rows(inv["workroots"])
    for d in inv["datasets"]:
        d["why"] = (f"{d['name']} cannot be deleted now: {d['busy']}."
                    if d.get("busy") else "")
    inv["total_bytes"] += sum(d["own_bytes"] for d in inv["datasets"])
    for label, p in (("Production engine record", retro_seasons.RETRO_RESEAL),
                     ("Sealed validation record", retro_seasons.RETRO_SEAL),
                     ("FluSight hub clone", HUB)):
        if Path(p).exists():
            inv["protected"].append({
                "label": label, "path": str(p),
                "size_h": retro.human_bytes(_tree_size(str(p)))})
    inv["total_h"] = retro.human_bytes(inv["total_bytes"])
    cats = []
    for key, label in _CATEGORIES:
        b = sum(int(r.get("own_bytes" if key == "datasets" else "bytes")
                    or 0) for r in inv[key])
        if b:
            cats.append({"key": key, "label": label, "bytes": b,
                         "size_h": retro.human_bytes(b)})
    inv["cats"] = cats
    inv["students"] = _student_experiments() if _students_here() else None
    inv["engine_cache"] = _engine_cache_row()
    from app.core.engines import pf
    inv["engine_cache_warning"] = pf.codegen_cache_warning()
    return inv


def _clearable_workroots() -> list:
    """[{"id", "bytes"}] newest first: every workroot except the active
    run's and anything inside a protected tree."""
    from app.core.runs import APP_STATE
    live = _live_workroot_ids()
    out = []
    wr = APP_STATE / "workroots"
    if wr.is_dir():
        for p in sorted((d for d in wr.iterdir() if d.is_dir()),
                        key=lambda d: d.name, reverse=True):
            if p.name in live or _storage_protected(p):
                continue
            out.append({"id": p.name, "bytes": _tree_size(str(p))})
    return out


def _clearable_run_ids(ledger) -> list:
    """Ledger run ids the clear control may remove: all but the active
    run's row."""
    live = _status.get("running") or ""
    out = []
    for r in ledger.rows(100_000):
        rid = r.get("run_id") or ""
        if r.get("status") == "running" and live.endswith(rid) and rid:
            continue
        out.append(rid)
    return out


#: the run ledger's table shows this many rows, newest first
LEDGER_ROWS = 50


@router.get("/storage", response_class=HTMLResponse)
@router.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request):
    """Storage tab: storage panel, then the run ledger. /runs is a kept
    alias (old reports and bookmarks link it)."""
    from app.core.runs import APP_STATE, is_research
    from app.core import retro
    from app.ui.routes.output import _files_deleted
    ledger = Ledger()
    rows = ledger.rows(LEDGER_ROWS)
    for r in rows:
        # the research badge carries the tag, so the label stays untagged;
        # its parts each hold together on a narrow screen
        r["parts"] = _ledger_parts(r["run_id"], r.get("spec", ""))
        r["label"] = " · ".join(r["parts"])
        r["asof"] = str(_spec_of(r.get("spec", "")).get("forecast_date")
                        or "")
        r["research"] = is_research(r.get("spec", ""))
        r["modified"] = _runs.is_modified(r.get("spec", ""))
        # the outcome as facts the page draws as chips and badges
        r["facts"] = _outcome_items(r.get("outcome", ""),
                                    deleted=_files_deleted(r["run_id"]))
        # a 'running' row with no live worker = the app was closed mid-run
        if r["status"] == "running" and not (_status.get("running") or "").endswith(r["run_id"]):
            r["status"] = "interrupted"
        # a deleted workroot keeps its row and shows a dash for disk use
        w = APP_STATE / "workroots" / r["run_id"]
        r["disk_h"] = (retro.human_bytes(_tree_size(str(w)))
                       if w.is_dir() else None)
    cw = _clearable_workroots()
    return templates.TemplateResponse(request, "runs.html", {
        "active": "Storage", "ledger": rows,
        # how many runs the ledger holds: the table shows the newest
        # LEDGER_ROWS and says when it leaves older ones out
        "ledger_total": max(len(ledger.rows(1_000_000)), len(rows)),
        "clear_count": len(_clearable_run_ids(ledger)),
        "storage": _storage_inventory(),
        # clear-all: count and weight, named by the confirmation
        "clear_workroots": {"count": len(cw),
                            "size_h": retro.human_bytes(
                                sum(w["bytes"] for w in cw))}})


@router.post("/runs/clear")
def runs_clear(request: Request, confirm: str = Form("")):
    """Clear every completed ledger row (confirmation = the count seen).
    Never the active run's row; never deletes workroot data on disk."""
    _invalidate_scans()
    ledger = Ledger()
    ids = _clearable_run_ids(ledger)
    if not ids:
        _flash("Nothing to clear: the ledger has no rows to remove.", "warn")
        return _back(request, "/storage")
    if confirm != str(len(ids)):
        _flash("Not cleared: the ledger changed "
               f"({len(ids)} clearable row{'' if len(ids) == 1 else 's'} "
               "now).", "warn", detail="Review and confirm again.")
        return _back(request, "/storage")
    n = ledger.delete_runs(ids)
    _invalidate_scans()
    _flash(f"Cleared {n} ledger row{'' if n == 1 else 's'}.", "ok",
           detail="No data on disk was deleted: the runs' workroots stay "
           "in the storage panel until deleted there.")
    return _back(request, "/storage")


def _replaying_why(kind: str, ident: str) -> str:
    """Why a retrospective season, or an archived run of one (ident
    <season>__archived_<stamp>), cannot be deleted while its season
    replays, in _busy_why's words; "" otherwise and for every other kind.
    Asked twice by a delete: with the other checks (_storage_target), then
    again under _engine_lock once the tree is marked, the lock a Run
    claims a season under, after refusing a marked tree: of a Resume and a
    delete, one comes first and the other refuses."""
    if kind == "retro-season":
        st = _season_status(ident)
        return _busy_why(kind, ident, st) if st in _RETRO_ACTIVE else ""
    if kind == "retro-archive":
        import re as _re
        m = _re.match(r"(\d{4}-\d{2})", ident or "")
        if m and _season_status(m.group(1)) in _RETRO_ACTIVE:
            return _busy_why(kind, m.group(1))
    return ""


def _storage_target(kind: str, ident: str):
    """(path, busy_reason) for one storage delete request, after all
    validation EXCEPT the confirmation; (None, message) when refused."""
    import re as _re
    from app.core import retro
    from app.core.runs import APP_STATE
    if kind == "workroot":
        if not _re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", ident or ""):
            return None, "Unrecognized workroot name."
        p = APP_STATE / "workroots" / ident
        if ident in _live_workroot_ids():
            return None, _busy_why(kind, ident)
        base = APP_STATE / "workroots"
    elif kind == "retro-season":
        if not _valid_season(ident):
            return None, "Unrecognized season name."
        why = _replaying_why(kind, ident)
        if why:
            return None, why
        p = retro_seasons.RETRO_ROOT / ident
        base = retro_seasons.RETRO_ROOT
    elif kind == "retro-archive":
        m = _re.match(r"(\d{4}-\d{2})", ident or "")
        stamp = (retro.archive_stamp_of(ident, m.group(1)) if m else "")
        if not stamp:
            return None, "Unrecognized archived run identifier."
        why = _replaying_why(kind, ident)
        if why:
            return None, why
        p = retro_seasons.RETRO_ROOT / ident
        base = retro_seasons.RETRO_ROOT
    elif kind == "report-archive":
        if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", ident or ""):
            return None, "Unrecognized report archive date."
        held = _archiving_date()
        if held is not None and held in ("", ident):
            return None, _busy_why(kind, ident)
        p = APP_STATE / "archive" / ident
        base = APP_STATE / "archive"
    elif kind == "experiment" and _students_here():
        # <name>/<id>: a / belongs to neither a folder's name nor an id
        from app.core import experiments as X
        from app.core import runner
        from app.core.problem_codes import Refusal
        name, _sep, eid = (ident or "").partition("/")
        if name not in runner.folders() or not X._ID_RE.fullmatch(eid):
            return None, "Unrecognized student experiment."
        try:
            runner.check(name, eid)
        except Refusal as e:
            return None, f"{e.findings[0]['text']}."
        row = next((r for r in runner.storage(size=lambda q: 0)["rows"]
                    if r["ident"] == ident), None)
        if row is None:
            return None, "Nothing is on disk under that name."
        if row["busy"]:
            return None, row["why"]
        base = runner.folder(name) / "experiments"
        p = base / eid
    elif kind == "engine-cache":
        # cleared by storage_delete through reclaim.clear_codegen_cache,
        # which asks again under the engine lock
        from app.core import reclaim
        p = reclaim.codegen_cache_dir()
        if ident != p.name:
            return None, "Unrecognized storage entry."
        if not reclaim.codegen_cache_entries():
            return None, "Nothing is on disk under that name."
        if _storage_protected(p):
            return None, ("That folder is protected; the console never "
                          "deletes it.")
        why = reclaim.codegen_cache_refusal(_engine_busy_reason())
        if why:
            return None, _busy_why(kind, why)
        return p, ""
    else:
        return None, "Unrecognized storage kind."
    # Containment by construction (separator-free identifiers). Not resolved
    # here: a symlinked season is legitimate (delete_tree removes the link),
    # but _storage_protected resolves, so a link into a protected tree fails.
    assert p.parent == Path(base), "storage target escaped its parent"
    if _storage_protected(p):
        # which record it is is not claimed: FLUBNF_PROTECT_ROOTS protects
        # folders that are neither the sealed records nor the hub clone
        return None, ("That folder is protected; the console never "
                      "deletes it.")
    if not (p.is_dir() or p.is_symlink()):
        return None, "Nothing is on disk under that name."
    return p, ""


@router.post("/storage/delete")
def storage_delete(request: Request, kind: str = Form(""),
                   ident: str = Form(""), confirm: str = Form("")):
    """Delete one storage entry permanently: validate, refuse busy or
    protected, then require the confirmation to name the entry."""
    from app.core import retro
    _invalidate_scans()
    p, why = _storage_target(kind, ident)
    if p is None:
        _flash(f"Not deleted: {why[:1].lower()}{why[1:]}", "warn")
        return _back(request, "/storage")
    if confirm != ident:
        _flash("Not deleted: the deletion was not confirmed.", "warn")
        return _back(request, "/storage")
    if kind == "engine-cache":
        return _clear_engine_cache(request)
    # a season or archived run whose results are still being written
    # after its replay or a results visit: a delete meanwhile could fail
    # half way. Marked first, so no results page starts a finalize on it
    # from here on (retro_prep._removing)
    from contextlib import ExitStack
    from app.ui import retro_prep
    from app.ui.state import _engine_lock
    with ExitStack() as held:
        # marked under _engine_lock, and the season's status looked at
        # again there: a Resume claimed since the first look is refused
        # here, and one posted from now on finds the mark (routes/retro.py
        # asks under the same lock). Released before the delete itself
        with _engine_lock:
            busy = held.enter_context(retro_prep._removing(p))
            replaying = "" if busy else _replaying_why(kind, ident)
        if busy == retro_prep._ALREADY_REMOVING:
            # a second delete at once (a double click, another tab), or
            # an import replacing the run: the first goes on and says so
            _flash(f"Not deleted: {ident} is {busy}.", "warn",
                   detail="Nothing else changed.")
            return _back(request, "/storage")
        if busy:
            _flash(f"Not deleted: the {busy} of {ident} are still being "
                   "prepared.", "warn", detail="Try again in a minute.")
            return _back(request, "/storage")
        if replaying:
            _flash(f"Not deleted: {replaying[:1].lower()}{replaying[1:]}",
                   "warn")
            return _back(request, "/storage")
        # its week maps may still be written after its replay or a
        # results visit: stopped first, or a delete meanwhile could fail
        # half way (retro_prep._stop_warm). Under the mark, so no
        # finalize starts a new warm once this one stops
        if not retro_prep._stop_warm(p):
            _flash(f"Not deleted: the week maps of {ident} are still being "
                   "prepared.", "warn", detail="Try again in a minute.")
            return _back(request, "/storage")
        size_h = retro.human_bytes(retro.dir_size(p))
        try:
            retro.delete_tree(p)
        except Exception as e:
            _flash(f"Could not delete {ident}: {type(e).__name__}: "
                   f"{str(e)[:160]}.", "error",
                   detail="Nothing else changed.")
            return _back(request, "/storage")
    _invalidate_scans()
    noun = {"workroot": "workroot", "retro-season": "retrospective season",
            "retro-archive": "archived retrospective run",
            "report-archive": "report archive",
            "experiment": "student experiment"}.get(kind, "entry")
    tail = ("Its ledger row remains as the run's record."
            if kind == "workroot" else "")
    _flash(f"Deleted the {noun} {ident}: {size_h} freed.", "ok", detail=tail)
    return _back(request, "/storage")


#: what a cleared engine cache means, said wherever one is cleared
_CACHE_CLEARED = ("The engine compiles each model again on its next fit, "
                  "which takes a little longer once; no forecast, score or "
                  "report changes.")


def _clear_engine_cache(request: Request):
    """Storage's Delete on the engine cache: cleared unless an engine job
    runs, asked again under the engine lock (reclaim.clear_codegen_cache)."""
    from app.core import reclaim, retro
    from app.ui.state import _engine_lock
    out = reclaim.clear_codegen_cache(busy=_engine_busy_reason,
                                      lock=_engine_lock)
    _invalidate_scans()
    if out["refused"]:
        why = (_busy_why("engine-cache", out["refused"]) if out["busy"]
               else f"{out['refused']}.")
        _flash(f"Not deleted: {why[:1].lower()}{why[1:]}", "warn")
        return _back(request, "/storage")
    _flash(f"Cleared the engine cache: {retro.human_bytes(out['bytes'])} "
           "freed.", "ok", detail=_CACHE_CLEARED)
    return _back(request, "/storage")


@router.post("/storage/clear-workroots")
def storage_clear_workroots(request: Request, confirm: str = Form("")):
    """Delete every completed run's workroot (confirmation = the count
    seen). Live/protected checks repeat per directory; ledger rows stay."""
    from app.core import retro
    from app.core.runs import APP_STATE
    _invalidate_scans()
    items = _clearable_workroots()
    if not items:
        _flash("Nothing to delete: no run workroots on disk"
               + (" apart from the active run's." if _live_workroot_ids()
                  else "."), "warn")
        return _back(request, "/storage")
    if confirm != str(len(items)):
        _flash("Not deleted: the storage panel changed "
               f"({len(items)} deletable workroot"
               f"{'' if len(items) == 1 else 's'} now).", "warn",
               detail="Review and confirm again.")
        return _back(request, "/storage")
    live = _live_workroot_ids()
    freed, n = 0, 0
    for it in items:
        p = APP_STATE / "workroots" / it["id"]
        # re-checked: a run claimed since the render keeps its workroot
        if it["id"] in live or _storage_protected(p) \
                or not (p.is_dir() or p.is_symlink()):
            continue
        try:
            size = retro.dir_size(p)
            retro.delete_tree(p)
            freed += size
            n += 1
        except Exception:
            continue          # one stuck tree must not sink the sweep
    _invalidate_scans()
    _flash(f"Deleted {n} run workroot{'' if n == 1 else 's'}: "
           f"{retro.human_bytes(freed)} freed.", "ok",
           detail="Every ledger row is kept and shows a dash for disk use.")
    return _back(request, "/storage")


# === Storage: reclaim (prune completed intermediates, compress samples) ===
# GET is a dry run by category; POST performs it behind a counts
# confirmation. Classification lives in app/core/reclaim.py; samples gzip
# losslessly with mtimes kept, so every score and export is reproducible.

def _reclaim_skips() -> tuple:
    """(season entry names, workroot names) the reclaim must not touch right
    now: seasons replaying, mid-finalize or still warming their week map
    cards (the warm reads each week's samples file, which a reclaim could
    compress or remove under it), trees a delete, a move or an import's
    Replace holds (retro_prep._removing's mark), and the active run's
    workroot. The survey and the perform step take the same rule, so
    their counts agree while nothing changes."""
    from app.ui import retro_prep
    skip_seasons = {s for s in retro_seasons._known_seasons()
                    if _season_status(s) in _RETRO_ACTIVE}
    for key, job in list(_results_jobs.items()):
        if not job:
            continue
        warming = job.get("warm") is not None and not job["warm"].is_set()
        if not job["done"].is_set() or warming:
            skip_seasons.add(Path(key).name)
    with retro_prep._results_lock:
        marked = list(retro_prep._REMOVING)
    skip_seasons.update(Path(k).name for k in marked)
    return skip_seasons, set(_live_workroot_ids())


@contextmanager
def _reclaim_hold(tree: Path):
    """Around reclaim's work on one season tree (one week's prune, one
    file's compress: reclaim.execute's `hold`): held under the lock a
    delete's, a move's or a Replace's mark is taken under
    (retro_prep._results_lock), it yields False while such a mark holds
    the tree, and True otherwise. So the mark never comes between this
    look and the work: a delete or a Replace that arrives during one
    file's compress waits for that file, then marks the tree, and reclaim
    leaves the rest of it alone."""
    from app.ui import retro_prep
    with retro_prep._results_lock:
        yield not retro_prep._being_removed(tree)


def _reclaim_survey() -> dict:
    """reclaim.survey's plan, plus the engine cache: cache_bytes (in
    total_est) when it may be cleared now, else cache_why, why it is kept.
    A protected cache is left out, as protected seasons are. The cache
    stays out of the confirmation token: clearing more or less of it loses
    nothing."""
    from app.core import reclaim
    from app.core.runs import APP_STATE
    skip_seasons, skip_workroots = _reclaim_skips()
    plan = reclaim.survey(retro_seasons.RETRO_ROOT, APP_STATE / "workroots",
                          skip_seasons=skip_seasons,
                          skip_workroots=skip_workroots)
    plan["cache_bytes"], plan["cache_why"] = 0, ""
    if _engine_cache_clearable():
        why = reclaim.codegen_cache_refusal(_engine_busy_reason())
        if why:
            plan["cache_why"] = why
        else:
            plan["cache_bytes"] = reclaim.codegen_cache_bytes()
    plan["total_est"] += plan["cache_bytes"]
    return plan


@router.get("/api/storage/reclaim")
def api_storage_reclaim():
    """Dry run: what a reclaim would free, by category (no side effects).
    'confirm' must match storage_reclaim's counts token."""
    from app.core import retro
    plan = _reclaim_survey()
    hb = retro.human_bytes
    cats = []
    if plan["week_bytes"]:
        cats.append({
            "label": "Completed-week fit intermediates",
            "bytes": plan["week_bytes"], "bytes_h": hb(plan["week_bytes"]),
            "detail": (f"{plan['weeks']} completed weeks across "
                       f"{len(plan['season_ids'])} season "
                       f"tree{'' if len(plan['season_ids']) == 1 else 's'}")})
    if plan["workroot_bytes"]:
        cats.append({
            "label": "Completed-run workroot intermediates",
            "bytes": plan["workroot_bytes"],
            "bytes_h": hb(plan["workroot_bytes"]),
            "detail": (f"{plan['workroots']} completed "
                       f"run{'' if plan['workroots'] == 1 else 's'}; "
                       "results, reports, and submissions are kept")})
    if plan["compress_files"]:
        cats.append({
            "label": "Stored-sample compression (lossless gzip)",
            "bytes": plan["est_compress_saved"],
            "bytes_h": hb(plan["est_compress_saved"]),
            "detail": (f"{plan['compress_files']} stored weeks, "
                       f"{hb(plan['compress_bytes'])} now; estimated "
                       f"{hb(plan['est_compress_saved'])} freed, every week "
                       "stays scoreable and playable")})
    if plan["cache_bytes"]:
        cats.append({
            "key": "engine-cache",
            "label": "Engine cache (compiled models)",
            "bytes": plan["cache_bytes"], "bytes_h": hb(plan["cache_bytes"]),
            "detail": ("the engine compiles each model again on its next "
                       "fit; no forecast changes")})
    counts = f"{plan['weeks']}/{plan['workroots']}/{plan['compress_files']}"
    return {"categories": cats, "total": plan["total_est"],
            "total_h": hb(plan["total_est"]), "confirm": counts}


@router.post("/storage/reclaim")
def storage_reclaim(request: Request, confirm: str = Form("")):
    """Perform the reclaim the dry run described (confirmation = its
    weeks/workroots/files counts). Busy and protection rules re-apply per
    entry."""
    from app.core import reclaim, retro
    from app.core.runs import APP_STATE
    _invalidate_scans()
    plan = _reclaim_survey()
    counts = f"{plan['weeks']}/{plan['workroots']}/{plan['compress_files']}"
    if plan["total_est"] <= 0 and plan["compress_files"] == 0:
        nothing = ("No completed week or run carries intermediates, and "
                   "every stored week is already compressed.")
        if plan["cache_why"]:
            # the cache alone, and an engine job holds it: said, as
            # Storage's Delete says it
            why = _busy_why("engine-cache", plan["cache_why"])
            _flash(f"Not reclaimed: {why[:1].lower()}{why[1:]}", "warn",
                   detail=nothing)
        else:
            _flash("Nothing to reclaim.", "warn", detail=nothing)
        return _back(request, "/storage")
    if confirm != counts:
        _flash("Not reclaimed: the storage panel changed since the report.",
               "warn", detail="A run finished or files moved. Review the "
               "reclaim report and confirm again.")
        return _back(request, "/storage")
    skip_seasons, skip_workroots = _reclaim_skips()
    out = reclaim.execute(retro_seasons.RETRO_ROOT, APP_STATE / "workroots",
                          skip_seasons=skip_seasons,
                          skip_workroots=skip_workroots,
                          hold=_reclaim_hold)
    # the engine cache, when the report offered it: asked again under the
    # engine lock, so a run started since keeps it
    cache = {"bytes": 0, "refused": "", "busy": False}
    if plan["cache_bytes"]:
        from app.ui.state import _engine_lock
        cache = reclaim.clear_codegen_cache(busy=_engine_busy_reason,
                                            lock=_engine_lock)
    _invalidate_scans()
    hb = retro.human_bytes
    bits = []
    if out["week_bytes"]:
        bits.append(f"{hb(out['week_bytes'])} of fit intermediates from "
                    f"{out['weeks']} completed week"
                    f"{'' if out['weeks'] == 1 else 's'}")
    if out["workroot_bytes"]:
        bits.append(f"{hb(out['workroot_bytes'])} from "
                    f"{out['workroots']} completed run workroot"
                    f"{'' if out['workroots'] == 1 else 's'}")
    if out["compress_files"]:
        bits.append(f"{hb(out['compress_saved'])} by compressing "
                    f"{out['compress_files']} stored week"
                    f"{'' if out['compress_files'] == 1 else 's'} in place")
    if cache["bytes"]:
        bits.append(f"{hb(cache['bytes'])} by clearing the engine cache")
    # kept because an engine job holds it, at the survey or under the
    # lock: said in Storage's words; any other refusal as it came
    held = plan["cache_why"] or (cache["refused"] if cache["busy"] else "")
    if held:
        kept = _busy_why("engine-cache", held) + " "
    elif cache["refused"]:
        kept = f"The engine cache was kept: {cache['refused']}. "
    else:
        kept = ""
    _flash(f"Reclaimed {hb(out['total'] + cache['bytes'])}.", "ok",
           detail=("; ".join(bits) + ". " if bits else "") + kept
           + "Every stored week, score, report and submission file is "
           "kept; the sealed validation record and the hub clone were not "
           "touched.")
    return _back(request, "/storage")
