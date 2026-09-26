"""The dataset store: ROOT, ids and folders, ingest() of one upload and
_materialize(), which writes the FluSight-shaped files an engine reads."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import time
import uuid
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Optional

#: the package itself: ROOT, get, resolve and MAX_SNAPSHOT_FILES are
#: read through it at call time, where tests monkeypatch them
from app.core import datasets as _pkg
from app.core.runs import APP_STATE

from .checks import KINDS
from .parsing import _fmt_num, _int_or_float, saturday_on_or_before, slug
from .reading import validate
from .report import DEFAULT_LIMITS, DatasetError, Limits, Problem, Report

if TYPE_CHECKING:
    from .dataset import Dataset

#: the dataset store; tests monkeypatch it (on the package, see _root)
ROOT = APP_STATE / "datasets"

#: manifest schema (part of the identity digest)
SCHEMA = 1
#: file names inside a dataset folder
SOURCE_FILE = "source.csv"
SERIES_FILE = "series.csv"
LOCATIONS_FILE = "locations.csv"
META_FILE = "meta.json"
VINTAGE_DIR = "vintages"
VINTAGE_PREFIX = "target-hospital-admissions_"
#: dataset ids: slug + '-' + 12 hex of the identity digest
ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,31}-[0-9a-f]{12}")


def _root() -> Path:
    return Path(_pkg.ROOT)


def _atomic_write_text(p: Path, text: str) -> None:
    """Write beside, then os.replace (the repo's atomic-write pattern)."""
    tmp = p.with_name(p.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)


def _csv_text(header, rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def identity_digest(sha256: str, *, kind: str, week_start_sunday: bool,
                    target: Optional[str], columns: dict) -> str:
    """sha256 over the upload's bytes digest AND every ingest option that
    changes the stored series, so the same bytes read differently get a
    different id (and a spec pinning the digest notices). The weekday
    shift follows from the bytes; ``week_start_sunday`` (a Sunday file
    moved +6 days) keeps the ids the earlier Sunday option minted."""
    opts = {"schema": SCHEMA, "sha256": sha256, "kind": kind,
            "week_start_sunday": bool(week_start_sunday), "target": target,
            "columns": {k: v for k, v in sorted(columns.items())}}
    return hashlib.sha256(json.dumps(opts, sort_keys=True).encode()
                          ).hexdigest()


def valid_id(dataset_id) -> bool:
    return isinstance(dataset_id, str) and bool(ID_RE.fullmatch(dataset_id))


def _dir(dataset_id) -> Path:
    """The dataset's folder, refusing any id that is malformed or resolves
    outside the store (path traversal, symlinks)."""
    if not valid_id(dataset_id):
        raise DatasetError(f"Not a dataset id: {dataset_id!r}.")
    root = _root().resolve()
    p = (root / dataset_id).resolve()
    if p.parent != root:
        raise DatasetError(f"Dataset {dataset_id!r} resolves outside the "
                           "dataset store; refused.")
    return p


def default_name(filename: str, targets=(), target: Optional[str] = None
                 ) -> str:
    """A dataset's name when none is given: the file's name without its
    extension, and the target when the file holds several ('flu.csv' with
    'wk inc flu hosp' chosen -> 'flu (wk inc flu hosp)'), so datasets
    stored from one file's targets are told apart. At most 80
    characters, the target kept whole when it fits."""
    stem = Path(str(filename or "")).stem or "dataset"
    if target and len(targets) > 1:
        tail = f" ({target})"
        return (stem[:max(1, 80 - len(tail))] + tail)[:80]
    return stem[:80]


def _checked_kind(kind):
    """``kind`` as declared, None when it was not; DatasetError (with a
    kind_invalid problem) for a kind that is not one of KINDS."""
    kind = kind or None
    if kind is not None and kind not in KINDS:
        raise DatasetError(f"Declare the value kind: one of {', '.join(KINDS)}.",
                           [Problem("kind_invalid", f"Value kind {kind!r} is "
                                    f"not one of {', '.join(KINDS)}.")])
    return kind


def _tmp_dir() -> Path:
    """A fresh folder beside the store: the dataset is built there and
    renamed into place, so a reader never sees a half-written one."""
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / f".tmp-{uuid.uuid4().hex}"
    tmp.mkdir()
    return tmp


def _refuse(rep: Report) -> None:
    """DatasetError (with the problems and the report) for a report that
    holds any problem: nothing is stored."""
    if not rep.ok:
        raise DatasetError(
            f"{len(rep.problems)} problem(s) in the upload; nothing was "
            "stored.", rep.problems, rep)


def _store(tmp: Path, rep: Report, name: str, *, kind, filename: str,
           extra=None, source_text: str | None = None) -> Dataset:
    """Store the valid report's dataset built in ``tmp``: the id is the
    name's slug plus the identity digest, so identical bytes with identical
    options under the same name return the dataset already stored;
    ``source_text`` is written as source.csv when the upload did not tee
    one. ``kind`` None takes the kind the values show."""
    _refuse(rep)
    declared = kind is not None
    kind = kind or rep.summary["inferred_kind"]
    digest = identity_digest(
        rep.sha256, kind=kind,
        week_start_sunday=bool(rep.summary.get("week_start_sunday")),
        target=rep.summary.get("target"), columns=rep.columns)
    dataset_id = f"{slug(name)}-{digest[:12]}"
    final = _dir(dataset_id)
    if (final / META_FILE).is_file():
        return _pkg.get(dataset_id)
    if source_text is not None:
        _atomic_write_text(tmp / SOURCE_FILE, source_text)
    _materialize(tmp, rep, name=name, dataset_id=dataset_id, digest=digest,
                 kind=kind, declared=declared, filename=filename, extra=extra)
    try:
        os.rename(tmp, final)
    except OSError:
        if (final / META_FILE).is_file():      # a concurrent twin won
            return _pkg.get(dataset_id)
        raise
    return _pkg.get(dataset_id)


def ingest(source, name: Optional[str], *, kind: Optional[str] = None,
           week_start_sunday: bool = False, target: Optional[str] = None,
           limits: Limits = DEFAULT_LIMITS, filename: str = "",
           columns: Optional[dict] = None) -> "Dataset":
    """Validate and store one upload; returns the stored Dataset.

    ``name`` None or '' takes default_name (the file name, with the target
    of a file that holds several). ``kind`` None or '' takes the kind the
    values show (whole numbers are counts); ``columns`` is validate's
    column mapping; ``week_start_sunday`` is accepted and ignored (see
    validate). Raises DatasetError (with ``.problems``) and writes nothing
    when any problem is found. Re-ingesting identical bytes with identical
    options under the same name returns the existing dataset (idempotent).
    The folder is built beside the store and renamed into place, so a
    reader never sees a half-written dataset."""
    kind = _checked_kind(kind)
    tmp = _tmp_dir()
    try:
        with open(tmp / SOURCE_FILE, "wb") as tee:
            rep = validate(source, kind=kind, target=target, limits=limits,
                           columns=columns, _tee=tee)
        _refuse(rep)
        name = name or default_name(filename, rep.targets,
                                    rep.summary.get("target"))
        return _store(tmp, rep, name, kind=kind, filename=filename)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def _materialize(d: Path, rep: Report, *, name, dataset_id, digest, kind,
                 declared, filename, extra=None) -> None:
    recs = rep.records
    names = sorted({r[1] for r in recs}, key=str.casefold)
    width = max(2, len(str(len(names))))
    key_of = {n: f"c{i:0{width}d}" for i, n in enumerate(names, 1)}
    src_of = {r[1]: r[2] for r in recs}

    # latest population per group (by week, then by as_of)
    pop_latest, pop_varies = {}, {}
    for a, n, _, dd, _, p in sorted(recs, key=lambda r: (r[3], r[0] or date.min)):
        if p is not None:
            if n in pop_latest and pop_latest[n] != p:
                pop_varies[n] = True
            pop_latest[n] = p
    has_pop = rep.summary["has_population"]

    # normalized series: every row, every snapshot
    series_rows = [
        ((a.isoformat() if a else ""), dd.isoformat(), key_of[n], n,
         src_of[n], _fmt_num(v), (_fmt_num(p) if p is not None else ""))
        for a, n, _, dd, v, p in sorted(
            recs, key=lambda r: (r[0] or date.min, key_of[r[1]], r[3]))]
    _atomic_write_text(d / SERIES_FILE, _csv_text(
        ("as_of", "date", "location", "location_name", "source_key", "value",
         "population"), series_rows))

    _atomic_write_text(d / LOCATIONS_FILE, _csv_text(
        ("abbreviation", "location", "location_name", "population",
         "source_key"),
        [(key_of[n], key_of[n], n,
          (str(int(round(pop_latest[n]))) if has_pop and n in pop_latest
           else ""), src_of[n]) for n in names]))

    # vintages: the FluSight archive shape
    snapshots = {}
    for r in recs:
        snapshots.setdefault(r[0], []).append(r)
    as_of_map, used = {}, {}
    if rep.summary["has_as_of"]:
        for a in sorted(snapshots):
            k = saturday_on_or_before(a).isoformat()
            as_of_map.setdefault(k, []).append(a.isoformat())
            used[k] = a                              # latest as_of wins
    else:
        k = max(r[3] for r in recs).isoformat()
        used[k] = None
    vdir = d / VINTAGE_DIR
    vdir.mkdir()
    for k, a in used.items():
        rows = []
        for _, n, _, dd, v, p in sorted(snapshots[a],
                                        key=lambda r: (r[3], key_of[r[1]])):
            rate = ""
            if kind == "count" and has_pop and p:
                rate = f"{v / p * 1e5:.6g}"
            rows.append((dd.isoformat(), key_of[n], n, _fmt_num(v), rate))
        _atomic_write_text(vdir / f"{VINTAGE_PREFIX}{k}.csv", _csv_text(
            ("date", "location", "location_name", "value", "weekly_rate"),
            rows))

    groups = []
    for n in names:
        ds = sorted({r[3] for r in recs if r[1] == n})
        groups.append({
            "name": n, "key": key_of[n], "source_key": src_of[n],
            "population": (_int_or_float(pop_latest[n])
                           if has_pop and n in pop_latest else None),
            "population_varies": bool(pop_varies.get(n)),
            "rows": sum(1 for r in recs if r[1] == n),
            "first": ds[0].isoformat(), "last": ds[-1].isoformat(),
            "national": n == rep.summary.get("national_group")})
    s = rep.summary
    meta = {
        "schema": SCHEMA,
        "id": dataset_id,
        "name": name,
        "digest": digest,
        "sha256": rep.sha256,
        "bytes": rep.n_bytes,
        "filename": filename,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "format": s["format"],
        "columns": rep.columns,
        "options": {"kind": kind, "week_start_sunday": s["week_start_sunday"],
                    "target": s["target"],
                    "date_shift_days": s["date_shift_days"],
                    "kind_from": "declared" if declared else "values"},
        "read_as": {"encoding": s["encoding"], "delimiter": s["delimiter"]},
        "kind": kind,
        "target": s["target"],
        "rows": s["rows"],
        "groups": groups,
        "date_range": [s["first"], s["last"]],
        "has_population": has_pop,
        "has_as_of": s["has_as_of"],
        "vintages": sorted(used),
        "as_of_map": as_of_map,
        "as_of_used": {k: (a.isoformat() if a else None)
                       for k, a in sorted(used.items())},
        "national_group": s.get("national_group"),
        "na_dropped": int(s.get("na_dropped") or 0),
        "warnings": list(rep.warnings),
        **(extra or {}),
    }
    _atomic_write_text(d / META_FILE, json.dumps(meta, indent=1) + "\n")
