"""The reading pages (Methods, the Models views) use the ONE shell every
page uses; the retired main.reading column and its prose grid are gone (a
<details> body sits in ::details-content, so grid placement squeezed it into
a gutter strip).

Asserted: cards span the main column; ALL card text is block flow at the
card's content width (no measure cap, no prose grid); figures and equation
panels center; wide blocks scroll inside the card.
"""
import re
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
JOINED = " ".join(NAU.split())

READING_PAGES = ("/methods", "/models", "/model/pf", "/model/analogue",
                 "/model/pf2s")

# retired override blocks: none of these may ever come back
FIG_RULE = 'svg[role="img"]{margin-left:0 !important'
EQ_RULE = '.eqpanel{margin-left:0'


def test_the_reading_column_special_case_is_gone():
    """No main.reading rules survive: the reading pages ride the base
    main shell (2560px cap, fluid padding, centered), the same shell as
    every operational page."""
    assert "main.reading" not in NAU
    assert "main{max-width:2560px;margin:0 auto;" in JOINED
    for page in READING_PAGES:
        html = client.get(page).text
        assert '<main id="main" class="">' in html, page
        assert 'class="reading"' not in html, page


def test_no_grid_for_prose_anywhere():
    """Prose is never laid out with grid columns. Every display:grid in
    the stylesheet belongs to a named panel layout (.cols, .grid2, .grid3,
    .vintagecols, .playgrid, .runsplit, the .runsettings .kv list), never
    to .card itself, so a details body, a paragraph and a kicker all take
    the card's content width by plain block flow."""
    for m in re.finditer(r"([^{}]+)\{[^}]*display\s*:\s*grid", NAU):
        selector = " ".join(m.group(1).split())
        assert ".card" not in selector.replace("details.card", ""), selector
        assert not selector.endswith(".card"), selector
        assert "summary" not in selector and "details" not in selector, \
            selector
    # no per-child grid placement: the only exception was the .valpanel
    # list, whose rules are gone, so any grid-column rule now fails here
    for m in re.finditer(r"([^{}]+)\{[^}]*grid-column", NAU):
        selector = " ".join(m.group(1).split())
        assert selector.startswith(".valpanel"), selector


def test_card_text_has_no_measure_cap():
    """One width for all text in a card: the .card p rule states margins
    only, and no rule reintroduces a ch measure on card prose."""
    assert ".card p{margin:.45rem 0}" in JOINED
    assert "72ch" not in NAU
    assert "95ch" not in NAU
    # the one deliberate ch cap left in the file is the Data page's
    # vintage-table caption, a documented instrument-width choice
    caps = re.findall(r"max-width\s*:\s*\d+ch", NAU)
    assert caps == ["max-width:24ch"], caps


def test_details_bodies_flow_at_card_width():
    """The collapsible blocks that carried the squeeze: their bodies are
    plain block flow. Nothing styles a details child into a column, and
    the intro/bngl/ledgerfold summaries keep their disclosure language."""
    for sel in ("details.card", "details.intro", "details.bngl",
                "details.preview", "details.ledgerfold"):
        for m in re.finditer(re.escape(sel) + r"[^{]*\{([^}]*)\}", NAU):
            body = m.group(1)
            for banned in ("grid", "max-width", "float", "column-count"):
                assert banned not in body, (sel, body)
    for page in ("/models", "/model/pf2s"):
        html = client.get(page).text
        assert '<details class="card intro">' in html, page


def test_figures_and_equations_center():
    """Figures center at their natural widths (the diagram macros' inline
    margin auto); equation panels span the card, flat (no well of their
    own), with the equation lines centered inside."""
    html = client.get("/methods").text
    assert html.count('role="img"') >= 2             # compartment + two-strain
    assert "display:block;margin:.6rem auto" in html  # the diagram macros
    assert 'class="eqpanel"' in html
    assert ".eqpanel{margin:.45rem 0 .25rem;" in JOINED
    assert "text-align:center" in JOINED.split(".eqpanel{", 1)[1] \
        .split("}", 1)[0]
    # the panels carry no width cap of their own any more
    assert "max-width:800px" not in NAU


def test_the_left_hugging_overrides_are_gone():
    """The pre-rebuild left-alignment override blocks must never come
    back, in the shell, the page, or any rendered reading page."""
    assert FIG_RULE not in BASE_T
    assert FIG_RULE not in METHODS_T
    assert EQ_RULE not in BASE_T
    assert EQ_RULE not in METHODS_T
    for page in READING_PAGES:
        html = client.get(page).text
        assert FIG_RULE not in html, page
        assert EQ_RULE not in html, page


def test_operational_pages_keep_the_same_shell():
    for page in ("/", "/data", "/forecast", "/runs", "/retro", "/output"):
        html = client.get(page).text
        assert '<main id="main" class="">' in html, page
        assert 'class="reading"' not in html, page
