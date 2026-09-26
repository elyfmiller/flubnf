"""RESEARCH (staged): user-supplied target datasets (custom CSV target data).

A dataset is one uploaded CSV of weekly target data in either shape:

  * grouped CSV: ``date, target_group, value[, population]``.
  * hubverse time series: ``target_end_date | date, location,
    observation | value[, target][, as_of][, location_name][, population]``.

or a folder of such files, one snapshot per as_of (``validate_snapshots``,
``ingest_snapshots``): each file is read as one upload is, and takes its
as_of from an as_of column inside it or from the one date its name
carries (2024-10-05.csv, admissions_2024-10-05.csv, the hub archive's
target-hospital-admissions_2024-10-05.csv). The files are stored as ONE
vintage-true dataset, exactly as one CSV holding the same rows with an
as_of column would be; they must share their groups and population
column, and give one file per as_of Saturday.

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
    separators); undeclared, the kind is asked for, never inferred. A
    population is a whole number of people: 123.456, 1.000 or 8.5 is
    refused (with dots that may separate thousands, 123456). A
    value or name that an unquoted separator split (1,234 or Bern, Stadt
    without quotes) is refused, whether its second half lands past the
    header or in an ignored column.
  * headers: case, space and underscore do not matter, and obvious aliases
    are read (``ROLE_ALIASES``). A required column that cannot be matched,
    or two columns that could both be it, asks for a column mapping
    (``columns=``) instead of guessing. Other columns are ignored and named
    in a notice; trailing empty columns and rows are dropped.
  * dates: YYYY-MM-DD, YYYY/MM/DD, M/D/YYYY, M/D/YY and MM-DD-YYYY, with or
    without a time ("2024-01-06 00:00:00"). Every date of a file must fall
    on one weekday; it is moved to the MMWR week-ending Saturday of its
    Sunday-to-Saturday week, with a notice. Mixed weekdays and day-first
    dates are refused, and so are dates written M/D that read both ways
    when either reading puts them on one weekday with no week missing (a
    single week, or one week per group), an as_of written M/D that reads
    both ways unless the file proves month-first by an as_of or a date
    with a day over 12 (1/13/2024; 05/05/2024 proves neither order) and
    each such snapshot's newest week then ends 0 to MAX_ASOF_LAG days
    before it (read month-first on the dates' word alone, with a notice;
    which reading fits the snapshots more closely proves nothing), a
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

Public API: ``validate``, ``ingest``, ``validate_snapshots``,
``ingest_snapshots``, ``list_datasets``, ``get``, ``delete``,
``Dataset`` (``vintages``/``vintage_path`` mirror app/core/data.py),
``Report``/``Problem``, ``problem_groups``, ``Limits``, ``DatasetError``,
``KINDS``, ``ROLE_ALIASES``, ``ROOT``.
"""
# The package, by topic (each module's names are re-exported here, so
# ``from app.core import datasets as D`` reads as before and tests can
# monkeypatch D.ROOT, D.get, D.MAX_SNAPSHOT_FILES on this module):
#   report.py     Problem, Report, Limits, DatasetError; message helpers;
#                 summary_lines / problem_lines (the CLI's text)
#   parsing.py    byte streams, encodings, separators, dates, numbers,
#                 headers, group-name forms (pf_stem, slug)
#   reading.py    validate() and the reading pass (_read, _map_columns)
#   checks.py     the row, group and structure checks
#   store.py      ROOT, ids, ingest() and _materialize()
#   snapshots.py  validate_snapshots / ingest_snapshots (one file per as_of)
#   dataset.py    Dataset, get, resolve, from_spec, list_datasets, delete
from __future__ import annotations

from .checks import (
                     GROUP_RE,
                     KINDS,
                     MAX_ASOF_LAG,
                     MAX_GAP_DAYS,
                     NAME_MARKS,
                     NATIONAL_NAMES,
                     RESERVED_NAMES,
                     WEEKDAYS,
                     group_name_ok,
                     is_national_name,
)
from .dataset import (
                     Dataset,
                     date_fromiso,
                     delete,
                     from_spec,
                     get,
                     list_datasets,
                     resolve,
)
from .parsing import (
                     DELIMITERS,
                     ENCODING_NAMES,
                     END_HEADERS,
                     EXTRA_ALIASES,
                     NA_TOKENS,
                     PRECEDENCE,
                     REQUIRED,
                     ROLE_ALIASES,
                     ROLES,
                     detect_encoding,
                     grouping_or_decimal,
                     number_style,
                     parse_date,
                     pf_stem,
                     saturday_on_or_before,
                     slug,
                     sniff_delimiter,
                     week_ending,
)
from .reading import SNIFF_LINES, validate
from .report import (
                     DEFAULT_LIMITS,
                     KIND_OF,
                     MAX_EXAMPLES,
                     MAX_ROWS_KEPT,
                     MAX_ROWS_SHOWN,
                     PROBLEM_KINDS,
                     DatasetError,
                     Limits,
                     Problem,
                     Report,
                     problem_groups,
                     problem_lines,
                     summary_lines,
)
from .snapshots import (
                     MAX_SNAPSHOT_FILES,
                     SOURCES_DIR,
                     default_snapshot_name,
                     ingest_snapshots,
                     name_dates,
                     validate_snapshots,
)
from .store import (
                     ID_RE,
                     LOCATIONS_FILE,
                     META_FILE,
                     ROOT,
                     SCHEMA,
                     SERIES_FILE,
                     SOURCE_FILE,
                     VINTAGE_DIR,
                     VINTAGE_PREFIX,
                     default_name,
                     identity_digest,
                     ingest,
                     valid_id,
)

__all__ = [
                     "DEFAULT_LIMITS",
                     "DELIMITERS",
                     "ENCODING_NAMES",
                     "END_HEADERS",
                     "EXTRA_ALIASES",
                     "GROUP_RE",
                     "ID_RE",
                     "KINDS",
                     "KIND_OF",
                     "LOCATIONS_FILE",
                     "MAX_ASOF_LAG",
                     "MAX_EXAMPLES",
                     "MAX_GAP_DAYS",
                     "MAX_ROWS_KEPT",
                     "MAX_ROWS_SHOWN",
                     "MAX_SNAPSHOT_FILES",
                     "META_FILE",
                     "NAME_MARKS",
                     "NATIONAL_NAMES",
                     "NA_TOKENS",
                     "PRECEDENCE",
                     "PROBLEM_KINDS",
                     "REQUIRED",
                     "RESERVED_NAMES",
                     "ROLES",
                     "ROLE_ALIASES",
                     "ROOT",
                     "SCHEMA",
                     "SERIES_FILE",
                     "SNIFF_LINES",
                     "SOURCES_DIR",
                     "SOURCE_FILE",
                     "VINTAGE_DIR",
                     "VINTAGE_PREFIX",
                     "WEEKDAYS",
                     "Dataset",
                     "DatasetError",
                     "Limits",
                     "Problem",
                     "Report",
                     "date_fromiso",
                     "default_name",
                     "default_snapshot_name",
                     "delete",
                     "detect_encoding",
                     "from_spec",
                     "get",
                     "group_name_ok",
                     "grouping_or_decimal",
                     "identity_digest",
                     "ingest",
                     "ingest_snapshots",
                     "is_national_name",
                     "list_datasets",
                     "name_dates",
                     "number_style",
                     "parse_date",
                     "pf_stem",
                     "problem_groups",
                     "problem_lines",
                     "resolve",
                     "saturday_on_or_before",
                     "slug",
                     "sniff_delimiter",
                     "summary_lines",
                     "valid_id",
                     "validate",
                     "validate_snapshots",
                     "week_ending",
]
