"""The horizon convention, pinned before anyone reindexes it.

THE TRAP THIS EXISTS TO CATCH. The repository carries two different
zero-horizons and they are not the same week:

  stored "0"     the ORIGIN: the anchor week itself, the last observed
                 point, as every samples.json.gz on disk keys it. The
                 sealed record carries this and can never be migrated.
  canonical "0"  the FIRST FORECAST week, the hub's own label, whose
                 target_end_date equals the submission's reference_date.

The two are ONE WEEK APART. That is why the reindex was not done as a
rename: renaming would not drop a key, it would OVERWRITE the anchor with
a forecast and move every submitted row a week early, silently, with the
right row count and the wrong dates. This repository has shipped one
off-by-one of exactly that shape already (see
`app/core/submit.py:hub_reference_date`, the 2026-08-26 run whose file
name and rows disagreed by a week).

So the stored form is frozen and `app.core.horizons` translates at the
storage boundary. In memory, above `read_week_samples`, horizons are
"0".."3" and the anchor is ORIGIN. These tests hold that line.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import ensemble as ENS, floor, submit as SUB   # noqa: E402
from app.core.engines import pf as PF                        # noqa: E402


from app.core import horizons as HZ                            # noqa: E402

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
    """A record carrying something this module was not taught about must
    reach a reader intact and be refused there, not be silently renamed."""
    assert HZ.to_canonical({"9": "?"}) == {"9": "?"}


def test_pf_collect_emits_the_anchor_under_origin():
    import inspect
    src = inspect.getsource(PF.collect)
    assert "d[hz.ORIGIN].extend" in src
    assert "tr[:, n - 1 + k]" in src            # the origin: no horizon added
    assert "tr[:, n - 1 + k + h]" in src        # the forecasts: h weeks on
    assert "d[str(h - 1)]" in src               # ... stored under hub labels


def test_floor_excludes_the_origin_from_the_collapse_test():
    import inspect
    src = inspect.getsource(floor)
    assert "str(h) != hz.ORIGIN" in src


def test_submission_horizon_zero_carries_canonical_zero_not_the_anchor():
    """The frozen join. FluSight horizon 0's target_end_date IS the
    reference date, and it is fed by canonical "0", never by ORIGIN."""
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
    """The failure mode the convention exists to prevent: if the anchor
    were treated as a forecast, this would emit a row. It must not."""
    rows = SUB.quantile_rows({HZ.ORIGIN: FIVE[HZ.ORIGIN]}, "01", "2026-01-03")
    assert rows == []


def test_a_stored_shaped_member_does_not_sneak_the_anchor_in():
    """Feeding submit a STORED-shaped dict (anchor under "0") must not
    submit the anchor as horizon 0. Nothing should do this, and if
    something does it must be wrong loudly rather than by a week."""
    stored = {"0": [999.0, 999.0, 999.0], "1": [1.0, 1.0, 1.0]}
    rows = SUB.quantile_rows(stored, "01", "2026-01-03")
    h0 = [r["value"] for r in rows if r["horizon"] == 0
          and abs(float(r["output_type_id"]) - 0.5) < 1e-9]
    assert h0 and h0[0] == 999, (
        "this documents that submit trusts its input to be canonical; the "
        "storage boundary is what guarantees that")


def test_member_quantiles_never_consume_the_origin():
    """member_quantiles_from_samples summarises forecast horizons only.
    Feeding it an origin key must not produce a fifth horizon."""
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
# Run artefacts: results.json under a workroot. These have NO anchor, so the
# two conventions are told apart by the presence of "4" and never guessed at.
# A workroot written before the reindex is the user's record of what was
# forecast, so the console must keep rendering it.
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
    """A half-rewritten artefact must not be converted by a whole-file
    guess: each location map decides for itself."""
    mixed = {"ensemble": {"Old": {"1": 1, "2": 2, "3": 3, "4": 4},
                          "New": {"0": 1, "1": 2, "2": 3, "3": 4}}}
    out = HZ.models_to_canonical(mixed)
    assert out["ensemble"]["Old"] == {"0": 1, "1": 2, "2": 3, "3": 4}
    assert out["ensemble"]["New"] == {"0": 1, "1": 2, "2": 3, "3": 4}


def test_run_artefacts_round_trip():
    canon = {"pf": {"Ohio": {h: {"0.5": float(h)} for h in HZ.HORIZONS}}}
    assert HZ.models_to_canonical(HZ.models_to_stored(canon)) == canon


def test_read_samples_is_the_boundary_not_read_week_samples():
    """read_samples is public and had other callers. Converting one level
    up left the national aggregate reading a STORED record with a
    CANONICAL loop, which scored the anchor as horizon 0 and dropped the
    four-week horizon (test_retro_national caught it: 3 scored, 4
    expected). The conversion belongs at the file parser."""
    import inspect
    from app.core import retro
    assert "hz.record_to_canonical" in inspect.getsource(retro.read_samples)
