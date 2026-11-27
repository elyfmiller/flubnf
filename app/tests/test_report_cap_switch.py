"""The weekly report's tail figures and its cap switch (roadmap "Now" #9,
compromise C4): one legend line explains the "h3 97.5%" figures beside
each location's name, each figure is spelled out for assistive tech, one
report-wide Submitted / Before cap switch sets every chart, and only a
location the cap changed carries a "cap applied" link whose line gives
its h3 97.5% before and after. The switch's script runs on the served
markup (served_dom: JavaScriptCore here, node in CI)."""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import served_dom as SD                                       # noqa: E402
from app.core import report_grid as G                         # noqa: E402
from app.core import report_v2                                 # noqa: E402
from app.tests.test_report_design_pass import _bundle, _render  # noqa: E402
from app.tests.test_report_grid import _filed  # noqa: E402

needs_js = pytest.mark.skipif(
    not SD.HAVE_JS, reason="no JavaScript engine (JavaScriptCore jsc or node)")


def _capped(tmp_path, top=30.0):
    """A rendered report whose Ohio file the cap lowered (the model's own
    h3 97.5% is 46; the file's `top`), Alabama's file unchanged."""
    b = _bundle()
    oh = next(p for p in b["grid"]["panels"] if p["key"] == "OH")
    al = next(p for p in b["grid"]["panels"] if p["key"] == "AL")
    _filed(tmp_path, oh, top=top)
    _filed(tmp_path, al, fips="01")
    return report_v2.render_bundle(b, tmp_path / "r.html").read_text(
        encoding="utf-8")


def _section(html, start, end="</section>"):
    s = html[html.index(start):]
    return s[:s.index(end)]


def _figure(html, key):
    s = html[html.index(f'<figure class="gpanel" id="g-{key}"'):]
    return s[:s.index("</figure>")]


# ------------------------------------------------------- the legend line

def test_one_legend_line_explains_the_tail_figures(tmp_path):
    """Under the All locations legend, once: what "h3 97.5%" is (the top
    of each model's 95% range for the last forecast week, named), what it
    is a multiple of (the cap's own level, the last three weeks'
    average), when it turns red, and, on a capped run, what the arrow
    is."""
    html = _capped(tmp_path)
    assert html.count('class="g-tailkey"') == 1
    grid = _section(html, 'id="all-locations"')
    line = grid[grid.index('<p class="g-tailkey">'):]
    line = line[:line.index("</p>")]
    words = re.sub(r"<[^>]+>", "", line)
    assert words.startswith("h3 97.5% is the top of each model's 95% range "
                            "for the last forecast week (h3, ending Jan 31)")
    assert "a multiple of the average of the last three weeks of data" in words
    assert "before the cap" in words
    assert f"red above {G.TAIL_X:.0f}×" in words
    assert ("→ marks the same figure in the submitted file, after the "
            "cap.") in words
    # it sits in the first page's legend row, after the model keys
    head = grid[grid.index('<div class="g-head"'):]
    head = head[:head.index('<div class="g-cells">')]
    assert head.index('class="g-key"') < head.index('class="g-tailkey"')
    # "the last three weeks" is the cap's own level, as registered
    from flubnf import tailcap
    assert tailcap.RECENT_WEEKS == 3 and tailcap.LEVEL_PRODUCTION == "mean"


def test_an_uncapped_report_has_no_arrow_words(tmp_path):
    """Where no file differs from the model's own, the line says nothing
    about a cap or an arrow, and the report has no switch."""
    html = _render(tmp_path)
    line = html[html.index('<p class="g-tailkey">'):]
    line = line[:line.index("</p>")]
    assert "cap" not in line and "→" not in line
    assert 'data-ba-all="' not in html and 'id="capswitch"' not in html


def test_each_figure_is_spelled_out_for_assistive_tech(tmp_path):
    """Each model's figure carries its words (M-E12's form) in visually
    hidden text, the marks themselves hidden from assistive tech; the
    hover says them all."""
    html = _capped(tmp_path)
    oh = _figure(html, "OH")
    tail = oh[oh.index('<span class="g-tail"'):]
    pf_name, an_name = G._SHORT["pf"], G._SHORT["analogue"]
    # recent level 22 (the last three weeks 21, 22, 23): 46 is 2.1x, the
    # file's 30 is 1.4x
    pf_words = (f"97.5% at h3 = 2.1× the last three weeks&#x27; average "
                f"({pf_name}), submitted 1.4×")
    assert f'<span class="uk-sr">{pf_words}</span>' in tail
    assert (f"the last three weeks&#x27; average ({an_name})</span>") in tail
    assert '<span class="g-tail-l" aria-hidden="true">h3 97.5%</span>' in tail
    assert '<span class="g-tail-own" aria-hidden="true">2.1×</span>' in tail
    assert '<span class="g-tail-f" aria-hidden="true">→1.4×' in tail
    title = re.search(r'<span class="g-tail" title="([^"]+)"', tail).group(1)
    assert pf_words in title and f"({an_name})" in title
    # above the red line, the words say so
    w = G.tail_words("analogue", 24.0, True, 11.0)
    assert w == (f"97.5% at h3 = 24× the last three weeks' average "
                 f"({an_name}), above 15×, submitted 11×")


def test_a_ratio_just_under_ten_prints_as_ten():
    assert G._times(9.97) == "10×" and G._times(9.94) == "9.9×"


# --------------------------------------------------- the one switch

def test_one_report_wide_switch_and_no_pair_on_any_card(tmp_path):
    """The kit's segmented switch, once, in the report's controls, labelled
    Charts, Submitted pressed; no card or detail carries a pair."""
    html = _capped(tmp_path)
    assert html.count('data-ba-all="s"') == 1
    assert html.count('data-ba-all="b"') == 1
    assert html.count('class="uk-seg" id="capswitch"') == 1
    controls = _section(html, '<div class="rp-controls">',
                        '<nav class="rp-jump"')
    sw = controls[controls.index('id="capswitch"'):]
    assert re.search(r'data-ba-all="s" aria-pressed="true"[^>]*>Submitted<', sw)
    assert re.search(r'data-ba-all="b" aria-pressed="false"[^>]*>Before cap<',
                     sw)
    assert '<span class="rp-lbl" aria-hidden="true">Charts</span>' in controls
    assert 'role="group" aria-label="Charts: the submitted file' in sw
    assert "data-ba-key" not in html and 'class="uk-seg g-ba"' not in html
    # the per-card switch's rules are gone with it
    assert ".g-ba{" not in G.grid_css() and ".g-ba >" not in G.grid_css()
    assert ".rp-ba > .g-ba" not in html


# ---------------------------------------------- the "cap applied" link

def test_only_a_changed_card_carries_the_link_with_its_figures(tmp_path):
    """Ohio's file differs: its card has the link and a closed line with
    the h3 97.5% before and after, in admissions and as multiples;
    Alabama's file matches the model's own and its card has no control
    at all."""
    html = _capped(tmp_path)
    oh, al = _figure(html, "OH"), _figure(html, "AL")
    assert ('<button type="button" class="g-capbtn" data-cap-key="OH" '
            'aria-expanded="false" aria-controls="gcap-OH">cap applied'
            '<span class="uk-sr"> to Ohio</span></button>') in oh
    line = re.search(r'<p class="g-capline" id="gcap-OH" '
                     r'data-cap-line="OH" hidden>([^<]+)</p>', oh)
    assert line, oh
    pf_name = G._SHORT["pf"]
    assert line.group(1) == (
        "Shown before the cap. h3 97.5%, before → submitted: "
        f"{pf_name} 46 → 30 (2.1× → 1.4×).")
    assert "<button" not in al and "g-capline" not in al
    assert "data-ba" not in al and "data-cap" not in al
    # the United States panel and its feature under the map: unchanged
    assert "data-cap-key" not in _figure(html, "US")
    assert "data-cap-key" not in _section(html, 'id="us-feature"', "</aside>")


def test_the_link_follows_the_card_into_the_feature_and_the_detail(tmp_path):
    """A capped United States carries the link on its panel, on the
    larger panel under the map and in its detail, one key, unique ids."""
    b = _bundle()
    b["details"]["US"] = dict(b["details"]["OH"], name="United States")
    us = next(p for p in b["grid"]["panels"] if p["key"] == "US")
    _filed(tmp_path, us, fips="US", top=30.0)
    html = report_v2.render_bundle(b, tmp_path / "r.html").read_text(
        encoding="utf-8")
    # the panel, the feature, the national detail
    assert html.count('data-cap-key="US"') == 3
    feat = _section(html, 'id="us-feature"', "</aside>")
    assert 'aria-controls="gcap-US-feature"' in feat
    assert 'id="gcap-US-feature" data-cap-line="US" hidden' in feat
    nat = _section(html, '<section class="state" id="st-US"')
    assert 'aria-controls="gcap-st-US"' in nat
    assert nat.count('data-ba-for="US"') == 2        # the fan, the numbers
    ids = re.findall(r' id="(gcap-[^"]+)"', html)
    assert sorted(ids) == ["gcap-US", "gcap-US-feature", "gcap-st-US"]
    # a detail with no before-the-cap version of its own takes no link
    b2 = _bundle()
    b2["details"]["OH"]["model"] = "analogue"         # no such file below
    oh = next(p for p in b2["grid"]["panels"] if p["key"] == "OH")
    _filed(tmp_path / "w", oh, top=30.0)
    html2 = report_v2.render_bundle(b2, tmp_path / "w" / "r.html").read_text(
        encoding="utf-8")
    sec = _section(html2, '<section class="state" id="st-OH"')
    assert "data-cap-key" not in sec and 'data-ba-for="OH"' not in sec
    assert html2.count('data-cap-key="OH"') == 1      # the panel keeps it


def test_paper_keeps_the_drawing_without_the_link(tmp_path):
    """Print shows the submitted drawing: the link and its line stay off
    paper; the legend line prints."""
    css = G.grid_css()
    pr = css[css.index("@media print{"):]
    assert ".g-capbtn,.g-capline{display:none!important}" in pr
    assert ".g-tailkey{font-size:6.6pt}" in pr


def test_the_link_is_a_text_link_and_no_pill():
    """A pressable word, underlined in the link colour, with no outline
    and no pill radius."""
    css = G.grid_css()
    rule = css[css.index(".g-capbtn{"):].split("}", 1)[0]
    assert "border:0" in rule and "text-decoration:underline" in rule
    assert "color:var(--gold)" in rule and "radius" not in rule


# ----------------------------------------- the switch's script, served

_PRELUDE = r"""
var window = {};
var EVENTS = [];
var CustomEvent = function (t, o) { this.type = t; this.detail = o.detail; };
var dispatchEvent = function (e) {
  EVENTS.push(e.detail.key + ':' + e.detail.mode); };
// Element.closest, as a browser has it, over MiniDOM's own matches()
Object.getPrototypeOf(document).closest = function (sel) {
  for (var n = this; n && n.nodeType === 1; n = n.parentNode)
    if (n.matches(sel)) return n;
  return null;
};
"""

_BODY = r"""
function click(sel) {
  document.querySelector(sel).dispatchEvent({type: 'click', bubbles: true});
}
function shown(key) {
  var out = [], ws = document.querySelectorAll('[data-ba-for]');
  for (var i = 0; i < ws.length; i++) {
    if (ws[i].getAttribute('data-ba-for') !== key) continue;
    var vs = ws[i].querySelectorAll('[data-ba-v]');
    for (var j = 0; j < vs.length; j++)
      if (!vs[j].hidden) out.push(vs[j].getAttribute('data-ba-v'));
  }
  return out.join('');
}
function attr(sel, a) {
  var ns = document.querySelectorAll(sel), out = [];
  for (var i = 0; i < ns.length; i++) out.push(ns[i].getAttribute(a));
  return out.join(',');
}
function lines(key) {
  var ns = document.querySelectorAll('[data-cap-line]'), n = 0;
  for (var i = 0; i < ns.length; i++)
    if (ns[i].getAttribute('data-cap-line') === key && !ns[i].hidden) n++;
  return n;
}
function state() {
  var s = [shown('OH'), attr('button[data-ba-all]', 'aria-pressed'),
           attr('button[data-cap-key]', 'aria-expanded'), lines('OH'),
           EVENTS.join(' ')];
  EVENTS = [];
  return s;
}
var out = [state()];
click('button[data-ba-all="b"]'); out.push(state());
click('button[data-ba-all="s"]'); out.push(state());
click('button[data-cap-key="OH"]'); out.push(state());
click('button[data-ba-all="b"]'); click('button[data-ba-all="s"]');
out.push(state());
click('#gcap-st-OH');                      // the line itself: nothing
out.push(state());
document.querySelectorAll('button[data-cap-key="OH"]')[1]
  .dispatchEvent({type: 'click', bubbles: true});
out.push(state());
return out;
"""


def _script(html, marker, tmp_path):
    """The page's inline script holding `marker`, as a file."""
    for m in re.finditer(r"<script>(.*?)</script>", html, re.S):
        if marker in m.group(1):
            f = tmp_path / "ba.js"
            f.write_text(m.group(1), encoding="utf-8")
            return f
    raise AssertionError(f"no inline script holds {marker!r}")


@needs_js
def test_the_switch_and_the_links_move_every_part(tmp_path):
    """The served report's own handler on its own markup: Before cap shows
    every location's before parts and tells the live charts (rp-ba); a
    location's link shows it before the cap whatever the switch says,
    opens its lines and marks every link for it expanded; a second press
    on any of them closes it."""
    html = _capped(tmp_path / "run")
    js = _script(html, "data-ba-all", tmp_path)
    page = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S)
    got = SD.run(tmp_path, page, [js], _BODY, prelude=_PRELUDE)
    assert got == [
        ["ss", "true,false", "false,false", 0, ""],
        ["bb", "false,true", "false,false", 0, "OH:b"],
        ["ss", "true,false", "false,false", 0, "OH:s"],
        ["bb", "true,false", "true,true", 2, "OH:b"],
        ["bb", "true,false", "true,true", 2, "OH:b OH:b"],
        ["bb", "true,false", "true,true", 2, ""],
        ["ss", "true,false", "false,false", 0, "OH:s"],
    ]
