"""Phone width and large text: Storage's rows, the run ledger's filter, the
Sandbox's menus and runs table, the Display menu and the research run's
particles field keep their words readable and inside the screen (checked in
Chromium at 390 and 768 px, text 100, 130 and 160%; these pin the rules)."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"


def _css(name):
    return (STATIC / name).read_text(encoding="utf-8")


def _flat(css):
    return re.sub(r"\s+", " ", css)


def _media(css, query):
    """The body of the first @media block with this query."""
    i = css.index(query)
    body, depth = "", 0
    for ch in css[css.index("{", i):]:
        depth += ch == "{"
        depth -= ch == "}"
        body += ch
        if depth == 0:
            return body
    raise AssertionError(query)


def test_a_storage_row_stacks_its_size_and_action_under_the_title_on_a_phone():
    # three columns left the title 0 px at 160% and pushed Delete off screen
    phone = _flat(_media(_css("tabs/storage.css"), "@media (max-width:40rem)"))
    assert ('.st-row{grid-template-columns:minmax(0,1fr) auto; '
            'grid-template-areas:"title title" "meta meta" "size act"}') in phone


def test_a_segmented_switch_wraps_rather_than_squeezing_its_words():
    # the ledger's six filters drew over each other at 130 and 160%
    kit = _flat(_css("ui-kit.css"))
    assert ".uk-seg{flex-wrap:wrap}" in kit
    assert (".uk-seg > *{flex:1 1 auto;margin-left:-1px; "
            "box-shadow:0 -1px 0 var(--field-line)}") in kit


def test_the_sandbox_menus_open_inside_the_screen():
    # anchored right:0 to a button that sits at the left on a phone, they
    # hung off the left edge
    phone = _flat(_media(_css("tabs/sandbox.css"), "@media (max-width:640px)"))
    assert ".sbhead-menus > details.sbmanage{position:static}" in phone
    assert ".sbhead-menus .sbmenu{left:0;right:auto}" in phone
    # wider windows at large text: moved back inside when opened
    js = _css("sandbox.js")
    assert "d.addEventListener('toggle'" in js
    assert "if (left < 8) m.style.right = (left - 8) + 'px';" in js


def test_the_sandbox_runs_table_shows_it_scrolls_sideways_on_a_phone():
    # its last columns were cut mid-number with no cue
    phone = _flat(_media(_css("nau.css"), "@media(max-width:640px){\n  .eqpanel"))
    assert ".figscroll,.sbscroll{background:" in phone


def test_the_display_menu_fits_its_readout_and_theme_names_at_large_text():
    nau = _flat(_css("nau.css"))
    assert ".fontsize input[type=range]{flex:1 1 auto;min-width:3rem;" in nau
    assert ".dm-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(5em,1fr));" in nau


def test_the_research_runs_particles_keep_their_number_visible():
    # the live count beside the field squeezed it to "1000C"
    css = _flat(_css("tabs/models.css"))
    assert ".md-research .uk-affix{flex-wrap:wrap}" in css
    assert ".md-research .uk-affix > input{flex-basis:9ch;min-width:9ch}" in css
