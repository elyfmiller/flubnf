"""Lenient reading of an upload (app/core/datasets.py validate/ingest): one
rule per test group, each also refusing what would be silently wrong.

Weekdays (any one weekday -> its week-ending Saturday, with a notice),
separators, numbers (thousands and decimal commas), encodings, header
aliases and the column mapping, datetimes and trailing blanks, row numbers,
problem kinds, kind inference, and stable ids. No hub, no engine.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.core import datasets as D

FIX = Path(__file__).resolve().parent / "fixtures"
TPL = FIX / "grouped-template-head.csv"
TPL_POP = FIX / "grouped-template-population-head.csv"


@pytest.fixture(autouse=True)
def _store_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")


def sats(start="2024-08-03", n=6):
    d0 = date.fromisoformat(start)
    return [d0 + timedelta(days=7 * i) for i in range(n)]


def csv_text(header, rows, sep=",", end="\n"):
    return end.join([header] + rows) + end


def ok(rep):
    assert rep.ok, [str(p) for p in rep.problems]
    return rep


def only(rep, code):
    assert code in rep.codes, [str(p) for p in rep.problems]
    return next(p for p in rep.problems if p.code == code)


def final_values(ds, group=None):
    rows = list(csv.DictReader(open(ds.final_path, encoding="utf-8")))
    return [r["value"] for r in rows
            if group is None or r["location_name"] == group]


# ---------------------------------------------------------------- weekdays

@pytest.mark.parametrize("back,name", [(6, "Sunday"), (5, "Monday"),
                                       (4, "Tuesday"), (3, "Wednesday"),
                                       (2, "Thursday"), (1, "Friday")])
def test_any_one_weekday_moves_to_its_week_ending_saturday(back, name):
    rows = [f"{(d - timedelta(days=back)).isoformat()},A,{i}"
            for i, d in enumerate(sats())]
    rep = ok(D.validate(csv_text("date,target_group,value", rows).encode()))
    s = rep.summary
    assert s["first"] == "2024-08-03" and s["last"] == "2024-09-07"
    assert s["date_shift_days"] == back and s["weekday"] == name
    plural = "day" if back == 1 else "days"
    assert rep.warnings[0] == (f"Dates moved to week-ending Saturdays: "
                               f"+{back} {plural} (each {name} to the "
                               "Saturday that ends its week).")
    ds = D.ingest(csv_text("date,target_group,value", rows).encode(), "wk")
    assert ds.weeks() == [d.isoformat() for d in sats()]
    assert ds.meta["options"]["date_shift_days"] == back


def test_saturdays_stay_put_without_a_notice():
    rows = [f"{d.isoformat()},A,1" for d in sats()]
    rep = ok(D.validate(csv_text("date,target_group,value", rows).encode()))
    assert rep.summary["date_shift_days"] == 0 and rep.warnings == []


def test_week_ending_is_the_mmwr_saturday():
    sat = date(2024, 8, 10)
    for k in range(7):                           # Sunday 08-04 .. Saturday
        assert D.week_ending(date(2024, 8, 4) + timedelta(days=k)) == sat


def test_mixed_weekdays_list_every_odd_row():
    rows = [f"{d.isoformat()},A,1" for d in sats(n=8)]
    rows[2] = "2024-08-19,A,1"                   # a Monday
    rows[5] = "2024-09-08,A,1"                   # a Sunday
    p = only(D.validate(csv_text("date,target_group,value", rows).encode()),
             "weekday")
    assert p.rows == (4, 7)
    assert "2 different" not in p.message        # three weekdays here
    assert "3 different weekdays" in p.message
    assert "6 rows on Saturday, 1 on Monday, 1 on Sunday" in p.message \
        or "6 rows on Saturday, 1 on Sunday, 1 on Monday" in p.message
    assert "2024-08-19 (A, Monday, row 4)" in p.message


def test_mixed_weekdays_that_read_day_first_say_so():
    # Saturdays written D/M/Y with every day <= 12: read month-first they
    # scatter over the week; read day-first they are all Saturdays
    days = [d for d in (date(2024, 1, 1) + timedelta(days=i)
                        for i in range(366))
            if d.weekday() == 5 and d.day <= 12][:10]
    rows = [f"{d.day:02d}/{d.month:02d}/{d.year},A,1" for d in days]
    rep = D.validate(csv_text("date,target_group,value", rows).encode())
    p = only(rep, "weekday")
    assert "Read day-first they would all be Saturdays" in p.message
    assert "not accepted" in p.message


def test_day_first_dates_are_refused_by_name():
    rows = ["13/01/2024,A,1", "20/01/2024,A,2", "yesterday,A,3"]
    rep = D.validate(csv_text("date,target_group,value", rows).encode())
    p = only(rep, "date_day_first")
    assert "rows 2, 3" in p.message and "13/01/2024" in p.message
    assert "day-first" in p.message
    assert only(rep, "date_parse").rows == (4,)


def test_spreadsheet_date_numbers_get_a_hint():
    rep = D.validate(b"date,target_group,value\n45297,A,1\n45304,A,2\n")
    assert "spreadsheet date numbers" in only(rep, "date_parse").message


def test_a_day_first_file_is_one_problem_not_three():
    """Sundays written DD/MM/YYYY: the dates with a day over 12 are
    day-first; the others (07/01/2024) must not be read month-first into
    weekday and missing-week problems as well."""
    days = [date(2023, 12, 31) + timedelta(days=7 * i) for i in range(10)]
    rows = [f"{d:%d/%m/%Y},{g},{i}" for i, d in enumerate(days)
            for g in ("Adult", "Pediatric")]
    rep = D.validate(csv_text("date,target_group,value", rows).encode())
    assert rep.codes == ["date_day_first"]
    assert rep.problems[0].rows == (2, 3, 6, 7, 8, 9, 10, 11, 16, 17, 18, 19)
    assert "31/12/2023" in rep.problems[0].message


def test_yy_mm_dd_dates_are_neither_read_nor_called_day_first():
    rows = [f"{d:%y/%m/%d},A,{i}" for i, d in enumerate(sats("2024-01-06"))]
    rep = D.validate(csv_text("date,target_group,value", rows).encode())
    assert rep.codes == ["date_parse"]
    assert "24/01/06 could be year-first or day-first" in rep.problems[0].message


def test_two_digit_years_read_as_a_spreadsheet_reads_them():
    assert D.parse_date("1/6/68")[0] == date(1968, 1, 6)
    assert D.parse_date("1/6/30")[0] == date(1930, 1, 6)
    assert D.parse_date("1/6/29")[0] == date(2029, 1, 6)
    assert D.parse_date("8/3/24")[0] == date(2024, 8, 3)


def test_a_day_first_as_of_says_so():
    raw = (b"as_of,target_end_date,location,observation\n"
           b"13/01/2024,2024-01-06,US,1\n13/01/2024,2024-01-13,US,2\n")
    p = only(D.validate(raw), "as_of_parse")
    assert "13/01/2024 is day-first" in p.message


def test_an_as_of_that_reads_both_ways_is_settled_by_its_snapshots():
    """ISO weeks, as_of written 03/01/2024 and 10/01/2024 (3 and 10
    January): read month-first they were stored silently as snapshots of
    March and October over data that ends 2024-01-06."""
    raw = (b"target_end_date,location,observation,as_of\n"
           b"2023-12-30,A,5,03/01/2024\n2024-01-06,A,6,10/01/2024\n"
           b"2023-12-30,A,5,10/01/2024\n")
    rep = D.validate(raw)
    assert rep.codes == ["as_of_ambiguous"]
    p = rep.problems[0]
    assert p.rows == (2, 3, 4) and p.kind == "Dates"
    assert "03/01/2024 is 2024-03-01 or 2024-01-03" in p.message
    with pytest.raises(D.DatasetError):
        D.ingest(raw, "asof")
    assert D.list_datasets() == []
    # month-first that fits (1/8/24 just after the week of 2024-01-06)
    rep = ok(D.validate(b"target_end_date,location,observation,as_of\n"
                        b"2024-01-06,A,5,1/8/24\n2023-12-30,A,4,1/8/24\n"))
    assert rep.summary["as_of"] == ["2024-01-08"]
    # 1/13/2024 reads one way, and so does the column it is in
    ok(D.validate(b"target_end_date,location,observation,as_of\n"
                  b"2023-12-30,A,5,1/3/2024\n2024-01-06,A,6,1/13/2024\n"))


#: an as_of whose day equals its month (05/05/2024) once counted as proof
#: of month-first and switched the check off: 12/05/2024 was stored as a
#: December snapshot of weeks that end in May
ASOF_PALINDROME = (b"target_end_date,location,observation,as_of\n"
                   b"2024-04-27,A,5,05/05/2024\n2024-04-27,A,5,12/05/2024\n"
                   b"2024-05-04,A,6,12/05/2024\n")
#: a date column written M/D once switched the check off, though 02/02/2024
#: reads the same both ways: 05/02/2024 was stored as May 2, not Feb 5
ASOF_PAL_DATE = (b"week,location,observation,as_of\n"
                 b"02/02/2024,US,288,05/02/2024\n02/02/2024,01,20,05/02/2024\n")


def test_an_as_of_whose_day_is_its_month_proves_no_order():
    rep = D.validate(ASOF_PALINDROME)
    assert rep.codes == ["as_of_ambiguous"]
    p = rep.problems[0]
    assert p.rows == (3, 4)
    assert ("e.g., 12/05/2024 is 2024-12-05 or 2024-05-12, row 3: "
            "2024-04-27, A") in p.message
    with pytest.raises(D.DatasetError):
        D.ingest(ASOF_PALINDROME, "pal")
    # alone, it is the same date either way
    rep = ok(D.validate(b"target_end_date,location,observation,as_of\n"
                        b"2024-04-27,A,5,05/05/2024\n"
                        b"2024-05-04,A,6,05/05/2024\n"))
    assert rep.summary["as_of"] == ["2024-05-05"]


def test_dates_written_m_d_prove_month_first_only_with_a_day_over_12():
    rep = D.validate(ASOF_PAL_DATE)
    assert rep.codes == ["as_of_ambiguous"]
    p = rep.problems[0]
    assert p.rows == (2, 3)
    assert ("05/02/2024 is 2024-05-02 or 2024-02-05, row 2: 02/02/2024, US"
            in p.message)
    # dates with both numbers <= 12 say nothing either
    raw = (b"week,location,observation,as_of\n"
           b"02/03/2024,A,1,12/02/2024\n02/10/2024,A,2,12/02/2024\n")
    assert D.validate(raw).codes == ["as_of_ambiguous"]
    # an as_of that says so itself stands
    rep = ok(D.validate(b"week,location,observation,as_of\n"
                        b"02/03/2024,A,1,2/5/2024\n02/10/2024,A,2,2/13/2024\n"
                        b"02/03/2024,A,1,2/13/2024\n"))
    assert rep.summary["as_of"] == ["2024-02-05", "2024-02-13"]


def test_the_closer_fit_decides_past_the_longest_lag():
    """A long-lagged ISO snapshot beside an as_of that reads both ways:
    1/2/2024 is 3 days after its week month-first, 33 day-first."""
    raw = (b"target_end_date,location,observation,as_of\n"
           b"2024-03-02,A,5,2024-06-29\n2023-12-30,A,4,1/2/2024\n")
    assert ok(D.validate(raw)).summary["as_of"] == ["2024-01-02",
                                                    "2024-06-29"]
    raw = raw.replace(b"1/2/2024", b"2/1/2024")      # the other way round
    assert D.validate(raw).codes == ["as_of_ambiguous"]


def test_month_first_dates_do_not_carry_an_as_of_that_does_not_fit():
    """1/13/2024 proves the dates month-first, but as_of dates with both
    numbers <= 12 must still fit their snapshots read so."""
    # month-first would put the weeks after their as_of (Jan 12)
    raw = (b"target_end_date,location,observation,as_of\n"
           b"1/6/2024,A,5,1/12/2024\n1/13/2024,A,6,1/12/2024\n")
    p = only(D.validate(raw), "as_of_ambiguous")
    assert "a snapshot would hold weeks after its as_of" in p.message
    assert ("The 'target_end_date' dates are month-first (e.g., 1/13/2024)"
            in p.message)
    # months after their newest week, where day-first is days after
    raw = (b"target_end_date,location,observation,as_of\n"
           b"12/30/2023,A,5,03/01/2024\n1/6/2024,A,6,10/01/2024\n")
    p = only(D.validate(raw), "as_of_ambiguous")
    assert "day-first fits the snapshots better" in p.message
    # month-first that fits stands
    rep = ok(D.validate(b"target_end_date,location,observation,as_of\n"
                        b"12/30/2023,A,5,1/8/2024\n1/6/2024,A,6,1/8/2024\n"))
    assert rep.summary["as_of"] == ["2024-01-08"]


def test_an_as_of_passed_only_by_the_move_to_saturday_says_so():
    """A same-day as_of on Wednesday dates is refused (the week ends on
    the Saturday after it), which surprised: the message says why."""
    raw = (b"target_end_date,location,observation,as_of\n"
           b"2024-01-03,A,5,2024-01-10\n2024-01-10,A,6,2024-01-10\n")
    p = only(D.validate(raw), "as_of_before_date")
    assert "2024-01-10 (week ending 2024-01-13) in as_of 2024-01-10" \
        in p.message
    assert "Each date was moved to the Saturday that ends its week" \
        in p.message
    # a week after its as_of as written needs no such note
    p = only(D.validate(b"target_end_date,location,observation,as_of\n"
                        b"2024-01-06,A,5,2024-01-06\n"
                        b"2024-01-13,A,6,2024-01-06\n"), "as_of_before_date")
    assert "moved to the Saturday" not in p.message


def test_a_single_week_written_month_or_day_first_is_refused():
    """Over two weeks or more the weekdays and gaps tell a day-first file;
    over one, 06/01/2024 was read as June 1 without a word."""
    p = only(D.validate(b"date,target_group,value\n06/01/2024,A,5\n"
                        b"06/01/2024,B,7\n"), "date_ambiguous")
    assert p.rows == (2, 3)
    assert "reads as 2024-06-01 month-first or 2024-01-06 day-first" \
        in p.message
    for one in (b"1/13/2024", b"2024-06-01", b"1/1/2024"):
        ok(D.validate(b"date,target_group,value\n" + one + b",A,5\n"))


@pytest.mark.parametrize("header", ["week_ending", "Week End", "end_date",
                                    "target_end_date"])
@pytest.mark.parametrize("back,name", [(6, "Sunday"), (5, "Monday"),
                                       (4, "Tuesday")])
def test_week_ends_on_a_sunday_monday_or_tuesday_are_refused(header, back,
                                                              name):
    """Most of a week ending on these days lies in the MMWR week before;
    moving each to the Saturday after would label every week a week
    late."""
    rows = [f"{(d - timedelta(days=back)).isoformat()},A,{i}"
            for i, d in enumerate(sats("2024-01-13"))]
    rep = D.validate(csv_text(f"{header},target_group,value", rows).encode())
    p = only(rep, "weekday_end")
    first = date(2024, 1, 13) - timedelta(days=back)
    assert f"its dates are {name}s" in p.message
    assert f"{first.isoformat()} -> 2024-01-06" in p.message
    assert p.rows == (2, 3, 4, 5, 6, 7)
    # the same dates as week starts (or any date) move forward
    rep = ok(D.validate(csv_text("date,target_group,value", rows).encode()))
    assert rep.summary["first"] == "2024-01-13"


def test_week_ends_on_a_wednesday_or_friday_move_forward():
    for back in (3, 1):
        rows = [f"{(d - timedelta(days=back)).isoformat()},A,{i}"
                for i, d in enumerate(sats("2024-01-13"))]
        rep = ok(D.validate(csv_text("week_ending,target_group,value",
                                     rows).encode()))
        assert rep.summary["date_shift_days"] == back


@pytest.mark.parametrize("header", ["Week ending (Sunday)", "period_end",
                                    "PeriodEnd"])
def test_a_mapped_column_named_for_week_ends_is_guarded_too(header):
    """Only the alias headers were guarded: a mapped 'Week ending
    (Sunday)' column of Sundays moved +6, a week late."""
    rows = [f"{(d - timedelta(days=6)).isoformat()},A,{i}"
            for i, d in enumerate(sats("2024-01-13"))]
    rep = D.validate(csv_text(f"{header},target_group,value", rows).encode(),
                     columns={"date": header})
    p = only(rep, "weekday_end")
    assert "2024-01-07 -> 2024-01-06" in p.message


@pytest.mark.parametrize("back,name", [(0, "Saturday"), (1, "Friday"),
                                       (2, "Thursday"), (3, "Wednesday"),
                                       (6, "Sunday")])
def test_week_starts_on_a_thursday_friday_or_saturday_are_refused(back, name):
    """Most of a week starting on these days lies in the MMWR week after:
    keeping each in the week of its first day labels it a week early."""
    rows = [f"{(d - timedelta(days=back)).isoformat()},A,{i}"
            for i, d in enumerate(sats("2024-01-13"))]
    rep = D.validate(csv_text("week_start,target_group,value", rows).encode(),
                     columns={"date": "week_start"})
    if back >= 3:                    # Sunday to Wednesday: its own week
        assert ok(rep).summary["first"] == "2024-01-13"
        return
    p = only(rep, "weekday_start")
    first = date(2024, 1, 13) - timedelta(days=back)
    assert f"its dates are {name}s" in p.message
    assert f"{first.isoformat()} -> 2024-01-20" in p.message


def test_a_gap_names_the_weeks_it_leaves_out():
    rows = [f"{d.isoformat()},A,{i}" for i, d in enumerate(sats(n=8))]
    del rows[2]                                  # 2024-08-17
    p = only(D.validate(csv_text("date,target_group,value", rows).encode()),
             "gap")
    assert p.rows == (3, 4)
    assert ("2024-08-17 is missing between 2024-08-10 and 2024-08-24 in "
            "group 'A'") in p.message
    del rows[2:4]                                # and 08-24, 08-31
    p = only(D.validate(csv_text("date,target_group,value", rows).encode()),
             "gap")
    assert ("2024-08-17 to 2024-08-31 (3 weeks) are missing between "
            "2024-08-10 and 2024-09-07") in p.message


def test_week_problems_quote_the_dates_as_the_file_writes_them():
    """Wednesdays moved +3: the rows say 2024-01-10, not 2024-01-13."""
    raw = (b"as_of,target_end_date,location,observation\n"
           b"2024-01-10,2023-12-27,US,10\n2024-01-10,2024-01-03,US,11\n"
           b"2024-01-10,2024-01-10,US,12\n")
    p = only(D.validate(raw), "as_of_before_date")
    assert ("2024-01-10 (week ending 2024-01-13) in as_of 2024-01-10 (US)"
            in p.message)
    rows = [f"{(d - timedelta(days=3)).isoformat()},A,{i}"
            for i, d in enumerate(sats(n=6))]
    rows.append(rows[1])
    del rows[3]
    rep = D.validate(csv_text("date,target_group,value", rows).encode())
    assert "2024-07-31 (week ending 2024-08-03) + A" not in str(rep.problems)
    assert ("2024-08-07 (week ending 2024-08-10) + A"
            in only(rep, "duplicate").message)
    assert ("2024-08-21 (week ending 2024-08-24) is missing"
            in only(rep, "gap").message)


# --------------------------------------------------------------- separators

def test_a_sep_line_names_the_separator():
    """A spreadsheet's "sep=;" first line (it hides the line, so the header
    is row 1) once became the header and asked for a column mapping."""
    rows = [f"{d.isoformat()};A;{i}" for i, d in enumerate(sats())]
    rows[2] = "2024-08-17;A;-1"
    raw = csv_text("sep=;\r\ndate;target_group;value", rows).encode()
    p = only(D.validate(raw), "value_negative")
    assert p.rows == (4,)
    rep = ok(D.validate(raw.replace(b";-1", b";1")))
    assert rep.summary["delimiter"] == "semicolon"
    assert rep.summary["first_rows"][0]["row"] == 2


@pytest.mark.parametrize("sep", [",", ";", "\t"])
def test_comma_semicolon_and_tab_files_read_alike(sep):
    rows = [sep.join((d.isoformat(), "Adult", str(10 + i), "5000"))
            for i, d in enumerate(sats())]
    raw = csv_text(sep.join(("date", "target_group", "value", "population")),
                   rows).encode()
    rep = ok(D.validate(raw))
    assert rep.summary["groups"] == ["Adult"] and rep.summary["rows"] == 6
    assert rep.summary["has_population"]
    assert rep.summary["delimiter"] == D.DELIMITERS[sep]


def test_sniff_prefers_the_separator_that_names_most_columns():
    assert D.sniff_delimiter(["date;group;value\n", "2024-08-03;A;1,5\n"]) == ";"
    assert D.sniff_delimiter(['date,group,value\n',
                              '2024-08-03,A,"1;5"\n']) == ","
    assert D.sniff_delimiter(["date\tgroup\tvalue\n"]) == "\t"
    assert D.sniff_delimiter(["just one column\n"]) == ","


# ------------------------------------------------------------------ numbers

@pytest.mark.parametrize("texts,sep,style", [
    (["1", "25", "0.5"], ",", "plain"),
    (["1,234", "56"], ",", "thousands"),             # a quoted "1,234"
    (["1,234,567"], ";", "thousands"),               # can only be grouping
    (["1,234.5", "7"], ";", "thousands"),
    (["1,234", "0.5"], ";", "thousands"),            # '.' is the decimal
    (["1,5", "2"], ";", "decimal_comma"),
    (["0,25", "1,234"], "\t", "decimal_comma"),      # "1,234" = 1.234 here
    (["1.234,5"], ";", "decimal_comma"),
    (["1.234.567"], ";", "decimal_comma"),           # dot grouping
    (["1.234", "2.5"], ";", "plain"),
    (["1.234"], ",", "plain"),                       # a comma file: 1.234
    (["1,234"], ";", None),                          # 1234 or 1.234?
    (["1.234"], ";", None),
    (["1.234"], "\t", None),
    (["1,5", "2.5"], ";", None),                     # both decimal marks
    (["1,5"], ",", None),                            # decimal comma, comma file
])
def test_number_style(texts, sep, style):
    assert D.number_style(texts, sep)[0] == style


def test_quoted_thousands_in_a_comma_file_are_counts():
    rows = [f'{d.isoformat()},A,"1,{i:03d}","1,234,567"'
            for i, d in enumerate(sats())]
    raw = csv_text("date,target_group,value,population", rows).encode()
    rep = ok(D.validate(raw))
    assert rep.summary["inferred_kind"] == "count"
    assert any("thousands separators" in w for w in rep.warnings)
    ds = D.ingest(raw, "th")
    assert final_values(ds) == [str(1000 + i) for i in range(6)]
    assert ds.kind == "count" and ds.populations == {"A": 1234567}


def test_decimal_commas_in_a_semicolon_file_are_rates():
    rows = [f"{d.isoformat()};A;{i},5;1.234.567" for i, d in enumerate(sats())]
    raw = csv_text("date;target_group;value;population", rows).encode()
    rep = ok(D.validate(raw))
    assert rep.summary["inferred_kind"] == "rate"
    assert any("decimal commas" in w for w in rep.warnings)
    ds = D.ingest(raw, "dc")
    assert final_values(ds) == [f"{i}.5" for i in range(6)]
    assert ds.kind == "rate" and ds.populations == {"A": 1234567}


@pytest.mark.parametrize("values,sep,why", [
    (["1.000", "1.200"], ";", "1.000 could be 1000 or 1.000"),
    (["1,5", "2.5"], ";", "mixed with decimal points"),
    (['"1,5"', '"2,5"'], ",", "semicolon- or tab-separated"),
])
def test_ambiguous_numbers_are_refused_with_their_rows(values, sep, why):
    rows = [sep.join((d.isoformat(), "A", v))
            for d, v in zip(sats(), values)]
    rep = D.validate(csv_text(sep.join(("date", "target_group", "value")),
                              rows).encode())
    p = only(rep, "value_format")
    assert why in p.message and "rows 2, 3" in p.message
    assert "value_numeric" not in rep.codes


#: a comma file whose dots may separate thousands (987, 1.234, 12.345):
#: once read as decimals and stored as rates without a word
DOT_THOUSANDS = (b"date,group,value\n2024-01-06,Berlin,987\n"
                 b"2024-01-13,Berlin,1.234\n2024-01-20,Berlin,2.345\n"
                 b"2024-01-27,Berlin,12.345\n2024-02-03,Berlin,999\n"
                 b"2024-02-10,Berlin,850\n")


def test_dots_that_may_separate_thousands_ask_for_the_kind():
    rep = D.validate(DOT_THOUSANDS)
    assert rep.codes == ["kind_ambiguous"]
    p = rep.problems[0]
    assert p.rows == (3, 4, 5) and p.kind == "Values"
    assert ("e.g., 1.234 (2024-01-13, Berlin), 2.345 (2024-01-20, Berlin), "
            "12.345 (2024-01-27, Berlin)") in p.message
    assert "1.234 is 1.234 as a rate or 1234 as a count" in p.message
    assert "Choose whether the values are counts or rates" in p.message
    assert rep.summary["inferred_kind"] is None       # nothing inferred
    with pytest.raises(D.DatasetError):
        D.ingest(DOT_THOUSANDS, "berlin")
    assert D.list_datasets() == []
    # declared counts: refused, with the separator named
    p = only(D.validate(DOT_THOUSANDS, kind="count"), "value_not_integer")
    assert p.rows == (3, 4, 5)
    assert "3 are not written as whole numbers" in p.message
    assert "write the numbers without them (1.234 as 1234)" in p.message
    # declared rates: decimals, and a notice says how they were read
    rep = ok(D.validate(DOT_THOUSANDS, kind="rate"))
    assert [r[4] for r in rep.records][1:4] == [1.234, 2.345, 12.345]
    assert any("as decimals, as the values are rates" in w
               for w in rep.warnings)
    assert D.ingest(DOT_THOUSANDS, "berlin", kind="rate").kind == "rate"


@pytest.mark.parametrize("values,kind", [
    (["987", "1.000", "2.000"], None),      # whole as decimals: 1 or 1000?
    (["987", "1.000", "2.000"], "count"),
    (["1,234", "5.678"], None),             # a quoted comma says nothing
])
def test_whole_looking_dot_values_are_not_counts_by_default(values, kind):
    rows = [f'{d.isoformat()},A,"{v}"' for d, v in zip(sats(), values)]
    rep = D.validate(csv_text("date,target_group,value", rows).encode(),
                     kind=kind)
    assert rep.codes == ["kind_ambiguous" if kind is None
                         else "value_not_integer"]


@pytest.mark.parametrize("values", [
    ["0.5", "1.234"],                       # 0.5: the dot is a decimal
    ["1.25", "2.345"],
    ["1234.567", "2"],                      # four digits: no grouping
    ["987", "1234", "12"],
])
def test_a_column_that_shows_its_decimals_is_still_inferred(values):
    rows = [f"{d.isoformat()},A,{v}" for d, v in zip(sats(), values)]
    rep = ok(D.validate(csv_text("date,target_group,value", rows).encode()))
    assert rep.summary["inferred_kind"] == (
        "count" if values[0] == "987" else "rate")


@pytest.mark.parametrize("sep", [";", "\t"])
def test_decimal_commas_that_may_separate_thousands_ask_for_the_kind(sep):
    """The mirror in a semicolon or tab file: 1,234 is 1.234 or 1234."""
    rows = [sep.join((d.isoformat(), "A", v))
            for d, v in zip(sats(), ["987", "1,234", "2,500"])]
    raw = csv_text(sep.join(("date", "target_group", "value")),
                   rows).encode()
    p = only(D.validate(raw), "kind_ambiguous")
    assert p.rows == (3, 4) and "comma separating thousands" in p.message
    assert "1,234 is 1.234 as a rate or 1234 as a count" in p.message
    p = only(D.validate(raw, kind="count"), "value_not_integer")
    assert "(1,234 as 1234)" in p.message
    rep = ok(D.validate(raw, kind="rate"))
    assert [r[4] for r in rep.records] == [987, 1.234, 2.5]
    # a decimal comma that cannot be grouping settles it (rates)
    rows[0] = sep.join(("2024-08-03", "A", "1,5"))
    rep = ok(D.validate(csv_text(sep.join(("date", "target_group",
                                           "value")), rows).encode()))
    assert rep.summary["inferred_kind"] == "rate"


def test_the_command_line_names_the_kind_option():
    lines = D.problem_lines(D.validate(DOT_THOUSANDS))
    assert lines[-1] == "Say which with --kind count or --kind rate."


def test_a_population_column_is_read_on_its_own_style():
    rows = [f"{d.isoformat()};A;{10 + i};1,500" for i, d in enumerate(sats())]
    rep = D.validate(csv_text("date;target_group;value;population",
                              rows).encode())
    only(rep, "population_format")


def test_dot_thousands_are_named_as_such():
    """A population read as dot thousands once got the decimal-comma
    notice."""
    rows = [f"{d.isoformat()};A;{10 + i};1.234.567" for i, d in
            enumerate(sats())]
    rep = ok(D.validate(csv_text("date;target_group;value;Pop",
                                 rows).encode()))
    assert rep.records[0][5] == 1234567
    assert rep.warnings == ["Read the 'Pop' column's dots as thousands "
                            "separators (1.234 = 1234)."]
    rows = [f"{d.isoformat()};A;{i},5;1.234.567" for i, d in
            enumerate(sats())]
    rep = ok(D.validate(csv_text("date;target_group;value;Pop",
                                 rows).encode()))
    assert rep.warnings[0] == "Read the 'value' column's decimal commas (1,5 = 1.5)."


@pytest.mark.parametrize("text", ["1_000", "５", "٣", "infinity", "0x10"])
def test_numbers_are_ascii_digits(text):
    """float() alone reads '1_000' as 1000 and full-width digits."""
    rows = [f"{d.isoformat()},A,{i}" for i, d in enumerate(sats())]
    rows[2] = f"2024-08-17,A,{text}"
    p = only(D.validate(csv_text("date,target_group,value",
                                 rows).encode()), "value_numeric")
    assert p.rows == (4,) and text in p.message


def test_missing_values_quote_the_cell_its_date_and_group():
    rows = [f"{d.isoformat()},{g},{i},1000" for i, d in enumerate(sats())
            for g in ("A", "B")]
    rows[3] = "2024-08-10,B,,1000"
    rows[6] = "2024-08-24,A,NA,"
    rep = D.validate(csv_text("date,target_group,value,population",
                              rows).encode())
    p = only(rep, "value_na")
    assert p.rows == (5, 8)
    assert ("(rows 5, 8; e.g., (blank) (2024-08-10, B), NA (2024-08-24, A))"
            in p.message)
    assert "row 5; e.g., row 5" not in str(rep.problems)
    p = only(rep, "population_missing")
    assert "(row 8; e.g., (blank) (2024-08-24, A))" in p.message


# ---------------------------------------------------------------- encodings

def _intl_rows():
    return [f"{d.isoformat()}\tÅland\t{i}" for i, d in enumerate(sats())] + [
        f"{d.isoformat()}\tNiños\t{i}" for i, d in enumerate(sats())]


@pytest.mark.parametrize("codec", ["utf-16", "utf-16-le", "utf-16-be",
                                   "utf-8", "utf-8-sig"])
def test_utf16_and_utf8_files_keep_their_names(codec):
    """utf-16 = a spreadsheet's "Unicode text" (BOM, tab-separated);
    utf-16-le/-be carry no BOM."""
    raw = csv_text("date\ttarget_group\tvalue", _intl_rows()).encode(codec)
    rep = ok(D.validate(raw))
    assert rep.summary["groups"] == ["Niños", "Åland"]
    assert rep.summary["encoding"] == ("UTF-16" if "16" in codec else "UTF-8")
    assert rep.summary["delimiter"] == "tab"
    assert not any("Windows-1252" in w for w in rep.warnings)


def test_windows_1252_is_read_and_named():
    raw = csv_text("date\ttarget_group\tvalue", _intl_rows()).encode("cp1252")
    rep = ok(D.validate(raw))
    assert rep.summary["groups"] == ["Niños", "Åland"]
    assert rep.summary["encoding"] == "Windows-1252"
    assert "Windows-1252" in rep.warnings[0]


def test_a_late_non_utf8_byte_rereads_the_whole_file(tmp_path):
    """The first non-UTF-8 byte sits far past the first read-ahead: the
    whole file is read again as Windows-1252, and the stored source is the
    upload's exact bytes."""
    rows = [f"{d.isoformat()},A,{i % 50}" for i, d in
            enumerate(sats("1950-01-07", 3000))]
    rows += [f"{d.isoformat()},Niños,{i}" for i, d in
             enumerate(sats("1950-01-07", 3000))]
    raw = csv_text("date,target_group,value", rows).encode("cp1252")
    assert raw.index(b"\xf1") > 32 * 1024          # many read chunks in
    rep = ok(D.validate(raw))
    assert rep.summary["groups"] == ["A", "Niños"]
    assert rep.summary["rows"] == 6000 and rep.n_bytes == len(raw)
    ds = D.ingest(raw, "late")
    assert ds.source_path.read_bytes() == raw
    assert ds.groups == ["A", "Niños"]


def test_windows_1252_undefined_bytes_read_as_latin1():
    rows = [f"{d.isoformat()},A,1,note \x81" for d in sats()]
    raw = csv_text("date,target_group,value,notes", rows).encode("latin-1")
    rep = ok(D.validate(raw))
    assert rep.summary["encoding"] == "Windows-1252"


def test_detect_encoding():
    assert D.detect_encoding(b"\xef\xbb\xbfdate") == "utf-8-sig"
    assert D.detect_encoding("date".encode("utf-16")) == "utf-16"
    assert D.detect_encoding("date,group".encode("utf-16-le")) == "utf-16-le"
    assert D.detect_encoding("date,group".encode("utf-16-be")) == "utf-16-be"
    assert D.detect_encoding(b"date,group") == "utf-8"
    assert D.detect_encoding(b"") == "utf-8"


# ------------------------------------------------------------------ headers

@pytest.mark.parametrize("role,header", [
    (r, h) for r, hs in {
        "date": ["date", "Week", "week_end", "Week Ending", "END_DATE",
                 "target_end_date", "week-ending"],
        "value": ["value", "Count", "cases", "Admissions",
                  "hospitalizations", "observation"],
        "group": ["target_group", "Group", "location", "Location Name",
                  "region", "JURISDICTION"],
        "population": ["population", "Pop"],
    }.items() for h in hs])
def test_header_aliases(role, header):
    names = {"date": "date", "group": "target_group", "value": "value"}
    names[role] = header
    cols = [names["date"], names["group"], names["value"]]
    rows = [f"{d.isoformat()},A,{i}" for i, d in enumerate(sats())]
    if role == "population":
        cols.append(header)
        rows = [r + ",1000" for r in rows]
    rep = ok(D.validate(csv_text(",".join(cols), rows).encode()))
    assert rep.columns[role] == header
    assert rep.summary["has_population"] == (role == "population")


def test_header_matching_ignores_case_spaces_and_underscores():
    rows = [f"{d.isoformat()},A,{i}" for i, d in enumerate(sats())]
    rep = ok(D.validate(csv_text(" Target End Date ,TARGET GROUP,Val_ue",
                                 rows).encode()))
    assert rep.columns == {"format": "grouped", "date": "Target End Date",
                           "group": "TARGET GROUP", "value": "Val_ue"}


def test_the_canonical_pairs_keep_their_precedence():
    rows = [f"{d.isoformat()},2000-01-01,A,{i},0" for i, d in enumerate(sats())]
    rep = ok(D.validate(csv_text("target_end_date,date,location,observation,"
                                 "value", rows).encode()))
    assert rep.columns["date"] == "target_end_date"
    assert rep.columns["value"] == "observation"
    assert "Ignored column(s): date, value." in rep.warnings


def test_two_candidate_date_columns_ask_for_a_choice():
    rows = [f"{d.isoformat()},{d.isoformat()},A,1" for d in sats()]
    raw = csv_text("date,week,group,value", rows).encode()
    rep = D.validate(raw)
    p = only(rep, "ambiguous_columns")
    assert "'date' and 'week'" in p.message
    assert "Choose one (e.g., date)" in p.message
    assert rep.needs_mapping and rep.codes == ["ambiguous_columns"]
    rep = ok(D.validate(raw, columns={"date": "week"}))
    assert rep.columns["date"] == "week"
    assert "Ignored column(s): date." in rep.warnings


def test_a_column_mapping_names_headers_or_positions():
    rows = [f"{d.isoformat()},A,{i},9" for i, d in enumerate(sats())]
    raw = csv_text("day,area,amount,people", rows).encode()
    rep = D.validate(raw)
    assert rep.needs_mapping and rep.codes == ["missing_columns"]
    assert rep.headers == ["day", "area", "amount", "people"]
    rep = ok(D.validate(raw, columns={"date": "Day", "group": "#2",
                                      "value": "amount",
                                      "population": "people"}))
    assert rep.columns == {"format": "grouped", "date": "day",
                           "group": "area", "value": "amount",
                           "population": "people"}
    ds = D.ingest(raw, "mapped", columns={"date": "day", "group": "area",
                                          "value": "amount"})
    assert ds.meta["columns"]["value"] == "amount" and ds.groups == ["A"]


def test_a_mapping_to_nothing_or_twice_is_refused():
    raw = csv_text("day,area,amount", ["2024-08-03,A,1"]).encode()
    rep = D.validate(raw, columns={"date": "when", "group": "area",
                                   "value": "amount"})
    assert "'when' for the date" in only(rep, "column_unknown").message
    assert rep.needs_mapping
    rep = D.validate(raw, columns={"date": "day", "group": "area",
                                   "value": "day"})
    only(rep, "column_unknown")


def test_location_with_location_name_is_the_hubverse_pair():
    rows = [f"{d.isoformat()},01,Alabama,5" for d in sats()]
    rep = ok(D.validate(csv_text("date,location,location_name,value",
                                 rows).encode()))
    assert rep.columns["group"] == "location"
    assert rep.columns["location_name"] == "location_name"
    assert rep.summary["format"] == "hubverse"
    assert rep.summary["groups"] == ["Alabama"]


def test_datetimes_trailing_blank_rows_and_columns_and_extra_columns():
    rows = [f"{d.isoformat()} 00:00:00,A,{i},note {i},," for i, d in
            enumerate(sats())] + [",,,,,", ",,,,,", ""]
    raw = csv_text("Week Ending,Region,Admissions,Notes,,", rows,
                   end="\r\n").encode()
    rep = ok(D.validate(raw))
    assert rep.summary["first"] == "2024-08-03" and rep.summary["rows"] == 6
    assert rep.warnings == ["Ignored column(s): Notes."]
    assert rep.summary["first_rows"][0] == {
        "row": 2, "date": "2024-08-03 00:00:00", "week": "2024-08-03",
        "group": "A", "value": "0", "population": ""}


def test_a_short_row_is_ragged_only_when_it_lacks_a_used_column():
    rows = [f"{d.isoformat()},A,{i},x" for i, d in enumerate(sats())]
    rows[1] = rows[1].rsplit(",", 1)[0]          # lacks only 'notes'
    ok(D.validate(csv_text("date,target_group,value,notes", rows).encode()))
    rows[2] = "2024-08-17,A"                     # lacks the value
    p = only(D.validate(csv_text("date,target_group,value,notes",
                                 rows).encode()), "ragged")
    assert p.rows == (4,)


@pytest.mark.parametrize("raw,example", [
    # an unquoted thousands comma: once read as value 1, kind count
    (b"date,target_group,value\n2024-01-06,A,1,234\n2024-01-13,A,1,500\n"
     b"2024-01-20,A,987\n", "row 2: 2024-01-06,A,1,234"),
    # ... and with a population after it: once value 1, population 234
    (b"date,target_group,value,population\n2024-01-06,A,1,234,5000\n"
     b"2024-01-13,A,1,500,5000\n", "row 2: 2024-01-06,A,1,234,5000"),
    # an unquoted comma in the last used column: once the group 'Bern'
    (b"date,value,target_group\n2024-01-06,5,Bern, Stadt\n"
     b"2024-01-13,6,Bern, Stadt\n", "row 2: 2024-01-06,5,Bern, Stadt"),
])
def test_a_row_with_more_fields_than_the_header_is_refused(raw, example):
    """An unquoted separator inside a value splits it; the cells past the
    header were once dropped without a word, so the row read wrong."""
    rep = D.validate(raw)
    assert rep.codes == ["extra_fields"]
    p = rep.problems[0]
    assert p.rows == (2, 3) and p.kind == "Columns"
    assert example in p.message and '"1,234"' in p.message
    with pytest.raises(D.DatasetError):
        D.ingest(raw, "cut")
    assert D.list_datasets() == []


def test_extra_fields_name_the_separator_and_spare_empty_cells():
    rows = [f"{d.isoformat()};A;{i};;" for i, d in enumerate(sats())]
    ok(D.validate(csv_text("date;target_group;value", rows).encode()))
    rows[3] = "2024-08-24;A;1;x"
    p = only(D.validate(csv_text("date;target_group;value", rows).encode()),
             "extra_fields")
    assert p.rows == (5,) and "unquoted semicolon" in p.message
    # a quoted comma is one field, as ever
    rep = ok(D.validate(b'date,target_group,value\n2024-01-06,A,"1,234"\n'
                        b'2024-01-13,A,"1,500"\n'))
    assert [r[4] for r in rep.records] == [1234, 1500]


@pytest.mark.parametrize("raw", [
    # a trailing comment column the writer always writes: once read as
    # value 1 (1234 lost), with only the ignored-column notice
    (b"date,target_group,value,comment\n2024-01-06,A,1,234,\n"
     b"2024-01-13,A,987,\n2024-01-20,A,1,002,\n"),
    # the same from a writer that drops trailing empty cells: the base
    # refused it as ragged, the lenient reader once accepted it
    (b"date,target_group,value,comment\n2024-01-06,A,1,234\n"
     b"2024-01-13,A,987\n2024-01-20,A,1,002\n"),
])
def test_a_number_split_into_an_ignored_column_is_refused(raw):
    """An unquoted "1,234" whose second half lands in an ignored column:
    no cell is past the header, so the field count alone missed it."""
    rep = D.validate(raw)
    assert rep.codes == ["split"]
    p = rep.problems[0]
    assert p.rows == (2, 4) and p.kind == "Columns"
    assert "row 2: 1 then 234, likely 1,234" in p.message
    assert "ignored 'comment' column" in p.message
    with pytest.raises(D.DatasetError):
        D.ingest(raw, "cut")
    assert D.list_datasets() == []


def test_a_name_split_into_an_ignored_column_is_refused():
    """'Bern, Stadt' unquoted was stored as the group 'Bern'."""
    raw = (b"date,value,target_group,notes\n2024-01-06,5,Bern, Stadt\n"
           b"2024-01-13,6,Bern, Stadt\n")
    p = only(D.validate(raw), "split")
    assert p.rows == (2, 3)
    assert "row 2: 'Bern' then ' Stadt', likely \"Bern, Stadt\"" in p.message
    # no space after the comma, but a row longer than the others
    raw = (b"date,value,target_group,notes\n2024-01-06,5,Bern,Stadt,\n"
           b"2024-01-13,6,Zug,\n2024-01-20,7,Zug,\n")
    rep = D.validate(raw)
    assert rep.codes == ["extra_fields"] and rep.problems[0].rows == (2,)


def test_short_rows_padding_and_numeric_columns_are_not_splits():
    # a lazy writer: a note on the last row only
    ok(D.validate(b"date,target_group,value,note\n2024-01-06,A,5\n"
                  b"2024-01-13,A,6\n2024-01-20,A,7,ok\n"))
    # every row padded alike, and a stray trailing comma
    ok(D.validate(b"date,target_group,value,notes\n2024-01-06,A,5,x,,\n"
                  b"2024-01-13,A,6,y,,\n2024-01-20,A,7,,,\n"))
    ok(D.validate(b"date,target_group,value\n2024-01-06,A,5,\n"
                  b"2024-01-13,A,6\n"))
    # a numeric column of its own after the value; a note after a space
    ok(D.validate(b"date,target_group,value,beds\n2024-01-06,A,5,120\n"
                  b"2024-01-13,A,6,95\n2024-01-20,A,7,250\n"))
    ok(D.validate(b"date,target_group,value,notes\n2024-01-06,A,5, approx\n"
                  b"2024-01-13,A,6,\n"))
    ok(D.validate(b"date, target_group, value, notes\n2024-01-06, A, 5, rain\n"
                  b"2024-01-13, A, 6, snow\n"))
    # 3 digits after the value on EVERY row: either reading, said aloud
    rep = ok(D.validate(b"date,target_group,value,beds\n2024-01-06,A,5,120\n"
                        b"2024-01-13,A,6,195\n2024-01-20,A,7,250\n"))
    assert any(w.startswith("On every row the 'value' cell is 1 to 3 digits")
               and 'write them as "5,120" or 5120' in w for w in rep.warnings)


#: a stray opening quote in an ignored column: Python's csv reader runs it
#: to the end of the file, and 6 of 8 rows (all of group B) were lost with
#: only the ignored-column notice
STRAY_QUOTE = (b'date,target_group,value,note\n2024-01-06,A,5,\n'
               b'2024-01-13,A,6,"approx\n2024-01-20,A,7,\n2024-01-27,A,8,\n'
               b'2024-01-06,B,1,\n2024-01-13,B,2,\n2024-01-20,B,3,\n'
               b'2024-01-27,B,4,\n')


def test_a_stray_quote_that_swallows_the_rows_below_is_refused():
    rep = D.validate(STRAY_QUOTE)
    assert rep.codes == ["quote"] and rep.problems[0].rows == (3,)
    assert ("row 3's 'note' cell takes in rows 4 to 9, such as "
            "2024-01-20,A,7,") in rep.problems[0].message
    with pytest.raises(D.DatasetError):
        D.ingest(STRAY_QUOTE, "quote")
    assert D.list_datasets() == []
    # closed further down, the rows between are still lost: named too
    p = only(D.validate(b'date,target_group,value,note\n2024-01-06,A,5,\n'
                        b'2024-01-13,A,6,"approx\n2024-01-20,A,7,\n'
                        b'2024-01-27,A,8,x"\n2024-02-03,A,9,\n'), "quote")
    assert "takes in rows 4 to 5" in p.message
    # in a used column, the row itself goes too
    rep = D.validate(b'date,target_group,value\n2024-01-06,A,5\n'
                     b'2024-01-13,"A,6\n2024-01-20,A,7\n2024-01-27,A,8\n')
    assert rep.codes == ["quote"]


def test_a_note_over_two_lines_is_a_note_numbered_by_its_first():
    rep = ok(D.validate(b'date,target_group,value,note\n'
                        b'2024-01-06,A,5,"line1\r\nline2"\n2024-01-13,A,6,\n'))
    assert rep.summary["rows"] == 2
    p = only(D.validate(b'date,target_group,value,note\n'
                        b'2024-01-06,A,x,"line1\nline2"\n2024-01-13,A,6,\n'),
             "value_numeric")
    assert p.rows == (2,)


# ----------------------------------------------------- mixed encodings

def test_utf8_text_with_a_stray_windows_1252_row_is_refused():
    """20 UTF-8 rows 'Zürich' and one appended Windows-1252 row: reading
    the whole file as Windows-1252 once split the group in two ('ZÃ¼rich'
    and 'Zürich') and accepted it."""
    rows = [f"{d.isoformat()},Zürich,{i}".encode()
            for i, d in enumerate(sats("2023-10-07", 20))]
    rows.append(b"2024-02-24,Z\xfcrich,20")
    raw = b"date,target_group,value\n" + b"\n".join(rows) + b"\n"
    rep = D.validate(raw)
    assert rep.codes == ["encoding_mixed"] and rep.problems[0].rows == (22,)
    msg = rep.problems[0].message
    assert "row 22: 2024-02-24,Z�rich,20, byte 0xFC" in msg
    assert "row 2: 2023-10-07,Zürich,0" in msg
    with pytest.raises(D.DatasetError):
        D.ingest(raw, "mixed")


def test_a_stray_byte_in_an_ignored_column_still_refuses_mixed_text():
    """The stray byte sat in an ignored notes column, and every UTF-8 name
    was renamed 'ZÃ¼rich' with only a Windows-1252 notice."""
    rows = [f"{d.isoformat()},Zürich,{i},ok".encode()
            for i, d in enumerate(sats("2020-01-04", 300))]
    rows.append(b"2025-10-04,Z\xc3\xbcrich,1,caf\xe9")
    raw = b"date,target_group,value,notes\n" + b"\n".join(rows) + b"\n"
    rep = D.validate(raw)
    assert rep.codes == ["encoding_mixed"] and rep.problems[0].rows == (302,)
    assert not any("ZÃ" in w for w in rep.warnings)


def test_a_bom_file_with_a_stray_byte_names_its_row():
    raw = (b"\xef\xbb\xbfdate,target_group,value\n2024-01-06,Z\xc3\xbcrich,1\n"
           b"2024-01-13,Z\xfcrich,2\n")
    rep = D.validate(raw)
    assert rep.codes == ["encoding"] and rep.problems[0].rows == (3,)
    msg = rep.problems[0].message
    assert "marked as UTF-8" in msg and "row 3: 2024-01-13,Z�rich,2" in msg
    assert "Save it as CSV UTF-8" not in msg


def test_a_file_with_no_utf8_character_still_reads_as_windows_1252():
    raw = csv_text("date,target_group,value", [
        f"{d.isoformat()},{g},{i}" for g in ("Zürich", "Genève")
        for i, d in enumerate(sats())]).encode("cp1252")
    rep = ok(D.validate(raw))
    assert rep.summary["groups"] == ["Genève", "Zürich"]
    assert rep.warnings[0].startswith("Not UTF-8 text: read as Windows-1252")
    assert "Check these names: Genève, Zürich" in rep.warnings[0]


def test_utf32_is_read_not_taken_for_utf16():
    text = csv_text("date,target_group,value", [
        f"{d.isoformat()},Zürich,{i}" for i, d in enumerate(sats())])
    for codec, name in (("utf-32", "utf-32"), ("utf-32-le", "utf-32-le"),
                        ("utf-32-be", "utf-32-be")):
        raw = text.encode(codec)
        assert D.detect_encoding(raw[:4096]) == name
        rep = ok(D.validate(raw))
        assert rep.summary["groups"] == ["Zürich"]
        assert rep.summary["encoding"] == "UTF-32"


# --------------------------------------------------- rows, kinds, reporting

def test_rows_with_another_separator_are_named_as_such():
    """A semicolon header over comma rows gave four stacked problems (a
    ragged row, a bad date, a missing value and a group '' -> 'group1')."""
    rep = D.validate(b"date;target_group;value\n2024-01-06,A,5\n"
                     b"2024-01-13,A,6\n")
    assert rep.codes == ["separator_mixed"] and rep.problems[0].rows == (2, 3)
    assert ("The header is separated by semicolons but the rows by commas "
            "(rows 2, 3; e.g., row 2: 2024-01-06,A,5).") \
        in rep.problems[0].message
    rep = D.validate(b"date,target_group,value\n2024-01-06;A;5\n")
    assert "separated by commas but the rows by semicolons" \
        in rep.problems[0].message
    rep = D.validate(b"date;target_group;value\n2024-01-06;A;5\n"
                     b"2024-01-13;A;6\n2024-01-20,A,7\n")
    assert rep.codes == ["separator_mixed"]
    assert "1 row(s) are separated by commas, not semicolons like the rest" \
        in rep.problems[0].message


def test_separator_only_rows_and_a_dos_end_mark_are_blank():
    """',,,' was taken for a header ('Found: ,,,'), and a trailing Ctrl-Z
    for a row with four problems."""
    assert D.validate(b"\n\n,,,\n").codes == ["empty"]
    ok(D.validate(b"date,target_group,value\r\n2024-01-06,A,5\r\n"
                  b"2024-01-13,A,6\r\n\x1a"))


def test_a_blank_group_says_blank_and_control_characters_show():
    p = only(D.validate(b"date,target_group,value\n2024-01-06,A,5\n"
                        b"2024-01-13,,6\n2024-01-20,A,7\n"), "group_blank")
    assert ("The 'target_group' column is blank on 1 row(s) (row 3; e.g., "
            "row 3: 2024-01-13, value 6).") in p.message
    rep = D.validate(b"date,target_group,value\n2024-01-06,A,5\n"
                     b"2024-01-13,,6\n")
    assert not any("group1" in str(x) for x in rep.problems)
    # a NUL is shown, not an invisible character
    p = only(D.validate(b"date,target_group,value\n2024-01-06,A,5\x00\n"),
             "value_numeric")
    assert "e.g., 5␀ (2024-01-06, A))" in p.message


def test_every_example_names_its_date_and_group():
    """Some problems quoted a bare cell ('e.g., -1'), a duplicate one of
    its two rows and nothing of their values."""
    raw = (b"date,target_group,value,population\n"
           b"2024-08-03,A,1,100\n2024-08-03,A,2,100\n2024-08-10,A,-3,100\n"
           b"2024-08-17,A,x,0\n2024-08-24,A,4,100\nsoon,B,1,100\n"
           b"2024-08-31\n")
    rep = D.validate(raw)
    msg = {p.code: p.message for p in rep.problems}
    assert "e.g., 2024-08-03 + A (values 1 and 2))" in msg["duplicate"]
    assert "e.g., -3 (2024-08-10, A))" in msg["value_negative"]
    assert "e.g., x (2024-08-17, A))" in msg["value_numeric"]
    assert "e.g., 0 (2024-08-17, A))" in msg["population_invalid"]
    assert "e.g., soon (B))" in msg["date_parse"]
    assert "e.g., row 8: 2024-08-31)" in msg["ragged"]
    p = only(D.validate(raw, kind="count"), "value_numeric")
    assert "x (2024-08-17, A)" in p.message
    # an as_of snapshot's duplicate names its as_of too
    p = only(D.validate(b"target_end_date,location,observation,as_of\n"
                        b"2024-01-06,US,1,2024-01-08\n"
                        b"2024-01-06,US,2,2024-01-08\n"), "duplicate")
    assert ("2024-01-06 + US (as_of 2024-01-08; values 1 and 2)"
            in p.message)
    # an ambiguous number, a day-first date and an as_of that is not one
    p = only(D.validate(b"date;target_group;value\n2024-01-06;A;9\n"
                        b"2024-01-13;A;1.234\n"), "value_format")
    assert "1.234 could be 1234 or 1.234; row 3: 2024-01-13, A)" in p.message
    p = only(D.validate(b"date,target_group,value\n13/01/2024,A,1\n"
                        b"20/01/2024,A,2\n"), "date_day_first")
    assert "e.g., 13/01/2024 (A), 20/01/2024 (A))" in p.message
    p = only(D.validate(b"as_of,target_end_date,location,observation\n"
                        b"soon,2024-01-06,US,1\n"), "as_of_parse")
    assert "e.g., soon (2024-01-06, US))" in p.message


def test_row_numbers_are_the_spreadsheets_rows():
    """Header = row 1; a blank row still counts, as in a spreadsheet."""
    rows = [f"{d.isoformat()},A,{i}" for i, d in enumerate(sats())]
    rows.insert(2, "")
    rows[4] = rows[4].rsplit(",", 1)[0] + ",-3"
    p = only(D.validate(csv_text("date,target_group,value", rows,
                                 end="\r\n").encode()), "value_negative")
    assert p.rows == (6,) and "row 6" in p.message


def test_many_rows_are_summarized():
    rows = [f"{d.isoformat()},A,-1" for d in sats(n=20)]
    p = only(D.validate(csv_text("date,target_group,value", rows).encode()),
             "value_negative")
    assert "rows 2, 3, 4, 5, 6, 7 and 14 more" in p.message
    assert len(p.rows) == 20


def test_every_problem_names_rows_and_groups_by_kind():
    rows = [f"{d.isoformat()},A,{i}" for i, d in enumerate(sats())]
    rows += ["2024-08-12,B,1", "soon,B,2", "2024-08-24,B/C,x",
             "2024-08-31,A,-1", rows[0]]
    rep = D.validate(csv_text("date,target_group,value", rows).encode())
    assert {"weekday", "date_parse", "value_numeric", "value_negative",
            "group_name", "duplicate"} <= set(rep.codes)
    for p in rep.problems:
        assert p.rows and "row" in p.message and "e.g." in p.message, p
    kinds = [k for k, _ in D.problem_groups(rep.problems)]
    assert kinds == ["Dates", "Values", "Groups", "Weeks"]
    assert D.problem_groups([]) == []


def test_undeclared_kind_is_inferred_and_recorded():
    ds = D.ingest(TPL, "tpl")
    assert ds.kind == "count" and ds.meta["options"]["kind_from"] == "values"
    rows = [f"{d.isoformat()},A,{i}.25" for i, d in enumerate(sats())]
    ds = D.ingest(csv_text("date,target_group,value", rows).encode(), "r", kind="")
    assert ds.kind == "rate" and not ds.pf_eligible
    ds = D.ingest(TPL, "declared", kind="rate")
    assert ds.meta["options"]["kind_from"] == "declared"


def test_ids_of_files_the_earlier_reader_accepted_do_not_change():
    """The same bytes and options mint the same id as before lenient
    reading (a run pinning a dataset keeps resolving it); an inferred kind
    equal to the declared one is the same dataset."""
    assert D.ingest(TPL, "Grouped Template", kind="count").id == \
        "grouped-template-cbcc64262fc3"
    assert D.ingest(TPL, "Grouped Template").id == \
        "grouped-template-cbcc64262fc3"
    assert D.ingest(TPL_POP, "Kids", kind="count").id == "kids-4b5adeebc6ea"
    assert D.ingest(TPL_POP, "Kids", kind="rate").id == "kids-5d027ea655b4"
    sun = b"date,target_group,value\n2024-07-28,A,1\n2024-08-04,A,2\n"
    assert D.ingest(sun, "sun").id == "sun-113cc4fb1cab"
    assert len(D.list_datasets()) == 4


def test_two_as_of_columns_are_refused_not_mapped():
    """A mapping names the four roles only, so a doubled extra column is a
    plain problem, not a mapping step."""
    rows = [f"{d.isoformat()},A,1,2024-10-05,2024-10-05" for d in sats()]
    rep = D.validate(csv_text("date,group,value,as_of,As Of", rows).encode())
    assert rep.codes == ["duplicate_columns"] and not rep.needs_mapping
    assert "Two columns could be the as_of" in rep.problems[0].message
