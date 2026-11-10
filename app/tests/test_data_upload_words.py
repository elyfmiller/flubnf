"""The Data tab's upload words (bug hunt 2026-10-25, G27).

  * A dataset's Forecast form says "Groundhog (own data) only" once.
  * The Data tab's newest-week tip recommends a choice by the name the
    Forecast tab's Data issues box gives it.
  * The Weekly CSV tip is two short lines that name every date form the
    template uses; the column names and encodings are in README.
  * Dotted numbers say what each Values choice needs: rates keep them,
    counts are written without the dots.
  * A workbook, or a binary file, is named as such before any reading,
    with no "read as Windows-1252" note beside the refusal.
  * The preview buttons' tip says what Save only does.
"""
import re
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

def test_a_workbook_or_a_binary_file_is_named_not_decoded():
    workbook = ("This looks like an Excel workbook, not a CSV file: save it "
                "as CSV UTF-8.")
    binary = ("The file is not text: it holds binary data. Save it as CSV "
              "UTF-8.")
    for head, said in ((b"PK\x03\x04\x14\x00\x06\x00", workbook),
                       (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", workbook),
                       (bytes(range(256)) * 4, binary),
                       (bytes(range(1, 256)) * 4, binary)):  # no NUL at all
        rep = D.validate(head + bytes(range(256)) * 8)
        assert [p.message for p in rep.problems] == [said]
        assert rep.warnings == []                  # no encoding note
    # UTF-16 text (NUL in every other byte) still reads
    rep = D.validate("date,target_group,value\n2024-01-06,A,5\n"
                     "2024-01-13,A,6\n".encode("utf-16"))
    assert "encoding" not in rep.codes


# ------------------------------------------ DA-21: Save only stays here

def test_the_buttons_tip_says_what_save_only_does():
    tpl = (ROOT / "app/ui/templates/_dataset_check.html").read_text(
        encoding="utf-8")
    assert ('"Forecast this and Replay this store the dataset, then open'
            in tpl)
    assert ('("; Save only stores it and stays here" if where == "data" '
            'else "")') in tpl
