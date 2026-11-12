"""The server's first paint prices only values the run accepts (review of
#93 at d160002b, finding 5).

The page scripts read the Retrospective's runners box (retro_progress.js
runners) and the Forecast form's Particles and Independent Runs
(forecast_form.js knobWhole) as the run reads what each number box posts,
and give no figure for a value the run refuses. The server's own first
paint still read digits only, so after a refused POST the page came back
with the Oracle option, or the Run row's time line, priced at the
default (for good without script; until the script ran with it):

  * routes/retro._form_costs: a remembered runners "2e0" priced at the
    default width;
  * routes/forecast._run_estimate: a remembered Particles "1e4" priced at
    the default 10,000.

Now each reads as the run does: what the box can hold (HTML's valid
floating-point number, else blank), then the POST's or the check's own
reading. The page as served says what its script says on the same page
before any change.
"""
from __future__ import annotations

import re

import pytest

import served_dom as SD                                    # noqa: E402
from app.core import knobs
from app.core.engines import pf
from app.ui import pipeline
from app.ui import retro_seasons as RS
from app.ui import state as ui_state
from app.ui.routes import forecast as FC
from app.ui.routes import retro as ui_retro

from test_retro_cost_refused import (                      # noqa: E402,F401
    BASE, EST_JS, PF_OPT, SAID, SEASON, TICKER_JS, client, world)
from test_retro_runners_refused import (                   # noqa: E402
    RUNNERS, _post_reads, _sent, _want)
from test_forecast_runrow import (                         # noqa: E402,F401
    W3, _page, _served, hub, today)
from test_forecast_particles_refused import (              # noqa: E402
    PARTICLES, REPLICATES, _server_reads)
from test_datasets_ui import isolated                      # noqa: E402,F401

needs_js = pytest.mark.skipif(not SD.HAVE_JS,
                              reason="no JavaScript engine (jsc or node)")

#: the review's runners values: the run refuses each
REFUSED_RUNNERS = ["2e0", "2.0", "1e1"]


# ------------------------------------------------- the Retrospective's runners

def _retro_first_paint(width: str) -> str:
    """The Oracle option as the server first paints it, with `width` the
    runners the last POST held."""
    ui_retro._last_retro_form.clear()
    ui_retro._last_retro_form.update({
        "season": SEASON, "locations": "panel6", "engine": "pf",
        "width": width})
    RS._retro_status.clear()
    return client.get("/retro").text


def test_a_refused_runners_value_gets_no_figure(world):
    for v in REFUSED_RUNNERS:
        html = _retro_first_paint(v)
        assert f'name="width" value="{v}"' in html
        assert PF_OPT.search(html).group(1) == BASE, v
    # an accepted one keeps its figure, the default's for blank
    assert PF_OPT.search(_retro_first_paint("2")).group(1) == _want(2)
    assert PF_OPT.search(_retro_first_paint("")).group(1) == \
        _want(pf.DEFAULT_SHARD_WIDTH)


def test_the_first_paint_prices_what_the_post_would_run(world, monkeypatch):
    """Every runners value: the option as served is priced at the width
    the real POST starts with for what the box posts, or has no figure
    where the POST refuses it."""
    monkeypatch.setitem(ui_state._status, "running", None)
    monkeypatch.setitem(ui_state._status, "flash", None)
    reads = [_post_reads(monkeypatch, _sent(v)) for v in RUNNERS]
    got = [PF_OPT.search(_retro_first_paint(v)).group(1) for v in RUNNERS]
    assert got == [_want(w) for w in reads]
    assert got.count(BASE) == reads.count(None) > 5


@needs_js
def test_the_retro_script_keeps_what_the_server_painted(world, tmp_path):
    got, want = [], []
    for i, v in enumerate(RUNNERS):
        html = _retro_first_paint(v)
        want.append(PF_OPT.search(html).group(1))
        got.append(SD.run(tmp_path / str(i), html, [EST_JS, TICKER_JS],
                          SAID + "return said();"))
    assert got == want


# ------------------------------------- the Forecast form's Particles and Runs

def _fc_line(html: str) -> str:
    """The Run row's time line as served ("" while hidden)."""
    box = re.search(r'<div id="fc-est"[^>]*>', html).group(0)
    if " hidden" in box:
        return ""
    return re.search(r'<span class="uk-sr">Run time: </span><span>'
                     r'([^<]*)</span>', html).group(1)


def _fc_first_paint(key: str, value: str) -> str:
    return _page({"knobs": {key: value}}).text


@pytest.fixture
def engine_ready(monkeypatch):
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "ready")
    monkeypatch.setenv("FLUBNF_ENGINE", "public")


def test_a_refused_particles_value_gets_no_line(hub, engine_ready):
    html = _fc_first_paint("pf.particles", "1e4")
    assert re.search(r'data-knob="pf.particles"', html)
    assert 'value="1e4"' in html
    assert _fc_line(html) == ""
    # the default, and an accepted value, keep their lines
    assert _fc_line(_page().text) == FC.run_words("all", 53, 3, 10_000, W3)
    assert _fc_line(_fc_first_paint("pf.particles", "40000")) == \
        FC.run_words("all", 53, 3, 40_000, W3)


CASES = ([("pf.particles", v) for v in PARTICLES]
         + [("pf.replicates", v) for v in REPLICATES])


def _fc_want(key: str, value: str) -> str:
    read = _server_reads(key, value)
    if key == "pf.particles":
        return FC.run_words("all", 53, 3, read, W3)
    return FC.run_words("all", 53, read, 10_000, W3)


def test_the_first_paint_prices_what_the_check_would_run(hub, engine_ready):
    """Every value: the line as served is the one for the value the run's
    check reads from what the box posts, or none where it refuses it."""
    got = [_fc_line(_fc_first_paint(k, v)) for k, v in CASES]
    want = [_fc_want(k, v) for k, v in CASES]
    assert got == want
    refused = [c for c in CASES if _server_reads(*c) is None]
    assert got.count("") == len(refused) > 10
    assert knobs.BY_KEY["pf.particles"].default == 10_000


@needs_js
def test_the_forecast_script_keeps_what_the_server_painted(tmp_path, hub,
                                                          engine_ready):
    got, want = [], []
    for i, (k, v) in enumerate(CASES):
        html = _fc_first_paint(k, v)
        want.append(_fc_line(html))
        got.append(_served(tmp_path / str(i), html, W3,
                           "return time();"))
    assert got == want
    # both kinds are here
    assert "" in got and any(got)
