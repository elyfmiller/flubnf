"""Phone width and large text: Storage's rows, the run ledger's filter, the
Sandbox's menus and runs table, the Display menu and the research run's
particles field keep their words readable and inside the screen (checked in
Chromium at 390 and 768 px, text 100, 130 and 160%).

Each check asks the cascade (css_cascade: the page's stylesheets in link
order) what the element gets at that width, so a later or stronger rule
that undoes the fix, or a rule left outside its media block, fails it."""
from pathlib import Path

import css_cascade as C

STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"
TEMPLATES = Path(__file__).resolve().parents[1] / "ui" / "templates"
PHONE, WIDE = 390, 1280
MAIN = ("html", "body", "main")


def _css(name):
    return (STATIC / name).read_text(encoding="utf-8")


def _get(cas, chain, props, width):
    """(property, value) the cascade gives the last element of `chain`."""
    win = cas.winner(C.path(*chain), props, width)
    return None if win is None else (win.prop, " ".join(win.value.split()))


def test_a_storage_row_stacks_its_size_and_action_under_the_title_on_a_phone():
    # three columns left the title 0 px at 160% and pushed Delete off screen
    assert '<div class="st-row"' in (TEMPLATES / "runs.html").read_text(
        encoding="utf-8")
    cas = C.Cascade.page("tabs/storage.css")
    row = MAIN + ("div.card", "section.st-sec", "div.st-row")
    assert _get(cas, row, "grid-template-columns", PHONE) == (
        "grid-template-columns", "minmax(0,1fr) auto")
    assert _get(cas, row, "grid-template-areas", PHONE) == (
        "grid-template-areas", '"title title" "meta meta" "size act"')
    # a wide window keeps the three columns
    assert _get(cas, row, "grid-template-areas", WIDE) == (
        "grid-template-areas", '"title size act" "meta size act"')


def test_a_segmented_switch_wraps_rather_than_squeezing_its_words():
    # the ledger's six filters drew over each other at 130 and 160%
    cas = C.Cascade.page("tabs/storage.css")
    seg = MAIN + ("div.st-filter#st-filter", "div.uk-seg")
    choice = seg + ("button[type=button][aria-pressed=false]",)
    for width in (PHONE, WIDE):
        assert _get(cas, seg, ("flex-wrap", "flex-flow"), width) == (
            "flex-wrap", "wrap")
        # no later longhand takes back the shorthand's grow and shrink
        assert _get(cas, choice, ("flex", "flex-grow", "flex-shrink",
                                  "flex-basis"), width) == ("flex", "1 1 auto")
        assert _get(cas, choice, "box-shadow", width) == (
            "box-shadow", "0 -1px 0 var(--field-line)")


def test_the_sandbox_menus_open_inside_the_screen():
    # anchored right:0 to a button that sits at the left on a phone, they
    # hung off the left edge
    cas = C.Cascade.page("bngl-editor.css", "tabs/sandbox.css")
    manage = MAIN + ("div.sbhead", "div.sbhead-menus", "details.sbmanage[open]")
    menu = manage + ("div.sbmenu",)
    assert _get(cas, manage, "position", PHONE) == ("position", "static")
    assert _get(cas, menu, "left", PHONE) == ("left", "0")
    assert _get(cas, menu, "right", PHONE) == ("right", "auto")
    # a wide window: the menu hangs from its button's right edge
    assert _get(cas, manage, "position", WIDE) == ("position", "relative")
    assert _get(cas, menu, "right", WIDE) == ("right", "0")
    # wider windows at large text: moved back inside when opened
    js = _css("sandbox.js")
    assert "d.addEventListener('toggle'" in js
    assert "if (left < 8) m.style.right = (left - 8) + 'px';" in js


def test_the_manage_menus_rows_stay_inside_it_at_large_text():
    # SB-01: at 390 px and text 130 and 160%, Duplicate and Delete model
    # ended past the menu's edge (Chromium: Delete model at 474 and 582 px
    # in a menu ending at 367 and 362): the rows could not wrap, the field
    # (13rem) could not shrink, and Download model would not break
    page = (TEMPLATES / "sandbox.html").read_text(encoding="utf-8")
    assert '<div class="row sb-menurow">' in page
    assert '<form method="post" action="/sandbox/new" class="sbdup">' in page
    cas = C.Cascade.page("bngl-editor.css", "tabs/sandbox.css")
    menu = MAIN + ("div.sbhead", "div.sbhead-menus", "details.sbmanage[open]",
                   "div.sbmenu")
    dup_row = menu + ("form.sbdup", "div.row")
    file_row = menu + ("div.row.sb-menurow",)
    field = dup_row + ("input#sb-dup-name[name=name][required]",)
    for row in (dup_row, file_row):
        assert _get(cas, row, ("flex-wrap", "flex-flow"), PHONE) == (
            "flex-wrap", "wrap")
    # Download model (.zip) alone is wider than the menu at 160%: its words
    # may break; wider windows keep each label on one line
    for item in (file_row + ("a.btn.quiet[download]",),
                 file_row + ("form", "button.quiet.sb-danger[type=button]")):
        assert _get(cas, item, "white-space", PHONE) == (
            "white-space", "normal"), item
        assert _get(cas, item, "white-space", WIDE) == (
            "white-space", "nowrap"), item
    assert _get(cas, field, "min-width", PHONE) == ("min-width", "0")
    basis = cas.winner(C.path(*field), ("flex", "flex-basis"), PHONE)
    assert basis is not None
    basis = basis.value.split()[-1] if basis.prop == "flex" else basis.value
    chain = C.path(*menu)
    pad = cas.winner(chain, ("padding", "padding-left", "padding-right"),
                     PHONE)
    assert pad.prop == "padding"
    side = pad.value.split()[1 if len(pad.value.split()) > 1 else 0]
    for text in (100, 130, 160):
        root = 16 * text / 100
        room = (C.px(cas.value(chain, "max-width", PHONE), root, PHONE)
                - 2 * C.px(side, root, PHONE) - 2)
        # the field starts no wider than the menu's inside, and may shrink
        assert C.px(basis, root, PHONE) <= room, (text, basis, room)
    # a wide window keeps the one-line rows and the 13rem field
    assert _get(cas, dup_row, ("flex-wrap", "flex-flow"), WIDE) == (
        "flex-wrap", "nowrap")
    assert _get(cas, field, "width", WIDE) == ("width", "13rem")


def test_the_sandbox_runs_table_shows_it_scrolls_sideways_on_a_phone():
    # its last columns were cut mid-number with no cue
    cas = C.Cascade.page("bngl-editor.css", "tabs/sandbox.css")
    box = MAIN + ("div.card", "div.sbscroll")
    got = _get(cas, box, ("background", "background-image"), PHONE)
    assert got and got[0] == "background"
    assert got[1].startswith(
        "linear-gradient(to right,var(--card) 40%,transparent) left/1.5rem "
        "100% no-repeat local,")
    assert "no-repeat scroll" in got[1]
    assert _get(cas, box, ("overflow-x", "overflow"), PHONE) == (
        "overflow-x", "auto")


def test_the_display_menu_fits_its_readout_and_theme_names_at_large_text():
    cas = C.Cascade.page()
    pop = ("html", "body", "header.nav", "details.display#displaymenu[open]",
           "div.displaypop", "section.dm-sec")
    slider = pop + ("div.fontsize", "input#dm-fs[type=range]")
    grid = pop + ("div.themepick", "div.dm-grid")
    for width in (PHONE, WIDE):
        assert _get(cas, slider, ("flex", "flex-grow", "flex-shrink",
                                  "flex-basis"), width) == ("flex", "1 1 auto")
        assert _get(cas, slider, "min-width", width) == ("min-width", "3rem")
        assert _get(cas, slider, "width", width) == ("width", "auto")
        assert _get(cas, grid, "display", width) == ("display", "grid")
        assert _get(cas, grid, "grid-template-columns", width) == (
            "grid-template-columns", "repeat(auto-fill,minmax(5em,1fr))")


def test_the_research_runs_particles_keep_their_number_visible():
    # the live count beside the field squeezed it to "1000C"
    cas = C.Cascade.page("tabs/models.css")
    affix = MAIN + ("div.card.md-research#research-run", "form",
                    "div.md-field", "span.uk-affix")
    field = affix + ("input#rr-particles[type=number]",)
    for width in (PHONE, WIDE):
        assert _get(cas, affix, ("flex-wrap", "flex-flow"), width) == (
            "flex-wrap", "wrap")
        assert _get(cas, field, ("flex", "flex-basis"), width) == (
            "flex-basis", "9ch")
        assert _get(cas, field, "min-width", width) == ("min-width", "9ch")
