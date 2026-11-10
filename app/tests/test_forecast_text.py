"""The Forecast tab's and the run page's words and marks (bug hunt
2026-10-25, G30).

  * With data issues the Settings card keeps its own "i" and the panel's:
    the newest-week line under the date has no "?" while the Data issues
    box names each state, and the box has no "i" of its own or per state.
    Results say the data issues in one row.
  * Run summaries say the choices in the box's words: no raw keys
    ("set_aside", "carry", "zero-anchor level") and no "no row".
  * The Model settings panel lists only what a student can set, with hints
    free of engine names; Methods lists the fixed values.
  * The Settings "i" and the archive-gap refusal say the rule as it works:
    a Saturday the archive skipped is refused, and holidays are named only
    for a gap of a week or two.
  * The Real-time and Vintage pills are a group of pressed buttons.
  * The run page says how a modified run's files were named once, under
    one heading.
"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import knobs as K                              # noqa: E402
from app.core import missing as MS                           # noqa: E402
from app.core import reported                                # noqa: E402
from app.core import runs as runs_mod                        # noqa: E402
from app.core.runs import Ledger, RunSpec                    # noqa: E402
from app.ui import state as ui_state                         # noqa: E402

from test_data_source import (W1, W2, W3, _capture, _hub,     # noqa: E402,F401
                              _isolated, client)
from test_newest_reported import NEW                         # noqa: E402
from test_newest_reported import _hub as _newest_hub         # noqa: E402

UI = Path(__file__).resolve().parents[1] / "ui"
GH = {"analogue": "Groundhog"}


# ------------------------------------------------- FC-26: one statement

#: engine builds the Settings card's engine row can show: none known (CI,
#: no mark), the public engine unread (a computer without it: "engine
#: build unknown" and its "?") and the private production build (an ok
#: badge, no "?")
_PUBLIC_UNREAD = {"branch": "", "commit": "", "dirty": False,
                  "source": "unknown", "engine": "public",
                  "path": "/x/flubnf-public/bin/python",
                  "error": "there is no Python at /x/flubnf-public/bin/python"}
_PRIVATE_PROD = {"branch": "feature/particle-filter", "commit": "2fdadee0",
                 "dirty": False, "source": "git", "path": "/x/PyBNF-pf"}


def _engine_build_pinned(monkeypatch, build: dict) -> None:
    """Pages render the engine build from `build`. The startup thread
    resolves this machine's own build under the shell's engine, not the
    suite's, and can land in the middle of a test: the template's view is
    pinned, not the cache that thread writes. The cache is swapped only
    while the view is worked out, so a write by that thread is never lost
    with the test's copy."""
    from app.ui import templating
    from app.ui import versions as V
    with monkeypatch.context() as m:
        m.setattr(V, "ENGINE_BUILD", dict(build))
        view = V.engine_build_view()
    monkeypatch.setitem(templating.templates.env.globals,
                        "engine_build_view", lambda: dict(view))


@pytest.mark.parametrize("build, eb_marks", [
    ({}, []),
    (_PUBLIC_UNREAD, ["tip-eb-fc"]),
    (_PRIVATE_PROD, []),
], ids=["no-build", "public-unread", "private-production"])
def test_with_data_issues_the_settings_card_keeps_two_marks(tmp_path,
                                                            monkeypatch,
                                                            build, eb_marks):
    _engine_build_pinned(monkeypatch, build)
    _newest_hub(tmp_path / "hub", monkeypatch,
                newest={"Ohio": "0", "Utah": "5", "Nebraska": None})
    ui_state._last_form.clear()
    ui_state._last_form.update({"forecast_date": NEW, "locations": ["all"],
                                "engine": "all"})
    page = client.get("/forecast").text
    card = page.split('class="card fc-settings"', 1)[1].split(
        'id="model-settings"', 1)[0]
    # the Settings "i" alone before the panel: no "?" on the newest-week
    # line, no "i" on the box or its rows; the one "?" the card may carry
    # is the engine build's, when that build is not the production one
    assert card.count('class="uk-tt-btn"') == 1
    assert card.count('class="tipbtn"') == len(eb_marks)
    assert re.findall(r'class="tipbtn"[^>]*aria-describedby="([^"]+)"',
                      card) == eb_marks
    assert 'id="tip-newest-gaps"' not in page and "tip-di-why" not in page
    assert 'id="tt-data-issues"' not in page and 'id="di-count"' not in page
    # the line keeps its counts
    line = page.split('id="newest-check"')[1].split("</p>")[0]
    assert '<span class="uk-badge-t">1 reads 0</span>' in line


def test_results_say_the_data_issues_in_one_row():
    extra = {"data_choices": {"week": W1, "states": {
        "Alaska": {"issue": "no row", "what": "no row", "choice": "carry",
                   "recommended": "carry", "followed": True},
        "Arizona": {"issue": "zero", "what": "reads 0 after 67, 59, 29",
                    "choice": "level", "recommended": "set_aside",
                    "followed": False}}}}
    o = {"analogue_anchor_notes": {
            "Alaska": f"anchored on {W1}: 1 newer week(s) unreported",
            "Arizona": f"zero-anchor level: newest week {W2} reads 0",
            "Utah": f"anchored on {W1}: 1 newer week(s) unreported"},
         "data_flags": {"analogue": [{"location": "Arizona", "week": W2,
                                      "value": 0.0,
                                      "rule": "zero-anchor level"}]}}
    covered = set(MS.choices_of(extra))
    # the states chosen in Data issues are that row's; Utah, not chosen,
    # keeps its own row
    arow = runs_mod.anchor_notes_row(o, GH, skip=covered)
    assert arow[1].startswith("Groundhog: 1 location anchored earlier")
    assert "Alaska" not in arow[1]
    assert runs_mod.zero_anchor_row(o, GH, skip=covered) is None
    row = runs_mod.data_issues_row(o, extra, GH)
    assert row[1].startswith("1 level, 1 anchored earlier<")
    assert ("Alaska: not reported; from the last reported week. Arizona: "
            "reads 0 after 67, 59, 29; level. Groundhog, Alaska: anchored on "
            f"{W1}: 1 newer week(s) unreported. Groundhog, Arizona: level: "
            f"newest week {W2} reads 0.") in row[1]
    # the counts against the recommendations are Run settings', once
    assert "recommended" not in row[1].split("<", 1)[0]
    assert runs_mod.data_issues_label(extra) == (
        "2 states, 1 recommended, 1 changed: Arizona level")


# ------------------------------------------------ FC-27: the box's words

def test_run_summaries_say_choices_in_the_boxs_words():
    assert reported.REASON_TEXT["no row"] == "not reported"
    assert reported.CHOICE_WORDS["carry"] == "from the last reported week"
    extra = {"data_choices": {"states": {
        "Ohio": {"what": "reads 2 after 75", "choice": "set_aside",
                 "followed": False},
        "Utah": {"what": "no row", "choice": "carry", "followed": False},
        "Iowa": {"what": "reads 0", "choice": "abstain", "followed": False}}},
        "knobs": {}}
    label = runs_mod.data_issues_label(extra)
    assert label.endswith("Iowa no forecast, Ohio both from the week before, "
                          "Utah from the last reported week")
    tip = runs_mod.data_issues_row({}, extra, GH)[1]
    for raw in ("set_aside", "carry.", "no row", "abstain"):
        assert raw not in tip, raw
    # a record that names the week a set-aside or carry forecasts from
    # reads with it, as the box's own option did ("Both from 10-04")
    aside = {"choice": "set_aside", "what": "reads 2 after 75", "from_week": "2098-10-04"}
    carry = {"choice": "carry", "what": "no row", "from_week": "2098-10-04"}
    assert reported.choice_text(aside) == "both from 10-04"
    assert reported.choice_text(carry) == "from 10-04"
    assert reported.choice_text({"choice": "set_aside"}) == "both from the week before"
    assert reported.choice_text({"choice": "carry"}) == "from the last reported week"
    assert reported.choice_text({"choice": "keep"}) == "kept"
    assert reported.choice_text({"choice": "omit"}) == "left out"
    assert reported.reason_text("no row") == "not reported"
    assert reported.reason_text("reads 0 after 1, 4") == "reads 0 after 1, 4"
    row = runs_mod.data_issues_row({}, {"data_choices": {"states": {
        "Alaska": {**carry, "followed": True}, "Ohio": {**aside, "followed": True}}}}, GH)
    assert "Alaska: not reported; from 10-04." in row[1]
    assert "Ohio: reads 2 after 75; both from 10-04." in row[1]
    flags = {"analogue": [{"location": "Iowa", "week": W1, "value": 0.0,
                           "rule": "zero-anchor abstain"},
                          {"location": "Utah", "week": W1, "value": 0.0,
                           "rule": "zero-anchor blend"}]}
    assert MS.choices_line(flags) == "1 no forecast, 1 blend"
    # the run-wide rule by the Run form's label
    assert runs_mod.data_issues_label(
        K.write_extra({MS.ZERO_ANCHOR_KEY: "level"}, {})) == (
        "Groundhog when the newest week reads 0: level")


# ----------------------------------------------- FC-28: what can be set

def test_the_panel_lists_only_what_a_student_can_set():
    ui_state._last_form.clear()
    page = client.get("/forecast").text
    panel = page.split('id="model-settings"', 1)[1].split("</details>\n<script")[0]
    assert "coming later" not in panel and "Fixed by the model" not in panel
    for k in K.LATER:
        assert f'data-knob="{k}"' not in panel, k
    for lk in K.LOCKED:
        assert lk.key not in panel.replace("knob.", ""), lk.key
    # the hints name no engine internals
    for raw in ("rule 3", "rho*mult", "i0", "sealed record", "the seal",
                "Liu-West"):
        assert raw not in panel, raw
    # Methods keeps them: the fixed values, the coming-later rows, the
    # technical notes
    mt = client.get("/methods").text
    fixed = mt.split('id="mt-set-fixed"')[1].split("</details>")[0]
    assert all(lk.key in fixed for lk in K.LOCKED)
    assert "Liu-West kernel scale h; the sealed record ran 0.30." in mt
    assert "It pins rho*mult and i0." in mt


# ---------------------------------------------- FC-29: the rule as it is

def test_the_date_rule_and_the_gap_refusal_say_what_happens(tmp_path,
                                                            monkeypatch):
    from app.ui.routes import forecast as ui_forecast
    tpl = (UI / "templates" / "forecast.html").read_text(encoding="utf-8")
    assert "any day anchors on the latest archived week" not in tpl
    assert ("<b>Forecast date:</b> a Saturday must be an archived week; any "
            "other day anchors on the latest archived week before it.") in tpl
    # the gap's own width, from the snapshot before to the one after
    assert ui_forecast._gap_weeks("2026-01-10", "2026-01-24") == 1
    assert ui_forecast._gap_weeks("2024-04-27", "2024-11-16") == 28
    assert ui_forecast._gap_weeks("2026-01-10", "2026-01-17") == 0
    assert ui_forecast._gap_weeks("x", "2026-01-17") == 0
    started = _capture(monkeypatch, tmp_path)
    # a holiday: one Saturday skipped
    _hub(tmp_path / "hub", [W1, W2, W3], [W1, W3], monkeypatch)
    ui_state._status["running"] = None
    client.post("/run", data={"forecast_date": W2, "mode": "vintage",
                              "locations": ["Ohio"], "engine": "analogue"},
                follow_redirects=False)
    assert ui_state._status["flash_detail"].startswith(
        f"The archive skips 1 week after {W1} (usually a holiday week).")
    # an off-season gap: five weeks back to the nearest snapshot
    far = "2098-11-08"
    _hub(tmp_path / "hub2", [W1, far, "2098-11-15"], [W1, "2098-11-15"],
         monkeypatch)
    ui_state._status.update(running=None, flash=None, flash_detail=None)
    client.post("/run", data={"forecast_date": far, "mode": "vintage",
                              "locations": ["Ohio"], "engine": "analogue"},
                follow_redirects=False)
    assert started == []
    detail = ui_state._status["flash_detail"]
    assert "holiday" not in detail
    n = ui_forecast._gap_weeks(W1, "2098-11-15")
    assert n >= 5
    assert detail.startswith(f"The archive skips {n} weeks after {W1}.")


# ------------------------------------------------- FC-30: pressed buttons

def test_the_mode_pills_are_a_group_of_pressed_buttons():
    page = client.get("/forecast").text
    # the row itself is the group; Real-time is pressed before the script runs
    modes = page.split('<div class="modes" role="group" aria-label="Forecast mode">', 1)[1].split("</div>", 1)[0]
    assert 'role="tab' not in modes and "aria-selected" not in modes
    assert modes.count('data-mode="realtime" aria-pressed="true"') == 1
    assert modes.count('data-mode="vintage" aria-pressed="false"') == 1
    assert "b.setAttribute('aria-pressed', b.dataset.mode === mode" in page
    css = (UI / "static" / "nau.css").read_text(encoding="utf-8")
    assert '.pill.mode[aria-pressed="true"]' in css
    assert ".modes > [role=" not in css


# ---------------------------------------------- FC-33: each fact once

def test_the_run_page_names_a_modified_runs_files_once(tmp_path,
                                                      monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    led = Ledger()
    spec = RunSpec(engine="analogue", forecast_date=W1,
                   extra=K.write_extra({"groundhog.own_share": 0.4}, {}))
    rid = led.open_run(spec, Path("pending"), {})
    led.close_run(rid, "ok", {})
    page = client.get(f"/runs/{rid}").text
    assert 'id="modified-note"' in page and "Files named" in page
    rec = page.split('class="card runrec"', 1)[1]
    rec = rec.split("Produced by", 1)[0]
    assert "<dt>files</dt>" not in rec
    assert "<strong>Settings</strong>" not in rec
    assert "<dt>model settings</dt>" in rec
    # the weekly report, read without the app, keeps its files row
    assert "files" in dict(runs_mod.report_settings(json.loads(
        spec.to_json())))
    assert runs_mod.settings_html([("a", "b")], title="").startswith(
        '<div class="hint runsettings"><dl')
