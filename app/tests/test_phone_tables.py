"""Phone width and large text: the tables, drawings and folds that were cut
off or fell apart at 390 px (and at text 130 to 160%) keep their facts on
the screen (checked in Chromium; these pin the rules and markup)."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.ui import server as srv

client = TestClient(srv.app)
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


def _phone(name, query="@media(max-width:640px){\n  .eqpanel"):
    return _flat(_media(_css(name), query))


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
    phone = _phone("nau.css")
    assert ".pipe,.figscroll{overflow-x:auto;" in phone
    assert ".figscroll,.sbscroll{background:" in phone


def test_a_setting_stacks_with_its_range_and_default_on_a_phone():
    # ME-06: Range and Default sat 300 px off-screen in a 38rem table
    html = client.get("/methods").text
    assert '<td data-label="Range">' in html and '<td data-label="Default">' in html
    phone = _phone("tabs/methods.css", "@media (max-width:640px){\n  .mt-rec")
    assert ".mt-settings{min-width:0}" in phone
    assert ".mt-settings thead{display:none}" in phone
    assert '.mt-settings td[data-label]::before{content:attr(data-label) ": "}' in phone


def test_a_variables_table_puts_the_units_and_source_under_the_meaning_on_a_phone():
    # ME-07 (also MO-19): the Source column was cut to "ind", "der", "fitt"
    # while one-letter symbols took a quarter of the width
    phone = _phone("nau.css")
    assert ".eqvars-t thead{display:none}" in phone
    assert (".eqvars-t tr{display:grid;grid-template-columns:fit-content(6rem) "
            "minmax(0,1fr);") in phone
    assert ".eqvars-t tbody th{grid-row:span 3;white-space:normal}" in phone


def test_the_records_seasons_never_split_at_their_hyphen():
    # ME-08: "2023-" / "24" on a phone, and the table 7 px wider than its box
    html = client.get("/methods").text
    for label in ("2023&#8209;24", "2024&#8209;25", "2025&#8209;26",
                  "2024&#8209;25 and 2025&#8209;26"):
        assert f"<td>{label}</td>" in html, label
    assert "<td>2023-24</td>" not in html
    assert '<table class="mt-rec">' in html
    phone = _phone("tabs/methods.css", "@media (max-width:640px){\n  .mt-rec")
    assert ".mt-rec td,.mt-rec th{padding:.28rem .3rem}" in phone


def test_a_long_label_cannot_starve_a_fact_lists_values():
    # ME-09: "Placement among teams" took its full width at 160% text and
    # the values broke letter by letter
    kit = _flat(_css("ui-kit.css"))
    assert ".uk-stats--kv{grid-template-columns:fit-content(40%) minmax(0,1fr);" in kit


def test_a_long_fold_title_wraps_beside_its_chevron():
    # ME-10: the chevron sat alone on a line and the title started below it
    kit = _flat(_css("ui-kit.css"))
    assert ".uk-fold-sum{min-width:0;max-width:calc(100% - 1.4em);overflow-wrap:anywhere}" in kit


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
    assert ".figscroll > svg.dg-harm{min-width:560px}" in _phone("nau.css")


def test_a_long_dataset_name_wraps_and_the_stored_table_scrolls_in_its_card():
    # DA-10: an 80-character name tripled every row and ran the browser's
    # heading off the card; DA-11: the hidden "Actions" header escaped the
    # card and scrolled the page sideways at 768 px and 160% text
    nau = _flat(_css("nau.css"))
    assert ".dstable td.dsname,#h-ds-browse{overflow-wrap:anywhere}" in nau
    assert ".dstable td.dsname{min-width:12rem}" in nau
    assert (".dsup .tablewrap,#datasets .tablewrap{max-width:100%;overflow-x:auto;"
            "position:relative}") in nau
    data = _flat(_css("tabs/data.css"))
    assert ".dt-rowacts{display:flex;flex-wrap:nowrap;" in data
    assert "@media(max-width:600px){.dt-rowacts{flex-wrap:wrap}}" in data
