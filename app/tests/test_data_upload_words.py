"""The Data tab's upload words (bug hunt 2026-10-25, G27).

  * A dataset's Forecast form says "Groundhog (own data) only" once.
  * The Data tab's newest-week tip recommends a choice by the name the
    Forecast tab's Data issues box gives it.
  * The Weekly CSV tip is two short lines that name every date form the
    template uses; the column names and encodings are in README.
  * Dotted numbers say what each Values choice needs: rates keep them,
    counts are written without the dots.
  * A workbook, or a binary file, is named as such before any reading,
    with no "read as Windows-1252" note beside the refusal; a CSV with a
    few control characters in its cells is still read as text. A zip is
    named a workbook or a zip archive, an OLE file a workbook or another
    Office file (a zip of CSV files is no Excel workbook).
  * A value column chosen in the mapping stands: another column named
    like a value (cases) is not read as the value in its place.
  * The preview buttons' tip says what Save only does.
"""
import gzip
import io
import random
import re
import sqlite3
import struct
import zipfile
import zlib
from pathlib import Path

from app.core import datasets as D
from app.core import reported
from app.ui import pipeline
from app.ui.routes import forecast as ui_forecast
from test_datasets_ui import client, isolated, stored        # noqa: F401
from test_newest_reported import _hub

ROOT = Path(__file__).resolve().parents[2]


# ----------------------------------------------- DA-09: "only" said once

def test_the_dataset_forms_badge_says_only_once(monkeypatch):
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "absent")
    ds = stored()
    page = client.get(f"/forecast?source={ds.id}").text
    assert ("Groundhog (own data) only: the particle-filter engine is not "
            "installed") in page
    assert "only only" not in page


# ---------------------------------- DA-15: the box's name for the choice

def test_the_data_tab_recommends_a_choice_by_the_boxs_name(tmp_path,
                                                           monkeypatch):
    _hub(tmp_path / "hub", monkeypatch, newest={"Ohio": "0"})
    said = reported.check().details()[0]
    assert said.startswith("0 after 40, 40, 40: Ohio. Recommended: both "
                           "from the week before")
    assert "set aside" not in said
    # the words of the Forecast tab's "All zero states:" select
    assert ui_forecast._ALL_TEXT["set_aside"] == "Both from the week before"


# --------------------------------------------- DA-16: a short note, M/D/YY

def test_the_weekly_csv_tip_is_two_short_lines():
    page = client.get("/data").text
    tip = re.search(r'id="tip-dsup-data-about"[^>]*>(.*?)</span></span>',
                    page, re.S).group(1)
    lines = re.findall(r'<span class="ncline">(.*?)</span>', tip + "</span>")
    assert len(lines) == 2 and sum(len(t) for t in lines) < 400
    assert "YYYY-MM-DD, M/D/YYYY or M/D/YY" in lines[0]
    # the template's own dates are one of them
    template = (ROOT / "app/ui/static/dataset-template.csv").read_text()
    assert re.match(r"\d{1,2}/\d{1,2}/\d{2},", template.splitlines()[1])
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "location, region, jurisdiction" in readme
    assert "UTF-8, UTF-16 or Windows-1252" in readme


# ------------------------------------------ DA-17: what each choice needs

def test_dotted_numbers_say_what_counts_need():
    raw = ("date,target_group,value\n2024-01-06,A,1.234\n2024-01-13,A,2.500\n"
           "2024-01-20,A,3.125\n2024-01-27,A,4.750\n").encode()
    (p,) = D.validate(raw).problems
    assert p.message.endswith("1.234 is 1.234 as a rate or 1234 as a count. "
                              "Rates: choose rates. Counts: write them "
                              "without the dots (1.234 as 1234).")
    assert "Choose whether" not in p.message


# ------------------------------------- DA-20: not a CSV, named as such

#: what a zip (an .xlsx, an .ods, a .docx, a zip of CSV files) and an OLE
#: file (an .xls, a .doc) are called
ZIP_SAID = ("This looks like a workbook or a zip archive, not a CSV file: "
            "save the sheet as CSV UTF-8, or unzip the archive and choose "
            "the CSV files in it.")
OLE_SAID = ("This looks like a workbook or another Office file, not a CSV "
            "file: save the sheet as CSV UTF-8.")


def test_a_workbook_or_a_binary_file_is_named_not_decoded():
    binary = ("The file is not text: it holds binary data. Save it as CSV "
              "UTF-8.")
    for head, said in ((b"PK\x03\x04\x14\x00\x06\x00", ZIP_SAID),
                       (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", OLE_SAID),
                       (bytes(range(256)) * 4, binary),
                       (bytes(range(1, 256)) * 4, binary)):  # no NUL at all
        rep = D.validate(head + bytes(range(256)) * 8)
        assert [p.message for p in rep.problems] == [said]
        assert rep.warnings == []                  # no encoding note
    # UTF-16 text (NUL in every other byte) still reads
    rep = D.validate("date,target_group,value\n2024-01-06,A,5\n"
                     "2024-01-13,A,6\n".encode("utf-16"))
    assert "encoding" not in rep.codes


def _png(width, height, seed=1):
    """A real PNG of noise pixels, written with zlib alone."""
    rnd = random.Random(seed)
    rows = b"".join(b"\x00" + bytes(rnd.randrange(256)
                                    for _ in range(width * 3))
                    for _ in range(height))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data)))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2,
                                         0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def test_a_text_csv_with_a_few_control_characters_still_reads(tmp_path):
    """Review of #86 (S2): eight vertical tabs in an unused note column (text
    pasted from Word) made a valid CSV 'binary data'; before #86 it was
    read, with the column ignored. Real binary files are still refused."""
    binary = ("The file is not text: it holds binary data. Save it as CSV "
              "UTF-8.")
    rows = [f"2024-01-{d:02d},A,{v},a\x0bb\x0bc\n"
            for d, v in ((6, 5), (13, 6), (20, 7), (27, 8))]
    text = "date,target_group,value,note\n" + "".join(rows)
    rep = D.validate(text.encode())
    assert rep.problems == [] and rep.warnings == ["Ignored column(s): note."]
    # the same as Windows-1252 (an accented name: not UTF-8)
    rep = D.validate(text.replace(",A,", ",Zürich,").encode("cp1252"))
    assert rep.problems == []
    assert rep.warnings[0].startswith("Not UTF-8 text: read as Windows-1252")
    assert rep.warnings[1] == "Ignored column(s): note."
    # eight NUL bytes after a valid CSV: the row is named, as before
    rep = D.validate(b"date,target_group,value\n2024-01-06,A,5\n"
                     b"2024-01-13,A,6\n2024-01-20,A,7\n" + bytes(8))
    assert "encoding" not in rep.codes and rep.problems[0].rows == (5,)
    # binary files: an image, a gzip, a database, a zip
    db = tmp_path / "flu.db"
    con = sqlite3.connect(db)
    con.execute("create table t (a, b)")
    con.executemany("insert into t values (?, ?)",
                    [(i, "x" * i) for i in range(100)])
    con.commit()
    con.close()
    for raw in (_png(64, 64), _png(2, 2),
                gzip.compress(text.encode() * 50), db.read_bytes()):
        rep = D.validate(raw)
        assert [p.message for p in rep.problems] == [binary]
        assert rep.warnings == []
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("flu.csv", text)
    rep = D.validate(archive.getvalue())
    assert rep.codes == ["encoding"] and rep.warnings == []


def _xlsx() -> bytes:
    """A small .xlsx as a spreadsheet program writes one: a zip of its
    XML parts (one sheet, one row)."""
    ns = "http://schemas.openxmlformats.org"
    parts = {
        "[Content_Types].xml": (
            f'<Types xmlns="{ns}/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '</Types>'),
        "_rels/.rels": (
            f'<Relationships xmlns="{ns}/package/2006/relationships">'
            f'<Relationship Id="r1" Type="{ns}/officeDocument/2006/'
            'relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'),
        "xl/workbook.xml": (
            f'<workbook xmlns="{ns}/spreadsheetml/2006/main"><sheets>'
            '<sheet name="flu" sheetId="1" r:id="r1" xmlns:r="'
            f'{ns}/officeDocument/2006/relationships"/></sheets></workbook>'),
        "xl/worksheets/sheet1.xml": (
            f'<worksheet xmlns="{ns}/spreadsheetml/2006/main"><sheetData>'
            '<row r="1"><c r="A1" t="inlineStr"><is><t>date</t></is></c>'
            '</row></sheetData></worksheet>')}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in parts.items():
            z.writestr(name, body)
    return buf.getvalue()


def test_a_zip_of_csv_files_is_not_called_an_excel_workbook():
    """Review of #86 (S3): any zip or OLE file was "an Excel workbook": a
    zip of CSV files, a .docx, an .ods. The words now fit each, and the
    same files are refused (a zip or an OLE file, before any reading)."""
    text = "date,target_group,value\n2024-01-06,A,5\n2024-01-13,A,6\n"
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("flu/2024-01-13.csv", text)
        z.writestr("flu/2024-01-20.csv", text)
    for raw, said in ((archive.getvalue(), ZIP_SAID), (_xlsx(), ZIP_SAID),
                      (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(4088),
                       OLE_SAID)):
        rep = D.validate(raw)
        assert rep.codes == ["encoding"] and rep.warnings == []
        assert [p.message for p in rep.problems] == [said]
        assert "Excel" not in said
    # the Data tab's check says the same words
    r = client.post("/data/datasets/check",
                    files={"file": ("flu.zip", archive.getvalue(),
                                    "application/zip")},
                    data={"kind": "count"})
    assert r.json()["ok"] is False
    assert "a workbook or a zip archive, not a CSV file" in r.json()["html"]
    # a CSV that holds those letters is text, read as before
    rep = D.validate(text.replace(",A,", ",PK,").encode())
    assert rep.problems == []


# ------------------------- SB-05, review of #83: a mapped value column stands

def test_a_value_column_chosen_in_the_mapping_stands():
    """Review of #83 (S3): with the value mapped to n, a cases column of
    words was read as the value in n's place: "The 'cases' column must
    contain numbers only", and "Ignored column(s): n", against the choice
    just made. The file is refused as it was before #83, for the column
    the mapping leaves unnamed."""
    raw = (b"date,cases,n\n2024-01-06,ten,5\n2024-01-13,12,6\n"
           b"2024-01-20,<5,7\n2024-01-27,14,8\n")
    rep = D.validate(raw, columns={"value": "n"})
    assert rep.codes == ["missing_columns"]
    assert rep.problems[0].message.startswith("No column for the group")
    assert "'cases' column must contain numbers" not in rep.problems[0].message
    assert rep.warnings == []                  # n is not "ignored"
    # files that read are read as before: n of numbers, the value mapped
    rep = D.validate(raw.replace(b"ten", b"10").replace(b"<5", b"4"),
                     columns={"value": "n"})
    assert rep.problems == [] and rep.columns["value"] == "n"
    assert rep.warnings == ["Ignored column(s): cases."]
    # cases mapped, or the one column named like a value: its words named
    for cols, body in (({"value": "cases"}, raw),
                       (None, b"date,cases\n2024-01-06,ten\n2024-01-13,12\n")):
        rep = D.validate(body, columns=cols)
        assert rep.codes == ["value_numeric"]
        assert "The 'cases' column must contain numbers only" in \
            rep.problems[0].message


# ------------------------------------------ DA-21: Save only stays here

def test_the_buttons_tip_says_what_save_only_does():
    tpl = (ROOT / "app/ui/templates/_dataset_check.html").read_text(
        encoding="utf-8")
    assert ('"Forecast this and Replay this store the dataset, then open'
            in tpl)
    assert ('("; Save only stores it and stays here" if where == "data" '
            'else "")') in tpl
