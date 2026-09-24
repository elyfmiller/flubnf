"""RESEARCH (staged): user-supplied target datasets (custom CSV target data).

A dataset is one uploaded CSV of weekly target data in either shape:

  * MicroHub (github.com/sjfox/microhub; the owner's fork elyfmiller/microhub):
    ``date, target_group, value[, population]``.
  * hubverse time series: ``target_end_date | date, location,
    observation | value[, target][, as_of][, location_name][, population]``.

Headers are case- and space-insensitive; other columns are ignored and named
in the warnings. This module parses and validates an upload (the MicroHub
``validate_data`` checks plus FluBNF's own), stores it under
``app/state/datasets/<id>/`` and materializes the SAME file shapes the hub path
reads, so the engines can consume a dataset unchanged in later stages:

  * ``locations.csv``: the flubnf/data/locations.csv shape (abbreviation,
    location, location_name, population) plus ``source_key``. ``location`` is
    a minted key 'c01', 'c02', ... that survives zfill(2) and can never
    collide with a FIPS code or 'US'.
  * ``vintages/target-hospital-admissions_<Saturday>.csv``: the FluSight
    archive shape (date, location, location_name, value, weekly_rate). One
    final vintage (keyed by the newest week) when the upload has no as_of;
    one per as_of Saturday when it has.

Nothing here touches the hub, an engine or pandas; a custom dataset is never
the default source (the caller opts in per page and per run).

Public API: ``validate``, ``ingest``, ``list_datasets``, ``get``, ``delete``,
``Dataset`` (``vintages``/``vintage_path`` mirror app/core/data.py),
``Report``/``Problem``, ``Limits``, ``DatasetError``, ``KINDS``, ``ROOT``.
"""
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
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from app.core.runs import APP_STATE

#: the dataset store; tests monkeypatch it
ROOT = APP_STATE / "datasets"

#: manifest schema (part of the identity digest)
SCHEMA = 1

#: the value kinds an upload must declare: counts (PF-eligible, Poisson floor,
#: integer export) or rates/proportions (neither)
KINDS = ("count", "rate")

#: file names inside a dataset folder
SOURCE_FILE = "source.csv"
SERIES_FILE = "series.csv"
LOCATIONS_FILE = "locations.csv"
META_FILE = "meta.json"
VINTAGE_DIR = "vintages"
VINTAGE_PREFIX = "target-hospital-admissions_"

#: MicroHub's gap rule: consecutive dates within a group may differ by at most
#: 8 days ("allow up to 8 days to handle rounding", R/data_utils.R)
MAX_GAP_DAYS = 8

#: group names: they become PF directory names, BNGL suffixes (spaces -> '_'),
#: ledger keys and HTML text
GROUP_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _]{0,39}")

#: names the console gives another meaning: us_national.US_SPELLINGS (national
#: row) and 'all' (every location)
RESERVED_NAMES = ("US", "US (NATIONAL)", "UNITED STATES", "USA", "ALL")

#: tokens read as a missing value (MicroHub/readr's NA set, plus common ones)
NA_TOKENS = {"", "na", "n/a", "nan", "null", "none", "-"}

#: dataset ids: slug + '-' + 12 hex of the identity digest
ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,31}-[0-9a-f]{12}")

#: header aliases, first present wins
DATE_ALIASES = ("target_end_date", "date")
VALUE_ALIASES = ("observation", "value")
GROUP_ALIASES = ("target_group", "location")
OPTIONAL = ("population", "as_of", "target", "location_name")

MAX_EXAMPLES = 3


class DatasetError(Exception):
    """A dataset could not be ingested or found. ``problems`` holds the
    validation problems when the cause was the upload's content."""

    def __init__(self, message: str, problems: Optional[list] = None):
        super().__init__(message)
        self.problems = list(problems or [])


@dataclass(frozen=True)
class Limits:
    """Upload limits, enforced while the bytes stream in."""
    max_bytes: int = 100 * 1024 * 1024
    max_rows: int = 1_500_000
    max_groups: int = 200


DEFAULT_LIMITS = Limits()


@dataclass(frozen=True)
class Problem:
    """One validation problem: a stable code for callers and tests, and a
    human-readable message that carries an example."""
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass
class Report:
    """What validate() found. ``ok`` is True only with no problems; warnings
    never block. ``summary`` describes the parsed data (empty when the file
    could not be read far enough)."""
    problems: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    columns: dict = field(default_factory=dict)
    # parsed rows (as_of|None, name, source_key, date, value, population|None)
    records: list = field(default_factory=list, repr=False)
    sha256: str = ""
    n_bytes: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def codes(self) -> list:
        return [p.code for p in self.problems]

    def add(self, code: str, message: str) -> None:
        self.problems.append(Problem(code, message))


class _LimitExceeded(Exception):
    pass


# --------------------------------------------------------------- streaming

class _CappedReader(io.RawIOBase):
    """A binary stream wrapper that hashes, counts, optionally tees to a
    file, and stops once more than ``max_bytes`` have been read."""

    def __init__(self, raw, max_bytes: int, tee=None):
        self._raw, self._max, self._tee = raw, max_bytes, tee
        self.n = 0
        self.sha = hashlib.sha256()

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        chunk = self._raw.read(len(b))
        if not chunk:
            return 0
        self.n += len(chunk)
        if self.n > self._max:
            raise _LimitExceeded("bytes")
        self.sha.update(chunk)
        if self._tee is not None:
            self._tee.write(chunk)
        b[:len(chunk)] = chunk
        return len(chunk)


def _open_source(source):
    """(binary stream, close?) for bytes, a path, or a binary file object."""
    if isinstance(source, (bytes, bytearray)):
        return io.BytesIO(bytes(source)), True
    if isinstance(source, (str, Path)):
        return open(source, "rb"), True
    return source, False


# ------------------------------------------------------------------- dates

_DATE_FORMATS = (
    ("YYYY-MM-DD", re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"), "ymd"),
    ("M/D/YYYY", re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"), "mdy"),
    ("M/D/YY", re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2})"), "mdy2"),
    ("MM-DD-YYYY", re.compile(r"(\d{1,2})-(\d{1,2})-(\d{4})"), "mdy"),
)


def parse_date(text: str):
    """(date, format label) for the accepted formats, else (None, None).

    Accepted: YYYY-MM-DD, M/D/YYYY, M/D/YY (MicroHub's template) and
    MM-DD-YYYY. Day-first (D/M/Y), which MicroHub also tries, is not
    accepted: it is ambiguous for every day <= 12 and a silent misparse
    would shift weeks. Two-digit years follow POSIX %y: 00-68 -> 20xx."""
    s = (text or "").strip()
    for label, rx, order in _DATE_FORMATS:
        m = rx.fullmatch(s)
        if not m:
            continue
        a, b, c = (int(x) for x in m.groups())
        if order == "ymd":
            y, mo, d = a, b, c
        else:
            mo, d, y = a, b, c
            if order == "mdy2":
                y += 2000 if y < 69 else 1900
        try:
            return date(y, mo, d), label
        except ValueError:
            return None, None
    return None, None


def saturday_on_or_before(d: date) -> date:
    """The MMWR week-ending Saturday on or before ``d`` (the vintage key of
    an as_of: Saturday as_of -> itself, Wednesday -> the Saturday before)."""
    return d - timedelta(days=(d.weekday() - 5) % 7)


def _num(text: str):
    """float, None for an NA token, or raise ValueError."""
    s = (text or "").strip()
    if s.lower() in NA_TOKENS:
        return None
    v = float(s)
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(s)
    return v


def _fmt_num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else repr(float(v))


def _int_or_float(v: float):
    return int(v) if float(v).is_integer() else float(v)


def _examples(items) -> str:
    return ", ".join(str(x) for x in list(items)[:MAX_EXAMPLES])


def _norm_name(name: str) -> str:
    """The form two group names must not share: PF cell directories replace
    spaces with '_', and macOS/Windows filesystems fold case."""
    return name.replace(" ", "_").casefold()


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:32]
    return s.strip("-") or "dataset"


# -------------------------------------------------------------- validation

def validate(source, *, kind: Optional[str] = None,
             week_start_sunday: bool = False, target: Optional[str] = None,
             limits: Limits = DEFAULT_LIMITS, _tee=None) -> Report:
    """Parse and validate one upload; every problem is reported at once.

    ``source`` is bytes, a path, or a binary file object. ``kind`` is the
    declared value kind ('count' or 'rate'; None skips the kind check and
    the summary reports the inferred kind). ``week_start_sunday`` declares
    that dates are week-START Sundays, shifted +6 to the MMWR Saturday.
    ``target`` picks one target when the file carries several.

    MicroHub's validate_data checks: required columns; dates parseable;
    value numeric, >= 0, never NA; no duplicate (date, group); no gap over
    8 days within a group. FluBNF adds: Saturday week-ending dates; safe,
    unique group names; a declared kind; one target; population > 0 on
    every row when the column exists; one name per location; no snapshot
    week after its as_of; and the size limits, enforced while streaming.
    """
    rep = Report()
    stream, close = _open_source(source)
    capped = _CappedReader(stream, limits.max_bytes, tee=_tee)
    raw_rows = []
    try:
        try:
            text = io.TextIOWrapper(io.BufferedReader(capped),
                                    encoding="utf-8-sig", newline="")
            reader = csv.reader(text)
            header = next(reader, None)
            if header is None:
                rep.add("empty", "The file is empty: expected a header row "
                        "such as date,target_group,value.")
                return rep
            cols = _map_columns(header, rep)
            if cols is None:
                return rep
            idx = cols["_idx"]
            groups_seen = set()
            ragged = []
            gcol = idx["group"]
            for row in reader:
                if not row or all(not c.strip() for c in row):
                    continue
                if len(raw_rows) >= limits.max_rows:
                    raise _LimitExceeded("rows")
                if len(row) < len(header):
                    ragged.append(reader.line_num)
                    row = row + [""] * (len(header) - len(row))
                g = row[gcol].strip()
                if g not in groups_seen:
                    groups_seen.add(g)
                    if len(groups_seen) > limits.max_groups:
                        raise _LimitExceeded("groups")
                raw_rows.append((reader.line_num,
                                 {k: row[i] for k, i in idx.items()}))
            if ragged:
                rep.add("ragged", f"{len(ragged)} row(s) have fewer fields "
                        f"than the header (e.g., line(s) {_examples(ragged)}).")
        except _LimitExceeded as e:
            what = str(e)
            if what == "bytes":
                rep.add("limit_bytes", f"The file is larger than the "
                        f"{limits.max_bytes:,}-byte limit; nothing was read "
                        "past it.")
            elif what == "rows":
                rep.add("limit_rows", f"The file has more than "
                        f"{limits.max_rows:,} data rows (the limit).")
            else:
                rep.add("limit_groups", f"The file has more than "
                        f"{limits.max_groups} groups (the limit).")
            return rep
        except UnicodeDecodeError as e:
            rep.add("encoding", "The file is not UTF-8 text (e.g., byte "
                    f"{e.object[e.start:e.start + 1]!r} cannot be decoded). "
                    "Save it as CSV UTF-8.")
            return rep
        except csv.Error as e:
            rep.add("csv", f"The file is not a readable CSV: {e}.")
            return rep
    finally:
        rep.sha256, rep.n_bytes = capped.sha.hexdigest(), capped.n
        if close:
            stream.close()
    rep.columns = {k: v for k, v in cols.items() if k != "_idx"}
    _check_rows(rep, raw_rows, cols, kind=kind,
                week_start_sunday=week_start_sunday, target=target)
    return rep


def _map_columns(header, rep: Report):
    """{role: header text, '_idx': {role: index}, 'format': ...} or None
    (with the problem recorded) when a required column is missing."""
    norm = [h.strip().lower() for h in header]
    dup = sorted({h for h in norm if norm.count(h) > 1 and h})
    if dup:
        rep.add("duplicate_columns", "Column names repeat (ignoring case and "
                f"spaces): {_examples(dup)}. Each column must appear once.")
        return None
    pos = {h: i for i, h in enumerate(norm)}

    def first(aliases):
        return next((a for a in aliases if a in pos), None)

    d, v = first(DATE_ALIASES), first(VALUE_ALIASES)
    present_groups = [a for a in GROUP_ALIASES if a in pos]
    missing = []
    if d is None:
        missing.append("date (or target_end_date)")
    if not present_groups:
        missing.append("target_group (or location)")
    if v is None:
        missing.append("value (or observation)")
    if missing:
        rep.add("missing_columns", "Missing columns: " + ", ".join(missing)
                + f". Found: {', '.join(h for h in header) or '(none)'}.")
        return None
    if len(present_groups) > 1:
        rep.add("ambiguous_columns", "The file has both 'target_group' and "
                "'location'; keep exactly one of them as the group column.")
        return None
    g = present_groups[0]
    cols = {"format": "microhub" if g == "target_group" else "hubverse",
            "date": header[pos[d]].strip(), "group": header[pos[g]].strip(),
            "value": header[pos[v]].strip()}
    idx = {"date": pos[d], "group": pos[g], "value": pos[v]}
    for o in OPTIONAL:
        if o in pos and not (o == "location_name" and g != "location"):
            cols[o] = header[pos[o]].strip()
            idx[o] = pos[o]
    used = set(idx.values())
    ignored = [header[i].strip() for i in range(len(header))
               if i not in used and header[i].strip()]
    if ignored:
        rep.warnings.append(f"Ignored column(s): {', '.join(ignored)}.")
    cols["_idx"] = idx
    return cols


def _check_rows(rep: Report, raw_rows: list, cols: dict, *, kind,
                week_start_sunday: bool, target) -> None:
    fmt = cols["format"]
    if kind is not None and kind not in KINDS:
        rep.add("kind_invalid", f"Value kind {kind!r} is not one of "
                f"{', '.join(KINDS)}: declare whether values are counts or "
                "rates.")

    # one target per dataset
    tgt_used = None
    if "target" in cols:
        targets = sorted({r["target"].strip() for _, r in raw_rows})
        if target is not None:
            if target not in targets:
                rep.add("target_unknown", f"Target {target!r} is not in the "
                        f"file. Targets found: {_examples(targets)}.")
                return
            raw_rows = [(ln, r) for ln, r in raw_rows
                        if r["target"].strip() == target]
            tgt_used = target
        elif len(targets) > 1:
            rep.add("target_required", f"The file holds {len(targets)} "
                    f"targets ({', '.join(targets)}); choose one.")
            return
        else:
            tgt_used = targets[0] if targets else None
    elif target is not None:
        rep.add("target_unknown", f"Target {target!r} was chosen but the "
                "file has no 'target' column.")
        return
    if not raw_rows:
        rep.add("empty", "The file has a header but no data rows.")
        return

    bad_dates, bad_asof, bad_vals, neg, na, nonint = [], [], [], [], [], []
    bad_pop, miss_pop = [], []
    formats = set()
    has_pop, has_asof = "population" in cols, "as_of" in cols
    has_lname = "location_name" in cols
    wrong_day = []
    recs = []
    for ln, r in raw_rows:
        d, f = parse_date(r["date"])
        if d is None:
            bad_dates.append(r["date"].strip() or "(blank)")
        else:
            formats.add(f)
            want = 6 if week_start_sunday else 5
            if d.weekday() != want:
                wrong_day.append(f"{r['date'].strip()} "
                                 f"({d.strftime('%A')}, line {ln})")
            elif week_start_sunday:
                d = d + timedelta(days=6)
        a = None
        if has_asof:
            a, _ = parse_date(r["as_of"])
            if a is None:
                bad_asof.append(r["as_of"].strip() or "(blank)")
        raw_v = r["value"].strip()
        try:
            v = _num(raw_v)
        except ValueError:
            bad_vals.append(raw_v)
            v = None
        else:
            if v is None:
                na.append(ln)
            elif v < 0:
                neg.append(f"{raw_v} (line {ln})")
            elif kind == "count" and not v.is_integer():
                nonint.append(f"{raw_v} (line {ln})")
        p = None
        if has_pop:
            raw_p = r["population"].strip()
            try:
                p = _num(raw_p)
            except ValueError:
                bad_pop.append(f"{raw_p} (line {ln})")
            else:
                if p is None:
                    miss_pop.append(ln)
                elif p <= 0:
                    bad_pop.append(f"{raw_p} (line {ln})")
                    p = None
        key = r["group"].strip()
        name = key
        if has_lname and r["location_name"].strip():
            name = r["location_name"].strip()
        # every row with a usable date (and as_of) joins the structural
        # checks (duplicates, gaps), as in MicroHub, whatever its value
        if d is not None and (a is not None or not has_asof):
            recs.append((a, name, key, d, v, p))

    col = cols["date"]
    if bad_dates:
        rep.add("date_parse", f"The '{col}' column contains "
                f"{len(bad_dates)} value(s) that could not be parsed as dates "
                f"(e.g., {_examples(bad_dates)}). Ensure dates are in "
                "M/D/YY, MM/DD/YYYY, MM-DD-YYYY, or YYYY-MM-DD format.")
    if wrong_day:
        want = ("Sundays (week-start, shifted +6 to the Saturday)"
                if week_start_sunday else "Saturdays (the last day of the "
                "MMWR week)")
        hint = ("" if week_start_sunday else " If your dates are week-start "
                "Sundays, choose the Sunday option to shift them +6 days.")
        rep.add("weekday", f"{len(wrong_day)} date(s) are not {want} "
                f"(e.g., {_examples(wrong_day)}).{hint}")
    if bad_asof:
        rep.add("as_of_parse", f"The '{cols['as_of']}' column contains "
                f"{len(bad_asof)} value(s) that could not be parsed as dates "
                f"(e.g., {_examples(bad_asof)}).")
    vcol = cols["value"]
    if bad_vals:
        rep.add("value_numeric", f"The '{vcol}' column must contain numbers "
                f"only. Non-numeric values found: "
                f"{_examples(dict.fromkeys(bad_vals))}.")
    if neg:
        rep.add("value_negative", f"The '{vcol}' column contains {len(neg)} "
                f"negative value(s) (e.g., {_examples(neg)}). Values must be "
                "zero or positive.")
    if na:
        rep.add("value_na", f"The '{vcol}' column contains {len(na)} missing "
                f"(NA) value(s) (e.g., line(s) {_examples(na)}). All rows "
                "must have a value; delete rows for weeks not reported.")
    if nonint:
        rep.add("value_not_integer", f"The values were declared counts but "
                f"{len(nonint)} are not whole numbers (e.g., "
                f"{_examples(nonint)}). Declare the kind 'rate' instead.")
    if bad_pop:
        rep.add("population_invalid", f"The '{cols['population']}' column "
                f"has {len(bad_pop)} value(s) that are not positive numbers "
                f"(e.g., {_examples(bad_pop)}).")
    if miss_pop:
        rep.add("population_missing", f"The '{cols['population']}' column "
                f"is blank on {len(miss_pop)} row(s) (e.g., line(s) "
                f"{_examples(miss_pop)}). Give every row a population, or "
                "remove the column.")
    if len(formats) > 1:
        rep.warnings.append(f"Dates mix formats ({', '.join(sorted(formats))}); "
                            "each was read by its own pattern.")

    _check_groups(rep, raw_rows, cols)
    _check_structure(rep, recs, cols)

    rep.records = recs
    if recs:
        dates = sorted({r[3] for r in recs})
        names = sorted({r[1] for r in recs}, key=str.casefold)
        integral = all(float(r[4]).is_integer() for r in recs
                       if r[4] is not None)
        asofs = sorted({r[0] for r in recs if r[0] is not None})
        rep.summary = {
            "format": fmt,
            "rows": len(recs),
            "groups": names,
            "first": dates[0].isoformat(),
            "last": dates[-1].isoformat(),
            "weeks": len(dates),
            "kind": kind if kind in KINDS else None,
            "inferred_kind": "count" if integral else "rate",
            "target": tgt_used,
            "has_population": has_pop and not (bad_pop or miss_pop),
            "has_as_of": has_asof,
            "as_of": [a.isoformat() for a in asofs],
            "week_start_sunday": bool(week_start_sunday),
        }
        if has_pop:
            pops = {}
            for r in recs:
                pops.setdefault(r[1], set()).add(r[5])
            varies = [n for n in names if len(pops.get(n, ())) > 1]
            if varies:
                rep.warnings.append(
                    f"Population varies by date for {_examples(varies)}"
                    f"{' and others' if len(varies) > MAX_EXAMPLES else ''}; "
                    "the latest value is used for the particle filter.")


def _check_groups(rep: Report, raw_rows: list, cols: dict) -> None:
    """Names: charset, reserved spellings, collisions after space->'_' and
    case folding, and one name per location (hubverse)."""
    has_lname = "location_name" in cols
    key2names, name2keys = {}, {}
    for _, r in raw_rows:
        key = r["group"].strip()
        name = (r["location_name"].strip()
                if has_lname and r["location_name"].strip() else key)
        key2names.setdefault(key, set()).add(name)
        name2keys.setdefault(name, set()).add(key)
    what = "location name" if cols["format"] == "hubverse" else "target_group"
    bad = [n for n in name2keys if not GROUP_RE.fullmatch(n)]
    if bad:
        sugg = [f"'{n}' -> '{_suggest(n)}'" for n in bad]
        rep.add("group_name", f"{len(bad)} {what} value(s) use characters "
                "other than letters, digits, space and underscore, start "
                "with a space or underscore, or exceed 40 characters (e.g., "
                f"{_examples(sugg)}).")
    reserved = [n for n in name2keys if n.upper() in RESERVED_NAMES]
    if reserved:
        rep.add("group_reserved", f"Group name(s) {_examples(reserved)} are "
                "reserved (the console reads them as the US national row or "
                "as every location); rename them, e.g. 'National'.")
    folded = {}
    for n in name2keys:
        folded.setdefault(_norm_name(n), []).append(n)
    clash = [sorted(v) for v in folded.values() if len(v) > 1]
    if clash:
        rep.add("group_collision", f"{len(clash)} set(s) of group names "
                "differ only by case or by space vs underscore, and would "
                "collide in folder names (e.g., "
                f"{_examples(' / '.join(repr(x) for x in c) for c in clash)}).")
    multi = [f"{k}: {', '.join(sorted(v))}" for k, v in key2names.items()
             if len(v) > 1]
    multi += [f"{n}: {', '.join(sorted(v))}" for n, v in name2keys.items()
              if len(v) > 1 and has_lname]
    if multi:
        rep.add("location_name_conflict", "Each location must have exactly "
                "one location_name and vice versa (e.g., "
                f"{_examples(multi)}).")


def _suggest(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9 _]+", "_", name).strip(" _")[:40]
    return s or "group1"


def _check_structure(rep: Report, recs: list, cols: dict) -> None:
    """Duplicates, gaps (per snapshot and group), and snapshot weeks after
    their as_of."""
    seen, dups = set(), []
    series = {}
    late = []
    for a, name, _, d, _, _ in recs:
        k = (a, name, d)
        if k in seen:
            dups.append(f"{d.isoformat()} + {name}"
                        + (f" (as_of {a.isoformat()})" if a else ""))
        seen.add(k)
        series.setdefault((a, name), set()).add(d)
        if a is not None and d > a:
            late.append(f"{d.isoformat()} in as_of {a.isoformat()} ({name})")
    if dups:
        unit = ("as_of/date/group" if "as_of" in cols else "date/group")
        rep.add("duplicate", f"Duplicate rows found for {len(dups)} {unit} "
                f"combination(s) (e.g., {_examples(dups)}). Each combination "
                "must appear exactly once.")
    gaps = []
    for (a, name), ds in sorted(series.items(),
                                key=lambda kv: (kv[0][0] or date.min,
                                                kv[0][1])):
        ds = sorted(ds)
        for p, q in zip(ds, ds[1:]):
            if (q - p).days > MAX_GAP_DAYS:
                gaps.append(f"gap between {p.isoformat()} and "
                            f"{q.isoformat()} in group '{name}'"
                            + (f", as_of {a.isoformat()}" if a else ""))
    if gaps:
        rep.add("gap", f"Missing weeks detected in {len(gaps)} place(s) "
                f"(e.g., {_examples(gaps)}). The data should have one row per "
                "week per group.")
    if late:
        rep.add("as_of_before_date", f"{len(late)} row(s) hold a week after "
                f"their snapshot's as_of (e.g., {_examples(late)}).")


# ------------------------------------------------------------------ storage

def _root() -> Path:
    return Path(ROOT)


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
    different id (and a spec pinning the digest notices)."""
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


def ingest(source, name: str, *, kind: str, week_start_sunday: bool = False,
           target: Optional[str] = None, limits: Limits = DEFAULT_LIMITS,
           filename: str = "") -> "Dataset":
    """Validate and store one upload; returns the stored Dataset.

    Raises DatasetError (with ``.problems``) and writes nothing when any
    problem is found. Re-ingesting identical bytes with identical options
    under the same name returns the existing dataset (idempotent). The
    folder is built beside the store and renamed into place, so a reader
    never sees a half-written dataset."""
    if kind not in KINDS:
        raise DatasetError(f"Declare the value kind: one of {', '.join(KINDS)}.",
                           [Problem("kind_invalid", f"Value kind {kind!r} is "
                                    f"not one of {', '.join(KINDS)}.")])
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / f".tmp-{uuid.uuid4().hex}"
    tmp.mkdir()
    try:
        with open(tmp / SOURCE_FILE, "wb") as tee:
            rep = validate(source, kind=kind,
                           week_start_sunday=week_start_sunday,
                           target=target, limits=limits, _tee=tee)
        if not rep.ok:
            raise DatasetError(
                f"{len(rep.problems)} problem(s) in the upload; nothing was "
                "stored.", rep.problems)
        digest = identity_digest(rep.sha256, kind=kind,
                                 week_start_sunday=week_start_sunday,
                                 target=rep.summary.get("target"),
                                 columns=rep.columns)
        dataset_id = f"{slug(name)}-{digest[:12]}"
        final = _dir(dataset_id)
        if (final / META_FILE).is_file():
            return get(dataset_id)
        _materialize(tmp, rep, name=name, dataset_id=dataset_id,
                     digest=digest, kind=kind,
                     week_start_sunday=week_start_sunday, filename=filename)
        try:
            os.rename(tmp, final)
        except OSError:
            if (final / META_FILE).is_file():      # a concurrent twin won
                return get(dataset_id)
            raise
        return get(dataset_id)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def _materialize(d: Path, rep: Report, *, name, dataset_id, digest, kind,
                 week_start_sunday, filename) -> None:
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
            "first": ds[0].isoformat(), "last": ds[-1].isoformat()})
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
        "options": {"kind": kind, "week_start_sunday": bool(week_start_sunday),
                    "target": s["target"]},
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
        "warnings": list(rep.warnings),
    }
    _atomic_write_text(d / META_FILE, json.dumps(meta, indent=1) + "\n")


# ------------------------------------------------------------------ reading

@dataclass
class Dataset:
    """A stored dataset: its manifest plus the paths and adapters an engine
    needs. ``vintages``/``vintage_path`` mirror app/core/data.py."""
    path: Path
    meta: dict

    @property
    def id(self) -> str:
        return self.meta["id"]

    @property
    def name(self) -> str:
        return self.meta["name"]

    @property
    def kind(self) -> str:
        return self.meta["kind"]

    @property
    def has_population(self) -> bool:
        return bool(self.meta["has_population"])

    @property
    def has_as_of(self) -> bool:
        return bool(self.meta["has_as_of"])

    @property
    def groups(self) -> list:
        return [g["name"] for g in self.meta["groups"]]

    @property
    def name2key(self) -> dict:
        return {g["name"]: g["key"] for g in self.meta["groups"]}

    @property
    def populations(self) -> dict:
        """Latest population per group name (the particle filter's N);
        empty when the upload had none."""
        return ({g["name"]: g["population"] for g in self.meta["groups"]}
                if self.has_population else {})

    @property
    def pf_eligible(self) -> bool:
        """Counts with a population: what the SIHRS filter needs."""
        return self.kind == "count" and self.has_population

    @property
    def source_path(self) -> Path:
        return self.path / SOURCE_FILE

    @property
    def series_path(self) -> Path:
        return self.path / SERIES_FILE

    @property
    def locations_csv(self) -> Path:
        """The locations table in the flubnf/data/locations.csv shape."""
        return self.path / LOCATIONS_FILE

    def vintages(self) -> list:
        """Every materialized vintage key (Saturday), ascending."""
        return list(self.meta["vintages"])

    def vintage_path(self, date: str) -> Path:
        """Exact vintage or a LOUD error naming nearby ones (rule 5)."""
        p = self.path / VINTAGE_DIR / f"{VINTAGE_PREFIX}{date}.csv"
        if str(date) not in self.meta["vintages"] or not p.is_file():
            vs = self.vintages()
            try:
                t = saturday_on_or_before(parse_date(str(date))[0])
                near = [v for v in vs
                        if abs((date_fromiso(v) - t).days) <= 45]
            except (TypeError, ValueError, AttributeError):
                near = []
            raise FileNotFoundError(
                f"No vintage for {date} in dataset {self.name!r}. "
                f"Nearby: {near or vs[-3:]}")
        return p

    @property
    def final_path(self) -> Path:
        """The newest vintage (the final data when there is no as_of)."""
        return self.vintage_path(self.meta["vintages"][-1])

    def reference_dates(self) -> list:
        """MicroHub's retrospective dates: every distinct week except the
        first, from the final data."""
        with open(self.final_path, newline="") as fh:
            ds = sorted({r["date"] for r in csv.DictReader(fh)})
        return ds[1:]

    def population_series(self, name: str) -> list:
        """[(date, population)] for one group from the final snapshot,
        oldest first (population may vary by date); [] without one."""
        final_as_of = self.meta["as_of_used"][self.meta["vintages"][-1]] or ""
        out = []
        with open(self.series_path, newline="") as fh:
            for r in csv.DictReader(fh):
                if (r["location_name"] == name and r["as_of"] == final_as_of
                        and r["population"]):
                    out.append((r["date"], float(r["population"])))
        return sorted(out)

    def ref(self) -> dict:
        """What a run spec pins: id, digest prefix, name."""
        return {"id": self.id, "digest": self.meta["digest"][:16],
                "name": self.name}


def date_fromiso(s: str) -> date:
    return date.fromisoformat(str(s)[:10])


def get(dataset_id: str) -> Dataset:
    """The stored dataset; DatasetError for a bad or unknown id."""
    d = _dir(dataset_id)
    mp = d / META_FILE
    if not mp.is_file():
        raise DatasetError(f"No dataset {dataset_id!r}.")
    return Dataset(d, json.loads(mp.read_text(encoding="utf-8")))


def resolve(ref: Optional[dict]) -> Optional[Dataset]:
    """The dataset a spec's ref names, None for no ref; raises when it is
    gone or its digest no longer matches (never a silent substitute)."""
    if not ref:
        return None
    ds = get(ref.get("id"))
    if not ds.meta["digest"].startswith(str(ref.get("digest") or "?")):
        raise DatasetError(f"Dataset {ds.id!r} no longer matches the "
                           "digest this run pinned.")
    return ds


def list_datasets() -> list:
    """Every readable stored dataset, newest first."""
    root = _root()
    if not root.is_dir():
        return []
    out = []
    for p in root.iterdir():
        if not valid_id(p.name) or not (p / META_FILE).is_file():
            continue
        try:
            out.append(get(p.name))
        except (DatasetError, ValueError, OSError):
            continue
    return sorted(out, key=lambda d: (d.meta.get("created", ""), d.id),
                  reverse=True)


def delete(dataset_id: str) -> None:
    """Remove a dataset folder. Refuses malformed ids, ids resolving
    outside the store, and folders that are not datasets."""
    d = _dir(dataset_id)
    if d.is_symlink() or not (d / META_FILE).is_file():
        raise DatasetError(f"No dataset {dataset_id!r}.")
    shutil.rmtree(d)


def summary_lines(rep: Report) -> list:
    """A short human summary of a valid report (the CLI's output)."""
    s = rep.summary
    kind = s["kind"] or f"{s['inferred_kind']} (inferred; declare it)"
    lines = [
        f"format      {s['format']}",
        f"rows        {s['rows']:,}",
        f"groups      {len(s['groups'])}: {', '.join(s['groups'][:8])}"
        + (" ..." if len(s["groups"]) > 8 else ""),
        f"weeks       {s['weeks']} ({s['first']} to {s['last']})",
        f"kind        {kind}",
        f"population  {'yes' if s['has_population'] else 'no'}",
        "as_of       " + (f"{len(s['as_of'])} snapshot(s), "
                           f"{s['as_of'][0]} to {s['as_of'][-1]}"
                           if s["as_of"] else "none (final data only)"),
    ]
    if s["target"]:
        lines.append(f"target      {s['target']}")
    return lines
