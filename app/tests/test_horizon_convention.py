"""The horizon convention, pinned before anyone reindexes it.

Two zero-horizons, ONE WEEK APART:

  stored "0"     the ORIGIN: the anchor week (last observed point), as every
                 samples.json.gz on disk keys it; the sealed record is frozen.
  canonical "0"  the FIRST FORECAST week (the hub's label; its
                 target_end_date equals the reference_date).

A rename would overwrite the anchor with a forecast and shift every
submitted row a week early with the right row count. So the stored form is
frozen and app.core.horizons translates at the storage boundary: in memory
horizons are "0".."3" and the anchor is ORIGIN.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import ensemble as ENS, floor, submit as SUB   # noqa: E402
from app.core.engines import pf as PF                        # noqa: E402


from app.core import horizons as HZ                            # noqa: E402

# the console run on the synthetic vintage (PF faked, the rest real)
from test_oracle_step import hubfiles                         # noqa: E402,F401
from test_optional_outputs import _default_run, pipeline_env  # noqa: E402,F401

#: a canonical member: four forecasts plus the anchor riding alongside
FIVE = {h: [10.0 * (int(h) + 2), 11.0 * (int(h) + 2), 12.0 * (int(h) + 2)]
        for h in HZ.HORIZONS}
FIVE[HZ.ORIGIN] = [10.0, 11.0, 12.0]


def test_the_stored_and_canonical_zeroes_are_a_week_apart():
    """The whole reason app.core.horizons exists."""
    assert HZ.to_canonical({"0": "anchor"}) == {HZ.ORIGIN: "anchor"}
    assert HZ.to_canonical({"1": "first forecast"}) == {"0": "first forecast"}
    assert HZ.ORIGIN not in HZ.HORIZONS


def test_the_boundary_round_trips_a_whole_week():
    stored = {"0": "anchor", "1": "a", "2": "b", "3": "c", "4": "d"}
    canon = HZ.to_canonical(stored)
    assert canon == {HZ.ORIGIN: "anchor", "0": "a", "1": "b", "2": "c", "3": "d"}
    assert HZ.to_stored(canon) == stored


def test_an_unknown_key_is_carried_through_not_guessed_at():
    """An unknown key is carried through intact, never renamed."""
    assert HZ.to_canonical({"9": "?"}) == {"9": "?"}


def test_pf_collect_emits_the_anchor_under_origin():
    import inspect
    src = inspect.getsource(PF.collect)
    assert "d[hz.ORIGIN].extend" in src
    # col is the fit origin's column (n - 1, or the last week offset for a
    # gapped series laid out one column per week)
    assert "tr[:, col + k]" in src              # the origin: no horizon added
    assert "tr[:, col + k + h]" in src          # the forecasts: h weeks on
    assert "d[str(h - 1)]" in src               # ... stored under hub labels


def test_floor_excludes_the_origin_from_the_collapse_test():
    import inspect
    src = inspect.getsource(floor)
    assert "str(h) != hz.ORIGIN" in src


def test_submission_horizon_zero_carries_canonical_zero_not_the_anchor():
    """FluSight horizon 0 (target_end_date == reference date) is fed by
    canonical "0", never ORIGIN."""
    rows = SUB.quantile_rows(FIVE, "01", "2026-01-03")
    ref = SUB.hub_reference_date("2026-01-03")
    h0 = [r for r in rows if r["horizon"] == 0]
    assert h0, "no horizon 0 rows"
    assert {r["target_end_date"] for r in h0} == {str(ref.date())}
    # canonical "0" has median 11.0*2 = 22; the anchor's is 11
    med = [r["value"] for r in h0 if abs(float(r["output_type_id"]) - 0.5) < 1e-9]
    assert med and med[0] == pytest.approx(22.0, abs=0.5)


def test_the_four_submitted_horizons_are_canonical_zero_through_three():
    rows = SUB.quantile_rows(FIVE, "01", "2026-01-03")
    assert sorted({r["horizon"] for r in rows}) == [0, 1, 2, 3]
    ref = SUB.hub_reference_date("2026-01-03")
    import pandas as pd
    for h in (0, 1, 2, 3):
        ends = {r["target_end_date"] for r in rows if r["horizon"] == h}
        assert ends == {str((ref + pd.Timedelta(weeks=h)).date())}


def test_a_member_carrying_only_the_anchor_submits_nothing():
    """An anchor-only member submits nothing."""
    rows = SUB.quantile_rows({HZ.ORIGIN: FIVE[HZ.ORIGIN]}, "01", "2026-01-03")
    assert rows == []


def test_a_stored_shaped_member_does_not_sneak_the_anchor_in():
    """submit trusts its input to be canonical: a STORED-shaped dict would
    submit the anchor as horizon 0 (documented here; the storage boundary
    prevents it)."""
    stored = {"0": [999.0, 999.0, 999.0], "1": [1.0, 1.0, 1.0]}
    rows = SUB.quantile_rows(stored, "01", "2026-01-03")
    h0 = [r["value"] for r in rows if r["horizon"] == 0
          and abs(float(r["output_type_id"]) - 0.5) < 1e-9]
    assert h0 and h0[0] == 999, (
        "this documents that submit trusts its input to be canonical; the "
        "storage boundary is what guarantees that")


def test_member_quantiles_never_consume_the_origin():
    """member_quantiles_from_samples ignores the origin key."""
    s = {h: [1.0, 10.0, 99.0] for h in HZ.HORIZONS}
    s[HZ.ORIGIN] = [1.0, 10.0, 99.0]
    out = ENS.member_quantiles_from_samples(s)
    assert sorted(out) == ["0", "1", "2", "3"]


def test_scoring_never_consumes_the_origin():
    import inspect
    from app.core import scoring
    src = inspect.getsource(scoring.score_quantiles)
    assert "for h in (0, 1, 2, 3)" in src


# ---------------------------------------------------------------------------
# Run artefacts (results.json) carry NO anchor: conventions are told apart
# by the presence of "4". Pre-reindex workroots must keep rendering.
# ---------------------------------------------------------------------------

def test_a_legacy_run_artefact_still_reads():
    legacy = {"ensemble": {"Ohio": {"1": {"0.5": 14.0}, "2": {"0.5": 15.0},
                                    "3": {"0.5": 16.0}, "4": {"0.5": 17.0}}}}
    out = HZ.models_to_canonical(legacy)
    assert sorted(out["ensemble"]["Ohio"]) == ["0", "1", "2", "3"]
    # one week ahead keeps its VALUE, it only changes its label
    assert out["ensemble"]["Ohio"]["0"] == {"0.5": 14.0}


def test_a_canonical_run_artefact_is_left_alone():
    canon = {"ensemble": {"Ohio": {h: {"0.5": 14.0 + int(h)}
                                   for h in HZ.HORIZONS}}}
    assert HZ.models_to_canonical(canon) == canon


def test_detection_is_per_location_not_per_file():
    """Each location map decides its own convention (no whole-file guess)."""
    mixed = {"ensemble": {"Old": {"1": 1, "2": 2, "3": 3, "4": 4},
                          "New": {"0": 1, "1": 2, "2": 3, "3": 4}}}
    out = HZ.models_to_canonical(mixed)
    assert out["ensemble"]["Old"] == {"0": 1, "1": 2, "2": 3, "3": 4}
    assert out["ensemble"]["New"] == {"0": 1, "1": 2, "2": 3, "3": 4}


def test_run_artefacts_round_trip():
    canon = {"pf": {"Ohio": {h: {"0.5": float(h)} for h in HZ.HORIZONS}}}
    assert HZ.models_to_canonical(HZ.models_to_stored(canon)) == canon


def test_read_samples_is_the_boundary_not_read_week_samples():
    """The conversion lives in read_samples (the file parser), so every
    caller, e.g. the national aggregate, sees canonical keys."""
    import inspect
    from app.core import retro
    assert "hz.record_to_canonical" in inspect.getsource(retro.read_samples)


# ---------------------------------------------------------------------------
# The public site: site_build emits canonical fan keys; the page's JS reads
# exactly those, and a live run's stored results.json is canonicalised first.
# ---------------------------------------------------------------------------

def test_site_page_js_iterates_the_canonical_horizons():
    """draw() iterates the canonical horizons (stored keys dropped week one)."""
    import json
    import re
    from app.core import site_page
    js = re.sub(r"\s+", "", site_page.JS)
    stored = "['1','2','3','4']"
    assert stored not in js and stored.replace("'", '"') not in js
    canon = json.dumps(list(HZ.HORIZONS)).replace(" ", "")
    assert "hs=" + canon in js, (
        "draw() must iterate the canonical horizons from app.core.horizons")


def _levels(v):
    return {str(L): v + L for L in (0.1, 0.25, 0.5, 0.75, 0.9)}


def test_live_run_fans_keep_all_four_weeks_from_a_legacy_results_json():
    from app.core import site_build as sb
    legacy = {h: _levels(10.0 * int(h)) for h in HZ.STORED_HORIZONS}
    results = {"forecast_date": "2026-01-03",
               "observed": {"Ohio": [["2025-12-27", 5.0],
                                     ["2026-01-03", 6.0]]},
               "models": {"pf": {"Ohio": legacy},
                          "analogue": {"Ohio": legacy}}}
    fans = sb._fans_from_results(results, {})
    q = fans["Ohio"]["q"]
    assert sorted(q) == list(HZ.HORIZONS)
    # one week ahead (stored "1") is canonical "0"; four weeks ahead kept
    assert q["0"]["0.5"] == pytest.approx(10.5)
    assert q["3"]["0.5"] == pytest.approx(40.5)
    assert fans["Ohio"]["an"] == {"0": 10.5, "1": 20.5, "2": 30.5, "3": 40.5}


# ---------------------------------------------------------------------------
# The convention is recorded where results.json is written and read back:
# a stored location missing only its last horizon ("4") is not misread as
# canonical (one week off). The "4" guess serves files without the record.
# ---------------------------------------------------------------------------

def _stored_missing_last():
    return {"analogue": {"Ohio": {"1": {"0.5": 14.0}, "2": {"0.5": 15.0},
                                  "3": {"0.5": 16.0}}}}


def test_a_recorded_stored_convention_is_read_not_guessed():
    out = HZ.models_to_canonical(_stored_missing_last(), HZ.STORED)
    assert out["analogue"]["Ohio"] == {"0": {"0.5": 14.0},
                                       "1": {"0.5": 15.0},
                                       "2": {"0.5": 16.0}}
    canon = {"pf": {"Ohio": {h: {"0.5": 1.0} for h in HZ.HORIZONS}}}
    assert HZ.models_to_canonical(canon, HZ.CANONICAL) == canon
    # no record (an older file): the guess, unchanged
    assert HZ.models_to_canonical(_stored_missing_last()) == \
        _stored_missing_last()


def test_home_outlook_reads_the_recorded_convention():
    """A stored results.json whose Ohio lacks "4": the one-week-ahead card
    is stored "1" (canonical "0"), not missing."""
    from app.ui.routes import home as ui_home
    q = {str(lv): 100.0 + 50 * lv for lv in
         (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975, 0.99)}
    res = {"forecast_date": "2098-01-03",
           "horizon_convention": "stored",
           "observed": {"Ohio": [["2097-12-27", 120.0]]},
           "models": {"analogue": {"Ohio": {"1": q, "2": q, "3": q}}}}
    cards, _meta = ui_home._outlook_cards(res, None)
    assert cards["39"].get("probs")
    assert "1-wk median: 125" in cards["39"]["hover_html"]


def test_a_console_run_records_its_convention(pipeline_env):
    """The pipeline's results.json says which convention it holds."""
    import json
    from app.core import runs as R
    _default_run(pipeline_env["names"])
    res = json.loads(next((R.APP_STATE / "workroots").glob(
        "*/results.json")).read_text())
    assert res["horizon_convention"] == "stored"
    assert "4" in res["models"]["analogue"]["Ohio"]
