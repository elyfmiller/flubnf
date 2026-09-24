"""Custom datasets (app/core/datasets.py): parse, validate, store, adapt.

Fixtures: the first ten weeks of FluBNF's synthetic template
(app/ui/static/dataset-template.csv) in app/tests/fixtures, one in the
bytes a spreadsheet's "CSV UTF-8" export writes (BOM, CRLF, M/D/YY dates)
and one with populations; hubverse-shaped CSVs are built inline. No hub,
no engine, no network: runs with FLUBNF_HUB=/nonexistent.
"""
from __future__ import annotations

import csv
import io
import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.core import datasets as D

FIX = Path(__file__).resolve().parent / "fixtures"
TPL = FIX / "grouped-template-head.csv"
TPL_POP = FIX / "grouped-template-population-head.csv"
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _store_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")


def sats(start="2024-08-03", n=10, step=7):
    d0 = date.fromisoformat(start)
    return [d0 + timedelta(days=step * i) for i in range(n)]


def grouped_csv(rows, header="date,target_group,value") -> bytes:
    return (header + "\n" + "\n".join(rows) + "\n").encode()


def grouped_series(groups=("A", "B"), n=6, start="2024-08-03", pop=False):
    out = []
    for i, d in enumerate(sats(start, n)):
        for j, g in enumerate(groups):
            row = f"{d.isoformat()},{g},{10 * (j + 1) + i}"
            out.append(row + (f",{1000 * (j + 1)}" if pop else ""))
    return out


def hub_csv(rows, header="as_of,target,target_end_date,location,"
            "location_name,observation") -> bytes:
    return (header + "\n" + "\n".join(rows) + "\n").encode()


def ok(rep):
    assert rep.ok, [str(p) for p in rep.problems]
    return rep


def only(rep, code):
    assert code in rep.codes, [str(p) for p in rep.problems]
    return next(p for p in rep.problems if p.code == code)


# ------------------------------------------------------------ grouped files

def test_fixture_keeps_a_spreadsheets_byte_shape():
    raw = TPL.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbfdate,target_group,value\r\n")
    assert b"1/1/22,Pediatric,57\r\n" in raw


def test_fixtures_are_the_synthetic_templates_first_ten_weeks():
    tpl = (REPO / "app" / "ui" / "static" / "dataset-template.csv"
           ).read_text().splitlines()
    assert TPL_POP.read_text().splitlines() == tpl[:31]
    assert TPL.read_bytes().decode("utf-8-sig").splitlines() == [
        ",".join(r.split(",")[:3]) for r in tpl[:31]]
    weeks = {}
    for r in csv.DictReader(io.StringIO("\n".join(tpl))):
        weeks.setdefault(r["date"], {})[r["target_group"]] = int(r["value"])
    assert len(weeks) == 143
    assert all(w["Overall"] == w["Pediatric"] + w["Adult"]
               for w in weeks.values())


def test_the_template_and_slices_are_what_the_generator_writes():
    from scripts import make_dataset_template as M
    built = M.build()
    assert sorted(built) == sorted([M.TEMPLATE, M.SLICE, M.SLICE_POP])
    for rel, data in built.items():
        assert (REPO / rel).read_bytes() == data, rel
    assert (REPO / M.SLICE) == TPL and (REPO / M.SLICE_POP) == TPL_POP


def test_grouped_template_validates_bom_crlf_mdyy():
    rep = ok(D.validate(TPL, kind="count"))
    s = rep.summary
    assert s["format"] == "grouped"
    assert s["groups"] == ["Adult", "Overall", "Pediatric"]
    assert s["first"] == "2022-01-01" and s["weeks"] == 10
    assert s["has_population"] is False and s["has_as_of"] is False
    assert s["inferred_kind"] == "count"
    assert rep.columns["date"] == "date"          # BOM stripped from header


def test_grouped_population_template_ingests():
    ds = D.ingest(TPL_POP, "Grouped template", kind="count")
    assert ds.has_population and ds.pf_eligible and not ds.has_as_of
    assert ds.populations == {"Adult": 5236907, "Overall": 6989325,
                              "Pediatric": 1752418}
    assert ds.source_path.read_bytes() == TPL_POP.read_bytes()
    assert ds.vintages() == ["2022-03-05"]


# -------------------------------------------------------------- date rules

@pytest.mark.parametrize("text", ["2024-08-03", "8/3/2024", "08/03/2024",
                                  "8/3/24", "08-03-2024", "8-3-2024",
                                  "2024/08/03", "2024-08-03 00:00:00",
                                  "2024-08-03T00:00:00Z", "8/3/2024 0:00",
                                  "8/3/2024 12:00 AM"])
def test_accepted_date_formats(text):
    assert D.parse_date(text)[0] == date(2024, 8, 3)


@pytest.mark.parametrize("text", ["13/01/2024", "3 Aug 2024",
                                  "2024-02-30", "", "20240803",
                                  "2024-08-03 noon"])
def test_rejected_date_formats(text):
    assert D.parse_date(text) == (None, None)


def test_each_format_validates_as_a_column():
    for fmt in ("{d:%Y-%m-%d}", "{d.month}/{d.day}/{d:%Y}",
                "{d.month}/{d.day}/{d:%y}", "{d:%m-%d-%Y}"):
        rows = [f"{fmt.format(d=d)},A,{i}" for i, d in enumerate(sats())]
        rep = ok(D.validate(grouped_csv(rows), kind="count"))
        assert rep.summary["first"] == "2024-08-03"


def test_bom_is_tolerated_on_any_file():
    ok(D.validate(b"\xef\xbb\xbf" + grouped_csv(grouped_series()),
                  kind="count"))


def test_mixed_weekdays_are_refused_with_rows_and_examples():
    rows = [f"{d.isoformat()},A,1" for d in sats()]
    rows[3] = f"{(sats()[3] + timedelta(days=1)).isoformat()},A,1"
    p = only(D.validate(grouped_csv(rows), kind="count"), "weekday")
    assert "most are Saturdays, but 1 Sunday" in p.message
    assert "row 5" in p.message and "e.g., 2024-08-25 (Sunday)" in p.message
    assert p.rows == (5,)


def test_sunday_shift_moves_week_start_to_saturday():
    """A consistent Sunday file moves +6 days by itself; the old Sunday
    option is still accepted and changes nothing."""
    rows = [f"{(d - timedelta(days=6)).isoformat()},A,{i}"
            for i, d in enumerate(sats())]
    for sunday in (False, True):
        rep = ok(D.validate(grouped_csv(rows), kind="count",
                            week_start_sunday=sunday))
        assert rep.summary["first"] == "2024-08-03"
        assert rep.warnings[0].startswith(
            "Dates moved to week-ending Saturdays: +6 days")
    ds = D.ingest(grouped_csv(rows), "sun", kind="count",
                  week_start_sunday=True)
    assert ds.vintages() == [sats()[-1].isoformat()]
    assert ds.meta["options"]["date_shift_days"] == 6


def test_the_old_sunday_option_no_longer_refuses_saturdays():
    rep = ok(D.validate(grouped_csv(grouped_series()), kind="count",
                        week_start_sunday=True))
    assert rep.summary["first"] == "2024-08-03"
    assert rep.summary["date_shift_days"] == 0 and not rep.warnings


# --------------------------------------------------------- the base checks

def test_missing_columns_stops_early_and_names_them():
    rep = D.validate(b"day,target_group,amount\n2024-08-03,A,1\n")
    p = only(rep, "missing_columns")
    assert "date" in p.message and "value" in p.message
    assert rep.codes == ["missing_columns"]
    assert rep.needs_mapping and rep.headers == ["day", "target_group",
                                                 "amount"]


def test_unparseable_dates():
    rows = grouped_series() + ["yesterday,A,3", "2024-13-01,A,3"]
    p = only(D.validate(grouped_csv(rows), kind="count"), "date_parse")
    assert "yesterday" in p.message and "2 value(s)" in p.message


def test_value_non_numeric_negative_and_na():
    rows = grouped_series(n=6)
    rows[0] = rows[0].rsplit(",", 1)[0] + ",lots"
    rows[1] = rows[1].rsplit(",", 1)[0] + ",-4"
    rows[2] = rows[2].rsplit(",", 1)[0] + ",NA"
    rows[3] = rows[3].rsplit(",", 1)[0] + ","
    rep = D.validate(grouped_csv(rows), kind="count")
    assert "lots" in only(rep, "value_numeric").message
    assert "-4" in only(rep, "value_negative").message
    msg = only(rep, "value_na").message
    assert "blank or NA on 2 row(s)" in msg
    # each example is the cell as written, with its date and group
    assert "e.g., NA (2024-08-10, A), (blank) (2024-08-10, B))" in msg


def test_duplicate_date_group():
    rows = grouped_series() + [grouped_series()[0]]
    p = only(D.validate(grouped_csv(rows), kind="count"), "duplicate")
    assert "2024-08-03 + A" in p.message


def test_gap_over_eight_days_within_a_group():
    rows = [r for r in grouped_series() if not r.startswith("2024-08-17,A")]
    p = only(D.validate(grouped_csv(rows), kind="count"), "gap")
    assert "2024-08-10 and 2024-08-24" in p.message and "'A'" in p.message


def test_every_problem_is_reported_at_once_and_nothing_is_written():
    rows = grouped_series() + ["2024-08-05,A,1", "2024-08-03,A,-1",
                               "bad,B,2", "2024-09-07,Bad/Name,3"]
    rep = D.validate(grouped_csv(rows), kind="count")
    assert {"weekday", "value_negative", "date_parse", "group_name",
            "duplicate"} <= set(rep.codes)
    assert all("e.g." in p.message for p in rep.problems)
    with pytest.raises(D.DatasetError) as e:
        D.ingest(grouped_csv(rows), "bad", kind="count")
    assert e.value.problems
    assert D.list_datasets() == []
    assert [p.name for p in D.ROOT.iterdir()] == []   # temp folder removed


# ------------------------------------------------------- FluBNF's checks

def test_kind_must_be_declared_for_ingest_and_counts_must_be_whole():
    with pytest.raises(D.DatasetError):
        D.ingest(grouped_csv(grouped_series()), "x", kind="percent")
    assert "kind_invalid" in D.validate(grouped_csv(grouped_series()),
                                        kind="percent").codes
    rows = [f"{d.isoformat()},A,{i + 0.5}" for i, d in enumerate(sats())]
    only(D.validate(grouped_csv(rows), kind="count"), "value_not_integer")
    rep = ok(D.validate(grouped_csv(rows), kind="rate"))
    assert rep.summary["inferred_kind"] == "rate"


def test_rate_datasets_carry_no_weekly_rate():
    rows = [f"{d.isoformat()},A,{i + 0.5},100" for i, d in enumerate(sats())]
    ds = D.ingest(grouped_csv(rows, "date,target_group,value,population"),
                  "r", kind="rate")
    got = list(csv.DictReader(open(ds.final_path)))
    assert got[0]["value"] == "0.5" and got[0]["weekly_rate"] == ""
    assert not ds.pf_eligible


@pytest.mark.parametrize("name", ["Kids/Teens", "_x", "a" * 41,
                                  "a-b", "a.b", "Niños/Niñas"])
def test_group_name_charset(name):
    rows = [f"{d.isoformat()},{name},1" for d in sats()]
    p = only(D.validate(grouped_csv(rows), kind="count"), "group_name")
    assert "->" in p.message                           # a suggested rename
    assert "row 2" in p.message and p.rows == (2,)


@pytest.mark.parametrize("name", ["Niños", "Åland", "Zürich 0 4", "東京"])
def test_letters_of_any_script_are_group_names(name):
    rows = [f"{d.isoformat()},{name},1" for d in sats()]
    ds = D.ingest(grouped_csv(rows), "intl", kind="count")
    assert ds.groups == [name]
    assert list(csv.DictReader(open(ds.final_path, encoding="utf-8"))
                )[0]["location_name"] == name


@pytest.mark.parametrize("name", ["All", "all", "ALL"])
def test_reserved_group_names(name):
    rows = [f"{d.isoformat()},{name},1" for d in sats()]
    only(D.validate(grouped_csv(rows), kind="count"), "group_reserved")


@pytest.mark.parametrize("name", ["US", "usa", "United States",
                                  "US (national)", "National", "national"])
def test_a_national_group_is_accepted_and_flagged(name):
    rows = grouped_series(groups=("Adult", name))
    rep = ok(D.validate(grouped_csv(rows), kind="count"))
    assert rep.summary["national_group"] == name
    ds = D.ingest(grouped_csv(rows), "nat", kind="count")
    assert ds.national_group == name and ds.meta["national_group"] == name
    g = {x["name"]: x for x in ds.meta["groups"]}
    assert g[name]["national"] is True and g["Adult"]["national"] is False
    # a minted key like every group: never FluSight's literal 'US'
    assert ds.name2key[name].startswith("c")
    assert "US" not in {r["location"] for r in csv.DictReader(
        open(ds.locations_csv))}


def test_two_national_spellings_are_refused():
    rows = grouped_series(groups=("US", "National"))
    p = only(D.validate(grouped_csv(rows), kind="count"), "national_multiple")
    assert "'National'" in p.message and "'US'" in p.message


def test_no_national_group_is_recorded_as_none():
    ds = D.ingest(TPL, "tpl", kind="count")
    assert ds.national_group is None
    assert all(g["national"] is False for g in ds.meta["groups"])


@pytest.mark.parametrize("a,b", [("Age 0", "Age_0"), ("Adult", "adult"),
                                 ("Age 0", "age_0")])
def test_group_names_colliding_after_underscore_or_casefold(a, b):
    rows = grouped_series(groups=(a, b))
    p = only(D.validate(grouped_csv(rows), kind="count"), "group_collision")
    assert a in p.message and b in p.message


def test_population_rules():
    h = "date,target_group,value,population"
    rows = grouped_series(pop=True)
    rows[0] = rows[0].rsplit(",", 1)[0] + ",0"
    rows[1] = rows[1].rsplit(",", 1)[0] + ","
    rows[2] = rows[2].rsplit(",", 1)[0] + ",many"
    rep = D.validate(grouped_csv(rows, h), kind="count")
    assert "2 value(s)" in only(rep, "population_invalid").message
    only(rep, "population_missing")


def test_population_varying_by_date_keeps_the_latest_and_the_series():
    h = "date,target_group,value,population"
    rows = [f"{d.isoformat()},A,5,{1000 + i}" for i, d in enumerate(sats())]
    rep = ok(D.validate(grouped_csv(rows, h), kind="count"))
    assert any("varies" in w for w in rep.warnings)
    ds = D.ingest(grouped_csv(rows, h), "pop", kind="count")
    assert ds.populations == {"A": 1009}
    assert ds.meta["groups"][0]["population_varies"] is True
    ser = ds.population_series("A")
    assert ser[0] == ("2024-08-03", 1000.0) and ser[-1][1] == 1009.0
    loc = list(csv.DictReader(open(ds.locations_csv)))
    assert loc[0]["population"] == "1009"


def test_ignored_columns_are_named():
    rows = [f"{d.isoformat()},01,Alabama,5,0.1" for d in sats()]
    rep = ok(D.validate(hub_csv(rows, "date,location,location_name,value,"
                                "weekly_rate"), kind="count"))
    assert any("weekly_rate" in w for w in rep.warnings)
    assert rep.summary["format"] == "hubverse"
    assert rep.summary["groups"] == ["Alabama"]


def test_both_group_columns_is_ambiguous():
    rep = D.validate(b"date,target_group,location,value\n2024-08-03,A,01,1\n")
    assert rep.codes == ["ambiguous_columns"]


def test_empty_and_non_utf8_files():
    assert D.validate(b"").codes == ["empty"]
    assert D.validate(b"date,target_group,value\n").codes == ["empty"]
    # not UTF-8: read as Windows-1252, the name kept, and said so
    rep = ok(D.validate(b"date,target_group,value\n2024-08-03,Ni\xf1os,1\n"))
    assert rep.summary["groups"] == ["Niños"]
    assert rep.warnings[0].startswith("Not UTF-8 text: read as Windows-1252")
    # a BOM declares UTF-8: bytes that are not stay an encoding problem
    rep = D.validate(b"\xef\xbb\xbfdate,target_group,value\n"
                     b"2024-08-03,Ni\xf1os,1\n")
    assert rep.codes == ["encoding"]


def test_ragged_rows_are_reported():
    rows = grouped_series() + ["2024-10-12,A"]
    only(D.validate(grouped_csv(rows), kind="count"), "ragged")


# ---------------------------------------------------------------- limits

class _Endless(io.RawIOBase):
    """A header then valid rows forever: proves limits stop the stream."""

    def __init__(self, groups=1):
        self.buf = b"date,target_group,value\n"
        self.i, self.groups, self.read_bytes = 0, groups, 0

    def readable(self):
        return True

    def readinto(self, b):
        while len(self.buf) < len(b):
            d = date(2000, 1, 1) + timedelta(days=7 * (self.i // self.groups))
            g = f"G{self.i % self.groups}" if self.groups > 1 else "A"
            self.buf += f"{d.isoformat()},{g},1\n".encode()
            self.i += 1
        n = len(b)
        b[:n], self.buf = self.buf[:n], self.buf[n:]
        self.read_bytes += n
        return n


def test_byte_limit_stops_the_stream():
    src = _Endless()
    rep = D.validate(src, limits=D.Limits(max_bytes=50_000))
    assert rep.codes == ["limit_bytes"]
    assert src.read_bytes < 50_000 + 65_536


def test_row_limit():
    rep = D.validate(_Endless(), limits=D.Limits(max_rows=100))
    assert rep.codes == ["limit_rows"]


def test_group_limit():
    rep = D.validate(_Endless(groups=10_000), limits=D.Limits(max_groups=5))
    assert rep.codes == ["limit_groups"]


def test_limits_refuse_ingest_and_write_nothing():
    with pytest.raises(D.DatasetError) as e:
        D.ingest(TPL, "big", kind="count", limits=D.Limits(max_bytes=100))
    assert [p.code for p in e.value.problems] == ["limit_bytes"]
    assert D.list_datasets() == []


# ------------------------------------------------------------- hubverse

def _snapshot(as_of, weeks, target="wk inc flu hosp", bump=0):
    rows = []
    for i, d in enumerate(weeks):
        rows.append(f"{as_of},{target},{d.isoformat()},01,Alabama,{10 + i + bump}")
        rows.append(f"{as_of},{target},{d.isoformat()},02,Alaska,{3 + i}")
    return rows


def test_as_of_vintages_map_to_saturday_keys_latest_wins():
    w = sats("2025-05-03", 12)                   # through 2025-07-19
    rows = (_snapshot("2025-06-28", [d for d in w if d <= date(2025, 6, 28)])
            + _snapshot("2025-07-19", w, bump=100)
            + _snapshot("2025-07-23", w, bump=200))     # Wednesday
    ds = D.ingest(hub_csv(rows), "hub", kind="count")
    assert ds.has_as_of
    assert ds.vintages() == ["2025-06-28", "2025-07-19"]
    assert ds.meta["as_of_map"]["2025-07-19"] == ["2025-07-19", "2025-07-23"]
    assert ds.meta["as_of_used"]["2025-07-19"] == "2025-07-23"
    early = list(csv.DictReader(open(ds.vintage_path("2025-06-28"))))
    late = list(csv.DictReader(open(ds.vintage_path("2025-07-19"))))
    assert max(r["date"] for r in early) == "2025-06-28"
    al = [r for r in late if r["location_name"] == "Alabama"]
    assert al[0]["value"] == "210"               # the Wednesday snapshot
    assert ds.final_path == ds.vintage_path("2025-07-19")


def test_snapshot_holding_a_week_after_its_as_of_is_refused():
    rows = _snapshot("2025-06-25", sats("2025-06-07", 4))  # 06-28 > 06-25
    p = only(D.validate(hub_csv(rows), kind="count"), "as_of_before_date")
    assert "2025-06-28 in as_of 2025-06-25" in p.message


def test_duplicates_and_gaps_are_per_snapshot():
    w = sats("2025-05-03", 6)
    rows = _snapshot("2025-06-07", w) + _snapshot("2025-06-14", w)
    ok(D.validate(hub_csv(rows), kind="count"))      # same weeks, two as_ofs
    rows2 = rows + [rows[0]]
    only(D.validate(hub_csv(rows2), kind="count"), "duplicate")
    rows3 = [r for r in rows if not r.startswith("2025-06-14,wk inc flu hosp,"
                                                 "2025-05-17,01")]
    p = only(D.validate(hub_csv(rows3), kind="count"), "gap")
    assert "as_of 2025-06-14" in p.message


def test_bad_as_of_dates():
    rows = _snapshot("someday", sats("2025-05-03", 3))
    only(D.validate(hub_csv(rows), kind="count"), "as_of_parse")


def test_multi_target_needs_a_choice():
    w = sats("2025-05-03", 4)
    rows = _snapshot("2025-05-24", w) + _snapshot(
        "2025-05-24", w, target="wk inc flu prop ed visits")
    p = only(D.validate(hub_csv(rows), kind="count"), "target_required")
    assert "wk inc flu hosp" in p.message and "prop ed visits" in p.message
    rep = ok(D.validate(hub_csv(rows), kind="count",
                        target="wk inc flu hosp"))
    assert rep.summary["target"] == "wk inc flu hosp"
    assert rep.summary["rows"] == 8
    only(D.validate(hub_csv(rows), kind="count", target="nope"),
         "target_unknown")
    only(D.validate(grouped_csv(grouped_series()), kind="count", target="x"),
         "target_unknown")


def test_location_name_must_be_one_to_one():
    rows = [f"{d.isoformat()},01,Alabama,5" for d in sats()]
    rows[0] = rows[0].replace("Alabama", "Alabamaa")
    only(D.validate(hub_csv(rows, "date,location,location_name,value"),
                    kind="count"), "location_name_conflict")


def test_hub_national_row_is_the_datasets_national_group():
    rows = [f"{d.isoformat()},US,US,5" for d in sats()] + [
        f"{d.isoformat()},01,Alabama,2" for d in sats()]
    raw = hub_csv(rows, "target_end_date,location,location_name,observation")
    rep = ok(D.validate(raw, kind="count"))
    assert rep.summary["national_group"] == "US"
    ds = D.ingest(raw, "hub", kind="count")
    loc = {r["location_name"]: r for r in csv.DictReader(open(ds.locations_csv))}
    assert loc["US"]["source_key"] == "US" and loc["US"]["location"] != "US"


def test_national_key_with_another_name_is_national():
    rows = [f"{d.isoformat()},US,Whole country,5" for d in sats()]
    rep = ok(D.validate(hub_csv(rows, "date,location,location_name,value"),
                        kind="count"))
    assert rep.summary["national_group"] == "Whole country"


def test_hubverse_na_rows_are_dropped_counted_and_recorded():
    w = sats("2025-05-03", 6)
    rows = _snapshot("2025-06-07", w)
    rows[2] = rows[2].rsplit(",", 1)[0] + ",NA"
    rows[5] = rows[5].rsplit(",", 1)[0] + ","
    rep = ok(D.validate(hub_csv(rows), kind="count"))
    assert "2 row(s) with no value were dropped." in rep.warnings
    assert rep.summary["na_dropped"] == 2 and rep.summary["rows"] == 10
    ds = D.ingest(hub_csv(rows), "na", kind="count")
    assert ds.meta["na_dropped"] == 2
    assert "2 row(s) with no value were dropped." in ds.meta["warnings"]
    got = list(csv.DictReader(open(ds.final_path)))
    assert len(got) == 10 and all(r["value"] for r in got)


def test_hubverse_na_rows_do_not_count_as_gaps():
    """The NA row still marks its week as present in the file."""
    w = sats("2025-05-03", 6)
    rows = _snapshot("2025-06-07", w)
    rows[4] = rows[4].rsplit(",", 1)[0] + ",NA"        # a middle Alabama week
    rep = ok(D.validate(hub_csv(rows), kind="count"))
    assert rep.summary["na_dropped"] == 1


def test_grouped_na_stays_an_error():
    rows = grouped_series()
    rows[0] = rows[0].rsplit(",", 1)[0] + ",NA"
    rep = D.validate(grouped_csv(rows), kind="count")
    only(rep, "value_na")
    assert not any("dropped" in w for w in rep.warnings)


def test_headers_are_case_and_space_insensitive():
    rows = [f"{d.isoformat()},01,5" for d in sats()]
    rep = ok(D.validate(hub_csv(rows, " Target_End_Date ,LOCATION,Observation"),
                        kind="count"))
    assert rep.summary["groups"] == ["01"]


# ------------------------------------------------------------- adapters

def test_locations_table_has_the_hub_shape_and_safe_keys():
    names = [f"G{i}" for i in range(12)]
    ds = D.ingest(grouped_csv(grouped_series(groups=names, pop=True),
                              "date,target_group,value,population"),
                  "many", kind="count")
    hub_cols = open(REPO / "flubnf" / "data" / "locations.csv"
                    ).readline().strip().replace('"', "").split(",")
    got = list(csv.DictReader(open(ds.locations_csv)))
    assert list(got[0])[:4] == hub_cols[:4]
    fips = {r["location"] for r in csv.DictReader(
        open(REPO / "flubnf" / "data" / "locations.csv"))}
    keys = [r["location"] for r in got]
    assert len(set(keys)) == len(names)
    for k in keys:
        assert k.zfill(2) == k and not k.isdigit()
        assert k not in fips and k.upper() != "US"
    assert {r["location_name"]: r["source_key"] for r in got}["G3"] == "G3"


def test_minted_keys_stay_unique_past_99_groups():
    rows = [f"2024-08-03,G{i},1" for i in range(150)]
    ds = D.ingest(grouped_csv(rows), "wide", kind="count")
    keys = list(ds.name2key.values())
    assert len(set(keys)) == 150 and all(len(k) == 4 for k in keys)


def test_vintage_file_has_the_archive_shape_and_reads_like_one():
    ds = D.ingest(TPL_POP, "tpl", kind="count")
    p = ds.final_path
    assert p.name == "target-hospital-admissions_2022-03-05.csv"
    assert open(p).readline().strip() == \
        "date,location,location_name,value,weekly_rate"
    # the data.load_vintage recipe
    import pandas as pd
    df = pd.read_csv(p, dtype={"location": str})
    df["location"] = df["location"].str.zfill(2)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    assert len(df[df["value"].notna()]) == 30
    # the Groundhog/Oracle reader
    from flubnf.oracle_bank import load_rows
    rows = load_rows(p, date(2022, 2, 5))
    assert {r.location for r in rows} == {"c01", "c02", "c03"}
    assert max(r.date for r in rows) == date(2022, 2, 5)


def test_sihrs_resolve_state_reads_the_dataset_with_no_hub():
    from flubnf.sihrs_fit import resolve_state
    ds = D.ingest(TPL_POP, "tpl", kind="count")
    st = resolve_state("Pediatric", truth_csv=ds.final_path,
                       locations_csv=ds.locations_csv,
                       season_start="2022-01-01", as_of="2022-01-29")
    assert st.population == 1752418 and st.fips == "c03"
    assert list(st.observed) == [57.0, 65.0, 68.0, 71.0, 62.0]


def test_unversioned_dataset_has_one_final_vintage():
    ds = D.ingest(TPL, "tpl", kind="count")
    assert ds.vintages() == ["2022-03-05"]
    with pytest.raises(FileNotFoundError) as e:
        ds.vintage_path("2022-02-26")
    assert "Nearby: ['2022-03-05']" in str(e.value)
    with pytest.raises(FileNotFoundError):
        ds.vintage_path("../../etc/passwd")
    assert ds.reference_dates()[0] == "2022-01-08"
    assert len(ds.reference_dates()) == 9


def test_series_csv_keeps_every_row():
    ds = D.ingest(TPL_POP, "tpl", kind="count")
    rows = list(csv.DictReader(open(ds.series_path)))
    assert len(rows) == 30
    assert list(rows[0]) == ["as_of", "date", "location", "location_name",
                             "source_key", "value", "population"]


def test_meta_records_the_ingest():
    ds = D.ingest(TPL_POP, "My Data!", kind="count", filename="x.csv")
    m = ds.meta
    for k in ("name", "id", "digest", "columns", "groups", "date_range",
              "kind", "has_population", "has_as_of", "created"):
        assert k in m
    assert m["date_range"] == ["2022-01-01", "2022-03-05"]
    assert m["columns"]["group"] == "target_group"
    assert m["groups"][0] == {"name": "Adult", "key": "c01",
                              "source_key": "Adult", "population": 5236907,
                              "population_varies": False, "rows": 10,
                              "first": "2022-01-01", "last": "2022-03-05",
                              "national": False}
    assert m["national_group"] is None and m["na_dropped"] == 0
    assert ds.ref() == {"id": ds.id, "digest": m["digest"][:16],
                        "name": "My Data!"}


# ---------------------------------------------------- identity and store

def test_id_is_stable_and_idempotent():
    a = D.ingest(TPL, "Grouped Template", kind="count")
    b = D.ingest(TPL.read_bytes(), "Grouped Template", kind="count")
    assert a.id == b.id and a.id.startswith("grouped-template-")
    assert D.ID_RE.fullmatch(a.id)
    assert len(D.list_datasets()) == 1
    assert a.meta["created"] == b.meta["created"]


def test_id_covers_ingest_options_and_name():
    a = D.ingest(TPL, "t", kind="count")
    b = D.ingest(TPL, "t", kind="rate")
    c = D.ingest(TPL, "u", kind="count")
    assert len({a.id, b.id, c.id}) == 3
    assert a.meta["digest"] != b.meta["digest"]
    assert a.meta["digest"] == c.meta["digest"]
    assert a.meta["sha256"] == b.meta["sha256"]


def test_id_slug_is_path_safe():
    ds = D.ingest(TPL, "../../etc/passwd", kind="count")
    assert ds.id.startswith("etc-passwd-") and ds.path.parent == D.ROOT.resolve()
    ds2 = D.ingest(TPL, "!!!", kind="count")
    assert ds2.id.startswith("dataset-")


def test_list_get_delete():
    ds = D.ingest(TPL, "one", kind="count")
    (D.ROOT / ".tmp-stale").mkdir()
    (D.ROOT / "not-a-dataset").mkdir()
    assert [d.id for d in D.list_datasets()] == [ds.id]
    assert D.get(ds.id).meta == ds.meta
    D.delete(ds.id)
    assert not ds.path.exists() and D.list_datasets() == []
    with pytest.raises(D.DatasetError):
        D.get(ds.id)
    with pytest.raises(D.DatasetError):
        D.delete(ds.id)


@pytest.mark.parametrize("bad", ["..", "../x", "a/b", "/etc", "", None,
                                 "x-0123456789ab/../..", ".tmp-stale",
                                 "UPPER-0123456789ab", "x-0123456789ab\n"])
def test_delete_and_get_refuse_bad_ids(bad):
    with pytest.raises(D.DatasetError):
        D.delete(bad)
    with pytest.raises(D.DatasetError):
        D.get(bad)


def test_delete_refuses_a_symlink_out_of_the_store(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "meta.json").write_text("{}")
    D.ROOT.mkdir(parents=True)
    link = D.ROOT / "evil-0123456789ab"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks here")
    with pytest.raises(D.DatasetError):
        D.delete("evil-0123456789ab")
    assert (outside / "meta.json").is_file()


def test_resolve_pins_the_digest():
    ds = D.ingest(TPL, "one", kind="count")
    assert D.resolve(None) is None
    assert D.resolve(ds.ref()).id == ds.id
    with pytest.raises(D.DatasetError):
        D.resolve({**ds.ref(), "digest": "0" * 16})
    D.delete(ds.id)
    with pytest.raises(D.DatasetError):
        D.resolve(ds.ref())


def test_saturday_on_or_before():
    assert D.saturday_on_or_before(date(2025, 7, 19)) == date(2025, 7, 19)
    assert D.saturday_on_or_before(date(2025, 7, 23)) == date(2025, 7, 19)
    assert D.saturday_on_or_before(date(2025, 7, 20)) == date(2025, 7, 19)
