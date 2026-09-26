"""validate(): one reading pass over an upload (_read: the header, the
column mapping, every row's cells) before checks.py judges the rows."""
from __future__ import annotations

import csv
import io
import itertools
import re
from collections import Counter
from typing import Optional

from .checks import _check_rows
from .parsing import (
    _CUT_HEAD,
    _CUT_TAIL,
    _ESCAPED,
    _PLAIN,
    _UTF8_CHAR,
    DELIMITERS,
    ENCODING_NAMES,
    EXTRA_ALIASES,
    PRECEDENCE,
    REQUIRED,
    ROLE_ALIASES,
    ROLES,
    _CappedReader,
    _day_first,
    _LimitExceeded,
    _norm_header,
    _open_source,
    _Replayable,
    _week_side,
    detect_encoding,
    parse_date,
    sniff_delimiter,
)
from .report import (
    DEFAULT_LIMITS,
    MAX_EXAMPLES,
    Limits,
    Report,
    _examples,
    _rows,
    _Tally,
    _vis,
)

#: lines read to sniff the separator
SNIFF_LINES = 50


def _blank_row(row) -> bool:
    """A row with nothing in it: empty cells, or only separators of another
    kind (',,,' in a semicolon file) and a DOS end-of-file mark (Ctrl-Z)."""
    return all(not c.replace("\x1a", "").strip().strip(",;\t").strip()
               for c in row)
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
        pick = ends[0] if role == "date" and len(ends) == 1 else cands[0]
        rep.suggest[role] = (header[pick] if times[header[pick]] == 1
                             else f"#{pick + 1}")
        eg = label[pick] + (", the end of each week" if pick in ends
                            and role == "date" else "")
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
