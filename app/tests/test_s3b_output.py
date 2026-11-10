"""Output's second review pass (G32, #94: OU-07, OU-17, OU-14).

  * Two requests checking files at once: a result added while another
    request writes the kept results neither fails that request nor the
    Output page (OU-07).
  * The kept results file holds one entry per file, its newest version,
    for every file still there, past 512 files too; a deleted file leaves
    it at the next write, and past the bound the file checked longest ago
    goes first. The README names the file (OU-07).
  * A notice's "?" keeps a leading name as written: a jurisdiction, US, a
    model or data name (OU-17).
  * The page carries the server's clock, and a page left open reloads at
    a badge change by that clock, not the browser's (OU-14).
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                               # noqa: E402
from app.core import hubcheck                                  # noqa: E402
from app.core.html_page import kit_macros                      # noqa: E402
from app.ui import server as srv                               # noqa: E402
from app.ui.routes import output as O                          # noqa: E402
from test_output_polish import _CLOCK, UI                      # noqa: E402
from test_output_run_pages import GH, _due, _run, root         # noqa: E402,F401

REPO = Path(__file__).resolve().parents[2]


def _ok(path):
    """hubcheck.summary's shape for a file that passes."""
    return {"ok": True, "round": False, "problems": [],
            "reference_date": "", "due": None}


def _kept(state: Path) -> list:
    return json.loads((state / O.CHECKS_FILE).read_text(encoding="utf-8")
                      )["files"]


def _paths_in_memory() -> set:
    return {k if isinstance(k, str) else k[0] for k in list(O._CHECKED)}


@pytest.fixture()
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    O._CHECKED.clear()
    O._CHECKS_READ.clear()
    yield tmp_path
    O._CHECKED.clear()
    O._CHECKS_READ.clear()


@pytest.fixture()
def clean_checks():
    O._CHECKED.clear()
    O._CHECKS_READ.clear()
    yield
    O._CHECKED.clear()
    O._CHECKS_READ.clear()


def _csv(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / f"{name}.csv"
    f.write_bytes(b"x")
    return f


# ------------------------------------- OU-07: two requests at once

def _race(monkeypatch, other: Path) -> dict:
    """While the first request walks the results to write them, a second
    thread checks `other` (adds its result). The first walker waits until
    that result is in or the second thread ends, never more than 5 s, so a
    fix that holds a lock over the walk cannot hang here."""
    real = O._keepable
    fired = threading.Event()
    out = {"errors": []}

    def second():
        try:
            O._check_summary(str(other))
        except BaseException as e:                 # noqa: BLE001
            out["errors"].append(e)
    t2 = threading.Thread(target=second, daemon=True)
    out["thread"] = t2

    def walking() -> bool:
        f = sys._getframe(2)
        while f is not None:
            if f.f_code.co_name == "_keep_checks":
                return True
            f = f.f_back
        return False

    def hooked(s):
        if (not fired.is_set() and threading.current_thread() is not t2
                and walking()):
            fired.set()
            t2.start()
            end = time.monotonic() + 5
            while (time.monotonic() < end and t2.is_alive()
                   and str(other) not in _paths_in_memory()):
                time.sleep(0.005)
        return real(s)
    monkeypatch.setattr(O, "_keepable", hooked)
    out["fired"] = fired
    return out


def test_a_result_added_while_the_results_are_written_fails_no_request(
        state, monkeypatch):
    monkeypatch.setattr(hubcheck, "summary", _ok)
    a, b = _csv(state / "f", "a"), _csv(state / "f", "b")
    race = _race(monkeypatch, b)
    O._check_summary(str(a))          # the walk the second thread changes
    race["thread"].join(10)
    assert race["fired"].is_set() and not race["thread"].is_alive()
    assert race["errors"] == []
    # both results reach the disk: the later write has both
    assert sorted(r[0] for r in _kept(state)) == sorted([str(a), str(b)])


def test_the_output_page_answers_while_another_request_adds_a_result(
        root, monkeypatch, clean_checks):                  # noqa: F811
    _run(root, "2098-01-03", [GH])
    other = _csv(root / "elsewhere", f"2098-01-10-{GH}")
    race = _race(monkeypatch, other)
    r = TestClient(srv.app, raise_server_exceptions=False).get("/output")
    race["thread"].join(10)
    assert race["fired"].is_set() and race["errors"] == []
    assert r.status_code == 200, r.text[-400:]
    assert f"2098-01-10-{GH}.csv" in r.text


# ------------------------------------- OU-07: the kept results file

def test_past_512_files_the_kept_file_holds_each_files_newest_result(
        state, monkeypatch):
    monkeypatch.setattr(hubcheck, "summary", _ok)
    files = [_csv(state / "f", f"{i:03d}") for i in range(600)]
    for f in files:
        O._check_summary(str(f))
    # one file written again: its newest version replaces the older one
    st = files[7].stat()
    os.utime(files[7], ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    O._check_summary(str(files[7]))
    want = {str(f): [f.stat().st_mtime_ns, f.stat().st_size] for f in files}
    kept = _kept(state)
    assert len(kept) == 600 and {r[0]: r[1:3] for r in kept} == want
    assert len(O._CHECKED) == 600
    # a deleted file leaves it at the next write, in memory too
    files[3].unlink()
    new = _csv(state / "f", "new")
    O._check_summary(str(new))
    kept = {r[0] for r in _kept(state)}
    assert str(files[3]) not in kept and str(new) in kept
    assert len(kept) == 600 and str(files[3]) not in _paths_in_memory()
    # a relaunch reads them all back: no file is checked again
    O._CHECKED.clear()
    O._CHECKS_READ.clear()
    calls = []
    monkeypatch.setattr(hubcheck, "summary",
                        lambda p: calls.append(p) or _ok(p))
    for f in files[:3] + files[4:] + [new]:
        O._check_summary(str(f))
    assert calls == []


def test_past_the_bound_the_file_checked_longest_ago_goes_first(
        state, monkeypatch):
    monkeypatch.setattr(hubcheck, "summary", _ok)
    monkeypatch.setattr(O, "CHECKS_MAX", 4)
    a, b, c, d, e = (_csv(state / "f", n) for n in "abcde")
    for f in (a, b, c):
        O._check_summary(str(f))
    st = a.stat()
    os.utime(a, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    O._check_summary(str(a))          # a again: one entry, now the newest
    assert len(O._CHECKED) == 3
    O._check_summary(str(d))
    O._check_summary(str(e))          # five files: b, checked longest ago, goes
    assert [r[0] for r in _kept(state)] == [str(c), str(a), str(d), str(e)]
    assert _paths_in_memory() == {str(c), str(a), str(d), str(e)}
    # a relaunch under a smaller bound keeps the newest
    monkeypatch.setattr(O, "CHECKS_MAX", 2)
    O._CHECKED.clear()
    O._CHECKS_READ.clear()
    O._read_checks()
    assert list(O._CHECKED) == [str(d), str(e)]


def test_the_readme_names_the_kept_results_file():
    readme = (REPO / "README.md").read_text(encoding="utf-8").replace(
        "\r\n", "\n")
    para = readme.split("`app/state/` (ledger and retrospectives)", 1)[1]
    para = para.split("\n\n", 1)[0]
    assert f"`app/state/{O.CHECKS_FILE}`" in para
    assert "delete it at any time" in para and "checks run again" in para


# ------------------------------------- OU-17: a leading name as written

def _label(html: str) -> str:
    return re.search(r'aria-label="(About [^"]*)"', html).group(1)


def test_a_notices_tip_keeps_a_leading_name_as_written():
    k = kit_macros()
    for title, want in (
            ("Ohio reads 0", "About Ohio reads 0"),
            ("Groundhog has no donors.", "About Groundhog has no donors"),
            ("New York reads 0", "About New York reads 0"),
            ("District of Columbia is late", "About District of Columbia is late"),
            ("Puerto Rico's file is late", "About Puerto Rico&#39;s file is late"),
            ("Oracle step not applied", "About Oracle step not applied"),
            ("US reads 0", "About US reads 0"),
            # ordinary sentence starts are still lowered
            ("New run started", "About new run started"),
            ("No run 20261025T184517-9a04d9 is recorded here",
             "About no run 20261025T184517-9a04d9 is recorded here"),
            ("Not run on Ohio.", "About not run on Ohio"),
            ("Ohioans", "About ohioans")):
        assert _label(str(k.alert("warn", title, tiptext="x", id="a"))) == want
        empty = _label(str(k.empty(title, tiptext="x", id="e")))
        # the empty state's title is not trimmed of its period
        assert empty.rstrip(".") == want


def test_every_jurisdiction_is_a_kept_name():
    import csv
    with open(REPO / "flubnf" / "data" / "locations.csv",
              newline="", encoding="utf-8") as fh:
        names = {r["location_name"] for r in csv.DictReader(fh)}
    assert len(names) == 53 and "US" in names
    assert names <= set(kit_macros().KEEP_NAMES)


# ------------------------------------- OU-14: the server's clock

def test_the_output_page_carries_the_servers_clock(root, monkeypatch):  # noqa: F811
    monkeypatch.setattr(O, "_date_status", lambda ref, today=None, now=None: {
        **_due(ref), "flips": ["2098-01-07T16:00:00Z", "2098-01-08T04:00:00Z"]})
    _run(root, "2098-01-03", [GH])
    before = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    html = TestClient(srv.app).get("/output").text
    after = dt.datetime.now(dt.timezone.utc)
    (stamp,) = re.findall(r'<script data-out-now="([^"]+)">', html)
    t = dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.timezone.utc)
    assert before <= t <= after
    # the countdown reads it
    assert "var now=Date.now()+gap," in html
    assert "srv=document.querySelectorAll('[data-out-now]')" in html


def _countdown(tmp_path, stamp: str, minutes) -> list:
    """The page's own countdown under node (test_output_polish's harness),
    the browser's clock at 2098-01-05T16:00Z when the page loads and the
    server's stamped at `stamp`; [time left, reloads] at each minute."""
    page = (UI / "output.html").read_text(encoding="utf-8")
    js = page.split("(function(){\n  var lefts=", 1)[1]
    js = "(function(){\n  var lefts=" + js.split("\n })();", 1)[0] + "\n })();"
    drv = tmp_path / "clock.js"
    drv.write_text(_CLOCK + (
        "stamps=[{getAttribute:function(){return %s;}}];\n" % json.dumps(stamp))
        + js + r"""
var said=[];
function at(min){now=T0+min*60000;ticks[0]();
  said.push([left.textContent,reloads]);}
""" + "".join(f"at({m});" for m in minutes)
        + "\nconsole.log(JSON.stringify(said));\n", encoding="utf-8")
    out = subprocess.run([shutil.which("node"), str(drv)], capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="no node")
def test_a_browser_clock_ahead_waits_for_the_servers_badge_change(tmp_path):
    # the browser 30 min ahead: the badge's change at 17:00 comes at the
    # browser's 17:30, once, and the time left is the server's
    said = _countdown(tmp_path, "2098-01-05T15:30:00Z", [0, 61, 89, 91, 92])
    assert said == [["2 days 12 h left", 0],
                    ["2 days 11 h left", 0],
                    ["2 days 11 h left", 0],
                    ["2 days 10 h left", 1],
                    ["2 days 10 h left", 1]]


@pytest.mark.skipif(not shutil.which("node"), reason="no node")
def test_a_browser_clock_behind_reloads_when_the_server_passes_the_change(
        tmp_path):
    said = _countdown(tmp_path, "2098-01-05T16:30:00Z", [0, 29, 31, 32])
    assert [r for _, r in said] == [0, 0, 1, 1]
