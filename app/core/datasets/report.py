"""Problems, the Report validate() fills, and the message helpers every
check uses (row lists, examples, bounded tallies); summary_lines and
problem_lines render a Report as the CLI prints it."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .parsing import REQUIRED, ROLES

MAX_EXAMPLES = 3
#: row numbers a problem message lists before "and N more"
MAX_ROWS_SHOWN = 6
#: row numbers a Problem keeps for callers
MAX_ROWS_KEPT = 200


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
    # several snapshot files read as one dataset (validate_snapshots)
    ("Snapshots", ("limit_files", "snapshot_undated", "snapshot_two_dates",
                   "snapshot_as_of_twice", "snapshot_as_of_name",
                   "snapshot_columns", "snapshot_groups", "snapshot_more")),
    ("Columns", ("missing_columns", "ambiguous_columns", "column_unknown",
                 "duplicate_columns", "ragged", "extra_fields", "split")),
    ("Dates", ("date_parse", "date_day_first", "date_ambiguous", "weekday",
               "weekday_end", "weekday_start", "as_of_parse",
               "as_of_ambiguous", "as_of_before_date")),
    ("Values", ("value_numeric", "value_format", "kind_ambiguous",
                "value_negative", "value_na", "value_not_integer")),
    ("Population", ("population_invalid", "population_missing",
                    "population_format", "population_not_integer")),
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
    # role -> header: the column an ambiguous role's problem suggests
    suggest: dict = field(default_factory=dict)
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
#: control characters, shown in messages as their Unicode pictures (a NUL
#: as U+2400) instead of invisibly
_CTRL = re.compile("[\x00-\x08\x0a-\x1f]")


def _vis(text) -> str:
    return _CTRL.sub(lambda m: chr(0x2400 + ord(m.group())), str(text))
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
    if s.get("snapshot_files"):
        lines.append(f"files       {len(s['snapshot_files'])} snapshot "
                     "files, one per as_of")
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
        # the column an ambiguity's problem suggests, else the first free
        eg = rep.suggest.get(unset[0]) or (free[0] if free else "#1")
        out.append("Name them with --column ROLE=HEADER (ROLE: "
                   + ", ".join(ROLES) + f"), e.g. --column {unset[0]}="
                   + (f'"{eg}"' if re.search(r"[\s\"']", eg) else eg)
                   + ".")
    return out
