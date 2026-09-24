"""Storage (GET /storage, alias GET /runs): the disk inventory, the run
ledger, and delete, clear and reclaim.

An APIRouter server.py includes before the forecast routes, so POST
/runs/clear stays ahead of GET /runs/{run_id}: the first route a path
matches names the Allow header of a wrong-method request. datasets_ui reads
_storage_inventory, _storage_target and _tree_size here.
"""
from __future__ import annotations

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
from app.ui.shared import (_back, _flash, _invalidate_scans, _outcome_chips,
                           _run_label, _scan_archive_dates)
from app.ui.state import _status
from app.ui.templating import templates

router = APIRouter()


# === Storage (/storage, /runs): inventory, delete, clear, reclaim -> runs.html ===
# The sealed records and the hub clone are never deletable (no control, and
# refused again on POST); running/paused trees are refused server-side.
# Every destructive POST requires a confirmation naming exactly what the
# user saw (name or count); a stale confirmation deletes nothing.

@ttlcache.ttl_cache(ttl_s=60.0)
def _tree_size(path: str) -> int:
    from app.core import retro
    return retro.dir_size(Path(path))


def _storage_protected(p: Path) -> bool:
    """True when a path lies inside a sealed record or the hub clone."""
    from flubnf.settings import HUB
    try:
        rp = Path(p).resolve()
    except OSError:
        return True                      # unresolvable: refuse, never guess
    for root in [base for base, _ in _sealed_roots()] + [HUB]:
        try:
            r = Path(root).resolve()
            if rp == r or rp.is_relative_to(r):
                return True
        except OSError:
            continue
    return False


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


def _storage_inventory() -> dict:
    """Storage panel rows with sizes: workroots, live retro seasons, retro
    archives, report archives, your datasets (each with a busy flag), plus
    the protected trees (no controls). total_bytes/total_h sum the managed
    categories only, each byte once: a dataset adds its own folder (the
    upload and its replays), its runs being counted as workroots."""
    import re as _re
    from app.core import retro
    from app.core.runs import APP_STATE, is_research, run_display
    from app.ui import datasets_ui as _dsu
    from flubnf.settings import HUB
    inv = {"workroots": [], "retro": [], "retro_archives": [],
           "report_archives": [], "datasets": [], "protected": [],
           "total_bytes": 0, "total_h": ""}
    live_ids = _live_workroot_ids()
    console_busy = bool(_status.get("running"))
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
            inv["workroots"].append({
                "id": p.name, "size_h": retro.human_bytes(size),
                "label": disp["what"], "when": disp["when"],
                "scope": disp["scope"], "recorded": disp["recorded"],
                "research": is_research(row.get("spec", "")),
                "modified": _runs.is_modified(row.get("spec", "")),
                "busy": p.name in live_ids,
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
                    "status": st, "busy": st in _RETRO_ACTIVE})
                continue
            m = _re.match(r"(\d{4}-\d{2})", p.name)
            if m and retro.archive_stamp_of(p.name, m.group(1)):
                season = m.group(1)
                stamp = retro.archive_stamp_of(p.name, season)
                size = _tree_size(str(p))
                inv["total_bytes"] += size
                inv["retro_archives"].append({
                    "id": p.name, "season": season,
                    "when": retro.stamp_human(stamp),
                    "size_h": retro.human_bytes(size),
                    "busy": _season_status(season) in _RETRO_ACTIVE})
    arch = APP_STATE / "archive"
    for d in reversed(_scan_archive_dates(arch)):
        size = _tree_size(str(arch / d))
        inv["total_bytes"] += size
        inv["report_archives"].append({
            "id": d, "size_h": retro.human_bytes(size),
            "busy": console_busy})
    inv["datasets"] = _dsu.storage_rows(inv["workroots"])
    inv["total_bytes"] += sum(d["own_bytes"] for d in inv["datasets"])
    for label, p in (("Production engine record", retro_seasons.RETRO_RESEAL),
                     ("Sealed validation record", retro_seasons.RETRO_SEAL),
                     ("FluSight hub clone", HUB)):
        if Path(p).exists():
            inv["protected"].append({
                "label": label, "path": str(p),
                "size_h": retro.human_bytes(_tree_size(str(p)))})
    inv["total_h"] = retro.human_bytes(inv["total_bytes"])
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


@router.get("/storage", response_class=HTMLResponse)
@router.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request):
    """Storage tab: storage panel, then the run ledger. /runs is a kept
    alias (old reports and bookmarks link it)."""
    from app.core.runs import APP_STATE, is_research
    from app.core import retro
    ledger = Ledger()
    rows = ledger.rows(50)
    for r in rows:
        # the research badge carries the tag, so the label stays untagged
        r["label"] = _run_label(r["run_id"], r.get("spec", ""), tag=False)
        r["research"] = is_research(r.get("spec", ""))
        r["modified"] = _runs.is_modified(r.get("spec", ""))
        r["chips"] = _outcome_chips(r.get("outcome", ""))
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
        _flash("The run ledger has no completed rows to clear.")
        return _back(request, "/storage")
    if confirm != str(len(ids)):
        _flash("The ledger changed since this page was rendered "
               f"({len(ids)} clearable row{'' if len(ids) == 1 else 's'} "
               "now). Nothing was cleared; review and confirm again.")
        return _back(request, "/storage")
    n = ledger.delete_runs(ids)
    _invalidate_scans()
    _flash(f"Cleared {n} completed row{'' if n == 1 else 's'} from the run "
           "ledger. No data on disk was deleted: the runs' workroots stay "
           "in the storage panel until deleted there.")
    return _back(request, "/storage")


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
            return None, (f"The run {ident} is active; its workroot cannot "
                          "be deleted while it runs.")
        base = APP_STATE / "workroots"
    elif kind == "retro-season":
        if not _valid_season(ident):
            return None, "Unrecognized season name."
        if _season_status(ident) in _RETRO_ACTIVE:
            return None, (f"{ident} is replaying (status: "
                          f"{_season_status(ident)}); stop it first.")
        p = retro_seasons.RETRO_ROOT / ident
        base = retro_seasons.RETRO_ROOT
    elif kind == "retro-archive":
        m = _re.match(r"(\d{4}-\d{2})", ident or "")
        stamp = (retro.archive_stamp_of(ident, m.group(1)) if m else "")
        if not stamp:
            return None, "Unrecognized archived run identifier."
        season = m.group(1)
        if _season_status(season) in _RETRO_ACTIVE:
            return None, (f"{season} is replaying; stop it before deleting "
                          "its archived runs.")
        p = retro_seasons.RETRO_ROOT / ident
        base = retro_seasons.RETRO_ROOT
    elif kind == "report-archive":
        if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", ident or ""):
            return None, "Unrecognized report archive date."
        if _status.get("running"):
            return None, ("A console run is in progress and may be writing "
                          "the archive; stop it first.")
        p = APP_STATE / "archive" / ident
        base = APP_STATE / "archive"
    else:
        return None, "Unrecognized storage kind."
    # Containment by construction (separator-free identifiers). Not resolved
    # here: a symlinked season is legitimate (delete_tree removes the link),
    # but _storage_protected resolves, so a link into a protected tree fails.
    assert p.parent == Path(base), "storage target escaped its parent"
    if _storage_protected(p):
        return None, ("That tree is protected (the sealed validation "
                      "record and the hub clone are never deletable from "
                      "the interface).")
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
        _flash(f"{why} Nothing was deleted.")
        return _back(request, "/storage")
    if confirm != ident:
        _flash("The deletion was not confirmed, so nothing was deleted.")
        return _back(request, "/storage")
    size_h = retro.human_bytes(retro.dir_size(p))
    try:
        retro.delete_tree(p)
    except Exception as e:
        _flash(f"Could not delete {ident}: {type(e).__name__}: "
               f"{str(e)[:160]}. Nothing else changed.")
        return _back(request, "/storage")
    _invalidate_scans()
    noun = {"workroot": "workroot", "retro-season": "retrospective season",
            "retro-archive": "archived retrospective run",
            "report-archive": "report archive"}.get(kind, "entry")
    tail = (" Its ledger row remains as the run's record."
            if kind == "workroot" else "")
    _flash(f"Deleted the {noun} {ident}: {size_h} freed.{tail}")
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
        _flash("No completed run workroots are on disk to delete.")
        return _back(request, "/storage")
    if confirm != str(len(items)):
        _flash("The storage panel changed since this page was rendered "
               f"({len(items)} deletable workroot"
               f"{'' if len(items) == 1 else 's'} now). Nothing was "
               "deleted; review and confirm again.")
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
    _flash(f"Deleted {n} completed run workroot{'' if n == 1 else 's'}: "
           f"{retro.human_bytes(freed)} freed. Every ledger row is kept "
           "and shows a dash for disk use.")
    return _back(request, "/storage")


# === Storage: reclaim (prune completed intermediates, compress samples) ===
# GET is a dry run by category; POST performs it behind a counts
# confirmation. Classification lives in app/core/reclaim.py; samples gzip
# losslessly with mtimes kept, so every score and export is reproducible.

def _reclaim_skips() -> tuple:
    """(season entry names, workroot names) the reclaim must not touch right
    now: seasons replaying or mid-finalize, and the active run's workroot."""
    skip_seasons = {s for s in retro_seasons._known_seasons()
                    if _season_status(s) in _RETRO_ACTIVE}
    for key, job in list(_results_jobs.items()):
        if job and not job["done"].is_set():
            skip_seasons.add(Path(key).name)
    return skip_seasons, set(_live_workroot_ids())


def _reclaim_survey() -> dict:
    from app.core import reclaim
    from app.core.runs import APP_STATE
    skip_seasons, skip_workroots = _reclaim_skips()
    return reclaim.survey(retro_seasons.RETRO_ROOT, APP_STATE / "workroots",
                          skip_seasons=skip_seasons,
                          skip_workroots=skip_workroots)


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
        _flash("There is nothing to reclaim: no completed week or run "
               "carries intermediates and every stored week is already "
               "compressed.")
        return _back(request, "/storage")
    if confirm != counts:
        _flash("The storage panel changed since this report was made "
               "(a run finished or files moved). Nothing was deleted; "
               "review the reclaim report and confirm again.")
        return _back(request, "/storage")
    skip_seasons, skip_workroots = _reclaim_skips()
    out = reclaim.execute(retro_seasons.RETRO_ROOT, APP_STATE / "workroots",
                          skip_seasons=skip_seasons,
                          skip_workroots=skip_workroots)
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
    _flash(f"Reclaimed {hb(out['total'])}: " + "; ".join(bits) + ". Every "
           "stored week, score, report, and submission file is kept; the "
           "sealed validation record and the hub clone were not touched.")
    return _back(request, "/storage")
