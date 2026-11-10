"""Sandbox messages (bug hunt 2026-10-25, G25).

  * A notice's tip keeps a BNG2.pl log's lines (the reason itself leads
    the refusal: test_perl_bng_env).
  * The Sandbox's upload, which has no column picker, sends a column
    choice to the Data tab's upload, and a one-series file with a word in
    its value column names that word.
  * Rate data says what to do: a fit reads counts.
  * Check's headline promises no run above a note that says a run stops.
  * Check names a value that is not a finite number and still reports.
  (A blank value's advice, which once led into the gap rule, is pinned in
  test_dataset_lenient.)
"""
from pathlib import Path

from app.core import sandbox as sb
from test_sandbox_upload import _upload, box, client         # noqa: F401

STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"


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


# ------------------------------------- SB-14: no promise above a stop

def test_checks_headline_promises_no_run_above_a_note_that_says_it_stops():
    js = (STATIC / "sandbox.js").read_text(encoding="utf-8")
    assert ("return c.code === 'ROW_BEFORE_START' || c.code === "
            "'KEY_UNKNOWN';") in js
    assert "notes + (f.machine || stops ? '.' : '; the model can run.')" \
        in js


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
