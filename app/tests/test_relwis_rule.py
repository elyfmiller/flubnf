"""The single relWIS rule.

Everywhere a relWIS prints outside a scores table it must wear the same
encoding the app teaches elsewhere: tabular numerals, the ok/bad
below-1-beats-baseline classes, and a label naming the member and the cell
coverage the score rests on. Error chips speak plain language; the raw
error string lives on the run page and nowhere else. The Methods
performance table colors every printed score, member failures included.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

from app.ui import server as srv                    # noqa: E402
from app.ui import shared as ui_shared              # noqa: E402

client = TestClient(srv.app)

NAU = Path(__file__).resolve().parents[1] / "ui" / "static" / "nau.css"


def test_relwis_chip_formats_member_coverage_and_classes():
    # with no member given, the mechanistic member's display name (never
    # the internal "PF")
    assert ui_shared.relwis_chip(4.067, cells=2) == \
        ('Oracle SIHRS relWIS <span class="relwis bad">4.067</span>'
         ' vs FluSight baseline, ratio of sums (2 cells)')
    assert ui_shared.relwis_chip(0.987, cells=1, member="Groundhog") == \
        ('Groundhog relWIS <span class="relwis ok">0.987</span>'
         ' vs FluSight baseline, ratio of sums (1 cell)')
    # coverage unknown: the parenthetical is omitted, never invented
    assert ui_shared.relwis_chip(0.5) == \
        ('Oracle SIHRS relWIS <span class="relwis ok">0.500</span>'
         ' vs FluSight baseline, ratio of sums')
    # an unreadable value yields nothing rather than a broken chip
    assert ui_shared.relwis_chip("nonsense") == ""
    assert ui_shared.relwis_chip(None) == ""


def test_outcome_chips_apply_the_rule():
    chips = ui_shared._outcome_chips(json.dumps(
        {"pf_cells": 2, "pf_failures": {"a": "boom"},
         "submissions": {"PF-SIHRS": "p", "Ensemble": "q"},
         "report": "r.html", "pf_relwis": 4.067}))
    # a row from before the Oracle step (no bank recorded): the filter
    # alone, one name for its fits and its relWIS
    assert "Particle filter alone: 2 fits" in chips
    assert '<span class="bad">1 failure</span>' in chips
    assert "2 submissions" in chips
    assert ('Particle filter alone relWIS <span class="relwis bad">4.067'
            '</span> vs FluSight baseline, ratio of sums (2 cells)') in chips
    good = ui_shared._outcome_chips(json.dumps({"pf_cells": 1,
                                          "pf_relwis": 0.702}))
    assert ('Particle filter alone relWIS <span class="relwis ok">0.702'
            '</span> vs FluSight baseline, ratio of sums (1 cell)') in good


def test_ledger_figures_say_their_verdict_with_an_icon():
    """On the Storage ledger a relWIS figure is followed by the kit's check
    or warning icon, named, so the verdict never rests on color alone."""
    items = ui_shared._outcome_items({"pf_cells": 2, "pf_relwis": 4.067,
                                      "analogue_relwis": 0.702})
    pf, gh = [str(i["text"]) for i in items if "relWIS" in i["chip"]]
    assert '<span class="relwis bad">4.067</span><svg class="uk-icon ' \
           'st-verdict uk-c-error"' in pf
    assert 'aria-label="does not beat the baseline"' in pf
    assert '0.702</span><svg class="uk-icon st-verdict uk-c-ok"' in gh
    assert 'aria-label="beats the baseline"' in gh


def test_outcome_chips_name_the_mechanistic_member_by_what_the_row_ran():
    """The chip names the member by what the row ran, with the season
    trees' two display names (site_build.PF_LABEL_ORACLE and
    PF_LABEL_FILTER), never the internal "PF" or a name of its own: the
    Oracle step's bank label -> Oracle SIHRS; oracle = none, or a row from
    before the step (no bank) -> Particle filter alone. Every fact of a row
    names the member the same way, and the run page names it so too (M-E17).
    Nothing in the ledger is rewritten: the name is read from the outcome."""
    from app.core import runs
    from app.core.site_build import PF_LABEL_FILTER, PF_LABEL_ORACLE
    member = ui_shared._outcome_chips(json.dumps(
        {"pf_cells": 9, "pf_relwis": 0.741, "pf_relwis_cells": 9,
         "oracle": "admissions-fbase@288b139f"}))
    assert member.startswith(f"{PF_LABEL_ORACLE}: 9 fits")
    assert (f'{PF_LABEL_ORACLE} relWIS <span class="relwis ok">0.741</span>'
            ' vs FluSight baseline, ratio of sums (9 cells)') in member
    plain = ui_shared._outcome_chips(json.dumps(
        {"pf_relwis": 0.813, "oracle": "none"}))
    assert plain.startswith(f"{PF_LABEL_FILTER} relWIS")
    old = ui_shared._outcome_chips(json.dumps({"pf_cells": 3,
                                               "pf_relwis": 0.813}))
    assert old.startswith(f"{PF_LABEL_FILTER}: 3 fits")
    assert f"{PF_LABEL_FILTER} relWIS" in old
    for chips in (member, plain, old):
        assert "PF " not in chips and "plain filter" not in chips
    # a filter that never ran is named for the member it was to run
    skipped = ui_shared._outcome_chips(json.dumps({"pf_skipped": "no venv"}))
    assert skipped.startswith(f"{PF_LABEL_ORACLE} skipped (no engine)")
    # the run page's results table names the member the same way
    spec = json.dumps({"forecast_date": "2098-01-03"})
    page = runs.results_html({"pf_cells": 3, "pf_relwis": 0.813}, spec)
    assert f'<th scope="row">{PF_LABEL_FILTER}</th>' in page
    assert f'<th scope="row">{PF_LABEL_FILTER} fits</th>' in page
    assert PF_LABEL_ORACLE not in page
    page = runs.results_html({"pf_cells": 9, "pf_relwis": 0.741,
                              "oracle": "admissions-fbase@288b139f"}, spec)
    assert f'<th scope="row">{PF_LABEL_ORACLE}</th>' in page
    assert f'<th scope="row">{PF_LABEL_ORACLE} fits</th>' in page
    # and its settings, beside the results on the run page, say the same:
    # the members as they ran, and no Oracle step before it existed
    spec = json.dumps({"forecast_date": "2098-01-03", "engine": "all"})
    old = dict(runs.spec_settings(spec, {"pf_cells": 3, "pf_relwis": 0.8}))
    assert old["engine"] == runs.ENGINE_LABELS["all"].replace(
        PF_LABEL_ORACLE, PF_LABEL_FILTER)
    assert old["Oracle step"] == "not applied (a run from before the step)"
    now = dict(runs.spec_settings(spec, {"pf_cells": 3,
                                         "oracle": "admissions-fbase@x"}))
    assert now["engine"] == runs.ENGINE_LABELS["all"]
    assert now["Oracle step"] == "on (console default)"
    # the engine row is built from the member's name, never by editing
    # the text: a filter-only run is the filter alone, not "... only"
    pf_only = json.dumps({"forecast_date": "2098-01-03", "engine": "pf"})
    solo = dict(runs.spec_settings(pf_only, {"pf_cells": 3}))
    assert solo["engine"] == PF_LABEL_FILTER
    solo = dict(runs.spec_settings(pf_only, {"pf_cells": 3,
                                             "oracle": "admissions-fbase@x"}))
    assert solo["engine"] == runs.ENGINE_LABELS["pf"]
    # every row of the results table names the member one way: the
    # anchor-notes row too
    page = runs.results_html({"pf_cells": 3, "pf_relwis": 0.8,
                              "pf_anchor_notes": {"Ohio": "anchored on "
                                                  "2098-01-03"}}, spec)
    assert f"{PF_LABEL_FILTER}: 1 location anchored earlier" in page
    assert PF_LABEL_ORACLE not in page
    # asked, not yet run (the progress card): the console's default
    asked = dict(runs.spec_settings(spec))
    assert asked["engine"] == runs.ENGINE_LABELS["all"]
    assert asked["Oracle step"] == "on (console default)"
    # a run on a dataset: its member as the dataset pages name it
    from app.core.custom_run import MEMBER_LABELS
    assert runs.pf_member_name({"dataset": "d", "oracle": "none"}) == \
        MEMBER_LABELS["pf"]


def test_error_chips_speak_plain_language_never_tracebacks():
    raw = "module 'pandas.io.json' has no attribute 'dumps'"
    chips = ui_shared._outcome_chips(json.dumps({"error": raw}))
    assert "pandas" not in chips                  # the raw string never leaks
    assert '<span class="bad">failed</span>' in chips
    assert "run page" in chips                    # and says where the raw is


def test_runs_page_renders_chips_as_markup():
    html = srv.templates.env.get_template("runs.html").render(
        active="Runs", ledger=[
            {"run_id": "r1", "label": "2098-01-03 · Jan 03 09:31",
             "status": "ok", "elapsed_s": 60.0,
             "facts": ui_shared._outcome_items(json.dumps(
                 {"pf_cells": 2, "pf_relwis": 4.067}))}])
    # the span survives unescaped, so the color classes actually apply
    assert '<span class="relwis bad">4.067</span>' in html
    assert "&lt;span" not in html


def test_run_page_keeps_the_raw_error_string():
    raw = "module 'pandas.io.json' has no attribute 'dumps'"
    html = srv.templates.env.get_template("run.html").render(
        active="Runs", run_id="r1", status="error", error=raw,
        label="2098-01-03", models={}, settings=[], versions=[],
        subs=[], report=None)
    assert "pandas.io.json" in html               # the raw record of what broke


def test_methods_table_colors_every_score_members_included():
    r = client.get("/methods")
    assert r.status_code == 200
    # member seasons that lost to the baseline are marked, not neutral,
    # and say so with an icon too (never color alone)
    assert ('<td class="num bad">1.045<svg class="uk-icon mt-verdict"'
            in r.text)
    assert 'aria-label="does not beat the baseline"' in r.text
    # and seasons that beat it wear the same ok, both models and the
    # retired bare analogue's reference row alike
    for v in ("0.767", "0.697", "0.781", "0.756", "0.618",
              "0.680", "0.627", "0.645"):
        assert f'<td class="num ok">{v}<svg class="uk-icon mt-verdict"' in r.text, v


def test_relwis_class_is_tabular():
    css = NAU.read_text()
    assert ".relwis{font-variant-numeric:tabular-nums" in css
