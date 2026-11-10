"""The model pages' marks, scripts and figure labels (bug hunt
2026-10-25, G33).

  * A run without this model says so in plain text under the empty
    state, with no "?" (MO-12).
  * The chart library loads only where a fan is drawn, and deferred
    (MO-16).
  * The seasonal-forcing figure labels its dashed lines in the axis's own
    units, e to the plus and minus epsilon-1 around 1.0 (HM-17).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from test_models_tab import _run, client, no_runs        # noqa: E402,F401

PAIR = '<script src="/static/plotly.min.js"{}></script><script src="/static/charts.js"{}></script>'


def test_a_run_without_this_model_says_so_without_a_mark(monkeypatch):
    _run(monkeypatch, ["analogue"])
    t = client.get("/models").text
    fc = t.split('class="card md-fc"', 1)[1].split('<div id="mfan">', 1)[1]
    fc = fc.split("</div>\n  </div>", 1)[0]
    assert 'class="tipbtn"' not in fc and 'class="uk-tt-btn"' not in fc
    assert ('<p class="hint md-nofc-why">The latest real-time run (2098-11-14 '
            '· 11-14 09:31:00) has none from this model.</p>') in fc


def test_the_chart_library_loads_only_for_a_fan_and_deferred(monkeypatch,
                                                              no_runs):
    for path in ("/models", "/model/analogue", "/model/pf2s"):
        assert "plotly.min.js" not in client.get(path).text, path
    _run(monkeypatch, ["pf", "analogue"])
    t = client.get("/model/analogue").text
    assert PAIR.format(" defer", " defer") in t
    # the first draw waits for the deferred scripts
    assert ("if(document.readyState==='loading')addEventListener("
            "'DOMContentLoaded',()=>draw());") in t
    assert "plotly.min.js" not in client.get("/model/pf2s").text


def test_the_forcing_figures_lines_read_in_the_axis_units():
    t = client.get("/").text
    fig = t.split('class="dg-harm"', 1)[1].split("</svg>", 1)[0]
    assert "&#946;(t) / &#946;" in fig or "β(t) / β" in fig
    assert "&#183;&#8202;e" not in fig and "· e" not in fig
    assert '>1.0</text>' in fig
    assert fig.count('<text x="68" y="33">e<tspan') == 1
    assert fig.count('<text x="68" y="164">e<tspan') == 1
