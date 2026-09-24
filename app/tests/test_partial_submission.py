"""Partial submission files: a defect confined to one location's rows drops
that location, the file is written with the rest and checked again, and
the dropped location and its reason are recorded. A file-level defect, or
no valid location left, still refuses the whole file (app/core/submit.py
write_submission and _hub_gate)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import horizons as hz                          # noqa: E402
from app.core import hubcheck as HC                          # noqa: E402
from app.core import submit as SB                            # noqa: E402

from test_oracle_step import hubfiles                        # noqa: E402,F401
from test_optional_outputs import _default_run, pipeline_env  # noqa: E402,F401

#: a season week: its reference date 2026-10-10 is a FluSight round
ASOF = "2026-10-03"
REF = "2026-10-10"


def _fips() -> list:
    from flubnf.settings import load_locations
    return list(load_locations().location.astype(str).str.zfill(2))


def _rows(fips, seed=3) -> list:
    rng = np.random.default_rng(seed)
    rows = []
    for i, f in enumerate(fips):
        base = 20.0 + i
        s = {h: (base * (1 + 0.1 * int(h))
                 * rng.lognormal(0, 0.3, 300)).tolist() for h in hz.HORIZONS}
        rows += SB.quantile_rows(s, f, ASOF)
    return rows


def _flatten(rows, fips):
    """Every row of one location at one value: a zero-width distribution."""
    return [dict(r, value=7) if r["location"] == fips else r for r in rows]


def test_one_bad_location_is_dropped_and_the_rest_written(tmp_path):
    fips = _fips()
    assert len(fips) == 53
    bad = fips[5]
    dropped = {}
    p = SB.write_submission(_flatten(_rows(fips), bad), "pf", ASOF, tmp_path,
                            dropped=dropped)
    d = pd.read_csv(p, dtype=str)
    assert d.location.nunique() == 52
    assert bad not in set(d.location)
    assert list(dropped) == [bad]
    assert "zero-width" in dropped[bad]
    # the written file passes every check, the round included
    assert not HC.failures(HC.check_file(p), allow_round=False)
    assert p.name == f"{REF}-{SB.hub_model_id('pf')}.csv"


def test_a_location_only_the_hub_checks_catch_is_dropped_too(tmp_path):
    """A defect validate does not look at (a count above the plausibility
    bound) is traced to its location by the hub's own checks."""
    fips = _fips()
    bad = fips[7]
    rows = [dict(r, value=r["value"] + 10**9) if r["location"] == bad else r
            for r in _rows(fips)]
    dropped = {}
    p = SB.write_submission(rows, "analogue", ASOF, tmp_path, dropped=dropped)
    d = pd.read_csv(p, dtype=str)
    assert d.location.nunique() == 52 and bad not in set(d.location)
    assert list(dropped) == [bad]
    assert "population" in dropped[bad]
    assert not HC.failures(HC.check_file(p))


def test_every_location_bad_refuses_the_file(tmp_path):
    fips = _fips()[:3]
    rows = _rows(fips)
    for f in fips:
        rows = _flatten(rows, f)
    dropped = {}
    with pytest.raises(ValueError, match="failed validation"):
        SB.write_submission(rows, "pf", ASOF, tmp_path, dropped=dropped)
    assert not list(tmp_path.rglob("*.csv"))
    assert not list(tmp_path.rglob("*.tmp"))
    assert dropped == {}


def test_every_location_failing_the_hub_checks_refuses_the_file(tmp_path):
    rows = [dict(r, value=r["value"] + 10**9) for r in _rows(_fips()[:4])]
    with pytest.raises(ValueError, match="hub's checks"):
        SB.write_submission(rows, "pf", ASOF, tmp_path)
    assert not list(tmp_path.rglob("*.csv"))


def test_a_file_level_defect_still_refuses_the_whole_file(tmp_path):
    fips = _fips()
    # mixed reference dates: two as-ofs in one file
    rows = _rows(fips[:10]) + SB.quantile_rows(
        {h: list(np.linspace(5, 50, 200)) for h in hz.HORIZONS}, fips[20],
        "2026-09-26")
    with pytest.raises(ValueError, match="disagree"):
        SB.write_submission(rows, "pf", ASOF, tmp_path)
    # a reference date that is not a Saturday (a Friday as-of)
    with pytest.raises(ValueError, match="not a Saturday"):
        SB.write_submission(
            [r for f in fips[:5] for r in SB.quantile_rows(
                {h: list(np.linspace(5, 50, 200)) for h in hz.HORIZONS},
                f, "2026-10-02")], "pf", "2026-10-02", tmp_path)
    # and a defect in one location does not rescue a file-level one
    with pytest.raises(ValueError, match="disagree"):
        SB.write_submission(_flatten(rows, fips[3]), "pf", ASOF, tmp_path)
    assert not list(tmp_path.rglob("*.csv"))


def test_a_file_level_hub_check_is_never_split(tmp_path):
    """_hub_gate refuses a name defect outright: no location is dropped
    for it."""
    rows = _rows(_fips()[:3])
    tmp = tmp_path / "f.csv"
    pd.DataFrame(rows).to_csv(tmp, index=False, lineterminator="\n")
    with pytest.raises(ValueError, match="file_location"):
        SB._hub_gate(tmp, f"{REF}-{SB.hub_model_id('pf')}.csv",
                     "NAU_PyBNF-GroundHogCGR", hub_named=True)


def test_a_clean_file_is_written_as_before(tmp_path):
    """No defect: nothing dropped, every row written in order."""
    fips = _fips()
    rows = _rows(fips)
    dropped = {}
    p = SB.write_submission(rows, "pf", ASOF, tmp_path, dropped=dropped)
    assert dropped == {}
    want = pd.DataFrame(rows).to_csv(index=False, lineterminator="\n")
    assert p.read_text() == want


def test_the_run_records_the_dropped_location(pipeline_env, monkeypatch):
    """Through the pipeline: the dropped location is named in the run
    outcome, by location name, under its file; the run and the other file
    are unaffected."""
    real = SB.write_submission

    def _corrupt(rows, model, *a, **k):
        rows = list(rows)
        if model == "pf":
            f = rows[0]["location"]
            rows = _flatten(rows, f)
        return real(rows, model, *a, **k)
    monkeypatch.setattr(SB, "write_submission", _corrupt)
    names = pipeline_env["names"]
    _spec, out = _default_run(names)
    assert not out.get("submission_errors"), out
    drops = out["submission_dropped"]
    assert list(drops) == [SB.hub_model_id("pf")]
    (name, why), = drops[SB.hub_model_id("pf")].items()
    assert name in names and "zero-width" in why
    d = pd.read_csv(out["submissions"][SB.hub_model_id("pf")], dtype=str)
    assert d.location.nunique() == 3
    json.dumps(out)
