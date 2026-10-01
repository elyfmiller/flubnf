"""The Output page says which run its weekly report is from, and keeps up
with new runs (routes/output.output_page, output_stamp, output.html).

  * the report buttons name the run beside "as of" (/runs/<id>/report and
    its download), so the file always matches the label; the bare
    /output/report links still work for old bookmarks;
  * /runs/<id>/report serves only a run id's shape;
  * the page carries a stamp (the newest run with a results.json, and
    whether a run is on); its script reloads once no run is on and the
    stamp moved or the page was rendered mid-run, never over a focused
    form; base.html reloads a page the back/forward cache restores.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                               # noqa: E402
from app.core.runs import Ledger, RunSpec                      # noqa: E402
from app.ui import server as srv                               # noqa: E402
from app.ui import shared as ui_shared                         # noqa: E402
from app.ui import state as ui_state                           # noqa: E402
from app.ui.routes import output as O                          # noqa: E402

client = TestClient(srv.app)
OR = "NAU_PyBNF-OracleSIHRS"
NODE = shutil.which("node")


@pytest.fixture()
def root(tmp_path, monkeypatch):
    before = dict(ui_state._status)
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    ui_state._status["running"] = None
    ui_shared._invalidate_scans()
    yield tmp_path
    ui_state._status.clear()
    ui_state._status.update(before)
    ui_shared._invalidate_scans()


def _run(root, asof, tag) -> str:
    """A closed run with a file and a weekly report; its id."""
    import time
    time.sleep(1.05)                     # run ids sort by their start second
    led = Ledger()
    rid = led.open_run(RunSpec(engine="all", forecast_date=asof,
                               locations=["Ohio"]), Path("pending"), {})
    w = root / "workroots" / rid
    d = w / "submission" / OR
    d.mkdir(parents=True)
    (d / f"{O._reference_date(asof)}-{OR}.csv").write_text(tag)
    (w / "report.html").write_text(f"<html><body>REPORT {tag}</body></html>")
    (w / "results.json").write_text(json.dumps(
        {"forecast_date": asof, "spec": "", "models": {}}))
    led.set_workroot(rid, w)
    led.close_run(rid, "ok", {})
    ui_shared._invalidate_scans()
    return rid


# ------------------------------------------------ the report names its run

def test_the_report_buttons_name_the_run_beside_as_of(root):
    first = _run(root, "2098-01-03", "first")
    latest = _run(root, "2098-01-10", "latest")
    html = client.get("/output").text
    card = html.split('id="weekly-report"', 1)[1].split("</div>\n", 1)[0]
    assert f'href="/runs/{latest}/report"' in card
    assert f'href="/runs/{latest}/report/download" download' in card
    assert first not in card
    # no link that means "whatever is newest when clicked"
    assert 'href="/output/report"' not in html
    assert 'href="/output/report/download"' not in html
    # beside "as of": the run, as the file rows name theirs
    when = f"{latest[4:6]}-{latest[6:8]} {latest[9:11]}:{latest[11:13]}"
    assert "as of 2098-01-10" in card
    assert f'<a href="/runs/{latest}">run {when}</a>' in card
    # the link serves that run's report, under the dated name
    r = client.get(f"/runs/{latest}/report/download")
    assert r.status_code == 200 and "REPORT latest" in r.text
    assert "FluBNF-weekly-report-2098-01-10.html" in \
        r.headers["content-disposition"]
    # a page left open keeps naming its own run's report
    _run(root, "2098-01-17", "newer")
    assert "REPORT latest" in client.get(
        f"/runs/{latest}/report/download").text
    # old bookmarks still answer: the newest run's
    assert "REPORT newer" in client.get("/output/report/download").text
    assert "REPORT newer" in client.get("/output/report").text


def test_a_run_report_route_takes_only_a_run_ids_shape(root):
    rid = _run(root, "2098-01-03", "real")
    assert client.get(f"/runs/{rid}/report").status_code == 200
    # a folder under workroots whose name is not a run id
    upper = "20980101T000000-ABCDEF"
    odd = root / "workroots" / upper
    odd.mkdir()
    (odd / "report.html").write_text("<html>NOT A RUN</html>")
    # and app state's own folder, reached through ".."
    (root / "report.html").write_text("<html>STATE ROOT</html>")
    for bad in (upper, "%2E%2E", "..x", rid + "0", "x" * 22):
        for tail in ("/report", "/report/download"):
            r = client.get(f"/runs/{bad}{tail}")
            assert r.status_code == 404, (bad, tail)
            assert "NOT A RUN" not in r.text and "STATE ROOT" not in r.text
            assert "No report for this run" in r.text
            assert 'href="/runs"' in r.text            # the way to Storage


# ---------------------------------------------------- the freshness stamp

def test_the_stamp_follows_the_newest_results_and_the_run(root):
    assert client.get("/api/output/stamp").json() == {
        "stamp": "", "running": False}
    first = _run(root, "2098-01-03", "first")
    assert client.get("/api/output/stamp").json() == {
        "stamp": first, "running": False}
    ui_state._status["running"] = "all:x"
    assert client.get("/api/output/stamp").json()["running"] is True
    second = _run(root, "2098-01-03", "second")
    ui_state._status["running"] = None
    assert client.get("/api/output/stamp").json() == {
        "stamp": second, "running": False}


def _script(html: str) -> str:
    """The Output page's freshness script, as rendered."""
    m = re.search(r"<script>\s*// fresh after a run.*?</script>", html, re.S)
    assert m, "the Output page carries no freshness script"
    return m.group(0)[len("<script>"):-len("</script>")]


def test_the_page_carries_its_stamp_and_the_checks(root):
    rid = _run(root, "2098-01-03", "only")
    html = client.get("/output").text
    js = _script(html)
    stamp = json.loads(re.search(r"var S=(\{[^}]*\})", js).group(1))
    assert stamp == {"stamp": rid, "running": False}
    for needle in ("'/api/output/stamp'", "addEventListener('pageshow'",
                   "addEventListener('focus'", "'visibilitychange'",
                   "window.GUARD_BUSY", "document.activeElement.form",
                   "location.reload()"):
        assert needle in js, needle
    ui_state._status["running"] = "all:x"
    js = _script(client.get("/output").text)
    assert json.loads(re.search(r"var S=(\{[^}]*\})", js).group(1)) == {
        "stamp": rid, "running": True}
    # every page: a page restored from the back/forward cache reloads
    assert "addEventListener('pageshow',e=>{if(e.persisted)location.reload();});" \
        in html


_HARNESS = """
var said=[], timers=[], on={}, don={};
var location={reload:function(){said.push('reload');}};
var window={GUARD_BUSY:false};
var document={hidden:false, activeElement:null,
  addEventListener:function(n,f){don[n]=f;}};
function addEventListener(n,f){on[n]=f;}
function setTimeout(f){timers.push(f);return timers.length;}
function clearTimeout(){}
var replies=[];
function fetch(url){said.push(url);var d=replies.shift();
  if(d&&d.down)return Promise.reject(new Error('no server'));
  var st=(d&&d.status)||200, b=(d&&d.status)?d.body:d;
  return Promise.resolve({ok:st<400,status:st,
    json:function(){return Promise.resolve(b);}});}
async function settle(){for(var i=0;i<8;i++)await Promise.resolve();}
async function tick(){var f=timers.shift();if(f)f();await settle();}
"""


def _js(script: str, stamp: dict, steps: str) -> list:
    """Run the freshness script against a stand-in page (node); what it
    fetched and whether it reloaded, in order."""
    src = re.sub(r"var S=\{[^}]*\}", "var S=" + json.dumps(stamp), script)
    prog = (_HARNESS + src + "\n(async function(){\n" + steps
            + "\nconsole.log(JSON.stringify(said));})();\n")
    out = subprocess.run([NODE, "-e", prog], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(not NODE, reason="no node")
def test_the_script_reloads_once_a_run_has_ended(root):
    _run(root, "2098-01-03", "only")
    js = _script(client.get("/output").text)
    url = "/api/output/stamp"
    idle = {"stamp": "A", "running": False}
    # nothing new: no reload
    assert _js(js, idle, "replies=[{stamp:'A',running:false}];"
               "on.pageshow();await settle();") == [url]
    # a newer run's results landed: reload
    assert _js(js, idle, "replies=[{stamp:'B',running:false}];"
               "on.focus();await settle();") == [url, "reload"]
    # a run is on: look again in a few seconds, reload once it has ended
    assert _js(js, idle, "replies=[{stamp:'A',running:true},"
               "{stamp:'B',running:true},{stamp:'B',running:false}];"
               "on.pageshow();await settle();await tick();await tick();"
               ) == [url, url, url, "reload"]
    # a run that ended with nothing new: no reload
    assert _js(js, idle, "replies=[{stamp:'A',running:true},"
               "{stamp:'A',running:false}];"
               "on.pageshow();await settle();await tick();") == [url, url]
    # rendered mid-run: reload once the run has ended, whatever the stamp
    assert _js(js, {"stamp": "A", "running": True},
               "replies=[{stamp:'A',running:false}];"
               "on.pageshow();await settle();") == [url, "reload"]
    # a focused form (or the guard modal) defers it; back in view resumes
    assert _js(js, idle, "document.activeElement={form:{}};"
               "replies=[{stamp:'B',running:false},{stamp:'B',running:false}];"
               "on.pageshow();await settle();"
               "document.activeElement=null;await tick();"
               ) == [url, url, "reload"]
    assert _js(js, idle, "window.GUARD_BUSY=true;"
               "replies=[{stamp:'B',running:false}];"
               "on.pageshow();await settle();") == [url]
    # a hidden window asks nothing until it is back in view
    assert _js(js, idle, "document.hidden=true;on.focus();await settle();"
               "document.hidden=false;replies=[{stamp:'B',running:false}];"
               "don.visibilitychange();await settle();") == [url, "reload"]


@pytest.mark.skipif(not NODE, reason="no node")
def test_a_failed_check_is_never_a_change(root):
    """An older server's 404 for the stamp route, a reply without a stamp,
    or no server at all: no reload (a reload there would repeat on every
    load). A page rendered mid-run keeps looking after a failed check."""
    _run(root, "2098-01-03", "only")
    js = _script(client.get("/output").text)
    url = "/api/output/stamp"
    idle = {"stamp": "A", "running": False}
    assert _js(js, idle, "replies=[{status:404,body:{detail:'Not Found'}}];"
               "on.pageshow();await settle();") == [url]
    assert _js(js, idle, "replies=[{detail:'x'}];"
               "on.pageshow();await settle();") == [url]
    assert _js(js, idle, "replies=[{down:true}];"
               "on.pageshow();await settle();") == [url]
    assert _js(js, {"stamp": "A", "running": True},
               "replies=[{down:true},{stamp:'B',running:false}];"
               "on.pageshow();await settle();await tick();"
               ) == [url, url, "reload"]


def test_a_page_rendered_without_a_stamp_has_no_check(root, monkeypatch):
    """A pull while the console runs reloads templates, not routes: an
    older output_page renders no stamp, and the page still renders."""
    _run(root, "2098-01-03", "only")
    real = O.templates.TemplateResponse

    def old_route(request, name, context, *a, **k):
        context = {k2: v for k2, v in context.items() if k2 != "stamp"}
        return real(request, name, context, *a, **k)
    monkeypatch.setattr(O.templates, "TemplateResponse", old_route)
    r = client.get("/output")
    assert r.status_code == 200 and "Weekly report" in r.text
    assert "// fresh after a run" not in r.text


def test_the_week_picker_offers_only_weeks_with_a_report(root):
    """A run whose report failed is archived without one; the picker's
    Download would save the 404 notice as a file, so that week is not
    offered."""
    _run(root, "2098-01-10", "only")
    (root / "archive" / "2098-01-03" / "submission").mkdir(parents=True)
    with_report = root / "archive" / "2098-01-10"
    with_report.mkdir(parents=True, exist_ok=True)
    (with_report / "report.html").write_text("<html>REPORT</html>")
    ui_shared._invalidate_scans()
    html = client.get("/output").text
    assert '<option value="2098-01-10">' in html
    assert '<option value="2098-01-03">' not in html
