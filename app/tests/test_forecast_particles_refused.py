"""The Forecast page's time line prices only Particles and Independent
Runs the run accepts (review of #93, re-check at 099907c, finding 3).

Particles is a number box: a browser lets "1e4" through (within its min
and max), and the run's check refuses it ("Particles: '1e4' is not a whole
number."). The time line showed the default's figure. Now the page's
script (forecast_form.js) reads each box as the server's check
(app/core/knobs.py) reads what the box posts, as the Retrospective's
script does (retro_progress.js knobWhole), and hides the line when the
check refuses it. A text the box cannot hold ("x") is blank there, and so
posts blank: the default, as before.

The page is the one the server rendered, run with its own scripts
(served_dom); no run is posted.
"""
from __future__ import annotations

import json
import re

import pytest

from app.core import knobs
from app.ui import pipeline
from app.ui.routes import forecast as FC

import served_dom as SD                                # noqa: E402
from test_datasets_ui import client, isolated          # noqa: E402,F401
from test_forecast_runrow import (                     # noqa: E402,F401
    W3, _page, _served, hub, today)

#: what a browser's number box holds (HTML's valid floating-point number);
#: anything else it holds, and posts, as blank
HTML_FLOAT = re.compile(
    r"-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")

#: Particles as typed: the review's, others the box lets through, whole
#: numbers on and past the field's edges, and texts the box cannot hold
PARTICLES = ["1e4", "1E4", "10000.0", "2.5e3", "1e5", "-10000", "0", "999",
             "1000", "100000", "100001", "40000", "040000", "9" * 400,
             "0" * 4295 + "40000", "0" * 4296 + "40000",
             "", "x", "10,000", " 5000 ", "+5000"]
#: Independent Runs as typed (Particles blank)
REPLICATES = ["1e0", "2.0", "0", "11", "-1", "1", "10", "", "x"]


def _server_reads(key: str, typed: str):
    """What the run's check makes of what the box posts for `typed`: its
    value (blank: the default), or None when it refuses it."""
    sent = typed if HTML_FLOAT.fullmatch(typed) else ""
    try:
        got = knobs.parse({key: sent}, "all")
    except knobs.KnobError:
        return None
    return got.get(key, knobs.BY_KEY[key].default)


@pytest.mark.skipif(not SD.HAVE_JS,
                    reason="no JavaScript engine (jsc or node)")
def test_the_line_prices_only_what_the_run_accepts(tmp_path, hub,
                                                   monkeypatch):
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "ready")
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    html = _page().text
    box = re.search(r'<input type="number"[^>]*data-knob="pf.particles"'
                    r'[^>]*>', html).group(0)
    assert 'min="1000"' in box and 'max="100000"' in box
    got = _served(tmp_path, html, W3, """
      var P = %s, R = %s, out = [time()], i;
      for (i = 0; i < P.length; i++) {
        set('[data-knob="pf.particles"]', P[i], "input"); out.push(time());
      }
      set('[data-knob="pf.particles"]', "", "input");
      for (i = 0; i < R.length; i++) {
        set('[data-knob="pf.replicates"]', R[i], "input"); out.push(time());
      }
      return out;""" % (json.dumps(PARTICLES), json.dumps(REPLICATES)))
    parts = [_server_reads("pf.particles", v) for v in PARTICLES]
    reps = [_server_reads("pf.replicates", v) for v in REPLICATES]
    want = [FC.run_words("all", 53, 3, 10_000, W3)]
    want += [FC.run_words("all", 53, 3, p, W3) for p in parts]
    want += [FC.run_words("all", 53, r, 10_000, W3) for r in reps]
    assert got == want
    # the review's value: refused by the run, so no line, where the
    # default's figure was shown
    assert parts[0] is None and got[1] == ""
    assert got[0].startswith("Oracle SIHRS and Groundhog, 53 locations: ")
    # both kinds are here: refused values and accepted ones
    assert parts.count(None) > 8 and reps.count(None) > 3
    assert got.count("") == parts.count(None) + reps.count(None)
