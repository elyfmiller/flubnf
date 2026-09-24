"""The upload box (templates/_dataset_upload.html, static/dataset_upload.js,
POST /data/datasets/check): one partial on the Data, Forecast and
Retrospective tabs; an instant check that stores nothing and shows every
problem, a column mapping or a preview; "Forecast this" and "Replay this"
store the file and open it with sensible defaults.

No hub and no engine: FLUBNF_HUB=/nonexistent; the store lives in tmp_path.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.core.runs as runs_mod
from app.core import datasets as D
from app.ui import datasets_ui as DU
from app.ui import server as srv

from test_dataset_engines import grouped_bytes         # noqa: E402

client = TestClient(srv.app)
STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"
NODE = shutil.which("node") or "/opt/node22/bin/node"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path / "state")
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path / "retro")
    status = dict(srv._status)
    srv._status["running"] = None
    srv._status.pop("flash", None)
    DU._LAST.clear()
    DU._REPLAY.clear()
    srv._invalidate_scans()
    yield
    srv._status.clear()
    srv._status.update(status)
    DU._LAST.clear()
    DU._REPLAY.clear()
    srv._invalidate_scans()


def check(raw, name="kids.csv", where="data", **data):
    return client.post(f"/data/datasets/check?where={where}",
                       files={"file": (name, raw, "text/csv")}, data=data)


def store(raw, name="Kids", **data):
    return client.post("/data/datasets",
                       files={"file": ("kids.csv", raw, "text/csv")},
                       data={"name": name, **data}, follow_redirects=False)


def boxes(page):
    return re.findall(r'<form[^>]*data-dsup data-where="(\w+)"', page)


# -------------------------------------------------------- one shared box

def test_the_box_is_on_data_forecast_and_retrospective():
    for url, where in (("/data", "data"), ("/forecast", "forecast"),
                       ("/retro", "replay")):
        page = client.get(url).text
        assert boxes(page) == [where], url
        assert page.count('src="/static/dataset_upload.js"') == 1, url
        assert f'<label class="dsdrop" for="dsup-{where}-file" data-drop>' \
            in page
        # shown (instead of the title) while a file is dragged over
        assert '<span class="dsdrop-on" aria-hidden="true">Drop to check' \
            in page
        assert (f'<input type="file" name="file" id="dsup-{where}-file" '
                'required') in page
        assert 'accept=".csv,.tsv,.txt,' in page
        assert "dataset-template.csv" in page
        assert '<option value="" selected>from the values</option>' in page
    # the old manual weekday option is gone from every page
    assert "week-start Sundays" not in client.get("/data").text


def test_the_box_stays_on_a_dataset_forecast_and_the_hub_is_unchanged():
    raw = grouped_bytes()
    loc = store(raw, next="data").headers["location"]
    ds_id = loc.split("source=")[1].split("#")[0]
    page = client.get(f"/forecast?source={ds_id}").text
    assert boxes(page) == ["forecast"]
    hub = client.get("/forecast").text
    assert 'action="/run"' in hub and "all 52 jurisdictions" in hub
    assert hub.index('id="fc-upload"') < hub.index('id="fcform"')


def test_the_script_is_served_and_parses():
    r = client.get("/static/dataset_upload.js")
    assert r.status_code == 200 and "/data/datasets/check" in r.text
    if Path(NODE).exists():
        out = subprocess.run([NODE, "--check", str(STATIC /
                                                   "dataset_upload.js")],
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr


# ------------------------------------------------------------ the check

def test_a_valid_file_previews_and_stores_nothing():
    r = check(grouped_bytes())
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] and j["inferred_kind"] == "count"
    assert not j["needs_mapping"] and j["targets"] == []
    html = j["html"]
    assert "Ready to use." in html and "Nothing was stored" not in html
    assert "<dt>Groups</dt><dd>3: Adult, Overall, Pediatric</dd>" in html
    assert "2019-08-03 to 2024-02-24" in html
    assert "<dt>Values</dt><dd>counts (from the values)</dd>" in html
    assert "<dt>Population</dt><dd>yes</dd>" in html
    assert "comma-separated, UTF-8" in html
    assert html.count("<polyline") == 3                 # one per group
    assert 'aria-label="Adult: ' in html
    assert "First rows as read" in html
    # the date as written sits under its week
    assert ('<td class="wk">2019-08-03<span class="dsasw">8/3/19</span></td>'
            in html)
    assert '<button class="gold" name="next" value="forecast">Forecast this' \
        in html
    assert 'name="next" value="replay">Replay this' in html
    assert D.list_datasets() == []


def test_the_replay_panel_leads_with_replay_this():
    html = check(grouped_bytes(), where="replay").json()["html"]
    assert '<button class="gold" name="next" value="replay">Replay this' in html
    assert "Save only" not in html


def test_problems_come_grouped_by_kind_with_rows():
    raw = (b"date,target_group,value\n2024-08-03,A,1\n2024-08-10,A,-2\n"
           b"2024-08-19,A,3\nsoon,B/C,x\n")
    j = check(raw).json()
    assert not j["ok"]
    html = j["html"]
    assert "Nothing was stored." in html and "problems to fix" in html
    kinds = re.findall(r'<p class="dsp-kind">(\w+)</p>', html)
    assert kinds == ["Dates", "Values", "Groups", "Weeks"]
    # each example with its date and group
    assert ('(row 3; e.g., -2 (<span class="nw">2024-08-10</span>, A))'
            in html and "(row 4;" in html)
    assert "(row 5; e.g., soon (B/C))" in html
    assert "Ready to use." not in html
    # a date stays on one line at phone width (it broke after a hyphen)
    assert '<span class="nw">2024-08-19</span> (A, Monday, row 4)' in html


def test_an_unmatched_column_asks_for_a_mapping_instead_of_an_error():
    raw = b"day,area,amount\n2024-08-03,A,1\n2024-08-10,A,2\n"
    j = check(raw).json()
    assert j["needs_mapping"] and not j["ok"]
    html = j["html"]
    assert "Nothing was stored." not in html
    assert "Which column is which?" in html
    assert "Choose the column that holds the date, the group and the value." \
        in html
    assert '<select name="col_date" id="dsup-data-col-date" data-recheck>' \
        in html
    assert '<option value="#1">day</option>' in html
    assert '<option value="#2" selected>area</option>' not in html
    j = check(raw, col_date="#1", col_group="#2", col_value="#3").json()
    assert j["ok"] and "Ready to use." in j["html"]
    # the chosen columns stay offered, preselected
    assert '<option value="#3" selected>amount</option>' in j["html"]
    r = store(raw, col_date="#1", col_group="#2", col_value="#3")
    assert r.status_code == 303
    assert D.list_datasets()[0].meta["columns"]["value"] == "amount"


def test_a_file_with_several_targets_waits_for_a_choice():
    """Nothing is picked for the user: the picker offers every target,
    preselects none, and the preview (with its store buttons) comes only
    once one is chosen."""
    raw = (b"target_end_date,target,location,observation\n"
           b"2024-08-03,wk inc flu hosp,01,1\n"
           b"2024-08-10,wk inc flu hosp,01,2\n"
           b"2024-08-03,wk inc covid hosp,01,3\n")
    j = check(raw).json()
    assert not j["ok"] and j["target"] == ""
    assert j["targets"] == ["wk inc covid hosp", "wk inc flu hosp"]
    html = j["html"]
    assert '<select name="target" id="dsup-data-target" data-recheck>' in html
    assert '<option value="" selected>choose…</option>' in html
    assert " selected>wk inc" not in html
    assert "Nothing was stored." not in html and "Ready to use." not in html
    assert 'value="forecast"' not in html
    j = check(raw, target="wk inc flu hosp").json()
    assert j["ok"] and "<option selected>wk inc flu hosp</option>" in j["html"]
    assert "Ready to use." in j["html"]
    single = b"target_end_date,target,location,observation\n2024-08-03,a,01,1\n"
    assert 'name="target"' not in check(single).json()["html"]
    # storing without a choice stores nothing and asks again
    r = store(raw, next="forecast")
    assert r.status_code == 422 and D.list_datasets() == []
    assert '<option value="" selected>choose…</option>' in r.text


def test_blank_target_cells_are_a_problem_not_dropped_rows():
    """Rows with a blank target once vanished behind a lone named target
    (no picker, 'Ready to use'), then failed to store."""
    raw = (b"target_end_date,target,location,observation\n"
           b"2024-01-06,,US,5\n2024-01-06,wk inc flu hosp,US,5\n"
           b"2024-01-13,wk inc flu hosp,US,6\n")
    j = check(raw).json()
    assert not j["ok"] and "Ready to use." not in j["html"]
    assert ("The &#39;target&#39; column is blank on 1 row(s) (row 2; e.g., "
            'row 2: <span class="nw">2024-01-06</span>, US), while the others '
            "name wk inc flu hosp.") in j["html"]
    assert 'name="target"' not in j["html"]
    rep = D.validate(raw, target="wk inc flu hosp")
    assert rep.codes == ["target_blank"]


def test_two_candidate_date_columns_say_why_they_ask():
    """The mapping step once said only 'Choose the column that holds the
    date.', dropping the reason; nothing is picked for the user."""
    rows = "\n".join(f"2024-01-{d + 2:02d},2024-01-{d:02d},Coast,{d}"
                     for d in (6, 13, 20))
    raw = f"date,week_ending,group,value\n{rows}\n".encode()
    j = check(raw).json()
    assert j["needs_mapping"] and not j["ok"]
    html = j["html"]
    assert ("Two columns could be the date: &#39;date&#39; and "
            "&#39;week_ending&#39;.") in html
    # the example is the column of week ends, not the Monday report date
    assert "Choose one (e.g., week_ending, the end of each week)" in html
    assert "Choose the column that holds the date." not in html
    assert '<option value="">choose…</option>' in html      # Date: unset
    j = check(raw, col_date="#2").json()
    assert j["ok"] and "Ignored column(s): date." in j["html"]


def test_a_status_line_is_read_out_not_the_whole_result():
    """The result box was a live region, so every check (each column
    picked) read out the facts, the sparklines and the first rows again;
    a short status line says what the check found instead. The script
    keeps a focused column or target select focused across its re-check
    (it once replaced the result and dropped the focus to the page)."""
    page = client.get("/forecast").text
    assert '<p class="dsup-status" data-dsup-status role="status"></p>' in page
    assert "<div class=\"dsup-result\" data-result>" in page
    assert check(grouped_bytes()).json()["status"].startswith(
        "Ready to use: 3 groups, ")
    assert check(b"day,area,amount\n2024-08-03,A,1\n").json()["status"] == \
        "Choose which column is which."
    two = (b"target_end_date,target,location,observation\n"
           b"2024-08-03,a,01,1\n2024-08-03,b,01,3\n")
    assert check(two).json()["status"] == "Choose the target."
    j = check(b"date,target_group,value\n2024-08-03,A,-1\nsoon,A,2\n").json()
    assert j["status"] == "Nothing was stored: 2 problems to fix."
    assert 'role="alert"' not in j["html"]
    js = (STATIC / "dataset_upload.js").read_text()
    assert "if (keep !== null) refocus(keep);" in js
    assert "if (keep === null) {" in js       # a kept result is not blanked


def test_a_kind_filled_in_from_the_values_stays_from_the_values():
    """The box shows the inferred kind in its select (kind_auto=1 while
    it is not picked by hand); posting it must not turn it into a declared
    kind: the preview keeps '(from the values)' and the store records
    kind_from 'values', as the CLI does."""
    j = check(grouped_bytes(), kind="count", kind_auto="1").json()
    assert "<dt>Values</dt><dd>counts (from the values)</dd>" in j["html"]
    j = check(grouped_bytes(), kind="count").json()
    assert "<dt>Values</dt><dd>counts</dd>" in j["html"]
    assert store(grouped_bytes(), kind="count",
                 kind_auto="1").status_code == 303
    (ds,) = D.list_datasets()
    assert ds.kind == "count" and ds.meta["options"]["kind_from"] == "values"
    page = client.get("/data").text
    assert '<input type="hidden" name="kind_auto" value="" data-kind-auto>' \
        in page


def test_the_check_reports_notices_and_the_declared_kind():
    raw = (b"Week;Region;Cases\n2024-08-04;A;1,5\n2024-08-11;A;2,5\n")
    j = check(raw).json()
    assert j["ok"] and j["inferred_kind"] == "rate"
    assert "Dates moved to week-ending Saturdays: +6 days" in j["html"]
    assert "decimal commas" in j["html"]
    assert "semicolon-separated" in j["html"]
    j = check(raw, kind="count").json()
    assert not j["ok"] and "not whole numbers" in j["html"]


def test_numbers_that_read_two_ways_leave_the_kind_to_the_user():
    """987, 1.234, 12.345 in a comma file were read as decimals and the
    kind filled in as rates; the check now asks, and fills in nothing."""
    raw = (b"date,group,value\n2024-01-06,Berlin,987\n"
           b"2024-01-13,Berlin,1.234\n2024-01-20,Berlin,12.345\n")
    j = check(raw).json()
    assert not j["ok"] and j["inferred_kind"] is None
    assert "Choose whether the values are counts or rates" in j["html"]
    assert "Ready to use." not in j["html"]
    j = check(raw, kind="rate").json()
    assert j["ok"] and "<dt>Values</dt><dd>rates</dd>" in j["html"]


def test_the_check_refuses_what_is_not_a_file(monkeypatch):
    r = client.post("/data/datasets/check", data={"kind": "count"},
                    files={"x": ("a", b"", "text/plain")})
    assert r.status_code == 400 and "Choose a CSV file" in r.json()["html"]
    r = check(grouped_bytes(), kind="percent")
    assert r.status_code == 400 and "counts or rates" in r.json()["html"]
    monkeypatch.setattr(D, "DEFAULT_LIMITS", D.Limits(max_bytes=2000))
    monkeypatch.setattr(DU, "FORM_SLACK", 0)
    r = check(b"date,target_group,value\n" + b"2024-08-03,A,1\n" * 500)
    assert r.status_code == 413 and "limit" in r.json()["html"]


def test_the_check_is_local_and_same_origin_only():
    r = client.post("/data/datasets/check",
                    files={"file": ("a.csv", grouped_bytes())},
                    headers={"host": "rebind.example"})
    assert r.status_code == 403
    r = client.post("/data/datasets/check",
                    files={"file": ("a.csv", grouped_bytes())},
                    headers={"origin": "http://evil.example"})
    assert r.status_code == 403


# ------------------------------------------------- "Forecast/Replay this"

def test_forecast_this_opens_the_forecast_tab_on_the_dataset():
    r = store(grouped_bytes(), next="forecast", kind="")
    assert r.status_code == 303
    (ds,) = D.list_datasets()
    assert r.headers["location"] == f"/forecast?source={ds.id}"
    page = client.get(r.headers["location"]).text
    assert f'name="dataset" value="{ds.id}"' in page
    newest = ds.forecast_dates()[-1]
    assert f'name="forecast_date" value="{newest}"' in page
    assert re.search(r'id="ck-all" value="all" name="locations"\s+checked',
                     page)


def test_replay_this_opens_the_replay_card_on_its_newest_season():
    other = store(grouped_bytes(groups=("A", "B")), name="Other")
    assert other.status_code == 303
    r = store(grouped_bytes(), name="Kids", next="replay")
    ds = next(d for d in D.list_datasets() if d.name == "Kids")
    assert r.headers["location"] == f"/retro?dataset={ds.id}#dataset-replay"
    page = client.get(f"/retro?dataset={ds.id}").text
    assert f'<option value="{ds.id}" selected>Kids</option>' in page
    card = page[page.index('id="dataset-replay"'):]
    assert '"default_first": "2023-10-07"' in card
    assert '"default_last": "2024-02-24"' in card
    # an unknown id selects nothing
    page = client.get("/retro?dataset=nope-000000000000").text
    assert " selected>Kids</option>" not in page


def test_the_data_list_replay_link_preselects():
    loc = store(grouped_bytes()).headers["location"]
    ds_id = loc.split("source=")[1].split("#")[0]
    page = client.get("/data").text
    assert f'href="/retro?dataset={ds_id}#dataset-replay">Replay</a>' in page


def _weeks(first, last):
    from datetime import date, timedelta
    d, out = date.fromisoformat(first), []
    while d <= date.fromisoformat(last):
        out.append(d.isoformat())
        d += timedelta(days=7)
    return out


@pytest.mark.parametrize("dates,want", [
    ([], ("", "")),
    (["2024-01-06", "2024-01-13"], ("2024-01-06", "2024-01-13")),
    # one season: all of it, summer weeks too
    (_weeks("2023-08-05", "2024-07-27"), ("2023-08-05", "2024-07-27")),
    # two seasons, the newest with 8+ flu-season weeks: its Oct..Jun weeks
    (_weeks("2022-08-06", "2024-02-24"), ("2023-10-07", "2024-02-24")),
    # the shipped template: its newest season is 8 summer weeks, so the
    # last full flu season, not the trough (once 2024-08-03..09-21)
    (_weeks("2022-01-01", "2024-09-21"), ("2023-10-07", "2024-06-29")),
    # the newest holds under 8 flu-season weeks: the season before
    (_weeks("2022-10-01", "2023-10-28"), ("2022-10-01", "2023-06-24")),
    # no season holds 8: the whole range
    (["2023-01-07", "2023-05-06", "2023-07-29", "2023-08-05", "2023-08-12"],
     ("2023-01-07", "2023-08-12")),
])
def test_replay_window(dates, want):
    assert DU.replay_window(dates) == want
