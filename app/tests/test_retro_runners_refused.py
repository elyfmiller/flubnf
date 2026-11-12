"""The Retrospective's Oracle option prices only a runners width the run
accepts (review of #93, re-check at 099907c, finding 2).

The runners box is a number box: a browser lets "2e0", "2.0" and "1e1"
through, and the run's POST refuses them ("shard width: '2e0' is not a
whole number."). The option priced them at the default width. Now the
page's script (retro_progress.js FluBNFRetroCost) reads the box as the
POST reads what the box posts, and gives no figure when the POST
refuses it. A text the box cannot hold ("abc") is blank there, and so
posts blank: the default width, as before.

Each value goes through the real POST (the worker stubbed, recording the
width it was given) and through the page's own script on the page as
served (served_dom).
"""
from __future__ import annotations

import json
import re

import pytest

import served_dom as SD                                    # noqa: E402
from app.core.engines import pf                            # noqa: E402
from app.ui import retro_seasons as RS                     # noqa: E402
from app.ui import state as ui_state                       # noqa: E402
from app.ui.routes import retro as ui_retro                # noqa: E402

from test_retro_cost_refused import (                      # noqa: E402,F401
    BASE, EST_JS, LOCS, SAID, SEASON, START, TICKER_JS, WEEKS, _text,
    client, world)

#: what a browser's number box holds (HTML's valid floating-point number);
#: anything else it holds, and posts, as blank
HTML_FLOAT = re.compile(
    r"-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")

#: runners as typed: the review's three, others the box lets through,
#: whole numbers on and past the edges, and texts the box cannot hold
RUNNERS = ["2e0", "2.0", "1e1", "16.0", ".5", "-.5", "2E0", "1e-0",
           "-3", "0", "-0", "1", "2", "02", "16", "17", "99",
           "9" * 400, "0" * 4299 + "2", "0" * 4300 + "2",
           "", "abc", "1,000", " 2 ", "+2", "1_6"]


def _sent(typed: str) -> str:
    return typed if HTML_FLOAT.fullmatch(typed) else ""


def _post_reads(monkeypatch, sent: str):
    """The width the run's POST starts with for `sent`, or None when it
    refuses it (said in words, nothing started)."""
    launched = []
    monkeypatch.setattr(ui_retro, "_retro_bg",
                        lambda *a, **k: launched.append(a[2]))
    RS._retro_status.clear()
    ui_state._status.pop("flash", None)
    r = client.post("/retro/run", data={
        "season": SEASON, "locations": "panel6", "engine": "analogue",
        "knob.groundhog.zero_anchor": "level", "width": sent},
        follow_redirects=False)
    assert r.status_code == 303
    flash = ui_state._status.get("flash") or ""
    if not launched:
        assert (f"Not started: shard width: '{sent}' is not a whole "
                "number.") in flash, flash
        return None
    assert len(launched) == 1, flash
    return launched[0]


def _want(width) -> str:
    if width is None:
        return BASE
    return _text(RS._cost_words(WEEKS, START, LOCS * 3, 10_000, width))


@pytest.mark.skipif(not SD.HAVE_JS,
                    reason="no JavaScript engine (jsc or node)")
def test_the_option_prices_only_a_width_the_run_accepts(world, tmp_path,
                                                       monkeypatch):
    monkeypatch.setitem(ui_state._status, "running", None)
    monkeypatch.setitem(ui_state._status, "flash", None)
    reads = [_post_reads(monkeypatch, _sent(v)) for v in RUNNERS]
    # the review's values are refused by the run; whole numbers start it
    # at 1 to 16; blank (and what the box cannot hold) at the default
    assert reads[:3] == [None, None, None]
    assert dict(zip(RUNNERS, reads))["-3"] == 1
    assert dict(zip(RUNNERS, reads))["99"] == 16
    assert dict(zip(RUNNERS, reads))["abc"] == pf.DEFAULT_SHARD_WIDTH
    RS._retro_status.clear()
    ui_retro._last_retro_form.clear()
    html = client.get("/retro").text
    assert 'type="number" name="width"' in html
    got = SD.run(tmp_path, html, [EST_JS, TICKER_JS], SAID + """
      var out = [said()], i;
      for (i = 0; i < W.length; i++) out.push(set("width", W[i]));
      return out;""", prelude="var W = %s;" % json.dumps(RUNNERS))
    assert got[0] == _want(pf.DEFAULT_SHARD_WIDTH)
    assert got[1:] == [_want(w) for w in reads]
    # the review's values: no figure, where the default's was shown
    assert got[1:4] == [BASE] * 3
    assert got.count(BASE) == reads.count(None) > 5
