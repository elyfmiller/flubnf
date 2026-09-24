"""The data layer joins the type system: the A-/A/A+ control dispatches
fontsizechange; Plotly layouts use the brand face with a system fallback and
root-relative text sizes, redrawing on both events; SVG labels use rem
classes; nav tab size follows the window (clamp) on one row. The static report has no
control, so the player's hook is a no-op there.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

from app.ui import server as srv                    # noqa: E402

client = TestClient(srv.app)

UI = Path(__file__).resolve().parents[1] / "ui"
NAU = (UI / "static" / "nau.css").read_text()
PLAYER = (UI / "static" / "player.js").read_text()
BASE_T = (UI / "templates" / "base.html").read_text()
FORECAST_T = (UI / "templates" / "forecast.html").read_text()
MODEL_T = (UI / "templates" / "model.html").read_text()
DIAGRAMS_T = (UI / "templates" / "diagrams.html").read_text()
HOME_T = (UI / "templates" / "home.html").read_text()
SEASON_T = (UI / "templates" / "retro_season.html").read_text()


# ------------------------------------------------- the fontsizechange event

def test_fontsize_buttons_dispatch_fontsizechange():
    # the dispatch rides the same click handler that persists the choice,
    # mirroring the themechange pattern the theme button established
    assert "dispatchEvent(new Event('fontsizechange'))" in BASE_T
    handler = BASE_T.split("btns.forEach(function(b){b.onclick", 1)[1]
    assert "dispatchEvent(new Event('fontsizechange'))" in \
        handler.split("})();", 1)[0]
    # and the served shell carries it
    assert "dispatchEvent(new Event('fontsizechange'))" in \
        client.get("/data").text


# --------------------------------------------------- plotly layouts conform

def test_plotly_layouts_carry_the_brand_face_and_root_proportional_size():
    for src, name in ((FORECAST_T, "forecast"), (MODEL_T, "model"),
                      (PLAYER, "player")):
        assert '"DM Sans",system-ui' in src, name
        assert "rootPx" in src or "rootFont" in src, name


def test_chart_text_sits_on_the_type_scale_with_tight_margins():
    # ticks/legends at .85rem (above the .82rem hint floor), the title one
    # step up, all root-relative; tight margins plus automargin, so nothing
    # clips at A+ and no dead band pads the card
    assert "Math.round(fs * .85)" in PLAYER
    assert "Math.round(fs * .95)" in PLAYER
    assert "Math.round(fs * .82)" in PLAYER          # the now marker
    for src, name in ((FORECAST_T, "forecast"), (MODEL_T, "model")):
        assert "Math.round(fs*.85)" in src, name
        assert "Math.round(fs*.95)" in src, name
        assert "automargin:true" in src, name
    assert "automargin: true" in PLAYER
    # legends hang under the plot, never beside it (the right-hand legend
    # was a dead band up to a third of the card width)
    assert "orientation: 'h'" in PLAYER
    assert PLAYER.count("orientation") >= 1
    for src, name in ((FORECAST_T, "forecast"), (MODEL_T, "model")):
        assert "orientation:'h'" in src, name
    # the weekly report's figures (fixed 16px root, no font control) hold
    # the same floor: base and legend at 14px, above the 13.1px hint floor
    import plotly.graph_objects as go

    from app.core import report_v2
    fig = report_v2._fig_layout(go.Figure(), title="t", legend=True)
    assert fig.layout.font.size >= 14
    assert fig.layout.legend.font.size >= 14
    assert fig.layout.title.font.size > fig.layout.font.size
    assert fig.layout.xaxis.automargin and fig.layout.yaxis.automargin


def test_charts_redraw_on_fontsizechange_and_still_on_themechange():
    for src, name in ((FORECAST_T, "forecast"), (MODEL_T, "model"),
                      (PLAYER, "player")):
        assert "addEventListener('fontsizechange'" in src, name
        assert "addEventListener('themechange'" in src, name


def test_player_hook_is_a_noop_for_the_static_report():
    # the report host (mode static) has no fontsize buttons, so the event
    # never fires there: the player only LISTENS, never dispatches, and its
    # root-size probe degrades to the fixed default instead of throwing
    assert "dispatchEvent" not in PLAYER
    assert PLAYER.count("addEventListener('fontsizechange'") == 1
    assert "|| 16" in PLAYER


# ------------------------------------------------------- SVG labels in rem

def test_svg_labels_are_sized_in_rem_classes_not_viewbox_units():
    for src, name in ((DIAGRAMS_T, "diagrams"), (HOME_T, "home"),
                      (SEASON_T, "retro_season")):
        assert 'font-size="' not in src, name
        assert "svgt-" in src, name
    # the classes exist, in rem, with the smallest step holding the hint
    # floor once the artwork's viewBox scale is applied
    for rule in ("svg .svgt-xl{font-size:1.3rem}",
                 "svg .svgt-lg{font-size:1rem}",
                 "svg .svgt-md{font-size:.92rem}",
                 "svg .svgt-sm{font-size:.875rem}",
                 "svg .svgt-sub{font-size:.68em}"):
        assert rule in NAU, rule


# ------------------------------------------------------ nav tab type step

def test_tab_type_scales_with_the_window():
    # nine title-case tabs share one row with the brand and the Display
    # menu: their size follows the window (a clamp, not a breakpoint step),
    # and the strip scrolls sideways where it no longer fits
    i = NAU.index("header.nav a.tab{")
    block = NAU[i:NAU.index("}", i)]
    assert "font-size:clamp(.85rem," in block
    assert "padding:.8rem .45em" in block           # scales with the size
    j = NAU.index("header.nav .navtabs{")
    strip = NAU[j:NAU.index("}", j)]
    assert "overflow-x:auto" in strip and "min-width:0" in strip
    k = NAU.index("header.nav{")
    assert "flex-wrap:nowrap" in NAU[k:NAU.index("}", k)]
