"""The FluSight CSV writers carry the frozen join: reference = as-of + 7,
hub horizon 0..3 = internal samples "1".."4". This is the same formula
scripts/anchor_analysis.py validated against three seasons of scoring; the
writers computing anything else mislabels a real submission by a week."""
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.submit import quantile_rows, rows_from_quantiles  # noqa: E402


ASOF = "2025-12-13"          # a Saturday as-of; submission is due Wed 12-17
SAMPLES = {str(h): [10.0 * h, 12.0 * h, 14.0 * h] for h in (1, 2, 3, 4)}
QDICTS = {str(h): {0.5: 10.0 * h} for h in (1, 2, 3, 4)}


def test_reference_is_asof_plus_seven_matching_anchor_analysis():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    ref = (pd.Timestamp(ASOF) + timedelta(days=7)).date().isoformat()
    rows = quantile_rows(SAMPLES, "06", ASOF)
    assert rows and all(r["reference_date"] == ref == "2025-12-20"
                        for r in rows)


def test_target_end_dates_walk_the_four_target_weeks():
    rows = quantile_rows(SAMPLES, "06", ASOF)
    by_h = {r["horizon"]: r["target_end_date"] for r in rows}
    assert by_h == {0: "2025-12-20", 1: "2025-12-27",
                    2: "2026-01-03", 3: "2026-01-10"}


def test_horizon_zero_carries_internal_sample_one():
    rows = [r for r in quantile_rows(SAMPLES, "06", ASOF)
            if r["horizon"] == 0 and r["output_type_id"] == 0.5]
    assert rows[0]["value"] == 12.0          # median of samples "1"


def test_quantile_native_writer_same_join():
    rows = rows_from_quantiles(QDICTS, "06", ASOF)
    assert all(r["reference_date"] == "2025-12-20" for r in rows)
    by_h = {r["horizon"]: (r["target_end_date"], r["value"]) for r in rows}
    assert by_h[0] == ("2025-12-20", 10.0)
    assert by_h[3] == ("2026-01-10", 40.0)


# ---------------------------------------------------- hub value precision

def test_values_are_whole_admissions_like_the_official_files():
    """Measured in the hub clone (2026-08-21): every official
    FluSight-baseline and FluSight-ensemble 'wk inc flu hosp' quantile
    value from 2025 on is an integer count -- the long float tails in
    recent official files belong to the 'wk inc flu prop ed visits'
    proportion target. Our writers match that precision; the raw numpy
    quantiles were leaking 17-digit tails into the CSVs."""
    tailed = {str(h): [10.1234567890123 * h + i * 0.337 for i in range(40)]
              for h in (1, 2, 3, 4)}
    rows = quantile_rows(tailed, "06", ASOF)
    assert rows
    for r in rows:
        assert isinstance(r["value"], int), r
    qd = {str(h): {0.25: 9.700000000000001 * h, 0.5: 10.1 * h,
                   0.75: 11.499999999999998 * h} for h in (1, 2, 3, 4)}
    for r in rows_from_quantiles(qd, "06", ASOF):
        assert isinstance(r["value"], int), r


def test_rounding_preserves_quantile_monotonicity():
    """The guard: round, then enforce non-decreasing. A vector whose raw
    values are monotone but sit within one count of each other must come
    out monotone (never decreasing) after rounding."""
    import numpy as np
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
    """End to end through write_submission: the file on disk carries '12',
    never '12.0' and never a 17-digit tail."""
    from app.core.submit import write_submission
    samples = {str(h): [3.3 * h + i * 1.7 for i in range(50)]
               for h in (1, 2, 3, 4)}
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
    """The submission-blocking bug, pinned. A real run on 2026-08-26 wrote
    `2026-01-03-...csv` whose every row said reference_date 2026-01-10,
    because the rows were built from the as-of plus seven while the name
    came from the bare as-of. hub-config/validations.yml sets t0_colname:
    "reference_date", so the hub's round-id check compares the name against
    that column and would have rejected the file."""
    from app.core import submit
    from app.core.submit import write_submission
    rows = quantile_rows(SAMPLES, "06", ASOF)
    p = write_submission(rows, "pf", ASOF, tmp_path)
    assert p.name.startswith("2025-12-20-")          # not 2025-12-13
    stamped = {r["reference_date"] for r in rows}
    assert stamped == {p.name.split(f"-{submit.TEAM_ABBR}-")[0]}


def test_a_name_that_disagrees_with_the_rows_is_refused(tmp_path):
    """The loud check. Rows built from one as-of, file written for another:
    the writer must refuse rather than emit a file the hub will bounce."""
    import pytest
    from app.core.submit import write_submission
    rows = quantile_rows(SAMPLES, "06", ASOF)        # rows say 2025-12-20
    with pytest.raises(ValueError, match="disagree"):
        write_submission(rows, "pf", "2025-12-20", tmp_path)   # name 12-27
    # and nothing was written before the refusal
    assert not list(tmp_path.rglob("*.csv"))


def test_rows_from_two_asofs_in_one_file_are_refused(tmp_path):
    """A file carries exactly one reference date. Mixed rows are a defect
    the hub would catch; catch it here."""
    import pytest
    from app.core.submit import write_submission
    rows = (quantile_rows(SAMPLES, "06", ASOF)
            + quantile_rows(SAMPLES, "39", "2025-12-20"))
    with pytest.raises(ValueError, match="disagree"):
        write_submission(rows, "pf", ASOF, tmp_path)


# ------------------------------------------- hub identity, from the metadata

def test_identifiers_match_the_registered_model_metadata():
    """MODEL_ABBR and TEAM_ABBR are the only copy of the hub identity in
    Python; model-metadata/ is the registered copy. model-metadata/ is not
    packaged (pyproject includes only flubnf* and app*), so the constants
    cannot read the YAML at run time -- this test is the drift guard
    instead. The hub layout is model-output/<team>-<model>/, and the
    directory name must equal the metadata file's own name."""
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
    assert set(MODEL_ABBR.values()) == set(registered), (
        "app/core/submit.MODEL_ABBR and model-metadata/ disagree")
    for key, abbr in MODEL_ABBR.items():
        assert hub_model_id(key) == registered[abbr].stem


def test_an_unregistered_model_key_is_refused(tmp_path):
    """No call site may invent a name the hub has never seen."""
    import pytest
    from app.core.submit import write_submission
    rows = quantile_rows(SAMPLES, "06", ASOF)
    with pytest.raises(ValueError, match="unregistered model"):
        write_submission(rows, "PF-SIHRS", ASOF, tmp_path)


# ------------------------------- completeness: all 23 hub levels, or nothing

#: the shape the re-blend path fed the writer: results.json's display
#: quantiles, five of the hub's twenty-three
FIVE = (0.1, 0.25, 0.5, 0.75, 0.9)


def test_a_partial_quantile_set_is_refused(tmp_path):
    """hub-config/tasks.json marks the quantile `output_type_id` REQUIRED at
    all 23 levels, so a file carrying five is rejected on submission. The
    writer once took such rows without a murmur and produced a 20-row CSV
    in a directory indistinguishable from a real submission. Deleting the
    caller fixed that day's behaviour; this makes the requirement
    structural, so the next caller cannot reopen it."""
    import pytest
    from app.core.submit import write_submission
    qs = {str(h): {q: 10.0 * h + 100.0 * q for q in FIVE} for h in (1, 2, 3, 4)}
    rows = rows_from_quantiles(qs, "06", ASOF)
    assert len(rows) == 5 * 4                        # the shape that got through
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
    """The rule must not fire on the real thing. The sample path writes all
    23 levels for every horizon it carries, and horizons themselves are
    NOT a completeness rule (tasks.json marks horizon optional), so a run
    that dropped one horizon still writes a valid file."""
    from app.core.submit import validate, write_submission
    assert not validate(pd.DataFrame(quantile_rows(SAMPLES, "06", ASOF)))
    three = {h: v for h, v in SAMPLES.items() if h != "4"}
    rows = quantile_rows(three, "06", ASOF)
    assert {r["horizon"] for r in rows} == {0, 1, 2}
    assert write_submission(rows, "pf", ASOF, tmp_path).is_file()
