"""The Retrospective option's cost for a value the server refuses, and a
figure too large to read (review 3 of #93, re-check R5).

  * The page's script (retro_progress.js FluBNFRetroCost, on estimate.js)
    reads Particles and Independent Runs as the server's check does
    (app/core/knobs.py: blank is the default; commas and underscores
    dropped, then a whole number within the field's min and max) and
    gives the option no figure for anything the server refuses. After a
    refused hand post of 309 digits it priced 10,000 particles, and a
    value just past the field's max was priced as if it would run.
  * estimates.human and estimate.js human never write an exponent or a
    long run of float noise ("88477999999999983616.0 h"): nothing from
    TOO_MANY_HOURS up, at either end, and the two agree on every figure.
  * estimate.js keeps a count too long for a double (parseInt of 309
    digits) infinite, so its cost is no figure, as the server's
    OverflowError is; it was read as 0 and so as the reference 10,000.

The page is the one the server rendered, run with its own scripts
(served_dom), never a stand-in form.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient                  # noqa: E402

import served_dom as SD                                    # noqa: E402
from app.core import estimates, knobs, retro               # noqa: E402
from app.core.engines import pf                            # noqa: E402
from app.core.runs import RunSpec                          # noqa: E402
from app.ui import retro_seasons as RS                     # noqa: E402
from app.ui import server as srv                           # noqa: E402
from app.ui import shared as ui_shared                     # noqa: E402
from app.ui.routes import retro as ui_retro                # noqa: E402

client = TestClient(srv.app)

STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"
EST_JS, TICKER_JS = STATIC / "estimate.js", STATIC / "retro_progress.js"
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")
NODE = shutil.which("node")
needs_js = pytest.mark.skipif(not SD.HAVE_JS,
                              reason="no JavaScript engine (jsc or node)")

SEASON = "2098-99"
START = "2098-08-01"
WEEKS = ["2098-10-03", "2098-10-10", "2098-10-17", "2098-10-24"]
BASE = "Oracle SIHRS + Groundhog"
LOCS = 7                                  # the 6-state panel and US
PF_OPT = re.compile(r'<option value="pf" data-base="Oracle SIHRS \+ '
                    r'Groundhog">([^<]*)</option>')

#: Particles as typed: refused, accepted, and on the edges of both
PARTICLES = [
    "9" * 309, "9" * 400, "9" * 22, "9" * 30, "9" * 38,     # the review's
    "100001", "100000", "999", "1000", "0", "-5000", "-0",
    "2.5", "1e4", "abc", ",", "5 000", "+-5", "﻿5000",
    "20,000", "1_0000", " 5000 ", "+5000", "5000,", ", 5000",
    " 5000　", "\x1c5000",
    "0" * 4296 + "5000",                  # 4,300 digits: Python reads it
    "0" * 4297 + "5000",                  # 4,301: Python refuses it
    "",
]
#: Independent Runs as typed (Particles blank)
REPLICATES = ["11", "0", "x", "10", "2", "", "1,0", "3.0"]


@pytest.fixture
def world(tmp_path, monkeypatch):
    """An empty retro root, SEASON with four hub weeks, the worker stubbed
    and the remembered form cleared."""
    rr = tmp_path / "retro"
    rr.mkdir()
    monkeypatch.setattr(RS, "RETRO_ROOT", rr)
    monkeypatch.setattr(RS, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(retro, "available_seasons", lambda: [SEASON])
    monkeypatch.setattr(retro, "season_vintages",
                        lambda s: list(WEEKS) if s == SEASON else [])
    monkeypatch.setattr(ui_retro, "_retro_bg", lambda *a, **k: None)
    status, form = dict(RS._retro_status), dict(ui_retro._last_retro_form)
    RS._retro_status.clear()
    ui_retro._last_retro_form.clear()
    ui_shared._invalidate_scans()
    yield rr
    RS._retro_status.clear()
    RS._retro_status.update(status)
    ui_retro._last_retro_form.clear()
    ui_retro._last_retro_form.update(form)
    ui_shared._invalidate_scans()


def _text(words: str) -> str:
    return BASE + (f" ({words})" if words else "")


def _server_reads(key: str, raw: str):
    """What the server's check makes of `raw` for knob `key`: its value
    (blank: the default), or None when it refuses it."""
    try:
        got = knobs.parse({key: raw}, "all")
    except knobs.KnobError:
        return None
    return got.get(key, knobs.BY_KEY[key].default)


def _want(particles, replicates) -> str:
    if particles is None or replicates is None:
        return BASE
    return _text(RS._cost_words(WEEKS, START, LOCS * replicates, particles,
                                pf.DEFAULT_SHARD_WIDTH))


SAID = """
var fm = document.getElementById("rt-run-form");
FluBNFRetroCost.bind(fm);
function said() {
  return fm.querySelector('#retro-engine option[value="pf"]').textContent;
}
function set(name, v) {
  var f = fm.elements.namedItem(name);
  f.value = v;
  f.fire("input");
  return said();
}
"""


@needs_js
def test_the_script_says_nothing_for_what_the_server_refuses(world,
                                                             tmp_path):
    """Each value typed into Particles, then Independent Runs, on the page
    as served: no figure for what the server's check refuses, else the
    figure the server's rule gives for the value it reads."""
    html = client.get("/retro").text
    assert PF_OPT.search(html).group(1) == _want(10_000, 3)
    got = SD.run(tmp_path, html, [EST_JS, TICKER_JS], SAID + """
      var out = [said()], i;
      for (i = 0; i < P.length; i++) out.push(set("particles", P[i]));
      set("particles", "");
      for (i = 0; i < R.length; i++) out.push(set("replicates", R[i]));
      return out;""", prelude="var P = %s, R = %s;" % (
        json.dumps(PARTICLES), json.dumps(REPLICATES)))
    want = [_want(10_000, 3)]
    want += [_want(_server_reads("pf.particles", v), 3) for v in PARTICLES]
    want += [_want(10_000, _server_reads("pf.replicates", v))
             for v in REPLICATES]
    assert got == want
    # both kinds are here: refused values and accepted ones
    refused = [v for v in PARTICLES
               if _server_reads("pf.particles", v) is None]
    assert len(refused) > 10 and len(refused) < len(PARTICLES) - 5
    assert got.count(BASE) == len(refused) + sum(
        _server_reads("pf.replicates", v) is None for v in REPLICATES)


@needs_js
@pytest.mark.parametrize("digits", [309, 25])
def test_after_a_refused_post_the_page_and_its_script_agree(world, tmp_path,
                                                            digits):
    """The review's case: a hand-made post of a huge Particles, refused;
    the page that remembers it shows the option without a figure, and its
    script, run on that page, keeps it so."""
    r = client.post("/retro/run", data={
        "season": SEASON, "locations": "panel6", "engine": "pf",
        "mode": "resume", "particles": "9" * digits},
        follow_redirects=False)
    assert r.status_code == 303
    assert ui_retro._last_retro_form.get("particles") == "9" * digits
    html = client.get("/retro").text
    assert PF_OPT.search(html).group(1) == BASE
    got = SD.run(tmp_path, html, [EST_JS, TICKER_JS],
                 SAID + "return [said(), fm.elements.namedItem("
                 "'particles').value];")
    assert got == [BASE, "9" * digits]


# ------------------------------------------------ the words, either side

LONG_RUN = re.compile(r"\d{11,}")


def _clean(words: str) -> bool:
    """No exponent and no run of float noise in a figure."""
    return not re.search(r"e[+-]?\d", words) and not LONG_RUN.search(words)


def _js(tmp_path, prelude: str, body: str):
    drv = (prelude + "\nvar E = FluBNFEstimate;\n"
           "print(JSON.stringify((function(){ " + body + " })()));\n")
    if JSC.is_file():
        d = tmp_path / "driver.js"
        d.write_text(drv, encoding="utf-8")
        cmd = [str(JSC), str(EST_JS), str(d)]
    else:
        both = tmp_path / "both.js"
        both.write_text("var print = function(s){ console.log(s); };\n"
                        + EST_JS.read_text(encoding="utf-8") + "\n" + drv,
                        encoding="utf-8")
        cmd = [NODE, str(both)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, (out.stderr or out.stdout)
    return json.loads(out.stdout.strip().splitlines()[-1])


#: spans in seconds, around and past TOO_MANY_HOURS, with lo above hi too
EDGE = 3600 * estimates.TOO_MANY_HOURS
SPANS = [(600.0, 2400.0), (5400.0, 21600.0), (EDGE / 4, EDGE * 0.999),
         (EDGE / 4, EDGE), (EDGE, EDGE / 4), (1e30, 30.0),
         (3.2e23, 3.18528e23), (1e18, 4e18), (1e23, 3.5e24),
         (1e30, 1e36), (1e300, 1e308)]


def _py_words(digits: int) -> str:
    """The server's words for a Particles of `digits` nines (the season's
    four weeks, 21 fits, width 4, private engine)."""
    try:
        sec = estimates.run_seconds([14, 15, 16, 17], 21, int("9" * digits),
                                    4, "private")
    except OverflowError:
        return ""
    return estimates.human(*estimates.span(sec))


@needs_js
def test_no_figure_is_ever_an_exponent_or_float_noise(tmp_path):
    """Every Particles length from 1 to 400 digits, priced either side
    (the page's parseInt turns 309 digits into Infinity), and spans around
    the edge: the two agree, and no figure is an exponent or float
    noise."""
    attrs = estimates.page_params(4, "private")
    got = _js(tmp_path, "var ATTRS = %s, SPANS = %s;" % (
        json.dumps(attrs), json.dumps(SPANS)), """
      var p = E.params({getAttribute: function (n) {
        return ATTRS.hasOwnProperty(n) ? ATTRS[n] : null; }});
      var out = [], s, d, digits = "";
      for (d = 1; d <= 400; d++) {
        digits += "9";
        s = E.seconds([14, 15, 16, 17], 21, parseInt(digits, 10), 4, p);
        var sp = E.span(s, null, p.first);
        out.push(E.human(sp[0], sp[1]));
      }
      for (var i = 0; i < SPANS.length; i++)
        out.push(E.human(SPANS[i][0], SPANS[i][1]));
      return out;""")
    want = [_py_words(d) for d in range(1, 401)]
    want += [estimates.human(lo, hi) for lo, hi in SPANS]
    assert got == want
    assert all(_clean(w) for w in got)
    # an ordinary figure is still said; the review's figures are not
    assert got[3].startswith("about ") and got[4].startswith("about ")
    assert got[21] == got[308] == got[399] == ""
    assert got[400:402] == ["about 10 to 40 min", "about 1.5 to 6.0 h"]
    assert got[402].startswith("about ") and got[403:] == [""] * 8


def test_the_server_says_nothing_past_the_edge():
    """TOO_MANY_HOURS is far past any run, and below it every figure is
    plain digits."""
    assert estimates.TOO_MANY_HOURS <= 1e9
    for d in range(1, 401):
        assert _clean(_py_words(d))
    for lo, hi in SPANS:
        w = estimates.human(lo, hi)
        assert _clean(w)
        if max(lo, hi) >= EDGE:
            assert w == ""
    # the review's figure: 22 digits of Particles
    assert _py_words(22) == ""
    # within every field's bounds the most a Retrospective form prices
    # (100,000 particles, 10 runs, every location, one runner, a long
    # season, the public engine) is a figure
    most = estimates.run_seconds(list(range(1, 61)), 54 * 10, 100_000, 1,
                                 "public")
    w = estimates.human(*estimates.span(most))
    assert w.startswith("about ") and w.endswith(" h") and _clean(w)
    # the defaults on this page still have their figure
    assert RunSpec.particles == 10_000
