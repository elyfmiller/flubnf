"""The forecast archive never downgrades, and keeps what was submitted
(app/core/archive_record.py, app/ui/pipeline._archive_run, the Output
page's "Mark as submitted", the Storage panel).

  * a later run replaces the archive only when it is complete (finished
    ok, every requested file written whole, no submission error), or the
    archive holds an incomplete run; otherwise its files stay in its own
    folder and the Output page says the archive kept the earlier run;
  * "Mark as submitted" (POST, localhost only) marks the archive with the
    date and time, on disk beside it and on the run's ledger row; a marked
    archive is never replaced and Storage refuses to delete it; "Unmark"
    lifts both.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                               # noqa: E402
from app.core import archive_record as AR                      # noqa: E402
from app.core.runs import Ledger, RunSpec                      # noqa: E402
from app.ui import pipeline as P                               # noqa: E402
from app.ui import server as srv                               # noqa: E402
from app.ui import shared as ui_shared                         # noqa: E402
from app.ui import state as ui_state                           # noqa: E402

from test_oracle_step import hubfiles                          # noqa: E402,F401
from test_optional_outputs import _default_run, pipeline_env   # noqa: E402,F401

client = TestClient(srv.app)
#: pipeline_env stubs _archive_run; the pipeline test puts this back
REAL_ARCHIVE = P._archive_run
DATE = "2098-01-03"


@pytest.fixture(autouse=True)
def _isolated_status():
    before = dict(ui_state._status)
    yield
    ui_state._status.clear()
    ui_state._status.update(before)
    ui_shared._invalidate_scans()


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    ui_state._status["running"] = None
    ui_state._status["workroot"] = None
    ui_shared._invalidate_scans()
    return tmp_path


def _run(root, tag, status="ok") -> Path:
    """A closed ledger row and its workroot with one submission file."""
    led = Ledger()
    rid = led.open_run(RunSpec(engine="all", forecast_date=DATE,
                               locations=["Ohio"]), Path("pending"), {})
    w = root / "workroots" / rid
    (w / "submission" / "NAU_PyBNF-OracleSIHRS").mkdir(parents=True)
    (w / "results.json").write_text(json.dumps({"tag": tag}))
    (w / "submission" / "NAU_PyBNF-OracleSIHRS" / "f.csv").write_text(tag)
    led.set_workroot(rid, w)
    led.close_run(rid, status, {})
    return w


def _held(root) -> str:
    return json.loads((root / "archive" / DATE / "results.json")
                      .read_text())["tag"]


def test_a_complete_run_replaces_the_archive(root):
    a = _run(root, "A")
    assert Path(P._archive_run(a, DATE)) == root / "archive" / DATE
    b = _run(root, "B")
    P._archive_run(b, DATE)
    assert _held(root) == "B"
    rec = AR.read_record(root / "archive" / DATE)
    assert rec["run_id"] == b.name and rec["complete"] is True
    assert sorted(p.name for p in (root / "archive").iterdir()) == [DATE]


def test_an_incomplete_run_keeps_the_earlier_complete_archive(root):
    a = _run(root, "A")
    P._archive_run(a, DATE)
    b = _run(root, "B", status="partial")
    out = P._archive_run(b, DATE, complete=False)
    assert out.startswith("kept: this run is not complete")
    assert a.name in out
    assert _held(root) == "A"
    # its files stay in its own run folder
    assert (b / "submission" / "NAU_PyBNF-OracleSIHRS" / "f.csv").is_file()
    # an incomplete run does archive when nothing is there, and a later
    # incomplete run may replace an incomplete archive (never a downgrade)
    other = "2098-01-10"
    P._archive_run(b, other, complete=False)
    assert AR.read_record(root / "archive" / other)["complete"] is False
    c = _run(root, "C", status="partial")
    P._archive_run(c, other, complete=False)
    assert AR.read_record(root / "archive" / other)["run_id"] == c.name


def test_an_archive_from_before_the_record_counts_as_complete(root):
    old = root / "archive" / DATE
    old.mkdir(parents=True)
    (old / "results.json").write_text(json.dumps({"tag": "legacy"}))
    b = _run(root, "B", status="partial")
    assert P._archive_run(b, DATE, complete=False).startswith("kept:")
    assert _held(root) == "legacy"


def test_the_pipeline_keeps_a_complete_archive_from_a_run_with_a_dropped_location(
        pipeline_env, monkeypatch):
    """Through _run_all: a complete run archives; a later run whose file
    lost a location is incomplete, so the archive keeps the first."""
    from app.core import submit as SB
    monkeypatch.setattr(P, "_archive_run", REAL_ARCHIVE)
    _spec, first = _default_run(pipeline_env["names"])
    assert not first["archived"].startswith("kept")
    rid1 = next(iter(Ledger().rows(1)))["run_id"]
    real = SB.write_submission

    def _corrupt(rows, model, *a, **k):
        rows = list(rows)
        if model == "pf":
            f = rows[0]["location"]
            rows = [dict(r, value=7) if r["location"] == f else r
                    for r in rows]
        return real(rows, model, *a, **k)
    monkeypatch.setattr(SB, "write_submission", _corrupt)
    # run ids carry the second they start: the Output page's latest run
    # must be this one, not a same-second sibling
    import time
    time.sleep(1.1)
    _spec, second = _default_run(pipeline_env["names"])
    assert second["submission_dropped"]
    assert second["archived"].startswith("kept: this run is not complete")
    date = _spec.forecast_date
    assert AR.read_record(runs_mod.APP_STATE / "archive" / date
                          )["run_id"] == rid1
    # the Output page says so, and links the run the archive kept
    ui_shared._invalidate_scans()
    html = client.get("/output").text
    assert "the archive kept the earlier complete run" in html
    assert f'href="/runs/{rid1}"' in html


def test_mark_keeps_the_archive_and_unmark_lifts_it(root):
    a = _run(root, "A")
    P._archive_run(a, DATE)
    r = client.post("/output/submitted",
                    data={"date": DATE, "mark": "1", "run": a.name},
                    follow_redirects=False)
    assert r.status_code == 303
    sub = AR.read_submitted(root / "archive" / DATE)
    assert sub["run_id"] == a.name and sub["submitted_at"]
    o = json.loads(Ledger().row(a.name)["outcome"])
    assert o["submitted"]["date"] == DATE
    assert o["submitted"]["submitted_at"] == sub["submitted_at"]
    # a later complete run does not replace a marked archive
    b = _run(root, "B")
    out = P._archive_run(b, DATE)
    assert out.startswith("kept: the archive is marked submitted")
    assert _held(root) == "A"
    # unmark: the marker and the ledger mark go, the history stays
    client.post("/output/submitted",
                data={"date": DATE, "mark": "0", "run": a.name},
                follow_redirects=False)
    assert AR.read_submitted(root / "archive" / DATE) is None
    o = json.loads(Ledger().row(a.name)["outcome"])
    assert "submitted" not in o and o["submitted_unmarked"]["was"]
    P._archive_run(b, DATE)
    assert _held(root) == "B"


def test_storage_refuses_to_delete_a_marked_archive(root):
    a = _run(root, "A")
    P._archive_run(a, DATE)
    AR.mark(DATE)
    html = client.get("/storage").text
    row = html.split(f"Weekly report and submissions · {DATE}", 1)[1]
    row = row.split("</div>", 1)[0]
    assert "Submitted" in row and "data-del-storage" not in row
    client.post("/storage/delete", data={"kind": "report-archive",
                                         "ident": DATE, "confirm": DATE},
                follow_redirects=False)
    assert (root / "archive" / DATE).is_dir()
    assert "marked submitted" in (ui_state._status.get("flash") or "")
    AR.unmark(DATE)
    client.post("/storage/delete", data={"kind": "report-archive",
                                         "ident": DATE, "confirm": DATE},
                follow_redirects=False)
    assert not (root / "archive" / DATE).exists()


def test_the_output_page_shows_the_mark_and_the_unmark(root):
    a = _run(root, "A")
    (a / "results.json").write_text(json.dumps(
        {"tag": "A", "forecast_date": DATE,
         "spec": RunSpec(engine="all", forecast_date=DATE,
                         locations=["Ohio"]).to_json()}))
    P._archive_run(a, DATE)
    ui_shared._invalidate_scans()
    html = client.get("/output").text
    assert "Mark as submitted" in html and "Archived as the forecast" in html
    AR.mark(DATE, now=4102444800.0)
    ui_shared._invalidate_scans()
    html = client.get("/output").text
    mark = html.split('id="archive-mark"', 1)[1].split("</div>", 1)[0]
    assert "Submitted</span>" in mark and "Unmark" in mark
    assert AR.read_submitted(root / "archive" / DATE)["submitted_at"] in mark
    assert "Mark as submitted" not in mark


def test_marking_is_refused_from_a_foreign_host_or_mid_run(root):
    a = _run(root, "A")
    P._archive_run(a, DATE)
    r = client.post("/output/submitted", data={"date": DATE, "mark": "1"},
                    headers={"host": "evil.example"}, follow_redirects=False)
    assert r.status_code == 403
    ui_state._status["running"] = "all:x"
    client.post("/output/submitted", data={"date": DATE, "mark": "1"},
                follow_redirects=False)
    assert AR.read_submitted(root / "archive" / DATE) is None
    ui_state._status["running"] = None
    # a stale page (the archive now holds another run) is refused too
    client.post("/output/submitted",
                data={"date": DATE, "mark": "1", "run": "someone-else"},
                follow_redirects=False)
    assert AR.read_submitted(root / "archive" / DATE) is None
    client.post("/output/submitted", data={"date": "../x", "mark": "1"},
                follow_redirects=False)
    assert not (root / "x").exists()


def test_the_output_line_says_why_a_run_was_kept_out(root):
    """Kept out by the mark reads as the mark, even once unmarked; kept
    out as incomplete reads as incomplete."""
    from app.ui.routes import output as O
    a = _run(root, "A")
    P._archive_run(a, DATE)
    AR.mark(DATE)
    b = _run(root, "B")
    why = P._archive_run(b, DATE)
    AR.unmark(DATE)
    v = O._archive_view(b.name, DATE, {"archived": why})
    assert v["kept"] and v["kept_submitted"] and not v["submitted"]
    c = _run(root, "C", status="partial")
    why = P._archive_run(c, DATE, complete=False)
    v = O._archive_view(c.name, DATE, {"archived": why})
    assert v["kept"] and not v["kept_submitted"]
    assert v["run_id"] == a.name and not v["this_run"]
