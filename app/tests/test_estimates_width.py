"""The width a run is priced at (review 3, finding 7; app/core/estimates.py
priced_width and static/estimate.js seconds).

The estimate divided the fits by the run's width up to 16 on any
computer, so a wider Shard width always read faster: 159 fits over six
weeks read about 1.6 h at width 4, 47 min at 8 and 23 min at 16, on a
laptop whose default width is 4. More runners than this computer's default
(its cores less the two left for the console and the browser,
pf.default_shard_width) share the cores, so a run is priced at its width
but never above pf.DEFAULT_SHARD_WIDTH, as runner._week_cost prices every
run. The browser's copy reads that bound from data-est-most-width.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import estimates as E  # noqa: E402
from app.core import retro, runner  # noqa: E402
from app.core.engines import pf  # noqa: E402
from app.tests.test_estimates import (  # noqa: E402
    _js, _saturdays, needs_js, today)

assert today                                   # the fixture, imported

WEEKS = [10, 11, 12, 13, 14, 15]               # six weeks' n_obs


@pytest.fixture(params=["private", "public"])
def engine(request, monkeypatch):
    monkeypatch.setenv("FLUBNF_ENGINE", request.param)
    monkeypatch.delenv(pf.WIDTH_ENV, raising=False)
    return request.param


@pytest.mark.parametrize("default", [2, 4, 8, 16])
def test_a_width_above_this_computers_default_is_priced_at_the_default(
        default, engine, monkeypatch):
    monkeypatch.setattr(pf, "DEFAULT_SHARD_WIDTH", default)
    at_default = E.run_seconds(WEEKS, 159, 10_000, default)
    for w in range(default, 41):
        assert E.priced_width(w) == default
        assert E.run_seconds(WEEKS, 159, 10_000, w) == at_default
    for w in range(1, default):
        assert E.priced_width(w) == w
        assert E.run_seconds(WEEKS, 159, 10_000, w) == pytest.approx(
            sum(-(-159 // w) * E.fit_seconds(n, 10_000) for n in WEEKS),
            rel=1e-12)
    # FLUBNF_PF_WIDTH above the default: priced at the default too
    monkeypatch.setenv(pf.WIDTH_ENV, str(default + 5))
    assert E.priced_width(None) == default
    assert E.run_seconds(WEEKS, 159, 10_000) == at_default


def test_the_reviewers_laptop(today, monkeypatch):
    """Default width 4, ratio 2.0: widths 4, 8 and 16 read alike, the
    width-4 figure (1.6 h before and after)."""
    monkeypatch.setenv("FLUBNF_ENGINE", "private")
    monkeypatch.setattr(pf, "DEFAULT_SHARD_WIDTH", 4)
    words = {w: E.human(*E.span(E.run_seconds(WEEKS, 159, 10_000, w), 2.0))
             for w in (4, 8, 16)}
    assert set(words.values()) == {words[4]}
    monkeypatch.setattr(pf, "DEFAULT_SHARD_WIDTH", 16)
    wide = {w: E.human(*E.span(E.run_seconds(WEEKS, 159, 10_000, w), 2.0))
            for w in (4, 8, 16)}
    assert wide[4] == words[4] and len(set(wide.values())) == 3


@pytest.mark.parametrize("default", [2, 4, 8, 16])
@pytest.mark.parametrize("season", ["2024-25", "2025-26"])
def test_every_width_from_the_default_up_is_runner_week_cost(
        season, default, engine, monkeypatch):
    monkeypatch.setattr(pf, "DEFAULT_SHARD_WIDTH", default)
    start, end = retro.season_bounds(season)
    for asof in _saturdays(start, end)[::5]:
        n = E.n_obs_for(asof, start)
        for fits in (159, 21, 3):
            want = runner._week_cost(season, asof, fits, 10_000)
            for w in (default, default + 1, 16, 99):
                assert E.run_seconds([n], fits, 10_000, w) == want


def test_page_params_name_the_bound(engine, monkeypatch):
    monkeypatch.setattr(pf, "DEFAULT_SHARD_WIDTH", 6)
    p = E.page_params(16)
    assert tuple(p) == E.PARAM_NAMES
    assert p["data-est-width"] == "16"           # the form's own width
    assert p["data-est-most-width"] == "6"
    assert E.page_params(None)["data-est-most-width"] == "6"


@needs_js
@pytest.mark.parametrize("default", [2, 4, 8])
def test_the_page_script_prices_widths_as_the_server(default, tmp_path,
                                                     today, engine,
                                                     monkeypatch):
    """estimate.js under JavaScriptCore or node: every width 1 to 20, and
    the page's own (null), give the Python's seconds exactly."""
    monkeypatch.setattr(pf, "DEFAULT_SHARD_WIDTH", default)
    attrs = E.page_params(16)
    widths = list(range(1, 21))
    want = {"each": [E.run_seconds(WEEKS, 159, 10_000, w) for w in widths],
            "page": E.run_seconds(WEEKS, 159, 10_000, 16)}
    got = _js(tmp_path, """
      var attrs = %s, ns = %s, widths = %s;
      var p = E.params({getAttribute: function (k) {
        return attrs.hasOwnProperty(k) ? attrs[k] : null; }});
      return {each: widths.map(function (w) {
                return E.seconds(ns, 159, 10000, w, p); }),
              page: E.seconds(ns, 159, 10000, null, p)};
      """ % (json.dumps(attrs), json.dumps(WEEKS), json.dumps(widths)))
    assert got == want
    assert len(set(want["each"][default - 1:])) == 1


@needs_js
def test_the_page_script_needs_the_bound(tmp_path):
    attrs = {k: v for k, v in E.page_params(8).items()
             if k != "data-est-most-width"}
    got = _js(tmp_path, """
      var attrs = %s;
      return E.params({getAttribute: function (k) {
        return attrs.hasOwnProperty(k) ? attrs[k] : null; }});
      """ % json.dumps(attrs))
    assert got is None
