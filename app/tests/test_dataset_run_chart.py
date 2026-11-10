"""The fan on a custom dataset's run page (_dataset_run.html, bug hunt
2026-10-25 review: UI-03 and FC-31 on this sibling of the Forecast tab).

  * The Groundhog is drawn per theme (--model-analogue: a darker gold on
    light cards, the yellow on dark ones), as on the Forecast tab, the
    model pages and a dataset's replay; never the yellow on a light card.
  * The chart's toolbar stays off on a phone (640 px and under), where it
    sat on the chart's title, as on the Forecast tab.

The page's own script runs under node against a stub page whose tokens are
nau.css's, theme by theme, with the fans run_page_extra builds."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import css_cascade                                             # noqa: E402
from app.ui import datasets_ui as DU                           # noqa: E402
from app.ui.templating import templates                        # noqa: E402

NODE = shutil.which("node")
TOKENS = ("--model-analogue", "--gold", "--card", "--ink", "--line")
QS = {"0.1": 8.0, "0.5": 16.0, "0.9": 30.0}
RES = {"forecast_date": "2026-10-17",
       "dataset": {"id": "no-such-dataset", "name": "Clinic counts",
                   "vintage_true": True},
       "horizon_convention": "canonical",
       "models": {m: {"Group A": {"0": QS, "1": QS, "2": QS, "3": QS}}
                  for m in ("pf", "analogue")},
       "observed": {"Group A": [["2026-10-03", 10.0], ["2026-10-10", 12.0],
                                ["2026-10-17", 15.0]]}}


def _page(tmp_path, monkeypatch) -> str:
    """_dataset_run.html as run.html includes it, with run_page_extra's
    context (no stored dataset: no later data)."""
    monkeypatch.setattr(DU, "get_dataset", lambda _id: None)
    ctx = DU.run_page_extra(tmp_path, RES)
    return templates.env.from_string(
        '{% import "_tips.html" as tips %}{% include "_dataset_run.html" %}'
    ).render(**ctx)


def _script(page: str) -> str:
    bodies = [b for b in re.findall(r"<script>(.*?)</script>", page, re.S)
              if "FluCharts.react('dsf-plot'" in b]
    assert len(bodies) == 1
    return bodies[0]


def _tokens(theme: str) -> dict:
    cas = css_cascade.Cascade.page()
    root = css_cascade.path(f'html[data-theme="{theme}"]')
    return {t: cas.token(root, t) for t in TOKENS}


STUB = r"""
var calls = [], els = {};
function mk(tag){
  var e = {tag: tag, hidden: false, innerHTML: '', textContent: '',
    dataset: {}, selectedIndex: 0, children: [], attrs: {}, cls: {},
    onclick: null, onchange: null};
  e.appendChild = function(c){ e.children.push(c); };
  e.querySelectorAll = function(){ return e.children; };
  e.setAttribute = function(k, v){ e.attrs[k] = v; };
  e.classList = {toggle: function(k, on){ e.cls[k] = !!on; }};
  return e;
}
var document = {documentElement: {},
  getElementById: function(id){ return els[id] || (els[id] = mk(id)); },
  createElement: mk};
function getComputedStyle(){
  return {getPropertyValue: function(v){ return TOK[v] || ''; },
          fontSize: '16px'};
}
function matchMedia(q){
  var m = /\(max-width:\s*(\d+)px\)/.exec(q);
  return {matches: !!m && WIDTH <= +m[1]};
}
var FluCharts = {react: function(id, traces, layout, config){
  calls.push({id: id, traces: traces, config: config}); }};
var listeners = {};
function addEventListener(t, f){ listeners[t] = f; }
"""

DRIVE = r"""
function last(){
  var c = calls[calls.length - 1];
  var med = c.traces.filter(function(t){ return t.name === 'median'; })[0];
  var band = c.traces.filter(function(t){ return t.fill === 'tonexty'; })[0];
  return {title: c.id, median: med.line.color, band: band.fillcolor,
          bar: c.config.displayModeBar === undefined ? 'unset'
               : c.config.displayModeBar};
}
var out = {first: last()};
var buttons = els['dsf-models'].children;
buttons.forEach(function(b){ if(b.textContent === NAMES.analogue) b.onclick(); });
out.groundhog = last();
buttons.forEach(function(b){ if(b.textContent === NAMES.pf) b.onclick(); });
out.back = last();
console.log(JSON.stringify(out));
"""


def _run(tmp_path, monkeypatch, theme: str, width: int) -> dict:
    page = _page(tmp_path, monkeypatch)
    names = DU.MEMBER_NAMES
    drv = tmp_path / f"drive-{theme}-{width}.js"
    drv.write_text(
        f"var TOK = {json.dumps(_tokens(theme))};\n"
        f"var WIDTH = {width};\nvar NAMES = {json.dumps(names)};\n"
        + STUB + _script(page) + "\n" + DRIVE, encoding="utf-8")
    out = subprocess.run([NODE, str(drv)], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _rgba(hex_: str, a: float) -> str:
    n = int(hex_.lstrip("#"), 16)
    return f"rgba({n >> 16 & 255},{n >> 8 & 255},{n & 255},{a})"


@pytest.mark.skipif(not NODE, reason="no node to run the page's script")
@pytest.mark.parametrize("theme", css_cascade.themes())
def test_the_groundhog_is_drawn_in_its_theme_color(tmp_path, monkeypatch,
                                                   theme):
    tok = _tokens(theme)
    cols = json.loads(json.dumps(DU.templating._member_colors()))
    got = _run(tmp_path, monkeypatch, theme, 1280)
    # the particle filter keeps its member color, before and after
    assert got["first"]["median"] == cols["pf"]
    assert got["back"]["median"] == cols["pf"]
    # the Groundhog takes the theme's token: the median and its band
    gh = got["groundhog"]
    assert gh["median"] == tok["--model-analogue"]
    assert gh["band"] == _rgba(tok["--model-analogue"], .2)
    # which shows on the card: 3:1 at least (the yellow had 1.56 on white)
    ratio = css_cascade.contrast(gh["median"], tok["--card"])
    assert ratio >= 3.0, (theme, gh["median"], tok["--card"], ratio)


@pytest.mark.skipif(not NODE, reason="no node to run the page's script")
def test_the_yellow_is_never_drawn_on_a_light_card(tmp_path, monkeypatch):
    yellow = DU.templating._member_colors()["analogue"]
    for theme in ("light", "paper", "github", "solarized"):
        got = _run(tmp_path, monkeypatch, theme, 1280)["groundhog"]
        assert got["median"].lower() != yellow.lower(), theme


@pytest.mark.skipif(not NODE, reason="no node to run the page's script")
@pytest.mark.parametrize("width,phone", [(390, True), (640, True),
                                         (641, False), (1280, False)])
def test_the_toolbar_stays_off_on_a_phone(tmp_path, monkeypatch, width,
                                          phone):
    got = _run(tmp_path, monkeypatch, "light", width)
    # on every draw: the first, and after the model is switched. Wider, it
    # shows on hover (Plotly's own default when the page sets nothing)
    bars = [got[k]["bar"] for k in ("first", "groundhog", "back")]
    if phone:
        assert bars == [False] * 3
    else:
        assert all(b in ("hover", "unset") for b in bars), bars
