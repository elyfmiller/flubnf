"""The shipped donor bank of the Oracle SIHRS (bank change B2): the
FluSurv-NET path half on the Groundhog's shared selection, the shrink, the
identity rule R_EITHER, the label, the mixture draw, and equality with the
registered B2 screen's pools and shrink.

Offline tests use a small synthetic bank and hand-built pools. The record
tests read the B2 screen's files (oracle_member/b2, read only) and the
pinned hub copy, and skip where that tree is not on the machine;
FLUBNF_ORACLE_RECORD names another location for it, FLUBNF_ORACLE_FULL=1
compares all 85 record dates instead of the default six.
"""
import hashlib
import json
import math
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flubnf import analogue as AN                         # noqa: E402
from flubnf import oracle as OR                           # noqa: E402
from flubnf import oracle_bank as OB                      # noqa: E402
from flubnf import oracle_mix as MX                       # noqa: E402

RECORD = Path(os.environ.get(
    "FLUBNF_ORACLE_RECORD",
    "~/Documents/FluBNF-local/research/groundhog-beta")).expanduser()
OM = RECORD / "oracle_member"
B2 = OM / "b2"
PINNED_HUB = RECORD / "anchor" / "pinned" / "FluSight-forecast-hub"
GRID = RECORD.parent / "kernel-regularizer" / "grid" / "J15"
FULL = os.environ.get("FLUBNF_ORACLE_FULL") == "1"

record = pytest.mark.skipif(
    not ((B2 / "aux_pools" / "manifest.json").is_file()
         and (B2 / "calibration_b2.json").is_file() and PINNED_HUB.is_dir()
         and GRID.is_dir()),
    reason="the registered B2 record is not on this machine")


# ------------------------------------------------------------ a synthetic bank

def _saturday(y, m, d):
    x = date(y, m, d)
    while x.weekday() != 5:
        x += timedelta(days=1)
    return x


def _bank(seasons=range(2010, 2016), locs=("aa", "bb", "network_all")):
    """Weekly rates for whole seasons (August to July) with a seasonal bump;
    the first week of every season is missing for "aa" and the aggregate
    (no W-1 cell for the season's first donor week), "bb" is complete."""
    b = {}
    for j, loc in enumerate(locs):
        for s in seasons:
            d = _saturday(s, 8, 1)
            k = 0
            while AN.season_of(d) == s:
                if k > 0 or loc == "bb":
                    b[(loc, d)] = round(0.3 + 4.0 * math.exp(-((k - 24 - j) / 6.0) ** 2), 3)
                d += timedelta(days=7)
                k += 1
    return b


def test_the_pool_is_the_shared_selection_plus_the_eight_week_path():
    bank = _bank()
    grid = MX.Grid(bank)
    ts, e = 2015, 33                  # near the season start: some donors lack W-1
    paths, counts = MX.collect_paths(bank, grid, e, ts)
    _, keys = AN.donor_paths(bank, e, ts, length=6, with_keys=True)
    got = [(p["donor_location"], p["donor_week"]) for p in paths]
    # the pool is the shared selection's six-week cells, in its own order,
    # less the cells without a W-1 cell and the crossings
    assert got == [k for k in keys if k in set(got)]
    assert counts["n_forward6_present"] == len(keys)
    assert counts["n_selected"] == sum(
        1 for _ in AN._donor_cells(bank, e, ts, AN.DEFAULT_BANDWIDTH, False,
                                   AN.resolve_donor_exclusions(AN.EXCLUDED_DONOR_SEASONS)))
    no_prev = [k for k in keys if (k[0], k[1] - timedelta(days=7)) not in bank]
    assert no_prev, "the synthetic bank should have season-first donor weeks"
    assert counts["n_forward6_present"] - counts["n_window8_present"] == len(no_prev)
    assert not set(no_prev) & set(got)
    # every donor season strictly earlier and not excluded, within the bandwidth
    drop = AN.resolve_donor_exclusions(AN.EXCLUDED_DONOR_SEASONS)
    for p in paths:
        assert p["donor_season"] < ts and p["donor_season"] not in drop
        assert AN.calendar_distance(p["donor_epiweek"], e) <= AN.DEFAULT_BANDWIDTH
    # the aggregates are donors, flagged
    assert any(p["is_aggregate"] for p in paths)


def test_the_stamps_are_the_smoother_on_the_rate_series():
    bank = _bank()
    grid = MX.Grid(bank)
    paths, _ = MX.collect_paths(bank, grid, 44, 2015)
    assert paths
    for p in paths[:20]:
        loc, d = p["donor_location"], p["donor_week"]
        win = [bank[(loc, d + timedelta(days=7 * k))] for k in OB.PATH_WEEKS]
        ly = np.log(np.array(win))
        Y = (ly[:-2] + ly[1:-1] + ly[2:]) / 3.0
        assert abs(p["G_origin"] - (OB.GAMMA + Y[1] - Y[0])) < 1e-12
        for k in OB.HORIZONS:
            assert abs(p["G_mid"][k - 1] - (OB.GAMMA + (Y[k + 1] - Y[k - 1]) / 2.0)) < 1e-12


def test_the_season_crossing_rule_removes_paths_into_the_target_season():
    # the bank is a latest-issue snapshot: it holds the target season too
    bank = _bank(seasons=range(2010, 2017))
    grid = MX.Grid(bank)
    # a late-season target: the last donor season's July weeks run into the
    # target season's August
    T = _saturday(2016, 7, 16)
    e = AN.epiweek(T)
    ts = AN.season_of(T)
    with_rule, c1 = MX.collect_paths(bank, grid, e, ts)
    without, c0 = MX.collect_paths(bank, grid, e, ts, crossing_rule=False)
    assert c1["n_crossing"] == c0["n_crossing"] > 0
    assert len(without) - len(with_rule) == c1["n_crossing"]
    for p in with_rule:
        for k in OB.PATH_WEEKS:
            assert AN.season_of(p["donor_week"] + timedelta(days=7 * k)) < ts


def test_rows_round_trip_at_the_table_precision_and_digest(tmp_path):
    bank = _bank()
    grid = MX.Grid(bank)
    paths, counts = MX.collect_paths(bank, grid, 45, 2015)
    assert MX.admissible(counts)
    rows = MX.path_rows("2015-11-07", 45, 2015, paths, "donor")
    pool = MX.pool_from_rows(rows)
    assert pool["n"] == len(paths) and pool["rule"] == 1
    assert np.array_equal(pool["G_mid"], np.array(
        [[float(f"{x:.5f}") for x in p["G_mid"]] for p in paths]))
    week = {"asof": "2015-11-07", "rows": rows, "bank_digest": "0" * 64,
            "target_season": 2015, "target_epiweek": 45, "rule": "donor",
            "admissible": True, "counts": counts, "shrink": 0.9,
            "shrink_prior_seasons": [2014], "n_paths": pool["n"],
            "digest": OB.digest_rows(rows)}
    man = MX.write_pool(week, tmp_path)
    back, man2 = MX.read_pool(tmp_path, "2015-11-07")
    assert man2 == json.loads(json.dumps(man, default=str))
    assert np.array_equal(back["G_mid"], pool["G_mid"])
    # a tampered table is refused
    fp = MX.pool_path(tmp_path, "2015-11-07")
    txt = fp.read_text()
    fp.write_text(txt.replace(rows[0]["G_mid1"], "9.99999", 1))
    with pytest.raises(ValueError, match="does not match"):
        MX.read_pool(tmp_path, "2015-11-07")
    # an inadmissible half is ONE identity row
    idr = MX.path_rows("2015-11-07", 45, 2015, [], MX.IDENTITY_TEXT)
    assert len(idr) == 1 and idr[0]["donor_location"] == "IDENTITY"
    assert MX.pool_from_rows(idr)["rule"] == 0


def test_the_shrink_acts_on_the_log_growth():
    G = np.array([[1.5, 2.1875, 3.0, 2.5]])
    s = 0.9
    assert np.allclose(MX.shrunk(G, s), OB.GAMMA + s * (G - OB.GAMMA))
    assert MX.shrunk(np.array([OB.GAMMA]), 0.5)[0] == OB.GAMMA
    pool = {"n": 1, "rule": 1, "G_mid": G}
    sp = MX.shrunk_pool(pool, s)
    assert np.array_equal(sp["G_mid_raw"], G) and sp["shrink"] == s
    assert np.array_equal(sp["G_mid"], MX.shrunk(G, s))


def test_an_unfittable_shrink_raises():
    adm = {("01", _saturday(2097, 11, 1) + timedelta(days=7 * k)): 50.0 + k for k in range(20)}
    with pytest.raises(ValueError, match="cannot be fitted"):
        MX.fit_shrink(adm, _bank(), _saturday(2098, 1, 3))


def test_the_identity_rule_is_r_either_and_the_label():
    assert MX.resolve_w_aux(True, True) == MX.W_AUX == 0.5
    assert MX.resolve_w_aux(False, True) == 1.0
    assert MX.resolve_w_aux(True, False) == 0.0
    assert MX.resolve_w_aux(False, False) is None
    assert MX.mixture_state(True, True) == "both"
    assert MX.STREAM == "admissions-fbase+flusurv" and MX.IDENTITY_RULE == "R_EITHER"
    assert MX.label("288b139f" + "0" * 56, "06eff6a7" + "1" * 56) == \
        "admissions-fbase@288b139f+flusurv@06eff6a7"


# -------------------------------------------------------------- the draw

T = date(2025, 1, 11)


def _pool(n=40, seed=7, lo=1.6, hi=2.8, rule=1):
    rng = np.random.default_rng(seed)
    G = np.round(rng.uniform(lo, hi, size=(n, 4)), 5)
    return {"n": n if rule else 0, "rule": rule,
            "rule_text": "donor" if rule else "identity:test",
            "G_mid": G if rule else np.zeros((0, 4)), "season": np.full(n if rule else 0, 2022)}


def _samples(n=2000, seed=3, growth=0.1):
    rng = np.random.default_rng(seed)
    x0 = rng.gamma(20.0, 5.0, n)
    xh = [x0 * np.exp(growth * h) * rng.lognormal(0.0, 0.05 * h, n) for h in (1, 2, 3, 4)]
    return x0, xh


def test_the_mixture_keeps_the_admissions_donor_on_half_the_samples():
    x0, xh = _samples()
    adm, aux = _pool(), _pool(n=73, seed=11, lo=1.4, hi=3.2)
    lb = OR.member_for_cell(x0, xh, adm, T, "39")
    gh = OR.member_for_cell(x0, xh, adm, T, "39", aux_pool=aux)
    assert lb.active and gh.active and gh.w_aux == 0.5 and lb.w_aux == 0.0
    u, v = OR.two_uniforms(OR.SUBMITTED_SEED, T, "39", len(x0))
    assert np.array_equal(u, OR.uniforms(OR.SUBMITTED_SEED, T, "39", len(x0)))
    keep = v >= 0.5
    assert gh.n_aux_drawn == int((~keep).sum()) and 0 < gh.n_aux_drawn < len(x0)
    c = OR.cell_quantities(x0, xh)
    cell = {"lam_T": c["lam_T"], "G_T": c["G_T"], "o": c["o"]}
    Fx, _ = OR.factors(cell, OR.blend(c["G_T"], aux["G_mid"], 0.5))
    ix = ((v / 0.5) * aux["n"]).astype(int)
    for hi in range(4):
        # the kept samples are the admissions-only member's, bit for bit
        assert np.array_equal(gh.samples[hi][keep], lb.samples[hi][keep])
        # the others carry the FluSurv-NET path floor((v / w_aux) n_aux)
        assert np.array_equal(gh.samples[hi][~keep], np.asarray(xh[hi])[~keep] * Fx[ix[~keep], hi])


def test_w_aux_zero_is_the_admissions_only_member_bitwise():
    x0, xh = _samples()
    adm, aux = _pool(), _pool(n=73, seed=11)
    lb = OR.member_for_cell(x0, xh, adm, T, "06")
    r0 = OR.member_for_cell(x0, xh, adm, T, "06", aux_pool=aux, w_aux=0.0)
    for s in OR.SEEDS:
        assert np.array_equal(lb.q_seed[s], r0.q_seed[s])
    for a, b in zip(lb.samples, r0.samples):
        assert np.array_equal(a, b)


def test_one_admissible_half_carries_the_whole_draw_and_none_is_the_identity():
    x0, xh = _samples()
    adm_no, aux = _pool(rule=0), _pool(n=73, seed=11)
    r = OR.member_for_cell(x0, xh, adm_no, T, "39", aux_pool=aux)
    assert r.active and r.w_aux == 1.0 and r.n_aux_drawn == len(x0)
    _, v = OR.two_uniforms(OR.SUBMITTED_SEED, T, "39", len(x0))
    c = OR.cell_quantities(x0, xh)
    cell = {"lam_T": c["lam_T"], "G_T": c["G_T"], "o": c["o"]}
    Fx, _ = OR.factors(cell, OR.blend(c["G_T"], aux["G_mid"], 0.5))
    d = (v * aux["n"]).astype(int)
    assert np.array_equal(r.samples[2], np.asarray(xh[2]) * Fx[d, 2])
    r = OR.member_for_cell(x0, xh, _pool(), T, "39", aux_pool=_pool(rule=0))
    assert r.active and r.w_aux == 0.0
    r = OR.member_for_cell(x0, xh, adm_no, T, "39", aux_pool=_pool(rule=0))
    assert not r.active and r.w_aux is None
    for s in OR.SEEDS:
        assert np.array_equal(r.q_seed[s], r.q_null)
    # an explicit w_aux that draws from an inadmissible half is refused
    with pytest.raises(ValueError, match="not admissible"):
        OR.member_for_cell(x0, xh, adm_no, T, "39", aux_pool=aux, w_aux=0.5)


def test_the_mixture_guard_counts_only_the_indices_used():
    rows, sel, ab, g = OR.mixture_rows(
        np.ones((3, 4)), np.ones(3, bool), 2 * np.ones((5, 4)), np.ones(5, bool),
        u=np.array([0.1, 0.9, 0.99]), v=np.array([0.2, 0.7, 0.4999999]), w_aux=0.5,
        n_adm=3, n_aux=5)
    assert list(sel) == [True, False, True] and g == 0 and ab == 0
    assert rows[1, 0] == 1.0 and rows[0, 0] == 2.0


# ------------------------------------------------------------- the record

def _sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@pytest.mark.skipif(not (OM / "PREREG_oracle_member_ADDENDUM_A2.md").is_file(),
                    reason="the registered documents are not on this machine")
def test_the_three_document_hashes_are_the_files():
    assert _sha(OM / "PREREG_oracle_member_FROZEN.md") == OR.PREREG_SHA256
    assert _sha(B2 / "PREREG_b2_FROZEN.md") == OR.B2_SHA256
    assert _sha(OM / "PREREG_oracle_member_ADDENDUM_A2.md") == OR.ADDENDUM_A2_SHA256


def _record_dates() -> list:
    out = []
    for s in ("2023-24", "2024-25", "2025-26"):
        d = GRID / s / "weeks"
        out += sorted(p.name for p in d.iterdir() if p.is_dir()) if d.is_dir() else []
    if FULL:
        return out
    # a FluSurv-NET-only date of 2023-24, an identity date, two window dates,
    # the one admissions-only date, the epiweek-53 date
    return [a for a in ("2023-10-21", "2024-04-13", "2024-12-28", "2025-01-11",
                        "2025-06-14", "2026-01-03") if a in out]


@record
def test_the_flusurv_half_is_the_b2_screens_pool_and_shrink():
    """Every pool of the chosen dates equals the screen's written pool
    (content digest and file bytes, aux_pools/manifest.json), its counts
    calibration_b2.json per_date, and the shrink the 85 per-date values."""
    calib = json.loads((B2 / "calibration_b2.json").read_text())
    man = json.loads((B2 / "aux_pools" / "manifest.json").read_text())
    pops = OB.load_populations(PINNED_HUB / "auxiliary-data" / "locations.csv")
    aux = MX.read_bank()
    assert aux[1]["digest"] == man["bank_digest"]
    dates = _record_dates()
    assert dates
    states = {}
    for asof in dates:
        vf = (PINNED_HUB / "auxiliary-data" / "target-data-archive"
              / f"target-hospital-admissions_{asof}.csv")
        vb = OB.build_vintage(asof, vf, pops)
        wk = MX.build_week(asof, vb.count_bank, aux=aux)
        mp, cp = man["pools"][asof], calib["per_date"][asof]["flusurv_half"]
        assert wk["digest"] == mp["content_digest"], asof
        assert wk["shrink"] == calib["summary"]["shrink_per_date"][asof], asof
        c = wk["counts"]
        assert [c["n_selected"], c["n_forward6_present"], c["n_window8_present"],
                c["n_crossing"], c["n_guard_removed"], c["n_path"]] == \
            [cp["n_selected_by_library_rule"], cp["n_forward6_present"],
             cp["n_window8_present"], cp["n_removed_by_season_crossing_rule"],
             cp["n_removed_by_guards"], cp["n_path"]], asof
        assert wk["admissible"] == (cp["n_path"] >= 30)
        adm_ok = OB.collect_paths(vb).rule == "donor"
        st = MX.mixture_state(adm_ok, wk["admissible"])
        assert st == calib["per_date"][asof]["mixture_R_EITHER"]["state"], asof
        states[st] = states.get(st, 0) + 1
    if FULL:
        assert states == {"both": 52, "flusurv_only": 28, "admissions_only": 1, "identity": 4}
