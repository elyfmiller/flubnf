"""RESEARCH (staged): user-supplied target datasets (custom CSV target data).

A dataset is one uploaded CSV of weekly target data in either shape:

  * grouped CSV: ``date, target_group, value[, population]``.
  * hubverse time series: ``target_end_date | date, location,
    observation | value[, target][, as_of][, location_name][, population]``.

Reading is lenient but never silently wrong (``validate``; the Data,
Forecast and Retrospective upload box, the Sandbox upload and ``flubnf
dataset`` all read through it):

  * encodings: UTF-8 with or without a BOM, UTF-16 (a spreadsheet's
    "Unicode text"), UTF-32, else Windows-1252 (bytes it leaves undefined
    read as Latin-1), named in a notice; non-ASCII group names are kept.
    A file that holds UTF-8 characters AND bytes that are not UTF-8 mixes
    encodings: it is refused, naming the rows, since either reading
    garbles one of the two.
  * separators: comma, semicolon or tab, sniffed from the header. A quote
    opened and not closed on its row, which takes in the rows below it
    (to the end of the file), is refused; a note over two lines is kept.
  * numbers: "1,234" in a comma file is 1234; decimal commas ("1,5") are
    read in a semicolon or tab file when the column shows it unambiguously;
    anything that could go either way is refused. A column whose every
    decimal could as well be a thousands separator (987, 1.234, 12.345 in
    a comma file; 1,234 in a semicolon or tab file) is read by the
    declared kind: rates as decimals, counts refused (written without
    separators); undeclared, the kind is asked for, never inferred. A value or name that an
    unquoted separator split (1,234 or Bern, Stadt without quotes) is
    refused, whether its second half lands past the header or in an
    ignored column.
  * headers: case, space and underscore do not matter, and obvious aliases
    are read (``ROLE_ALIASES``). A required column that cannot be matched,
    or two columns that could both be it, asks for a column mapping
    (``columns=``) instead of guessing. Other columns are ignored and named
    in a notice; trailing empty columns and rows are dropped.
  * dates: YYYY-MM-DD, YYYY/MM/DD, M/D/YYYY, M/D/YY and MM-DD-YYYY, with or
    without a time ("2024-01-06 00:00:00"). Every date of a file must fall
    on one weekday; it is moved to the MMWR week-ending Saturday of its
    Sunday-to-Saturday week, with a notice. Mixed weekdays and day-first
    dates are refused, and so is a single week written M/D that reads both
    ways, an as_of written M/D that reads both ways unless its snapshots
    settle it (day-first would put a week after its as_of, or fits them
    less closely; a tie stands only when the dates prove month-first by a
    day over 12, as in 1/13/2024: 05/05/2024 proves neither order), a
    column whose header names week ENDS ('week ending (Sunday)',
    'period_end') whose dates are Sundays, Mondays or Tuesdays, and one
    naming week STARTS whose dates are Thursdays, Fridays or Saturdays
    (most of such a week lies in the MMWR week before, or after, so moving
    it would label it a week late, or early).

Every problem is reported at once, each with its row numbers (the
spreadsheet's rows: the header is row 1) and an example; ``problem_groups``
sorts them by kind. meta.json records the shape as ``format``: 'grouped' or
'hubverse'. This module stores a valid upload under
``app/state/datasets/<id>/`` and materializes the SAME file shapes the hub
path reads, so the engines consume a dataset unchanged:

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
``Report``/``Problem``, ``problem_groups``, ``Limits``, ``DatasetError``,
``KINDS``, ``ROLE_ALIASES``, ``ROOT``.
"""
from __future__ import annotations

import codecs
import csv
import hashlib
import io
import itertools
import json
import os
import re
import shutil
import time
import unicodedata
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from app.core.runs import APP_STATE

#: the dataset store; tests monkeypatch it
ROOT = APP_STATE / "datasets"

#: manifest schema (part of the identity digest)
SCHEMA = 1

#: the value kinds: counts (PF-eligible, Poisson floor, integer export) or
#: rates/proportions (neither). Undeclared, the values decide: whole numbers
#: are counts (unless their decimals could be thousands separators, see
#: grouping_or_decimal: then the kind is asked for).
KINDS = ("count", "rate")

#: file names inside a dataset folder
SOURCE_FILE = "source.csv"
SERIES_FILE = "series.csv"
LOCATIONS_FILE = "locations.csv"
META_FILE = "meta.json"
VINTAGE_DIR = "vintages"
VINTAGE_PREFIX = "target-hospital-admissions_"

#: the gap rule: consecutive dates within a group may differ by at most 8
#: days (one week plus a day's slack for rounding), so no week is missing
MAX_GAP_DAYS = 8

#: group names: they become PF directory names and BNGL suffixes (through
#: pf_stem), ledger keys and HTML text. Letters of any script are kept, with
#: the combining marks that write them (group_name_ok)
GROUP_RE = re.compile(r"[^\W_][\w ]{0,39}")
#: the Unicode categories of the combining marks a name may hold after its
#: first letter: the vowel signs and viramas of Devanagari ('दिल्ली'), Thai
#: ('กรุงเทพ') and other scripts, which \w does not match
NAME_MARKS = ("Mn", "Mc")

#: 'all' means every location to the console, so no group may be called it
RESERVED_NAMES = ("ALL",)

#: spellings (case-insensitive) that make a group the dataset's NATIONAL row
#: (owner decision 2026-09-24): us_national.US_SPELLINGS plus 'National'. It
#: gets a minted key like every group (never the literal FIPS 'US', so it
#: cannot pass for FluSight's series), is flagged national in meta.json and
#: is reported beside pooled scores, never inside them. One per dataset.
NATIONAL_NAMES = ("US", "USA", "UNITED STATES", "US (NATIONAL)", "NATIONAL")

#: tokens read as a missing value (R readr's NA set, plus common ones)
NA_TOKENS = {"", "na", "n/a", "nan", "null", "none", "-"}

#: dataset ids: slug + '-' + 12 hex of the identity digest
ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,31}-[0-9a-f]{12}")

#: the columns a file can name, by role, as normalized headers (lower case,
#: no spaces, underscores, hyphens or dots). A role takes the one column
#: whose header is among its aliases; see _map_columns for the two
#: canonical pairs that resolve by precedence.
ROLE_ALIASES = {
    "date": ("targetenddate", "date", "week", "weekend", "weekending",
             "enddate", "weekenddate", "weekendingdate"),
    "group": ("targetgroup", "location", "group", "locationname", "region",
              "jurisdiction"),
    "value": ("observation", "value", "count", "counts", "cases",
              "admissions", "hospitalizations", "hospitalisations"),
    "population": ("population", "pop"),
}
#: the hubverse extras (their own names only)
EXTRA_ALIASES = {"as_of": ("asof",), "target": ("target",),
                 "location_name": ("locationname",)}
#: the roles a column mapping may name; the first three are required
ROLES = ("date", "group", "value", "population")
REQUIRED = ("date", "group", "value")
#: the pairs FluBNF always read by precedence (the first wins, silently)
PRECEDENCE = {"date": ("targetenddate", "date"),
              "value": ("observation", "value")}
#: date headers that name the END of each week (see _week_side)
END_HEADERS = ("targetenddate", "weekend", "weekending", "enddate",
               "weekenddate", "weekendingdate")

#: separators tried when sniffing, with their names
DELIMITERS = {",": "comma", ";": "semicolon", "\t": "tab"}
#: encodings, as notices and summaries name them
ENCODING_NAMES = {"utf-8": "UTF-8", "utf-8-sig": "UTF-8", "utf-16": "UTF-16",
                  "utf-16-le": "UTF-16", "utf-16-be": "UTF-16",
                  "utf-32": "UTF-32", "utf-32-le": "UTF-32",
                  "utf-32-be": "UTF-32", "cp1252": "Windows-1252"}
#: a byte UTF-8 could not decode, as errors="surrogateescape" keeps it
_ESCAPED = re.compile("[\udc80-\udcff]")
#: a character UTF-8 did decode beyond ASCII
_UTF8_CHAR = re.compile("[^\x00-\x7f\udc80-\udcff]")

MAX_EXAMPLES = 3
#: row numbers a problem message lists before "and N more"
MAX_ROWS_SHOWN = 6
#: row numbers a Problem keeps for callers
MAX_ROWS_KEPT = 200
#: lines read to sniff the separator
SNIFF_LINES = 50

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday")


class DatasetError(Exception):
    """A dataset could not be ingested or found. ``problems`` holds the
    validation problems when the cause was the upload's content, and
    ``report`` the whole Report (headers, targets, summary) when there was
    one."""

    def __init__(self, message: str, problems: Optional[list] = None,
                 report: Optional["Report"] = None):
        super().__init__(message)
        self.problems = list(problems or [])
        self.report = report


@dataclass(frozen=True)
class Limits:
    """Upload limits, enforced while the bytes stream in."""
    max_bytes: int = 100 * 1024 * 1024
    max_rows: int = 1_500_000
    max_groups: int = 200


DEFAULT_LIMITS = Limits()


@dataclass(frozen=True)
class Problem:
    """One validation problem: a stable code for callers and tests, a
    human-readable message that names its rows and carries an example, and
    the row numbers themselves (the first MAX_ROWS_KEPT)."""
    code: str
    message: str
    rows: tuple = ()

    def __str__(self) -> str:
        return self.message

    @property
    def kind(self) -> str:
        return KIND_OF.get(self.code, "File")


#: problem kinds, in the order a report lists them
PROBLEM_KINDS = (
    ("File", ("empty", "encoding", "encoding_mixed", "csv", "quote",
              "separator_mixed", "limit_bytes", "limit_rows", "limit_groups",
              "kind_invalid", "target_required", "target_unknown",
              "target_blank")),
    ("Columns", ("missing_columns", "ambiguous_columns", "column_unknown",
                 "duplicate_columns", "ragged", "extra_fields", "split")),
    ("Dates", ("date_parse", "date_day_first", "date_ambiguous", "weekday",
               "weekday_end", "weekday_start", "as_of_parse",
               "as_of_ambiguous", "as_of_before_date")),
    ("Values", ("value_numeric", "value_format", "kind_ambiguous",
                "value_negative", "value_na", "value_not_integer")),
    ("Population", ("population_invalid", "population_missing",
                    "population_format")),
    ("Groups", ("group_blank", "group_name", "group_reserved",
                "national_multiple", "group_collision",
                "location_name_conflict")),
    ("Weeks", ("duplicate", "gap")),
)
KIND_OF = {c: k for k, codes in PROBLEM_KINDS for c in codes}


def problem_groups(problems) -> list:
    """[(kind, [Problem, ...]), ...] in PROBLEM_KINDS order, empty kinds
    left out: how the upload box and the CLI list a report."""
    order = {k: i for i, (k, _) in enumerate(PROBLEM_KINDS)}
    out = {}
    for p in problems:
        k = p.kind if isinstance(p, Problem) else "File"
        out.setdefault(k, []).append(p)
    return sorted(out.items(), key=lambda kv: order.get(kv[0], 0))


@dataclass
class Report:
    """What validate() found. ``ok`` is True only with no problems; warnings
    (notices) never block. ``summary`` describes the parsed data (empty when
    the file could not be read far enough). ``headers`` and ``guess`` feed a
    column mapping; ``targets`` the target picker."""
    problems: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    columns: dict = field(default_factory=dict)
    # parsed rows (as_of|None, name, source_key, date, value, population|None)
    records: list = field(default_factory=list, repr=False)
    sha256: str = ""
    n_bytes: int = 0
    headers: list = field(default_factory=list)
    guess: dict = field(default_factory=dict)
    # role -> ['#N', ...]: the columns that could each be it
    ambiguous: dict = field(default_factory=dict)
    targets: list = field(default_factory=list)
    encoding: str = ""
    delimiter: str = ""

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def codes(self) -> list:
        return [p.code for p in self.problems]

    @property
    def needs_mapping(self) -> bool:
        """True when the only problems are columns that could not be matched
        (missing or ambiguous): a column mapping resolves them."""
        return bool(self.problems) and bool(self.headers) and all(
            c in ("missing_columns", "ambiguous_columns", "column_unknown")
            for c in self.codes)

    def add(self, code: str, message: str, rows=()) -> None:
        self.problems.append(Problem(code, message,
                                     tuple(sorted(set(rows)))[:MAX_ROWS_KEPT]))


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


class _Replayable(io.RawIOBase):
    """Reads through a stream once, remembering the bytes while a second
    reading may be needed (a UTF-8 guess that turns out wrong is decoded
    again from the start as Windows-1252). ``forget`` stops remembering;
    what is held is still replayed, then dropped. Closing is a no-op, so a
    discarded text wrapper cannot close the stream under the next one."""

    def __init__(self, raw):
        self._raw = raw
        self._buf = bytearray()
        self._pos = 0
        self._remember = True

    def readable(self) -> bool:
        return True

    def close(self) -> None:                   # see the class docstring
        pass

    def rewind(self) -> None:
        self._pos = 0

    def forget(self) -> None:
        self._remember = False

    def head(self, n: int) -> bytes:
        """The first n bytes (fewer at the end), then back to the start."""
        out = bytearray()
        chunk = bytearray(n)
        while len(out) < n:
            k = self.readinto(memoryview(chunk)[:n - len(out)])
            if not k:
                break
            out += chunk[:k]
        self.rewind()
        return bytes(out)

    def readinto(self, b) -> int:
        if self._pos < len(self._buf):
            k = min(len(b), len(self._buf) - self._pos)
            b[:k] = self._buf[self._pos:self._pos + k]
            self._pos += k
            if not self._remember and self._pos >= len(self._buf):
                self._buf, self._pos = bytearray(), 0
            return k
        k = self._raw.readinto(b)
        if k and self._remember:
            self._buf += bytes(b[:k])
            self._pos += k
        return k or 0


def _latin1_rest(err):
    """Windows-1252 leaves five bytes undefined; read them as Latin-1."""
    return err.object[err.start:err.end].decode("latin-1"), err.end


codecs.register_error("flubnf-latin1", _latin1_rest)


def _open_source(source):
    """(binary stream, close?) for bytes, a path, or a binary file object."""
    if isinstance(source, (bytes, bytearray)):
        return io.BytesIO(bytes(source)), True
    if isinstance(source, (str, Path)):
        return open(source, "rb"), True
    return source, False


def detect_encoding(head: bytes) -> str:
    """The codec for a file's first bytes: a BOM decides; UTF-32 and UTF-16
    without one show as NUL bytes in three of every four, or every other,
    position; otherwise UTF-8 (a file with no UTF-8 character but bytes
    that are not UTF-8 is read as Windows-1252, see validate)."""
    if head.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if head.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        return "utf-32"
    if head.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"
    s = head[:2048]
    quarter = len(s) // 4
    if quarter >= 2:
        z = [s[i::4].count(0) for i in range(4)]
        if min(z[1:]) > 0.8 * quarter and z[0] < 0.05 * quarter:
            return "utf-32-le"
        if min(z[:3]) > 0.8 * quarter and z[3] < 0.05 * quarter:
            return "utf-32-be"
    half = len(s) // 2
    if half >= 2:
        even, odd = s[0::2].count(0), s[1::2].count(0)
        if odd > 0.4 * half and even < 0.05 * half:
            return "utf-16-le"
        if even > 0.4 * half and odd < 0.05 * half:
            return "utf-16-be"
    return "utf-8"


def sniff_delimiter(lines) -> str:
    """',' ';' or tab: the separator that splits the header (the first
    non-blank line) into the most named columns; ties go to the one whose
    rows agree most with the header's width, then to the comma."""
    best, score = ",", None
    for d in DELIMITERS:
        rows = [r for r in csv.reader(lines, delimiter=d)
                if any(c.strip() for c in r)]
        if not rows:
            continue
        head = sum(1 for c in rows[0] if c.strip())
        agree = sum(1 for r in rows[1:] if len(r) >= head)
        s = (head, agree)
        if score is None or s > score:
            best, score = d, s
    return best


# ------------------------------------------------------------------- dates

_TIME = (r"(?:[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:\s?[AaPp][Mm])?"
         r"(?:Z|[+-]\d{2}:?\d{2})?)?")
_DATE_FORMATS = (
    ("YYYY-MM-DD", re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})" + _TIME), "ymd"),
    ("YYYY/MM/DD", re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})" + _TIME), "ymd"),
    ("M/D/YYYY", re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})" + _TIME), "mdy"),
    ("M/D/YY", re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2})" + _TIME), "mdy2"),
    ("MM-DD-YYYY", re.compile(r"(\d{1,2})-(\d{1,2})-(\d{4})" + _TIME), "mdy"),
)


def _date_parts(text: str):
    """(format label, order, (a, b, c)) for the first matching format."""
    s = (text or "").strip()
    for label, rx, order in _DATE_FORMATS:
        m = rx.fullmatch(s)
        if m:
            return label, order, tuple(int(x) for x in m.groups())
    return None, None, None


def _year2(yy: int) -> int:
    """A two-digit year as a spreadsheet reads it: 00-29 -> 20xx, 30-99 ->
    19xx (never a year decades ahead)."""
    return yy + (2000 if yy < 30 else 1900)


def _ymd(order, parts):
    a, b, c = parts
    if order == "ymd":
        return a, b, c
    return (_year2(c) if order == "mdy2" else c), a, b


def parse_date(text: str):
    """(date, format label) for the accepted formats, else (None, None).

    Accepted: YYYY-MM-DD, YYYY/MM/DD, M/D/YYYY, M/D/YY and MM-DD-YYYY,
    each optionally followed by a time ("2024-01-06 00:00:00"), which is
    dropped. Day-first (D/M/Y) is not accepted: it is ambiguous for every
    day <= 12 and a silent misparse would shift weeks. Two-digit years are
    read as a spreadsheet reads them: 00-29 -> 20xx, 30-99 -> 19xx."""
    label, order, parts = _date_parts(text)
    if label is None:
        return None, None
    try:
        return date(*_ymd(order, parts)), label
    except ValueError:
        return None, None


def _year_first2(text: str) -> bool:
    """True for a string that reads as YY/MM/DD ('24/01/06'): it could as
    well be day-first, so it is called neither."""
    label, order, parts = _date_parts(text)
    if order != "mdy2":
        return False
    try:
        date(_year2(parts[0]), parts[1], parts[2])
    except ValueError:
        return False
    return True


def _day_first(text: str):
    """The date a month-first string would be if read day-first, when only
    that reading is valid (the first number is over 12, and it is not a
    YY/MM/DD date either), else None."""
    label, order, parts = _date_parts(text)
    if order not in ("mdy", "mdy2") or parts[0] <= 12 or _year_first2(text):
        return None
    y, _, _ = _ymd(order, parts)
    try:
        return date(y, parts[1], parts[0])
    except ValueError:
        return None


def _swapped(text: str):
    """A month-first date read day-first (both numbers <= 12), else None."""
    label, order, parts = _date_parts(text)
    if order not in ("mdy", "mdy2") or parts[0] > 12 or parts[1] > 12:
        return None
    y, _, _ = _ymd(order, parts)
    try:
        return date(y, parts[1], parts[0])
    except ValueError:
        return None


def _month_first_only(text: str) -> bool:
    """True for a date written M/D that reads month-first only: its second
    number is a day over 12 (1/13/2024). A date whose day equals its month
    (05/05/2024) reads the same either way and proves neither order."""
    _, order, parts = _date_parts(text)
    return (order in ("mdy", "mdy2") and parts[1] > 12
            and parse_date(text)[0] is not None)


def saturday_on_or_before(d: date) -> date:
    """The MMWR week-ending Saturday on or before ``d`` (the vintage key of
    an as_of: Saturday as_of -> itself, Wednesday -> the Saturday before)."""
    return d - timedelta(days=(d.weekday() - 5) % 7)


def week_ending(d: date) -> date:
    """The Saturday that ends ``d``'s MMWR week (Sunday to Saturday)."""
    return d + timedelta(days=(5 - d.weekday()) % 7)


# ----------------------------------------------------------------- numbers

#: "1,234" / "1,234,567" / "1,234.5": comma thousands (first group 1-9)
_TH = re.compile(r"[+-]?[1-9]\d{0,2}(?:,\d{3})+(?:\.\d+)?")
#: "1.234" / "1.234.567" / "1.234,5": dot thousands (first group 1-9)
_DOTG = re.compile(r"[+-]?[1-9]\d{0,2}(?:\.\d{3})+(?:,\d+)?")
#: "1,5" / "0,25" / "1234,5": one comma between digits
_ONE_COMMA = re.compile(r"[+-]?\d+,\d+")
#: "1,234" or "1.234": either separator reading is possible
_EITHER = re.compile(r"[+-]?[1-9]\d{0,2}[.,]\d{3}")
#: a plain number as written in a CSV: ASCII digits, an optional decimal
#: point and exponent (float() alone also takes "1_000", full-width digits
#: and "infinity")
_PLAIN = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?",
                    re.ASCII)
#: the two halves of "1,234" or "1,234.5" written without quotes in a comma
#: file: 1 to 3 digits, then exactly 3 (and any decimals) in the next cell
_CUT_HEAD = re.compile(r"[+-]?\d{1,3}", re.ASCII)
_CUT_TAIL = re.compile(r"\d{3}(?:\.\d+)?", re.ASCII)


def number_style(texts, delimiter: str = ","):
    """How one column writes its numbers: (style, why) with style 'plain',
    'thousands' (',' groups, '.' decimals) or 'decimal_comma' ('.' groups,
    ',' decimals), or (None, why) when the column is ambiguous.

    A comma file's commas are thousands (a quoted "1,234"); decimal commas
    are read in a semicolon or tab file when some value can only be one
    ("1,5", "0,25", "1.234,5"). A column that mixes a decimal comma with a
    decimal point, or whose only separators could go either way ("1,234"
    or "1.234" in a semicolon or tab file), is ambiguous."""
    texts = [t for t in texts if t and ("," in t or "." in t)]
    if not texts:
        return "plain", ""
    dec_comma = [t for t in texts
                 if ("," in t and (_ONE_COMMA.fullmatch(t) or _DOTG.fullmatch(t))
                     and not _TH.fullmatch(t))
                 or (_DOTG.fullmatch(t) and t.count(".") > 1)]
    dec_point = [t for t in texts
                 if ("," in t and _TH.fullmatch(t)
                     and (t.count(",") > 1 or "." in t))
                 or ("." in t and "," not in t and not _DOTG.fullmatch(t))]
    either = [t for t in texts if _EITHER.fullmatch(t)]
    if dec_comma and dec_point:
        return None, (f"decimal commas like {dec_comma[0]} mixed with "
                      f"decimal points like {dec_point[0]}")
    if dec_comma:
        if delimiter == ",":
            return None, (f"a decimal comma like {dec_comma[0]}, read only in "
                          "semicolon- or tab-separated files")
        return "decimal_comma", ""
    if dec_point or delimiter == ",":
        return ("thousands" if any("," in t for t in texts) else "plain"), ""
    if either:
        t = either[0]
        return None, (f"{t} could be {t.replace(',', '').replace('.', '')} "
                      f"or {t.replace(',', '.')}")
    return "plain", ""


def grouping_or_decimal(texts, style, delimiter: str = ",") -> str:
    """The decimal mark ('.' or ',') a column's numbers are read with when
    every number written with it has 1 to 3 digits, the mark and exactly 3
    more, so it could as well separate thousands ("1.234" in a comma file:
    1.234 or 1234; "1,234" in a semicolon or tab file: 1.234 or 1234);
    else ''. Only the value kind can tell: counts are whole, so for them
    the mark would separate thousands (refused: they are written without),
    while rates read it as decimals. ``style`` is number_style's for the
    column: a comma file reads '.' as its decimal mark, a decimal-comma
    column ',', and a semicolon or tab column whose only separators are
    such commas (number_style's None) ',' as well."""
    seps = [t for t in texts if t and ("," in t or "." in t)]
    comma_only = (style is None and delimiter != "," and bool(seps)
                  and all("," in t and _EITHER.fullmatch(t) for t in seps))
    if style in ("plain", "thousands"):
        mark = "."
    elif style == "decimal_comma" or comma_only:
        mark = ","
    else:
        return ""
    marked = [t for t in seps if mark in t]
    return mark if marked and all(_EITHER.fullmatch(t) for t in marked) \
        else ""


def _num(text: str, style: str = "plain"):
    """float, None for an NA token, or raise ValueError."""
    s = (text or "").strip()
    if s.lower() in NA_TOKENS:
        return None
    if style == "thousands" and "," in s:
        if not _TH.fullmatch(s):
            raise ValueError(s)
        s = s.replace(",", "")
    elif style == "decimal_comma":
        if "." in s:
            if not _DOTG.fullmatch(s):
                raise ValueError(s)
            s = s.replace(".", "")
        s = s.replace(",", ".")
    elif "," in s:
        raise ValueError(s)
    if not _PLAIN.fullmatch(s):
        raise ValueError(s)
    v = float(s)
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(s)
    return v


def _fmt_num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else repr(float(v))


def _int_or_float(v: float):
    return int(v) if float(v).is_integer() else float(v)


def _examples(items) -> str:
    return ", ".join(_vis(x) for x in list(items)[:MAX_EXAMPLES])


def _rows(lines, total=None) -> str:
    """'row 5' / 'rows 5, 9, 12 and 40 more' (``total`` counts rows past
    the ones listed, when only the first few were kept)."""
    ls = sorted(set(lines))
    total = len(ls) if total is None else total
    shown = ", ".join(str(x) for x in ls[:MAX_ROWS_SHOWN])
    more = total - min(len(ls), MAX_ROWS_SHOWN)
    return (f"row{'s' if total != 1 else ''} {shown}"
            + (f" and {more:,} more" if more > 0 else ""))


class _Tally:
    """Rows sharing one finding, bounded however long the file: how many,
    the first MAX_ROWS_KEPT row numbers and the first MAX_EXAMPLES
    examples."""

    def __init__(self):
        self.n, self.lines, self.eg = 0, [], []

    def add(self, line: int, eg=None) -> None:
        self.n += 1
        if len(self.lines) < MAX_ROWS_KEPT:
            self.lines.append(line)
        if eg is not None and len(self.eg) < MAX_EXAMPLES:
            self.eg.append((line, eg))

    def merge(self, other: _Tally) -> None:
        self.n += other.n
        self.lines = sorted(self.lines + other.lines)[:MAX_ROWS_KEPT]
        self.eg = sorted(self.eg + other.eg,
                         key=lambda x: x[0])[:MAX_EXAMPLES]


def _norm_header(h: str) -> str:
    return re.sub(r"[\s_\-.]+", "", (h or "").strip().strip('"').lower())


#: a header word naming the END or the START of each week ('ending',
#: 'weekEnd', 'period_end', 'week_start', 'Week beginning')
_END_WORD = re.compile(r"(?:week|wk|period|epiweek)?(?:end|ending|ended|ends)"
                       r"(?:date|day)?")
_START_WORD = re.compile(r"(?:week|wk|period|epiweek)?(?:start|starting|"
                         r"started|starts|begin|begins|beginning|commencing)"
                         r"(?:date|day)?")


def _week_side(header: str):
    """'end' when a date header names the end of each week ('week_ending',
    'Week ending (Sunday)', 'period_end', 'PeriodEnd'), 'start' when it
    names the start ('week_start', 'Week beginning'), else None."""
    words = re.findall(r"[a-z]+", re.sub(r"([a-z])([A-Z])", r"\1 \2",
                                         header or "").lower())
    end = (_norm_header(header) in END_HEADERS
           or any(_END_WORD.fullmatch(w) for w in words))
    start = any(_START_WORD.fullmatch(w) for w in words)
    if end == start:
        return None
    return "end" if end else "start"



#: control characters, shown in messages as their Unicode pictures (a NUL
#: as U+2400) instead of invisibly
_CTRL = re.compile("[\x00-\x08\x0a-\x1f]")


def _vis(text) -> str:
    return _CTRL.sub(lambda m: chr(0x2400 + ord(m.group())), str(text))


def _blank_row(row) -> bool:
    """A row with nothing in it: empty cells, or only separators of another
    kind (',,,' in a semicolon file) and a DOS end-of-file mark (Ctrl-Z)."""
    return all(not c.replace("\x1a", "").strip().strip(",;\t").strip()
               for c in row)




def pf_stem(name: str) -> str:
    """A group's particle-filter cell-directory and BNGL-suffix stem
    (engines.pf.dataset_tag): ASCII letters, digits and '_', anything else
    '_'. A name with non-ASCII letters also gets a short digest of itself
    case-folded, so '東京' and '大阪' (both '__') or 'Zürich' and 'Zérich'
    stay apart; an ASCII name's stem is unchanged."""
    stem = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not name.isascii():
        stem += "_" + hashlib.sha1(name.casefold().encode()).hexdigest()[:6]
    return stem


def _norm_name(name: str) -> str:
    """The form two group names must not share: the PF stem, folded, as
    macOS/Windows filesystems fold case."""
    return pf_stem(name).casefold()


def _text(cell: str) -> str:
    """A name cell as stored: trimmed, Unicode NFC (a decomposed accent and
    its composed twin are one name)."""
    return unicodedata.normalize("NFC", (cell or "").strip())


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:32]
    return s.strip("-") or "dataset"


# -------------------------------------------------------------- validation

def validate(source, *, kind: Optional[str] = None,
             week_start_sunday: bool = False, target: Optional[str] = None,
             limits: Limits = DEFAULT_LIMITS, columns: Optional[dict] = None,
             _tee=None) -> Report:
    """Parse and validate one upload; every problem is reported at once.

    ``source`` is bytes, a path, or a binary file object. ``kind`` is the
    declared value kind ('count' or 'rate'; None or '' leaves it to the
    values, and the summary reports the inferred kind). ``target`` picks
    one target when the file carries several. ``columns`` maps roles
    (``ROLES``) to header names (or '#N', the Nth column) where the headers
    alone do not say. ``week_start_sunday`` is accepted and ignored: a
    file's dates are moved to their week-ending Saturday whatever weekday
    they share.

    The base checks: required columns; dates parseable; value numeric,
    >= 0, never NA in a grouped CSV; no duplicate (date, group); no gap
    over 8 days within a group. FluBNF adds: one weekday per file; safe,
    unique group names; one target; population > 0 on every row when the
    column exists; one name per location; no snapshot week after its as_of;
    and the size limits, enforced while streaming.
    """
    kind = kind or None
    stream, close = _open_source(source)
    capped = _CappedReader(stream, limits.max_bytes, tee=_tee)
    src = _Replayable(capped)
    rep, cols, raw_rows = Report(), None, []
    try:
        try:
            enc = detect_encoding(src.head(4096))
            if enc != "utf-8":
                src.forget()
            scan = _Scan()
            rep, cols, raw_rows = _read(src, enc, limits, columns, scan)
            if scan.bad and enc == "utf-8" and scan.utf8 is None:
                # not one UTF-8 character: a Windows-1252 file, read again
                src.forget()
                rep, cols, raw_rows = _read(src, "cp1252", limits, columns)
                rep.warnings.insert(0, "Not UTF-8 text: read as Windows-1252 "
                                    "(a spreadsheet's usual CSV).")
            elif scan.bad:
                # a BOM says UTF-8 (an encoding problem); UTF-8 text beside
                # bytes that are not mixes encodings
                rep, cols = Report(encoding=enc), None
                rep.add("encoding" if enc == "utf-8-sig" else
                        "encoding_mixed", _mixed_message(enc, scan), scan.bad)
        except _LimitExceeded as e:
            rep, cols = Report(), None
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
        except UnicodeDecodeError as e:
            rep, cols = Report(), None
            rep.add("encoding", f"The file is not readable "
                    f"{ENCODING_NAMES.get(enc, enc)} text (e.g., byte "
                    f"{e.object[e.start:e.start + 1]!r} cannot be decoded). "
                    "Save it as CSV UTF-8.")
        except csv.Error as e:
            rep, cols = Report(), None
            rep.add("csv", f"The file is not a readable CSV: {e}.")
    finally:
        rep.sha256, rep.n_bytes = capped.sha.hexdigest(), capped.n
        if close:
            stream.close()
    if cols is None:
        return rep
    rep.columns = {k: v for k, v in cols.items() if not k.startswith("_")}
    _check_rows(rep, raw_rows, cols, kind=kind, target=target)
    if rep.encoding == "cp1252":
        # a Mac Roman or Cyrillic file reads as Windows-1252 without an
        # error, its letters swapped one for one: show what was read
        odd = [g for g in rep.summary.get("groups", []) if not g.isascii()]
        if odd:
            rep.warnings = [
                w + (f" Check these names: {_examples(odd)}; if they look "
                     "wrong, save the file as CSV UTF-8.")
                if w.startswith("Not UTF-8 text") else w
                for w in rep.warnings]
    return rep


class _Scan:
    """What the UTF-8 reading met: rows holding bytes it could not decode
    (``bad``, with the first few lines as ``examples``) and the first row
    holding a character it did decode beyond ASCII (``utf8``)."""

    def __init__(self):
        self.bad, self.examples, self.utf8 = [], [], None

    def lines(self, text):
        """The text's lines, noting each as it passes (line numbers count
        as the csv reader's do: every physical line)."""
        for n, line in enumerate(text, 1):
            if not line.isascii():
                if _ESCAPED.search(line):
                    self.bad.append(n)
                    if len(self.examples) < MAX_EXAMPLES:
                        self.examples.append((n, line))
                if self.utf8 is None and _UTF8_CHAR.search(line):
                    self.utf8 = (n, line)
            yield line


def _shown(line: str) -> str:
    """A line for a message: undecodable bytes as U+FFFD, at most 60
    characters."""
    t = _ESCAPED.sub("\ufffd", line.strip())
    return t if len(t) <= 60 else t[:57] + "..."


def _mixed_message(enc: str, scan: _Scan) -> str:
    """The refusal of a UTF-8 file holding bytes that are not UTF-8."""
    ln, line = scan.examples[0]
    byte = ", ".join(f"0x{ord(c) - 0xDC00:02X}"
                     for c in dict.fromkeys(_ESCAPED.findall(line)))
    bad = (f"{len(scan.bad)} row(s) hold bytes that are not UTF-8 "
           f"({_rows(scan.bad)}; e.g., row {ln}: {_shown(line)}, byte "
           f"{byte})")
    if enc == "utf-8-sig" or scan.utf8 is None:   # a BOM says UTF-8
        return (f"The file is marked as UTF-8, but {bad}. Retype the "
                "characters shown as \ufffd and save the file again.")
    uln, uline = scan.utf8
    return (f"The file mixes encodings: it holds UTF-8 text (e.g., row "
            f"{uln}: {_shown(uline)}), but {bad}, as a Windows-1252 "
            "program writes them. Reading it either way would garble one "
            "of the two: retype the characters shown as \ufffd and save "
            "the file as CSV UTF-8.")


def _read(src: _Replayable, enc: str, limits: Limits, columns,
          scan: Optional[_Scan] = None):
    """One reading pass: (report, columns or None, [(row number, {role:
    cell})]). UTF-8 keeps a byte it cannot decode (surrogateescape) and
    notes it in ``scan``; the caller decides. Raises UnicodeDecodeError
    (UTF-16/32), csv.Error or _LimitExceeded."""
    rep = Report(encoding=enc)
    src.rewind()
    utf8 = enc in ("utf-8", "utf-8-sig")
    text = io.TextIOWrapper(
        io.BufferedReader(src), encoding=enc, newline="",
        errors=("flubnf-latin1" if enc == "cp1252" else
                "surrogateescape" if utf8 else "strict"))
    lines = (scan or _Scan()).lines(text) if utf8 else text
    sample = list(itertools.islice(lines, SNIFF_LINES))
    # a spreadsheet's "sep=;" first line names the separator; the
    # spreadsheet hides it, so the header below it is row 1
    sep = re.fullmatch(r'\s*"?sep=(.)"?[,;\t]*\s*', sample[0]) if sample else None
    if sep and sep.group(1) in DELIMITERS:
        sample = sample[1:]
        delim = sep.group(1)
    else:
        delim = sniff_delimiter(sample)
    rep.delimiter = delim
    reader = csv.reader(itertools.chain(sample, lines), delimiter=delim)
    header = None
    for row in reader:
        if not _blank_row(row):
            header = row
            break
    if header is None:
        rep.add("empty", "The file is empty: expected a header row "
                "such as date,target_group,value.")
        return rep, None, []
    header = [h.replace("\ufeff", "").strip() for h in header]
    while header and not header[-1]:              # trailing empty columns
        header.pop()
    if any("\x00" in h for h in header):
        rep.add("encoding", "The header holds NUL characters: the file is "
                "not text in an encoding FluBNF reads. Save it as CSV "
                "UTF-8.")
        return rep, None, []
    rep.headers = list(header)
    cols = _map_columns(header, rep, columns)
    if cols is None:
        return rep, None, []
    cols["_delim"] = delim
    idx = cols["_idx"]
    used = set(idx.values())
    need = max(used) + 1
    width = len(header)
    groups_seen = set()
    ragged, raw_rows, ragged_eg = [], [], ""
    # cells past the header's columns: an unquoted separator inside a value
    # ("1,234") split it, and slicing would keep the wrong half
    extra = _Tally()
    # a row longer than the shortest row that fills the header, its extra
    # cell empty but text in an ignored column: a split whose second half
    # went into that column ('1,234,' over 'date,group,value,comment')
    longer, complete = {}, None
    # a value or name split so that its second half lands in the IGNORED
    # column right after it, which a row of the same length hides (a
    # writer that drops trailing empty cells): [index, rows, rows whose
    # next cell is no number]
    num_cut, txt_cut = {}, {}
    for role in ("value", "population", "group", "location_name"):
        i = idx.get(role)
        if i is None or i + 1 >= width or i + 1 in used:
            continue
        if role in ("value", "population") and delim == ",":
            num_cut[role] = [i, _Tally(), 0]
        elif role in ("group", "location_name") and delim in ",;":
            txt_cut[role] = [i, _Tally()]
    gcol = idx["group"]
    # rows whose quote, opened and not closed, took in the rows below
    quoted = []
    # rows written with another separator, by that separator
    resep = {}
    prev = reader.line_num
    for row in reader:
        # a row is numbered by the line it starts on
        line, prev = prev + 1, reader.line_num
        if _blank_row(row):
            continue
        if len(raw_rows) >= limits.max_rows:
            raise _LimitExceeded("rows")
        if prev > line:
            # a cell over several lines: a note that runs on is kept, but
            # one holding what reads as rows of the file lost them
            hit = _swallowed(row, delim, idx["date"])
            if hit is not None:
                quoted.append((line, prev) + hit)
                if any("\n" in row[i] or "\r" in row[i]
                       for i in used if i < len(row)):
                    continue
        n = len(row)
        if n == 1:
            # one cell that another separator splits into the columns: a
            # row written with a different separator, reported as such
            # (not as a blank group, a bad date and a missing value)
            d2 = next((d for d in DELIMITERS if d != delim and len(next(
                csv.reader([row[0]], delimiter=d), [])) >= need), None)
            if d2 is not None:
                resep.setdefault(d2, _Tally()).add(line, row[0])
                continue
        cut = False
        for c in num_cut.values():
            i = c[0]
            head = row[i].strip() if i < n else ""
            tail = row[i + 1] if i + 1 < n else ""
            if _CUT_HEAD.fullmatch(head) and _CUT_TAIL.fullmatch(tail):
                c[1].add(line, (head, tail))
                cut = True
            elif not _PLAIN.fullmatch(tail.strip()):
                c[2] += 1
        for c in txt_cut.values():
            i = c[0]
            head = row[i] if i < n else ""
            tail = row[i + 1] if i + 1 < n else ""
            if (tail[:1].isspace() and tail.strip() and head.strip()
                    and not head[:1].isspace()):
                c[1].add(line, (head, tail))
                cut = True
        if n > width and any(c.strip() for c in row[width:]):
            extra.add(line, row)
        elif n >= width:
            complete = n if complete is None else min(complete, n)
            if n > width and not cut and any(
                    row[k].strip() for k in range(width) if k not in used):
                longer.setdefault(n, _Tally()).add(line, row)
        if n < need:
            if not ragged:
                ragged_eg = delim.join(row)
            ragged.append(line)
            row = row + [""] * (need - n)
        g = row[gcol].strip()
        if g not in groups_seen:
            groups_seen.add(g)
            if len(groups_seen) > limits.max_groups:
                raise _LimitExceeded("groups")
        raw_rows.append((line, {k: row[i] for k, i in idx.items()}))
    if quoted:
        starts = [q[0] for q in quoted]
        ln, end, i, text = quoted[0]
        col = header[i] if i < width and header[i] else f"#{i + 1}"
        rep.add("quote", f"{len(quoted)} row(s) open a quote (\") that is "
                "not closed on that row, so the rows below were read as part "
                f"of one cell ({_rows(starts)}; e.g., row {ln}'s '{col}' "
                f"cell takes in rows {ln + 1} to {end}, such as "
                f"{_shown(text)}). Delete the stray quote, or close it on "
                "its own row.", starts)
    for d2, t in resep.items():
        ln, text = t.eg[0]
        if t.n >= len(raw_rows):
            # most rows: the header and the rows use different separators
            rep.problems, rep.warnings = [], []
            rep.add("separator_mixed", f"The header is separated by "
                    f"{DELIMITERS[delim]}s but the rows by {DELIMITERS[d2]}s "
                    f"({_rows(t.lines, t.n)}; e.g., row {ln}: {_shown(text)}"
                    "). Save the file again with one separator throughout.",
                    t.lines)
            return rep, None, []
        rep.add("separator_mixed", f"{t.n} row(s) are separated by "
                f"{DELIMITERS[d2]}s, not {DELIMITERS[delim]}s like the rest "
                f"of the file ({_rows(t.lines, t.n)}; e.g., row {ln}: "
                f"{_shown(text)}). Save the file again with one separator "
                "throughout.", t.lines)
    if ragged:
        rep.add("ragged", f"{len(ragged)} row(s) have fewer fields than the "
                f"columns they need ({_rows(ragged)}; e.g., row {ragged[0]}: "
                f"{_shown(ragged_eg) or '(empty)'}).", ragged)
    for n, t in longer.items():
        if n > complete:
            extra.merge(t)
    if extra.n:
        ln, cells = extra.eg[0]
        shown = _vis(delim.join(cells))
        shown = shown if len(shown) <= 60 else shown[:57] + "..."
        how = ("An unquoted comma splits a value in two: write 1,234 as "
               '"1,234" or 1234, and quote a name that holds a comma '
               '("Bern, Stadt").' if delim == "," else
               f"An unquoted {DELIMITERS[delim]} splits a value in two: "
               "quote a value that holds one.")
        rep.add("extra_fields", f"{extra.n} row(s) have more fields than "
                f"the header's {width} column(s) ({_rows(extra.lines, extra.n)}"
                f"; e.g., row {ln}: {shown}). {how}", extra.lines)
    for role, (i, t, other) in num_cut.items():
        if not t.n:
            continue
        ln, (a, b) = t.eg[0]
        what = (f"the '{cols[role]}' cell is 1 to 3 digits and the ignored "
                f"'{header[i + 1]}' column after it holds 3 more")
        if other:
            # that column is blank or text elsewhere: these are halves
            rep.add("split", f"{t.n} row(s) look like a number split in two "
                    f"by an unquoted comma: {what} ({_rows(t.lines, t.n)}; "
                    f"e.g., row {ln}: {a} then {b}, likely {a},{b}). Write "
                    f'1,234 as "1,234" or 1234.', t.lines)
        elif t.n == len(raw_rows):
            # on every row: a 3-digit column of its own, or every number
            # split; say so
            rep.warnings.append(
                f"On every row {what} (e.g., row {ln}: {a} then {b}): if "
                f"they are numbers like {a},{b} split by an unquoted comma, "
                f'write them as "{a},{b}" or {a}{b}.')
    for role, (i, t) in txt_cut.items():
        if not t.n:
            continue
        ln, (a, b) = t.eg[0]
        sep = DELIMITERS[delim]
        rep.add("split", f"{t.n} row(s) look like a name split in two by an "
                f"unquoted {sep}: the ignored '{header[i + 1]}' column after "
                f"'{cols[role]}' starts with a space ({_rows(t.lines, t.n)}; "
                f"e.g., row {ln}: '{a}' then '{b}', likely "
                f'"{a}{delim}{b}"). Quote a name that holds a {sep} '
                f'("Bern{delim} Stadt"), or remove the space that starts '
                f"those '{header[i + 1]}' cells.", t.lines)
    return rep, cols, raw_rows


def _swallowed(row, delim: str, date_at: int):
    """(cell index, line) for the first line inside a multi-line cell that
    reads as a row of the file (a date where the date column is): a quote
    opened and never closed on its row took in the rows below, which
    Python's csv reader does to the end of the file. None for a note that
    merely runs over two lines."""
    for i, c in enumerate(row):
        if "\n" not in c and "\r" not in c:
            continue
        for text in c.splitlines()[1:]:
            cells = next(csv.reader([text], delimiter=delim), [])
            if len(cells) > max(date_at, 1):
                t = cells[date_at].strip()
                if parse_date(t)[0] is not None or _day_first(t):
                    return i, text
    return None


def _column_ref(header, want: str):
    """The index a mapping names: '#N' (1-based), an exact header, or a
    header equal after normalization; None when it names none or several."""
    w = (want or "").strip()
    if re.fullmatch(r"#\d+", w):
        i = int(w[1:]) - 1
        return i if 0 <= i < len(header) and header[i] else None
    hits = [i for i, h in enumerate(header) if h == w]
    if not hits:
        n = _norm_header(w)
        hits = [i for i, h in enumerate(header) if n and _norm_header(h) == n]
    return hits[0] if len(hits) == 1 else None


def _map_columns(header, rep: Report, columns=None):
    """{role: header text, '_idx': {role: index}, 'format': ...} or None
    (with the problem recorded) when a required column is missing or two
    columns could both be it. ``columns`` (role -> header) overrides."""
    norm = [_norm_header(h) for h in header]
    times = Counter(header)
    label = [h if times[h] == 1 else f"{h} (#{i + 1})"
             for i, h in enumerate(header)]
    chosen, missing, ambiguous, unknown = {}, [], {}, []
    for role, want in (columns or {}).items():
        if role not in ROLES or not str(want or "").strip():
            continue
        i = _column_ref(header, str(want))
        if i is None or i in chosen.values():
            unknown.append((role, str(want)))
        else:
            chosen[role] = i
    for role in ROLES:
        if role in chosen or any(r == role for r, _ in unknown):
            continue
        taken = set(chosen.values())
        cands = [i for i, h in enumerate(norm)
                 if h in ROLE_ALIASES[role] and i not in taken]
        if role == "group" and any(norm[i] == "location" for i in cands):
            # a hubverse file: location is the key, location_name its label
            cands = [i for i in cands if norm[i] != "locationname"]
        pre = PRECEDENCE.get(role)
        if pre and len(cands) > 1 and all(norm[i] in pre for i in cands):
            first = [i for i in cands if norm[i] == pre[0]]
            if len(first) == 1:
                cands = first
        if len(cands) == 1:
            chosen[role] = cands[0]
        elif len(cands) > 1:
            ambiguous[role] = cands
        elif role in REQUIRED:
            missing.append(role)
    rep.guess = {r: f"#{i + 1}" for r, i in chosen.items()}
    rep.ambiguous = {r: [f"#{i + 1}" for i in c] for r, c in ambiguous.items()}
    found = ", ".join(h for h in header if h) or "(none)"
    if unknown:
        rep.add("column_unknown", "No single unused column named "
                + "; ".join(f"{w!r} for the {r}" for r, w in unknown)
                + f". Found: {found}.")
    if missing:
        eg = {"date": "date, week, target_end_date",
              "group": "target_group, group, location",
              "value": "value, count, cases, observation"}
        rep.add("missing_columns", "No column for the " + " or the ".join(
            f"{r} (e.g., {eg[r]})" for r in missing)
            + f". Found: {found}. Choose which column holds each.")
    for role, cands in ambiguous.items():
        names = " and ".join(repr(label[i]) for i in cands)
        # for the date, the column of week ends (FluSight keys a week by
        # its end), never a report date that happens to come first
        ends = [i for i in cands if _week_side(header[i]) == "end"]
        eg = label[ends[0]] + ", the end of each week" if (
            role == "date" and len(ends) == 1) else label[cands[0]]
        rep.add("ambiguous_columns", f"Two columns could be the {role}: "
                f"{names}. Choose one (e.g., {eg}), or keep only one in the "
                "file.")
    if rep.problems:
        return None
    g = norm[chosen["group"]]
    cols = {"format": "hubverse" if g == "location" else "grouped",
            "_date_side": _week_side(header[chosen["date"]])}
    idx = dict(chosen)
    for role, i in chosen.items():
        cols[role] = label[i]
    for extra, names in EXTRA_ALIASES.items():
        if extra == "location_name" and g != "location":
            continue
        hits = [i for i, h in enumerate(norm)
                if h in names and i not in idx.values()]
        if len(hits) == 1:
            cols[extra], idx[extra] = label[hits[0]], hits[0]
        elif len(hits) > 1:
            rep.add("duplicate_columns", f"Two columns could be the "
                    f"{extra}: " + " and ".join(repr(label[i]) for i in hits)
                    + f" (e.g., {label[hits[0]]}). Keep only one in the file.")
            return None
    used = set(idx.values())
    ignored = [h for i, h in enumerate(header) if i not in used and h]
    if ignored:
        rep.warnings.append(f"Ignored column(s): {', '.join(ignored)}.")
    cols["_idx"] = idx
    return cols


def _check_rows(rep: Report, raw_rows: list, cols: dict, *, kind,
                target) -> None:
    fmt = cols["format"]
    delim = cols.get("_delim", ",")
    if kind is not None and kind not in KINDS:
        rep.add("kind_invalid", f"Value kind {kind!r} is not one of "
                f"{', '.join(KINDS)}: say whether values are counts or "
                "rates (e.g., count).")

    # one target per dataset
    tgt_used = None
    if "target" in cols:
        targets = sorted({r["target"].strip() for _, r in raw_rows})
        rep.targets = [t for t in targets if t]
        blank = [ln for ln, r in raw_rows if not r["target"].strip()]
        if blank and rep.targets:
            # which target such a row belongs to, the file does not say
            rep.add("target_blank", f"The '{cols['target']}' column is "
                    f"blank on {len(blank)} row(s) ({_rows(blank)}; e.g., "
                    f"row {blank[0]}: {_place(_rows_of(raw_rows, blank[:1])[0])}"
                    "), while the others name "
                    f"{_examples(rep.targets)}. Give every row its target, "
                    "or delete those rows.", blank)
            raw_rows = [(ln, r) for ln, r in raw_rows if r["target"].strip()]
        if target is not None:
            if target not in rep.targets:
                rep.add("target_unknown", f"Target {target!r} is not in the "
                        f"file. Targets found: "
                        f"{_examples(rep.targets) or '(none)'}.")
                return
            raw_rows = [(ln, r) for ln, r in raw_rows
                        if r["target"].strip() == target]
            tgt_used = target
        elif len(rep.targets) > 1:
            rep.add("target_required", f"The file holds {len(rep.targets)} "
                    f"targets ({', '.join(rep.targets)}); choose one.")
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

    has_pop, has_asof = "population" in cols, "as_of" in cols
    has_lname = "location_name" in cols
    vcol = cols["value"]
    vtexts = [r["value"].strip() for _, r in raw_rows]
    vstyle, vwhy = number_style(vtexts, delim)
    # every number written with the column's decimal mark could as well
    # carry a thousands separator (987, 1.234, 12.345 in a comma file): the
    # declared kind decides, and undeclared nothing is inferred
    mark = grouping_or_decimal(vtexts, vstyle, delim)
    if mark == "," and vstyle is None:
        vstyle, vwhy = "decimal_comma", ""
    pstyle, pwhy = (number_style([r["population"].strip()
                                  for _, r in raw_rows], delim)
                    if has_pop else ("plain", ""))
    for col, style, why, code, key in (
            (vcol, vstyle, vwhy, "value_format", "value"),
            (cols.get("population"), pstyle, pwhy, "population_format",
             "population")):
        if key == "value" and mark:
            continue                    # said below, with the kind
        if style is None or style == "decimal_comma":
            texts = [r[key].strip() for _, r in raw_rows]
        if style is None:
            seps = [(ln, t) for (ln, _), t in zip(raw_rows, texts)
                    if "," in t or "." in t]
            lines = [ln for ln, _ in seps]
            # the row of the number the reason quotes
            at = next((ln for ln, t in seps if t in why), lines[0])
            rep.add(code, f"The '{col}' column's numbers are ambiguous "
                    f"({_rows(lines)}; e.g., {why}; row {at}: "
                    f"{_place(_rows_of(raw_rows, [at])[0])}). Write them "
                    "without thousands separators, with a decimal point.",
                    lines)
        elif style == "thousands":
            rep.warnings.append(f"Read the '{col}' column's commas as "
                                "thousands separators (1,234 = 1234).")
        elif style == "decimal_comma":
            read = []
            if any("," in t for t in texts):
                read.append("decimal commas (1,5 = 1.5)")
            if any("." in t for t in texts):
                read.append("dots as thousands separators (1.234 = 1234)")
            rep.warnings.append(f"Read the '{col}' column's "
                                + " and ".join(read) + ".")

    bad_dates, day_first, bad_asof = [], [], []
    # as_of dates that read both month-first and day-first (03/01/2024),
    # each month-first reading's day-first twin, and whether any as_of
    # reads month-first only (1/13/2024; never 05/05/2024, which reads the
    # same both ways)
    asof_both, asof_alt, asof_md = _Tally(), {}, False
    bad_vals, neg, na, nonint = [], [], [], []
    # values written with a mark that could separate thousands (see mark)
    either = []
    bad_pop, miss_pop = [], []
    formats = set()
    parsed = []                                   # (line, raw date, date)
    rows = []                                     # (line, a, name, key, d, v, p)
    for ln, r in raw_rows:
        raw_d = r["date"].strip()
        d, f = parse_date(raw_d)
        if d is None:
            (day_first if _day_first(raw_d) else bad_dates).append(
                (ln, raw_d or "(blank)"))
        else:
            formats.add(f)
            parsed.append((ln, raw_d, d))
        a = None
        if has_asof:
            ta = r["as_of"].strip()
            a, _ = parse_date(ta)
            if a is None:
                bad_asof.append((ln, ta or "(blank)"))
            elif _swapped(ta) not in (None, a):
                asof_both.add(ln, (ta, a))
                asof_alt[a] = _swapped(ta)
            elif _month_first_only(ta):
                asof_md = True
        raw_v = r["value"].strip()
        v = None
        if vstyle is not None:
            try:
                v = _num(raw_v, vstyle)
            except ValueError:
                bad_vals.append((ln, raw_v))
            else:
                if v is None:
                    na.append((ln, raw_v or "(blank)"))
                elif v < 0:
                    neg.append((ln, raw_v))
                else:
                    grouped = bool(mark) and mark in raw_v
                    if grouped:
                        either.append((ln, raw_v))
                    if kind == "count" and (grouped or not v.is_integer()):
                        # 1.000 is no whole number as written: 1 or 1000
                        nonint.append((ln, raw_v))
        p = None
        if has_pop and pstyle is not None:
            raw_p = r["population"].strip()
            try:
                p = _num(raw_p, pstyle)
            except ValueError:
                bad_pop.append((ln, raw_p))
            else:
                if p is None:
                    miss_pop.append((ln, raw_p or "(blank)"))
                elif p <= 0:
                    bad_pop.append((ln, raw_p))
                    p = None
        key = _text(r["group"])
        name = key
        if has_lname and _text(r["location_name"]):
            name = _text(r["location_name"])
        # every row with a usable date (and as_of) joins the structural
        # checks (duplicates, gaps), whatever its value
        if d is not None and (a is not None or not has_asof):
            rows.append((ln, a, name, key, d, v, p))

    col = cols["date"]

    def cells(items, date=True):
        """'NA (2024-03-16, Pediatric)': a cell with its date and group."""
        return _cells(raw_rows, items, date)
    if bad_dates:
        lines = [ln for ln, _ in bad_dates]
        hint = ""
        if all(re.fullmatch(r"\d{5}(\.0+)?", t) for _, t in bad_dates):
            hint = (" They look like spreadsheet date numbers: format the "
                    "column as dates before saving.")
        elif any(_year_first2(t) for _, t in bad_dates):
            t = next(t for _, t in bad_dates if _year_first2(t))
            hint = (f" A date like {t} could be year-first or day-first: "
                    "write it as YYYY-MM-DD.")
        rep.add("date_parse", f"The '{col}' column contains "
                f"{len(bad_dates)} value(s) that could not be parsed as dates "
                f"({_rows(lines)}; e.g., {cells(bad_dates, date=False)})."
                " Write dates as YYYY-MM-DD, M/D/YYYY or M/D/YY." + hint, lines)
    if day_first:
        lines = [ln for ln, _ in day_first]
        rep.add("date_day_first", f"{len(day_first)} date(s) in '{col}' are "
                f"day-first ({_rows(lines)}; e.g., "
                f"{cells(day_first, date=False)}). "
                "Day-first dates are ambiguous and not accepted: write them "
                "as YYYY-MM-DD or M/D/YYYY.", lines)
    one = {d for _, _, d in parsed}
    if len(one) == 1 and not day_first and all(
            _swapped(t) not in (None, d) for _, t, d in parsed):
        # one week, written M/D with both numbers <= 12: no weekday or gap
        # tells which reading is meant, as it does over two weeks or more
        ln, t, d = parsed[0]
        lines = [x[0] for x in parsed]
        rep.add("date_ambiguous", f"The '{col}' column holds a single date, "
                f"{t} ({_rows(lines)}), which reads as {d.isoformat()} "
                f"month-first or {_swapped(t).isoformat()} day-first; with "
                "one week, nothing in the file says which. Write it as "
                "YYYY-MM-DD.", lines)
        parsed, rows = [], []
    if day_first:
        # a day-first file: its other dates were read month-first
        # (07/01/2024 as July 1), so their weekdays and weeks mean nothing
        parsed, rows = [], []
    shift = 0
    weekday = None
    wds = Counter(d.weekday() for _, _, d in parsed)
    if len(wds) == 1:
        weekday = next(iter(wds))
        shift = (5 - weekday) % 7
        side = cols.get("_date_side")
        if side == "end" and shift >= 4:
            # a week ENDING on a Sunday, Monday or Tuesday lies mostly in
            # the MMWR week before: moving it forward labels it a week late
            lines = [ln for ln, _, _ in parsed]
            ln, t, d = parsed[0]
            rep.add("weekday_end", f"The '{col}' column names the end of "
                    f"each week, but its dates are {WEEKDAYS[weekday]}s "
                    f"({_rows(lines)}; e.g., {cells([(ln, t)], date=False)})."
                    " A week ending on a "
                    f"{WEEKDAYS[weekday]} lies mostly in the MMWR week that "
                    f"ends the Saturday before ({t} -> "
                    f"{saturday_on_or_before(d).isoformat()}); moving it to "
                    "the Saturday after would label every week a week "
                    "late. Write each week's MMWR week-ending Saturday, or "
                    "name the column date if its dates start their weeks.",
                    lines)
            shift = 0
        elif side == "start" and shift <= 2:
            # a week STARTING on a Thursday, Friday or Saturday lies mostly
            # in the MMWR week after: keeping it labels it a week early
            lines = [ln for ln, _, _ in parsed]
            ln, t, d = parsed[0]
            rep.add("weekday_start", f"The '{col}' column names the start "
                    f"of each week, but its dates are {WEEKDAYS[weekday]}s "
                    f"({_rows(lines)}; e.g., {cells([(ln, t)], date=False)})."
                    " A week starting on a "
                    f"{WEEKDAYS[weekday]} lies mostly in the MMWR week that "
                    f"ends the Saturday after ({t} -> "
                    f"{(week_ending(d) + timedelta(days=7)).isoformat()}); "
                    "keeping it in the week of its first day would label "
                    "every week a week early. Write each week's MMWR "
                    "week-ending Saturday, or name the column date if its "
                    "dates end their weeks.", lines)
            shift = 0
    elif len(wds) > 1:
        top = wds.most_common(1)[0][0]
        off = [(ln, t, d) for ln, t, d in parsed if d.weekday() != top]
        what = [f"{n:,} on {WEEKDAYS[w]}" for w, n in wds.most_common()]
        what[0] = (f"{wds[top]:,} row{'s' if wds[top] != 1 else ''} on "
                   f"{WEEKDAYS[top]}")
        lines = [ln for ln, _, _ in off]
        whose = dict(zip(lines, (_text(r["group"]) for r in _rows_of(
            raw_rows, lines[:MAX_EXAMPLES]))))
        ex = _examples(f"{t} ({whose.get(ln)}, {WEEKDAYS[d.weekday()]}, "
                       f"row {ln})" for ln, t, d in off)
        hint = ""
        swapped = [_swapped(t) for _, t, _ in parsed]
        if all(swapped) and len({s.weekday() for s in swapped}) == 1:
            hint = (" Read day-first they would all be "
                    f"{WEEKDAYS[swapped[0].weekday()]}s, but day-first dates "
                    "are not accepted: write them as YYYY-MM-DD.")
        rep.add("weekday", f"The dates fall on {len(wds)} different weekdays: "
                f"{', '.join(what)} ({_rows(lines)}; e.g., {ex}). Every "
                "date must be the same day of its week."
                + hint, lines)
    if shift:
        rep.warnings.insert(0, f"Dates moved to week-ending Saturdays: "
                            f"+{shift} day{'s' if shift != 1 else ''} "
                            f"(each {WEEKDAYS[weekday]} to the Saturday that "
                            "ends its week).")
        rows = [(ln, a, n, k, d + timedelta(days=shift), v, p)
                for ln, a, n, k, d, v, p in rows]
    if bad_asof:
        lines = [ln for ln, _ in bad_asof]
        dmy = next((t for _, t in bad_asof if _day_first(t)), None)
        rep.add("as_of_parse", f"The '{cols['as_of']}' column contains "
                f"{len(bad_asof)} value(s) that could not be parsed as dates "
                f"({_rows(lines)}; e.g., {cells(bad_asof)})."
                + (f" A date like {dmy} is day-first, which is not "
                   "accepted: write it as YYYY-MM-DD or M/D/YYYY."
                   if dmy else ""), lines)
    # the date column proves month-first only by a date whose second
    # number is a day over 12 (1/13/2024): 02/02/2024 or 03/04/2024 read
    # either way, whatever the weekdays say
    dates_md = next((t for _, t, _ in parsed if _month_first_only(t)), None)
    if asof_both.n and rows and not asof_md:
        # every M/D as_of reads both ways and none says which. A snapshot's
        # as_of follows its newest week by days, so the snapshots decide:
        # month-first stands when day-first would put a week after its
        # as_of, or fits them less closely (or as closely, when the dates
        # prove month-first); else the file is refused (a silent pick moves
        # the snapshots by months). The fit: each snapshot's days from its
        # newest week to its as_of, the longest first
        def lags(reading):
            newest = {}
            for _, a, _, _, d, _, _ in rows:
                k = reading(a)
                newest[k] = max(newest.get(k, d), d)
            return sorted(((k - d).days for k, d in newest.items()),
                          reverse=True)
        mf, df = lags(lambda a: a), lags(lambda a: asof_alt.get(a, a))
        why = ""
        if min(df) < 0:
            pass                    # day-first puts a week after its as_of
        elif min(mf) < 0:
            why = ("read month-first, a snapshot would hold weeks after its "
                   "as_of, while read day-first each as_of follows its "
                   "newest week")
        elif df < mf:
            why = ("day-first fits the snapshots better (each as_of just "
                   "after its newest week)")
        elif df == mf and not dates_md:
            why = ("both readings fit the snapshots, and no as_of or date "
                   "is written with a day over 12 to say which")
        if why:
            ln, (t, a) = asof_both.eg[0]
            (r0,) = _rows_of(raw_rows, [ln])
            proven = (f" The '{col}' dates are month-first (e.g., "
                      f"{dates_md}), but the as_of dates must say so "
                      "themselves." if dates_md else "")
            rep.add("as_of_ambiguous", f"The '{cols['as_of']}' column's "
                    "dates read both month-first and day-first "
                    f"({_rows(asof_both.lines, asof_both.n)}; e.g., {t} is "
                    f"{a.isoformat()} or {_swapped(t).isoformat()}, row "
                    f"{ln}: {r0['date'].strip()}, {_text(r0['group'])}), and "
                    f"{why}.{proven} Write as_of dates as YYYY-MM-DD.",
                    asof_both.lines)
    if bad_vals:
        lines = [ln for ln, _ in bad_vals]
        rep.add("value_numeric", f"The '{vcol}' column must contain numbers "
                f"only: {len(bad_vals)} value(s) are not ({_rows(lines)}; "
                f"e.g., {cells(bad_vals)}).",
                lines)
    if neg:
        lines = [ln for ln, _ in neg]
        rep.add("value_negative", f"The '{vcol}' column contains {len(neg)} "
                f"negative value(s) ({_rows(lines)}; e.g., {cells(neg)}). "
                "Values "
                "must be zero or positive.", lines)
    if na and fmt == "grouped":
        # a grouped CSV lists only reported weeks: NA is an error
        lines = [ln for ln, _ in na]
        rep.add("value_na", f"The '{vcol}' column is blank or NA on "
                f"{len(na)} row(s) ({_rows(lines)}; e.g., {cells(na)}). All "
                "rows must have a value; delete rows for weeks not reported.",
                lines)
    elif na:
        # hubverse time series carry NA for unreported weeks (FluSight's
        # own file has thousands): dropped after the structural checks,
        # counted, never imputed (rule 10)
        rep.warnings.append(f"{len(na)} row(s) with no value were dropped.")
    sep_name = {".": "dot", ",": "comma"}.get(mark, "")
    if either and kind is None:
        # 1.234 is 1.234 or 1234: never guessed, the kind is asked for
        lines = [ln for ln, _ in either]
        t = either[0][1]
        rep.add("kind_ambiguous", f"The '{vcol}' column's numbers could be "
                f"decimals or have a {sep_name} separating thousands "
                f"({_rows(lines)}; e.g., {cells(either)}): {t} is "
                f"{t.replace(',', '.')} as a rate or {t.replace(mark, '')} "
                "as a count. Choose whether the values are counts or rates; "
                f"counts are written without thousands separators "
                f"({t.replace(mark, '')}).", lines)
    elif either and kind == "rate":
        t = either[0][1]
        rep.warnings.append(
            f"Read numbers like {t} in the '{vcol}' column as decimals"
            + (f" ({t} = {t.replace(',', '.')})" if mark == "," else "")
            + f", as the values are rates; if the {sep_name}s separate "
            f"thousands ({t} = {t.replace(mark, '')}), write the numbers "
            "without them."
            + (" Dots were read as thousands separators (1.234 = 1234)."
               if mark == "," and any("." in x for x in vtexts) else ""))
    if nonint:
        lines = [ln for ln, _ in nonint]
        grouped = [t for _, t in nonint if mark and mark in t]
        hint = ("Choose rates instead." if not grouped else
                f"If the {sep_name}s separate thousands, write the numbers "
                f"without them ({grouped[0]} as "
                f"{grouped[0].replace(mark, '')}); if they are decimals, "
                "choose rates instead.")
        rep.add("value_not_integer", f"The values were declared counts but "
                f"{len(nonint)} {'is' if len(nonint) == 1 else 'are'} not "
                + ("written as " if grouped else "")
                + f"whole numbers ({_rows(lines)}; e.g., {cells(nonint)}). "
                + hint, lines)
    if bad_pop:
        lines = [ln for ln, _ in bad_pop]
        rep.add("population_invalid", f"The '{cols['population']}' column "
                f"has {len(bad_pop)} value(s) that are not positive numbers "
                f"({_rows(lines)}; e.g., {cells(bad_pop)}).", lines)
    if miss_pop:
        lines = [ln for ln, _ in miss_pop]
        rep.add("population_missing", f"The '{cols['population']}' column "
                f"is blank or NA on {len(miss_pop)} row(s) ({_rows(lines)}; "
                f"e.g., {cells(miss_pop)}). Give every row a population, or "
                "remove the column.", lines)
    if len(formats) > 1:
        rep.warnings.append(f"Dates mix formats ({', '.join(sorted(formats))}); "
                            "each was read by its own pattern.")

    national = _check_groups(rep, raw_rows, cols)
    _check_structure(rep, rows, cols, shift=shift, raw_rows=raw_rows)

    recs = [(a, n, k, d, v, p) for _, a, n, k, d, v, p in rows]
    want = {r[0] for r in rows[:5]}
    written = {ln: r["date"].strip() for ln, r in raw_rows if ln in want}
    first_rows = [{"row": ln, "date": written.get(ln, ""),
                   "week": d.isoformat(), "group": n,
                   "value": (_fmt_num(v) if v is not None else ""),
                   "population": (_fmt_num(p) if p is not None else "")}
                  for ln, a, n, k, d, v, p in rows[:5]]
    n_na = 0
    if na and fmt != "grouped":
        kept = [r for r in recs if r[4] is not None]
        n_na = len(recs) - len(kept)
        recs = kept
        if not recs and rep.ok:
            rep.add("empty", "Every row's value is missing; nothing is "
                    "left to store.")
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
            # None: the values do not say (numbers like 1.234, see mark)
            "inferred_kind": (None if either else
                              "count" if integral else "rate"),
            "target": tgt_used,
            "has_population": has_pop and not (bad_pop or miss_pop),
            "has_as_of": has_asof,
            "as_of": [a.isoformat() for a in asofs],
            "week_start_sunday": shift == 6,
            "date_shift_days": shift,
            "weekday": WEEKDAYS[weekday] if weekday is not None else None,
            "encoding": ENCODING_NAMES.get(rep.encoding, rep.encoding),
            "delimiter": DELIMITERS.get(delim, delim),
            "na_dropped": n_na,
            "national_group": (national if national in names else None),
            "first_rows": first_rows,
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


def _rows_of(raw_rows, lines) -> list:
    """The raw rows at these row numbers, in the order given."""
    want = set(lines)
    got = {ln: r for ln, r in raw_rows if ln in want}
    return [got[ln] for ln in lines]


def _place(r, date: bool = True) -> str:
    """Where a raw row is: '2024-03-16, Pediatric' (its group alone when
    ``date`` is False, the cell quoted being the date itself)."""
    g = _text(r["group"]) or "no group"
    return f"{r['date'].strip() or 'no date'}, {g}" if date else g


def _cells(raw_rows, items, date: bool = True) -> str:
    """Examples of cells with their date and group, 'NA (2024-03-16,
    Pediatric)', from (row number, cell) pairs; a date cell with its group
    alone ('soon (Pediatric)', ``date`` False)."""
    items = list(items)[:MAX_EXAMPLES]
    return _examples(f"{t} ({_place(r, date)})" for (_, t), r in zip(
        items, _rows_of(raw_rows, [ln for ln, _ in items])))


def _name_char(c: str) -> bool:
    """A character a group name may hold after its first: a letter or
    digit of any script, a combining mark, a space or an underscore."""
    return (c.isalnum() or c in " _"
            or unicodedata.category(c) in NAME_MARKS)


def group_name_ok(name: str) -> bool:
    """GROUP_RE, with combining marks allowed after the first character:
    a letter or digit first, then letters, digits, marks, spaces and
    underscores, at most 40 characters."""
    return (0 < len(name) <= 40 and bool(GROUP_RE.fullmatch(name[0]))
            and all(_name_char(c) for c in name[1:]))


def is_national_name(name) -> bool:
    return str(name or "").strip().upper() in NATIONAL_NAMES


def _check_groups(rep: Report, raw_rows: list, cols: dict):
    """Names: charset, reserved spellings, collisions after the PF stem
    and case folding, one name per location (hubverse), and at most one
    national group. Returns the national group's name, or None."""
    has_lname = "location_name" in cols
    key2names, name2keys, first = {}, {}, {}
    for ln, r in raw_rows:
        key = _text(r["group"])
        name = (_text(r["location_name"])
                if has_lname and _text(r["location_name"]) else key)
        key2names.setdefault(key, set()).add(name)
        name2keys.setdefault(name, set()).add(key)
        first.setdefault(name, ln)
        first.setdefault(("key", key), ln)
    what = "location name" if cols["format"] == "hubverse" else "group"
    blank = [ln for ln, r in raw_rows if not _text(r["group"])]
    if blank:
        r = _rows_of(raw_rows, blank[:1])[0]
        rep.add("group_blank", f"The '{cols['group']}' column is blank on "
                f"{len(blank)} row(s) ({_rows(blank)}; e.g., row {blank[0]}: "
                f"{_vis(r['date'].strip())}, value "
                f"{_vis(r['value'].strip() or '(blank)')}"
                f"). Give every row its {'location' if has_lname else what}"
                ", or delete those rows.", blank)
    # a national spelling is accepted as is ('US (national)' included)
    bad = [n for n in name2keys
           if n and not group_name_ok(n) and not is_national_name(n)]
    if bad:
        sugg = [f"'{n}' -> '{_suggest(n)}'" for n in bad]
        rep.add("group_name", f"{len(bad)} {what} value(s) use characters "
                "other than letters (with their accents and vowel signs), "
                "digits, space and underscore, start with a space, an "
                "underscore or a sign, or exceed 40 characters ("
                f"{_rows(first[n] for n in bad)}; e.g., {_examples(sugg)}).",
                [first[n] for n in bad])
    reserved = [n for n in name2keys if n.upper() in RESERVED_NAMES]
    if reserved:
        rep.add("group_reserved", f"Group name(s) {_examples(reserved)} are "
                "reserved (the console reads 'all' as every location; "
                f"{_rows(first[n] for n in reserved)}). Rename it National "
                "if it is the total of the other groups (then it is kept "
                "out of their pooled scores), else, e.g., 'All ages'.",
                [first[n] for n in reserved])
    national = sorted({n for n, keys in name2keys.items()
                       if is_national_name(n)
                       or any(is_national_name(k) for k in keys)})
    if len(national) > 1:
        rep.add("national_multiple", f"{len(national)} groups are spelled as "
                f"a national row ({', '.join(repr(n) for n in national)}; "
                f"{_rows(first[n] for n in national)}); a dataset may hold "
                f"one national group (e.g., keep {national[0]!r}).",
                [first[n] for n in national])
    folded = {}
    for n in name2keys:
        folded.setdefault(_norm_name(n), []).append(n)
    clash = [sorted(v) for v in folded.values() if len(v) > 1]
    if clash:
        lines = [first[n] for c in clash for n in c]
        rep.add("group_collision", f"{len(clash)} set(s) of group names "
                "differ only by case, spaces, underscores or punctuation, "
                "and would collide in folder names "
                f"({_rows(lines)}; e.g., "
                f"{_examples(' / '.join(repr(x) for x in c) for c in clash)}).",
                lines)
    multi = [(f"{k}: {', '.join(sorted(v))}", first[("key", k)])
             for k, v in key2names.items() if len(v) > 1]
    multi += [(f"{n}: {', '.join(sorted(v))}", first[n])
              for n, v in name2keys.items() if len(v) > 1 and has_lname]
    if multi:
        lines = [ln for _, ln in multi]
        rep.add("location_name_conflict", "Each location must have exactly "
                f"one location_name and vice versa ({_rows(lines)}; e.g., "
                f"{_examples(t for t, _ in multi)}).", lines)
    return national[0] if len(national) == 1 else None


def _suggest(name: str) -> str:
    bare = "".join(c for c in name if _name_char(c)).strip()
    if is_national_name(bare):                 # 'U.S.' -> 'US', not 'U_S'
        return bare
    # each run of other characters becomes one underscore; marks are kept
    s = "".join(c if _name_char(c) else "\0" for c in name)
    s = re.sub("\0+", "_", s).strip(" _")
    while s and not GROUP_RE.fullmatch(s[0]):   # a mark cannot lead
        s = s[1:].lstrip(" _")
    return s[:40] or "group1"


def _check_structure(rep: Report, rows: list, cols: dict, *, shift: int = 0,
                     raw_rows=()) -> None:
    """Duplicates, gaps (per snapshot and group), and snapshot weeks after
    their as_of; ``rows`` are (row number, as_of, name, key, date, value,
    population), their dates moved ``shift`` days to Saturdays. Messages
    name weeks as the file writes them (and their Saturday when moved) and
    the weeks a gap leaves out."""
    seen, dups = {}, []
    series = {}
    late = []
    for ln, a, name, _, d, _, _ in rows:
        k = (a, name, d)
        if k in seen:
            dups.append((seen[k], ln, a, name, d))
        else:
            seen[k] = ln
        series.setdefault((a, name), {})[d] = ln
        if a is not None and d > a:
            late.append((ln, a, name, d))
    gaps = []
    for (a, name), ds in sorted(series.items(),
                                key=lambda kv: (kv[0][0] or date.min,
                                                kv[0][1])):
        days = sorted(ds)
        for p, q in zip(days, days[1:]):
            if (q - p).days > MAX_GAP_DAYS:
                gaps.append((ds[p], ds[q], a, name, p, q))
    if not (dups or gaps or late):
        return
    # the dates (and a duplicate's two values) as written, for the rows
    # the messages quote
    want = ({x[i] for x in dups[:MAX_EXAMPLES] for i in (0, 1)}
            | {x[0] for x in late[:MAX_EXAMPLES]}
            | {x[i] for x in gaps[:MAX_EXAMPLES] for i in (0, 1)})
    written = {ln: r["date"].strip() for ln, r in raw_rows if ln in want}
    value = {ln: _vis(r["value"].strip() or "(blank)") for ln, r in raw_rows
             if ln in want}

    def week(d, ln=None):
        """A week as the file writes it, with its Saturday when moved."""
        if not shift:
            return d.isoformat()
        return (f"{written.get(ln) or (d - timedelta(days=shift)).isoformat()}"
                f" (week ending {d.isoformat()})")

    def snap(a):
        return f", as_of {a.isoformat()}" if a else ""
    if dups:
        lines = [ln for x in dups for ln in x[:2]]
        unit = ("as_of/date/group" if "as_of" in cols else "date/group")
        rep.add("duplicate", f"Duplicate rows found for {len(dups)} {unit} "
                f"combination(s) ({_rows(lines)}; e.g., "
                + _examples(f"{week(d, l0)} + {name} ("
                            + (f"as_of {a.isoformat()}; " if a else "")
                            + f"values {value.get(l0, '?')} and "
                            f"{value.get(l1, '?')})"
                            for l0, l1, a, name, d in dups)
                + "). Each combination must appear exactly once.", lines)
    if gaps:
        lines = [ln for x in gaps for ln in x[:2]]
        eg = []
        for l0, l1, a, name, p, q in gaps[:MAX_EXAMPLES]:
            miss = []
            m = p + timedelta(days=7)
            while (q - m).days >= 4:
                miss.append(m)
                m += timedelta(days=7)
            where = (f"between {week(p, l0)} and {week(q, l1)} in group "
                     f"'{name}'{snap(a)}")
            if not miss:
                eg.append(f"a gap {where}")
            elif len(miss) == 1:
                eg.append(f"{week(miss[0])} is missing {where}")
            else:
                eg.append(f"{week(miss[0])} to {week(miss[-1])} "
                          f"({len(miss)} weeks) are missing {where}")
        rep.add("gap", f"Missing weeks detected in {len(gaps)} place(s) "
                f"({_rows(lines)}; e.g., {'; '.join(eg)}). The data should "
                "have one row per week per group.", lines)
    if late:
        lines = [x[0] for x in late]
        rep.add("as_of_before_date", f"{len(late)} row(s) hold a week after "
                f"their snapshot's as_of ({_rows(lines)}; e.g., "
                + _examples(f"{week(d, ln)} in as_of {a.isoformat()} ({name})"
                            for ln, a, name, d in late)
                + ")."
                # on or before the as_of as written, after it once moved
                + (" Each date was moved to the Saturday that ends its "
                   "week, which falls after the as_of: a snapshot holds "
                   "only weeks that ended by its as_of."
                   if shift and all(d - timedelta(days=shift) <= a
                                    for _, a, _, d in late) else ""), lines)


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


def ingest(source, name: str, *, kind: Optional[str] = None,
           week_start_sunday: bool = False, target: Optional[str] = None,
           limits: Limits = DEFAULT_LIMITS, filename: str = "",
           columns: Optional[dict] = None) -> "Dataset":
    """Validate and store one upload; returns the stored Dataset.

    ``kind`` None or '' takes the kind the values show (whole numbers are
    counts); ``columns`` is validate's column mapping; ``week_start_sunday``
    is accepted and ignored (see validate). Raises DatasetError (with
    ``.problems``) and writes nothing when any problem is found.
    Re-ingesting identical bytes with identical options under the same name
    returns the existing dataset (idempotent). The folder is built beside
    the store and renamed into place, so a reader never sees a half-written
    dataset."""
    kind = kind or None
    if kind is not None and kind not in KINDS:
        raise DatasetError(f"Declare the value kind: one of {', '.join(KINDS)}.",
                           [Problem("kind_invalid", f"Value kind {kind!r} is "
                                    f"not one of {', '.join(KINDS)}.")])
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / f".tmp-{uuid.uuid4().hex}"
    tmp.mkdir()
    try:
        with open(tmp / SOURCE_FILE, "wb") as tee:
            rep = validate(source, kind=kind, target=target, limits=limits,
                           columns=columns, _tee=tee)
        if not rep.ok:
            raise DatasetError(
                f"{len(rep.problems)} problem(s) in the upload; nothing was "
                "stored.", rep.problems, rep)
        declared = kind is not None
        kind = kind or rep.summary["inferred_kind"]
        sunday = bool(rep.summary.get("week_start_sunday"))
        digest = identity_digest(rep.sha256, kind=kind,
                                 week_start_sunday=sunday,
                                 target=rep.summary.get("target"),
                                 columns=rep.columns)
        dataset_id = f"{slug(name)}-{digest[:12]}"
        final = _dir(dataset_id)
        if (final / META_FILE).is_file():
            return get(dataset_id)
        _materialize(tmp, rep, name=name, dataset_id=dataset_id,
                     digest=digest, kind=kind, declared=declared,
                     filename=filename)
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
                 declared, filename) -> None:
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
    def national_group(self) -> Optional[str]:
        """The group read as the dataset's national row, or None."""
        return self.meta.get("national_group") or None

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
        """The retrospective reference dates: every distinct week except
        the first (a forecast needs one observed week), from the final
        data."""
        return self.weeks()[1:]

    # ---- the engines' view (later stages): one path per as-of -------------

    @property
    def vintage_true(self) -> bool:
        """True when the upload carried as_of snapshots: a forecast at a
        key sees the data as it stood then. Otherwise every as-of reads
        the final series truncated at the as-of (final data, not
        vintage-true)."""
        return self.has_as_of

    def _final_rows(self) -> list:
        """The final snapshot's rows, read once per Dataset object."""
        rows = self.__dict__.get("_final_cache")
        if rows is None:
            with open(self.final_path, newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.__dict__["_final_cache"] = rows
        return rows

    def weeks(self) -> list:
        """Every distinct week (Saturday, ISO) in the final data, ascending."""
        return sorted({r["date"] for r in self._final_rows()})

    def forecast_dates(self) -> list:
        """The as-of weeks a forecast may anchor on: every vintage key when
        versioned; otherwise every week but the first (the reference
        dates: a forecast needs one observed week)."""
        return self.vintages() if self.vintage_true else self.reference_dates()

    def truth_path(self, as_of: str) -> Path:
        """The archive-shaped CSV an engine reads for one as-of. Versioned:
        that key's snapshot (exact, rule 5). Unversioned: the final data,
        which every engine truncates at the as-of; a week the data does
        not hold is refused loudly, naming nearby weeks."""
        as_of = str(as_of)
        if self.vintage_true:
            return self.vintage_path(as_of)
        weeks = self.weeks()
        if as_of not in weeks:
            try:
                t = date_fromiso(as_of)
                near = [w for w in weeks
                        if abs((date_fromiso(w) - t).days) <= 45]
            except (TypeError, ValueError):
                near = []
            raise FileNotFoundError(
                f"No week {as_of} in dataset {self.name!r}. "
                f"Nearby: {near or weeks[-3:]}")
        return self.final_path

    def series(self, name: str, as_of: Optional[str] = None) -> dict:
        """{"dates": [...], "values": [...]} for one group as it stood at
        `as_of` (the newest vintage when None), truncated at the as-of so
        final data never leaks later weeks into a view; the shape of
        data.vintage_series."""
        if as_of is None:
            rows = self._final_rows()
        else:
            with open(self.truth_path(as_of), newline="",
                      encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        out = sorted((r["date"], float(r["value"])) for r in rows
                     if r["location_name"] == name and r["value"] != ""
                     and (as_of is None or r["date"] <= str(as_of)))
        return {"dates": [d for d, _ in out], "values": [v for _, v in out]}

    def truth(self) -> dict:
        """{(group name, ISO date): value} from the final data: what a
        dataset forecast is scored against."""
        return {(r["location_name"], r["date"]): float(r["value"])
                for r in self._final_rows() if r["value"] != ""}

    def population_series(self, name: str) -> list:
        """[(date, population)] for one group from the final snapshot,
        oldest first (population may vary by date); [] without one."""
        final_as_of = self.meta["as_of_used"][self.meta["vintages"][-1]] or ""
        out = []
        with open(self.series_path, newline="", encoding="utf-8") as fh:
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
    meta = json.loads(mp.read_text(encoding="utf-8"))
    return Dataset(d, meta)


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


def from_spec(spec) -> Optional[Dataset]:
    """The dataset a run spec (RunSpec, or its dict) names in
    ``extra["dataset"]``, else None WITHOUT touching the store: the hub
    path's call is a dictionary lookup and nothing more. A named dataset
    that is gone or changed raises (never a silent substitute)."""
    extra = (spec.get("extra") if isinstance(spec, dict)
             else getattr(spec, "extra", None))
    ref = extra.get("dataset") if isinstance(extra, dict) else None
    if not ref:
        return None
    return resolve(ref)


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
    kind = s["kind"] or f"{s['inferred_kind']} (inferred from the values)"
    lines = [
        f"format      {s['format']} ({s['delimiter']}-separated, "
        f"{s['encoding']})",
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
    if s.get("national_group"):
        lines.append(f"national    {s['national_group']} (reported beside "
                     "the pooled scores, never inside)")
    return lines


def problem_lines(rep: Report) -> list:
    """Every problem, grouped by kind, as indented text lines (the CLI's
    output); a column mapping's choices when that is all that is wrong."""
    out = []
    for kind, probs in problem_groups(rep.problems):
        out.append(f"{kind}:")
        out += [f"  - {p}" for p in probs]
    if "kind_ambiguous" in rep.codes:
        out.append("Say which with --kind count or --kind rate.")
    if rep.needs_mapping:
        out.append("Columns in the file: " + ", ".join(
            f"#{i + 1} {h}" for i, h in enumerate(rep.headers) if h))
        unset = [r for r in REQUIRED if r not in rep.guess] or ["date"]
        used = set(rep.guess.values())
        free = [h for i, h in enumerate(rep.headers)
                if h and f"#{i + 1}" not in used]
        out.append("Name them with --column ROLE=HEADER (ROLE: "
                   + ", ".join(ROLES) + f"), e.g. --column {unset[0]}="
                   + (free[0] if free else "#1") + ".")
    return out
