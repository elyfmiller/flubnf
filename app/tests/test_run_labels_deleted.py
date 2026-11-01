"""Run labels, a run whose files Storage deleted, and run pages that fail
soft (bug hunt 2026-10-25, G15).

  * Every run label reads the run's time to the second, so two runs in one
    minute read apart: the run page, its Superseded notice, Output, the
    Storage ledger and the workroot rows; a report archive names its round
    as the workroot rows do.
  * A run whose workroot Storage deleted says so: its page (no Superseded
    notice), its Results, the ledger's facts, the Forecast tab's card and
    the fans' badge.
  * A run page whose results.json cannot be read renders and says so.
  * An unknown run's page is titled as a run's page is.
  * Every workroot row on Storage links its run page, an unrecorded one too.
"""
import json
import re
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                               # noqa: E402
from app.core.runs import Ledger, RunSpec, results_html        # noqa: E402
from app.ui import forecast_aids as fa                         # noqa: E402
from app.ui import server as srv                               # noqa: E402
from app.ui import shared as ui_shared                         # noqa: E402
from app.ui import state as ui_state                           # noqa: E402
from app.ui.routes import output as O                          # noqa: E402
from app.ui.routes import storage as ui_storage                # noqa: E402

client = TestClient(srv.app)
GH = "NAU_PyBNF-GroundHogCGR"
#: the outcome of a run that wrote one file and the weekly report
WROTE = {"submissions": [GH], "report": "report.html"}


@pytest.fixture()
def root(tmp_path, monkeypatch):
    before = dict(ui_state._status)
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    from app.core import datasets as datasets_mod
    monkeypatch.setattr(datasets_mod, "ROOT", tmp_path / "datasets")
    for k in ("running", "workroot", "phase", "flash", "flash_kind",
              "flash_detail"):
        ui_state._status[k] = None
    ui_shared._invalidate_scans()
    yield tmp_path
    ui_state._status.clear()
    ui_state._status.update(before)
    ui_shared._invalidate_scans()


def _run(root, asof="2026-10-17") -> str:
    """A closed ledger row and its workroot: one Groundhog file, the
    report, results.json."""
    import time
    time.sleep(1.05)                     # run ids sort by their start second
    led = Ledger()
    rid = led.open_run(RunSpec(engine="analogue", forecast_date=asof,
                               locations=["Ohio"]), Path("pending"), {})
    w = root / "workroots" / rid
    d = w / "submission" / GH
    d.mkdir(parents=True)
    (d / f"{O._reference_date(asof)}-{GH}.csv").write_text("x")
    (w / "results.json").write_text(json.dumps({"forecast_date": asof,
                                                "models": {}}))
    (w / "report.html").write_text("<p>r</p>")
    led.set_workroot(rid, w)
    led.close_run(rid, "ok", dict(WROTE))
    ui_shared._invalidate_scans()
    return rid


def _time(rid: str) -> str:
    """A run's time as every label now reads it."""
    return f"{rid[4:6]}-{rid[6:8]} {rid[9:11]}:{rid[11:13]}:{rid[13:15]}"


# ----------------------------------------------- FC-15: labels to the second

def test_two_runs_in_one_minute_read_apart_everywhere(root):
    a, b = _run(root), _run(root)
    assert ui_shared._run_label(a, "", tag=False) == _time(a)
    assert _time(a) != _time(b)
    # the passed-over run names the one Output shows, by a label of its own
    page = client.get(f"/runs/{a}").text
    assert f"Run: 2026-10-17 · {_time(a)}" in page
    assert f"Output shows run {_time(b)} for 2026-10-24." in page
    assert f"Open run {_time(b)}</a>" in page
    assert O._run_when(b) == _time(b)
    # Storage: the ledger row and the workroot row read the same time
    assert ui_storage._ledger_parts(a, "")[-1] == f"run {_time(a)}"
    rows = {w["id"]: w for w in ui_storage._storage_inventory()["workroots"]}
    assert rows[a]["when"] == _time(a)


def test_a_report_archive_names_its_round_as_the_workroot_rows_do(root):
    _run(root)
    arch = root / "archive" / "2026-10-17"
    arch.mkdir(parents=True)
    (arch / "report.html").write_text("<p>r</p>")
    page = client.get("/storage").text
    assert ("Weekly report and submissions · Round 2026-10-24 (as of "
            "2026-10-17)") in page
    assert "Round 2026-10-24 (as of 2026-10-17)</a>" in page   # workroot


# -------------------------------------- FC-16: files Storage deleted say so

def test_a_run_whose_files_storage_deleted_says_so(root):
    a, b = _run(root), _run(root)
    shutil.rmtree(root / "workroots" / b)
    ui_shared._invalidate_scans()
    assert O._files_deleted(b) and not O._files_deleted(a)
    page = client.get(f"/runs/{b}").text
    assert "This run&#39;s files were deleted in Storage." in page
    assert "Superseded." not in page
    assert ('<th scope="row">Submission files</th><td>deleted</td>'
            in page)
    assert '<th scope="row">Weekly report</th><td>deleted</td>' in page
    # the Forecast tab's card reads its Results the same way
    card = results_html(WROTE, "", deleted=True)
    assert "1 file" not in card and "written" not in card
    # the ledger: one "files deleted" in place of the files and report
    chips = [i["text"] for i in ui_shared._outcome_items(WROTE, deleted=True)]
    assert "files deleted" in chips and "report" not in chips
    assert not any("submission" in c for c in chips)
    storage = client.get("/storage").text
    row = re.search(r'<tr[^>]*>(?:(?!</tr>).)*' + b + r'(?:(?!</tr>).)*</tr>',
                    storage, re.S).group(0)
    assert "files deleted" in row and "report" not in row
    # the fans are the earlier run's, and the badge says why
    rows = [{"run_id": b, "status": "ok", "spec": "",
             "files_deleted": True}, {"run_id": a, "status": "ok"}]
    assert fa.fan_run(rows, a)["earlier"] == \
        "earlier run · newest has its files deleted"


# ------------------------------------ FC-19: an unreadable results.json

def test_a_run_page_with_an_unreadable_results_file_renders_and_says_so(root):
    a = _run(root)
    f = root / "workroots" / a / "results.json"
    f.write_text(f.read_text()[:12])                 # cut off mid-string
    r = client.get(f"/runs/{a}")
    assert r.status_code == 200
    assert "This run&#39;s results file could not be read" in r.text


# --------------------------------------- UI-17: an unknown run's page title

def test_an_unknown_runs_page_is_titled_as_a_runs_page(root):
    a = _run(root)
    r = client.get("/runs/nope")
    assert r.status_code == 404
    assert "<title>FluBNF · Run</title>" in r.text
    assert "<title>FluBNF · Run</title>" in client.get(f"/runs/{a}").text


# ----------------------------------- ST-13: every workroot row links its run

def test_every_workroot_row_links_its_run_page_an_unrecorded_one_too(root):
    rid = "20261025T184651-0f80ce"
    w = root / "workroots" / rid
    w.mkdir(parents=True)
    (w / "report.html").write_text("<p>r</p>")
    ui_shared._invalidate_scans()
    page = client.get("/storage").text
    row = page.split(f'data-wid="{rid}"', 1)[1].split("</div>", 1)[0]
    assert f'<a href="/runs/{rid}">Unrecorded run</a>' in row
    assert client.get(f"/runs/{rid}").status_code == 200
