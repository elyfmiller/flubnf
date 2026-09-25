"""The weekly report says the same true thing everywhere.

  * Legend and hover agree: a state that was run and has data but no
    forecast reads "no forecast" (with the run's recorded reason) in both;
    "reporting gap" is kept for a state with no reported data.
"""
import html as _html
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import report_v2, runs as runs_mod                  # noqa: E402

# the console run on the synthetic vintage (PF faked, the rest real)
from test_oracle_step import hubfiles                         # noqa: E402,F401
from test_optional_outputs import _default_run, pipeline_env  # noqa: E402,F401


def _hover(html: str, fips: str) -> str:
    m = re.search(r'data-fips="%s" [^>]*?data-hover="([^"]*)"' % fips, html)
    assert m, fips
    return _html.unescape(m.group(1))


def _legend(html: str) -> str:
    return html[html.index('<div class="legend">'):
                html.index('<p class="hint">Hover a state')]


def _locs():
    from flubnf.settings import load_locations
    locs = load_locations()
    return locs, dict(zip(locs.location_name, locs.location.str.zfill(2)))


def _gh_q(base=100.0):
    return {h: {lv: base + 50 * lv for lv in report_v2.FAN_LEVELS}
            for h in ("0", "1", "2", "3")}


# --------------------------------------------------- legend vs hover (1)

def test_a_bare_card_in_scope_hovers_no_forecast_like_its_legend(tmp_path):
    """The legend calls an in-scope card without probabilities "no
    forecast"; its hover must not call the same state a reporting gap."""
    card = {"fips": "50", "name": "Vermont", "abbr": "VT", "probs": None,
            "hover_html": ""}
    html = report_v2.build_report(
        "2098-01-03", {"VT": card}, {}, {}, tmp_path / "r.html",
        fitted_fips=["50", "39"]).read_text()
    assert "no forecast</span>" in _legend(html)
    hv = _hover(html, "50")
    assert "no forecast" in hv and "reporting gap" not in hv
    # a card-less state in scope (an older bundle's gap) still reads the gap
    assert "reporting gap" in _hover(html, "39")
    assert "reporting gap" in _legend(html)


def test_pipeline_report_names_the_reason_and_keeps_gap_for_real_gaps(
        tmp_path):
    """A Groundhog-only run over Ohio (forecast), Utah (data, but the
    Groundhog abstained: newest week reads 0) and Vermont (no reported data
    at all): Utah is "no forecast" with its reason in legend and hover,
    Vermont alone is the reporting gap."""
    from app.ui import pipeline as ui_pipeline
    locs, n2f = _locs()
    spec = runs_mod.RunSpec(engine="analogue", forecast_date="2098-01-03",
                            locations=["Ohio", "Utah", "Vermont"])
    obs = {loc: [[f"2097-12-{d:02d}", 100.0 + d] for d in (6, 13, 20, 27)]
           for loc in ("Ohio", "Utah")}
    obs["Utah"][-1][1] = 0.0
    outcome = {"analogue_anchor_notes": {
        "Utah": "no forecast: newest week reads 0"}}
    ui_pipeline._write_weekly_report(spec, tmp_path, {}, obs, pd.DataFrame(),
                                     locs, n2f, 1.0, outcome,
                                     an_q={"Ohio": _gh_q()})
    html = (tmp_path / "report.html").read_text()
    leg = _legend(html)
    assert "no forecast</span>" in leg and "reporting gap" in leg
    ut = _hover(html, n2f["Utah"])
    assert "no forecast: newest week reads 0" in ut
    assert "reporting gap" not in ut
    assert "reporting gap" in _hover(html, n2f["Vermont"])
    bundle = json.loads((tmp_path / report_v2.BUNDLE_NAME).read_text())
    assert bundle["gap_fips"] == [n2f["Vermont"]]
    assert bundle["no_forecast"]["analogue"] == {
        n2f["Utah"]: "no forecast: newest week reads 0"}


# ------------------------------------------ the accuracy card's model (2)

def _gh_run(tmp_path, scores=None):
    from app.ui import pipeline as ui_pipeline
    locs, n2f = _locs()
    spec = runs_mod.RunSpec(engine="analogue", forecast_date="2098-01-03",
                            locations=["Ohio", "US"])
    obs = {loc: [[f"2097-12-{d:02d}", 100.0 + d] for d in (6, 13, 20, 27)]
           for loc in ("Ohio", "US")}
    kw = {"scores": scores} if scores is not None else {}
    ui_pipeline._write_weekly_report(
        spec, tmp_path, {}, obs, pd.DataFrame(), locs, n2f, 1.0, {},
        an_q={"Ohio": _gh_q(), "US": _gh_q(1000.0)}, **kw)
    html = (tmp_path / "report.html").read_text()
    return html[html.index('id="st-US"'):]


def test_groundhog_only_accuracy_card_names_the_model_it_waits_on(tmp_path):
    """No truth yet: the placeholder names the Groundhog, the model that
    ran, not an unnamed wait on the PF frame."""
    sec = _gh_run(tmp_path)
    assert "Groundhog: no scored weeks yet" in sec
    assert "Oracle SIHRS" not in sec


def test_groundhog_only_accuracy_card_scores_the_groundhog(tmp_path):
    gh = pd.DataFrame([
        {"location": "Ohio", "fips": "39", "horizon": 0,
         "wis": 1.0, "base_wis": 2.0},
        {"location": "US", "fips": "US", "horizon": 0,
         "wis": 3.0, "base_wis": 2.0}])
    sec = _gh_run(tmp_path, scores={"analogue": gh})
    assert "Groundhog relWIS" in sec
    assert '<td class="num ok">0.500</td>' in sec
    assert "Oracle SIHRS relWIS" not in sec
    assert "no scored weeks yet" not in sec.lower()


# ------------------------------------ Groundhog state detail sections (3)

def test_groundhog_only_run_has_state_sections_from_its_quantiles(tmp_path):
    """No PF samples: each state's fan comes from the Groundhog's
    quantiles on the same as-of-relative weeks (as-of + 7, 14, 21, 28),
    named as the Groundhog's, and the map links to it."""
    from app.ui import pipeline as ui_pipeline
    locs, n2f = _locs()
    spec = runs_mod.RunSpec(engine="analogue", forecast_date="2098-01-03",
                            locations=["Ohio", "US"])
    obs = {loc: [[f"2097-12-{d:02d}", 100.0 + d] for d in (6, 13, 20, 27)]
           for loc in ("Ohio", "US")}
    ui_pipeline._write_weekly_report(
        spec, tmp_path, {}, obs, pd.DataFrame(), locs, n2f, 1.0, {},
        an_q={"Ohio": _gh_q(), "US": _gh_q(1000.0)})
    bundle = json.loads((tmp_path / report_v2.BUNDLE_NAME).read_text())
    oh = bundle["details"]["OH"]
    assert oh["model"] == "analogue"
    fan = oh["fan"]
    assert fan["forecast_times"] == ["2098-01-10", "2098-01-17",
                                     "2098-01-24", "2098-01-31"]
    q = fan["quantiles"]["2098-01-10"]
    assert q["0.5"] == 125.0 and q["0.025"] == 101.25
    assert "Groundhog" in fan["title"]
    assert sum(oh["cat_probs"].values()) > 0.99
    assert bundle["details"]["US"]["model"] == "analogue"
    html = (tmp_path / "report.html").read_text()
    assert 'id="st-OH"' in html and "click it for detail" in html
    assert re.search(r'data-fips="39" [^>]*data-abbr="OH"', html)
    # the national section draws its (Groundhog) fan
    sec = html[html.index('id="st-US"'):]
    assert "national model run lands" not in sec


def test_pf_samples_still_draw_the_pf_fan_where_they_exist(tmp_path):
    """A state with PF samples keeps the PF's fan; only the states the PF
    left out fall back to the Groundhog's."""
    import numpy as np
    from app.ui import pipeline as ui_pipeline
    locs, n2f = _locs()
    spec = runs_mod.RunSpec(engine="pf", forecast_date="2098-01-03",
                            locations=["Ohio", "Utah"])
    rng = np.random.default_rng(3)
    pf = {"Ohio": {h: rng.gamma(5.0, 20.0, 300).tolist()
                   for h in ("0", "1", "2", "3")}}
    obs = {loc: [[f"2097-12-{d:02d}", 100.0 + d] for d in (6, 13, 20, 27)]
           for loc in ("Ohio", "Utah")}
    (tmp_path / "cells.json").write_text("[]")
    ui_pipeline._write_weekly_report(
        spec, tmp_path, pf, obs, pd.DataFrame(), locs, n2f, 1.0, {},
        an_q={"Ohio": _gh_q(), "Utah": _gh_q()})
    d = json.loads((tmp_path / report_v2.BUNDLE_NAME).read_text())["details"]
    assert d["OH"]["model"] == "pf" and "Groundhog" not in d["OH"]["fan"][
        "title"]
    assert d["UT"]["model"] == "analogue"


# ------------------------------------- the bundle's dates, named right (7)

def test_bundle_stores_the_asof_and_the_true_reference_date(tmp_path):
    """reference_date held the as-of; the bundle now stores both, each
    under its own name (hub reference_date = as-of + 7, the frozen join),
    and the report still reads the as-of."""
    from app.core.submit import hub_reference_date
    _gh_run(tmp_path)
    b = json.loads((tmp_path / report_v2.BUNDLE_NAME).read_text())
    assert b["asof"] == "2098-01-03"
    assert b["reference_date"] == str(hub_reference_date("2098-01-03").date())
    assert report_v2.bundle_asof(b) == "2098-01-03"
    report_v2.render_bundle(b, tmp_path / "again.html")
    assert "week of 2098-01-03" in (tmp_path / "again.html").read_text()


def test_report_names_the_runs_recorded_build_like_the_run_page(tmp_path,
                                                                monkeypatch):
    """After an update without a restart the server's RUNNING_SHA is not
    the code the run recorded; the report's app build (and engine versions)
    come from the run's ledger row, exactly as the run page shows them."""
    from app.ui import pipeline as ui_pipeline
    from app.ui.versions import RUNNING_SHA
    locs, n2f = _locs()
    spec = runs_mod.RunSpec(engine="analogue", forecast_date="2098-01-03",
                            locations=["Ohio"])
    obs = {"Ohio": [[f"2097-12-{d:02d}", 100.0 + d] for d in (6, 13, 20, 27)]}
    row = {"flubnf_sha": "a1b2c3d",
           "engine_versions": json.dumps({"engines": "pf,analogue",
                                          "pybnf": "1.2.3"})}
    ui_pipeline._write_weekly_report(
        spec, tmp_path, {}, obs, pd.DataFrame(), locs, n2f, 1.0, {},
        an_q={"Ohio": _gh_q()}, run_row=row)
    b = json.loads((tmp_path / report_v2.BUNDLE_NAME).read_text())
    assert "a1b2c3d" in b["settings_html"]
    if RUNNING_SHA:
        assert RUNNING_SHA not in b["settings_html"]
    # the run page's pairs (version_pairs of the row), not this process's
    assert "<dt>app build</dt><dd>a1b2c3d</dd>" in b["settings_html"]
    assert "<dt>pybnf</dt><dd>1.2.3</dd>" in b["settings_html"]
    assert "not installed" not in b["settings_html"]


def test_the_pipeline_hands_the_report_its_ledger_row(pipeline_env,
                                                      monkeypatch):
    from app.core.runs import Ledger
    from app.ui import pipeline as P
    seen = {}
    monkeypatch.setattr(P, "_write_weekly_report",
                        lambda *a, **k: seen.update(k))
    _default_run(pipeline_env["names"])
    row = Ledger().rows(1)[0]
    assert seen["run_row"]["run_id"] == row["run_id"]
    assert seen["run_row"]["flubnf_sha"] == row["flubnf_sha"]


def test_an_older_bundles_reference_date_still_reads_as_its_asof(tmp_path):
    old = {"version": 5, "reference_date": "2098-01-03", "cards": {},
           "details": {}, "national": {"summary_html": ""}}
    assert report_v2.bundle_asof(old) == "2098-01-03"
    html = report_v2.render_bundle(old, tmp_path / "r.html").read_text()
    assert "week of 2098-01-03" in html
