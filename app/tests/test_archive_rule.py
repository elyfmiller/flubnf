"""Which run's files a forecast date shows: never a downgrade
(app/core/archive_record.py, app/ui/pipeline._archive_run, the Output
page).

  * a later run replaces the archive only when it is complete (finished
    ok, every requested file written whole, no submission error), or the
    archive holds an incomplete run; otherwise its files stay in its own
    folder;
  * the Output page applies the same rule per model (archive_record.choose):
    each model's file for a date comes from the newest complete run, else
    from the newest run that wrote one.

The "Mark as submitted" record, its route and the Storage delete-lock it
set were removed in round 8 (FluBNF only writes files; the user uploads
them): their tests went with them.
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


def test_choose_is_the_newest_complete_else_the_newest():
    a = {"run_id": "20980103T100000-a", "complete": True}
    b = {"run_id": "20980103T110000-b", "complete": False}
    c = {"run_id": "20980103T120000-c", "complete": True}
    assert AR.choose([a, b]) is a              # never a downgrade
    assert AR.choose([b, a, c]) is c           # a newer complete run wins
    assert AR.choose([b]) is b                 # nothing complete: the newest
    d = {"run_id": "20980103T130000-d", "complete": False}
    assert AR.choose([b, d]) is d
    assert AR.choose([]) is None


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


def test_a_marker_left_by_an_earlier_version_neither_locks_nor_shows(root):
    """A submitted.json from before round 8 is inert: a later complete run
    replaces the archive, Storage offers the delete, and no route or page
    speaks of marks."""
    a = _run(root, "A")
    P._archive_run(a, DATE)
    (root / "archive" / DATE / "submitted.json").write_text(
        json.dumps({"run_id": a.name, "submitted_at": "2098-01-05 10:00"}))
    b = _run(root, "B")
    P._archive_run(b, DATE)
    assert _held(root) == "B"
    (root / "archive" / DATE / "submitted.json").write_text("{}")
    html = client.get("/storage").text
    row = html.split(f"Weekly report and submissions · {DATE}", 1)[1]
    assert "data-del-storage" in row.split("</div>", 1)[0]
    assert "Submitted" not in html and "unmarked" not in html
    out = client.get("/output").text
    assert "Mark as submitted" not in out and "Submitted" not in out
    assert client.post("/output/submitted", data={"date": DATE, "mark": "1"},
                       follow_redirects=False).status_code in (404, 405)
    client.post("/storage/delete", data={"kind": "report-archive",
                                         "ident": DATE, "confirm": DATE},
                follow_redirects=False)
    assert not (root / "archive" / DATE).exists()


def test_the_pipeline_keeps_a_complete_archive_from_a_run_with_a_dropped_location(
        pipeline_env, monkeypatch):
    """Through _run_all: a complete run archives; a later run whose Oracle
    SIHRS file lost a location is incomplete, so the archive keeps the
    first. The Output page shows the date's Oracle SIHRS file from the
    first run and its Groundhog file (whole in both) from the second."""
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
    # run ids carry the second they start: the second run must sort after
    import time
    time.sleep(1.1)
    _spec, second = _default_run(pipeline_env["names"])
    assert second["submission_dropped"]
    assert second["archived"].startswith("kept: this run is not complete")
    rid2 = next(iter(Ledger().rows(1)))["run_id"]
    date = _spec.forecast_date
    assert AR.read_record(runs_mod.APP_STATE / "archive" / date
                          )["run_id"] == rid1
    ui_shared._invalidate_scans()
    html = client.get("/output").text
    card = html.split(f'id="fc-{date}"', 1)[1].split('<div class="card', 1)[0]
    oracle, groundhog = card.split("NAU_PyBNF-GroundHogCGR</b>", 1)
    assert "NAU_PyBNF-OracleSIHRS</b>" in oracle
    assert f'href="/runs/{rid1}"' in oracle and rid2 not in oracle
    assert f'href="/runs/{rid2}"' in groundhog
    # the files a date shows are the runs' own, byte for byte
    from app.ui.routes import output as O
    (d,) = [x for x in O.forecast_dates()[0] if x["asof"] == date]
    by = {f["model"]: f for f in d["files"]}
    assert Path(by["NAU_PyBNF-OracleSIHRS"]["path"]).read_bytes() == \
        Path(first["submissions"]["NAU_PyBNF-OracleSIHRS"]).read_bytes()
    assert by["NAU_PyBNF-GroundHogCGR"]["path"] == \
        second["submissions"]["NAU_PyBNF-GroundHogCGR"]
