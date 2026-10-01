"""Each file served as a download leaves a line in
app/state/logs/downloads.log (app/ui/downloadlog.py): the route, the run,
the size and the sha256 prefix of the bytes that went out, and the path.
So "which file did I get" is answered from the server's side; writing
never fails a request, and the log rolls over like the slow-request log.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                               # noqa: E402
from app.core import archive_record                            # noqa: E402
from app.core.runs import Ledger, RunSpec                      # noqa: E402
from app.ui import downloadlog                                 # noqa: E402
from app.ui import perflog                                     # noqa: E402
from app.ui import server as srv                               # noqa: E402
from app.ui import shared as ui_shared                         # noqa: E402
from app.ui import state as ui_state                           # noqa: E402
from app.ui.routes import output as O                          # noqa: E402

client = TestClient(srv.app)
OR = "NAU_PyBNF-OracleSIHRS"
ASOF = "2098-01-03"


@pytest.fixture()
def run(tmp_path, monkeypatch):
    """A closed run with a CSV and a report, archived for its as-of."""
    before = dict(ui_state._status)
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    ui_state._status["running"] = None
    led = Ledger()
    rid = led.open_run(RunSpec(engine="all", forecast_date=ASOF,
                               locations=["Ohio"]), Path("pending"), {})
    w = tmp_path / "workroots" / rid
    d = w / "submission" / OR
    d.mkdir(parents=True)
    csv = d / f"{O._reference_date(ASOF)}-{OR}.csv"
    csv.write_text("reference_date,location,value\n2098-01-10,US,2786\n")
    (w / "report.html").write_text("<html><body>REPORT</body></html>")
    (w / "results.json").write_text(json.dumps(
        {"forecast_date": ASOF, "spec": "", "models": {}}))
    led.set_workroot(rid, w)
    led.close_run(rid, "ok", {})
    a = tmp_path / "archive" / ASOF
    a.mkdir(parents=True)
    (a / "report.html").write_text("<html><body>ARCHIVED</body></html>")
    archive_record.write_record(a, rid, True)
    ui_shared._invalidate_scans()
    yield rid, csv
    ui_state._status.clear()
    ui_state._status.update(before)
    ui_shared._invalidate_scans()


def _lines(root: Path) -> list:
    p = root / "logs" / "downloads.log"
    return p.read_text(encoding="utf-8").splitlines() if p.is_file() else []


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()[:12]


def test_each_download_leaves_a_line_naming_the_bytes_served(run, tmp_path):
    rid, csv = run
    assert _lines(tmp_path) == []
    r = client.get("/output/download", params={"path": str(csv)})
    assert r.status_code == 200
    (line,) = _lines(tmp_path)
    assert f"  /output/download  run {rid}  {len(r.content)} B  " \
        f"sha256 {_sha(r.content)}  {csv.resolve()}" in line
    for url, served in (
            ("/output/report/download", "workroots"),
            (f"/output/report/download?date={ASOF}", "archive"),
            (f"/runs/{rid}/report/download", "workroots")):
        r = client.get(url)
        assert r.status_code == 200, url
        last = _lines(tmp_path)[-1]
        assert f"  {url}  run {rid}  " in last, last
        assert f"sha256 {_sha(r.content)}" in last
        # the served path in the machine's own spelling (backslashes on
        # Windows)
        assert f"{os.sep}{served}{os.sep}" in last
        assert last.endswith("report.html")
    assert len(_lines(tmp_path)) == 4
    # a refused or missing file is not a download
    client.get("/output/download", params={"path": "/nowhere.csv"})
    client.get("/runs/20980101T000000-bbbbbb/report/download")
    assert len(_lines(tmp_path)) == 4


def test_the_log_never_fails_a_download(run, tmp_path):
    rid, csv = run
    (tmp_path / "logs").write_text("a file where the folder would be")
    r = client.get("/output/download", params={"path": str(csv)})
    assert r.status_code == 200 and r.content == csv.read_bytes()
    assert client.get(f"/runs/{rid}/report/download").status_code == 200
    downloadlog.write("/x", tmp_path / "gone.csv")       # nothing to hash


def test_the_log_rolls_over(run, tmp_path, monkeypatch):
    rid, csv = run
    monkeypatch.setattr(perflog, "MAX_BYTES", 200)
    for _ in range(4):
        client.get("/output/download", params={"path": str(csv)})
    logs = tmp_path / "logs"
    assert (logs / "downloads.log.1").is_file()
    assert (logs / "downloads.log").stat().st_size < 600
