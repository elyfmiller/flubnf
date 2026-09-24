"""A folder of snapshot files as one vintage-true dataset
(datasets.validate_snapshots / ingest_snapshots, the upload box's several
files, the Retrospective tab's Your data).

Each file is a normal weekly table read by the one lenient reader; its
as_of comes from an as_of column inside it, else from the one date its
name carries. The files are stored exactly as one CSV holding the same
rows with an as_of column would be. A single file behaves as before.

fixtures/snapshots: the template's three groups, 2023-01-07 on, as 8
weekly snapshots named as the hub archive names them, each holding the
weeks up to the Saturday before its as_of, its newest two weeks revised.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from app.core import datasets as D

from test_datasets_ui import client, isolated  # noqa: F401

SNAPS = Path(__file__).resolve().parent / "fixtures" / "snapshots"
FILES = sorted(SNAPS.iterdir())
ASOFS = ["2023-11-04", "2023-11-11", "2023-11-18", "2023-11-25",
         "2023-12-02", "2023-12-09", "2023-12-16", "2023-12-23"]


def snaps(folder="flu"):
    """The fixture as (filename, bytes), each named with its folder."""
    return [(f"{folder}/{p.name}", p.read_bytes()) for p in FILES]


def as_of_csv() -> bytes:
    """The same snapshots as ONE CSV with an as_of column."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["as_of", "date", "target_group", "value", "population"])
    for p in FILES:
        a = D.name_dates(p.name)[0].isoformat()
        for r in csv.DictReader(io.StringIO(p.read_text())):
            w.writerow([a, r["date"], r["target_group"], r["value"],
                        r["population"]])
    return buf.getvalue().encode()


def text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def only(rep, code):
    assert rep.codes == [code], [str(p) for p in rep.problems]
    return rep.problems[0]


# ------------------------------------------------------------------ names

def test_the_as_of_in_a_file_name():
    for name in ("2024-10-05.csv", "admissions_2024-10-05.csv",
                 "target-hospital-admissions_2024-10-05.csv",
                 "flu/2024_10_05.tsv", "snap-20241005.txt"):
        assert [d.isoformat() for d in D.name_dates(name)] == \
            ["2024-10-05"], name
    assert D.name_dates("admissions.csv") == []
    assert D.name_dates("2024-13-05.csv") == []            # not a date
    assert D.name_dates("x123456789.csv") == []            # a longer number
    assert len(D.name_dates("2024-10-05_to_2024-10-12.csv")) == 2


def test_a_snapshot_upload_is_named_by_its_folder():
    assert D.default_snapshot_name(["flu/2024-10-05.csv",
                                    "flu/2024-10-12.csv"]) == "flu"
    assert D.default_snapshot_name(["admissions_2024-10-05.csv",
                                    "admissions_2024-10-12.csv"]) \
        == "admissions"
    assert D.default_snapshot_name(["2024-10-05.csv",
                                    "2024-10-12.csv"]) == "snapshots"


# ------------------------------------------------------------------- core

def test_a_folder_is_one_vintage_true_dataset():
    rep = D.validate_snapshots(snaps())
    assert rep.ok, [str(p) for p in rep.problems]
    s = rep.summary
    assert s["has_as_of"] and s["as_of"] == ASOFS
    assert s["groups"] == ["Adult", "Overall", "Pediatric"]
    assert [f["file"] for f in s["snapshot_files"]] == [p.name for p in FILES]
    assert {f["as_of_from"] for f in s["snapshot_files"]} == {"name"}
    ds = D.ingest_snapshots(snaps(), None)
    assert ds.name == "flu" and ds.vintage_true
    assert ds.vintages() == ASOFS and ds.forecast_dates() == ASOFS
    assert len(ds.meta["snapshot_files"]) == 8
    # the originals are kept; source.csv holds every row with its as_of
    assert sorted(p.name for p in (ds.path / D.SOURCES_DIR).iterdir()) == \
        [p.name for p in FILES]
    head = text(ds.source_path).splitlines()[:2]
    assert head == ["as_of,date,group,value,population",
                    "2023-11-04,2023-01-07,Adult,229,5236907"]
    # the same files again: the same dataset
    assert D.ingest_snapshots(snaps(), None).id == ds.id
    assert len(D.list_datasets()) == 1


def test_a_folder_stores_what_one_as_of_csv_stores():
    """Each snapshot is materialized exactly as the one-CSV shape does."""
    folder = D.ingest_snapshots(snaps(), "folder")
    single = D.ingest(as_of_csv(), "single")
    assert folder.vintages() == single.vintages()
    for v in folder.vintages():
        assert text(folder.vintage_path(v)) == text(single.vintage_path(v))
    assert text(folder.locations_csv) == text(single.locations_csv)
    assert folder.meta["as_of_used"] == single.meta["as_of_used"]


def test_one_file_behaves_as_before():
    raw = FILES[0].read_bytes()
    one = D.validate_snapshots([(FILES[0].name, raw)])
    assert one.summary == D.validate(raw).summary
    assert not one.summary["has_as_of"]         # a dated name is not an as_of
    ds = D.ingest_snapshots([(f"flu/{FILES[0].name}", raw)], None)
    twin = D.ingest(raw, None, filename=FILES[0].name)
    assert ds.id == twin.id and not ds.vintage_true


def test_an_as_of_column_dates_a_file_whatever_its_name():
    files = []
    for i, p in enumerate(FILES[:3]):
        a = ASOFS[i]
        rows = p.read_text().splitlines()
        body = ["as_of," + rows[0]] + [f"{a},{r}" for r in rows[1:]]
        files.append((f"part{i + 1}.csv", "\n".join(body).encode()))
    rep = D.validate_snapshots(files)
    assert rep.ok, [str(p) for p in rep.problems]
    assert rep.summary["as_of"] == ASOFS[:3]
    assert {f["as_of_from"] for f in rep.summary["snapshot_files"]} == \
        {"column"}


# -------------------------------------------------------------- refusals

def test_files_without_an_as_of_are_refused():
    p = only(D.validate_snapshots([("a.csv", FILES[0].read_bytes()),
                                   ("b.csv", FILES[1].read_bytes())]),
             "snapshot_undated")
    assert p.message.startswith("2 file(s) carry no as_of: no date in the "
                                "name and no as_of column (a.csv, b.csv).")
    assert "2024-10-05.csv" in p.message


def test_two_files_for_one_as_of_week_are_refused():
    # 2023-11-09 (a Thursday) keys to the Saturday 2023-11-04
    p = only(D.validate_snapshots([
        (FILES[0].name, FILES[0].read_bytes()),
        ("admissions_2023-11-09.csv", FILES[0].read_bytes())]),
        "snapshot_as_of_twice")
    assert (f"week ending 2023-11-04: {FILES[0].name} and "
            "admissions_2023-11-09.csv") in p.message
    assert "Each as_of Saturday may come from one file only" in p.message


def test_a_week_after_its_file_s_as_of_is_refused():
    late = FILES[3].read_bytes()                      # weeks to 2023-11-18
    p = only(D.validate_snapshots([(FILES[0].name, late),
                                   (FILES[4].name, FILES[4].read_bytes())]),
             "as_of_before_date")
    assert p.message.startswith("6 row(s) hold a week after their "
                                "snapshot's as_of (in 1 file(s); e.g., "
                                "2023-11-11 in as_of 2023-11-04 (")
    assert p.kind == "Dates"


def test_groups_or_columns_that_differ_are_refused():
    kids = FILES[1].read_text().replace("Pediatric", "Kids").encode()
    p = only(D.validate_snapshots([(FILES[0].name, FILES[0].read_bytes()),
                                   (FILES[1].name, kids)]),
             "snapshot_groups")
    assert f"{FILES[1].name} lacks Pediatric and adds Kids" in p.message
    nopop = "\n".join(",".join(r.split(",")[:3]) for r in
                      FILES[1].read_text().splitlines()).encode()
    p = only(D.validate_snapshots([(FILES[0].name, FILES[0].read_bytes()),
                                   (FILES[1].name, nopop)]),
             "snapshot_columns")
    assert p.message.startswith("Columns differ across the files: 1 have a "
                                "population column and 1 do not")


def test_a_name_and_an_as_of_column_that_disagree_are_refused():
    rows = FILES[0].read_text().splitlines()
    body = ["as_of," + rows[0]] + [f"2023-11-11,{r}" for r in rows[1:]]
    p = only(D.validate_snapshots([
        (FILES[0].name, "\n".join(body).encode()),
        (FILES[2].name, FILES[2].read_bytes())]), "snapshot_as_of_name")
    assert f"{FILES[0].name}: named 2023-11-04, as_of 2023-11-11" in p.message


def test_a_file_s_own_problems_are_named_by_the_file():
    rep = D.validate_snapshots([
        (FILES[0].name, FILES[0].read_bytes()),
        ("admissions_2023-11-11.csv",
         b"date,target_group,value\n2023-01-07,A,-1\n")])
    p = only(rep, "value_negative")
    assert p.message.startswith("admissions_2023-11-11.csv: The 'value' "
                                "column contains 1 negative value(s)")
    # nothing stored
    with pytest.raises(D.DatasetError):
        D.ingest_snapshots([(FILES[0].name, FILES[0].read_bytes()),
                            ("admissions_2023-11-11.csv", b"date\n")], None)
    assert D.list_datasets() == []


def test_a_column_mapping_is_asked_once_for_every_file():
    odd = [(p.name, p.read_text().replace("target_group", "ward")
            .replace("value", "n").encode()) for p in FILES[:3]]
    rep = D.validate_snapshots(odd)
    assert rep.needs_mapping and rep.headers[:3] == ["date", "ward", "n"]
    assert all(p.message.startswith(FILES[0].name) for p in rep.problems)
    rep = D.validate_snapshots(odd, columns={"group": "ward", "value": "n"})
    assert rep.ok and rep.summary["as_of"] == ASOFS[:3]


# ---------------------------------------------------------------- the box

def _post(url, files, **data):
    return client.post(url, files=[("file", (n, b, "text/csv"))
                                   for n, b in files],
                       data=data, follow_redirects=False)


def test_the_box_takes_several_files_and_a_folder():
    page = client.get("/retro?tab=own").text
    assert ('<input type="file" name="file" id="dsup-replay-file" required '
            'multiple') in page
    # the folder pick: shown by the script where the browser offers one,
    # posted by it (the input has no name)
    assert ('<span class="dsfolder" data-folder-wrap hidden>' in page)
    assert ('<input type="file" id="dsup-replay-folder" data-folder '
            'webkitdirectory multiple>') in page
    assert "one snapshot per as_of" in page                 # the ? tip


def test_several_files_are_checked_together():
    j = _post("/data/datasets/check?where=replay", snaps()).json()
    assert j["ok"] and j["name"] == "flu"
    assert j["status"] == "Ready to use: 3 groups, 50 weeks, 8 snapshot files."
    html = j["html"]
    assert ('<dt>Snapshots</dt><dd>8 files, as_of <span class="nw">'
            '2023-11-04</span> to <span class="nw">2023-12-23</span></dd>'
            in html)
    assert f"First rows as read, from {FILES[0].name}" in html
    assert D.list_datasets() == []
    # a refusal names the files
    j = _post("/data/datasets/check", [("a.csv", FILES[0].read_bytes()),
                                       ("b.csv", FILES[1].read_bytes())]
              ).json()
    assert not j["ok"] and "carry no as_of" in j["html"]
    assert '<p class="dsp-kind">Snapshots</p>' in j["html"]


def test_replay_this_stores_one_vintage_true_dataset():
    r = _post("/data/datasets", snaps(), name="", next="replay")
    assert r.status_code == 303, r.text[:400]
    (ds,) = D.list_datasets()
    assert r.headers["location"] == f"/retro?dataset={ds.id}#main"
    page = client.get(r.headers["location"]).text
    assert "Vintage-true: each week sees its as_of snapshot." in page
    assert ("8 snapshots, as_of <span class=\"nw\">2023-11-04</span> to "
            "<span class=\"nw\">2023-12-23</span>.") in page
    first = page.split('id="dsr-first"')[1].split("</select>")[0]
    assert "<option selected>2023-11-04</option>" in first


def test_too_many_files_are_refused_before_reading(monkeypatch):
    monkeypatch.setattr(D, "MAX_SNAPSHOT_FILES", 3)
    j = _post("/data/datasets/check", snaps()).json()
    assert "Choose at most 3 files; nothing was read." in j["html"]
    r = _post("/data/datasets", snaps())
    assert r.status_code == 413 and "Choose at most 3 files" in r.text
    assert D.list_datasets() == []
