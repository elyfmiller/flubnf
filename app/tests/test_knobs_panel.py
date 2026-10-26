"""The Model settings panel (templates/_model_settings.html, Stage 3 of
app/core/knobs.py) on the Forecast and Retrospective forms.

Rendered from the registry: every knob a scope can carry has a labelled
input and its one-line help (no "?" per field: one "i" for the panel,
linking every setting on Methods), each group a fold that opens on a
changed row; the older field names are kept; the rendered form posted
untouched runs the shipped spec; a refused submission keeps what was
typed and opens the panel once, saying why; changed values alone never
open it; a run keeps on the form what it could not use; the override and
its reason are offered on the Forecast form and never outlive their run.
"""
import json
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import knobs as K                              # noqa: E402
from app.ui import server as srv                             # noqa: E402
from app.ui import pipeline as ui_pipeline                   # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons         # noqa: E402
from app.ui import forms as ui_forms                         # noqa: E402
from app.ui import shared as ui_shared                       # noqa: E402
from app.ui import state as ui_state                         # noqa: E402

client = TestClient(srv.app)
FD = "2098-01-04"


@pytest.fixture(autouse=True)
def _isolated():
    status_before, form_before = dict(ui_state._status), dict(ui_state._last_form)
    yield
    ui_state._status.clear(); ui_state._status.update(status_before)
    ui_state._last_form.clear(); ui_state._last_form.update(form_before)
    ui_shared._invalidate_scans()


class _Form(HTMLParser):
    """Controls inside one element id: name/value pairs a browser would
    post, plus every control's id, and the label for= targets."""

    def __init__(self, root_id):
        super().__init__()
        self.root_id, self.depth = root_id, 0
        self.root_tag = None
        self.fields, self.ids, self.label_for = [], [], set()
        self._select = None
        self._opts = []
        self.disabled = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id") == self.root_id and not self.depth:
            self.depth, self.root_tag = 1, tag
            return
        if not self.depth:
            return
        if tag == self.root_tag:
            self.depth += 1
        if tag == "label" and a.get("for"):
            self.label_for.add(a["for"])
        if tag == "input" and a.get("name"):
            self.ids.append(a.get("id"))
            if "disabled" in a:
                self.disabled.add(a["name"])
                return
            if a.get("type") == "checkbox":
                if "checked" in a:
                    self.fields.append((a["name"], a.get("value", "on")))
            else:
                self.fields.append((a["name"], a.get("value", "")))
        if tag == "select" and a.get("name"):
            self.ids.append(a.get("id"))
            self._select, self._opts = a, []
        if tag == "option" and self._select is not None:
            self._opts.append((a.get("value", ""), "selected" in a))

    def handle_endtag(self, tag):
        if self.depth and tag == self.root_tag:
            self.depth -= 1
        if tag == "select" and self._select is not None:
            sel = [v for v, s in self._opts if s] or [self._opts[0][0]]
            self.fields.append((self._select["name"], sel[0]))
            self._select = None


def _panel_form(html, root="model-settings"):
    f = _Form(root)
    f.feed(html)
    return f


def _panel_html(html, root="model-settings"):
    """The panel's markup alone (from its <details> to its end)."""
    start = html.index(f'id="{root}"')
    return html[start:html.index("</details>\n<script", start)]


def test_forecast_panel_renders_every_forecast_knob_with_its_help():
    ui_state._last_form.clear()                   # the page a fresh app shows
    html = client.get("/forecast").text
    assert 'id="model-settings"' in html and 'id="ms-badge"' in html
    f = _panel_form(html)
    names = {n for n, _ in f.fields} | f.disabled
    for k in K.REGISTRY:
        if k.key in K.DECISION_KEYS:
            continue        # asked on the form itself (the Data issues box)
        name = K.FIELD_OF.get(k.key, "knob." + k.key)
        assert name in names, k.key
        # its one-line help under the field, as the field's description,
        # never behind a "?" of its own
        rid = "ks-" + k.key.replace(".", "-")
        assert f'<p class="ms-hint" id="{rid}-hint">{escape(k.help)}' in html, k.key
        assert f'aria-describedby="{rid}-hint"' in html, k.key
        assert f'tip-{rid}-tip' not in html, k.key
        # the row keeps its label wrapper, which carries the changed mark
        assert (f'<div class="lblrow"><label for="{rid}">{escape(k.label)}'
                '</label></div>') in html, k.key
    # one explainer for the whole panel: the head's "i", beside Reset,
    # which links the Methods tab's table of every setting
    panel = _panel_html(html)
    assert panel.count('class="tipbtn"') == 0
    assert panel.count('class="uk-tt-btn"') == 1
    assert 'aria-controls="tt-ms-about"' in panel
    assert '<a href="/methods#settings">Every setting on Methods</a>' in panel
    # each group a fold, closed while nothing in it is changed, its fields
    # a fieldset named by the fold's title
    for gid, title, _cost in K.PANEL_GROUPS:
        assert (f'<details class="uk-fold ms-group" data-affects="'
                in panel), gid
        assert f'<span class="uk-fold-sum" id="ms-{gid}-t">{escape(title)}</span>' in panel, gid
        assert f'<fieldset class="ms-fields" aria-labelledby="ms-{gid}-t">' in panel, gid
    assert '" id="ms-fit" open>' not in panel
    # the script keeps each group's count live
    js = (Path(__file__).resolve().parents[1] / "ui" / "static"
          / "model_settings.js").read_text()
    assert "g.querySelectorAll('.ms-row.ms-changed:not([hidden])')" in js
    assert "c.textContent = n + ' changed';" in js
    # a changed row's mark names the default
    assert "--ms-mark:'changed · default 10,000'" in panel
    # raw choice values read as words
    assert '<option value="season_total_early">expected total (early season)</option>' in panel
    assert '<option value="rand" selected>random draws (default)</option>' in panel
    assert '<option value="lh">Latin hypercube</option>' in panel
    # the older field names are the knobs' own on this form
    for old in ("season_start", "weeks_to_drop", "replicates", "particles",
                "drop_same_day"):
        assert old in names
    # coming-later knobs are shown, disabled, and never posted
    assert {"knob." + k for k in K.LATER} == f.disabled
    # ... in one fold that counts them, each named by its group
    assert f">{len(K.LATER)} coming later<" in html
    fold = html.split('id="ms-later-fold"')[1].split("</details>")[0]
    assert fold.count('class="ms-row ms-later"') == len(K.LATER)
    # the override and its reason (a placeholder says what to type), and
    # the reset control
    assert 'name="submit_modified"' in html and 'name="modified_reason"' in html
    assert 'placeholder="Why export under the hub names?"' in html
    assert 'id="ms-reset"' in html and "Reset to defaults" in html
    assert "/static/model_settings.js" in html
    # the fixed list; each fixed value's reason as text under it
    assert "Fixed by the model definition" in html
    for key in ("horizons", "quantile_levels", "epiweek_53", "gamma"):
        assert f"<dt>{key}</dt>" in html
    for lk in K.LOCKED:
        assert f'<span class="fc-lk-why">{escape(lk.why)}</span>' in panel


def test_no_auxiliary_bank_turns_the_donor_weights_off():
    """FC-11 (2026-10-25): with the auxiliary bank at none the run is the
    bare, pooled analogue, yet the panel showed the own-state weight and
    the kernel at their shipped values and the Run row then read "Differs".
    The three donor-weight rows are off (posted never, skipped by the Run
    row's comparison) while the bank is none, and back on with it."""
    js = (Path(__file__).resolve().parents[1] / "ui" / "static"
          / "model_settings.js").read_text()
    assert ("var BARE = ['groundhog.aux_weight', 'groundhog.own_share', "
            "'groundhog.kernel_sd'];") in js
    assert "var off = !!aux && aux.value === 'none';" in js
    assert "if (BARE.indexOf(el.dataset.knob) >= 0) el.disabled = off;" in js
    assert "if (aux) aux.addEventListener('change', bare);" in js
    assert "bare(); syncSeason(); filter(); update();" in js
    # Reset puts the bank back first, so the weights reset with the rest
    assert "if (aux) { aux.value = aux.dataset.default || ''; bare(); }" in js
    # the Run row skips an off field, and the panel counts none as changed
    tpl = (Path(__file__).resolve().parents[1] / "ui" / "templates"
           / "forecast.html").read_text()
    assert "if (el.disabled || el.closest('[hidden]') || !(k in LAST.knobs)) return;" in tpl
    assert "if (el.disabled) return false;" in js
    # and an off row looks it, as a coming-later one does
    css = (Path(__file__).resolve().parents[1] / "ui" / "static"
           / "nau.css").read_text()
    assert ".ms-later,.ms-row:has(> [data-knob]:disabled){opacity:.62}" in css


def test_every_panel_input_has_an_associated_label():
    for page in ("/forecast", "/retro"):
        f = _panel_form(client.get(page).text)
        ids = [i for i in f.ids if i]
        assert ids and len(ids) == len(f.ids), page
        missing = [i for i in ids if i not in f.label_for]
        assert missing == [], (page, missing)


def test_retro_panel_leaves_out_what_a_replay_cannot_carry():
    html = client.get("/retro").text
    f = _panel_form(html)
    names = {n for n, _ in f.fields} | f.disabled
    assert "weeks_to_drop" not in names
    assert "knob.output.floor_lam" not in names
    assert {"particles", "replicates", "knob.oracle.w"} <= names
    assert 'name="submit_modified"' not in html          # nothing is exported
    assert 'value="10000"' in html


def test_posting_the_rendered_form_untouched_runs_the_shipped_spec(
        tmp_path, monkeypatch):
    import app.core.data as data
    monkeypatch.setattr(ui_state, "data_mod", data)
    monkeypatch.setattr(data, "vintage_path", lambda d: tmp_path)
    monkeypatch.setattr(data, "vintages", lambda: [FD])
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    started = []
    monkeypatch.setattr(ui_pipeline, "_run_all", lambda s: started.append(s))
    ui_state._last_form.clear()                   # the page a fresh app shows
    f = _panel_form(client.get("/forecast").text, root="fcform")
    posted = [(n, v) for n, v in f.fields if n not in ("forecast_date",
                                                     "locations")]
    body = {}
    for n, v in posted + [("forecast_date", FD), ("locations", "Ohio")]:
        body.setdefault(n, v)
    ui_state._status["running"] = None
    client.post("/run", data=body, follow_redirects=False)
    ui_state._status["running"] = None
    client.post("/run", data={"forecast_date": FD, "locations": "Ohio"},
                follow_redirects=False)
    assert len(started) == 2, ui_state._status.get("flash")
    assert "knobs" not in started[0].extra
    assert started[0].to_json() == started[1].to_json()


def test_a_refused_submission_keeps_the_typed_values_and_reads_modified(
        tmp_path, monkeypatch):
    import app.core.data as data
    monkeypatch.setattr(ui_state, "data_mod", data)
    monkeypatch.setattr(data, "vintage_path", lambda d: tmp_path)
    monkeypatch.setattr(ui_pipeline, "_run_all", lambda s: None)
    ui_state._status["running"] = None
    client.post("/run", data={"forecast_date": FD, "locations": "Ohio",
                              "knob.oracle.w": "0.25", "replicates": "4",
                              "submit_modified": "1"},      # no reason
                follow_redirects=False)
    assert "needs a reason" in ui_state._status.get("flash", "")
    html = client.get("/forecast").text
    f = _panel_form(html)
    got = dict(f.fields)
    assert got["knob.oracle.w"] == "0.25" and got["replicates"] == "4"
    assert got.get("submit_modified") == "1"
    # the refusal opens the panel (over a close the user stored before
    # it), says why under its head, and shows the reason field to fill;
    # the badge says the files would take the hub names
    assert '<details class="adv" open data-refused id="model-settings"' in html
    assert 'id="ms-badge"' in html and ">modified · hub names</span>" in html
    panel = _panel_html(html)
    assert ('id="ms-refused"><svg' in panel
            and "Exporting under the hub names needs a reason;" in panel)
    assert 'id="ms-override" hidden' not in html
    assert 'id="ms-why" hidden' not in html
    # the groups holding the typed values open on them, counted; the rest
    # of an open group's rows fold under them
    assert 'id="ms-step" open>' in panel and 'id="ms-fit" open>' in panel
    assert '<span class="ms-n">1 changed</span>' in panel
    assert 'id="ms-data">' in panel                    # nothing changed there
    fit = panel.split('id="ms-fit" open>')[1].split("</fieldset>")[0]
    assert fit.index('id="ks-pf-replicates"') < fit.index('id="ms-fit-more"')
    assert fit.index('id="ms-fit-more"') < fit.index('id="ks-pf-particles"')
    # ... on that page only: the next visit shows the panel closed, as
    # the user leaves it, the typed values kept
    html = client.get("/forecast").text
    assert '<details class="adv" id="model-settings"' in html
    assert 'id="ms-refused"' not in html
    assert dict(_panel_form(html).fields)["knob.oracle.w"] == "0.25"


def test_the_shipped_page_reads_shipped():
    ui_state._last_form.clear()
    html = client.get("/forecast").text
    assert ">default</span>" in html
    assert 'id="ms-override" hidden' in html


def test_panel_data_is_the_registry():
    p = K.panel("forecast")
    keys = [r["key"] for g in p["groups"] for r in g["rows"]]
    assert sorted(keys) == sorted(set(K.BY_KEY) - K.DECISION_KEYS)
    assert not p["modified"]
    rp = K.panel("retro")
    assert not {r["key"] for g in rp["groups"] for r in g["rows"]} \
        & K.NOT_IN_RETRO
    assert K.panel("forecast", {"oracle.w": "0.25"})["modified"]
    # a coming-later knob never reads modified, whatever was posted
    assert not K.panel("forecast", {"oracle.count_floor": "5"})["modified"]
    assert ui_forms._knobs.FORM_PREFIX == K.FORM_PREFIX
    json.dumps(p)                                       # template-safe


def test_the_panel_never_opens_by_itself():
    """The owner's report: the panel opened by itself while a forecast
    ran, and on every visit after a run with modified settings, pushing
    the forecasts out of sight. The browser posts the Season start the
    script filled in (August 1 of the forecast's season); that value is
    the default, so the page reads "default". Changed settings read
    "modified" in the summary's badge and leave the panel closed, during
    a run and after it."""
    ui_state._last_form.clear()
    ui_state._last_form.update({
        "forecast_date": FD, "locations": ["Ohio"], "engine": "all",
        "weeks_to_drop": 0, "replicates": 3, "members": 2,
        "season_start": "2097-08-01", "particles": 10000,
        "drop_same_day": 0, "knobs": {}, "submit_modified": False,
        "modified_reason": "", "ms_refused": False})
    ui_state._status.update({"running": "all:x", "run_label": "x",
                             "workroot": None, "expected_total": None})
    html = client.get("/forecast").text
    assert '<details class="adv" id="model-settings"' in html
    assert ">default</span>" in html
    # the filled value is not kept as a typed one: the script refills it
    assert dict(_panel_form(html).fields).get("season_start", "") == ""
    # a run with a real change still renders closed; its badge says so,
    # and how the files will be named (the override starts unticked)
    ui_state._last_form["knobs"] = {"oracle.w": "0.25"}
    html = client.get("/forecast").text
    assert '<details class="adv" id="model-settings"' in html
    assert ">modified · non-hub names</span>" in html
    # a season start of the user's own is kept, and reads modified
    ui_state._last_form.update({"knobs": {}, "season_start": "2097-09-15"})
    html = client.get("/forecast").text
    assert dict(_panel_form(html).fields)["season_start"] == "2097-09-15"
    assert ">modified · non-hub names</span>" in html
    assert '<details class="adv" id="model-settings"' in html
    # idle again: changed settings still leave it closed, badged
    # "modified"; so do the defaults
    ui_state._status.update({"running": None})
    try:
        ui_state._last_form["knobs"] = {"oracle.w": "0.25"}
        html = client.get("/forecast").text
        assert '<details class="adv" id="model-settings"' in html
        assert ">modified · non-hub names</span>" in html
        ui_state._last_form.update({"knobs": {}, "season_start": "2097-08-01"})
        html = client.get("/forecast").text
        assert '<details class="adv" id="model-settings"' in html
    finally:
        ui_state._last_form.clear()
    # only a refusal opens it
    assert ui_forms._knob_panel("forecast", {"knobs": {"oracle.w": "0.25"}})[
        "open"] is False
    assert ui_forms._knob_panel("forecast", {"ms_refused": True})["open"] is True


def test_season_auto_is_august_first_of_each_days_season():
    assert ui_forms._season_auto("2098-01-04") == {"2097-08-01"}
    assert ui_forms._season_auto("2097-09-06", "2097-07-26", "", None) == {
        "2097-08-01", "2096-08-01"}


def test_the_panel_remembers_only_the_users_own_toggle():
    ui = Path(__file__).resolve().parents[1] / "ui"
    js = (ui / "static" / "model_settings.js").read_text()
    # a click on the summary is stored for the session and restored, open
    # or closed (a close wins over everything but the page after a
    # refusal); no page render or run state opens it
    assert "sessionStorage.setItem(memo" in js
    assert "sum.addEventListener('click'" in js
    assert "if (left === '1') box.open = true;" in js
    assert ("else if (left === '0' && !box.hasAttribute('data-refused')) "
            "box.open = false;") in js
    # a run forgets the choice, so the page after it (and its reload when
    # the run ends) never reopens the panel
    assert "form.addEventListener('submit'" in js
    assert "sessionStorage.removeItem(memo)" in js
    tpl = (ui / "templates" / "_model_settings.html").read_text()
    assert "{% if kp.open %} open data-refused{% endif %}" in tpl
    assert "kp.modified %} open" not in tpl


def test_the_open_panel_stays_in_the_settings_column():
    """The owner's report: the open panel spread across the page and
    pushed the forecasts about 2,000 px down. It now stays in the side
    column, as the Retrospective's does, with the Run row held at the
    window's foot while it is open."""
    ui = Path(__file__).resolve().parents[1] / "ui"
    js = (ui / "static" / "model_settings.js").read_text()
    css = (ui / "static" / "tabs" / "forecast.css").read_text()
    assert "fc-col-wide" not in js and "fc-col-wide" not in css
    assert "grid-column:1 / -1" not in css
    assert "#model-settings[open] ~ .fc-runrow{position:sticky;bottom:0" in css
    # a changed field keeps its place: the bar sits in the group's padding
    assert ".ms-row.ms-changed{box-shadow:inset 3px 0 0 var(--warn);padding-left:.5rem;\n  margin-left:-.5rem}" in css


def test_a_hidden_row_is_posted_unchecked_and_a_refused_value_opens_its_folds():
    """M3: Run models did nothing when a value out of range sat in the
    closed panel or in a row the model choice hides (the browser could
    not show its message). A hidden row's field is still posted, so the
    next run's form keeps it (the server ignores a knob that does not
    apply), but its limits wait while the row is hidden; a refused value
    in a closed fold (the panel, a group, its "N more") opens each and
    shows the browser's message."""
    js = (Path(__file__).resolve().parents[1] / "ui" / "static"
          / "model_settings.js").read_text()
    assert "setLimits(n, !n.hidden);" in js
    assert "var LIMITS = {min: 'msMin', max: 'msMax', step: 'msStep'};" in js
    assert "if (a === 'step') el.setAttribute('step', 'any');" in js
    # nothing turns a hidden row's field off (an off field is not posted)
    assert "el.disabled = true" not in js
    assert "form.addEventListener('invalid'" in js and "}, true);" in js
    assert "shut.forEach(function (d) { d.open = true; });" in js
    assert "el.reportValidity()" in js
    # Reset resets every field but a coming-later one
    assert "if (!el.disabled) el.value" in js


def _post_run(monkeypatch, tmp_path, body):
    import app.core.data as data
    monkeypatch.setattr(ui_state, "data_mod", data)
    monkeypatch.setattr(data, "vintage_path", lambda d: tmp_path)
    monkeypatch.setattr(data, "vintages", lambda: [FD])
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    started = []
    monkeypatch.setattr(ui_pipeline, "_run_all", lambda s: started.append(s))
    ui_state._status["running"] = None
    client.post("/run", data={"forecast_date": FD, "locations": "Ohio", **body},
                follow_redirects=False)
    ui_state._status["running"] = None
    assert started, ui_state._status.get("flash")
    return started[-1]


#: the owner's weekly settings (docs/team/submission.md, 2026-10-12)
WEEKLY = {"replicates": "1", "particles": "1000",
          "knob.pf.seed_denominator": "season_total_early",
          "knob.oracle.w": "0.25"}


def test_a_groundhog_only_run_keeps_the_filters_settings(tmp_path, monkeypatch,
                                                         pf_engine_ready):
    """The review of M3: a hidden row's field was turned off, so a
    Groundhog-only run posted none of the particle filter's settings and
    the next run's form lost the owner's weekly ones. The browser posts
    them again (hidden, unchecked); a run that posts none of them (a model
    page's Groundhog run) keeps them too."""
    ui_state._last_form.clear()
    _post_run(monkeypatch, tmp_path, {"engine": "all", **WEEKLY})
    # the Forecast tab's Groundhog-only run: every field posted, the
    # filter's ignored by the run and kept by the form
    spec = _post_run(monkeypatch, tmp_path, {"engine": "analogue", **WEEKLY})
    assert "knobs" not in spec.extra
    got = dict(_panel_form(client.get("/forecast").text).fields)
    assert got["knob.oracle.w"] == "0.25" and got["particles"] == "1000"
    assert got["knob.pf.seed_denominator"] == "season_total_early"
    assert got["replicates"] == "1"
    # a model page's Groundhog run: none of the filter's fields posted
    _post_run(monkeypatch, tmp_path, {"engine": "analogue", "replicates": "1",
                                      "knob.groundhog.bandwidth": "3"})
    got = dict(_panel_form(client.get("/forecast").text).fields)
    assert got["knob.oracle.w"] == "0.25" and got["particles"] == "1000"
    assert got["knob.pf.seed_denominator"] == "season_total_early"
    assert got["knob.groundhog.bandwidth"] == "3"
    # what the run could use and did not post is the run's: shipped
    _post_run(monkeypatch, tmp_path, {"engine": "pf"})
    got = dict(_panel_form(client.get("/forecast").text).fields)
    assert got["knob.oracle.w"] == "0.5" and got["particles"] == "10000"
    assert got["knob.groundhog.bandwidth"] == "3"      # not the filter's
    ui_state._last_form.clear()


def test_kept_settings_are_only_what_the_run_cannot_use():
    from app.ui.routes import forecast as F
    prev = {"knobs": {"oracle.w": "0.25", "groundhog.bandwidth": "3"},
            "particles": 1000, "weeks_to_drop": 2}
    sent = {"engine", "forecast_date"}
    assert F._kept_settings(prev, {}, sent, "analogue", None) == (
        {"oracle.w": "0.25"}, {"particles": 1000})
    assert F._kept_settings(prev, {}, sent, "pf", None) == (
        {"groundhog.bandwidth": "3"}, {})
    # the Oracle step off: its settings are kept
    assert F._kept_settings(prev, {}, sent, "pf", "none")[0] == {
        "oracle.w": "0.25", "groundhog.bandwidth": "3"}
    # posted, or a direct call (the re-run passes every older field)
    assert F._kept_settings(prev, {"oracle.w": "0.3"}, None, "analogue",
                            None) == ({}, {})


def test_a_refusal_names_the_setting_as_the_panel_does():
    assert ui_forms._refusal_words("oracle.w: 2 is outside 0 to 1") == (
        "Oracle blend weight: 2 is outside 0 to 1.")
    assert ui_forms._refusal_words("the form sent knob.x more than once") == (
        "The form sent knob.x more than once.")
    assert ui_forms._knob_panel("forecast", {"ms_refused": True})["refused"] == ""


def test_the_panel_comes_into_view_when_opened_near_the_windows_foot():
    """The review: at 1440x900 the summary sat at the window's foot, and
    opening it held the Run row over it, so the panel seemed not to open.
    A click (or a refusal) brings the summary to the top when the panel
    would open out of sight, after base.html's two-frame click guard."""
    ui = Path(__file__).resolve().parents[1] / "ui"
    js = (ui / "static" / "model_settings.js").read_text()
    assert "sum.getBoundingClientRect().bottom + 96 <= foot" in js
    assert "sum.scrollIntoView({block: 'start'," in js
    assert ("requestAnimationFrame(function () {\n"
            "          requestAnimationFrame(function () { reveal(true); });") in js
    assert "if (box.hasAttribute('data-refused')) {" in js
    css = (ui / "static" / "tabs" / "forecast.css").read_text()
    assert "details[data-scope] > summary{scroll-margin-top:.75rem}" in css


def test_the_badge_says_how_the_files_will_be_named():
    """The review of M2: the override starts unticked each run and the
    panel closed, so the closed summary says how a modified run's files
    will be named."""
    js = (Path(__file__).resolve().parents[1] / "ui" / "static"
          / "model_settings.js").read_text()
    assert "'modified · ' + (tick.checked ? 'hub names' : 'non-hub names')" in js
    ui_state._last_form.clear()
    ui_state._last_form.update({
        "forecast_date": FD, "locations": ["Ohio"], "engine": "all",
        "weeks_to_drop": 0, "replicates": 3, "members": 2,
        "season_start": "", "particles": 10000, "drop_same_day": 0,
        "knobs": {"oracle.w": "0.25"}, "submit_modified": True,
        "modified_reason": "r", "ms_refused": False})
    try:
        assert ">modified · hub names</span>" in client.get("/forecast").text
        ui_state._last_form["submit_modified"] = False
        assert ">modified · non-hub names</span>" in client.get("/forecast").text
    finally:
        ui_state._last_form.clear()
    # no override on a replay's panel: the word alone
    p = ui_forms._knob_panel("retro", {"knobs": {"oracle.w": "0.25"}})
    html = srv.templates.env.get_template("_model_settings.html").render(
        knob_panel=p, form=None)
    assert '<span class="uk-badge-t">modified</span>' in html
