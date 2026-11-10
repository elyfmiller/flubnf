"""The Forecast form's first screen (UX review F38, F35 and F53, F54;
package P5).

  * the location filter and list sit in a fold ("Pick locations"),
    closed while the pick is one the chips already say (all 53, the 52
    without US, US only), open for any other pick, an unreadable state
    list and a dataset ("Pick groups"); a closed fold posts the same
    boxes, so /run gets the same form;
  * under Run models, one line says how long the run takes here: the
    models, the locations and the engine's cost model's span
    (app/core/estimates.py), by the same rule in routes/forecast.run_words
    (the page as first shown) and static/forecast_form.js (every change);
    the Groundhog alone says "about a minute";
  * on a dataset, one line says when the Groundhog has too little history
    for the week, while the donor window and Weeks to drop are at their
    defaults; Run models stays a plain button.

Run models' place in the window on first load (1280x900 and 390x844) and
the browser's FormData before and after were checked by hand in a scratch
console: no browser driver is installed here.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

import pytest

from app.core import data
from app.core import estimates as ES
from app.core import sandbox
from app.core.engines import pf
from app.ui import datasets_ui as DU
from app.ui import pipeline, templating
from app.ui import state as ui_state
from app.ui.routes import forecast as FC

import served_dom as SD                               # noqa: E402
from test_data_source import _hub                      # noqa: E402
from test_datasets_ui import (TEMPLATE, client,        # noqa: E402,F401
                              isolated, stored)

UI = Path(__file__).resolve().parents[1] / "ui"
FORM_JS = UI / "static" / "forecast_form.js"
EST_JS = UI / "static" / "estimate.js"
PAGE = (UI / "templates" / "forecast.html").read_text(encoding="utf-8")
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")
NODE = shutil.which("node")
needs_js = pytest.mark.skipif(
    not (JSC.is_file() or NODE),
    reason="no JavaScript engine (JavaScriptCore jsc or node)")
US = FC.US_CHOICE
#: past Saturdays: the default date is the newest, W3 (whatever today is)
W1, W2, W3 = "2025-10-04", "2025-10-11", "2025-10-18"


# ------------------------------------------------------------------ fixtures

@pytest.fixture
def today(monkeypatch):
    """The cost model's constants as reviewed (2026-11-09) and a width of
    8, so the pinned figures hold after a refit and on any computer (the
    default width too: a run is never priced above it,
    estimates.priced_width)."""
    monkeypatch.setattr(pf, "DEFAULT_SHARD_WIDTH", 8)
    monkeypatch.setattr(pf, "COST_INTERCEPT_S", 1.194)
    monkeypatch.setattr(pf, "COST_PER_WEEK_S", 0.6365)
    monkeypatch.setattr(pf, "COST_FORECAST_WEEKS", 4)
    monkeypatch.setattr(pf, "COST_REFERENCE_PARTICLES", 10_000)
    monkeypatch.setattr(pf, "PUBLIC_COST_RATIO", 2.4)
    monkeypatch.setattr(sandbox, "ETA_FIRST_SPAN", (1.0, 4.0))
    monkeypatch.setenv("FLUBNF_PF_WIDTH", "8")


@pytest.fixture
def hub(tmp_path, monkeypatch, today):
    """A hub archive of three weeks, the newest W3 (the default date)."""
    monkeypatch.setattr(ui_state, "data_mod", data)
    _hub(tmp_path / "hub", [W1, W2, W3], [W1, W2, W3], monkeypatch)
    ui_state._last_form.clear()


def _page(last=None, url="/forecast"):
    ui_state._last_form.clear()
    ui_state._last_form.update(last or {})
    r = client.get(url)
    assert r.status_code == 200, r.text[:500]
    return r


class _Form(HTMLParser):
    """The controls of form#fcform as the server renders them, each with
    whether it sits in the locations fold, and the fold's own state."""

    def __init__(self):
        super().__init__()
        self.inform = self.infold = False
        self.controls, self.fold, self.sel = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and a.get("id") == "fcform":
            self.inform = True
        if not self.inform:
            return
        if tag == "details" and a.get("id") == "fc-locpick":
            self.infold = True
            self.fold = {"open": "open" in a, "class": a.get("class")}
        if tag in ("input", "select", "textarea"):
            c = {"tag": tag, "name": a.get("name"), "id": a.get("id"),
                 "type": a.get("type"), "value": a.get("value"),
                 "checked": "checked" in a, "disabled": "disabled" in a,
                 "fold": self.infold}
            self.controls.append(c)
            if tag == "select":
                self.sel, c["value"] = c, None
        if tag == "option" and self.sel is not None:
            if self.sel["value"] is None or "selected" in a:
                if "selected" in a or self.sel.get("_first") is None:
                    self.sel["value"] = a.get("value")
                self.sel["_first"] = True

    def handle_endtag(self, tag):
        if tag == "select":
            self.sel = None
        if tag == "details" and self.infold:
            self.infold = False
        if tag == "form" and self.inform:
            self.inform = False


def _form(html):
    p = _Form()
    p.feed(html)
    for c in p.controls:
        c.pop("_first", None)
    return p


def _form_html(html):
    """form#fcform's markup, from its tag to its end."""
    start = html.index('id="fcform"')
    return html[start:html.index("</form>", start)]


def _posted(controls):
    """What the form posts with no script: named, enabled controls, a
    checkbox only when ticked."""
    out = []
    for c in controls:
        if not c["name"] or c["disabled"]:
            continue
        if c["type"] == "checkbox" and not c["checked"]:
            continue
        out.append((c["name"], c["value"]))
    return out


def _states():
    from flubnf.settings import load_locations
    t = load_locations()
    return list(t.location_name[(t.location.str.len() == 2)
                                & (t.abbreviation != "US")])


# ------------------------------------------------- the locations fold (F38)

PICKS = {
    # name: (remembered locations, posted locations, fold open)
    "all": (["all"], ["all", US], False),
    "states": ("STATES", "STATES", False),
    "us": ([US], [US], False),
    "custom": (["Texas", "Ohio", US], ["Ohio", "Texas", US], True),
    "custom_no_us": (["Ohio"], ["Ohio"], True),
    "nothing": ([], [], True),
}


@pytest.mark.parametrize("pick", list(PICKS))
def test_the_fold_holds_the_boxes_and_posts_the_same_pick(hub, pick):
    remembered, posted, open_ = PICKS[pick]
    states = _states()
    assert len(states) == 52
    if remembered == "STATES":
        remembered = posted = list(states)
    f = _form(_page({"locations": remembered}).text)
    assert f.fold == {"open": open_, "class": "uk-fold fc-locpick"}
    locs = [c for c in f.controls if c["name"] == "locations"]
    # every box (all, the 52, US) is in the fold, keeps its name, value and
    # id, and nothing else in the fold is named (the filter posts nothing)
    assert len(locs) == 54 and all(c["fold"] for c in locs)
    assert [c["value"] for c in locs] == ["all", *states, US]
    assert locs[0]["id"] == "ck-all" and locs[-1]["id"] == "ck-us"
    assert [c for c in f.controls if c["fold"] and c["name"] != "locations"] \
        == [{"tag": "input", "name": None, "id": "fc-locfilter",
             "type": "search", "value": None, "checked": False,
             "disabled": False, "fold": True}]
    sent = _posted(f.controls)
    assert [v for k, v in sent if k == "locations"] == posted
    # the rest of the form is the form without the fold: the same fields
    # in the same order whatever the pick
    names = [k for k, _v in sent if k != "locations"]
    assert names[:3] == ["mode", "forecast_date", "engine"]
    assert "weeks_to_nowcast" in names and "replicates" in names


def test_the_fold_is_the_same_form_for_every_pick(hub):
    def rest(last):
        f = _form(_page(last).text)
        return [c for c in f.controls if c["name"] != "locations"]
    base = rest({"locations": ["all"]})
    for pick in (["Ohio"], [US], []):
        assert rest({"locations": pick}) == base


def test_the_fold_says_what_it_holds_and_where(hub):
    html = _page().text
    form = _form_html(html)
    # between the presets and the model; the chips and the count outside
    i = form.index('id="fc-locpick"')
    assert form.index('class="fc-presets"') < i < form.index('id="model-pick"')
    assert form.index('id="lcount"') < i
    assert ('<summary><span class="uk-fold-sum">Pick locations</span>'
            '</summary>') in form
    # the list's own rows sit inside the fold (their words are UI-15's,
    # not this package's: G35 made the first one "all 53 locations")
    assert i < form.index('id="ck-all"') < form.index("</details>", i)
    # no "?" in the fold's summary
    summ = form[i:form.index("</summary>", i)]
    assert "uk-tip" not in summ


def test_an_unreadable_state_list_opens_the_fold(hub, monkeypatch):
    import flubnf.settings as S

    def boom():
        raise OSError("gone")
    monkeypatch.setattr(S, "load_locations", boom)
    f = _form(_page().text)
    assert f.fold["open"] is True


def test_last_pick_and_failed_last_run_open_the_fold():
    script = PAGE[PAGE.index("var FOLD = document.getElementById('fc-locpick');"):]
    assert "if (FOLD && (p === 'last' || p === 'failed')) FOLD.open = true;" \
        in script
    # a list measured while closed is measured again on opening
    assert "FOLD.addEventListener('toggle', paintFade);" in script


# ------------------------------------------- the Run row's time line (F35, F53)

@pytest.mark.parametrize("engine,lo,hi", [("public", 10, 40),
                                          ("private", 4, 17)])
def test_the_weekly_round_is_the_reviewers_figure(today, monkeypatch, engine,
                                                  lo, hi):
    """Both models, 53 locations, 3 Independent Runs, 10,000 particles at
    14 weeks observed: 159 fits at width 8, 10.1 min public and 4.2 min
    private (F35), shown as the span 1 to 4 times the model."""
    monkeypatch.setenv("FLUBNF_ENGINE", engine)
    w = FC.run_words("all", 53, 3, 10_000, "2026-10-31")
    assert w == ("Oracle SIHRS and Groundhog, 53 locations: "
                 f"about {lo} to {hi} min")
    sec = ES.run_seconds([14], 159, 10_000)
    assert w.endswith(ES.human(*ES.span(sec)))
    assert FC.run_words("pf", 53, 3, 10_000, "2026-10-31") == \
        f"Oracle SIHRS, 53 locations: about {lo} to {hi} min"


def test_the_line_by_its_rules(today, monkeypatch):
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    rw = FC.run_words
    # the Groundhog alone: no figure from the cost model
    assert rw("analogue", 53, 3, 10_000, "2026-10-31") == \
        "Groundhog, 53 locations: about a minute"
    assert rw("analogue", 1, None, None, "") == \
        "Groundhog, 1 location: about a minute"
    # without the engine Both runs the Groundhog alone; a broken install
    # fails Both and refuses the Oracle SIHRS alone: nothing to say
    assert rw("all", 53, 3, 10_000, "2026-10-31", pf_state="absent") == \
        "Groundhog, 53 locations: about a minute"
    assert rw("all", 53, 3, 10_000, "2026-10-31", pf_state="broken") == ""
    assert rw("pf", 53, 3, 10_000, "2026-10-31", pf_state="absent") == ""
    # nothing picked, no Independent Run, no usable date, a field missing,
    # an unknown model
    assert rw("all", 0, 3, 10_000, "2026-10-31") == ""
    assert rw("all", 53, 0, 10_000, "2026-10-31") == ""
    assert rw("all", 53, 3, 10_000, "") == ""
    assert rw("all", 53, None, 10_000, "2026-10-31") == ""
    assert rw("both", 53, 3, 10_000, "2026-10-31") == ""
    # this computer's recorded pace: at both ends, then "here"
    sec = ES.run_seconds([14], 159, 10_000)
    assert rw("all", 53, 3, 10_000, "2026-10-31", ratio=2.5) == (
        "Oracle SIHRS and Groundhog, 53 locations: "
        + ES.human(*ES.span(sec, 2.5)) + " here")
    # a smaller run and a typed season start
    sec = ES.run_seconds([ES.n_obs_for("2026-10-31", "2026-09-05")], 2,
                         2_000)
    assert rw("all", 1, 2, 2_000, "2026-10-31", "2026-09-05") == \
        "Oracle SIHRS and Groundhog, 1 location: " + ES.human(*ES.span(sec))
    # never the low end alone, and no dash anywhere
    assert re.fullmatch(r".*: about \d+ to \d+ min",
                        rw("all", 53, 3, 10_000, "2026-10-31"))
    for w in (rw("all", 53, 3, 10_000, "2026-10-31"),
              rw("analogue", 53, 3, 10_000, "")):
        assert "–" not in w and "—" not in w


def test_the_form_carries_the_estimate_and_the_line(hub, monkeypatch):
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "ready")
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    html = _page().text
    tag = re.search(r'<form method="post" action="/run" id="fcform"[^>]*>',
                    html).group(0)
    for k, v in ES.page_params(None).items():
        assert f'{k}="{v}"' in tag
    assert 'data-est-width="8"' in tag
    want = FC.run_words("all", 53, 3, 10_000, W3)
    assert want.startswith("Oracle SIHRS and Groundhog, 53 locations: about ")
    line = re.search(r'<div id="fc-est"[^>]*>.*?</div>', html).group(0)
    assert ('<div id="fc-est" class="fc-est" data-all="53" data-pf="ready" '
            'data-gh="about a minute">') in line
    assert ('<ul class="uk-meta" aria-label="Run time"><li>' in line
            and f'<span class="uk-sr">Run time: </span><span>{want}</span>'
            in line)
    # in the Run row, after Run models; no "?"
    row = html[html.index('<div class="fc-runrow">'):]
    row = row[:row.index('<div id="fc-est"')]
    assert '<button class="gold" data-guard="console-run">Run models</button>' \
        in row
    assert "uk-tip" not in line
    # the two scripts, each loaded once
    assert html.count('src="/static/estimate.js"') == 1
    assert html.count('src="/static/forecast_form.js"') == 1


def test_the_line_changes_with_the_model(hub, monkeypatch):
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "ready")

    def line(last):
        html = _page(last).text
        return re.search(r'<span class="uk-sr">Run time: </span><span>'
                         r'([^<]*)</span>', html).group(1)
    both = line({"engine": "all"})
    gh = line({"engine": "analogue"})
    assert both.startswith("Oracle SIHRS and Groundhog, 53 locations: about ")
    assert gh == "Groundhog, 53 locations: about a minute"
    assert line({"engine": "pf"}).startswith("Oracle SIHRS, 53 locations: ")
    # the remembered pick, Independent Runs and particles
    assert line({"locations": [US]}).startswith(
        "Oracle SIHRS and Groundhog, 1 location: ")
    small = line({"knobs": {"pf.particles": "2000"}, "replicates": 1})
    sec = ES.run_seconds([ES.n_obs_for(W3)], 53, 2_000)
    assert small == ("Oracle SIHRS and Groundhog, 53 locations: "
                     + ES.human(*ES.span(sec)))


def test_without_the_engine_both_reads_the_groundhog_alone(hub, monkeypatch):
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "absent")
    html = _page({"engine": "pf"}).text
    # the Oracle SIHRS alone is off: the select shows Both, run as the
    # Groundhog alone
    assert '<span>Groundhog, 53 locations: about a minute</span>' in html
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "broken")
    html = _page().text
    assert re.search(r'<div id="fc-est"[^>]* data-pf="broken"[^>]* hidden>',
                     html)


def test_a_fault_in_the_line_leaves_the_page(hub, monkeypatch):
    from app.ui import retro_seasons as RS

    def boom():
        raise RuntimeError("unreadable replay record")
    monkeypatch.setattr(RS, "_own_cost_ratio", boom)
    html = _page().text
    assert 'id="fc-est"' not in html and "data-est-" not in html
    assert '<button class="gold" data-guard="console-run">Run models</button>' \
        in html


def test_this_computers_pace_says_here(hub, monkeypatch):
    from app.ui import retro_seasons as RS
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "ready")
    monkeypatch.setattr(RS, "_own_cost_ratio", lambda: (2.07, 12))
    html = _page().text
    assert 'data-ratio="2.07"' in html
    want = FC.run_words("all", 53, 3, 10_000, W3, ratio=2.07)
    assert want.endswith(" here") and f"<span>{want}</span>" in html


# --------------------------------------- the page's script, by the same rules

def _js(tmp_path, body):
    files = [EST_JS, FORM_JS]
    drv = ("var E = FluBNFEstimate, F = FluBNFForecastForm;\n"
           "print(JSON.stringify((function(){ " + body + " })()));\n")
    if JSC.is_file():
        d = tmp_path / "driver.js"
        d.write_text(drv, encoding="utf-8")
        cmd = [str(JSC), *map(str, files), str(d)]
    else:
        both = tmp_path / "both.js"
        both.write_text("var print = function(s){ console.log(s); };\n"
                        + "\n".join(f.read_text(encoding="utf-8")
                                    for f in files) + "\n" + drv,
                        encoding="utf-8")
        cmd = [NODE, str(both)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, (out.stderr or out.stdout)
    return json.loads(out.stdout.strip().splitlines()[-1])


CASES = [
    {"engine": "all", "locations": 53, "replicates": 3, "particles": 10000,
     "anchor": "2026-10-31", "seasonStart": "", "ratio": None,
     "pf": "ready"},
    {"engine": "pf", "locations": 53, "replicates": 3, "particles": 10000,
     "anchor": "2026-10-31", "seasonStart": "2026-08-01", "ratio": None,
     "pf": "ready"},
    {"engine": "all", "locations": 1, "replicates": 1, "particles": 1000,
     "anchor": "2026-10-31", "seasonStart": "", "ratio": None,
     "pf": "ready"},
    {"engine": "all", "locations": 7, "replicates": 5, "particles": 40000,
     "anchor": "2027-03-27", "seasonStart": "2026-09-05", "ratio": None,
     "pf": "ready"},
    {"engine": "all", "locations": 53, "replicates": 10, "particles": 100000,
     "anchor": "2027-05-29", "seasonStart": "", "ratio": None,
     "pf": "ready"},
    {"engine": "all", "locations": 53, "replicates": 3, "particles": 10000,
     "anchor": "2026-10-31", "seasonStart": "", "ratio": 2.07,
     "pf": "ready"},
    {"engine": "analogue", "locations": 53, "replicates": 3,
     "particles": 10000, "anchor": "2026-10-31", "seasonStart": "",
     "ratio": None, "pf": "ready"},
    {"engine": "all", "locations": 53, "replicates": 3, "particles": 10000,
     "anchor": "2026-10-31", "seasonStart": "", "ratio": None,
     "pf": "absent"},
    {"engine": "all", "locations": 53, "replicates": 3, "particles": 10000,
     "anchor": "2026-10-31", "seasonStart": "", "ratio": None,
     "pf": "broken"},
    {"engine": "pf", "locations": 53, "replicates": 3, "particles": 10000,
     "anchor": "2026-10-31", "seasonStart": "", "ratio": None,
     "pf": "absent"},
    {"engine": "all", "locations": 0, "replicates": 3, "particles": 10000,
     "anchor": "2026-10-31", "seasonStart": "", "ratio": None,
     "pf": "ready"},
    {"engine": "all", "locations": 53, "replicates": 0, "particles": 10000,
     "anchor": "2026-10-31", "seasonStart": "", "ratio": None,
     "pf": "ready"},
    {"engine": "all", "locations": 53, "replicates": 3, "particles": 10000,
     "anchor": "", "seasonStart": "", "ratio": None, "pf": "ready"},
    {"engine": "all", "locations": 53, "replicates": None,
     "particles": 10000, "anchor": "2026-10-31", "seasonStart": "",
     "ratio": None, "pf": "ready"},
    {"engine": "all", "locations": 53, "replicates": 3, "particles": 10000,
     "anchor": "2026-10-31", "seasonStart": "2027-01-02", "ratio": None,
     "pf": "ready"},
]


@needs_js
@pytest.mark.parametrize("engine", ["public", "private"])
def test_the_script_says_what_the_server_says(tmp_path, monkeypatch, today,
                                              engine):
    monkeypatch.setenv("FLUBNF_ENGINE", engine)
    attrs = ES.page_params(None)
    got = _js(tmp_path, "var a = " + json.dumps(attrs) + ";"
              " var el = {getAttribute: function (n) {"
              " return a.hasOwnProperty(n) ? a[n] : null; }};"
              " var p = E.params(el), cs = " + json.dumps(CASES)
              + ", out = []; for (var i = 0; i < cs.length; i++) {"
              " var o = cs[i]; o.p = p; o.gh = "
              + json.dumps(FC.GROUNDHOG_RUN_WORDS)
              + "; out.push(F.runWords(E, o)); } return out;")
    want = [FC.run_words(c["engine"], c["locations"], c["replicates"],
                         c["particles"], c["anchor"], c["seasonStart"],
                         c["ratio"], c["pf"]) for c in CASES]
    assert got == want
    assert want[0].startswith("Oracle SIHRS and Groundhog, 53 locations: ")
    assert want[5].endswith(" here")
    assert want[6] == want[7] == "Groundhog, 53 locations: about a minute"
    assert want[8:14] == [""] * 6
    # the line changes between Both and the Groundhog alone
    assert want[0] != want[6]


# The script on the page as served (review 3 of #93, finding 13): it finds
# its form, fields and lines in the markup the server rendered, by its own
# selectors (served_dom), and must then write what the server writes. A
# renamed id, class or field name in either the template or the script
# leaves a line blank or stale, and fails here. The page's inline script
# (forecast.html paint()) puts the anchor week on the date field before
# forecast_form.js reads it: PAINT does that, and nothing else, first.

PAINT = ("var box = document.querySelector('input[name=forecast_date]');"
         " box.setAttribute('data-anchor', ANCHOR);")

#: the time line's text as shown ("" while hidden), and a field's change
#: as the browser sends it (the event bubbles to the form; the script
#: waits a tick)
SAID = """
var fm = document.getElementById("fcform");
function said(id, sel) {
  var el = document.getElementById(id);
  return el.hidden ? "" : el.querySelector(sel).textContent;
}
function time() { return said("fc-est", ".uk-meta li > span:last-child"); }
function donors() { return said("fc-ds-donors", ".uk-alert-text"); }
function set(sel, v, ev) {
  var el = fm.querySelector(sel);
  if (typeof v === "boolean") el.checked = v; else el.value = v;
  el.fire(ev || "change");
  flush();
}
function anchor(a) {
  fm.querySelector("input[name=forecast_date]").setAttribute("data-anchor", a);
  fm.querySelector("input[name=forecast_date]").fire("change");
  flush();
}
"""


def _served(tmp_path, html, anchor, body):
    return SD.run(tmp_path, html, [EST_JS, FORM_JS], SAID + body,
                  prelude="var ANCHOR = " + json.dumps(anchor) + "; " + PAINT)


@needs_js
def test_the_served_form_drives_the_time_line(tmp_path, hub, monkeypatch):
    """readRun on the page as served: the model, "all" as the line's
    count, else the ticked states and US, Independent Runs and particles
    (blank or unreadable: their default), Season start and the anchor
    week; the line shown is the server's at first and after each change,
    and hides with nothing to say."""
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "ready")
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    html = _page().text
    served = re.search(r'<span class="uk-sr">Run time: </span><span>'
                       r'([^<]*)</span>', html).group(1)
    got = _served(tmp_path, html, W3, """
      var out = [time()];
      set("#ck-all", false); out.push(time());        // US stays ticked
      var ones = fm.querySelectorAll("input.ck-one");
      for (var i = 0; i < 4; i++) ones[i].checked = true;
      set("#ck-us", false); out.push(time());
      set("#ck-us", true); out.push(time());
      set('[data-knob="pf.particles"]', "40000", "input"); out.push(time());
      set('[data-knob="pf.replicates"]', "", "input"); out.push(time());
      set('[data-knob="pf.replicates"]', "x", "input"); out.push(time());
      set('[data-knob="pf.replicates"]', "1", "input"); out.push(time());
      set('[data-knob="run.season_start"]', "2025-09-06"); out.push(time());
      set("#model-pick", "analogue"); out.push(time());
      set("#model-pick", "pf"); out.push(time());
      set("#model-pick", "all"); anchor(""); out.push(time());
      anchor(%s); set("#ck-all", true); out.push(time());
      return out;""" % json.dumps(W3))
    rw = FC.run_words
    want = [rw("all", 53, 3, 10_000, W3), rw("all", 1, 3, 10_000, W3),
            rw("all", 4, 3, 10_000, W3), rw("all", 5, 3, 10_000, W3),
            rw("all", 5, 3, 40_000, W3), rw("all", 5, 3, 40_000, W3),
            rw("all", 5, 3, 40_000, W3), rw("all", 5, 1, 40_000, W3),
            rw("all", 5, 1, 40_000, W3, "2025-09-06"),
            "Groundhog, 5 locations: about a minute",
            rw("pf", 5, 1, 40_000, W3, "2025-09-06"), "",
            rw("all", 53, 1, 40_000, W3, "2025-09-06")]
    assert got == want
    assert got[0] == served and served.startswith(
        "Oracle SIHRS and Groundhog, 53 locations: about ")
    # each change is seen (blank and unreadable Independent Runs are
    # the default's 3)
    assert len(set(got)) == len(want) - 2


@needs_js
def test_the_served_dataset_form_drives_the_donor_line(tmp_path):
    """readDonor on a dataset's page as served: the anchor week's count,
    the Groundhog, the donor window and Weeks to drop at their defaults;
    one group's donor weeks are plain weeks."""
    ds = stored(one_series_bytes(), "Flu")
    dates = ds.forecast_dates()
    counts = DU.donor_weeks(ds)
    html = _page(url=f"/forecast?source={ds.id}").text
    shown, served = _alert(html)
    assert shown is True
    assert '<option value="pf"' in _form_html(html)
    got = _served(tmp_path, html, dates[-1], """
      var out = [donors()];
      set('[data-knob="groundhog.bandwidth"]', "6", "input"); out.push(donors());
      set('[data-knob="groundhog.bandwidth"]', "2", "input"); out.push(donors());
      set('[data-knob="groundhog.bandwidth"]', "", "input"); out.push(donors());
      set('[data-knob="run.weeks_to_drop"]', "1", "input"); out.push(donors());
      set('[data-knob="run.weeks_to_drop"]', "0", "input"); out.push(donors());
      set("#model-pick", "pf"); out.push(donors());
      set("#model-pick", "analogue"); out.push(donors());
      anchor(%s); out.push(donors());
      anchor("1999-01-02"); out.push(donors());
      return out;""" % json.dumps(dates[2]))

    def thin(n):
        return ("The Groundhog has too little history for this week "
                f"({n} of 30 donor weeks).")
    assert got == [thin(counts[dates[-1]]), "", thin(counts[dates[-1]]),
                   thin(counts[dates[-1]]), "", thin(counts[dates[-1]]),
                   "", thin(counts[dates[-1]]), thin(counts[dates[2]]), ""]
    assert got[0] == served


@needs_js
def test_several_groups_count_group_weeks(tmp_path):
    """Two groups: a week counts once in each, so the line says
    group-weeks, on the page as served and from its script (review 3,
    finding 14); the counts are the engine's own, unchanged."""
    from test_dataset_engines import grouped_bytes
    ds = stored(grouped_bytes(groups=("North", "South"),
                              start=date(2023, 8, 5), end=date(2025, 11, 15),
                              pop=False), "Two")
    newest = ds.forecast_dates()[-1]
    n = DU.donor_weeks(ds)[newest]
    assert n < 30 and DU.donor_unit(len(ds.groups)) == "group-weeks"
    html = _page(url=f"/forecast?source={ds.id}").text
    text = ("The Groundhog has too little history for this week "
            f"({n} of 30 donor group-weeks).")
    assert _alert(html) == (True, text)
    data = re.search(r'<script type="application/json" id="fc-donor-data">'
                     r'(.*?)</script>', html).group(1)
    assert json.loads(data) == {"need": 30, "weeks": DU.donor_weeks(ds),
                                "unit": "group-weeks"}
    got = _served(tmp_path, html, newest, """
      var out = [donors()];
      set('[data-knob="groundhog.bandwidth"]', "6", "input"); out.push(donors());
      set('[data-knob="groundhog.bandwidth"]', "", "input"); out.push(donors());
      return out;""")
    assert got == [text, "", text]


@needs_js
def test_the_script_reads_fields_as_the_server_does(tmp_path):
    cases = ["", " 3 ", "3", "03", "2.5", "x", "-1", None]
    got = _js(tmp_path, "var cs = " + json.dumps(cases) + ", out = [];"
              " for (var i = 0; i < cs.length; i++)"
              " out.push(F.whole(cs[i], 'd')); return out;")
    assert got == [FC._whole_field(c, "d") for c in cases]


# ------------------------------------------- a dataset's donor line (F54)

def one_series_bytes() -> bytes:
    """One series, four seasons, no population: the Groundhog finds 15 to
    17 donor weeks at every week of its newest season (P4's fixture)."""
    d0, lines = date(2021, 8, 7), ["week_ending,cases"]
    for i in range(203):
        d = d0 + timedelta(days=7 * i)
        lines.append(f"{d.isoformat()},{20 + (i * 13) % 90}")
    return ("\n".join(lines) + "\n").encode()


def _alert(html):
    m = re.search(r'<div class="uk-alert uk-alert--warn" id="fc-ds-donors"'
                  r' role="status"( hidden)?>.*?<span class="uk-alert-text">'
                  r'([^<]*)</span></div>', html, re.S)
    return m and (not m.group(1), m.group(2))


def test_a_thin_week_says_the_groundhog_has_too_little_history():
    ds = stored(one_series_bytes(), "Flu")
    newest = ds.forecast_dates()[-1]
    n, need = DU.donor_weeks(ds)[newest], DU.donor_need()
    assert n < need == 30
    html = _page(url=f"/forecast?source={ds.id}").text
    assert _alert(html) == (True, "The Groundhog has too little history "
                                  f"for this week ({n} of 30 donor weeks).")
    # what the page's script reads: every forecast week's count
    data = re.search(r'<script type="application/json" id="fc-donor-data">'
                     r'(.*?)</script>', html).group(1)
    assert json.loads(data) == {"need": 30, "weeks": DU.donor_weeks(ds),
                                "unit": "weeks"}
    # informs only: Run models is the plain button, no reason button, and
    # the line has no "?"
    form = _form_html(html)
    assert '<button class="gold" data-guard="console-run">Run models</button>' \
        in form
    assert "uk-reason" not in form and "reason_button" not in form
    alert = form[form.index('id="fc-ds-donors"'):]
    assert "uk-tip" not in alert[:alert.index("</div>")]
    # the dataset form: the fold open, named for groups; no time line
    f = _form(html)
    assert f.fold["open"] is True
    assert '<span class="uk-fold-sum">Pick groups</span>' in html
    assert 'id="fc-est"' not in html and "data-est-" not in form


def test_the_line_hides_where_the_count_does_not_hold():
    ds = stored(one_series_bytes(), "Flu")
    url = f"/forecast?source={ds.id}"
    base = {"forecast_date": ds.forecast_dates()[-1], "locations": ["all"],
            "engine": "analogue", "weeks_to_drop": 0, "replicates": 3,
            "season_start": "", "flusurv": False}

    def shown(**over):
        DU._LAST[ds.id] = {**base, **over}
        return _alert(_page(url=url).text)[0]
    assert shown() is True
    # a wider donor window or a dropped week finds other donors
    assert shown(knobs={"groundhog.bandwidth": "6"}) is False
    assert shown(knobs={"groundhog.bandwidth": "2"}) is True
    assert shown(weeks_to_drop=1) is False
    # the Groundhog does not run
    assert shown(engine="pf") is False
    # a week with enough donors (none this early: the first weeks have
    # none at all, so the line shows)
    assert shown(forecast_date=ds.forecast_dates()[2]) is True


def test_a_rich_dataset_says_nothing():
    ds = stored(TEMPLATE.read_bytes(), "Kids")
    newest = ds.forecast_dates()[-1]
    assert DU.donor_weeks(ds)[newest] >= DU.donor_need()
    html = _page(url=f"/forecast?source={ds.id}").text
    shown, text = _alert(html)
    assert shown is False and text == ""


def test_no_counts_no_line(monkeypatch):
    """A dataset page whose context lacks donor_weeks shows no line and
    no counts."""
    real = templating.templates.TemplateResponse

    def without(request, name, ctx, *a, **kw):
        if ctx.get("dataset"):
            ctx = {**ctx, "dataset": {k: v for k, v in ctx["dataset"].items()
                                      if k != "donor_weeks"}}
        return real(request, name, ctx, *a, **kw)
    monkeypatch.setattr(templating.templates, "TemplateResponse", without)
    ds = stored(one_series_bytes(), "Flu")
    html = _page(url=f"/forecast?source={ds.id}").text
    assert 'id="fc-ds-donors"' not in html
    assert 'id="fc-donor-data"' not in html


@needs_js
def test_the_script_words_the_line_as_the_page_does(tmp_path):
    ds = stored(one_series_bytes(), "Flu")
    newest = ds.forecast_dates()[-1]
    n = DU.donor_weeks(ds)[newest]
    html = _page(url=f"/forecast?source={ds.id}").text
    base = {"count": n, "need": 30, "groundhog": True,
            "windowDefault": True, "dropDefault": True}
    cases = [base, {**base, "count": 30}, {**base, "count": None},
             {**base, "groundhog": False}, {**base, "windowDefault": False},
             {**base, "dropDefault": False}, {**base, "count": 0},
             {**base, "unit": "group-weeks"}, {**base, "unit": "weeks"}]
    got = _js(tmp_path, "var cs = " + json.dumps(cases) + ", out = [];"
              " for (var i = 0; i < cs.length; i++)"
              " out.push(F.donorText(cs[i])); return out;")
    assert got[0] == _alert(html)[1] == got[8]
    assert got[1:6] == [""] * 5
    assert got[6] == ("The Groundhog has too little history for this week "
                      "(0 of 30 donor weeks).")
    assert got[7] == ("The Groundhog has too little history for this week "
                      f"({n} of 30 donor group-weeks).")


def test_the_new_words_keep_the_house_rules():
    js = FORM_JS.read_text(encoding="utf-8")
    for text in (js, PAGE):
        assert "–" not in text and "—" not in text
        assert "posterior" not in text.lower()
    # ES5 only in the static script
    assert "=>" not in js and "`" not in js
    assert not re.search(r"\b(let|const)\s", js)

