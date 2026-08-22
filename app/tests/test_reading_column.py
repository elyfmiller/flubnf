"""Methods and Models read as one column: the prose left-aligns under its
measure cap, and the figures, equation panels, and their captions join it
at the same left content edge instead of centering. The overrides are
scoped -- Methods carries its own block, the Models mech card is covered
from the shell -- so the deliberately centered layouts elsewhere (home,
the exported reports) keep their centering."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.ui.server import app as srv                 # noqa: E402

client = TestClient(srv)

UI = Path(__file__).resolve().parents[1] / "ui"
METHODS_T = (UI / "templates" / "methods.html").read_text()
BASE_T = (UI / "templates" / "base.html").read_text()

FIG_RULE = 'svg[role="img"]{margin-left:0 !important;margin-right:auto !important}'
EQ_RULE = '.eqpanel{margin-left:0;margin-right:auto}'
NOTE_RULE = ('p.eqnote{text-align:left !important;'
             'margin-left:0 !important;margin-right:auto !important}')


def test_methods_left_aligns_every_figure_to_the_reading_column():
    html = client.get("/methods").text
    # the page ships its scoped block, covering diagrams (inline-centered),
    # equation panels (stylesheet-centered), and figure captions
    assert ".card " + FIG_RULE in html
    assert ".card " + EQ_RULE in html
    assert ".card .eqpanel " + NOTE_RULE in html
    # and it has figures for the rules to govern
    assert html.count('role="img"') >= 2             # SIHRS + two-strain
    assert 'class="eqpanel"' in html


def test_models_mech_card_gets_the_same_treatment_on_every_view():
    # the shell's scoped rules target the mech card the model views render
    assert ".card.mech " + FIG_RULE in BASE_T
    assert ".card.mech " + EQ_RULE in BASE_T
    assert ".card.mech .eqpanel " + NOTE_RULE in BASE_T
    for page in ("/models", "/model/analogue", "/model/ensemble",
                 "/model/pf2s"):
        html = client.get(page).text
        assert ".card.mech " + FIG_RULE in html, page
        assert 'class="card mech"' in html, page     # the card it governs


def test_the_override_stays_scoped():
    # Methods' broad .card selectors ship ONLY with the Methods page
    assert ".card " + FIG_RULE in METHODS_T
    home = client.get("/").text
    assert ".card " + FIG_RULE not in home
    # the shell rule everywhere is mech-scoped, so home's centered figures
    # (no mech card there) are untouched
    assert 'class="card mech"' not in home


# --------------------------------- the reading column centers on the page

NAU = (UI / "static" / "nau.css").read_text()


def test_reference_pages_center_the_reading_column():
    """User preference 2026-08-21: Methods and every Models view center
    their content column on the page (main.reading) instead of leaving it
    left-aligned in the wide shell. Prose keeps its 72ch measure and
    left-set text WITHIN the centered column; figures, equations, and
    captions ride along at the same left content edge (the scoped rules
    above are unchanged)."""
    # the stylesheet narrows and centers the opt-in column; the base main
    # keeps its margin:0 auto, so a smaller max-width IS the centering
    joined = " ".join(NAU.split())
    assert "main.reading{max-width:880px}" in joined
    assert "main{max-width:1500px;margin:0 auto;" in joined
    for page in ("/methods", "/models", "/model/pf", "/model/analogue",
                 "/model/ensemble", "/model/pf2s"):
        html = client.get(page).text
        assert '<main id="main" class="reading">' in html, page
    # the prose measure inside the column is untouched
    assert ".card p{margin:.45rem 0;max-width:72ch}" in joined


def test_operational_pages_keep_the_full_width_shell():
    for page in ("/", "/data", "/forecast", "/runs", "/retro", "/output"):
        html = client.get(page).text
        assert '<main id="main" class="">' in html, page
        assert 'class="reading"' not in html, page
