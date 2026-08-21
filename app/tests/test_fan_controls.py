"""The forecast fan card's controls: stable scroll, direct location
selection, and the expanded view.

Paging the fan or the data panel must change only the chart: the old
implementation emptied the plot container and then awaited the series
fetch, so the page lost the chart's height mid-flight and the browser
clamped the scroll position upward (a visible jump to the top on slow
fetches). The fix renders each pager shell once, reserves the chart's
height on the plot div, and repaints in place with Plotly.react. The
card also gains a location select beside the arrows (both drive the one
selection state) and an Expand control that opens the current chart in
the app's modal shell under the guard modal's focus contract.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

from app.ui import server as srv                    # noqa: E402

client = TestClient(srv.app)

UI = Path(__file__).resolve().parents[1] / "ui"
FORECAST_T = (UI / "templates" / "forecast.html").read_text()
MODEL_T = (UI / "templates" / "model.html").read_text()
NAU = (UI / "static" / "nau.css").read_text()


# ------------------------------------------------ paging never moves scroll

def test_pager_controls_are_buttons_never_fragment_links():
    # every pager control is a type="button" with a JS handler; an anchor
    # with href="#" would jump the page to the top on every click
    for t in (FORECAST_T, MODEL_T):
        assert 'href="#"' not in t
    for bid in ("fan-prev", "fan-next", "data-prev", "data-next",
                "fan-expand", "fanx-prev", "fanx-next", "fanx-close"):
        assert f'id="{bid}"' in FORECAST_T, bid
    assert FORECAST_T.count('class="quiet cnav" id="fan-prev"') == 1
    assert 'type="button" class="quiet cnav" id="pv"' in MODEL_T


def test_plots_repaint_in_place_and_reserve_their_height():
    # Plotly.react repaints the persistent div; newPlot (purge + rebuild)
    # is gone from both fan surfaces, and each plot div reserves the
    # chart's height so an in-flight fetch can never collapse the page
    for t, h in ((FORECAST_T, "min-height:400px"), (MODEL_T, "min-height:420px")):
        assert "Plotly.newPlot" not in t
        assert "Plotly.react" in t
        assert h in t


def test_model_pager_shell_renders_once_outside_draw():
    # the shell (arrows + pos + plot div) is built before draw() and the
    # handlers bind once: rebuilding it per flip destroyed the plot while
    # the fetch was in flight
    shell = MODEL_T.index("getElementById('mfan')")
    draw = MODEL_T.index("async function draw()")
    assert shell < draw
    assert MODEL_T.count("getElementById('pv').onclick") == 1
    assert MODEL_T.index("getElementById('pv').onclick") < draw


def test_data_panel_keeps_the_old_chart_while_fetching():
    # the fetch branch returns without emptying the panel; the plot is
    # cleared only when new content is actually ready
    fetch_branch = FORECAST_T.index("if(!SERIES[loc]){")
    empty = FORECAST_T.index("const el=document.getElementById('dataplots')")
    assert "el.innerHTML=''" not in FORECAST_T[empty:fetch_branch]


# ------------------------------------------------- the fan location select

def test_fan_card_offers_direct_location_selection():
    r = client.get("/forecast")
    assert r.status_code == 200
    # the select sits in the pager row, styled like the data panel's
    assert 'id="fan-loc" aria-label="forecast location"' in r.text
    assert "min-width:230px" in r.text
    # arrows and select drive the one selection state
    assert "getElementById('fan-loc').onchange" in r.text
    assert "FIDX=this.selectedIndex" in r.text
    # drawFan keeps both selects in step with the arrows
    assert "syncLocSel(document.getElementById('fan-loc'))" in r.text
    assert "sel.selectedIndex=FIDX" in r.text


# ------------------------------------------------------- the expanded view

def test_expanded_view_uses_the_modal_shell_and_focus_contract():
    r = client.get("/forecast")
    # the app's modal shell, viewport-sized
    assert 'id="fanx-modal" class="modal-back" hidden' in r.text
    assert 'class="modal fanx card" role="dialog" aria-modal="true"' in r.text
    assert 'aria-labelledby="fanx-title"' in r.text
    assert ".modal.fanx" in NAU
    # visible Close, Escape closes, focus returns to the opener without
    # scrolling, and Tab cycles inside the dialog including the select
    assert 'id="fanx-close">Close</button>' in r.text
    assert "e.key==='Escape'&&!xb.hidden" in r.text
    assert "t.focus({preventScroll:true})" in r.text
    assert "xb.querySelectorAll('button,select')" in r.text
    assert "getElementById('fanx-close').focus()" in r.text
    # the expanded view keeps its own working pager and select
    assert "getElementById('fanx-prev').onclick" in r.text
    assert "getElementById('fanx-next').onclick" in r.text
    assert "getElementById('fanx-loc').onchange" in r.text
    # and mirrors the card's chart without sharing mutable trace state
    assert "JSON.parse(JSON.stringify(traces))" in r.text
