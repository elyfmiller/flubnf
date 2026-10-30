"""The console's charts (bug hunt 2026-10-25, G19).

  * The Groundhog is drawn per theme (--model-analogue: a darker gold on
    light cards, the yellow on dark ones) on the Forecast tab, the model
    pages, the season page and a dataset's replay.
  * The charts' toolbar takes the app's focus ring, and stays off on a
    phone, where it sat on the chart's title.
  * A fan starts where its member started, before any week it set aside,
    and marks those weeks; the settled outcome stops at the last horizon.
  * The model page's pager draws only the location its readout names.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import missing                                   # noqa: E402

UI = Path(__file__).resolve().parents[2] / "app" / "ui"
NAU = (UI / "static" / "nau.css").read_text(encoding="utf-8")


def _tpl(name: str) -> str:
    return (UI / "templates" / name).read_text(encoding="utf-8")


# ------------------------------------------- UI-03 (MO-10): the Groundhog

def test_the_groundhog_is_drawn_per_theme_on_every_console_chart():
    # every theme block carries it with its scheme: dark gold on light
    for scheme, colour in (("light", "#806000"), ("dark", "#FFC72C")):
        n = NAU.count(f"--scheme:{scheme};")
        assert n == 4 and NAU.count(
            f"--scheme:{scheme}; --model-analogue:{colour};") == n
    for name in ("forecast.html", "model.html"):
        assert ("m==='analogue'?(css('--model-analogue')||MCOLORS.analogue)"
                in _tpl(name)), name
    season = _tpl("retro_season.html")
    assert ('{% set member_colors = dict(member_colors, '
            'analogue="var(--model-analogue)") %}') in season
    assert "analogue: css('--model-analogue')" in season
    assert ("(M === 'analogue' && css('--model-analogue'))"
            in _tpl("retro_dataset.html"))


# ------------------------------------------------ UI-04, FC-31: the toolbar

def test_the_chart_toolbar_wears_the_focus_ring_and_stays_off_on_a_phone():
    rule = re.search(r"\.js-plotly-plot \.plotly \.modebar \.modebar-btn"
                     r":focus-visible\{\s*([^}]*)\}", NAU)
    assert rule and "var(--focus-w,2px) solid var(--gold)" in rule.group(1)
    assert ("displayModeBar:matchMedia('(max-width: 640px)').matches?false"
            ":'hover'") in _tpl("forecast.html")


# ---------------------------------------- FC-14, FC-24: where a fan starts

def test_the_weeks_a_member_set_aside_come_from_the_runs_flags():
    outcome = {"data_flags": {
        "analogue": [
            {"location": "Ohio", "week": "2026-10-17", "value": 2.0,
             "rule": missing.SET_ASIDE_RULE},
            {"location": "Ohio", "week": "2026-10-17", "value": 0.0,
             "rule": missing.LEFT_OUT_RULE}],
        "pf": [{"location": "Arizona", "week": "2026-10-17", "value": 0.0,
                "rule": "trailing zero"}]}}
    assert missing.aside_weeks(outcome) == {
        "analogue": {"Ohio": ["2026-10-17"]},
        "pf": {"Arizona": ["2026-10-17"]}}
    assert missing.aside_weeks({}) == {}


def test_a_fan_starts_before_its_set_aside_weeks_and_ends_at_its_horizon():
    for name in ("forecast.html", "model.html"):
        js = _tpl(name)
        assert "while(ai>=0&&aside.has(obsX[ai])) ai--;" in js, name
        assert "name:'set aside'" in js, name
        assert "obsY.slice(-1)" not in js, name       # never the set-aside value
        # the settled outcome to the last horizon, not a week past it
        assert "+35" not in js, name
        assert ("lim.setUTCDate(lim.getUTCDate()+7*Math.max(...hs.map("
                "h=>parseInt(h))));") in js, name
    assert "const RASIDE = {{ run_aside_json | safe }};" in _tpl("forecast.html")


# ------------------------------------------------- MO-09: the pager's race

def test_the_model_pager_draws_only_the_location_it_names():
    js = _tpl("model.html").split("async function draw()", 1)[1]
    fetch = js.index("await fetch('/api/series")
    guard = js.index("if(tok!==drawSeq) return;")
    assert js.index("const tok=++drawSeq;") < fetch < guard


def test_the_forecast_and_model_pages_receive_the_set_aside_weeks(monkeypatch):
    from app.ui import shared
    from app.core import runs

    class Row:
        def row(self, rid):
            return {"outcome": json.dumps({"data_flags": {"analogue": [
                {"location": "Ohio", "week": "2026-10-17",
                 "rule": missing.SET_ASIDE_RULE}]}})}
    monkeypatch.setattr(runs, "Ledger", Row)
    assert shared._run_aside("r1") == {"analogue": {"Ohio": ["2026-10-17"]}}
    assert shared._run_aside(None) == {}
