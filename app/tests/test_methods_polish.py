"""Methods polish (methods.html, tabs/methods.css, knobs.py, diagrams.html).

  * a contents-bar jump lands the section title under the bar: the bar's
    height is measured again after the print button joins it and whenever
    it changes, and the Performance chip's target is its card;
  * the chip marked current is the last section whose top has passed the
    bar, and the last one once the page is scrolled to its end;
  * a prior range's rule is stated per distribution (0 ≤ low < high, or
    0 < low < high for the log-uniform priors); the panel's refusal
    already says it in words;
  * each setting's note on Methods is one plain sentence: no file paths,
    dates, names, screen figures or raw keys;
  * the two Policies folds' bodies continue from their titles;
  * printing breaks inside a card (a card taller than a page no longer
    pushes a blank page) but never inside a figure, table or fold;
  * every table scroller can be reached by keyboard and is named, as the
    figure scrollers are.
"""
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import knobs as K                        # noqa: E402
from app.core import site_build                        # noqa: E402
from app.ui.server import app as srv                   # noqa: E402

client = TestClient(srv)
STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"


def _methods() -> str:
    return client.get("/methods").text


# ------------------------------------------------- ME-04: jumps land in view

def test_the_bar_is_measured_after_the_print_button_and_when_it_changes():
    html = _methods()
    js = html.split("bar.appendChild(pb);", 1)[1]
    assert js.index("barH();") < js.index("addEventListener('beforeprint'")
    assert "if ('ResizeObserver' in window) new ResizeObserver(barH).observe(bar);" in js
    # the Performance chip's target is its card, as the other chips' are
    assert '<div class="card" id="performance"><h2>Measured performance</h2>' in html
    assert '<span id="performance"></span>' not in html


def test_the_site_harvest_still_drops_the_performance_card():
    site = site_build.harvest_methods({k: "x" for k in ("pybnf", "bngsim",
                                                        "bionetgen", "fastapi",
                                                        "plotly")})
    assert "Measured performance" not in site
    assert 'id="performance"' not in site


# ----------------------------------------- ME-05: the chip that reads current

def test_the_current_chip_is_the_last_section_passed_and_the_last_at_the_end():
    html = _methods()
    js = html.split("function spy()", 1)[1].split("var ticking", 1)[0]
    assert "if (secs[i].el.getBoundingClientRect().top <= band + 1) cur = secs[i];" in js
    assert "if (innerHeight + pageYOffset >= de.scrollHeight - 2) cur = secs[secs.length - 1];" in js
    assert "addEventListener('scroll', onScroll, {passive: true});" in html
    assert "seen[" not in html


# --------------------------------------------- ME-13: the prior range's rule

def test_a_prior_ranges_rule_is_stated_per_distribution():
    assert K.BY_KEY["pf.prior.mult"].range_text() == "0 < low < high"
    assert K.BY_KEY["pf.prior.r"].range_text() == "0 < low < high"
    assert K.BY_KEY["pf.prior.Reff"].range_text() == "0 ≤ low < high"
    assert K.BY_KEY["pf.prior.eps1"].range_text() == "0 ≤ low < high"
    html = _methods()
    row = html.split('id="set-pf-prior-mult"', 1)[1].split("</tr>", 1)[0]
    assert '<td data-label="Range">0 &lt; low &lt; high</td>' in row
    row = html.split('id="set-pf-prior-Reff"', 1)[1].split("</tr>", 1)[0]
    assert '<td data-label="Range">0 ≤ low &lt; high</td>' in row
    assert "the engine's rule" not in html


# ------------------------------------------------ ME-16: the notes are plain

def test_each_settings_note_is_one_plain_sentence():
    from app.ui.routes.methods import settings_reference
    notes = [r["note"] for g in settings_reference() for r in g["rows"]
             if r["note"]]
    assert len(notes) == 11
    keys = "|".join(re.escape(k) for k in K.BY_KEY)
    for n in notes:
        assert n.endswith(".") and ". " not in n, n
        assert len(n.split()) <= 45, n
        assert not re.search(keys, n), n                    # labels, not keys
        assert not re.search(r"docs/|\d{4}-\d{2}-\d{2}|Spencer|Ely|"
                             r"Pre-registered|rho\*mult|season_total", n), n
    html = client.get("/methods").text
    assert "Pre-registered screen" not in html and "Spencer Fox" not in html
    # what the sealed record ran stays
    assert "the sealed record ran 0.30" in K.BY_KEY["pf.jitter"].note


# ------------------------------------------- ME-18: the fold bodies continue

def test_the_policies_folds_do_not_repeat_their_titles():
    html = _methods()
    for fid, start in (("mt-newest", "<p>It is the forecaster's decision, per state"),
                       ("mt-sealcaveats", "<p>Seven of 76 sealed weeks' vintages")):
        body = html.split(f'id="{fid}"', 1)[1].split("</details>", 1)[0]
        body = body.split('<div class="uk-fold-body">', 1)[1].strip()
        assert body.startswith(start), (fid, body[:80])


# ---------------------------------------------- ME-21: printing breaks inside

def test_printing_breaks_inside_a_card_but_not_a_figure_or_table():
    css = (STATIC / "tabs" / "methods.css").read_text()
    printed = css.split("@media print{", 1)[1].split("\n}\n", 1)[0]
    assert ".mt-doc .card{break-inside:avoid" not in printed
    assert ".mt-doc .card{box-shadow:none;border-color:var(--line)}" in printed
    assert (".mt-doc .figscroll,.mt-doc figure,.mt-doc .uk-stats,.mt-doc tr"
            "{break-inside:avoid;page-break-inside:avoid}") in printed
    assert ".mt-doc thead{display:table-header-group}" in printed
    assert ".mt-doc .card h2,.mt-doc .card h3,.mt-doc summary{break-after:avoid" in printed


# ------------------------------------------ ME-22: the table scrollers reach

def test_every_table_scroller_can_be_reached_and_is_named():
    html = _methods()
    assert '<div style="overflow-x:auto">' not in html
    wrappers = re.findall(r'<div class="(mt-scroll|mt-setscroll|eqvars-scroll)"([^>]*)>', html)
    assert len(wrappers) >= 8, len(wrappers)
    for cls, attrs in wrappers:
        assert 'tabindex="0"' in attrs and 'role="region"' in attrs, (cls, attrs)
        assert re.search(r'aria-label="[^"]+ \(scrolls\)"', attrs), (cls, attrs)
    for label in ("Record by season (scrolls)",
                  "Measured performance by season (scrolls)",
                  "Components and versions (scrolls)", "Variables (scrolls)",
                  "Fixed by the model definition (scrolls)",
                  "Fit window (scrolls)"):
        assert f'aria-label="{label}"' in html, label
    # each settings group's table is named after the group
    groups = html.count('<details class="uk-fold mt-fold" id="mt-set-')
    assert groups >= 4
    assert len(re.findall(r'aria-label="[^"]+ \(scrolls\)"', html)) >= groups + 5
    css = (STATIC / "tabs" / "methods.css").read_text()
    assert ".mt-scroll{overflow-x:auto}" in css
    assert ".mt-scroll:focus-visible,.mt-setscroll:focus-visible,.eqvars-scroll:focus-visible{" in css
    # the model pages share the variables table
    assert 'class="eqvars-scroll" tabindex="0" role="region" aria-label="Variables (scrolls)"' \
        in client.get("/models").text
