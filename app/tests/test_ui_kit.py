"""The UI kit: the components that replace loose explanatory text
(templates/_tips.html macros, static/ui-kit.css, the FluBNFUI block of
static/tips.js; docs/UI-KIT.md).

Each macro is rendered through the console's own Jinja env and its
accessibility contract pinned: names, roles, the links between a control
and its explainer, state spoken as well as drawn. The stylesheet is held to
tokens only, and its measured pairs (a badge's word, an alert's text and
icon, the current step's number) to the contrast bars in every theme and
mode that nau.css defines.
"""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from markupsafe import Markup                        # noqa: E402

from app.ui.templating import templates             # noqa: E402

REPO = Path(__file__).resolve().parents[2]
UI = REPO / "app" / "ui"
TIPS_T = (UI / "templates" / "_tips.html").read_text()
BASE_T = (UI / "templates" / "base.html").read_text()
KIT_CSS = (UI / "static" / "ui-kit.css").read_text()
TIPS_JS = (UI / "static" / "tips.js").read_text()
NAU = (UI / "static" / "nau.css").read_text()
DOC = (REPO / "docs" / "UI-KIT.md").read_text()
DOCS_INDEX = (REPO / "docs" / "README.md").read_text()

MACROS = ("tip", "label", "icon", "icon_tip", "toggletip", "heading",
          "badge", "alert", "empty", "stats", "stat", "reason_button",
          "stepper", "progress", "legend", "fold", "meta")
ICON_NAMES = ("info", "warning", "error", "check", "clock", "download",
              "folder", "external", "lock", "calendar", "refresh", "dot",
              "close")
STATES = ("ok", "warn", "error", "info", "neutral", "pending")


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
    html = render('{{ t.badge(s, "the word") }}', s=state)
    a = first(html, "span", "uk-badge")
    assert f"uk-badge--{state}" in a["class"] and a["data-state"] == state
    assert '<span class="uk-badge-t">the word</span>' in html
    assert first(html, "svg")["aria-hidden"] == "true"
    assert f".uk-badge--{state}" in KIT_CSS


def test_badge_icons_differ_by_state_and_a_tip_follows():
    drawn = {s: render('{{ t.badge(s, "w") }}', s=s).split("<svg", 1)[1]
             for s in STATES if s != "pending"}
    assert len(set(drawn.values())) == len(drawn)         # shape, not hue
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


# ---------------------------------------------------------- the stylesheet

def _classes_in_macros() -> set:
    return set(re.findall(r"\buk-[a-z][\w-]*", TIPS_T)) - {"uk-js"}


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
    # widths and paddings in rem/em; px only for hairlines and radii
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


def test_badge_words_and_alerts_hold_the_bars_in_every_theme_and_mode():
    # the badge sits on the card (ui-kit.css), outlined in its state color
    assert "background:var(--card);color:var(--uk-c)" in KIT_CSS
    p = _alert_tint()
    seen = 0
    for name, hc, T in _grid():
        card = _rgb(T["card"])
        for tok in ("ok", "warn", "bad", "accent-ink", "mut"):
            assert _ratio(_rgb(T[tok]), card) >= 4.5, (name, tok)
        for tok in ("ok", "warn", "bad", "accent-ink"):
            bg = card if hc else _mix(_rgb(T[tok]), card, p)
            assert _ratio(_rgb(T["ink"]), bg) >= 4.5, (name, "ink on", tok)
            assert _ratio(_rgb(T["mut"]), bg) >= 4.5, (name, "mut on", tok)
            assert _ratio(_rgb(T[tok]), bg) >= 3.0, (name, tok, "icon")
        # the current step's number: the card color on the accent
        assert _ratio(_rgb(T["card"]), _rgb(T["accent-ink"])) >= 4.5, name
        seen += 1
    assert seen >= 16                        # four themes (or more) x 2 x 2


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


def test_tab_stylesheets_use_tokens_only():
    for css in sorted((UI / "static" / "tabs").glob("*.css")):
        body = re.sub(r"/\*.*?\*/", "", css.read_text(), flags=re.S)
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", body), css.name
        assert not re.search(r"\b(?:rgba?|hsla?)\(", body), css.name


@pytest.mark.parametrize("text", [TIPS_T, KIT_CSS, TIPS_JS, DOC],
                         ids=["_tips.html", "ui-kit.css", "tips.js", "UI-KIT.md"])
def test_kit_files_keep_the_house_rules(text):
    assert "\u2013" not in text and "\u2014" not in text
    low = text.lower()
    for word in ("claude", "anthropic", "microhub"):
        assert word not in low


def test_the_kit_script_is_es5():
    kit = TIPS_JS.split("The UI kit's behavior", 1)[1]
    code = re.sub(r"'[^'\n]*'", "''", re.sub(r"//[^\n]*", "", kit))
    assert "=>" not in code and "`" not in code
    assert not re.search(r"\b(?:let|const|class)\s", code)
