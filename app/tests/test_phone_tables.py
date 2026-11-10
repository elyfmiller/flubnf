"""Phone width and large text: the tables, drawings and folds that were cut
off or fell apart at 390 px (and at text 130 to 160%) keep their facts on
the screen (checked in Chromium). The markup is pinned as served; each rule
is checked through the cascade (css_cascade: the page's stylesheets in link
order), so a later or stronger rule that undoes it, or a rule left outside
its media block, fails the check."""
import re

from fastapi.testclient import TestClient

import css_cascade as C
from app.ui import server as srv

client = TestClient(srv.app)
PHONE, WIDE = 390, 1280
MAIN = ("html", "body", "main")
HOME = C.Cascade.page("tabs/home.css")
METHODS = C.Cascade.page("tabs/methods.css", "tabs/models.css")
MODEL = C.Cascade.page("tabs/models.css")
DATA = C.Cascade.page("tabs/data.css")


def _get(cas, chain, props, width):
    """(property, value) the cascade gives the last element of `chain`."""
    win = cas.winner(C.path(*chain), props, width)
    return None if win is None else (win.prop, " ".join(win.value.split()))


def _scrolls_with_its_cue(cas, box):
    """At phone width the box scrolls sideways and shows it (the shadow at
    the edge, nau.css .figscroll)."""
    assert _get(cas, box, ("overflow-x", "overflow"), PHONE) == (
        "overflow-x", "auto"), box
    bg = _get(cas, box, ("background", "background-image"), PHONE)
    assert bg and bg[0] == "background", box
    assert bg[1].startswith("linear-gradient(to right,var(--card) 40%,"), box


def test_the_home_workflow_and_performance_table_scroll_with_the_figures_cue():
    # HM-06, HM-09: the drawing was cut at the card's edge with no cue; at
    # larger text the table's last column was too. Both are now the kit's
    # scrolling regions (shadow at the edge, focusable, named)
    html = client.get("/").text
    assert ('<div class="pipe figscroll" tabindex="0" role="region" '
            'aria-label="Weekly forecasting workflow (scrolls)">') in html
    assert ('<div class="figscroll" tabindex="0" role="region" '
            'aria-label="Measured performance table (scrolls)">\n'
            '  <table class="perf">') in html
    _scrolls_with_its_cue(HOME, MAIN + (
        "div.card.hm-how", "div.pipe.figscroll[tabindex=0][role=region]"))
    _scrolls_with_its_cue(HOME, MAIN + (
        "div.grid2.homeperf", "div.card.hm-perf",
        "div.figscroll[tabindex=0][role=region]"))


def test_a_setting_stacks_with_its_range_and_default_on_a_phone():
    # ME-06: Range and Default sat 300 px off-screen in a 38rem table
    html = client.get("/methods").text
    assert '<td data-label="Range">' in html and '<td data-label="Default">' in html
    table = MAIN + ("div.mt-doc", "div.card", "div.mt-setscroll",
                    "table.mt-settings")
    assert _get(METHODS, table, "min-width", PHONE) == ("min-width", "0")
    assert _get(METHODS, table, "min-width", WIDE) == ("min-width", "38rem")
    assert _get(METHODS, table + ("thead",), "display", PHONE) == (
        "display", "none")
    for label in ("Range", "Default"):
        cell = table + ("tbody", "tr", f'td[data-label="{label}"]::before')
        assert _get(METHODS, cell, "content", PHONE) == (
            "content", 'attr(data-label) ": "'), label
        assert _get(METHODS, cell, "content", WIDE) is None, label


def test_a_variables_table_puts_the_units_and_source_under_the_meaning_on_a_phone():
    # ME-07 (also MO-19): the Source column was cut to "ind", "der", "fitt"
    # while one-letter symbols took a quarter of the width
    table = MAIN + ("div.card", "details.uk-fold.eqvars[open]",
                    "div.uk-fold-body", "div.eqvars-scroll", "table.eqvars-t")
    row, sym = table + ("tbody", "tr"), table + ("tbody", "tr", "th")
    for cas in (MODEL, METHODS):
        assert _get(cas, table + ("thead",), "display", PHONE) == (
            "display", "none")
        assert _get(cas, row, "display", PHONE) == ("display", "grid")
        assert _get(cas, row, "grid-template-columns", PHONE) == (
            "grid-template-columns", "fit-content(6rem) minmax(0,1fr)")
        assert _get(cas, sym, "grid-row", PHONE) == ("grid-row", "span 3")
        assert _get(cas, sym, "white-space", PHONE) == (
            "white-space", "normal")
        # a wide window keeps the table
        assert _get(cas, row, "display", WIDE) is None


def test_the_records_seasons_never_split_at_their_hyphen():
    # ME-08: "2023-" / "24" on a phone, and the table 7 px wider than its box
    html = client.get("/methods").text
    for label in ("2023&#8209;24", "2024&#8209;25", "2025&#8209;26",
                  "2024&#8209;25 and 2025&#8209;26"):
        assert f"<td>{label}</td>" in html, label
    assert "<td>2023-24</td>" not in html
    assert '<table class="mt-rec">' in html
    row = MAIN + ("div.mt-doc", "div.card", "div", "table.mt-rec", "tbody",
                  "tr")
    for cell in ("td", "th"):
        assert _get(METHODS, row + (cell,), ("padding", "padding-left",
                                             "padding-right"), PHONE) == (
            "padding", ".28rem .3rem"), cell


def test_a_long_label_cannot_starve_a_fact_lists_values():
    # ME-09: "Placement among teams" took its full width at 160% text and
    # the values broke letter by letter
    for cas, cls in ((METHODS, "mt-defs"), (MODEL, "md-facts")):
        facts = MAIN + ("div.card", f"dl.uk-stats.uk-stats--kv.{cls}")
        for width in (PHONE, WIDE):
            assert _get(cas, facts, "grid-template-columns", width) == (
                "grid-template-columns", "fit-content(40%) minmax(0,1fr)")


def test_a_long_fold_title_wraps_beside_its_chevron():
    # ME-10: the chevron sat alone on a line and the title started below it
    title = MAIN + ("div.card", "details.uk-fold", "summary",
                    "span.uk-fold-sum")
    for width in (PHONE, WIDE):
        assert _get(METHODS, title, "min-width", width) == ("min-width", "0")
        assert _get(METHODS, title, "max-width", width) == (
            "max-width", "calc(100% - 1.4em)")
        assert _get(METHODS, title, "overflow-wrap", width) == (
            "overflow-wrap", "anywhere")


def test_the_harmonic_scrolls_on_a_phone_and_set_expressions_hold_together():
    # MO-23: the harmonic's labels shrank to 8 px; "s ∈" / "{A, B}" and
    # "Binomial( n, shareA/" / "(A+B))" broke mid-expression
    for page in ("/models", "/model/pf2s", "/"):
        html = client.get(page).text
        assert re.search(r'<div class="figscroll" tabindex="0" role="region" '
                         r'aria-label="(Two-strain s|S)easonal harmonic \(scrolls\)">'
                         r'<svg class="dg-harm" viewBox="0 0 560 232"', html), page
    pf2s = client.get("/model/pf2s").text
    assert '<span class="nw"><i>s</i> &#8712; {A, B}</span>' in pf2s
    assert ('<span class="nw">Binomial(&#8239;<i>n</i>, '
            'share&#8202;A&#8202;/&#8202;(A&#8202;+&#8202;B)&#8239;)</span>') in pf2s
    for cas in (HOME, MODEL):
        box = MAIN + ("div.card", "div.figscroll[tabindex=0][role=region]")
        assert _get(cas, box + ("svg.dg-harm",), "min-width", PHONE) == (
            "min-width", "560px")
        _scrolls_with_its_cue(cas, box)


def test_a_long_dataset_name_wraps_and_the_stored_table_scrolls_in_its_card():
    # DA-10: an 80-character name tripled every row and ran the browser's
    # heading off the card; DA-11: the hidden "Actions" header escaped the
    # card and scrolled the page sideways at 768 px and 160% text
    wrap = MAIN + ("div.card#datasets", "div.tablewrap")
    row = wrap + ("table.compact.dstable", "tbody", "tr")
    name, acts = row + ("td.dsname",), row + ("td.dsactions", "div.dt-rowacts")
    for width in (PHONE, WIDE):
        assert _get(DATA, name, "overflow-wrap", width) == (
            "overflow-wrap", "anywhere")
        assert _get(DATA, wrap, "max-width", width) == ("max-width", "100%")
        assert _get(DATA, wrap, ("overflow-x", "overflow"), width) == (
            "overflow-x", "auto")
    assert _get(DATA, acts, ("flex-wrap", "flex-flow"), WIDE) == (
        "flex-wrap", "nowrap")
    assert _get(DATA, acts, ("flex-wrap", "flex-flow"), PHONE) == (
        "flex-wrap", "wrap")
    # a squeezed table keeps a readable name column
    assert _get(DATA, name, "min-width", WIDE) == ("min-width", "12rem")


def test_a_stacked_dataset_row_fits_a_phones_card_at_large_text():
    # the review of DA-10: once a row stacks (600 px and under) the name has
    # the whole line, but the column's 12rem floor stayed: 307 px at 160%
    # text in a card of about 298, so the table scrolled by 9 px
    name = MAIN + ("div.card#datasets", "div.tablewrap",
                   "table.compact.dstable", "tbody", "tr", "td.dsname")
    for width in (PHONE, 600):
        assert _get(DATA, name, ("flex-basis", "flex"), width) == (
            "flex-basis", "100%")
        floor = DATA.value(C.path(*name), "min-width", width)
        for text in (100, 130, 160):
            assert C.px(floor, 16 * text / 100, width) == 0, (width, text)
