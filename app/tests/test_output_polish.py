"""Output's speed, words and marks (bug hunt 2026-10-25, G32).

  * A file's hub checks are kept on disk, so a relaunch does not check
    every listed file again (OU-07).
  * The page's explainer is three lines, Your data's note one, and a
    line's failing checks open as a card's do (OU-10).
  * Each file's Download and Show in folder name the file (OU-13).
  * An open round's time left stays current, and the page reloads once
    when its badge changes (OU-14).
  * A notice's "?" names it with ids and names as written (OU-17).
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import hubcheck                                  # noqa: E402
from app.core.html_page import kit_macros                      # noqa: E402
from app.ui.routes import output as O                          # noqa: E402
from test_output_run_pages import (GH, OR, _due, _run, client,  # noqa: E402,F401
                                   root)

UI = Path(__file__).resolve().parents[1] / "ui" / "templates"


# ------------------------------------------------- OU-07: kept on disk

def test_hub_checks_are_kept_on_disk_across_a_relaunch(root, monkeypatch):
    _run(root, "2098-01-03", [GH])
    f = next(root.rglob("*.csv"))
    O._CHECKED.clear()
    O._CHECKS_READ.clear()
    s = O._check_summary(str(f))
    kept = json.loads((root / O.CHECKS_FILE).read_text(encoding="utf-8"))
    assert kept["rules"] == O._rules_digest() and len(kept["files"]) == 1
    # a relaunch: nothing in memory, the file unchanged, no check run
    O._CHECKED.clear()
    O._CHECKS_READ.clear()
    calls, check = [], hubcheck.summary
    monkeypatch.setattr(hubcheck, "summary",
                        lambda p: calls.append(p) or {"ok": False})
    again = O._check_summary(str(f))
    assert calls == [] and again["ok"] == s["ok"]
    assert again["due"] == s["due"]
    # a file written again: one entry for it, its newest version
    O._CHECKED.clear()
    O._CHECKS_READ.clear()
    monkeypatch.setattr(hubcheck, "summary", check)
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    O._check_summary(str(f))
    kept = json.loads((root / O.CHECKS_FILE).read_text(encoding="utf-8"))
    assert [r[:2] for r in kept["files"]] == [[str(f), f.stat().st_mtime_ns]]
    calls = []
    monkeypatch.setattr(hubcheck, "summary",
                        lambda p: calls.append(p) or {"ok": False})
    # other rules: the kept results are not read
    O._CHECKED.clear()
    O._CHECKS_READ.clear()
    monkeypatch.setattr(O, "_rules_digest", lambda: "other")
    O._check_summary(str(f))
    assert calls == [str(f)]


# ---------------------------------------------- OU-10: short, one style

def test_the_explainers_are_short_and_failing_lines_open_like_cards():
    page = (UI / "output.html").read_text(encoding="utf-8")
    about = page.split('{% set about %}', 1)[1].split("{% endset %}", 1)[0]
    assert about.count('<span class="uk-tt-line">') == 3
    assert len(re.sub(r"<[^>]+>", "", about).split()) < 110
    own = page.split('tips.heading("Your data", "out-own", "', 1)[1].split('"', 1)[0]
    assert len(own) < 120 and "23 levels" not in own
    # a line's failing checks: the cards' toggletip, not a tooltip
    assert ('tips.toggletip("out-lchk-" ~ di, "the hub check problems", '
            'title="Fails hub checks")') in page
    assert 'tips.badge("error", "fails hub checks", id="out-lchk-" ~ di) }}' in page


# ---------------------------------------------- OU-13: the file named

def test_each_files_controls_name_it(root):
    _run(root, "2098-01-03", [GH])
    html = client.get("/output").text
    name = f"2098-01-10-{GH}.csv"
    assert f'aria-label="Download {name}"' in html
    assert f'aria-label="Show {name} in folder"' in html


# ---------------------------------------- OU-14: the open round, live

def test_an_open_rounds_badge_changes_on_a_page_left_open(root, monkeypatch):
    utc = dt.timezone.utc
    due = O._date_status("2026-10-10", now=dt.datetime(2026, 10, 5, 19, tzinfo=utc))
    # its last 12 hours (11 PM EDT is 03:00 UTC), then the close
    assert due["flips"] == ["2026-10-07T15:00:00Z", "2026-10-08T03:00:00Z"]
    soon = O._date_status("2026-10-10", now=dt.datetime(2026, 10, 3, 12, tzinfo=utc))
    # the window opens at midnight Eastern on its first day (04:00 UTC)
    assert soon["state"] == "soon" and soon["flips"] == ["2026-10-04T04:00:00Z"]
    # a whole-day answer has no clock to flip by
    assert O._date_status("2026-10-10", today=dt.date(2026, 10, 5))["flips"] == []
    monkeypatch.setattr(O, "_date_status", lambda ref, today=None, now=None: {
        **_due(ref), "flips": ["2098-01-07T16:00:00Z", "2098-01-08T04:00:00Z"]})
    _run(root, "2098-01-03", [GH])
    html = client.get("/output").text
    assert ('<span data-out-left="2098-01-08T04:00:00Z">2 days 8 h left</span>'
            in html)
    assert 'data-out-flips="2098-01-07T16:00:00Z 2098-01-08T04:00:00Z"' in html
    assert "setInterval(tick,60000);" in html
    assert "sessionStorage.setItem('out-flip '+flips[i],'1')" in html


_CLOCK = r"""
var T0=Date.parse('2098-01-05T16:00:00Z'), now=T0, ticks=[], reloads=0,
    store={};
Date.now=function(){return now;};
var left={textContent:'2 days 12 h left',
  getAttribute:function(){return '2098-01-08T04:00:00Z';}};
var badge={getAttribute:function(){return '2098-01-05T17:00:00Z';}};
var document={hidden:false,activeElement:null,
  querySelectorAll:function(s){return s==='[data-out-left]'?[left]:[badge];},
  addEventListener:function(){}};
var window={}, location={reload:function(){reloads++;}};
var sessionStorage={getItem:function(k){return store[k]||null;},
  setItem:function(k,v){store[k]=v;}};
function setInterval(f){ticks.push(f);} function addEventListener(){}
"""


@pytest.mark.skipif(not shutil.which("node"), reason="no node")
def test_the_countdown_keeps_time_and_reloads_once_per_change(tmp_path):
    page = (UI / "output.html").read_text(encoding="utf-8")
    js = page.split("(function(){\n  var lefts=", 1)[1]
    js = "(function(){\n  var lefts=" + js.split("\n })();", 1)[0] + "\n })();"
    drv = tmp_path / "clock.js"
    drv.write_text(_CLOCK + js + r"""
var said=[];
function at(min){now=T0+min*60000;ticks[0]();
  said.push([left.textContent,reloads]);}
at(0); at(61); at(62);
console.log(JSON.stringify(said));
""", encoding="utf-8")
    out = subprocess.run([shutil.which("node"), str(drv)], capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    # the time left to the hour; one reload when the badge's hour passes,
    # none after it
    assert json.loads(out.stdout) == [["2 days 12 h left", 0],
                                      ["2 days 10 h left", 1],
                                      ["2 days 10 h left", 1]]


# ------------------------------------------- OU-17: names as written

def test_a_notices_tip_keeps_ids_and_names_as_written():
    k = kit_macros()
    html = str(k.empty("No run 20261025T184517-9a04d9 is recorded here",
                       tiptext="Its folder is gone.", id="out-notice"))
    assert 'aria-label="About no run 20261025T184517-9a04d9 is recorded here"' in html
    html = str(k.alert("warn", "FluSight window closed.", tiptext="x", id="a"))
    assert 'aria-label="About FluSight window closed"' in html
    html = str(k.alert("info", "Not run on Ohio.", tiptext="x", id="b"))
    assert 'aria-label="About not run on Ohio"' in html
