"""The admissions growth-path bank: the rule, the identity, the written pool
and its digest, and byte identity with the registered record.

Offline tests build a tiny synthetic vintage. The record tests read the
lab's pinned hub copy and the bank of the registered screen
(research/groundhog-beta, read only) and skip where that tree is not on
the machine; FLUBNF_ORACLE_RECORD names another location for it.
"""
import csv
import io
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flubnf import analogue as AN                         # noqa: E402
from flubnf import oracle_bank as OB                      # noqa: E402

RECORD = Path(os.environ.get(
    "FLUBNF_ORACLE_RECORD",
    "~/Documents/FluBNF-local/research/groundhog-beta")).expanduser()
PINNED_HUB = RECORD / "anchor" / "pinned" / "FluSight-forecast-hub"
FBASE = RECORD / "stage0" / "bank" / "data" / "paths_fbase"

record = pytest.mark.skipif(
    not (FBASE.is_dir() and PINNED_HUB.is_dir()),
    reason="the registered record (research/groundhog-beta) is not on this machine")


# ---------------------------------------------------------------- synthetic

def _saturdays(first: date, last: date) -> list:
    d = first
    while d.weekday() != 5:
        d += timedelta(days=1)
    out = []
    while d <= last:
        out.append(d)
        d += timedelta(days=7)
    return out


def _vintage(tmp_path, asof="2025-01-11", locs=("01", "02", "03", "04"),
             first=date(2022, 8, 1), tweak=None) -> Path:
    """A smooth positive series per location, weekly from `first` to the
    as-of date, values well above the floor. `tweak(loc, d, v)` may
    replace a value."""
    T = date.fromisoformat(asof)
    fp = tmp_path / f"target-hospital-admissions_{asof}.csv"
    with open(fp, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["date", "location", "location_name", "value"])
        for i, d in enumerate(_saturdays(first, T)):
            for j, loc in enumerate(locs):
                v = 60.0 + 40.0 * np.sin(2 * np.pi * (i + 7 * j) / 52.0) + 5 * j
                if tweak is not None:
                    v = tweak(loc, d, v)
                w.writerow([d.isoformat(), loc, f"loc{loc}", "" if v is None else v])
    return fp


POPS = {"01": 5e6, "02": 7e5, "03": 2e6, "04": 3e7}


def test_the_constants_are_the_registered_ones():
    assert OB.GAMMA == 7.0 / 3.2
    assert OB.COUNT_FLOOR == 10.0
    assert OB.BASE_WEEKS == (-1, 0, 1, 2) and OB.PATH_WEEKS == tuple(range(-1, 7))
    assert OB.MIN_DONOR_SEASONS == 2 and OB.SMOOTHER_ID == "c3log"
    assert OB.STREAM == "admissions-fbase"
    # the donor rule is the library's, by reference
    rb = OB.rule_block()
    assert rb["bandwidth"] == AN.DEFAULT_BANDWIDTH == 2
    assert rb["min_donors"] == AN.MIN_DONORS == 30
    assert rb["excluded_donor_seasons"] == sorted(AN.EXCLUDED_DONOR_SEASONS)
    assert rb["floor_weeks"] == [-1, 0, 1, 2] and rb["name"] == "FBASE"


def test_two_donor_seasons_give_a_donor_pool_from_the_library_selection(tmp_path):
    fp = _vintage(tmp_path)
    r = OB.build_pool("2025-01-11", fp, POPS)
    dp = r["paths"]
    assert dp.rule == "donor" and dp.reason == "ok"
    assert set(dp.n_by_season) == {2022, 2023}            # strictly earlier seasons
    assert dp.counts["n_path"] >= AN.MIN_DONORS
    # every donor is a library donor: same season and calendar tests
    for p in dp.donors:
        assert AN.season_of(p.week) < AN.season_of(date(2025, 1, 11))
        assert AN.calendar_distance(AN.epiweek(p.week), AN.epiweek(date(2025, 1, 11))) <= 2
        assert p.G_origin > 0 and np.isfinite(p.G_mid).all()
    pool = r["pool"]
    assert pool["rule"] == 1 and pool["n"] == len(dp.donors)
    assert pool["G_mid"].shape == (pool["n"], 4)
    assert r["label"].startswith("admissions-fbase@") and len(r["label"]) == len("admissions-fbase@") + 8


def test_one_donor_season_is_the_identity_rule(tmp_path):
    fp = _vintage(tmp_path, asof="2024-01-13", first=date(2022, 8, 1))
    r = OB.build_pool("2024-01-13", fp, POPS)
    dp = r["paths"]
    assert dp.rule == "identity" and dp.reason == "fewer_than_two_donor_seasons"
    assert dp.donors == [] and dp.diagnostic            # eligible donors kept apart
    assert np.array_equal(dp.rho_matrix(), np.ones((1, 4)))
    assert r["pool"]["rule"] == 0 and r["pool"]["n"] == 0
    rows = OB.path_rows(dp)
    assert len(rows) == 1 and rows[0][4] == "IDENTITY" and rows[0][3].startswith("identity:")


def test_the_fbase_floor_reads_the_origin_window_only(tmp_path):
    """A count below 10 in W+3..W+6 keeps the path under FBASE and drops it
    under the eight-week rule; a count below 10 in W-1..W+2 drops it under
    both. The difference is the registered bank change B1. The low week
    sits at epiweek 5 of 2023-24, so the January donors of the as-of
    (epiweek 2, bandwidth 2) read it at W+1 to W+4."""
    LOW = date(2024, 2, 3)
    low = {("02", LOW): 4.0}

    def tweak(loc, d, v):
        return low.get((loc, d), v)
    fp = _vintage(tmp_path, tweak=tweak)
    vb = OB.build_vintage("2025-01-11", fp, POPS)
    base = OB.collect_paths(vb)                          # FBASE (default)
    eight = OB.collect_paths(vb, floor_weeks=OB.PATH_WEEKS)
    assert base.counts["floor_weeks"] == list(OB.BASE_WEEKS)
    keys_b = {(p.location, p.week) for p in base.donors}
    keys_e = {(p.location, p.week) for p in eight.donors}
    assert keys_e < keys_b                               # eight-week is stricter
    # the paths FBASE keeps and the eight-week rule drops read the low week
    # only at W+3..W+6
    dropped = keys_b - keys_e
    assert dropped
    for loc, w in dropped:
        k = (LOW - w).days // 7
        assert loc == "02" and 3 <= k <= 6
    # a path whose origin window holds the low week is gone under both
    for loc, w in keys_b:
        if loc == "02":
            assert not (-1 <= (LOW - w).days // 7 <= 2)
    # and such a path exists in the selection (it was dropped by the floor,
    # not absent from the calendar window)
    assert base.counts["n_window_present"] > base.counts["n_base_floor_only"]


def test_the_season_crossing_rule_keeps_the_target_season_out(tmp_path):
    """A June as-of: a late-June donor's W+6 would be an August row of the
    target season and is dropped; the canary (every target-season row times
    10) then changes no path."""
    asof = "2025-06-14"
    fp = _vintage(tmp_path, asof=asof)
    vb = OB.build_vintage(asof, fp, POPS)
    dp = OB.collect_paths(vb)
    assert dp.counts["n_dropped_season_crossing"] > 0
    T = date.fromisoformat(asof)
    for p in dp.diagnostic:
        for k in OB.PATH_WEEKS:
            assert AN.season_of(p.week + timedelta(days=7 * k)) < AN.season_of(T)
    raw10 = {k: (v * 10 if AN.season_of(k[1]) >= AN.season_of(T) else v)
             for k, v in vb.raw.items()}
    vb10 = OB.build_vintage(asof, fp, POPS, raw_override=raw10)
    dp10 = OB.collect_paths(vb10)
    assert OB.path_rows(dp10) == OB.path_rows(dp)


def test_a_vintage_whose_newest_row_is_not_the_asof_is_refused(tmp_path):
    fp = _vintage(tmp_path, asof="2025-01-04")
    with pytest.raises(ValueError, match="newest row"):
        OB.build_vintage("2025-01-11", fp, POPS)


def test_rows_dated_after_the_asof_never_enter(tmp_path):
    """A file holding rows after the as-of date (a later pull) is read the
    Groundhog's way: truncated at T, the same-day row kept."""
    fp = _vintage(tmp_path, asof="2025-01-18")
    rows = OB.load_rows(fp, date(2025, 1, 11))
    assert max(r.date for r in rows) == date(2025, 1, 11)
    vb = OB.build_vintage("2025-01-11", fp, POPS)
    assert vb.newest_row_date() == date(2025, 1, 11)
    assert all(d <= date(2025, 1, 11) for (_, d) in vb.raw)
    assert set(vb.y_T()) == {"01", "02", "03", "04"}


# ------------------------------------------------ the written pool, verified

def test_write_then_read_round_trips_and_the_digest_is_over_content(tmp_path):
    fp = _vintage(tmp_path)
    r = OB.build_pool("2025-01-11", fp, POPS, out_dir=tmp_path / "bank",
                      built_utc="2026-01-01T00:00:00+00:00")
    man = r["manifest"]
    assert man["stream"] == "admissions-fbase" and man["layout_version"] == 1
    assert man["cells"] == r["paths"].counts["n_path"] == len(r["paths"].donors)
    assert man["source_sha256"] == OB.sha256_file(fp)
    assert man["rule"]["name"] == "FBASE" and man["pool_rule"] == "donor"
    assert (tmp_path / "bank" / "paths_2025-01-11.csv").is_file()
    assert (tmp_path / "bank" / "paths_2025-01-11.manifest.json").is_file()
    pool, man2 = OB.read_pool(tmp_path / "bank", "2025-01-11")
    assert man2 == man
    assert pool["n"] == r["pool"]["n"]
    assert np.array_equal(pool["G_mid"], r["pool"]["G_mid"])   # bit for bit
    assert np.array_equal(pool["G_origin"], r["pool"]["G_origin"])
    assert OB.label(man) == f"admissions-fbase@{man['digest'][:8]}"
    # the digest ignores the bookkeeping columns and the row order
    rows = OB.read_path_rows(tmp_path / "bank" / "paths_2025-01-11.csv")
    shuffled = list(reversed(rows))
    for x in shuffled:
        x["touches_voluntary_2024"] = "9"
    assert OB.digest_rows(shuffled) == man["digest"]
    rows[0]["G_mid2"] = "9.99999"
    assert OB.digest_rows(rows) != man["digest"]


def test_a_pool_that_does_not_match_its_manifest_is_refused(tmp_path):
    fp = _vintage(tmp_path)
    OB.build_pool("2025-01-11", fp, POPS, out_dir=tmp_path / "bank", built_utc="x")
    p = tmp_path / "bank" / "paths_2025-01-11.csv"
    lines = p.read_text().splitlines()
    cells = lines[1].split(",")
    cells[12] = "9.99999"                                  # G_mid1 of the first donor
    lines[1] = ",".join(cells)
    p.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="does not match its manifest"):
        OB.read_pool(tmp_path / "bank", "2025-01-11")
    (tmp_path / "bank" / "paths_2025-01-11.manifest.json").unlink()
    with pytest.raises(FileNotFoundError, match="no manifest"):
        OB.read_pool(tmp_path / "bank", "2025-01-11")


def test_an_identity_pool_writes_and_reads_as_the_identity(tmp_path):
    fp = _vintage(tmp_path, asof="2024-01-13")
    r = OB.build_pool("2024-01-13", fp, POPS, out_dir=tmp_path / "bank", built_utc="x")
    assert r["manifest"]["pool_rule"] == "identity" and r["manifest"]["cells"] == 0
    pool, man = OB.read_pool(tmp_path / "bank", "2024-01-13")
    assert pool["rule"] == 0 and pool["n"] == 0
    assert pool["rule_text"] == "identity:fewer_than_two_donor_seasons"


# -------------------------------------------------------------- the record

def _rebuilt_bytes(dp, diagnostic=False) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(OB.PATH_COLUMNS)
    for row in OB.path_rows(dp, diagnostic=diagnostic):
        w.writerow(row)
    return buf.getvalue().encode()


@record
def test_every_recorded_pool_is_rebuilt_byte_for_byte_from_the_pinned_vintage():
    """The registered bank (stage0/bank/data/paths_fbase, built 2026-09-22
    by the B1 collector from the pinned hub) against this module: every
    paths_<T>.csv, and every diagnostic file of the identity dates."""
    pops = OB.load_populations(PINNED_HUB / "auxiliary-data" / "locations.csv")
    files = sorted(FBASE.glob("paths_*.csv"))
    assert len(files) >= 3
    n_equal = n_diag = 0
    for f in files:
        asof = f.name[len("paths_"):-4]
        vf = (PINNED_HUB / "auxiliary-data" / "target-data-archive"
              / f"target-hospital-admissions_{asof}.csv")
        r = OB.build_pool(asof, vf, pops)
        assert _rebuilt_bytes(r["paths"]) == f.read_bytes(), asof
        n_equal += 1
        dg = FBASE / "diagnostic" / f"diag_{asof}.csv"
        if dg.is_file():
            assert r["paths"].rule == "identity", asof
            assert _rebuilt_bytes(r["paths"], diagnostic=True) == dg.read_bytes(), asof
            n_diag += 1
    assert n_equal == len(files)
    # the manifest of the bank as built lists the same files
    man = json.loads((FBASE / "manifest_fbase.json").read_text())
    assert man, "manifest_fbase.json is empty"


@record
def test_a_written_pool_of_a_recorded_date_verifies_and_carries_the_vintage_hash(tmp_path):
    pops = OB.load_populations(PINNED_HUB / "auxiliary-data" / "locations.csv")
    asof = "2025-01-11"
    vf = (PINNED_HUB / "auxiliary-data" / "target-data-archive"
          / f"target-hospital-admissions_{asof}.csv")
    r = OB.build_pool(asof, vf, pops, out_dir=tmp_path, built_utc="x")
    assert (tmp_path / f"paths_{asof}.csv").read_bytes() == (FBASE / f"paths_{asof}.csv").read_bytes()
    pool, man = OB.read_pool(tmp_path, asof)
    assert man["source_sha256"] == OB.sha256_file(vf)
    assert pool["n"] == 467 and man["cells"] == 467      # the record's count for the date
    assert np.array_equal(pool["G_mid"], r["pool"]["G_mid"])
