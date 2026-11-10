"""The run forms' time estimate (app/core/estimates.py) and its browser
copy (app/ui/static/estimate.js).

The estimate is the engine's own cost model, so these tests hold it equal
to the code that already prices runs: runner._week_cost and _week_n (the
Sandbox's experiment estimates), pf.expected_seconds over pf.shard_cells
(the sharded run's own prediction) and sandbox.eta_span (the Sandbox's
span). The reviewers' figures are pinned with today's constants patched
in, so a refit of the model does not break them. estimate.js runs under
JavaScriptCore, or node where jsc is absent (skips with neither), and must
give the Python's numbers and words exactly.
"""
import json
import math
import re
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import estimates as E  # noqa: E402
from app.core import retro, runner, runs, sandbox  # noqa: E402
from app.core.engines import pf  # noqa: E402

STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"
EST_JS = STATIC / "estimate.js"
EST_SRC = EST_JS.read_text(encoding="utf-8")
TICKER_JS = STATIC / "retro_progress.js"
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")
NODE = shutil.which("node")
needs_js = pytest.mark.skipif(
    not (JSC.is_file() or NODE),
    reason="no JavaScript engine (JavaScriptCore jsc or node)")


# ------------------------------------------------------------------ fixtures

@pytest.fixture
def today(monkeypatch):
    """The cost model's constants as reviewed (2026-11-09), so the pinned
    figures hold after a refit."""
    monkeypatch.setattr(pf, "COST_INTERCEPT_S", 1.194)
    monkeypatch.setattr(pf, "COST_PER_WEEK_S", 0.6365)
    monkeypatch.setattr(pf, "COST_FORECAST_WEEKS", 4)
    monkeypatch.setattr(pf, "COST_REFERENCE_PARTICLES", 10_000)
    monkeypatch.setattr(pf, "PUBLIC_COST_RATIO", 2.4)
    monkeypatch.setattr(sandbox, "ETA_FIRST_SPAN", (1.0, 4.0))


@pytest.fixture(params=["private", "public"])
def engine(request, monkeypatch):
    """Each engine set here, never taken from the shell or the install."""
    monkeypatch.setenv("FLUBNF_ENGINE", request.param)
    return request.param


def _saturdays(first: str, last: str) -> list:
    d, end, out = date.fromisoformat(first), date.fromisoformat(last), []
    while d.weekday() != 5:
        d += timedelta(days=1)
    while d <= end:
        out.append(d.isoformat())
        d += timedelta(days=7)
    return out


# ------------------------------------------------ the reviewers' figures

def test_weekly_grid_figures_private(today, monkeypatch):
    """Both models, all 53 locations, 3 Independent Runs, 10,000 particles:
    159 fits at n_obs 14 and width 8 is 4.2 min on the private engine."""
    monkeypatch.setenv("FLUBNF_ENGINE", "private")
    assert E.fit_seconds(14, 10_000) == pytest.approx(12.651)
    s = E.run_seconds([14], 159, 10_000, 8)
    assert s == pytest.approx(253.02)
    assert round(s / 60, 1) == 4.2
    assert round(E.run_seconds([40], 159, 10_000, 8) / 60, 2) == 9.73
    assert E.human(*E.span(s)) == "about 4 to 17 min"


def test_weekly_grid_figures_public(today, monkeypatch):
    """10.1 min at width 8 on the public engine; about 40 min at width 2
    (a 4-core laptop)."""
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    s8 = E.run_seconds([14], 159, 10_000, 8)
    assert round(s8 / 60, 1) == 10.1
    s2 = E.run_seconds([14], 159, 10_000, 2)
    assert s2 == pytest.approx(80 * 12.651 * 2.4)
    assert round(s2 / 60) == 40
    assert round(E.run_seconds([40], 159, 10_000, 8) / 60, 2) == 23.36
    assert E.human(*E.span(s8)) == "about 10 to 40 min"
    assert E.human(*E.span(s2)) == "about 0.7 to 2.7 h"


def test_engine_argument_overrides_the_process_engine(today, monkeypatch):
    monkeypatch.setenv("FLUBNF_ENGINE", "private")
    pub = E.run_seconds([14], 159, 10_000, 8, engine="public")
    assert pub == pytest.approx(E.run_seconds([14], 159, 10_000, 8) * 2.4,
                                rel=1e-12)
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    assert E.run_seconds([14], 159, 10_000, 8, engine="private") == \
        pytest.approx(253.02)


def test_no_fits_no_figure(engine):
    """The Groundhog alone fits nothing: zero seconds and no words, never
    "under a minute" (its time is not in the model)."""
    assert E.run_seconds([14, 15], 0, 10_000, 8) == 0.0
    assert E.human(*E.span(0.0)) == ""


# ----------------------------------------- agreement with the shipped code

@pytest.mark.parametrize("season", ["2024-25", "2025-26", "2097-98"])
def test_week_cost_agrees_with_runner(season, engine):
    """Week by week, run_seconds at pf.DEFAULT_SHARD_WIDTH is exactly
    runner._week_cost, and n_obs_for is exactly runner._week_n."""
    start, end = retro.season_bounds(season)
    weeks = _saturdays(start, end)
    for asof in weeks:
        n = E.n_obs_for(asof, start)
        assert n == runner._week_n(season, asof)
        assert E.n_obs_for(asof, "") == n            # August 1 seasons
        for fits, particles in ((159, 10_000), (21, 10_000), (3, 2_000),
                                (1, 500)):
            assert (E.run_seconds([n], fits, particles,
                                  pf.DEFAULT_SHARD_WIDTH)
                    == runner._week_cost(season, asof, fits, particles))
    # the whole season, added week by week
    ns = [E.n_obs_for(a, start) for a in weeks]
    total = 0.0
    for asof in weeks:
        total += runner._week_cost(season, asof, 159, 10_000)
    assert E.run_seconds(ns, 159, 10_000, pf.DEFAULT_SHARD_WIDTH) == total
    assert total == pytest.approx(sum(
        runner._week_cost(season, a, 159, 10_000) for a in weeks), rel=1e-12)


@pytest.mark.parametrize("width", [1, 2, 3, 7, 8, 16, 159, 400])
def test_run_seconds_is_the_slowest_shard(width, engine):
    """For cells sharing one n_obs, ceil(fits / width) waves is the
    sharded run's own prediction (its slowest shard)."""
    for n, fits, particles in ((14, 159, 10_000), (40, 21, 10_000),
                               (3, 5, 2_000)):
        cells = [{"n_obs": n, "particles": particles}] * fits
        assert E.run_seconds([n], fits, particles, width) == pytest.approx(
            pf.expected_seconds(pf.shard_cells(cells, width)), rel=1e-12)


def test_fit_seconds_is_cell_seconds(engine):
    for n in (0, 1, 14, 40, 52):
        for p in (None, 0, 1, 500, 10_000, 20_000):
            assert E.fit_seconds(n, p) == pf.cell_seconds(
                {"n_obs": n, "particles": p})
    for eng in ("public", "private"):
        assert E.fit_seconds(14, 10_000, eng) == pf.cell_seconds(
            {"n_obs": 14, "particles": 10_000}, eng)


@pytest.mark.parametrize("n", [14, 40])
@pytest.mark.parametrize("ratio", [None, 2.5])
@pytest.mark.parametrize("particles", [10_000, 2_000])
def test_span_is_the_sandbox_span(n, ratio, particles, engine):
    assert (E.span(sandbox.eta_seconds(n, particles), ratio)
            == sandbox.eta_span(n, particles, ratio))


def test_span_reads_the_sandbox_first_span(monkeypatch):
    """By import, not a copy: a change to ETA_FIRST_SPAN reaches it."""
    monkeypatch.setattr(sandbox, "ETA_FIRST_SPAN", (1.5, 3.0))
    assert E.span(100.0) == (150.0, 300.0)
    assert E.span(100.0, 2.0) == (200.0, 200.0)
    assert E.span(100.0, None, (1.0, 2.0)) == (100.0, 200.0)
    assert E.page_params()["data-est-first-span"] == "1.5 3.0"


def test_width_none_is_the_forecast_width(monkeypatch, engine):
    monkeypatch.delenv(pf.WIDTH_ENV, raising=False)
    w = pf.DEFAULT_SHARD_WIDTH
    assert E.run_seconds([14], 159, 10_000) == E.run_seconds(
        [14], 159, 10_000, w)
    monkeypatch.setenv(pf.WIDTH_ENV, "1")
    assert E.run_seconds([14], 159, 10_000) == E.run_seconds(
        [14], 159, 10_000, 1)
    assert E.page_params()["data-est-width"] == "1"
    assert E.page_params(4)["data-est-width"] == "4"      # the form's own
    assert E.run_seconds([14], 159, 10_000, 0) == E.run_seconds(
        [14], 159, 10_000, 1)                              # never below 1


# --------------------------------------------------------- weeks observed

def test_n_obs_for_counts_from_the_season_start():
    assert E.n_obs_for("2025-11-01", "") == 14
    assert E.n_obs_for("2025-11-01", "2025-08-01") == 14
    assert E.n_obs_for(date(2025, 11, 1), "2025-08-01") == 14
    assert E.n_obs_for("2025-08-02", "") == 1
    assert E.n_obs_for("2026-03-07", "") == runner._week_n("2025-26",
                                                           "2026-03-07")
    assert E.default_season_start("2026-03-07") == "2025-08-01"
    assert E.default_season_start("2026-03-07") == runs.default_season_start(
        "2026-03-07")
    assert E.n_obs_for("2025-07-26", "2025-08-01") == 0   # before the start


@pytest.mark.parametrize("bad", ["", None, "2025-02-30", "not a date"])
def test_n_obs_for_refuses_a_bad_anchor(bad):
    with pytest.raises(ValueError):
        E.n_obs_for(bad, "")


# ------------------------------------------------------------------ words

@pytest.mark.parametrize("lo,hi,words", [
    (600, 1200, "about 10 to 20 min"),
    (180, 180, "about 3 min"),
    (20, 70, "about 1 min"),             # both ends read 1 min
    (30, 59.9, "under a minute"),
    (5400, 21600, "about 1.5 to 6.0 h"),
    (600, 7200, "about 0.2 to 2.0 h"),   # the unit is the high end's
    (12000, 12000, "about 3.3 h"),
    (5000, 5399.9, "about 83 to 90 min"),
    (8100, 8100, "about 2.3 h"),         # 2.25: toFixed's tie, upward
    (150, 150, "about 3 min"),           # 2.5: Math.round's tie, upward
    (0, 0, ""),
    (-5, -1, ""),
    (float("nan"), 100, ""),
    (10, float("inf"), ""),
    (None, 100, ""),
])
def test_human(lo, hi, words):
    assert E.human(lo, hi) == words


def test_round_tenth_is_python_round():
    for x in (0.25, 0.75, 1.25, 2.5, 0.15, 0.35, 12.345, 123.45, 99.95,
              -0.25, 7.05, 1e-9, 253.02, 1012.08):
        assert E.round_tenth(x) == round(x, 1)


# ------------------------------------------------------------ page params

def test_page_params(today, engine, monkeypatch):
    monkeypatch.delenv(pf.WIDTH_ENV, raising=False)
    p = E.page_params()
    assert tuple(p) == E.PARAM_NAMES
    assert all(isinstance(v, str) for v in p.values())
    assert p == {"data-est-intercept": "1.194",
                 "data-est-per-week": "0.6365",
                 "data-est-forecast-weeks": "4",
                 "data-est-reference-particles": "10000",
                 "data-est-public-ratio": "2.4",
                 "data-est-first-span": "1.0 4.0",
                 "data-est-engine": engine,
                 "data-est-width": str(pf.DEFAULT_SHARD_WIDTH)}
    other = "private" if engine == "public" else "public"
    assert E.page_params(engine=other)["data-est-engine"] == other
    # a fresh dict each call: a caller's change does not reach the next
    p["data-est-width"] = "99"
    assert E.page_params()["data-est-width"] == str(pf.DEFAULT_SHARD_WIDTH)


def test_page_params_render_as_attributes():
    import jinja2
    html = jinja2.Environment(autoescape=True).from_string(
        "<form{{ est|xmlattr }}></form>").render(est=E.page_params(8))
    for k, v in E.page_params(8).items():
        assert f'{k}="{v}"' in html


def test_import_is_light():
    """The page shell can import it: no numpy until a span is asked for."""
    code = ("import sys; import app.core.estimates; "
            "print('numpy' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, timeout=60,
                         cwd=str(Path(__file__).resolve().parents[2]))
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"


# ------------------------------------------------- estimate.js, the mirror

def _js(tmp_path, body, *scripts):
    """Run `body` (a function body returning a value) against estimate.js
    and any other `scripts`; its JSON result."""
    files = [*scripts, EST_JS]
    drv = ("var E = FluBNFEstimate;\n"
           "print(JSON.stringify((function(){ " + body + " })()));\n")
    if JSC.is_file():
        d = tmp_path / "driver.js"
        d.write_text(drv, encoding="utf-8")
        cmd = [str(JSC), *map(str, files), str(d)]
    else:
        both = tmp_path / "both.js"
        both.write_text("var print = function(s){ console.log(s); };\n"
                        + "\n".join(Path(f).read_text(encoding="utf-8")
                                    for f in files) + "\n" + drv,
                        encoding="utf-8")
        cmd = [NODE, str(both)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, (out.stderr or out.stdout)
    return json.loads(out.stdout.strip().splitlines()[-1])


CASES = [
    # the Forecast default: all 53 locations x 3 Independent Runs, n_obs 14
    {"anchor": "2025-11-01", "start": "", "fits": 159, "particles": 10_000,
     "width": None, "ratio": None},
    # the 6-state panel late in a season, at width 2, with a recorded ratio
    {"anchor": "2026-05-02", "start": "2025-08-01", "fits": 21,
     "particles": 10_000, "width": 2, "ratio": 2.5},
    # a dataset's own start, few particles, wide
    {"anchor": "2025-12-20", "start": "2025-08-09", "fits": 3,
     "particles": 2_000, "width": 16, "ratio": None},
    # no particle count (the reference), one runner, first week
    {"anchor": "2024-08-03", "start": "", "fits": 53, "particles": 0,
     "width": 1, "ratio": None},
]


def _python_case(c, params_width, engine):
    n = E.n_obs_for(c["anchor"], c["start"])
    w = params_width if c["width"] is None else c["width"]
    sec = E.run_seconds([n], c["fits"], c["particles"], w, engine)
    lo, hi = E.span(sec, c["ratio"])
    return {"n": n, "sec": sec, "span": [lo, hi], "words": E.human(lo, hi)}


@needs_js
def test_js_matches_python_on_the_cases(tmp_path, engine):
    attrs = E.page_params(8)
    want = [_python_case(c, 8, None) for c in CASES]
    got = _js(tmp_path, """
      var attrs = %s, cases = %s;
      var el = {getAttribute: function (k) {
        return Object.prototype.hasOwnProperty.call(attrs, k) ? attrs[k] : null;
      }};
      var p = E.params(el);
      return cases.map(function (c) {
        var n = E.nObsFor(c.anchor, c.start);
        var sec = E.seconds([n], c.fits, c.particles, c.width, p);
        var sp = E.span(sec, c.ratio, p.first);
        return {n: n, sec: sec, span: sp, words: E.human(sp[0], sp[1])};
      });""" % (json.dumps(attrs), json.dumps(CASES)))
    assert got == want
    assert len({w["words"] for w in want}) >= 3       # distinct texts


@needs_js
def test_js_matches_python_over_a_season(tmp_path, today, engine):
    """The Retrospective's sum: every week of 2025-26, both widths."""
    start, end = retro.season_bounds("2025-26")
    weeks = _saturdays("2025-10-04", "2026-05-30")
    ns = [E.n_obs_for(a, start) for a in weeks]
    want = [E.run_seconds(ns, 159, 10_000, w) for w in (8, 2)]
    got = _js(tmp_path, """
      var attrs = %s, weeks = %s, start = %s;
      var p = E.params({getAttribute: function (k) {
        return attrs.hasOwnProperty(k) ? attrs[k] : null; }});
      var ns = weeks.map(function (a) { return E.nObsFor(a, start); });
      return [E.seconds(ns, 159, 10000, 8, p), E.seconds(ns, 159, 10000, 2, p)];
      """ % (json.dumps(E.page_params(8)), json.dumps(weeks),
             json.dumps(start)))
    assert got == want


@needs_js
def test_js_engine_and_particles_match(tmp_path, today, monkeypatch):
    monkeypatch.setenv("FLUBNF_ENGINE", "private")
    attrs = E.page_params(8)
    inputs = [(n, p, eng) for n in (0, 14, 40) for p in (0, 1, 500, 10_000)
              for eng in (None, "public", "private")]
    want = [E.fit_seconds(n, p, eng) for n, p, eng in inputs]
    got = _js(tmp_path, """
      var attrs = %s, inputs = %s;
      var p = E.params({getAttribute: function (k) {
        return attrs.hasOwnProperty(k) ? attrs[k] : null; }});
      return inputs.map(function (x) { return E.fitSeconds(x[0], x[1], p, x[2]); });
      """ % (json.dumps(attrs), json.dumps(inputs)))
    assert got == want


HUMAN_PAIRS = [[0, 0], [30, 59.9], [20, 70], [150, 150], [600, 1200],
               [5000, 5399.9], [600, 7200], [8100, 8100], [5400, 21600],
               [12000, 12000], [89.9, 90], [3570, 3630], [253.0, 1012.1],
               [607.2, 2429.0], [2429.0, 9716.0], [59.9, 60], [-5, 100]]


@needs_js
def test_js_words_and_rounding_match(tmp_path):
    xs = [0.25, 0.75, 1.25, 2.5, 0.15, 0.35, 12.345, 123.45, 99.95, -0.25,
          7.05, 1e-9, 253.02, 1012.08, 2428.992, 9715.968]
    got = _js(tmp_path, """
      var pairs = %s, xs = %s;
      return {words: pairs.map(function (p) { return E.human(p[0], p[1]); }),
              tenths: xs.map(E.roundTenth)};""" % (json.dumps(HUMAN_PAIRS),
                                                   json.dumps(xs)))
    assert got["words"] == [E.human(lo, hi) for lo, hi in HUMAN_PAIRS]
    assert got["tenths"] == [round(x, 1) for x in xs]


@needs_js
def test_words_are_the_retro_tickers_rule(tmp_path):
    """human() is retro_progress.js etaText after "about" ("~" one figure),
    so the Retrospective page writes times one way."""
    pairs = [p for p in HUMAN_PAIRS if p[1] >= 60]
    got = _js(tmp_path, """
      var pairs = %s, eta = FluBNFRetroTicker._internals.etaText;
      return pairs.map(function (p) { return eta(p[0], p[1]); });
      """ % json.dumps(pairs), TICKER_JS)
    for (lo, hi), text in zip(pairs, got):
        assert E.human(lo, hi) == "about " + text.lstrip("~")


@needs_js
def test_js_dates(tmp_path):
    anchors = [["2025-11-01", ""], ["2026-03-07", ""], ["2025-08-02", ""],
               ["2025-12-20", "2025-08-09"], ["2025-07-26", "2025-08-01"],
               ["2024-02-03", ""]]
    got = _js(tmp_path, """
      var a = %s;
      return {n: a.map(function (x) { return E.nObsFor(x[0], x[1]); }),
              bad: [E.nObsFor("", ""), E.nObsFor(null, ""),
                    E.nObsFor("2025-02-30", ""), E.nObsFor("not a date", ""),
                    E.nObsFor("2025-11-01", "2025-13-01")],
              start: E.defaultSeasonStart("2026-03-07")};""" % json.dumps(
        anchors))
    assert got["n"] == [E.n_obs_for(a, s) for a, s in anchors]
    assert got["bad"] == [None] * 5
    assert got["start"] == E.default_season_start("2026-03-07")


@needs_js
def test_js_params_missing_reads_null(tmp_path):
    got = _js(tmp_path, """
      var full = %s, out = [];
      Object.keys(full).forEach(function (drop) {
        out.push(E.params({getAttribute: function (k) {
          return k !== drop && full.hasOwnProperty(k) ? full[k] : null; }}));
      });
      out.push(E.params(null));
      return out;""" % json.dumps(E.page_params(8)))
    assert got == [None] * (len(E.PARAM_NAMES) + 1)


# --------------------------------------------------------- source checks

def test_estimate_js_is_es5_and_quiet():
    code = re.sub(r"/\*.*?\*/", "", EST_SRC, flags=re.S)
    code = re.sub(r"//[^\n]*", "", code)
    assert "=>" not in code and "`" not in code
    assert not re.search(r"\b(let|const|class|async|await)\b", code)
    assert "padStart" not in code and "(?<" not in code
    assert "fetch(" not in code and "XMLHttpRequest" not in code
    assert "document" not in code            # nothing touched at load
    assert "flubnf-estimate-v1" in EST_SRC
    assert "root.FluBNFEstimate = FluBNFEstimate" in EST_SRC


def test_wording():
    py = (Path(E.__file__)).read_text(encoding="utf-8")
    for src in (py, EST_SRC):
        low = src.lower()
        assert "posterior" not in low
        assert not re.search(r"\b(adapts?|tracks?|follows?)\b", low)
        assert "lwf_" not in low


def test_constants_mirror():
    """The two files name the same switch points."""
    assert "HOURS_FROM_S = %d" % E.HOURS_FROM_S in EST_SRC
    assert "MINUTE_S = %d" % E.MINUTE_S in EST_SRC
    assert math.isclose(E.HOURS_FROM_S, 5400)
