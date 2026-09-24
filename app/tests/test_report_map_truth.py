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
