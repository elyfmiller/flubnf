"""The Oracle SIHRS member: the closed form, eligibility and the identity,
the donor-index draw, and bitwise equality with the registered screen and
the producer's dry run.

Offline tests use small synthetic samples and a hand-built pool. The
record tests read the stored grid (kernel-regularizer/grid/J15), the
pinned hub copy, the producer's dry-run outputs and the screen's per-date
results (all read only) and skip where that tree is not on the machine;
FLUBNF_ORACLE_RECORD names another location for it, FLUBNF_ORACLE_FULL=1
compares every date the screen kept instead of the default six.
"""
import csv
import gzip
import json
import os
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flubnf import oracle as OR                           # noqa: E402
from flubnf import oracle_bank as OB                      # noqa: E402

RECORD = Path(os.environ.get(
    "FLUBNF_ORACLE_RECORD",
    "~/Documents/FluBNF-local/research/groundhog-beta")).expanduser()
OM = RECORD / "oracle_member"
PINNED_HUB = RECORD / "anchor" / "pinned" / "FluSight-forecast-hub"
GRID = RECORD.parent / "kernel-regularizer" / "grid" / "J15"
DRYRUN = OM / "shadow" / "producer" / "dryrun_out"
ARMS = OM / "screen" / "results" / "arms_by_date"
FULL = os.environ.get("FLUBNF_ORACLE_FULL") == "1"

record = pytest.mark.skipif(
    not (GRID.is_dir() and PINNED_HUB.is_dir() and ARMS.is_dir()),
    reason="the registered record is not on this machine")

T = date(2025, 1, 11)


def _pool(n=40, seasons=(2022, 2023), rule=1, G_mid=None):
    rng = np.random.default_rng(7)
    G = np.round(rng.uniform(1.6, 2.8, size=(n, 4)), 5) if G_mid is None else np.asarray(G_mid, float)
    return {"n": n if rule else 0, "rule": rule, "rule_text": "donor" if rule else "identity:test",
            "loc": np.array(["01"] * n, dtype="U2"), "week": np.array(["2023-01-07"] * n, dtype="U10"),
            "season": np.array([seasons[i % len(seasons)] for i in range(n)]),
            "G_origin": np.full(n, 2.2), "G_mid": G, "rho": G / 2.2, "vol24": np.zeros(n, int)}


def _samples(n=500, seed=3, growth=0.1):
    rng = np.random.default_rng(seed)
    x0 = rng.gamma(20.0, 5.0, n)
    xh = [x0 * np.exp(growth * h) * rng.lognormal(0.0, 0.05 * h, n) for h in (1, 2, 3, 4)]
    return x0, xh


# ------------------------------------------------------------- the closed form

def test_own_growth_held_is_the_identity_factor():
    """G_k = G_T for all k gives P_h = h lam_T and F = 1 (section 4.2's check)."""
    x0, xh = _samples()
    c = OR.cell_quantities(x0, xh)
    assert c["eligible"]
    G = np.full((3, 4), c["G_T"])
    F, valid = OR.factors({"lam_T": c["lam_T"], "G_T": c["G_T"], "o": c["o"]}, G)
    assert valid.all()
    P = OR.closed_form_P(np.full(3, c["lam_T"]), G - OR.GAMMA)
    assert np.allclose(P, np.outer(np.ones(3), c["lam_T"] * np.arange(1, 5)))
    assert np.allclose(F, np.exp(P - c["o"][None, :]))
    # w = 1 in the blend is exactly that: the member is the filter's own path
    r = OR.member_for_cell(x0, xh, _pool(), T, "39", w=1.0)
    assert r.active
    # every factor is exp(P_h(own) - o_h): the median path moves by that and
    # nothing else, so the medians of the transformed samples are m_h * F_h
    med = np.array([np.median(a) for a in r.samples])
    assert np.allclose(med, c["m"] * np.exp(P[0] - c["o"]))


def test_lnphi_is_phi_of_the_growth_and_zero_at_zero():
    assert OR.lnphi(0.0) == 0.0
    x = np.array([-1.0, 0.3, 2.0])
    assert np.allclose(OR.lnphi(x), np.log(np.expm1(x) / x))


def test_the_blend_is_geometric_in_G():
    Gd = np.array([[2.0, 2.5, 3.0, 1.5]])
    out = OR.blend(2.2, Gd, 0.5)
    assert np.allclose(out, np.sqrt(2.2 * Gd))
    assert np.allclose(OR.blend(2.2, Gd, 0.0), Gd)
    assert np.allclose(OR.blend(2.2, Gd, 1.0), 2.2)


# ------------------------------------------------- eligibility and identity

def test_cell_quantities_are_finite_only_and_the_median_is_the_half_level():
    x0, xh = _samples()
    xh[1] = np.concatenate([xh[1], [np.nan, np.inf]])
    x0 = np.concatenate([x0, [np.nan]])
    c = OR.cell_quantities(x0, xh)
    assert c["n_total"][1] == 502 and c["n_finite"][1] == 500
    assert c["n0_total"] == 501 and c["n0_finite"] == 500
    assert c["m0"] == np.median(x0[np.isfinite(x0)])
    assert c["m"][1] == np.quantile(xh[1][np.isfinite(xh[1])], 0.5)
    assert c["q_null"].shape == (4, 23)
    assert c["lam_T"] == np.log(c["m"][0] / c["m0"]) and c["G_T"] == OR.GAMMA + c["lam_T"]


def test_a_non_positive_median_or_origin_is_not_eligible():
    x0, xh = _samples()
    r = OR.member_for_cell(np.zeros_like(x0), xh, _pool(), T, "39")
    assert not r.eligible and not r.active
    for s in OR.SEEDS:
        assert np.array_equal(r.q_seed[s], r.q_null)
    xz = list(xh)
    xz[2] = np.zeros_like(xz[2])
    r = OR.member_for_cell(x0, xz, _pool(), T, "39")
    assert not r.eligible
    # a strongly negative own growth still leaves G_T > 0 here (no lam_T
    # guard, S3); G_T <= 0 needs lam_T <= -gamma
    x0b, xhb = _samples(growth=-2.5)
    rb = OR.member_for_cell(x0b, xhb, _pool(), T, "39")
    assert not rb.eligible and rb.G_T <= 0


def test_an_inadmissible_pool_is_the_identity_on_every_cell():
    x0, xh = _samples()
    r = OR.member_for_cell(x0, xh, _pool(rule=0), T, "39")
    assert r.eligible and not r.active
    for s in OR.SEEDS:
        assert np.array_equal(r.q_seed[s], r.q_null)
    for a, b in zip(r.samples, xh):
        assert np.array_equal(a, b)


def test_the_identity_leaves_non_finite_samples_and_the_origin_alone():
    x0, xh = _samples()
    xh[0] = np.concatenate([xh[0], [np.nan]])
    r = OR.member_for_cell(x0, xh, _pool(rule=0), T, "39")
    assert np.isnan(r.samples[0][-1]) and len(r.samples[0]) == 501


# ----------------------------------------------------------- the draw

def test_uniforms_are_keyed_on_seed_season_date_and_fips():
    u = OR.uniforms(OR.SEEDS[0], T, "39", 100)
    assert np.array_equal(u, OR.uniforms(OR.SEEDS[0], T, "39", 100))
    assert not np.array_equal(u, OR.uniforms(OR.SEEDS[1], T, "39", 100))
    assert not np.array_equal(u, OR.uniforms(OR.SEEDS[0], T, "40", 100))
    assert not np.array_equal(u, OR.uniforms(OR.SEEDS[0], date(2025, 1, 18), "39", 100))
    assert OR.season_index(date(2023, 9, 23)) == 0
    assert OR.season_index(date(2025, 6, 14)) == 1
    assert OR.season_index(date(2026, 1, 3)) == 2
    assert OR.season_index(date(2026, 11, 7)) == 3
    # the exact key: numpy's default_rng on [seed, season index, ordinal, FIPS]
    ref = np.random.default_rng([2026091801, 1, T.toordinal(), 39]).random(100)
    assert np.array_equal(u, ref)


def test_the_donor_index_guard_counts_and_clips():
    d, g = OR.donor_index(np.array([0.0, 0.5, 0.999999]), 3)
    assert list(d) == [0, 1, 2] and g == 0
    d, g = OR.donor_index(np.array([1.0]), 3)
    assert list(d) == [2] and g == 1


def test_the_member_is_paired_across_weights_and_transforms_every_block():
    x0, xh = _samples(n=2000)
    pool = _pool()
    r5 = OR.member_for_cell(x0, xh, pool, T, "39", w=0.5)
    r25 = OR.member_for_cell(x0, xh, pool, T, "39", w=0.25)
    assert r5.active and r25.active and r5.abstentions == 0 == r5.guard_hits
    # the same uniforms serve both weights: the same sample meets the same donor
    u = OR.uniforms(OR.SUBMITTED_SEED, T, "39", 2000)
    d, _ = OR.donor_index(u, pool["n"])
    c = OR.cell_quantities(x0, xh)
    cell = {"lam_T": c["lam_T"], "G_T": c["G_T"], "o": c["o"]}
    for w, r in ((0.5, r5), (0.25, r25)):
        F, _ = OR.factors(cell, OR.blend(c["G_T"], pool["G_mid"], w))
        for hi in range(4):
            assert np.array_equal(r.samples[hi], np.asarray(xh[hi]) * F[d][:, hi])
            assert np.array_equal(r.q_seed[OR.SUBMITTED_SEED][hi],
                                  np.quantile(r.samples[hi], OR.QL))
    # five seeds, each its own realisation, the submitted one kept as samples
    assert set(r5.q_seed) == set(OR.SEEDS)
    assert not np.array_equal(r5.q_seed[OR.SEEDS[0]], r5.q_seed[OR.SEEDS[1]])


def test_a_non_positive_donor_stamp_is_an_abstention_for_that_sample():
    x0, xh = _samples(n=300)
    G = _pool()["G_mid"]
    G[5, 2] = -0.5                                          # one bad path
    pool = _pool(G_mid=G)
    r = OR.member_for_cell(x0, xh, pool, T, "39")
    assert r.active
    u = OR.uniforms(OR.SUBMITTED_SEED, T, "39", 300)
    d, _ = OR.donor_index(u, pool["n"])
    hits = int((d == 5).sum())
    assert hits > 0
    # the abstentions count sums over the five seeds; the submitted seed's
    # samples on the bad path are untouched
    assert r.abstentions >= hits
    for hi in range(4):
        assert np.array_equal(r.samples[hi][d == 5], np.asarray(xh[hi])[d == 5])


def test_torn_blocks_raise_rather_than_transform():
    x0, xh = _samples()
    xh[3] = xh[3][:-1]
    with pytest.raises(ValueError, match="differ in length"):
        OR.member_for_cell(x0, xh, _pool(), T, "39")


def test_the_registered_constants():
    assert OR.PREREG_SHA256 == "67c9fa49a195908312f34ca783b21d85377759309df14461f86fbfd54d30c56f"
    assert OR.SEEDS == (2026091801, 2026091802, 2026091803, 2026091804, 2026091805)
    assert OR.SUBMITTED_SEED == 2026091801
    assert OR.W_PRODUCTION == 0.5 and OR.W_SECONDARY == 0.25
    assert OR.GAMMA == 7.0 / 3.2 and len(OR.QL) == 23


# ------------------------------------------------------------- the record

def _name_to_fips() -> dict:
    with open(PINNED_HUB / "auxiliary-data" / "locations.csv", newline="") as fh:
        return {r["location_name"]: r["location"].zfill(2) for r in csv.DictReader(fh)}


def _season_of(asof: str) -> str:
    y, m = int(asof[:4]), int(asof[5:7])
    s = y if m >= 8 else y - 1
    return f"{s}-{(s + 1) % 100:02d}"


def _dates() -> list:
    """(asof, dry-run kept?, npz kept?) for the dates to compare."""
    npz = sorted(p.name[:-4] for p in ARMS.glob("*.npz"))
    dry = sorted(p.name for s in DRYRUN.iterdir() if s.is_dir()
                 for p in (s / "weeks").iterdir() if p.is_dir()) if DRYRUN.is_dir() else []
    if FULL:
        chosen = sorted(set(npz) | set(dry))
    else:
        chosen = sorted(set(dry) | {"2025-01-11", "2026-01-03"})
    return [(d, d in dry, d in npz) for d in chosen]


def _compare_date(asof: str, in_dry: bool, in_npz: bool, pops, n2f) -> dict:
    season = _season_of(asof)
    T_ = date.fromisoformat(asof)
    vf = (PINNED_HUB / "auxiliary-data" / "target-data-archive"
          / f"target-hospital-admissions_{asof}.csv")
    pool = OB.build_pool(asof, vf, pops)["pool"]
    with gzip.open(GRID / season / "weeks" / asof / "samples.json.gz", "rt") as fh:
        S = json.load(fh)
    mq = (json.loads((DRYRUN / season / "weeks" / asof / "member_quantiles.json").read_text())
          if in_dry else None)
    z = np.load(ARMS / f"{asof}.npz", allow_pickle=True) if in_npz else None
    out = {"blocks": 0, "seed_blocks": 0, "diff": 0, "active": 0, "active_agree": True}
    for loc, blk in S["pf"].items():
        fips = n2f[loc]
        x0, xh = blk["0"], [blk[h] for h in ("1", "2", "3", "4")]
        r = OR.member_for_cell(x0, xh, pool, T_, fips, w=OR.W_PRODUCTION)
        r25 = OR.member_for_cell(x0, xh, pool, T_, fips, w=OR.W_SECONDARY)
        out["active"] += int(r.active)
        if mq is not None:
            for s in OR.SEEDS:
                for hi, hh in enumerate("0123"):
                    for name, got in (("LB", r), ("LB25", r25)):
                        ref = np.array(mq["members"][name]["per_seed"][str(s)][fips][hh], float)
                        out["seed_blocks"] += 1
                        out["diff"] += int(not np.array_equal(ref, got.q_seed[s][hi]))
            for hi, hh in enumerate("0123"):
                ref = np.array(mq["members"]["NULL"]["quantiles"][fips][hh]["unrounded"], float)
                out["blocks"] += 1
                out["diff"] += int(not np.array_equal(ref, r.q_null[hi]))
            out["active_agree"] &= (mq["members"]["LB"]["quantiles"][fips]["0"]["active"] == int(r.active))
        if z is not None:
            j = list(z["fips"]).index(fips)
            if "Q__LB" in z:
                for si, s in enumerate(OR.SEEDS):
                    out["seed_blocks"] += 8
                    out["diff"] += int(not np.array_equal(z["Q__LB"][si, j], r.q_seed[s])) * 4
                    out["diff"] += int(not np.array_equal(z["Q__LB25"][si, j], r25.q_seed[s])) * 4
            else:
                # an identity date of the screen (2023-24: one donor season):
                # the donor arms were not stored, the member is the identity
                out["identity_dates"] = True
                out["active_agree"] &= (not r.active) and pool["rule"] == 0
                for s in OR.SEEDS:
                    out["seed_blocks"] += 4
                    out["diff"] += int(not np.array_equal(r.q_seed[s], r.q_null)) * 4
            out["blocks"] += 4
            out["diff"] += int(not np.array_equal(z["sidecar"][j], r.q_null)) * 4
            out["active_agree"] &= (bool(z["eligible"][j]) == r.eligible)
    return out


@record
def test_the_member_is_bitwise_the_dry_run_and_the_screen():
    """LB per seed, LB25 per seed and NULL on every date the producer's dry
    run kept (member_quantiles.json) and every date the screen kept
    (arms_by_date/<T>.npz; the 2023-24 dates are the identity there)."""
    pops = OB.load_populations(PINNED_HUB / "auxiliary-data" / "locations.csv")
    n2f = _name_to_fips()
    dates = _dates()
    assert dates
    total = {"dates": 0, "blocks": 0, "seed_blocks": 0, "diff": 0}
    for asof, in_dry, in_npz in dates:
        if not (GRID / _season_of(asof) / "weeks" / asof / "samples.json.gz").is_file():
            continue
        res = _compare_date(asof, in_dry, in_npz, pops, n2f)
        assert res["diff"] == 0, (asof, res)
        assert res["active_agree"], asof
        total["dates"] += 1
        for k in ("blocks", "seed_blocks", "diff"):
            total[k] += res[k]
    assert total["dates"] >= 3 and total["diff"] == 0
    print(f"\noracle bitwise: {total}")
