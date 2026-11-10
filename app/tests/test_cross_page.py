"""Across pages (bug hunt 2026-10-25, G35).

  * With the browser's storage blocked, a page follows the OS's theme and
    contrast, and the Display menu's switches still turn and say so: no
    read or write of storage can stop the page's scripts (UI-12).
  * One count of places: 52 jurisdictions (the states, DC and Puerto
    Rico), and 53 locations with US national; US is never called a
    jurisdiction (UI-15).
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                      # noqa: E402

from app.ui import server as srv                               # noqa: E402

client = TestClient(srv.app)
NODE = shutil.which("node")
UI = Path(__file__).resolve().parents[1] / "ui"

# a page whose storage throws, as Safari's does with site data blocked
_PAGE = r"""
function boom(){throw new Error('SecurityError');}
var store={getItem:boom,setItem:boom,removeItem:boom};
var localStorage=store, sessionStorage=store, errors=[];
function El(){this.a={};this.style={};this.dataset={};}
El.prototype.setAttribute=function(k,v){this.a[k]=String(v);};
El.prototype.getAttribute=function(k){return k in this.a?this.a[k]:null;};
El.prototype.removeAttribute=function(k){delete this.a[k];};
var de=new El(), btn=new El(); btn.dataset.ax='contrast';
var document={documentElement:de,
  querySelectorAll:function(s){return s.indexOf('data-ax')>=0?[btn]:[];}};
function matchMedia(q){return {matches:q.indexOf('dark')>=0};}
function dispatchEvent(){} function Event(){}
"""


def _scripts():
    """The first-paint script and the a11y switches, as a page carries
    them."""
    html = client.get("/methods").text
    boot = html.split("// before first paint", 1)[1]
    boot = boot[boot.index("(function(){"):]
    boot = boot[:boot.index("})();") + len("})();")]
    sw = html.split("// accessibility modes:", 1)[1].split(
        "// text-size control:", 1)[0]
    return boot, sw[sw.index("(function(){"):]


@pytest.mark.skipif(not NODE, reason="no node to run the page's scripts")
def test_with_storage_blocked_a_page_follows_the_os_and_its_switches_work(
        tmp_path):
    boot, sw = _scripts()
    drv = tmp_path / "blocked.js"
    drv.write_text(
        _PAGE + "try{\n" + boot + "\n" + sw + "\n"
        "btn.onclick();\n"
        "}catch(e){errors.push(String(e));}\n"
        "console.log(JSON.stringify({theme:de.getAttribute('data-theme'),"
        "contrast:de.getAttribute('data-contrast'),"
        "checked:btn.getAttribute('aria-checked'),"
        "size:de.style.fontSize,errors:errors}));\n",
        encoding="utf-8")
    out = subprocess.run([NODE, str(drv)], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {
        "theme": "dark", "contrast": "high", "checked": "true",
        "size": "100%", "errors": []}


def test_every_storage_call_in_the_shell_is_guarded():
    base = (UI / "templates" / "base.html").read_text(encoding="utf-8")
    for line in base.splitlines():
        if re.search(r"(local|session)Storage\.", line):
            assert "try{" in line or line.lstrip().startswith(
                ("v=localStorage.getItem", "//")), line


def test_us_national_is_a_location_never_a_jurisdiction():
    pages = {p: client.get(p).text for p in ("/", "/forecast", "/data",
                                             "/methods", "/retro")}
    for p, html in pages.items():
        assert "53 jurisdictions" not in html, p
    assert "<b>all 53 locations</b>" in pages["/forecast"]
    # a run of them all says so in its progress label
    from app.ui.routes import forecast as fc
    assert fc._scope_label([f"S{i}" for i in range(52)] + ["US"]) == "all 53 locations"
    assert "<li><b>52</b> jurisdictions plus US national</li>" in pages["/"]
    tile = pages["/methods"].split('id="mt-locs">', 1)[1].split("</dd>", 1)[0]
    assert re.sub(r"<[^>]+>", " ", tile).split() == \
        "53 locations: 52 jurisdictions plus the national total".split()
    # the public site reads the tile as it is, with no rewrite of its own
    from app.core import site_build
    assert not hasattr(site_build, "_LOCS_TILE")
    # a replay's "all" is the 52; US national is its own box there
    assert ">all 52 jurisdictions</option>" in pages["/retro"]
    data = (UI / "templates" / "data.html").read_text(encoding="utf-8")
    assert 'tips.stat("Jurisdictions"' not in data
