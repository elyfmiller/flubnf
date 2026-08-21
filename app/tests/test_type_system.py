"""The data layer joins the type system (design finding 1).

The A-/A/A+ control dispatches fontsizechange, mirroring themechange;
every Plotly layout names the brand face with a system fallback and sizes
its text from the root font size, redrawing on both events; the inline SVG
diagrams size their labels through rem classes rather than fixed
viewBox-unit font-size attributes, so the control reaches the smallest
text in the app; and the navigation tabs step below 1100px so the row
survives the A+ setting. The static season report has no fontsize control,
so the shared player's hook must be a graceful no-op there.
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

def test_tab_type_steps_below_1100px():
    # eight title-case tabs at 1.05rem wrap at 900, and at 1280 with the A+
    # text size; below 1100px the tabs step to .95rem so the row holds
    i = NAU.index("@media(max-width:1100px)")
    block = NAU[i:i + 200]
    assert "header.nav a.tab" in block
    assert "font-size:.95rem" in block
