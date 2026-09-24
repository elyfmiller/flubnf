"""The FluSight CSV writers carry the frozen join: reference = as-of + 7,
hub horizon 0..3 = canonical samples "0".."3", and the anchor (hz.ORIGIN)
never reaches a row. Same formula scripts/anchor_analysis.py validated."""
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import horizons as hz  # noqa: E402
from app.core.submit import quantile_rows, rows_from_quantiles  # noqa: E402


ASOF = "2025-12-13"          # a Saturday as-of; submission is due Wed 12-17

#: Canonical shape: forecasts under "0".."3" plus the anchor under
#: hz.ORIGIN; values scale with PHYSICAL weeks ahead ("0" is one week on).
SAMPLES = {h: [10.0 * (int(h) + 1), 12.0 * (int(h) + 1), 14.0 * (int(h) + 1)]
           for h in hz.HORIZONS}
#: the last observed week: carried, never submitted, and far from every
#: forecast value so a row built from it would be obvious
SAMPLES[hz.ORIGIN] = [98.0, 99.0, 100.0]
QDICTS = {h: {0.5: 10.0 * (int(h) + 1)} for h in hz.HORIZONS}


def test_reference_is_asof_plus_seven_matching_anchor_analysis():
    ref = (pd.Timestamp(ASOF) + timedelta(days=7)).date().isoformat()
    rows = quantile_rows(SAMPLES, "06", ASOF)
    assert rows and all(r["reference_date"] == ref == "2025-12-20"
                        for r in rows)


def test_target_end_dates_walk_the_four_target_weeks():
    rows = quantile_rows(SAMPLES, "06", ASOF)
    by_h = {r["horizon"]: r["target_end_date"] for r in rows}
    assert by_h == {0: "2025-12-20", 1: "2025-12-27",
                    2: "2026-01-03", 3: "2026-01-10"}


def test_horizon_zero_carries_the_first_forecast_not_the_anchor():
    """Hub horizon 0 is the FIRST FORECAST week (canonical "0"), never the
    anchor, which would shift every row a week early."""
    rows = [r for r in quantile_rows(SAMPLES, "06", ASOF)
            if r["horizon"] == 0 and r["output_type_id"] == 0.5]
    assert rows[0]["value"] == 12.0          # median of canonical "0"
    # and the anchor's own values reached no row at all
    assert not [r for r in quantile_rows(SAMPLES, "06", ASOF)
                if r["value"] in (98, 99, 100)]


def test_quantile_native_writer_same_join():
    rows = rows_from_quantiles(QDICTS, "06", ASOF)
    assert all(r["reference_date"] == "2025-12-20" for r in rows)
    by_h = {r["horizon"]: (r["target_end_date"], r["value"]) for r in rows}
    assert by_h[0] == ("2025-12-20", 10.0)
    assert by_h[3] == ("2026-01-10", 40.0)


# ---------------------------------------------------- hub value precision

def test_values_are_whole_admissions_like_the_official_files():
    """Values are whole admissions, like the official 'wk inc flu hosp'
    files (raw numpy quantiles leaked 17-digit tails)."""
    tailed = {h: [10.1234567890123 * (int(h) + 1) + i * 0.337
                  for i in range(40)] for h in hz.HORIZONS}
    rows = quantile_rows(tailed, "06", ASOF)
    assert rows
    for r in rows:
        assert isinstance(r["value"], int), r
    qd = {h: {0.25: 9.700000000000001 * (int(h) + 1),
              0.5: 10.1 * (int(h) + 1),
              0.75: 11.499999999999998 * (int(h) + 1)} for h in hz.HORIZONS}
    for r in rows_from_quantiles(qd, "06", ASOF):
        assert isinstance(r["value"], int), r


def test_rounding_preserves_quantile_monotonicity():
    """Round, then enforce non-decreasing: near-ties stay monotone."""
    from app.core.submit import QUANTILES, _hub_values
    raw = [10.0 + 0.04 * i for i in range(len(QUANTILES))]   # 10.0 .. 10.88
    v = _hub_values(raw)
    assert all(b >= a for a, b in zip(v, v[1:]))
    # a deliberately jittered near-tie stays monotone too
    raw2 = [5.49, 5.51, 5.49999, 5.5001, 6.49, 6.51]
    v2 = _hub_values(raw2)
    assert all(b >= a for a, b in zip(v2, v2[1:]))
    assert all(float(x).is_integer() for x in v2)


def test_csv_writes_integers_not_float_tails(tmp_path):
    """On disk: '12', never '12.0' or a float tail."""
    from app.core.submit import write_submission
    samples = {h: [3.3 * (int(h) + 1) + i * 1.7 for i in range(50)]
               for h in hz.HORIZONS}
    rows = quantile_rows(samples, "06", ASOF)
    p = write_submission(rows, "pf", ASOF, tmp_path)
    text = p.read_text()
    lines = text.strip().splitlines()
    vals = [ln.rsplit(",", 1)[1] for ln in lines[1:]]
    assert vals
    for v in vals:
        assert "." not in v, v                       # whole counts only
        int(v)                                       # and parseable as such


# ------------------------------------------ the file name is the row's date

def test_filename_carries_the_reference_date_not_the_asof(tmp_path):
    """The file name carries the rows' reference_date, not the as-of: the
    hub's round-id check (t0_colname: reference_date) compares them."""
    from app.core import submit
    from app.core.submit import write_submission
    rows = quantile_rows(SAMPLES, "06", ASOF)
    p = write_submission(rows, "pf", ASOF, tmp_path)
    assert p.name.startswith("2025-12-20-")          # not 2025-12-13
    stamped = {r["reference_date"] for r in rows}
    assert stamped == {p.name.split(f"-{submit.TEAM_ABBR}-")[0]}


def test_a_name_that_disagrees_with_the_rows_is_refused(tmp_path):
    """Rows and name disagree: refuse instead of emitting a bounced file."""
    import pytest
    from app.core.submit import write_submission
    rows = quantile_rows(SAMPLES, "06", ASOF)        # rows say 2025-12-20
    with pytest.raises(ValueError, match="disagree"):
        write_submission(rows, "pf", "2025-12-20", tmp_path)   # name 12-27
    # and nothing was written before the refusal
    assert not list(tmp_path.rglob("*.csv"))


def test_rows_from_two_asofs_in_one_file_are_refused(tmp_path):
    """A file carries exactly one reference date."""
    import pytest
    from app.core.submit import write_submission
    rows = (quantile_rows(SAMPLES, "06", ASOF)
            + quantile_rows(SAMPLES, "39", "2025-12-20"))
    with pytest.raises(ValueError, match="disagree"):
        write_submission(rows, "pf", ASOF, tmp_path)


# ------------------------------------------- hub identity, from the metadata

def test_identifiers_match_the_registered_model_metadata():
    """MODEL_ABBR/TEAM_ABBR agree with model-metadata/ (not packaged, so
    this test is the drift guard); file stem is <team>-<model>."""
    import yaml
    from app.core.submit import MODEL_ABBR, TEAM_ABBR, hub_model_id
    root = Path(__file__).resolve().parents[2] / "model-metadata"
    files = sorted(root.glob("*.yml"))
    assert files, "no model metadata registered"
    registered = {}
    for f in files:
        meta = yaml.safe_load(f.read_text())
        assert meta["team_abbr"] == TEAM_ABBR, f.name
        registered[meta["model_abbr"]] = f
        # <team_abbr>-<model_abbr>.yml, the name the hub requires
        assert f.stem == f'{meta["team_abbr"]}-{meta["model_abbr"]}', f.name
    from app.core.submit import RETIRED_ABBR
    # every key the writer produces is a registered card, every card is
    # either produced or explicitly retired, and nothing is both
    assert set(MODEL_ABBR.values()) | set(RETIRED_ABBR) == set(registered), (
        "app/core/submit.MODEL_ABBR + RETIRED_ABBR and model-metadata/ "
        "disagree")
    assert not set(MODEL_ABBR.values()) & set(RETIRED_ABBR)
    for key, abbr in MODEL_ABBR.items():
        assert hub_model_id(key) == registered[abbr].stem
    # the blend's key is gone: no call site can write a CModel_Flu file
    import pytest
    with pytest.raises(ValueError, match="unregistered model"):
        hub_model_id("ensemble")


def test_an_unregistered_model_key_is_refused(tmp_path):
    """No call site may invent a name the hub has never seen."""
    import pytest
    from app.core.submit import write_submission
    rows = quantile_rows(SAMPLES, "06", ASOF)
    with pytest.raises(ValueError, match="unregistered model"):
        write_submission(rows, "PF-SIHRS", ASOF, tmp_path)


# ------------------------------- completeness: all 23 hub levels, or nothing

#: results.json's five display quantiles (of the hub's 23)
FIVE = (0.1, 0.25, 0.5, 0.75, 0.9)


def test_a_partial_quantile_set_is_refused(tmp_path):
    """hub-config/tasks.json requires all 23 quantile levels, so a partial
    set is refused structurally rather than written as a submittable file."""
    import pytest
    from app.core.submit import write_submission
    qs = {h: {q: 10.0 * (int(h) + 1) + 100.0 * q for q in FIVE}
          for h in hz.HORIZONS}
    rows = rows_from_quantiles(qs, "06", ASOF)
    assert len(rows) == 5 * len(hz.HORIZONS)         # the shape that got through
    with pytest.raises(ValueError, match="incomplete quantile set"):
        write_submission(rows, "ensemble", ASOF, tmp_path)
    assert not list(tmp_path.rglob("*.csv"))         # and nothing was written


def test_the_refusal_names_the_missing_levels():
    """A defect report a person can act on: how many levels, and which."""
    from app.core.submit import QUANTILES, validate
    keep = [q for q in QUANTILES if q not in (0.01, 0.99)]
    rows = [{"location": "06", "horizon": 0, "output_type": "quantile",
             "output_type_id": q, "value": 10.0 + i}
            for i, q in enumerate(keep)]
    said = [p for p in validate(pd.DataFrame(rows)) if "incomplete" in p]
    assert said, "a 21-level cell must be reported"
    assert "21 of 23" in said[0] and "0.01" in said[0] and "0.99" in said[0]


def test_a_full_set_from_samples_passes_completeness(tmp_path):
    """A full sample-path set passes; a dropped horizon is fine (horizon is
    optional in tasks.json)."""
    from app.core.submit import validate, write_submission
    assert not validate(pd.DataFrame(quantile_rows(SAMPLES, "06", ASOF)))
    three = {h: v for h, v in SAMPLES.items() if h != hz.HORIZONS[-1]}
    rows = quantile_rows(three, "06", ASOF)
    assert {r["horizon"] for r in rows} == {0, 1, 2}
    assert write_submission(rows, "pf", ASOF, tmp_path).is_file()


# --------------------------------------- the CSV lands whole, or not at all

def test_the_csv_lands_atomically_with_no_temp_residue(tmp_path,
                                                       monkeypatch):
    """write_submission writes beside and replaces: a failure at any stage
    leaves nothing under the hub name and no .tmp residue."""
    import pytest
    from app.core.submit import write_submission
    rows = quantile_rows(SAMPLES, "06", ASOF)
    p = write_submission(rows, "pf", ASOF, tmp_path / "ok")
    assert p.is_file()
    assert not list((tmp_path / "ok").rglob("*.tmp"))
    assert len(pd.read_csv(p)) == len(rows)          # every row arrived

    # to_csv dies mid-write (ENOSPC): neither the truncated temp nor a
    # hub-named file survives
    def _truncating(self, path, *a, **k):
        Path(path).write_text("reference_date,target\n2025-12-20")
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(pd.DataFrame, "to_csv", _truncating)
    with pytest.raises(OSError):
        write_submission(rows, "pf", ASOF, tmp_path / "died")
    left = [q for q in (tmp_path / "died").rglob("*") if q.is_file()]
    assert left == []
