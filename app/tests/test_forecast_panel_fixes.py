"""The Forecast tab's settings panel and Data issues box (bug hunt
2026-10-25, G26).

  * A run-wide setting that counts a state's newest week as unreported
    ("Newest weeks reading 0" or "Collapsed newest week") leaves that
    state only "Both from" and "Leave out": the box hides the rest while
    it is on, a run refuses them in words, and the run records what was
    applied (the rule, or the state's set-aside), never a choice the rule
    overrode.
  * A Data issues select is never narrower than its words.
  * A model-settings refusal is said once, under the panel, in plain
    words; Reset to defaults hides it.
  * A cleared date asks for one; the archived-week picker follows the
    date, so the same week can be picked again.
"""
from pathlib import Path

from app.core import reported
from app.ui import forms
from app.ui import state as ui_state
from test_data_issues import _capture_run, _isolated, _post, client  # noqa: F401
from test_newest_reported import WEEKS, _hub

UI = Path(__file__).resolve().parents[1] / "ui"


def _text(name: str) -> str:
    return (UI / name).read_text(encoding="utf-8")


# ------------------------------------- FC-13: the run-wide rule and the box

def test_a_run_wide_rule_leaves_a_covered_state_both_from_and_leave_out(
        tmp_path, monkeypatch):
    # Ohio reads 0 after 40s; Utah collapses to 5 after 40s
    _hub(tmp_path / "hub", monkeypatch, newest={"Ohio": "0", "Utah": "5"})
    rep = reported.check()
    rules = {r["name"]: r["rules"] for r in reported.box_rows(rep)}
    # a zero after 40 is also a week under a fifth of 40: either setting
    assert rules == {"Ohio": ["data.trailing_zero", "data.partial_week"],
                     "Utah": ["data.partial_week"]}
    page = client.get("/forecast").text
    assert ('data-rules="data.trailing_zero data.partial_week"' in page
            and 'data-rules="data.partial_week"' in page)
    started = _capture_run(monkeypatch)
    on = {"knob.data.trailing_zero": "missing"}
    # a choice the rule overrides is refused in words
    ui_state._status.pop("flash", None)
    _post({**on, "gap.39": "level", "gap.49": "keep"})
    assert started == []
    assert ui_state._status["flash"] == (
        "Not run: Data issues for Ohio: Level does not apply while Newest "
        f"weeks reading 0 is set to counted as unreported; choose Both from "
        f"{WEEKS[-2][5:]} or Leave out.")
    # Utah is not covered by this setting: its Keep stands
    _post({**on, "gap.39": "set_aside", "gap.49": "keep"})
    states = started[-1].extra["data_choices"]["states"]
    assert {l: (s["choice"], s["recommended"], s["followed"])
            for l, s in states.items()} == {
        "Ohio": ("set_aside", "set_aside", True),
        "Utah": ("keep", "set_aside", False)}
    # no answer (the box disabled): the rule covers the state, unrecorded
    _post(on)
    assert "Ohio" not in started[-1].extra["data_choices"]["states"]
    # without the setting every choice is offered, as before
    _post({"gap.39": "level", "gap.49": "keep"})
    assert started[-1].extra["data_choices"]["states"]["Ohio"]["choice"] \
        == "level"


def test_the_box_follows_the_setting_in_the_page():
    box = _text("templates/_data_issues.html")
    assert ("o.hidden = o.disabled = on && o.value !== 'set_aside' && "
            "o.value !== 'omit';") in box
    assert "document.addEventListener('DOMContentLoaded', follow);" in box
    assert "form.addEventListener('ms-reset', follow);" in box
    assert "return o.value === v && !o.disabled;" in box
    js = _text("static/model_settings.js")
    assert ("box.dispatchEvent(new CustomEvent('ms-reset', {bubbles: true}));"
            in js)


# ------------------------------------------ FC-18: the select's own words

def test_a_data_issues_select_is_never_narrower_than_its_words():
    css = _text("static/tabs/forecast.css")
    rule = css.split(".fc-di .di-state select{", 1)[1].split("}", 1)[0]
    assert "min-width:min-content" in rule


# ---------------------------- FC-21, FC-22: one refusal, plain, and reset

def test_a_model_settings_refusal_is_said_once_in_plain_words(
        tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch)
    started = _capture_run(monkeypatch)
    for field, typed, said in (
            ("knob.pf.jitter", "abc", "Kernel jitter: 'abc' is not a number."),
            ("knob.pf.prior.Reff", "2.5, 0.6",
             ("Prior range for Reff: 2.5, 0.6 is not a range: the low end "
              "must be 0 or more and below the high end.")),
            ("replicates", "0", "Replicates: 0 is outside 1 to 10.")):
        ui_state._status.pop("flash", None)
        r = _post({field: typed, "engine": "all"})
        assert r.status_code == 303 and started == []
        assert not ui_state._status.get("flash")     # no second notice
        page = client.get("/forecast").text
        why = page.split('id="ms-refused">')[1].split("</div>")[0]
        assert said.replace("'", "&#39;") in why
    assert forms._refusal_words(
        "pf.prior.r: prior_ranges: r__FREE [0.0, 40.0] is not a valid "
        "loguniform_var range") == ("Prior range for r: 0, 40 is not a "
                                    "range: the low end must be above 0 and "
                                    "below the high end.")
    assert forms._refusal_words("pf.particles: '1e4' is not a valid int") \
        == "Particles: '1e4' is not a whole number."


def test_reset_to_defaults_hides_the_refusal():
    js = _text("static/model_settings.js")
    reset = js.split("reset.addEventListener('click'", 1)[1].split(
        "// open or closed as the user left it", 1)[0]
    assert "var said = box.querySelector('.fc-ms-refused');" in reset
    assert "if (said) said.hidden = true;" in reset


# --------------------------------- FC-23, FC-25: the date and the picker

def test_a_cleared_date_asks_for_one_and_the_picker_follows_the_date():
    page = _text("templates/forecast.html")
    assert "if (!day) return 'Pick a date.';" in page
    assert ("if (pick) pick.value = VS.indexOf(box.value) >= 0 ? box.value "
            ": '';") in page


# ------------------------------ FC-21: the lead, the pages without the panel

def test_the_refusal_leads_with_not_run_and_a_model_page_keeps_one_line(
        tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch)
    started = _capture_run(monkeypatch)
    ui_state._status.pop("flash", None)
    _post({"replicates": "0", "engine": "all"})
    assert started == [] and not ui_state._status.get("flash")
    why = client.get("/forecast").text.split('id="ms-refused">')[1].split(
        "</div>", 1)[0]
    assert "<strong>Not run.</strong> Replicates: 0 is outside 1 to 10." in why
    assert forms._knob_panel("retro", {})["refused_lead"] == "Not started."
    # a form on a page without the panel (a model page's) keeps the line
    ui_state._status["running"] = None
    client.post("/run", data={"forecast_date": WEEKS[-1], "locations": ["Ohio"],
                              "replicates": "0", "engine": "all"},
                headers={"referer": "http://testserver/model/pf"},
                follow_redirects=False)
    assert ui_state._status["flash"] == "Not run: Replicates: 0 is outside 1 to 10."
    # a refusal before the first run: the page still renders (its defaults
    # under the remembered reason)
    ui_state._last_form.clear()
    ui_state._last_form["ms_refused"] = "pf.replicates: 0 is outside 1 to 10"
    assert client.get("/forecast").status_code == 200
