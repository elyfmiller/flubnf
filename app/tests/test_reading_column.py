"""Methods and Models center their composition (user request 2026-08-21,
second report): the reading column is fluid and centered on the page, and
INSIDE the cards the figures, equation panels, and prose share the same
center axis -- the diagrams and eqpanels keep their margin:auto centering
(the old left-hugging overrides are gone), and the prose block centers at
its 72ch measure while its text stays left-set. Operational pages keep the
full-width shell and are untouched by the reading-column rules."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.ui.server import app as srv                 # noqa: E402

client = TestClient(srv)

UI = Path(__file__).resolve().parents[1] / "ui"
METHODS_T = (UI / "templates" / "methods.html").read_text()
BASE_T = (UI / "templates" / "base.html").read_text()
NAU = (UI / "static" / "nau.css").read_text()

# the retired left-hugging overrides: these must never come back
FIG_RULE = 'svg[role="img"]{margin-left:0 !important'
EQ_RULE = '.eqpanel{margin-left:0'


def test_the_left_hugging_overrides_are_gone():
    """The figures and equation panels center inside their cards again:
    neither the shell nor the Methods page ships the old left-alignment
    override block, so the diagram macros' inline margin:auto centering
    and the stylesheet's centered .eqpanel/.valpanel margins govern."""
    assert FIG_RULE not in BASE_T
    assert FIG_RULE not in METHODS_T
    assert EQ_RULE not in BASE_T
    assert EQ_RULE not in METHODS_T
    for page in ("/methods", "/models", "/model/analogue",
                 "/model/ensemble", "/model/pf2s"):
        html = client.get(page).text
        assert FIG_RULE not in html, page
        assert EQ_RULE not in html, page


def test_figures_and_eqpanels_carry_their_centering_margins():
    """The centering itself: every mechanism diagram states margin auto
    inline, and the eqpanel/valpanel stylesheet rules keep their auto
    margins, so each centers within its card."""
    html = client.get("/methods").text
    assert html.count('role="img"') >= 2             # SIHRS + two-strain
    assert "display:block;margin:.6rem auto" in html # the diagram macros
    assert 'class="eqpanel"' in html
    joined = " ".join(NAU.split())
    assert ".eqpanel{max-width:800px;margin:.45rem auto .25rem;" in joined
    assert "margin:.35rem auto .2rem;" in joined     # .valpanel


def test_prose_centers_at_its_measure_inside_reading_cards():
    """The whole composition shares one center: within main.reading the
    card prose block centers at its 72ch measure (text stays left-set),
    so paragraphs, figures, and equation panels line up on the card's
    center axis instead of the prose hugging left below centered art."""
    joined = " ".join(NAU.split())
    assert ("main.reading .card p{margin-left:auto;margin-right:auto}"
            in joined)
    # the base prose measure is untouched
    assert ".card p{margin:.45rem 0;max-width:72ch}" in joined


# --------------------------------- the reading column centers on the page

def test_reference_pages_center_the_fluid_reading_column():
    """The column stays FLUID (user report 2026-08-21: a fixed 880px
    stopped breathing with the window): 92% of the viewport up to a 68rem
    cap, centered at every size by the base main's margin:0 auto."""
    joined = " ".join(NAU.split())
    assert "main.reading{width:min(92%,68rem)}" in joined
    assert "max-width:880px" not in joined           # the fixed cap is gone
    assert "main{max-width:1500px;margin:0 auto;" in joined
    for page in ("/methods", "/models", "/model/pf", "/model/analogue",
                 "/model/ensemble", "/model/pf2s"):
        html = client.get(page).text
        assert '<main id="main" class="reading">' in html, page


def test_operational_pages_keep_the_full_width_shell():
    for page in ("/", "/data", "/forecast", "/runs", "/retro", "/output"):
        html = client.get(page).text
        assert '<main id="main" class="">' in html, page
        assert 'class="reading"' not in html, page
