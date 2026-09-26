"""Reading the raw file: capped, replayable byte streams, encoding and
separator sniffing, dates, numbers (thousands and decimal marks), header
normalization and the group-name forms (pf_stem, slug)."""
from __future__ import annotations

import codecs
import csv
import hashlib
import io
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

#: tokens read as a missing value (R readr's NA set, plus common ones)
NA_TOKENS = {"", "na", "n/a", "nan", "null", "none", "-"}
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


# --------------------------------------------------------------- streaming

class _LimitExceeded(Exception):
    """Raised by _CappedReader past a Limits bound ('bytes', 'rows' or
    'groups' as its message)."""


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
            t = dec_comma[0]
            what = ("a decimal comma" if "," in t
                    else "dots separating thousands")
            return None, (f"{what} like {t}, read only in semicolon- or "
                          "tab-separated files")
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
