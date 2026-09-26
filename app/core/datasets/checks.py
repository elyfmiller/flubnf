"""The checks on the rows _read gave, every problem reported at once.

  _check_rows       the target column; the value and population number
                    styles; dates (parse, day-first, ambiguous M/D, one
                    weekday, week-end/start headers) and as_of dates;
                    values (numeric, negative, NA, whole for counts);
                    populations; then the two below, the records and the
                    summary
  _check_groups     names: charset, reserved, national, collisions, one
                    name per location
  _check_structure  duplicates, gaps and weeks after their as_of
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from datetime import date, timedelta

from .parsing import (
    _EITHER,
    DELIMITERS,
    ENCODING_NAMES,
    _day_first,
    _fmt_num,
    _month_first_only,
    _norm_name,
    _num,
    _swapped,
    _text,
    _year_first2,
    grouping_or_decimal,
    number_style,
    parse_date,
    saturday_on_or_before,
    week_ending,
)
from .report import MAX_EXAMPLES, Report, _examples, _rows, _Tally, _vis

#: the value kinds: counts (PF-eligible, Poisson floor, integer export) or
#: rates/proportions (neither). Undeclared, the values decide: whole numbers
#: are counts (unless their decimals could be thousands separators, see
#: grouping_or_decimal: then the kind is asked for).
KINDS = ("count", "rate")
#: the gap rule: consecutive dates within a group may differ by at most 8
#: days (one week plus a day's slack for rounding), so no week is missing
MAX_GAP_DAYS = 8

#: an as_of written M/D that reads both ways (03/01/2024) is read
#: month-first only when the file proves that order, and then only when
#: each such snapshot's newest week ends 0 to this many days before it:
#: read the other way round, a snapshot's as_of is at least 27 days off
MAX_ASOF_LAG = 21
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
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday")


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
    # each month-first reading's text and day-first twin, and the first
    # as_of that reads month-first only (1/13/2024; never 05/05/2024, which
    # reads the same both ways)
    asof_both, asof_alt, asof_md = _Tally(), {}, None
    # as_of formats, and the first month-first proof seen in each (a proof
    # in M/D/YYYY says nothing about an M/D/YY value in the same column)
    asof_formats, asof_amb_fmts, asof_md_by_fmt = set(), set(), {}
    bad_vals, neg, na, nonint = [], [], [], []
    # values written with a mark that could separate thousands (see mark)
    either = []
    # populations that are no whole number as written (123.456 in a comma
    # file: 123456 people with dots separating thousands, or none)
    bad_pop, miss_pop, frac_pop = [], [], []
    pmark = "," if pstyle == "decimal_comma" else "."
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
            a, af = parse_date(ta)
            if a is None:
                bad_asof.append((ln, ta or "(blank)"))
            else:
                asof_formats.add(af)
                if _swapped(ta) not in (None, a):
                    asof_both.add(ln, (ta, a))
                    asof_alt.setdefault(a, (ta, _swapped(ta)))
                    asof_amb_fmts.add(af)
                elif _month_first_only(ta):
                    asof_md_by_fmt.setdefault(af, ta)
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
                elif not p.is_integer() or (pmark in raw_p
                                            and _EITHER.fullmatch(raw_p)):
                    # a count of people: 1.000 is 1 or 1000, never 1.0
                    frac_pop.append((ln, raw_p))
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
    # dates written M/D with both numbers <= 12 (02/03/2024) read either
    # way. Over weeks in a row the wrong reading scatters (its weekdays
    # differ, its weeks leave gaps), but with one week per group both can
    # fall on one weekday with no week missing, and then, as with one week,
    # nothing in the file says which
    twin = {ln: _swapped(t) for ln, t, d in parsed
            if _swapped(t) not in (None, d)}
    if twin and not any(_month_first_only(t) for _, t, _ in parsed):
        if _weekly(rows) and _weekly(rows, twin):
            lines = sorted(twin)
            ln, t, d = next(x for x in parsed if x[0] in twin)
            (r0,) = _rows_of(raw_rows, [ln])
            rep.add("date_ambiguous", f"The '{col}' column's dates read "
                    f"both month-first and day-first ({_rows(lines)}; "
                    f"e.g., {t} ({_place(r0, date=False)}) is "
                    f"{d.isoformat()} or {twin[ln].isoformat()}), and either "
                    "reading puts every date on one weekday with no week "
                    "missing, so nothing in the file says which. Write "
                    "dates as YYYY-MM-DD.", lines)
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
    # an as_of proves month-first for the ambiguous ones only in their own
    # format(s); a proof written another way is not borrowed
    if asof_md_by_fmt and asof_amb_fmts <= set(asof_md_by_fmt):
        asof_md = next(iter(asof_md_by_fmt.values()))
    if asof_both.n and rows:
        # an as_of that reads both ways is read month-first only when the
        # file proves that order (an as_of or a date written with a day
        # over 12) and each such snapshot's newest week then ends 0 to
        # MAX_ASOF_LAG days before it; else the file is refused. Which
        # reading fits the snapshots more closely proves nothing: a
        # snapshot taken weeks after its newest week, or the day before
        # that week ends, can read days after it the other way round
        newest = {}                         # as_of -> (newest week, row)
        for ln, a, _, _, d, _, _ in rows:
            if a in asof_alt and (a not in newest or d > newest[a][0]):
                newest[a] = (d, ln)

        def after(a, w):
            """'3 days after' / '1 day before'"""
            n = (a - w).days
            return (f"{abs(n)} day{'s' if abs(n) != 1 else ''} "
                    + ("after" if n >= 0 else "before"))

        def lags(a):
            """How far each reading of ``a`` falls from its newest week."""
            t, twin = asof_alt[a]
            w = newest[a][0]
            return (f"{t} comes {after(a, w)} its snapshot's newest week, "
                    f"ending {w.isoformat()}",
                    f"read day-first, {after(twin, w)}")
        far = sorted(((a - w).days, a) for a, (w, _) in newest.items()
                     if not 0 <= (a - w).days <= MAX_ASOF_LAG)
        why, proven = "", ""
        ln, (t, a) = asof_both.eg[0]
        if not (asof_md or dates_md):
            why = ("nothing in the file says which: no as_of or date is "
                   "written M/D with a day over 12 (as 1/13/2024)")
            if a in newest:
                mf, df = lags(a)
                why += f". Read month-first, {mf}; {df}"
        elif far:
            n, a = far[0] if far[0][0] < 0 else far[-1]
            t, ln = asof_alt[a][0], newest[a][1]
            mf, df = lags(a)
            why = ((f"read month-first, a snapshot would hold weeks after "
                    f"its as_of ({mf}; {df})") if n < 0 else
                   (f"read month-first, {mf}, but an as_of that reads both "
                    f"ways is read month-first only up to {MAX_ASOF_LAG} "
                    f"days after it ({df})"))
            proven = (f" Other as_of dates are month-first (e.g., {asof_md})"
                      if asof_md else f" The '{col}' dates are month-first "
                      f"(e.g., {dates_md})") + (", but each as_of must "
                                                "also fit its snapshot read "
                                                "so.")
        elif not asof_md:
            rep.warnings.append(
                f"Read the '{cols['as_of']}' column's dates month-first, as "
                f"the '{col}' dates are (e.g., {dates_md}): {t} is "
                f"{a.isoformat()}, not {asof_alt[a][1].isoformat()}.")
        if why:
            (r0,) = _rows_of(raw_rows, [ln])
            rep.add("as_of_ambiguous", f"The '{cols['as_of']}' column's "
                    "dates read both month-first and day-first "
                    f"({_rows(asof_both.lines, asof_both.n)}; e.g., {t} is "
                    f"{a.isoformat()} or {asof_alt[a][1].isoformat()}, row "
                    f"{ln}: {_place(r0)}), and "
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
                "Values must be zero or positive.", lines)
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
    if frac_pop:
        lines = [ln for ln, _ in frac_pop]
        eg = next((t for _, t in frac_pop if _EITHER.fullmatch(t)), None)
        hint = (f"If the {'dots' if pmark == '.' else 'commas'} separate "
                "thousands, write the numbers without them "
                f"({eg} as {eg.replace(pmark, '')})." if eg else
                "Write each as a whole number.")
        rep.add("population_not_integer", f"The '{cols['population']}' "
                "column must hold whole numbers of people, but "
                f"{len(frac_pop)} {'is' if len(frac_pop) == 1 else 'are'} "
                f"not ({_rows(lines)}; e.g., {cells(frac_pop)}). " + hint,
                lines)
    if miss_pop:
        lines = [ln for ln, _ in miss_pop]
        rep.add("population_missing", f"The '{cols['population']}' column "
                f"is blank or NA on {len(miss_pop)} row(s) ({_rows(lines)}; "
                f"e.g., {cells(miss_pop)}). Give every row a population, or "
                "remove the column.", lines)
    if len(formats) > 1:
        rep.warnings.append(f"Dates mix formats ({', '.join(sorted(formats))}); "
                            "each was read by its own pattern.")
    if len(asof_formats) > 1:
        rep.warnings.append(f"The '{cols['as_of']}' dates mix formats "
                            f"({', '.join(sorted(asof_formats))}); each was "
                            "read by its own pattern.")

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
            "has_population": has_pop and not (bad_pop or miss_pop
                                               or frac_pop),
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


def _weekly(rows: list, twin=None) -> bool:
    """Whether ``rows`` (as _check_structure takes them, not yet moved)
    read as weekly series, each date replaced by its ``twin`` (by row
    number) where it has one: every date on one weekday, none twice in a
    group's snapshot, no week missing and none ending after its as_of."""
    twin = twin or {}
    wds, seen, series = set(), set(), {}
    for ln, a, name, _, d, _, _ in rows:
        d = twin.get(ln, d)
        wds.add(d.weekday())
        if (len(wds) > 1 or (a, name, d) in seen
                or (a is not None and week_ending(d) > a)):
            return False
        seen.add((a, name, d))
        series.setdefault((a, name), []).append(d)
    for ds in series.values():
        ds.sort()
        if any((q - p).days > MAX_GAP_DAYS for p, q in zip(ds, ds[1:])):
            return False
    return bool(rows)


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
