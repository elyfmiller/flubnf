"""Own datasets the Groundhog cannot forecast, and stored datasets that
cannot be read (the 2026-10-25 bug hunt, G07).

  * the check says when even the newest week gives the Groundhog too few
    weeks like it in earlier seasons; a dataset run that forecast no group
    is "partial", never a green "ok", and a replay that forecast no
    group-week ends "no forecast" (DA-01); the run page names the reason,
    not a newest week reading 0 (DA-03);
  * one week of data is refused: a forecast starts from the second (DA-08);
  * a dataset whose files went missing is named on its pages, not a 500
    (DA-12); an unreadable upload is said, not a 500 (DA-13); the same
    bytes under a name with the same id say where they are stored (DA-18).
"""
from __future__ import annotations

import json
import shutil
from datetime import date

import app.core.runs as runs_mod
from app.core import custom_retro as CX
from app.core import datasets as D
from app.ui import datasets_ui as DU
from app.ui import state as ui_state

from test_dataset_engines import grouped_bytes         # noqa: E402
from test_datasets_ui import (TEMPLATE, client,        # noqa: E402,F401
                              isolated, stored, upload)


def short_bytes() -> bytes:
    """Two groups, two seasons before the newest week: 20 donor weeks."""
    return grouped_bytes(groups=("North", "South"), start=date(2023, 8, 5),
                         end=date(2025, 11, 15), pop=False)


def check(raw: bytes) -> dict:
    r = client.post("/data/datasets/check",
                    files={"file": ("d.csv", raw, "text/csv")},
                    data={"kind": "count"})
    return r.json()


# ----------------------------------------------- too little for the Groundhog

def test_the_check_says_when_the_data_are_too_short_for_the_groundhog():
    j = check(short_bytes())
    assert j["ok"]
    html = " ".join(j["html"].split())
    assert ("Too little history for the Groundhog: at the newest week it "
            "finds 20 weeks like it in earlier seasons and needs 30, so it "
            "will not forecast this data on its own.") in html
    assert "Too little history" not in check(TEMPLATE.read_bytes())["html"]


def test_a_dataset_run_that_forecast_no_group_is_not_ok():
    ds = stored(short_bytes(), "short")
    client.post("/run/dataset", data={"dataset": ds.id,
                                      "forecast_date": "2025-11-15",
                                      "locations": "all",
                                      "engine": "analogue"})
    (row,) = runs_mod.Ledger().rows(5)
    assert row["status"] == "partial"
    o = json.loads(row["outcome"])
    assert o["exports"] == {}
    assert o["abstained"] == {"analogue": ["North", "South"]}
    page = " ".join(client.get(f"/runs/{row['run_id']}").text.split())
    # the reason is too few donors, not a newest week reading 0 (DA-03)
    assert "Too few donors" in page and "Groundhog (own data): 2 abstain" in page
    assert "Newest week reading 0" not in page


def test_a_replay_that_forecast_no_group_week_ends_no_forecast():
    ds = D.ingest(short_bytes(), "short", kind="count")
    weeks = CX.weeks_between(ds, "2025-09-06", "2025-11-08")
    out = CX.replay_dir(ds, CX.new_stamp(ds))
    meta = CX.run(ds, weeks, ds.groups, out_dir=out)
    assert meta["status"] == "no forecast"
    ok = D.ingest(TEMPLATE.read_bytes(), "template", kind="count")
    weeks = CX.weeks_between(ok, "2024-03-02", "2024-03-16")
    out = CX.replay_dir(ok, CX.new_stamp(ok))
    assert CX.run(ok, weeks, ok.groups, out_dir=out)["status"] == "done"


# ---------------------------------------------------------------- one week

def test_a_one_week_dataset_is_refused_at_the_check_and_the_store():
    raw = b"date,group,value\n2024-01-06,A,5\n"
    j = check(raw)
    assert not j["ok"]
    assert ("The data hold one week (<span class=\"nw\">2024-01-06</span>): "
            "a forecast starts from the week after the first, so at least "
            "two weeks are needed.") in " ".join(j["html"].split())
    r = upload(raw, "one")
    assert r.status_code == 422 and D.list_datasets() == []


def test_a_group_with_one_week_reads_one_week():
    raw = (b"date,group,value\n2024-01-06,A,5\n2024-01-13,A,6\n"
           b"2024-01-13,B,3\n")
    html = check(raw)["html"]
    assert "B: 1 week, peak" in html and "1 weeks" not in html


# --------------------------------------------------- a dataset's lost files

def test_a_dataset_whose_files_went_missing_is_named_not_a_500():
    whole = stored(name="Whole")
    ds = stored(TEMPLATE.read_bytes(), "Kids")
    shutil.rmtree(ds.path / "vintages")
    for page in (f"/data?source={ds.id}", f"/forecast?source={ds.id}",
                 f"/retro?dataset={ds.id}"):
        ui_state._status.pop("flash", None)
        r = client.get(page)
        assert r.status_code == 200, page
        assert ("Kids cannot be opened: its stored files are incomplete. "
                "Delete it on the Data tab and upload it again.") in r.text, page
    # the Data tab still lists it, with its Delete; the pickers leave it out
    # and the "Your data" tabs open the whole one
    assert f'action="/data/datasets/{ds.id}/delete"' in client.get("/data").text
    assert DU.choices() == [(whole.id, "Whole")]
    r = client.get("/forecast?tab=own", follow_redirects=False)
    assert r.headers["location"] == f"/forecast?source={whole.id}"


# ------------------------------------------------------ an unreadable upload

def test_an_unreadable_upload_is_said_not_a_500():
    r = client.post("/data/datasets", content=b"garbage",
                    headers={"content-type": "multipart/form-data"})
    assert r.status_code == 400
    assert "The upload could not be read; choose the file again." in r.text
    r = client.post("/data/datasets",
                    files={"file": ("d.csv", grouped_bytes(), "text/csv")},
                    data={"kind": "count",
                          **{f"f{i}": "x" for i in range(25)}})
    assert r.status_code == 400 and "could not be read" in r.text
    assert D.list_datasets() == []


# ------------------------------------------- the same bytes, another name

def test_the_same_file_under_a_name_with_the_same_id_says_where_it_is():
    raw = grouped_bytes()
    first = upload(raw, "流感 data")
    ui_state._status.pop("flash", None)
    second = upload(raw, "流行 data")
    assert first.headers["location"] == second.headers["location"]
    assert ui_state._status["flash"].startswith(
        "This file is already stored as 流感 data: 3 groups")
    assert len(D.list_datasets()) == 1
