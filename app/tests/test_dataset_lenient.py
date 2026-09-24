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
    assert "1 Monday" in p.message and "1 Sunday" in p.message


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


# --------------------------------------------------------------- separators

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
    (["1,000", "1,200"], ";", "1,000 could be 1000 or 1.000"),
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


def test_a_population_column_is_read_on_its_own_style():
    rows = [f"{d.isoformat()};A;{10 + i};1,500" for i, d in enumerate(sats())]
    rep = D.validate(csv_text("date;target_group;value;population",
                              rows).encode())
    only(rep, "population_format")


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
    rep = ok(D.validate(csv_text("date,target_group,value,notes",
                                 rows).encode()))
    rows[2] = "2024-08-17,A"                     # lacks the value
    p = only(D.validate(csv_text("date,target_group,value,notes",
                                 rows).encode()), "ragged")
    assert p.rows == (4,)


# --------------------------------------------------- rows, kinds, reporting

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
