"""The Model settings panel (templates/_model_settings.html, Stage 3 of
app/core/knobs.py) on the Forecast and Retrospective forms.

Rendered from the registry: every knob a scope can carry has a labelled
input and a "?" tip; the older field names are kept; the rendered form
posted untouched runs the shipped spec; a refused submission keeps what
was typed; the override and its reason are offered on the Forecast form.
"""
import json
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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


def test_forecast_panel_renders_every_forecast_knob_with_a_tip():
    html = client.get("/forecast").text
    assert 'id="model-settings"' in html and 'id="ms-badge"' in html
    f = _panel_form(html)
    names = {n for n, _ in f.fields} | f.disabled
    for k in K.REGISTRY:
        name = K.FIELD_OF.get(k.key, "knob." + k.key)
        assert name in names, k.key
        tid = "tip-ks-" + k.key.replace(".", "-") + "-tip"
        assert f'id="{tid}"' in html, k.key
        assert f'aria-describedby="{tid}"' in html
    # the older field names are the knobs' own on this form
    for old in ("season_start", "weeks_to_drop", "replicates", "particles",
                "drop_same_day"):
        assert old in names
    # coming-later knobs are shown, disabled, and never posted
    assert {"knob." + k for k in K.LATER} == f.disabled
    assert html.count("coming later") >= len(K.LATER)
    # the override and its reason, and the reset control
    assert 'name="submit_modified"' in html and 'name="modified_reason"' in html
    assert 'id="ms-reset"' in html and "Reset to shipped" in html
    assert "/static/model_settings.js" in html
    # the fixed list, with its tip
    assert "Fixed by the model definition" in html
    for key in ("horizons", "quantile_levels", "epiweek_53", "gamma"):
        assert f"<dt>{key}</dt>" in html


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
    assert '<details class="adv" open id="model-settings"' in html
    assert 'id="ms-badge"' in html and ">modified</span>" in html
    assert 'id="ms-override" hidden' not in html


def test_the_shipped_page_reads_shipped():
    ui_state._last_form.clear()
    html = client.get("/forecast").text
    assert ">shipped</span>" in html
    assert 'id="ms-override" hidden' in html


def test_panel_data_is_the_registry():
    p = K.panel("forecast")
    keys = [r["key"] for g in p["groups"] for r in g["rows"]]
    assert sorted(keys) == sorted(K.BY_KEY)
    assert not p["modified"]
    rp = K.panel("retro")
    assert not {r["key"] for g in rp["groups"] for r in g["rows"]} \
        & K.NOT_IN_RETRO
    assert K.panel("forecast", {"oracle.w": "0.25"})["modified"]
    # a coming-later knob never reads modified, whatever was posted
    assert not K.panel("forecast", {"oracle.count_floor": "5"})["modified"]
    assert ui_forms._knobs.FORM_PREFIX == K.FORM_PREFIX
    json.dumps(p)                                       # template-safe
