"""Sandbox messages (bug hunt 2026-10-25, G25).

  * A notice's tip keeps a BNG2.pl log's lines (the reason itself leads
    the refusal: test_perl_bng_env).
  * The Sandbox's upload, which has no column picker, sends a column
    choice to the Data tab's upload (a repeated header name too), and a
    one-series file with a word in its value column names that word.
  * Rate data says what to do: a fit reads counts.
  * Check's headline promises no run above a note that says a run stops
    (one data row too).
  * Check names a value that is not a finite number and still reports;
    the scale note leaves such a value out.
  (A blank value's advice, which once led into the gap rule, is pinned in
  test_dataset_lenient.)
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.core import sandbox as sb
from app.core import sandbox_check as SC
from app.core.problem_codes import CODES
from test_sandbox_upload import _upload, box, client         # noqa: F401

STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"
NODE = shutil.which("node")


# ------------------------------- SB-04 (WI-11): the log in the tip

def test_a_notices_tip_keeps_the_logs_lines():
    # BNG2.pl's log is one line a step; the tip once ran it together
    assert "#tip-flash{white-space:pre-line}" in (
        STATIC / "nau.css").read_text(encoding="utf-8")


# ----------------------------------------- SB-05: advice it can act on

def _report(r) -> str:
    return client.get(r.headers["location"]).text


def test_the_sandbox_upload_sends_a_column_choice_to_the_data_tab(box):
    page = _report(_upload("date,cases,deaths\n2024-01-06,5,1\n"
                           "2024-01-13,7,1\n2024-01-20,9,2\n",
                           name="two.csv", kind=""))
    assert ("Keep only one in the file, or upload it on the Data tab, "
            "where the column can be chosen.") in page
    assert "Choose one (e.g." not in page
    # a word in the one value column is named, not taken for a group
    page = _report(_upload("date,cases\n2024-01-06,5\n2024-01-13,ten\n"
                           "2024-01-20,9\n2024-01-27,11\n",
                           name="bad_text.csv", kind=""))
    assert "must contain numbers only" in page and "ten" in page
    assert "No column for the group" not in page


def test_a_repeated_header_name_gets_the_sandboxs_advice_too(box):  # noqa: F811
    # the store labels a repeated name 'cases (#2)': the ')' inside the
    # example once stopped the rewrite, leaving "Choose one" with no picker
    page = _report(_upload("date,cases,cases\n2024-01-06,5,1\n"
                           "2024-01-13,7,1\n2024-01-20,9,2\n",
                           name="twice.csv", kind=""))
    assert "(#2)" in page
    assert ("Keep only one in the file, or upload it on the Data tab, "
            "where the column can be chosen.") in page
    assert "Choose one" not in page


# ------------------------------------- SB-14: no promise above a stop

def test_checks_headline_promises_no_run_above_a_note_that_says_it_stops():
    js = (STATIC / "sandbox.js").read_text(encoding="utf-8")
    assert ("var RUN_STOPS = ['ROW_BEFORE_START', 'KEY_UNKNOWN', "
            "'ONE_ROW'];") in js
    assert "var stops = stopsRun(d.codes);" in js
    assert "notes + (f.machine || stops ? '.' : '; the model can run.')" \
        in js


@pytest.mark.skipif(not NODE, reason="no node")
def test_a_one_row_note_stops_the_run_under_node(tmp_path):
    # "one data row: this engine needs two or more" is a note (a warning)
    # whose words say the run stops: the page's own function, run here
    assert CODES["ONE_ROW"][0] == "warning"
    cases = [[{"code": "ONE_ROW"}], [{"code": "ROW_BEFORE_START"}],
             [{"code": "KEY_UNKNOWN"}],
             [{"code": "SCALE_OFF"}, {"code": "ONE_ROW"}],
             [{"code": "SCALE_OFF"}], [], None]
    drv = tmp_path / "d.js"
    drv.write_text(
        "var g = {}; (function(){ %s }).call(g);\n"
        "var S = g.SandboxPage;\n"
        "console.log(JSON.stringify(%s.map(function (c) "
        "{ return S.stopsRun(c); })));\n"
        % ((STATIC / "sandbox.js").read_text(encoding="utf-8"),
           json.dumps(cases)), encoding="utf-8")
    out = subprocess.run([NODE, str(drv)], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [True, True, True, True, False, False,
                                      False]


# ------------------------------------ SB-15: inf is named, Check goes on

def test_check_names_a_value_that_is_not_finite(sandbox_root):
    files = dict(sb.skeleton("mine"))
    for bad in ("inf", "1e400"):
        files["data.exp"] = f"# time T_weekly\n1 {bad}\n2 5\n"
        r = sb.check(files)
        assert not r["ok"]
        assert any("t = 1 whose value is not a finite number" in p
                   for p in r["problems"])
        assert not any("division by zero" in p for p in r["problems"])
        assert r["facts"]["rows"] == 2            # the rest still reports


def test_the_scale_note_leaves_out_a_value_that_is_not_finite():
    # the guarded division itself (Check's own run above never reaches it
    # here): an infinite count is left out of the data's range and total,
    # so no division by zero and no 'inf' in the fact
    for bad in (float("inf"), float("-inf")):
        fact, warn = SC._scale_note([1, 2], [bad, 5])
        assert fact == ("at its written values the model gives 1 to 2 a "
                        "week; data.exp holds 5 to 5")
        assert warn == ""
    # a model total past the largest number: no ratio is said
    assert SC._scale_note([float("inf"), 1], [1, 2])[1] == ""
    # a real tenfold gap still is
    assert "times the data's" in SC._scale_note([100, 200], [1, 2])[1]
