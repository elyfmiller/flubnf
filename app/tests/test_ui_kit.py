"""The UI kit: the components that replace loose explanatory text
(templates/_tips.html macros, static/ui-kit.css, the FluBNFUI block of
static/tips.js; docs/UI-KIT.md).

Each macro is rendered through the console's own Jinja env and its
accessibility contract pinned: names, roles, the links between a control
and its explainer, state spoken as well as drawn. The stylesheet is held to
tokens only, and its measured pairs (a mark's word on the card and on the
page ground, an alert's text and icon, the current step's number) to the
contrast bars in every theme and mode that nau.css defines. A mark (a
badge, a tag, a name chip) is held to its look as well, in every sheet
that can style one: no outline, no fill, and no icon on a state that
asks nothing of the reader.
"""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from markupsafe import Markup                        # noqa: E402

import css_cascade as C                             # noqa: E402
from app.ui.templating import templates             # noqa: E402

REPO = Path(__file__).resolve().parents[2]
UI = REPO / "app" / "ui"
TIPS_T = (UI / "templates" / "_tips.html").read_text()
BASE_T = (UI / "templates" / "base.html").read_text()
KIT_CSS = (UI / "static" / "ui-kit.css").read_text()
TIPS_JS = (UI / "static" / "tips.js").read_text()
NAU = (UI / "static" / "nau.css").read_text()
TABS = UI / "static" / "tabs"
#: every sheet that can style a mark: the kit, nau.css and the console's
#: other shared sheets, then each tab's own
SHEETS = {p.relative_to(UI / "static").as_posix(): p.read_text()
          for p in sorted((UI / "static").glob("*.css"))
          + sorted(TABS.glob("*.css"))}
DOC = (REPO / "docs" / "UI-KIT.md").read_text()
DOCS_INDEX = (REPO / "docs" / "README.md").read_text()

MACROS = ("tip", "label", "icon", "icon_tip", "toggletip", "heading",
          "badge", "alert", "empty", "stats", "stat", "reason_button",
          "stepper", "progress", "legend", "fold", "meta", "tag",
          "namechip", "runname")
ICON_NAMES = ("info", "warning", "error", "check", "clock", "download",
              "upload", "folder", "external", "lock", "calendar", "refresh", "dot",
              "close")
STATES = ("ok", "warn", "error", "info", "neutral", "pending")
#: the states that ask nothing of the reader: the word alone, muted
QUIET = ("ok", "info", "neutral")
#: the states that ask something or are under way: icon and word, colored
LOUD = ("warn", "error", "pending")


def render(src: str, **ctx) -> str:
    return templates.env.from_string(
        '{% import "_tips.html" as t %}' + src).render(**ctx)


class _Tags(HTMLParser):
    """Every start tag as (tag, attrs dict), in document order."""

    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def tags(html: str) -> list:
    p = _Tags()
    p.feed(html)
    return p.tags


def first(html: str, tag: str, cls: str = "") -> dict:
    for t, a in tags(html):
        if t == tag and (not cls or cls in (a.get("class") or "").split()):
            return a
    raise AssertionError(f"no <{tag} class={cls!r}> in {html[:200]}")


# ------------------------------------------------ the two original macros

def test_tip_and_label_render_exactly_as_before():
    # tests elsewhere and the Python twin (app/core/runs.py _tip) rely on
    # this markup byte for byte
    assert render('{{ t.tip("a", "the a", "Text") }}') == (
        '<span class="tip"><button type="button" class="tipbtn"\n'
        ' aria-label="About the a" aria-describedby="tip-a">?</button\n'
        '><span class="tipbox" role="tooltip" id="tip-a">Text</span></span>')
    assert render('{% call t.tip("a", "the a") %}<b>rich</b>{% endcall %}'
                  ).endswith('id="tip-a"><b>rich</b></span></span>')
    assert render('{{ t.label("Name", "n", "Hint", for_="x") }}') == (
        '<div class="lblrow"><label for="x">Name</label>'
        '<span class="tip"><button type="button" class="tipbtn"\n'
        ' aria-label="About name" aria-describedby="tip-n">?</button\n'
        '><span class="tipbox" role="tooltip" id="tip-n">Hint</span>'
        '</span></div>')


def test_tip_text_is_escaped_and_rich_text_passes():
    html = render('{{ t.tip("a", "x", "<b>1 < 2</b>") }}')
    assert "&lt;b&gt;1 &lt; 2&lt;/b&gt;" in html
    rich = render('{{ t.badge("warn", "w", tiptext=m, id="w") }}',
                  m=Markup('<a href="/m">Methods</a>'))
    assert '<a href="/m">Methods</a>' in rich


# --------------------------------------------------------------- the icons

@pytest.mark.parametrize("name", ICON_NAMES)
def test_every_icon_is_decorative_currentcolor_and_em_sized(name):
    html = render('{{ t.icon(n) }}', n=name)
    a = first(html, "svg")
    assert a["aria-hidden"] == "true" and a["focusable"] == "false"
    assert a["width"] == a["height"] == "1em" and a["viewbox"] == "0 0 16 16"
    assert a["stroke"] == "currentColor" and a["fill"] == "none"
    assert "role" not in a
    body = html.split(">", 1)[1]
    assert len(body) > 20                               # a drawing, not empty
    # colors only through currentColor
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b|rgb\(", html)
    fills = set(re.findall(r'(?:fill|stroke)="([^"]+)"', body))
    assert fills <= {"currentColor", "none"}, fills


def test_a_labelled_icon_is_an_image_with_that_name():
    a = first(render('{{ t.icon("lock", label="Protected") }}'), "svg")
    assert a["role"] == "img" and a["aria-label"] == "Protected"
    assert "aria-hidden" not in a


def test_the_script_draws_the_same_icons():
    tpl = dict(re.findall(r'"(\w+)": \'([^\']*)\'', TIPS_T.split(
        "{% set ICONS = {", 1)[1].split("} %}", 1)[0]))
    js_block = TIPS_JS.split("var ICONS = {", 1)[1].split("};", 1)[0]
    js = dict(re.findall(r"(\w+): '([^']*)'", js_block))
    assert set(tpl) == set(ICON_NAMES) == set(js)
    assert tpl == js
    # the run results' relWIS verdict (app/core/runs.py) draws two of them
    from app.core.runs import _VERDICT_ICON
    for name, _state, _label, paths in _VERDICT_ICON.values():
        assert paths == tpl[name], name


def test_icon_tip_is_a_tip_whose_button_is_the_icon():
    html = render('{{ t.icon_tip("w1", "unreported weeks", "warning", '
                  '"3 states", state="warn") }}')
    b = first(html, "button", "tipbtn")
    assert "uk-tipicon" in b["class"] and "uk-c-warn" in b["class"]
    assert b["aria-label"] == "About unreported weeks"
    assert b["aria-describedby"] == "tip-w1"
    assert first(html, "span", "tipbox")["role"] == "tooltip"
    assert first(html, "svg")["aria-hidden"] == "true"


# ------------------------------------------------ headings and toggletips

def test_heading_keeps_its_name_clean_and_its_tip_beside_it():
    html = render('{{ t.heading("Archive", "archive", "Each dot is a week.") }}')
    assert html.startswith('<div class="uk-heading"><h2 id="h-archive">'
                           'Archive</h2><span class="tip">')
    assert 'aria-describedby="tip-archive"' in html
    assert render('{{ t.heading("Plain", level=3) }}') == (
        '<div class="uk-heading"><h3>Plain</h3></div>')
    aside = render('{{ t.heading("Runs", "r", aside=a) }}',
                   a=Markup('<a class="btn" href="/x">Open</a>'))
    assert '<span class="uk-heading-aside"><a class="btn"' in aside


def test_toggletip_is_a_disclosure_never_a_tooltip():
    html = render('{% call t.toggletip("x", "the x", title="T") %}'
                  'See <a href="/methods">Methods</a>{% endcall %}')
    b = first(html, "button", "uk-tt-btn")
    assert b["type"] == "button" and b["aria-expanded"] == "false"
    assert b["aria-controls"] == "tt-x" and b["aria-label"] == "More about the x"
    pop = first(html, "span", "uk-tt-pop")
    assert pop["id"] == "tt-x" and "role" not in pop    # holds a link
    assert '<a href="/methods">Methods</a>' in html
    assert '<strong class="uk-tt-title">T</strong>' in html
    rich = render('{% call t.heading("H", "h", rich=True) %}x{% endcall %}')
    assert 'class="uk-tt"' in rich and 'role="tooltip"' not in rich


def test_toggletip_script_opens_closes_and_returns_focus():
    kit = TIPS_JS.split("The UI kit's behavior", 1)[1]
    assert "setAttribute('aria-expanded', 'true')" in kit
    assert "setAttribute('aria-expanded', 'false')" in kit
    assert "e.key !== 'Escape'" in kit and "close(w, true)" in kit
    assert "'focusout'" in kit and "relatedTarget" in kit
    # without script the panel shows while focus is inside the toggletip
    assert "html:not(.uk-js) .uk-tt:focus-within > .uk-tt-pop" in KIT_CSS
    assert "root.classList.add('uk-js')" in kit


# ------------------------------------------------------ status components

@pytest.mark.parametrize("state", STATES)
def test_badge_says_its_state_in_a_word_and_an_icon(state):
    # the markup is the same for every state: the state as a class and a
    # data attribute, the word, and the state's icon (decorative). The
    # stylesheet decides which states show the icon (the next tests), so a
    # script that turns a quiet badge into a warning finds its icon there
    html = render('{{ t.badge(s, "the word") }}', s=state)
    a = first(html, "span", "uk-badge")
    assert f"uk-badge--{state}" in a["class"] and a["data-state"] == state
    assert '<span class="uk-badge-t">the word</span>' in html
    assert first(html, "svg")["aria-hidden"] == "true"
    assert f".uk-badge--{state}" in KIT_CSS


def test_a_quiet_state_is_the_word_alone_and_a_loud_one_keeps_its_icon():
    rules = _rules(KIT_CSS)
    hidden = {sel for sel, d in rules if d.get("display") == "none"}
    for s in QUIET:
        # ok, info and neutral ask nothing: no icon, the muted token (the
        # ink where the word is a stat's value), normal weight, free to wrap
        assert f".uk-badge--{s} > .uk-icon" in hidden, s
        d = _own(rules, f"uk-badge--{s}")
        assert d["--uk-c"] == ["var(--uk-quiet,var(--mut))"], s
        assert d["font-weight"] == ["500"] and d["white-space"] == ["normal"]
        # a word free to wrap is never clipped to its first line (the
        # word's ellipsis is for a loud mark, held on one line)
        assert _rule(rules, f".uk-badge--{s} > .uk-badge-t") == {
            "overflow": "visible"}, s
    for s in LOUD:
        # warn, error and pending keep icon and word, in the state's color
        # (no other rule in any sheet hides it: the next test)
        assert f".uk-badge--{s} > .uk-icon" not in hidden, s
    assert {s: _own(rules, f"uk-badge--{s}")["--uk-c"] for s in LOUD} == {
        "warn": ["var(--warn)"], "error": ["var(--bad)"],
        "pending": ["var(--accent-ink)"]}
    # the word takes the state's color, the icon follows it (currentColor)
    assert _own(rules, "uk-badge")["color"] == ["var(--uk-c)"]
    # a stat whose value is a status reads as a value: the ink, and the
    # value's own size and weight
    assert ("--uk-quiet", "var(--ink)") in [
        (k, v) for sel, d in rules if sel == ".uk-stat-v" for k, v in d.items()]
    in_stat = _rule(rules, ".uk-stat-v .uk-badge")
    assert in_stat["font-size"] == in_stat["font-weight"] == "inherit"
    # the word, not the icon, gives a badge its baseline: the badge centers
    # its icon, so without this a loud mark set on a baseline (a stat's
    # value) would sit above its neighbors and a quiet one would not
    assert _own(rules, "uk-badge")["align-items"] == ["center"]
    assert _rule(rules, ".uk-badge > .uk-badge-t") == {"align-self": "baseline"}


#: what may hide an icon or a drawing outside any mark, by sheet: the
#: Display menu switch's knob, and the Oracle pipeline's two drawings (one
#: shows at a time)
_ICON_HIDERS = {("nau.css", ".dm-sw-knob .uk-icon"),
                ("nau.css", ".figpipe > svg.pipe-v"),
                ("nau.css", ".figpipe:has(> svg.pipe-v) > svg.pipe-h")}
_HIDDEN = (("display", "none"), ("visibility", "hidden"), ("opacity", "0"))


def test_no_rule_in_any_sheet_hides_a_loud_state_s_icon():
    # a warning, a failure and work under way are an icon and a word. The
    # quiet states hide theirs by name; any other rule that hides an icon
    # where a badge may hold one (inside a badge, a pair, a row, a table)
    # would take a warning's icon with it
    quiet = re.compile(r"\.uk-badge--(?:ok|info|neutral)(?![\w-])")
    loud = re.compile(r"\.uk-badge--(?:warn|error|pending)(?![\w-])")
    seen = []
    for name, css in SHEETS.items():
        for sel, d in _rules(css):
            if not any(d.get(k, "").replace("!important", "").strip() == v
                       for k, v in _HIDDEN):
                continue
            if not re.search(r"\.uk-icon(?![\w-])|(?:^|[^\w-])svg(?![\w-])",
                             _split(sel, " >+~")[-1]):
                continue
            seen.append((name, sel))
            if (name, sel) in _ICON_HIDERS:
                continue
            named = re.sub(r":not\([^)]*\)", "", sel)
            assert quiet.search(named) and not loud.search(named), (name, sel)
    # the check sees the quiet states' own rules
    assert ("ui-kit.css", ".uk-badge--neutral > .uk-icon") in seen


def test_badge_icons_differ_by_state_and_a_tip_follows():
    drawn = {s: render('{{ t.badge(s, "w") }}', s=s).split("<svg", 1)[1]
             for s in STATES if s != "pending"}
    assert len(set(drawn.values())) == len(drawn)         # shape, not hue
    # the three states that show their icon: triangle, octagon, clock
    loud = {s: render('{{ t.badge(s, "w") }}', s=s).split("<svg", 1)[1]
            for s in LOUD}
    assert len(set(loud.values())) == 3
    html = render('{{ t.badge("warn", "not archived", "Why.", id="ln") }}')
    assert 'id="ln"' in html and 'aria-describedby="tip-ln"' in html
    assert 'aria-label="About not archived"' in html


def test_alert_roles_follow_its_kind():
    err = render('{{ t.alert("error", "Nothing was stored.", tiptext="3 '
                 'problems", id="a1") }}')
    a = first(err, "div", "uk-alert")
    assert a["role"] == "alert" and "uk-alert--error" in a["class"]
    assert 'aria-describedby="tip-a1"' in err
    assert 'aria-label="About nothing was stored"' in err
    warn = render('{{ t.alert("warn", "Reopen.", title="Update pulled.") }}')
    assert first(warn, "div", "uk-alert")["role"] == "status"
    assert "<strong>Update pulled.</strong> Reopen." in warn
    quiet = render('{{ t.alert("info", "x", live="") }}')
    assert "role" not in first(quiet, "div", "uk-alert")
    act = render('{{ t.alert("info", "x", action=a) }}',
                 a=Markup('<a href="/retro">Open</a>'))
    assert '<span class="uk-alert-action"><a href="/retro">Open</a>' in act
    # a title over a second line keeps its icon by the title, the action
    # centered on both lines
    two = render('{{ t.alert("ok", "x", title="Done", cls="uk-alert--two-line") }}')
    assert first(two, "div", "uk-alert")["class"] == "uk-alert uk-alert--ok uk-alert--two-line"
    assert ".uk-alert--two-line{align-items:flex-start}" in KIT_CSS
    assert ".uk-alert--two-line > .uk-alert-action{align-self:center}" in KIT_CSS


def test_empty_state_is_an_icon_a_title_and_one_action():
    html = render('{{ t.empty("No runs yet", "clock", action=a) }}',
                  a=Markup('<a class="btn gold" href="/forecast">Run</a>'))
    assert first(html, "svg")["aria-hidden"] == "true"
    assert '<p class="uk-empty-title">No runs yet</p>' in html
    assert '<div class="uk-empty-action"><a class="btn gold"' in html
    compact = render('{{ t.empty("Nothing here", compact=True) }}')
    assert "uk-empty--compact" in compact


def test_stats_are_a_definition_list_of_labelled_values():
    html = render('{% call t.stats("uk-stats--kv", label="Hub") %}'
                  '{{ t.stat("Vintages", 42, "weeks", "One per week.", id="nv") }}'
                  '{{ t.stat("relWIS", "0.666", state="ok") }}{% endcall %}')
    dl = first(html, "dl")
    assert dl["class"] == "uk-stats uk-stats--kv" and dl["aria-label"] == "Hub"
    assert html.count('<div class="uk-stat') == 2
    assert "<dt>Vintages<span class=\"tip\">" in html
    assert '<span class="uk-stat-v" id="nv">42</span> <span class="uk-stat-u">weeks</span>' in html
    assert 'class="uk-stat uk-stat--ok"' in html
    # dt/dd only inside the dl, each pair in its div
    names = [t for t, _ in tags(html)]
    assert names.count("dt") == names.count("dd") == 2


def test_reason_button_is_described_by_its_reason():
    off = render('{{ t.reason_button("Apply the Oracle step", "sb-oracle-why", '
                 '"edited", cls="gold") }}')
    # the order the sandbox's own test pins
    assert 'class="gold" disabled aria-describedby="tip-sb-oracle-why"' in off
    assert 'id="tip-sb-oracle-why">edited</span>' in off
    assert first(off, "span", "uk-reason-tip").get("hidden") is None
    on = render('{{ t.reason_button("Run", "rw", "engine missing", off=False, '
                'type="submit", data={"guard": "console-run"}) }}')
    b = first(on, "button")
    assert "disabled" not in b and "aria-describedby" not in b
    assert b["data-guard"] == "console-run" and b["type"] == "submit"
    assert b["data-uk-reason"] == "rw"
    assert "hidden" in first(on, "span", "uk-reason-tip")
    js = TIPS_JS.split("function setReason", 1)[1].split("\n  }\n", 1)[0]
    assert "btn.disabled = !!reason" in js and "wrap.hidden = !reason" in js


def test_stepper_speaks_each_state_and_marks_the_current_step():
    html = render('{{ t.stepper([{"label": "Data", "href": "/data", '
                  '"tip": "confirm"}, {"label": "Forecast"}, {"label": '
                  '"Output", "state": "error"}], current=2, id="s") }}')
    lis = [a for t, a in tags(html) if t == "li"]
    assert [a["class"] for a in lis] == ["uk-step uk-step--done",
                                         "uk-step uk-step--current",
                                         "uk-step uk-step--error"]
    assert lis[1]["aria-current"] == "step"
    assert "aria-current" not in lis[0]
    assert "(done)" in html and "(current step)" in html and "(problem)" in html
    assert first(html, "ol")["aria-label"] == "Steps"
    assert html.count('class="uk-step-mark" aria-hidden="true"') == 3
    assert 'aria-describedby="tip-s-1"' in html and '<a href="/data">' in html
    guide = render('{{ t.stepper([{"label": "a"}, {"label": "b"}]) }}')
    assert "aria-current" not in guide and "uk-step--todo" in guide


def test_progress_is_a_labelled_progressbar():
    html = render('{{ t.progress("Replay", 3, 10, "3 of 10 weeks", id="p") }}')
    bar = first(html, "div", "uk-progress-track")
    assert bar["role"] == "progressbar" and bar["aria-labelledby"] == "p-l"
    assert (bar["aria-valuemin"], bar["aria-valuemax"], bar["aria-valuenow"]
            ) == ("0", "10", "3")
    assert bar["aria-valuetext"] == "3 of 10 weeks"
    assert 'style="width:30.0%"' in html
    busy = render('{{ t.progress("Pulling", id="q") }}')
    assert "uk-progress--busy" in busy and "aria-valuenow" not in busy


def test_legend_chips_hide_their_swatches_and_name_the_list():
    html = render('{{ t.legend([("var(--gold)", "Oracle SIHRS", "line"), '
                  '{"color": "var(--mut)", "text": "baseline", "shape": '
                  '"dash", "tip": "t"}], id="lg") }}')
    assert first(html, "ul", "uk-legend")["aria-label"] == "Legend"
    sw = [a for t, a in tags(html) if "uk-sw" in (a.get("class") or "")]
    assert len(sw) == 2 and all(a["aria-hidden"] == "true" for a in sw)
    assert sw[0]["style"] == "--sw:var(--gold)" and "uk-sw--line" in sw[0]["class"]
    assert 'aria-describedby="tip-lg-2"' in html
    for shape in ("line", "dash", "dotted", "point", "ring", "band"):
        assert f".uk-sw--{shape}" in KIT_CSS


def test_fold_and_meta():
    fold = render('{% call t.fold("3 missing", id="f", open=True) %}'
                  '<ul><li>x</li></ul>{% endcall %}')
    assert fold.startswith('<details class="uk-fold" id="f" open><summary>')
    assert '<div class="uk-fold-body"><ul><li>x</li></ul></div>' in fold
    meta = render('{{ t.meta([("calendar", "2026-09-20", "As of"), '
                  '("folder", "5 MB"), "plain"]) }}')
    assert '<span class="uk-sr">As of: </span><span>2026-09-20</span>' in meta
    assert meta.count("<li>") == 3 and meta.count('aria-hidden="true"') == 2


def test_tag_and_name_chip():
    # a tag is a word with no state: no icon, no role
    tag = render('{{ t.tag("relWIS") }}')
    assert tag == '<span class="uk-tag">relWIS</span>'
    # a name chip holds its "?", named for the chip
    chip = render('{{ t.namechip("Seasonal forcing", "f", "The curve.") }}')
    assert chip.startswith('<span class="uk-name">Seasonal forcing<span class="tip">')
    assert 'aria-label="About seasonal forcing"' in chip
    assert 'id="tip-f">The curve.</span>' in chip
    assert ".uk-figline" in KIT_CSS
    # both are plain muted words in the line (no outline, no fill: the
    # stylesheet tests below), the chip's "?" as close as a badge's
    rules = _rules(KIT_CSS)
    assert _own(rules, "uk-tag")["color"] == ["var(--mut)"]
    assert _own(rules, "uk-name")["color"] == ["var(--mut)"]
    assert _rule(rules, ".uk-name > .tip") == {"margin-left": "0"}


def test_hidden_alert_and_empty_stay_hidden():
    a = render('{{ t.alert("warn", "x", id="a", hidden=True) }}')
    e = render('{{ t.empty("None", id="e", hidden=True) }}')
    assert ' hidden>' in a and ' hidden>' in e
    # their display rule would override [hidden]; the kit puts it back
    assert ".uk-alert[hidden]{display:none}" in KIT_CSS
    assert ".uk-empty[hidden]{display:none}" in KIT_CSS


def test_stat_tip_label_names_the_tip():
    s = render('{{ t.stat("relWIS", "0.9", tiptext="Below 1 beats it.", '
               'id="r", tip_label="relWIS") }}')
    assert 'aria-label="About relWIS"' in s


def test_the_script_builds_the_kit_markup_the_macros_write():
    # FluBNFUI.tip/alert/progress, so page scripts never copy the markup
    for name in ("function tip(", "function alert(", "function progress(",
                 "function setProgress(", "tip: tip, alert: alert",
                 "progress: progress, setProgress: setProgress"):
        assert name in TIPS_JS, name
    # the tab scripts that fill a box with kit pieces use them
    static = UI / "static"
    assert "ui.progress(text)" in (static / "dataset_upload.js").read_text()
    assert "FluBNFUI.alert(kind, text, title, tip, '')" in \
        (static / "sandbox.js").read_text()
    for p in (static / "dataset_upload.js", static / "sandbox.js",
              UI / "templates" / "data.html",
              UI / "templates" / "sandbox_views.html"):
        t = p.read_text()
        assert "'<div class=\"uk-alert" not in t, p.name
        assert 'class="tipbtn" aria-label="About \'' not in t, p.name


# ---------------------------------------------------------- the stylesheet

def _classes_in_macros() -> set:
    return set(re.findall(r"\buk-[a-z][\w-]*", TIPS_T)) - {"uk-js"}


def _split(text: str, seps: str) -> list:
    """`text` cut at each separator that is outside parentheses."""
    out, depth, cur = [], 0, ""
    for ch in text:
        depth += (ch == "(") - (ch == ")")
        if depth == 0 and ch in seps:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return [x.strip() for x in out + [cur] if x.strip()]


def _rules(css: str) -> list:
    """Every rule of a sheet as (selector, {property: value}), one entry
    per selector of a list, comments out; a rule inside an @media or
    @container block counts like any other."""
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", body):
        decls = {}
        for d in _split(m.group(2), ";"):
            k, _, v = d.partition(":")
            decls[k.strip()] = " ".join(v.split())
        for sel in _split(m.group(1), ","):
            out.append((" ".join(sel.split()), decls))
    return out


def _rule(rules: list, selector: str) -> dict:
    """The declarations of the first rule with that selector (a later one
    is a mode's override: forced colors, reduced motion)."""
    for sel, decls in rules:
        if sel == selector:
            return decls
    raise AssertionError(f"no rule {selector}")


def _own(rules: list, cls: str) -> dict:
    """What the sheet gives the class by its bare selector, as
    {property: [values]}."""
    out = {}
    for sel, decls in rules:
        if sel == "." + cls:
            for k, v in decls.items():
                out.setdefault(k, []).append(v)
    return out


def _styles(rules: list, cls: str) -> list:
    """(selector, declarations) of every rule that styles an element of
    the class itself, wherever it sits: the selector's last compound
    names the class (not a longer class that starts with its name)."""
    names = re.compile(r"\." + re.escape(cls) + r"(?![\w-])")
    return [(sel, d) for sel, d in rules
            if names.search(_split(sel, " >+~")[-1])]


#: what draws a box: an edge, a ground, a rounded corner, room inside
_BOX = re.compile(r"^(?:border|outline|background|box-shadow|padding)")
_NO_BOX = {"0", "none", "transparent"}


def _boxes(rules: list, cls: str) -> list:
    return [(sel, k, v) for sel, d in _styles(rules, cls)
            for k, v in d.items() if _BOX.match(k) and v not in _NO_BOX]


@pytest.mark.parametrize("cls", ["uk-badge", "uk-badge-t", "uk-tag",
                                 "uk-name"] + [
    f"uk-badge--{s}" for s in STATES])
def test_a_mark_has_no_outline_no_fill_and_no_pill(cls):
    # a badge (its word included), a tag and a name chip are set in the
    # line like text. Only something that can be pressed has an outline,
    # so no rule in any sheet (the kit's, nau.css's or a tab's; the
    # high-contrast and forced-colors blocks included) draws a box around
    # one
    rules = _rules(KIT_CSS)
    assert _styles(rules, cls), cls
    for name, css in SHEETS.items():
        assert _boxes(_rules(css), cls) == [], name
    assert "nau.css" in SHEETS and "tabs/storage.css" in SHEETS
    # and the helper sees a box where there is one
    assert _boxes(rules, "uk-alert") and _boxes(rules, "uk-seg")


def _at_blocks(css: str, prelude: str) -> str:
    """The bodies of every at-rule block that opens with `prelude`
    (comments out, braces matched), one after another."""
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, start = [], 0
    while (k := body.find(prelude + "{", start)) >= 0:
        i = k + len(prelude) + 1
        depth = 1
        for j in range(i, len(body)):
            depth += (body[j] == "{") - (body[j] == "}")
            if depth == 0:
                break
        assert depth == 0, f"{prelude} is not closed"
        out.append(body[i:j])
        start = j
    assert out, f"no {prelude} block"
    return "\n".join(out)


def test_marks_side_by_side_stand_apart_and_a_tag_holds_together():
    rules = _rules(KIT_CSS)
    # with no box to part them, a mark followed by another stands apart
    # from it
    assert _rule(rules, ":is(.uk-badge,.uk-badge-pair,.uk-tag)"
                        ":has(+ :is(.uk-badge,.uk-badge-pair,.uk-tag))") == {
        "margin-right": ".45rem"}
    # a tag moves to the next line whole, never split mid-phrase
    assert _own(rules, "uk-tag")["white-space"] == ["nowrap"]


def test_the_newest_week_s_dots_sit_midway_between_its_counts():
    # the newest week writes " · " between its count marks. The kit's room
    # after a mark followed by a mark would land before each dot (the
    # sibling rule skips the text between them), so nau.css takes it back
    # there. Each selector names an element, which outranks the kit's rule
    # (two classes) wherever the sheets load
    nau = _rules(NAU)
    assert _rule(nau, "p.newest-check > .uk-badge") == {"margin-right": "0"}
    assert _rule(nau, "dd.dt-newest-dd > .uk-badge") == {"margin-right": "0"}
    # and the counts are children of those two, with the dot between
    from types import SimpleNamespace
    r = SimpleNamespace(week="2098-10-11", complete=False, clean=False,
                        max_lag=2, details=lambda: ["Ohio: no row."],
                        short=lambda: "3 of 5 reported · 2 not reported"
                                      " · 1 reads 0")

    class Parents(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack, self.found = [], []

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if "uk-badge" in (a.get("class") or "").split():
                self.found.append(self.stack[-1])
            if tag not in ("path", "circle", "line", "rect", "polyline"):
                self.stack.append((tag, a.get("class") or ""))

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag("path", attrs)

        def handle_endtag(self, tag):
            if tag not in ("path", "circle", "line", "rect", "polyline"):
                self.stack.pop()

    for src, host in (
            ('{{ n.check(r, short=True) }}', ("p", "newest-check hint")),
            ('<dd class="dt-newest-dd">{{ n.row(r) }}</dd>',
             ("dd", "dt-newest-dd"))):
        html = templates.env.from_string(
            '{% import "_newest.html" as n %}' + src).render(r=r)
        assert html.count(' · <span class="uk-badge uk-badge--neutral"') == 2
        p = Parents()
        p.feed(html)
        assert p.found == [host, host], (src, p.found)
    data_t = (UI / "templates" / "data.html").read_text()
    assert '<dd class="dt-newest-dd">{{ newest.row(newest_report) }}</dd>' \
        in data_t


def test_the_modes_thicken_no_edge_on_a_mark():
    # with no border left on a mark, the high-contrast and forced-colors
    # blocks thicken and recolor only the edges that remain
    modes = KIT_CSS.split(
        "/* ---- 14. high contrast and forced colors ---- */", 1)[1]
    for cls in ("uk-badge", "uk-tag", "uk-name"):
        assert not re.search(r"\." + cls + r"(?![\w-])", modes), cls
    assert '[data-contrast="high"] .uk-seg{border-width:2px}' in modes
    assert (".uk-alert,.uk-tt-pop,.uk-step-mark,.uk-seg"
            "{border-color:CanvasText}") in modes


def test_a_status_inside_a_link_reads_as_a_link():
    # no pill marks it as pressable, so its word is underlined
    assert _rule(_rules(KIT_CSS), "a > .uk-badge > .uk-badge-t")[
        "text-decoration"] == "underline"
    # the Sandbox's last-run status is the one such link; its own rule no
    # longer rounds it or strips the underline
    sbr = _rules((TABS / "sandbox.css").read_text())
    sb = _rule(sbr, "a.sb-runlink")
    assert "border-radius" not in sb and "text-decoration" not in sb
    # with no pill its hit area would be its word; a ring centered on the
    # word keeps it 24px each way at least, and moves nothing
    assert sb["position"] == "relative"
    hit = _rule(sbr, "a.sb-runlink::before")
    assert hit["position"] == "absolute" and hit["content"] == '""'
    assert hit["width"] == hit["height"] == "max(100%,24px)"
    assert (hit["left"], hit["top"], hit["transform"]) == (
        "50%", "50%", "translate(-50%,-50%)")


#: the tabs' own counts and kinds that are not controls, by sheet: the same
#: look as a quiet mark (plain words with no box)
TAB_WORDS = {
    "forecast.css": (".ms-n", ".fc-ms-state",
                     ".ms-row.ms-changed > .lblrow > label::after"),
    "models.css": (".md-tag",),
    "home.css": (".hm-facts li",),
    "storage.css": (".st-fact", ".st-lcount"),
}


@pytest.mark.parametrize("sheet", sorted(TAB_WORDS))
def test_the_tabs_own_counts_and_kinds_draw_no_box(sheet):
    rules = _rules((TABS / sheet).read_text())
    for sel in TAB_WORDS[sheet]:
        mine = [d for s2, d in rules if s2 == sel]
        assert mine, sel
        for d in mine:
            drawn = {k: v for k, v in d.items()
                     if _BOX.match(k) and v not in _NO_BOX}
            assert drawn == {}, (sel, drawn)


def test_the_tabs_own_words_keep_their_other_signal():
    fc_css = (TABS / "forecast.css").read_text()
    fcr = _rules(fc_css)
    fc = dict(fcr)
    # a changed setting: the bar at its row's edge carries the warning
    # color, the words by its label say it (never color alone), in the ink
    # so they stand apart from the muted label; the group's count of
    # changed rows reads as they do
    assert _rule(fcr, ".ms-row.ms-changed")["box-shadow"] == (
        "inset 3px 0 0 var(--warn)")
    after = fc[".ms-row.ms-changed > .lblrow > label::after"]
    assert after["content"] == 'var(--ms-mark,"changed")'
    assert after["color"] == fc[".ms-n"]["color"] == "var(--ink)"
    # forced colors set a box-shadow to none, so there an edge in the
    # system's text color is the bar, the field kept where it stands
    forced = _rule(_rules(_at_blocks(fc_css, "@media (forced-colors:active)")),
                   ".ms-row.ms-changed")
    assert forced == {"border-left": "3px solid CanvasText",
                      "margin-left": "calc(-.5rem - 3px)"}
    assert _rule(fcr, ".ms-row.ms-changed")["margin-left"] == "-.5rem"
    # the pickers' live count ("12 of 53"), shared by the Forecast tab and
    # the Retrospective's Your data, so in nau.css: quiet words, no box
    count = [d for sel, d in _rules(NAU) if sel == ".fc-count"]
    assert count and all(d["color"] == "var(--mut)" for d in count)
    assert all(not {k for k in d if _BOX.match(k) and d[k] not in _NO_BOX}
               for d in count)
    # the Model settings summary's count of changed settings: quiet words
    # beside the fold's title, gone while every setting is at its default;
    # the summary is the kit fold's row, never a filled button
    assert fc[".fc-ms-state"]["color"] == "var(--mut)"
    assert fc[".fc-ms-state:empty"] == {"display": "none"}
    assert not [s for s, d in fcr if "ms-panel" in s
                and {"background", "background-color", "border"} & set(d)]
    # the location presets are one select: no chip rules are left
    assert not [s for s, _ in fcr if "fc-chip" in s]
    # Storage: the ledger's count beside its heading is quiet words, as
    # every count beside a heading is, and its facts take a quiet mark's
    # weight
    st = dict(_rules((TABS / "storage.css").read_text()))
    assert st[".st-lcount"] == {"color": "var(--mut)",
                                "font-size": "var(--fs-label)",
                                "font-weight": "500"}
    assert st[".st-fact"]["font-weight"] == "500"
    # Methods: the rules every run keeps are an ordinary bulleted list,
    # with no check drawn before each line
    mt = _rules((TABS / "methods.css").read_text())
    assert not [s for s, _ in mt if s.startswith(".mt-rules") and "::" in s]
    assert "list-style" not in _rule(mt, ".mt-rules")
    # the model switcher's "research": muted, and the ink of the choice on
    # the page being read (measured below)
    md = dict(_rules((TABS / "models.css").read_text()))
    assert md[".md-tag"]["color"] == "var(--mut)"
    assert md[".md-switch > [aria-current] > .md-tag"] == {"color": "inherit"}
    # the diagram's symbol key keeps its box (it is a key, not a status)
    assert "border" in md[".md-par"]


def test_the_ledger_s_run_name_wraps_in_its_column():
    # Storage's run ledger: a run's name (tips.runname) takes its own line,
    # so its start and the quiet facts after it (research, modified
    # settings) share the line under it. The name is long ("Data through
    # Nov 21 · forecasts for weeks ending Nov 28 to Dec 19"), so it wraps
    # inside its column and the summary column keeps its room, with no
    # sideways scroll; nothing holds it to one line
    css = (TABS / "storage.css").read_text()
    rules = _rules(css)
    led = _rule(rules, ".st-ledger")
    assert led["overflow-x"] == "auto"
    assert [d for s, d in rules if s == ".st-ledger td.st-run .uk-run > a"] \
        == [{"display": "block"}]
    assert [d for s, d in rules if s == ".st-ledger td.st-run .uk-run-sub"] \
        == [{"display": "inline", "margin-right": ".6rem"}]
    assert not [s for s, d in rules
                if "st-run" in s and d.get("white-space") == "nowrap"]
    # the phone's cards keep their own layout (rows as grids, no scroll);
    # the column headings go, a group's round heading stays
    phone = _rules(_at_blocks(css, "@media (max-width:40rem)"))
    assert (".st-ledger", {"overflow-x": "visible"}) in phone
    assert (".st-ledger thead", {"display": "none"}) in phone
    assert (".st-ledger tr.st-ghead", {"display": "block",
                                       "padding-left": ".1rem",
                                       "padding-right": ".1rem"}) in phone


def test_every_kit_class_has_a_rule():
    # the modifier classes built from an argument are listed by hand
    built = {f"uk-badge--{s}" for s in STATES} | {
        f"uk-alert--{k}" for k in ("error", "warn", "info", "ok")} | {
        f"uk-step--{s}" for s in ("done", "current", "todo", "error")} | {
        f"uk-stat--{s}" for s in ("ok", "warn", "error")} | {
        f"uk-c-{s}" for s in ("ok", "warn", "error", "info", "muted")}
    wanted = {c for c in _classes_in_macros() if not c.endswith("-")} | built
    for c in sorted(wanted):
        assert re.search(r"\." + re.escape(c) + r"(?![\w-])", KIT_CSS), c


def test_kit_colors_come_only_from_tokens():
    body = re.sub(r"/\*.*?\*/", "", KIT_CSS, flags=re.S)
    forced = body.split("@media (forced-colors:active)", 1)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", body)
    assert not re.search(r"\b(?:rgba?|hsla?)\(", body)
    assert not re.search(r":\s*(?:white|black)\b", body)
    # system colors appear only in the forced-colors block
    assert not re.search(r"\b(?:CanvasText|Highlight)\b", forced[0])
    for m in re.finditer(r"color-mix\(([^)]*)\)", body):
        assert "var(--" in m.group(1), m.group(0)


def test_kit_sizes_follow_the_text_size():
    body = re.sub(r"/\*.*?\*/", "", KIT_CSS, flags=re.S)
    assert not re.findall(r"font-size:\s*[\d.]+px", body)
    # widths and paddings in rem/em; px only for hairlines and radii, and
    # the one floor that must not shrink with the text: the 24px hit area
    # of the "?" and "i" buttons (max(1.6rem,24px))
    body = body.replace("max(1.6rem,24px)", "1.6rem")
    for m in re.finditer(r"([\d.]+)px", body):
        assert float(m.group(1)) <= 5, m.group(0)


def test_base_loads_the_kit_after_the_theme():
    nau = BASE_T.index('<link rel="stylesheet" href="/static/nau.css">')
    kit = BASE_T.index('<link rel="stylesheet" href="/static/ui-kit.css">')
    between = BASE_T[nau:kit]
    assert "<link" not in between.split(">", 1)[1] and kit > nau
    assert '<script src="/static/tips.js" defer></script>' in BASE_T


def test_the_restart_notice_is_a_kit_alert(monkeypatch):
    env = templates.env
    monkeypatch.setitem(env.globals, "restart_needed", lambda: True)
    monkeypatch.setitem(env.globals, "running_sha", lambda: "abc1234")
    html = env.from_string('{% extends "base.html" %}').render(active="Home")
    alert = html.split('<div class="uk-alert uk-alert--warn" id="restart"', 1)[1]
    assert alert.startswith(' role="alert">')
    assert "<strong>Update pulled.</strong> Quit the app fully and reopen." in alert
    tip = alert.split('id="tip-restart">', 1)[1]
    assert " ".join(tip.split()).startswith(
        "This window still runs build abc1234. Quit the app fully and "
        "reopen; a page reload refreshes the look, not the server logic.")


# ---------------------------------------------------- contrast, every mode

def _block(selector: str) -> dict:
    m = re.search(re.escape(selector) + r"\{([^}]*)\}", NAU)
    assert m, selector
    return dict(re.findall(r"--([\w-]+)\s*:\s*([^;]+);", m.group(1)))


def _grid():
    """(name, resolved tokens) for every theme block x contrast x vision,
    resolved as the cascade does (root, theme, contrast, vision)."""
    root = _block(":root")
    themes = {"light": {}}
    for t in re.findall(r'\[data-theme="([\w-]+)"\]\{', NAU):
        themes[t] = _block(f'[data-theme="{t}"]')
    hc, cvd = _block('[data-contrast="high"]'), _block('[data-vision="cvd"]')
    for th, over in themes.items():
        for c in (False, True):
            for v in (False, True):
                toks = dict(root)
                toks.update(over)
                if c:
                    toks.update(hc)
                if v:
                    toks.update(cvd)
                yield f"{th}{'+hc' if c else ''}{'+cvd' if v else ''}", c, \
                    {n: _deref(toks, n) for n in toks}


def _deref(toks: dict, name: str, depth: int = 0) -> str:
    """A token's literal, following var() chains."""
    assert depth < 10, f"var() cycle at --{name}"
    val = toks[name].strip()
    m = re.fullmatch(r"var\(--([\w-]+)\)", val)
    return _deref(toks, m.group(1), depth + 1) if m else val


def _rgb(v: str) -> tuple:
    v = v.strip()
    m = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", v)
    assert m, f"unparsed color {v!r}"
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(c) -> float:
    def lin(x):
        x /= 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])


def _ratio(a, b) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _mix(a, b, p: float) -> tuple:
    """color-mix(in srgb, a p, b)"""
    return tuple(p * x + (1 - p) * y for x, y in zip(a, b))


def _alert_tint() -> float:
    rule = KIT_CSS.split(".uk-alert{", 1)[1].split("}", 1)[0]
    m = re.search(r"background:color-mix\(in srgb,var\(--uk-c\) (\d+)%,"
                  r"var\(--card\)\)", rule)
    assert m, "the alert's tint moved"
    return int(m.group(1)) / 100


#: the color of every word the kit sets as a mark: the three loud states,
#: the quiet states and the tag (muted), and --ok, which a stat's value,
#: an icon tip and the .uk-c-ok word still wear
MARK_TOKENS = ("ok", "warn", "bad", "accent-ink", "mut")


def test_badge_words_and_alerts_hold_the_bars_in_every_theme_and_mode():
    # a mark brings no ground of its own (ui-kit.css: no border, no fill),
    # so its word is measured on both grounds a page has: the card, and
    # the page ground under a page title or a section outside a card
    badge = _own(_rules(KIT_CSS), "uk-badge")
    assert badge["border"] == ["0"] and badge["background"] == ["none"]
    assert badge["color"] == ["var(--uk-c)"]
    p = _alert_tint()
    seen = 0
    for name, hc, T in _grid():
        card, ground = _rgb(T["card"]), _rgb(T["bg"])
        for tok in MARK_TOKENS:
            for where, surface in (("card", card), ("page ground", ground)):
                assert _ratio(_rgb(T[tok]), surface) >= 4.5, (name, tok, where)
        for tok in ("ok", "warn", "bad", "accent-ink"):
            bg = card if hc else _mix(_rgb(T[tok]), card, p)
            assert _ratio(_rgb(T["ink"]), bg) >= 4.5, (name, "ink on", tok)
            assert _ratio(_rgb(T["mut"]), bg) >= 4.5, (name, "mut on", tok)
            assert _ratio(_rgb(T[tok]), bg) >= 3.0, (name, tok, "icon")
        # the current step's number: the card color on the accent
        assert _ratio(_rgb(T["card"]), _rgb(T["accent-ink"])) >= 4.5, name
        seen += 1
    assert seen >= 16                        # four themes (or more) x 2 x 2


def _token(value: str) -> str:
    m = re.fullmatch(r"var\(--([\w-]+)\)", value)
    assert m, value
    return m.group(1)


def test_a_mark_on_a_filled_surface_takes_that_surface_s_text_color():
    # the state colors and the muted token are measured on the card and on
    # the page ground only. Wherever a mark can sit on another fill, a
    # rule hands it that surface's own text color, and that pair holds
    # 4.5:1; its state then rests on its icon and its word
    kit, nau = _rules(KIT_CSS), _rules(NAU)
    for host in (".uk-alert", ".tipbox", '.uk-seg > [aria-pressed="true"]',
                 ".uk-seg > [aria-current]"):
        assert _rule(kit, host + " .uk-badge") == {"color": "inherit"}, host
        assert _rule(kit, host + " .uk-tag") == {"color": "inherit"}, host
    # a tab chosen in a switch is that switch's fill too
    for kind in (".uk-badge", ".uk-tag"):
        assert _rule(kit, '.uk-seg > [role="tab"][aria-selected="true"] '
                     + kind) == {"color": "inherit"}
    # the Model settings toggle is a fold's row with no fill (it was a
    # filled pill that wore a badge on its fill)
    assert not [s for s, _ in nau if "advbtn" in s]
    tip = _rule(nau, ".tipbox")
    seg = _rule(kit, '.uk-seg > button[aria-pressed="true"]')
    quiet = _rule(kit, '.uk-seg--quiet > button[aria-pressed="true"]')
    m = re.fullmatch(r"color-mix\(in srgb,var\(--([\w-]+)\) (\d+)%,"
                     r"var\(--card\)\)", quiet["background"])
    assert m, "the quiet switch's tint moved"
    tint_tok, tint_p = m.group(1), int(m.group(2)) / 100
    p = _alert_tint()
    seen = 0
    for name, hc, T in _grid():
        def c(value):
            return _rgb(T[_token(value)])
        card = _rgb(T["card"])
        pairs = {
            "a tooltip": (c(tip["color"]), c(tip["background"])),
            "a switch's chosen side": (c(seg["color"]), c(seg["background"])),
            "the quiet switch's current page": (
                c(quiet["color"]), _mix(_rgb(T[tint_tok]), card, tint_p)),
        }
        for tok in ("ok", "warn", "bad", "accent-ink"):
            pairs[f"an alert ({tok})"] = (
                _rgb(T["ink"]), card if hc else _mix(_rgb(T[tok]), card, p))
        for where, (fg, bg) in pairs.items():
            assert _ratio(fg, bg) >= 4.5, (name, where)
        seen += 1
    assert seen >= 16
    # why the rules are there: left in its own color, a mark would not
    # hold on these fills (measured when they were written: the muted word
    # on the old open Model settings button's accent fill fell under 3:1 in
    # some theme, and the dim theme's red on an alert's tint under 4.5:1). Not pinned: a
    # theme that improves those pairs must not fail this test


#: a segmented switch's segments as the pages write them (the kit's own
#: rules, then nau.css's before them, as base.html links them), each
#: with keyboard focus: (where, its chain from the root)
_SEG_FOCUS = {
    "a chosen button": ("div.uk-seg[role=group]",
                        'button[type=button][aria-pressed="true"]:focus-visible'),
    "a chosen tab": ("div.mviews.uk-seg[role=tablist]",
                     'button[type=button][role=tab][aria-selected="true"]'
                     ':focus-visible'),
    "a chosen link": ("span.uk-seg[role=group]",
                      'a[href][aria-current="true"]:focus-visible'),
    "a chosen button, quiet": ("nav.uk-seg.uk-seg--quiet",
                               'button[type=button][aria-pressed="true"]'
                               ':focus-visible'),
    "the current page, quiet": ("nav.uk-seg.uk-seg--quiet",
                                'a[href][aria-current="page"]:focus-visible'),
    "a choice not chosen": ("div.uk-seg[role=group]",
                            'button[type=button][aria-pressed="false"]'
                            ':focus-visible'),
}


def _seg_focus(on=()):
    """{where: (the ring's color, the segment's fill)} as the cascade
    gives them, the values as written (a token, a color-mix, a system
    color)."""
    cas = C.Cascade.page()
    out = {}
    for where, (seg, item) in _SEG_FOCUS.items():
        chain = C.path("html", "body", "main", "div.card", seg, item)
        ring = cas.winner(chain, ("outline", "outline-color"), on=on)
        fill = cas.winner(chain, ("background", "background-color"), on=on)
        assert ring is not None and fill is not None, where
        color = ring.value
        if ring.prop == "outline":
            # the shorthand's color: its one var() that is not the width
            color = [v for v in re.findall(r"var\(--[\w-]+\)", ring.value)
                     if "focus-w" not in v][-1]
        out[where] = (color.strip(), fill.value.strip())
    return out


def test_the_focus_ring_shows_on_every_segment_of_a_switch():
    """The kit draws a segment's focus as a ring inside it, in the gold
    the chosen segment is filled with: on the chosen one it could not be
    seen (1:1 on the dark themes). Each segment's ring holds 3:1 against
    the segment under it, in every theme, with and without high contrast
    and the color-vision palette; in forced colors the chosen one is the
    system's highlight and its ring the highlight's text."""
    got = _seg_focus()
    # the ring is inside the segment (the switch clips what is outside)
    cas = C.Cascade.page()
    off = cas.value(C.path("html", "body", "div.uk-seg",
                           'button[aria-pressed="true"]:focus-visible'),
                    "outline-offset")
    assert off == "-3px"
    seen = 0
    for name, _hc, T in _grid():
        card = _rgb(T["card"])

        def paint(value):
            if value == "transparent":
                return card
            m = re.fullmatch(r"color-mix\(in srgb,var\(--([\w-]+)\) "
                             r"(\d+)%,var\(--card\)\)", value)
            if m:
                return _mix(_rgb(T[m.group(1)]), card, int(m.group(2)) / 100)
            return _rgb(T[_token(value)])

        for where, (ring, fill) in got.items():
            r = _ratio(paint(ring), paint(fill))
            assert r >= 3.0, (name, where, ring, fill, round(r, 2))
        seen += 1
    assert seen >= 16
    # forced colors: the system's pair, which keeps its own contrast
    forced = _seg_focus(on={"forced-colors:active"})
    for where in ("a chosen button", "a chosen tab", "a chosen link",
                  "a chosen button, quiet", "the current page, quiet"):
        assert forced[where] == ("HighlightText", "Highlight"), where


def test_the_tabs_own_words_hold_the_bar_where_they_sit():
    # the model switcher sits on the page ground; its "research" word is
    # muted there (measured above) and takes the ink on the current page's
    # tint, where the muted token falls short in the dim theme
    quiet = _rule(_rules(KIT_CSS),
                  '.uk-seg--quiet > button[aria-pressed="true"]')
    m = re.fullmatch(r"color-mix\(in srgb,var\(--([\w-]+)\) (\d+)%,"
                     r"var\(--card\)\)", quiet["background"])
    assert m and quiet["color"] == "var(--ink)"
    # (measured when the rule was written: the muted token fell under
    # 4.5:1 on that tint in the dim theme; not pinned, so a theme that
    # improves it does not fail here)
    for name, _hc, T in _grid():
        tint = _mix(_rgb(T[m.group(1)]), _rgb(T["card"]), int(m.group(2)) / 100)
        assert _ratio(_rgb(T["ink"]), tint) >= 4.5, name
    # the Home hero's facts: white at 84% on the tile, and the bold word in
    # its own token, with no chip fill under them (the tile runs from
    # --navy to --navy-deep)
    home = dict(_rules((TABS / "home.css").read_text()))
    assert home[".hm-facts li"]["color"] == (
        "color-mix(in srgb,currentColor 84%,transparent)")
    assert home[".hm-facts b"]["color"] == "var(--hero-chip-ink)"
    white = (255, 255, 255)
    for name, _hc, T in _grid():
        for end in ("navy", "navy-deep"):
            tile = _rgb(T[end])
            assert _ratio(_mix(white, tile, .84), tile) >= 4.5, (name, end)
            assert _ratio(_rgb(T["hero-chip-ink"]), tile) >= 4.5, (name, end)


# ------------------------------------------- the docs and the house rules

def test_the_doc_covers_every_macro_and_is_indexed():
    for m in MACROS:
        assert f"tips.{m}(" in DOC, m
    for rule in ("MOVE", "REPLACE", "KEEP", "DELETE"):
        assert rule in DOC
    assert "static/tabs/" in DOC and "{% block head %}" in DOC
    assert "[UI-KIT.md](UI-KIT.md)" in DOCS_INDEX
    for m in re.findall(r"{% macro (\w+)\(", TIPS_T):
        assert m in MACROS, f"{m} is not in the test's list"


def test_the_doc_says_when_a_mark_earns_its_place():
    # beside "Before adding a control": the questions asked of every mark
    a = DOC.index("## Before adding a control")
    b = DOC.index("## Before adding a mark")
    c = DOC.index("## Components")
    assert a < b < c
    section = DOC[b:c]
    for rule in ("Never repeat the neighbor", "A normal state is said quietly",
                 "One mark per fact"):
        assert f"**{rule}.**" in section, rule
    for state in STATES:
        assert f"`{state}`" in section, state
    # and the page describes the look the sheet draws
    contract = DOC.split("## Accessibility contract", 1)[1].split("\n## ", 1)[0]
    assert "A mark has no outline" in contract
    assert "only what can be pressed has an outline" in contract
    assert "A key is not a mark and keeps its box" in contract
    assert "on the card and on the page ground" in contract
    for gone in ("outlined, muted pill", "a badge's word on the card,",
                 "becomes a named chip"):
        assert gone not in DOC, gone


def test_tab_stylesheets_use_tokens_only():
    for css in sorted((UI / "static" / "tabs").glob("*.css")):
        body = re.sub(r"/\*.*?\*/", "", css.read_text(), flags=re.S)
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", body), css.name
        assert not re.search(r"\b(?:rgba?|hsla?)\(", body), css.name


@pytest.mark.parametrize("text", [TIPS_T, KIT_CSS, TIPS_JS, DOC],
                         ids=["_tips.html", "ui-kit.css", "tips.js", "UI-KIT.md"])
def test_kit_files_keep_the_house_rules(text):
    assert "\u2013" not in text and "\u2014" not in text


def test_the_kit_script_is_es5():
    kit = TIPS_JS.split("The UI kit's behavior", 1)[1]
    code = re.sub(r"'[^'\n]*'", "''", re.sub(r"//[^\n]*", "", kit))
    assert "=>" not in code and "`" not in code
    assert not re.search(r"\b(?:let|const|class)\s", code)
