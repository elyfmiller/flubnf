"""Snapshot folders: several files, one per as_of, validated and stored
as ONE vintage-true dataset (validate_snapshots, ingest_snapshots)."""
from __future__ import annotations

import hashlib
import re
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Optional

#: the package itself: ROOT, get, resolve and MAX_SNAPSHOT_FILES are
#: read through it at call time, where tests monkeypatch them
from app.core import datasets as _pkg

from .parsing import _fmt_num, saturday_on_or_before
from .reading import validate
from .report import (
    DEFAULT_LIMITS,
    MAX_EXAMPLES,
    Limits,
    Problem,
    Report,
    _examples,
)
from .store import _checked_kind, _csv_text, _refuse, _store, _tmp_dir, ingest

if TYPE_CHECKING:
    from .dataset import Dataset


# ------------------------------------------------------ snapshot folders
# Several files, one per as_of, each a normal weekly table (the hub
# archive's shape: target-hospital-admissions_2024-10-05.csv, ...), read
# as ONE vintage-true dataset. Each file goes through validate() as it is;
# its as_of comes from an as_of column inside it, else from the one date
# its name carries. The as_of rules are the one-file rules: keyed by the
# Saturday on or before it, and no snapshot week after its as_of.

#: a date in a snapshot file's name: 2024-10-05, 2024_10_05 or 20241005,
#: never inside a longer number
_NAME_DATE = re.compile(r"(?<!\d)(\d{4})([-_]?)(\d{2})\2(\d{2})(?!\d)")
#: at most this many files in one snapshot upload (ten years of weeks)
MAX_SNAPSHOT_FILES = 520
#: a snapshot upload's original files, kept beside source.csv
SOURCES_DIR = "sources"
#: problems that ask for a choice every file shares (a column mapping, a
#: target): said once, for the first file that asks
_SHARED_CHOICE = ("missing_columns", "ambiguous_columns", "column_unknown",
                  "target_required")


def _base(filename) -> str:
    """A file's own name, whatever folder a browser or a shell put before
    it ('flu/2024-10-05.csv' -> '2024-10-05.csv')."""
    return str(filename or "").replace("\\", "/").rsplit("/", 1)[-1]


def name_dates(filename) -> list:
    """The distinct real dates a file's name carries, in order."""
    out = []
    for m in _NAME_DATE.finditer(_base(filename)):
        try:
            d = date(int(m[1]), int(m[3]), int(m[4]))
        except ValueError:
            continue
        if d not in out:
            out.append(d)
    return out


def default_snapshot_name(filenames) -> str:
    """A snapshot upload's name when none is given: the folder the files
    came from, else the first file's name without its date
    ('admissions_2024-10-05.csv' -> 'admissions'), else 'snapshots'."""
    parents = {str(f or "").replace("\\", "/").rpartition("/")[0]
               for f in filenames}
    if len(parents) == 1:
        folder = parents.pop().rstrip("/").rsplit("/", 1)[-1]
        if folder and folder != ".":
            return folder[:80]
    stem = Path(_base(filenames[0]) if filenames else "").stem
    stem = _NAME_DATE.sub("", stem).strip(" _-.")
    return (stem or "snapshots")[:80]


def _tee_path(folder: Path, filename: str) -> Path:
    """Where an original file is kept: its own name, numbered when two
    folders gave the same one."""
    base = _base(filename) or "snapshot.csv"
    p, i = folder / base, 2
    while p.exists():
        p = folder / f"{Path(base).stem}-{i}{Path(base).suffix}"
        i += 1
    return p


def _validate_kept(fname, src, tee_dir, **kw) -> Report:
    """validate() one file, its bytes kept in ``tee_dir`` when given."""
    if tee_dir is None:
        return validate(src, **kw)
    with open(_tee_path(tee_dir, fname), "wb") as tee:
        return validate(src, _tee=tee, **kw)


def _files_said(files) -> str:
    """'a.csv' / 'a.csv, b.csv, c.csv and 4 more'."""
    files = list(files)
    more = len(files) - MAX_EXAMPLES
    return _examples(files) + (f" and {more} more" if more > 0 else "")


def validate_snapshots(files, *, kind: Optional[str] = None,
                       target: Optional[str] = None,
                       limits: Limits = DEFAULT_LIMITS,
                       columns: Optional[dict] = None,
                       _tee_dir: Optional[Path] = None) -> Report:
    """Validate several snapshot files, ``[(filename, source), ...]``, as
    one dataset; a single file is validate()'s, exactly as before.

    Each file is read by validate() with the same kind, target and column
    mapping; its problems come back named by the file (those of the first
    few files, and a count of the rest). Then, across the files: each
    needs an as_of (an as_of column, or one date in its name; both must
    agree), one file per as_of Saturday, no week after its file's as_of,
    the same groups and the same population column in every file, and the
    limits over all of them. The report's summary is the whole dataset's,
    with ``snapshot_files`` listing each file and its as_of."""
    files = list(files)
    if len(files) == 1:
        name, src = files[0]
        return _validate_kept(name, src, _tee_dir, kind=kind, target=target,
                              limits=limits, columns=columns)
    rep = Report()
    if not files:
        rep.add("empty", "No files were given.")
        return rep
    if len(files) > _pkg.MAX_SNAPSHOT_FILES:
        rep.add("limit_files", f"{len(files)} files were given; one upload "
                f"holds at most {_pkg.MAX_SNAPSHOT_FILES} snapshot files.")
        return rep
    parts = []
    for fname, src in files:
        r = _validate_kept(fname, src, _tee_dir, kind=kind, target=target,
                           limits=limits, columns=columns)
        parts.append((_base(fname), r))
    first = parts[0][1]
    rep.sha256 = hashlib.sha256("\n".join(sorted(
        f"{f}\t{r.sha256}" for f, r in parts)).encode()).hexdigest()
    rep.n_bytes = sum(r.n_bytes for _, r in parts)
    rep.targets = sorted({t for _, r in parts for t in r.targets})
    rep.encoding, rep.delimiter = first.encoding, first.delimiter
    # a notice said by several files is said once, naming them
    said = {}
    for f, r in parts:
        for w in r.warnings:
            said.setdefault(w, []).append(f)
    for w, fs in said.items():
        who = ("Every file" if len(fs) == len(parts) and len(fs) > 1
               else fs[0] if len(fs) == 1
               else f"{len(fs)} files ({_files_said(fs)})")
        rep.warnings.append(f"{who}: {w}")

    bad = [(f, r) for f, r in parts if not r.ok]
    if bad:
        # the file that asks for a mapping lends its headers to the box
        asks = next((r for _, r in bad if r.needs_mapping), None)
        src_h = asks or first
        rep.headers, rep.guess = src_h.headers, src_h.guess
        rep.ambiguous, rep.suggest = src_h.ambiguous, src_h.suggest
        if all(set(r.codes) <= set(_SHARED_CHOICE) for _, r in bad):
            bad = bad[:1]                 # one choice serves every file
        for f, r in bad[:MAX_EXAMPLES]:
            for p in r.problems:
                rep.problems.append(Problem(p.code, f"{f}: {p.message}",
                                            p.rows))
        if len(bad) > MAX_EXAMPLES:
            more = [f for f, _ in bad[MAX_EXAMPLES:]]
            rep.add("snapshot_more", f"{len(more)} more file(s) have "
                    f"problems too ({_files_said(more)}); they are listed "
                    "once the ones above are fixed.")
        return rep
    rep.headers, rep.guess = first.headers, first.guess

    # each file's as_of: its as_of column, else the date in its name
    undated, two, clash, dated = [], [], [], []
    for f, r in parts:
        in_name = name_dates(f)
        if r.summary["has_as_of"]:
            asofs = sorted({x[0] for x in r.records})
            if (len(in_name) == 1 and len(asofs) == 1
                    and saturday_on_or_before(in_name[0])
                    != saturday_on_or_before(asofs[0])):
                clash.append((f, in_name[0], asofs[0]))
            dated.append((f, r, r.records, "column"))
        elif len(in_name) == 1:
            a = in_name[0]
            dated.append((f, r, [(a,) + tuple(x[1:]) for x in r.records],
                          "name"))
        elif in_name:
            two.append((f, in_name))
        else:
            undated.append(f)
    if undated:
        rep.add("snapshot_undated", f"{len(undated)} file(s) carry no as_of: "
                f"no date in the name and no as_of column "
                f"({_files_said(undated)}). Name each snapshot file by its "
                "as_of date (e.g., 2024-10-05.csv or "
                "admissions_2024-10-05.csv), or give it an as_of column.")
    if two:
        rep.add("snapshot_two_dates", f"{len(two)} file name(s) hold more "
                "than one date, so which is the as_of is not clear (e.g., "
                + "; ".join(f"{f}: {' and '.join(d.isoformat() for d in ds)}"
                            for f, ds in two[:MAX_EXAMPLES])
                + "). Keep one date in each name, or give the file an as_of "
                "column.")
    if clash:
        rep.add("snapshot_as_of_name", f"{len(clash)} file(s) are named for "
                "one as_of and hold another in their as_of column (e.g., "
                + "; ".join(f"{f}: named {n.isoformat()}, as_of "
                            f"{a.isoformat()}" for f, n, a in
                            clash[:MAX_EXAMPLES])
                + "). Rename the file or correct its as_of column.")

    # one file per as_of Saturday (within one file the latest as_of of a
    # week wins, as in a single upload)
    dated.sort(key=lambda x: min(r[0] for r in x[2]))
    keyed = {}
    for f, _, recs, _ in dated:
        for k in {saturday_on_or_before(x[0]) for x in recs}:
            keyed.setdefault(k, []).append(f)
    twice = [(k, fs) for k, fs in sorted(keyed.items()) if len(fs) > 1]
    if twice:
        rep.add("snapshot_as_of_twice", f"{len(twice)} as_of week(s) come "
                "from more than one file (e.g., "
                + "; ".join(f"week ending {k.isoformat()}: "
                            + " and ".join(fs[:MAX_EXAMPLES])
                            for k, fs in twice[:MAX_EXAMPLES])
                + "). Each as_of Saturday may come from one file only; "
                "remove the extra files.")

    # no week after its file's as_of (a named file's; an as_of column is
    # checked inside validate)
    late = []
    for f, r, recs, how in dated:
        if how == "name":
            late += [(f, x[0], x[1], x[3], r.summary["date_shift_days"])
                     for x in recs if x[3] > x[0]]
    if late:
        files_late = list(dict.fromkeys(x[0] for x in late))
        moved = all(sh and d - timedelta(days=sh) <= a
                    for _, a, _, d, sh in late)
        rep.add("as_of_before_date", f"{len(late)} row(s) hold a week after "
                f"their snapshot's as_of (in {len(files_late)} file(s); "
                "e.g., " + _examples(dict.fromkeys(
                    f"{d.isoformat()} in as_of {a.isoformat()} ({f})"
                    for f, a, _, d, _ in late)) + ")."
                + (" Each date was moved to the Saturday that ends its "
                   "week, which falls after the as_of: a snapshot holds "
                   "only weeks that ended by its as_of." if moved else
                   " A snapshot holds only weeks that ended by its as_of; "
                   "check the date in the file's name."))

    # the same columns and groups in every file
    with_pop = [f for f, r in parts if "population" in r.columns]
    if with_pop and len(with_pop) < len(parts):
        without = [f for f, r in parts if "population" not in r.columns]
        rep.add("snapshot_columns", f"Columns differ across the files: "
                f"{len(with_pop)} have a population column and "
                f"{len(without)} do not (e.g., {_files_said(without)} "
                "without). Give every file the same columns.")
    ref_f, ref_r = (dated[0][0], dated[0][1]) if dated else parts[0]
    ref = set(ref_r.summary["groups"])
    diff = []
    for f, r in parts:
        g = set(r.summary["groups"])
        if g != ref:
            said_ = []
            if ref - g:
                said_.append("lacks " + _examples(sorted(ref - g,
                                                         key=str.casefold)))
            if g - ref:
                said_.append("adds " + _examples(sorted(g - ref,
                                                        key=str.casefold)))
            diff.append(f"{f} {' and '.join(said_)}")
    if diff:
        rep.add("snapshot_groups", f"Groups differ across the files "
                f"({len(diff)} file(s) against {ref_f}; e.g., "
                + "; ".join(diff[:MAX_EXAMPLES])
                + "). Every snapshot must hold the same groups.")

    recs = [x for _, _, rs, _ in dated for x in rs]
    if len(recs) > limits.max_rows:
        rep.add("limit_rows", f"The files have more than "
                f"{limits.max_rows:,} data rows together (the limit).")
    if rep.n_bytes > limits.max_bytes:
        rep.add("limit_bytes", f"The files are larger than the "
                f"{limits.max_bytes:,}-byte limit together.")
    if rep.problems:
        return rep

    s0 = dated[0][1].summary
    rep.columns = dict(dated[0][1].columns)
    rep.records = recs
    kinds = {r.summary["inferred_kind"] for _, r in parts}
    dates = sorted({x[3] for x in recs})

    def joined(key):
        return ", ".join(sorted({r.summary[key] for _, r in parts}))
    rep.summary = {
        **s0,
        "rows": len(recs),
        "first": dates[0].isoformat(), "last": dates[-1].isoformat(),
        "weeks": len(dates),
        "inferred_kind": (None if None in kinds else
                          "count" if kinds == {"count"} else "rate"),
        "has_population": all(r.summary["has_population"]
                              for _, r in parts),
        "has_as_of": True,
        "as_of": sorted({x[0].isoformat() for x in recs}),
        "encoding": joined("encoding"), "delimiter": joined("delimiter"),
        "na_dropped": sum(int(r.summary.get("na_dropped") or 0)
                          for _, r in parts),
        "first_rows_file": dated[0][0],
        "snapshot_files": [
            {"file": f, "as_of_from": how, "rows": len(rs),
             "sha256": r.sha256,
             "as_of": sorted({x[0].isoformat() for x in rs})}
            for f, r, rs, how in dated],
    }
    return rep


def ingest_snapshots(files, name: Optional[str], *,
                     kind: Optional[str] = None,
                     target: Optional[str] = None,
                     limits: Limits = DEFAULT_LIMITS,
                     columns: Optional[dict] = None) -> "Dataset":
    """Validate and store several snapshot files, ``[(filename, source),
    ...]``, as ONE vintage-true dataset (validate_snapshots); a single file
    is ingest()'s, its id unchanged. ``name`` None or '' takes
    default_snapshot_name. The originals are kept under ``sources/``;
    source.csv holds every snapshot's rows as read, with their as_of.
    Raises DatasetError and writes nothing when any problem is found; the
    same files with the same options return the stored dataset."""
    files = list(files)
    if len(files) == 1:
        fname, src = files[0]
        return ingest(src, name, kind=kind, target=target, limits=limits,
                      filename=_base(fname), columns=columns)
    kind = _checked_kind(kind)
    tmp = _tmp_dir()
    (tmp / SOURCES_DIR).mkdir()
    try:
        rep = validate_snapshots(files, kind=kind, target=target,
                                 limits=limits, columns=columns,
                                 _tee_dir=tmp / SOURCES_DIR)
        _refuse(rep)
        has_pop = rep.summary["has_population"]
        source = _csv_text(
            ("as_of", "date", "group", "value")
            + (("population",) if has_pop else ()),
            [(a.isoformat(), d.isoformat(), n, _fmt_num(v))
             + ((_fmt_num(p),) if has_pop else ())
             for a, n, _, d, v, p in sorted(
                 rep.records, key=lambda r: (r[0], r[3],
                                             r[1].casefold()))])
        files_meta = rep.summary["snapshot_files"]
        return _store(tmp, rep, name or default_snapshot_name(
            [f for f, _ in files]), kind=kind,
            filename=f"{len(files_meta)} snapshot files",
            extra={"snapshot_files": files_meta}, source_text=source)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
