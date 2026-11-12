"""A figure too large to say (review 3 of #93, finding 3): a posted form
can carry any number, which the Retrospective page remembers and prices on
every visit. estimates.human and estimate.js human say nothing from
TOO_MANY_HOURS up, where Python's exact rounding gave up
(decimal.InvalidOperation) and the page's toFixed wrote "about 1e+33 h";
below it both read as before, and alike. Since the re-check's R5 the edge
is 1e9 hours, at either end of a span: above it a figure was float noise
("88477999999999983616.0 h"), and no form prices a run that long.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.core import estimates as ES

EST_JS = Path(__file__).resolve().parents[1] / "ui" / "static" / "estimate.js"
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")
NODE = shutil.which("node")
needs_js = pytest.mark.skipif(
    not (JSC.is_file() or NODE),
    reason="no JavaScript engine (JavaScriptCore jsc or node)")

EDGE = 3600 * ES.TOO_MANY_HOURS
#: (lo, hi) in seconds: ordinary spans, the last ones said, and too large
#: (the edge at either end; the review's long figures)
SPANS = [(600.0, 2400.0), (5400.0, 21600.0), (1e9, 4e9),
         (1e11, 3.5e12), (EDGE / 4, EDGE * (1 - 1e-15)), (EDGE / 4, EDGE),
         (EDGE, EDGE / 4), (1e18, 4e18), (1e23, 3.5e24), (1e24, 1e30),
         (1e30, 1e36), (1e300, 1e308)]


def _js(tmp_path, body):
    drv = ("var E = FluBNFEstimate;\n"
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


def test_a_figure_too_large_says_nothing():
    got = [ES.human(lo, hi) for lo, hi in SPANS]
    assert got[:2] == ["about 10 to 40 min", "about 1.5 to 6.0 h"]
    # up to the edge, as before: the exact figure in hours
    for (lo, hi), w in zip(SPANS[2:5], got[2:5]):
        assert w == "about %s to %s h" % (ES._js_fixed1(lo / 3600),
                                          ES._js_fixed1(hi / 3600))
    assert got[5:] == [""] * 7
    assert ES.TOO_MANY_HOURS == 1e9
    # a 40-digit or 400-digit particles figure: nothing, never an error
    for particles in (10 ** 40, 10 ** 400):
        try:
            sec = ES.run_seconds([14], 21, particles, 4)
        except OverflowError:
            sec = float("inf")
        assert ES.human(*ES.span(sec)) == ""
    assert ES.human(10 ** 400, 10 ** 400) == ""


@needs_js
def test_the_page_says_what_the_server_says(tmp_path):
    got = _js(tmp_path, "var cs = " + json.dumps(SPANS) + ", out = [];"
              " for (var i = 0; i < cs.length; i++)"
              " out.push(E.human(cs[i][0], cs[i][1])); return out;")
    assert got == [ES.human(lo, hi) for lo, hi in SPANS]
    assert "e+" not in json.dumps(got)
