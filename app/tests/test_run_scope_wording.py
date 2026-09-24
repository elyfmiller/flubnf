"""What a run did NOT do is said plainly.

  * Retrospective Run settings (app.core.retro.settings_summary, shared by
    the console and both reports): the engine preset in plain words, and
    no particle/replicate/shard rows when no particle filter ran.
  * The weekly report of a run with no state detail sections (a
    Groundhog-only run): the map invites a click only when a section
    exists, states without one wear no hover ring, states outside the run
    read "not fitted in this run" (not "no forecast"), and the national
    detail says US was not part of the run instead of waiting on scores.
  * The shared chart config turns Plotly's legend tips off (the "Double-click
    on legend" hint covered the expanded view's Close button).
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import report_v2, retro, runs as runs_mod, usmap   # noqa: E402
from app.core.scoring import NO_SCORES_HTML, summary_table_html   # noqa: E402

GH_META = {"season": "2025-26", "settings": {
    "season": "2025-26", "scope": "panel6",
    "locations": ["Alaska", "US"], "particles": 10000, "replicates": 3,
    "width": 4, "engine": "analogue"}}


# ------------------------------------------------ retrospective settings

def test_groundhog_replay_names_the_preset_and_drops_filter_rows():
    pairs = dict(retro.settings_summary(GH_META))
    assert pairs["engine"] == "Groundhog only"
    assert "engine preset" not in pairs
    # the form's defaults were recorded, but no filter ran
    for k in ("particles", "replicates", "shard width"):
        assert k not in pairs
    assert pairs["season"] == "2025-26"


def test_pf_replay_keeps_its_filter_rows_in_plain_words():
    meta = json.loads(json.dumps(GH_META))
    meta["settings"]["engine"] = "pf"
    pairs = dict(retro.settings_summary(meta))
    assert pairs["engine"] == "Oracle SIHRS and the Groundhog"
    assert pairs["particles"] == "10,000"
    assert pairs["replicates"] == "3" and pairs["shard width"] == "4"
    # a record from before the preset ran the filter, and names no engine
    del meta["settings"]["engine"]
    pairs = dict(retro.settings_summary(meta))
    assert pairs["particles"] == "10,000" and "engine" not in pairs


def test_one_label_map_serves_the_route_and_the_record():
    from app.ui.routes import retro as ui_retro
    for k in retro.ENGINES:
        assert ui_retro.retro_engine_label(k) == retro.engine_label(k)
    assert retro.engine_label("analogue") == "Groundhog only"


# --------------------------------------------------- weekly report wording

def _cards(abbrs=("OH",)):
    fips = {"OH": "39", "TX": "48"}
    out = {a: {"name": a, "abbr": a, "fips": fips[a],
               "probs": {"stable": 1.0}, "hover_html": f"<b>{a}</b>"}
           for a in abbrs}
    out["TX"] = out.get("TX") or {"name": "Texas", "abbr": "TX",
                                  "fips": "48"}      # bare card, not run
    return out


def _detail():
    fan = report_v2.fan_figure_from_quantiles(
        ["2026-01-03"], [10.0], ["2026-01-10"],
        {"2026-01-10": {str(lv): 10.0 for lv in report_v2.FAN_LEVELS}})
    return {"OH": {"name": "Ohio", "fan": fan,
                   "cat": report_v2.cat_bar({"stable": 1.0}),
                   "table_rows": []}}


def test_click_invitation_only_with_sections(tmp_path):
    none = report_v2.build_report(
        "2026-01-03", _cards(), {}, {}, tmp_path / "a.html",
        fitted_fips=["39"]).read_text()
    assert "click it" not in none
    assert "Hover a state for its category probabilities;" in none
    some = report_v2.build_report(
        "2026-01-03", _cards(), _detail(), {}, tmp_path / "b.html",
        fitted_fips=["39"]).read_text()
    assert "Hover a state for its category probabilities, click it" in some


def test_states_without_a_section_do_not_look_clickable():
    svg = usmap.svg_map({"39": {"abbr": "OH", "name": "Ohio",
                                "probs": {"stable": 1.0}}},
                        clickable=set())
    assert 'class="st noclick"' in svg and 'data-abbr="OH"' not in svg
    assert "click for details" not in svg
    # cursor and hover ring belong to clickable states only
    assert ".st.noclick{cursor:default}" in svg
    assert ".st:not(.noclick):hover{stroke:" in svg
    assert ".st:hover{" not in svg


def test_states_outside_the_run_read_not_fitted(tmp_path):
    html = report_v2.build_report(
        "2026-01-03", _cards(), {}, {}, tmp_path / "a.html",
        fitted_fips=["39"]).read_text()
    assert "not fitted in this run</span>" in html
    assert "no forecast</span>" not in html
    # an in-scope card without probabilities is still "no forecast"
    html = report_v2.build_report(
        "2026-01-03", _cards(), {}, {}, tmp_path / "b.html",
        fitted_fips=["39", "48"]).read_text()
    assert "no forecast</span>" in html


def test_national_detail_says_us_was_not_run(tmp_path):
    nat = {"summary_html": "<div class='card'>" + summary_table_html(
        pd.DataFrame()) + "</div>"}
    assert NO_SCORES_HTML in nat["summary_html"]
    out = report_v2.build_report(
        "2026-01-03", _cards(), {}, dict(nat), tmp_path / "a.html",
        fitted_fips=["39"], national_in_run=False).read_text()
    sec = out[out.index('id="st-US"'):]
    assert "US (national) was not part of this run." in sec
    assert "No scored weeks yet" not in sec
    assert "national model run lands" not in sec
    # unknown (older bundles): nothing new is claimed
    old = report_v2.build_report(
        "2026-01-03", _cards(), {}, dict(nat), tmp_path / "b.html",
        fitted_fips=["39"]).read_text()
    assert "was not part of this run" not in old
    assert "No scored weeks yet" in old


def test_groundhog_only_pipeline_run_records_scope_and_says_so(tmp_path):
    """The real build path for a Groundhog-only, states-only run: no PF
    samples (the state sections are the Groundhog's) and no national run."""
    from flubnf.settings import load_locations
    from app.ui import pipeline as ui_pipeline
    locs = load_locations()
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    spec = runs_mod.RunSpec(engine="analogue", forecast_date="2098-01-03",
                            locations=["Ohio"])
    an_q = {"Ohio": {h: {str(lv): 100.0 + 50 * lv for lv in
                         report_v2.FAN_LEVELS} for h in ("0", "1", "2", "3")}}
    obs = {"Ohio": [[f"2097-12-{d:02d}", 100.0 + d] for d in (6, 13, 20, 27)]}
    outcome = {}
    ui_pipeline._write_weekly_report(spec, tmp_path, {}, obs, pd.DataFrame(),
                                     locs, n2f, 1.0, outcome, an_q=an_q)
    bundle = json.loads((tmp_path / report_v2.BUNDLE_NAME).read_text())
    assert bundle["version"] == report_v2.BUNDLE_VERSION >= 5
    assert bundle["national_in_run"] is False
    html = (tmp_path / "report.html").read_text()
    # the Groundhog's fan gives Ohio a section, so the map invites a click
    assert "click it" in html and 'id="st-OH"' in html
    assert "US (national) was not part of this run." in html
    assert "No scored weeks yet" not in html
    # a run that includes US records it
    spec2 = runs_mod.RunSpec(engine="analogue", forecast_date="2098-01-03",
                             locations=["Ohio", "US"])
    (tmp_path / "b").mkdir()
    ui_pipeline._write_weekly_report(spec2, tmp_path / "b", {}, obs,
                                     pd.DataFrame(), locs, n2f, 1.0, {},
                                     an_q=an_q)
    b2 = json.loads((tmp_path / "b" / report_v2.BUNDLE_NAME).read_text())
    assert b2["national_in_run"] is True
