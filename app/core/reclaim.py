"""PRODUCTION: the storage-reclaim policy (server storage panel, retro
week/season pruning).

Storage reclaim: what may be deleted, what must survive, as code.

LOAD-BEARING (never touched here):
  * stored week samples (samples.json / .gz): every score, frame and export
    derives from them;
  * scores.json, run_meta.json, playback caches, season report HTML;
  * a workroot's record: results.json, pf_status.json, cells.json,
    scores_pf.json, report.html and its bundle, every submission CSV;
  * the sealed record (app/state/retro_seal) and the hub clone: refused
    wholesale by path resolution before any other rule.

INTERMEDIATE (deletable once its week or run is COMPLETE):
  * per-cell fit trees (<location>_r<n>/: BNGL copies, .net, .cdat/.gdat,
    trajectories, pf_state.npz);
  * runner scripts, shard lists, prep manifests, cells_done/, HALT flags,
    .prog files.

Every function refuses protected trees itself, so no caller mistake can
reach them. An interrupted week keeps every checkpoint and resumes.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from app.core import retro
from app.core.runs import APP_STATE

#: survives a week's prune: samples (both forms), the quantile sidecar, and
#: the Oracle step's oracle.json and donor bank
WEEK_KEEP = (retro.SAMPLES_JSON, retro.SAMPLES_GZ, retro.QUANTILES_NAME,
             "oracle.json", "oracle_bank")

#: a per-cell fit tree inside a workroot or week: <location>_r<replicate>
CELL_DIR_RE = re.compile(r".+_r\d+$")

#: per-shard scaffolding (runner scripts + stderr, cell lists, status files;
#: unnumbered pf_runner.py is pre-sharding). The MERGED pf_status.json and
#: cells.json are the record and deliberately do not match.
WORKROOT_SCAFFOLD_RE = re.compile(
    r"^(pf_runner(_\d+)?\.(py|err)|pf_cells_\d+\.json|pf_status_\d+\.json)$")

#: dry-run estimate (gzip -6 measured 3.67x); the perform step reports real bytes
EST_GZ_RATIO = 3.5

#: research season trees (the two-strain evidence) the sweep may COMPRESS
#: (lossless) but never prune or delete
RESEARCH_ROOTS = (APP_STATE / "retro_2s",)


def _protected_roots() -> list:
    """The trees reclaim never touches: the sealed record, the hub clone, and
    FLUBNF_PROTECT_ROOTS (os.pathsep-separated, read per call) so a research
    arm outside app/state keeps the per-cell evidence a diagnostic needs."""
    from flubnf.settings import HUB
    roots = [APP_STATE / "retro_seal", Path(HUB)]
    extra = os.environ.get("FLUBNF_PROTECT_ROOTS", "")
    roots.extend(Path(x) for x in extra.split(os.pathsep) if x.strip())
    return roots


def is_protected(p: Path) -> bool:
    """True when a path is inside (or is) a protected root, resolved first so
    a symlink into one is caught. Unresolvable paths count as protected."""
    try:
        rp = Path(p).resolve()
    except OSError:
        return True
    for root in _protected_roots():
        try:
            r = Path(root).resolve()
        except OSError:
            continue
        if rp == r or rp.is_relative_to(r):
            return True
    return False


def _size(p: Path) -> int:
    """Bytes under one entry: a file's size, or a directory tree's."""
    try:
        st = os.lstat(p)
    except OSError:
        return 0
    if not p.is_dir() or p.is_symlink():
        return st.st_size
    return retro.dir_size(p)


# ------------------------------------------------------------ week pruning

def week_intermediates(wd: Path) -> list:
    """Entries in a COMPLETED week directory that are intermediates: every
    entry except the samples record. An incomplete week (no samples yet)
    has no intermediates by definition -- its checkpoints are its record."""
    wd = Path(wd)
    if retro.samples_file(wd) is None or is_protected(wd):
        return []
    try:
        return sorted(p for p in wd.iterdir() if p.name not in WEEK_KEEP)
    except OSError:
        return []


def prune_week(wd: Path) -> int:
    """Remove a completed week's fit intermediates. Returns bytes freed;
    0 when the week is incomplete or protected (nothing is touched)."""
    freed = 0
    for p in week_intermediates(wd):
        freed += _delete(p)
    return freed


def season_week_dirs(root: Path) -> list:
    """Completed week directories in one season tree, ascending."""
    return [p.parent for p in retro.season_sample_files(root)]


def prune_season(root: Path) -> dict:
    """Prune every completed week in a season tree. Refuses protected
    trees wholesale. Returns {"bytes": freed, "weeks": n_pruned}."""
    root = Path(root)
    if is_protected(root):
        return {"bytes": 0, "weeks": 0}
    freed = weeks = 0
    for wd in season_week_dirs(root):
        b = prune_week(wd)
        if b:
            freed += b
            weeks += 1
    return {"bytes": freed, "weeks": weeks}


# -------------------------------------------------------- workroot pruning

def workroot_complete(w: Path) -> bool:
    """A console run's workroot is complete once its assembled record
    exists: results.json is written last, after report and submissions."""
    return (Path(w) / "results.json").is_file()


def workroot_intermediates(w: Path) -> list:
    """Intermediates inside a COMPLETED workroot: the per-cell fit trees,
    the per-shard runner scripts and their stderr, the per-shard cell lists
    and status files, and .prog progress files. The assembled record
    (results, scores, the MERGED status, cells.json, report, bundle,
    submissions) stays untouched."""
    w = Path(w)
    if not workroot_complete(w) or is_protected(w):
        return []
    out = []
    try:
        scopes = [w]
        # a research run's pf2s/ has the same layout as the top level
        if (w / "pf2s").is_dir() and not (w / "pf2s").is_symlink():
            scopes.append(w / "pf2s")
        for scope in scopes:
            for p in sorted(scope.iterdir()):
                if (p.is_dir() and not p.is_symlink()
                        and CELL_DIR_RE.match(p.name)):
                    out.append(p)
                elif (WORKROOT_SCAFFOLD_RE.match(p.name)
                      or p.name.endswith((".prog", ".tmp"))):
                    out.append(p)
    except OSError:
        return []
    return out


def prune_workroot(w: Path) -> int:
    """Remove a completed workroot's fit intermediates. Returns bytes
    freed; 0 when the run is incomplete or protected."""
    freed = 0
    for p in workroot_intermediates(w):
        freed += _delete(p)
    return freed


def _delete(p: Path) -> int:
    """Delete one intermediate entry, returning the bytes it held. The
    protection barrier is re-checked here, per entry, so no list built
    earlier can carry a deletion into a protected tree."""
    if is_protected(p):
        return 0
    size = _size(p)
    try:
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
        else:
            p.unlink(missing_ok=True)
    except OSError:
        return 0
    return size


# ----------------------------------------------------- compression migration

def compressible_files(root: Path) -> list:
    """Stored weeks in one season tree still in the plain-JSON form. The
    sealed record is refused wholesale (its bytes are its evidence)."""
    root = Path(root)
    if is_protected(root):
        return []
    return [p for p in retro.season_sample_files(root)
            if p.name == retro.SAMPLES_JSON and not is_protected(p)]


def compress_tree(root: Path) -> dict:
    """Compress every plain-JSON stored week in one season tree, preserving
    each file's mtime (caches stay valid). Returns {"saved", "files"}."""
    saved = files = 0
    for p in compressible_files(root):
        try:
            before = p.stat().st_size
            gz = retro.compress_samples_file(p)
            saved += before - gz.stat().st_size
            files += 1
        except OSError:
            continue              # one stuck file must not sink the sweep
    return {"saved": saved, "files": files}


# ------------------------------------------------------------ the full plan

def _season_entries(retro_root: Path, skip: set) -> list:
    """Season trees under the retro root (live and archived), minus skipped
    (busy) names and protected trees. Symlinked seasons are operated on
    through the link, as every read/write path does."""
    root = Path(retro_root)
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.iterdir()):
        if p.name in skip or not (p.is_dir() or p.is_symlink()):
            continue
        if not (p / "weeks").is_dir() or is_protected(p):
            continue
        out.append(p)
    return out


def survey(retro_root: Path, workroot_base: Path,
           research_roots=None,
           skip_seasons: set | None = None,
           skip_workroots: set | None = None) -> dict:
    """The dry run: what a reclaim would free, by category, touching
    nothing. The perform step recomputes this same plan and refuses to act
    if the counts moved (the storage panel's stale-confirmation contract).
    """
    if research_roots is None:
        research_roots = RESEARCH_ROOTS      # read at call time: patchable
    skip_seasons = set(skip_seasons or ())
    skip_workroots = set(skip_workroots or ())
    plan = {"week_bytes": 0, "weeks": 0, "season_ids": [],
            "workroot_bytes": 0, "workroots": 0, "workroot_ids": [],
            "compress_bytes": 0, "compress_files": 0, "compress_ids": [],
            "est_compress_saved": 0, "total_est": 0}
    managed = _season_entries(retro_root, skip_seasons)
    research = []
    for rr in research_roots:
        rr = Path(rr)
        if rr.is_dir() and not is_protected(rr):
            research += [p for p in sorted(rr.iterdir())
                         if (p / "weeks").is_dir() and not is_protected(p)]
    for entry in managed:
        pruned_here = False
        for wd in season_week_dirs(entry):
            items = week_intermediates(wd)
            if items:
                b = sum(_size(p) for p in items)
                if b:
                    plan["week_bytes"] += b
                    plan["weeks"] += 1
                    pruned_here = True
        if pruned_here:
            plan["season_ids"].append(entry.name)
    # research trees are compress-only
    for entry in managed + research:
        comp = compressible_files(entry)
        if comp:
            b = sum(p.stat().st_size for p in comp)
            plan["compress_bytes"] += b
            plan["compress_files"] += len(comp)
            plan["compress_ids"].append(entry.name)
    base = Path(workroot_base)
    if base.is_dir():
        for w in sorted(d for d in base.iterdir() if d.is_dir()):
            if w.name in skip_workroots:
                continue
            items = workroot_intermediates(w)
            if items:
                b = sum(_size(p) for p in items)
                if b:
                    plan["workroot_bytes"] += b
                    plan["workroots"] += 1
                    plan["workroot_ids"].append(w.name)
    plan["est_compress_saved"] = int(
        plan["compress_bytes"] * (1 - 1 / EST_GZ_RATIO))
    plan["total_est"] = (plan["week_bytes"] + plan["workroot_bytes"]
                         + plan["est_compress_saved"])
    return plan


def plan_counts(plan: dict) -> tuple:
    """The stale-confirmation token: (pruned weeks, pruned workroots,
    files to compress)."""
    return (int(plan["weeks"]), int(plan["workroots"]),
            int(plan["compress_files"]))


def execute(retro_root: Path, workroot_base: Path,
            research_roots=None,
            skip_seasons: set | None = None,
            skip_workroots: set | None = None) -> dict:
    """Perform the reclaim the survey described, against the tree as it
    stands NOW (every busy and protection rule re-applied per entry).
    Returns actual bytes freed per category."""
    if research_roots is None:
        research_roots = RESEARCH_ROOTS      # read at call time: patchable
    skip_seasons = set(skip_seasons or ())
    skip_workroots = set(skip_workroots or ())
    out = {"week_bytes": 0, "weeks": 0, "workroot_bytes": 0, "workroots": 0,
           "compress_saved": 0, "compress_files": 0}
    for entry in _season_entries(retro_root, skip_seasons):
        r = prune_season(entry)
        out["week_bytes"] += r["bytes"]
        out["weeks"] += r["weeks"]
        c = compress_tree(entry)
        out["compress_saved"] += c["saved"]
        out["compress_files"] += c["files"]
    for research in research_roots:
        research = Path(research)
        if not research.is_dir() or is_protected(research):
            continue
        for p in sorted(research.iterdir()):
            if (p / "weeks").is_dir() and not is_protected(p):
                c = compress_tree(p)
                out["compress_saved"] += c["saved"]
                out["compress_files"] += c["files"]
    base = Path(workroot_base)
    if base.is_dir():
        for w in sorted(d for d in base.iterdir() if d.is_dir()):
            if w.name in skip_workroots:
                continue
            b = prune_workroot(w)
            if b:
                out["workroot_bytes"] += b
                out["workroots"] += 1
    out["total"] = (out["week_bytes"] + out["workroot_bytes"]
                    + out["compress_saved"])
    return out
