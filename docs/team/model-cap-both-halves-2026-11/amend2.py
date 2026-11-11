"""Amendment 2 (AMENDMENT2.txt beside this file): the cap's level on the
Oracle SIHRS's own October rounds, 2026-10-10, 10-17 and 10-24 (the last
before the cap), as submitted, with the Groundhog's same rounds as the
reference. Post hoc, no engine: the submitted hub rows, then the shrink at
10x and 15x on the three-week mean (R3) or the larger of it and the last
week (RX), scored under FluSight's cell rule.
  amend2.py --check    build every arm and run the code check (reads no truth)
  amend2.py --score    score every arm and print the report
Run from the repository root (PYTHONPATH=.), with FLUBNF_HUB this lane's hub
clone at a73013aa and CAP_ROOT the research folder (results/amend2/ out)."""
import math, sys
from datetime import timedelta
import numpy as np, pandas as pd
import both as BO
from app.core import groundhog as gh, scoring, data as D
from flubnf import tailcap as TC

ROUNDS = ["2026-10-10", "2026-10-17", "2026-10-24"]
MEMBERS = {"Oracle": "NAU_PyBNF-OracleSIHRS", "Groundhog": "NAU_PyBNF-GroundHogCGR"}
ARMS = ["N", "S10-R3", "S10-RX", "S15-R3", "S15-RX"]
SEED = 20261111
OUT = BO.RES / "amend2"
KEY = ["member", "asof", "fips", "horizon"]


def asof_of(rnd):
    """The data week a round was run on: its reference date less 7 days
    (canonical horizon h targets asof + 7(h+1), the hub's horizon h)."""
    return str((pd.Timestamp(rnd) - timedelta(days=7)).date())


def hub_rows(member, rnd):
    t = pd.read_csv(D.HUB / "model-output" / MEMBERS[member] / f"{rnd}-{MEMBERS[member]}.csv",
                    dtype={"location": str, "output_type_id": str})
    t = t[(t.target == TC.TARGET) & (t.output_type == "quantile") & (t.location != "US")]
    rows = [{"target": r.target, "output_type": r.output_type, "location": r.location.zfill(2),
             "horizon": int(r.horizon), "output_type_id": r.output_type_id, "value": float(r.value)}
            for r in t.itertuples()]
    return rows


def round_arms(member, rnd):
    """{arm: {(fips, h): block}} and the round's limits and level record."""
    asof = asof_of(rnd)
    obs = BO.obs_by_fips(asof)
    rows = hub_rows(member, rnd)
    B0 = BO.blocks(rows)
    fips = sorted({f for f, _ in B0})
    lv = {f: BO.levels(obs.get(f, [])) for f in fips}
    A, lims = {"N": B0}, {}
    for n in (10, 15):
        for V in ("R3", "RX"):
            lim = {f: (n * lv[f][V] if math.isfinite(lv[f][V]) and lv[f][V] > 0 else float("nan")) for f in fips}
            A[f"S{n}-{V}"] = BO.blocks(TC.cap_rows(rows, lim, mode="shrink")[0])
            lims[f"{n}-{V}"] = lim
    return A, {"asof": asof, "levels": lv, "lims": lims}


def check(A, rec):
    """(i) the shrink as written (BO.k_written over every horizon in the file,
    rounded and monotone); (ii) median kept, monotone, whole where moved;
    (iii) the RX limit never below the R3 limit."""
    bad = []
    B0 = A["N"]
    fips = sorted({f for f, _ in B0})
    by_loc = {f: {h: b for (g, h), b in B0.items() if g == f} for f in fips}
    for tag in ("10-R3", "10-RX", "15-R3", "15-RX"):
        lim, S = rec["lims"][tag], A[f"S{tag}"]
        for f in fips:
            kw = BO.k_written(by_loc[f], lim[f])
            for h, b in by_loc[f].items():
                m, want = b[0.5], dict(b)
                if math.isfinite(lim[f]) and kw < 1 and m > 0:
                    for L, v in b.items():
                        if L > 0.5 and v > 0: want[L] = m * (v / m) ** kw
                if BO.round_monotone(want, b) != S[(f, h)]: bad.append(("i", tag, f, h))
                x, levs = S[(f, h)], sorted(b)
                if x[0.5] != b[0.5]: bad.append(("ii median", tag, f, h))
                if any(x[a] > x[c] for a, c in zip(levs, levs[1:])): bad.append(("ii monotone", tag, f, h))
                if any(x[L] != b[L] and float(x[L]) != int(x[L]) for L in levs): bad.append(("ii whole", tag, f, h))
    for n in (10, 15):
        for f in fips:
            a, b = rec["lims"][f"{n}-R3"][f], rec["lims"][f"{n}-RX"][f]
            if math.isfinite(a) and not (b >= a): bad.append(("iii", n, f, a, b))
    return bad


def build():
    out, defects, info = {}, [], []
    for member in MEMBERS:
        for rnd in ROUNDS:
            A, rec = round_arms(member, rnd)
            defects += [(member, rnd) + d for d in check(A, rec)]
            lv = rec["levels"]
            n_up = sum(1 for f in lv if math.isfinite(lv[f]["RX"]) and lv[f]["RX"] > lv[f]["R3"])
            touched = {a: sum(1 for k, b in A[a].items() if b != A["N"][k]) for a in ARMS[1:]}
            info.append((member, rnd, rec["asof"], len({f for f, _ in A["N"]}), n_up, touched))
            out[(member, rnd)] = (A, rec)
    return out, defects, info


def main_check():
    _, defects, info = build()
    for member, rnd, asof, nloc, n_up, touched in info:
        print(f"{member} {rnd} (data {asof}): {nloc} states, larger above mean in {n_up}; blocks changed {touched}")
    print(f"defects: {len(defects)}")
    for d in defects[:20]: print(d)


def main_score():
    built, defects, info = build()
    truth, _ = scoring.load_truth()
    CC, VV = {a: [] for a in ARMS}, {a: [] for a in ARMS}
    for (member, rnd), (A, rec) in built.items():
        asof = rec["asof"]
        for a in ARMS:
            q = BO.to_q({k: b for k, b in A[a].items() if 0 <= k[1] <= 3})
            c, v = gh.score_week(q, asof, BO.n2f, truth)
            if not c.empty: CC[a].append(c.assign(member=member, asof=asof, round=rnd))
            if not v.empty: VV[a].append(v.assign(member=member, asof=asof, round=rnd))
    CC = {a: pd.concat(x, ignore_index=True) for a, x in CC.items()}
    VV = {a: pd.concat(x, ignore_index=True) for a, x in VV.items()}
    for a in ARMS:
        CC[a]["fips"] = CC[a]["fips"].astype(str); VV[a]["fips"] = VV[a]["fips"].astype(str)
    # the cells both members have, so the members are compared on the same cells
    keys = [set(map(tuple, CC[a][CC[a].member == m][["asof", "fips", "horizon"]].to_numpy().tolist()))
            for a in ARMS for m in MEMBERS]
    common = set.intersection(*keys)
    for a in ARMS:
        k = list(zip(CC[a]["asof"], CC[a].fips, CC[a].horizon))
        CC[a] = CC[a][[x in common for x in k]].copy()
        V = VV[a][VV[a].scored.astype(bool)]
        kv = list(zip(V["asof"], V.fips, V.horizon))
        VV[a] = V[[x in common for x in kv]].copy()
    OUT.mkdir(parents=True, exist_ok=True)
    for a in ARMS:
        CC[a].to_csv(OUT / f"cells_{a}.csv.gz", index=False)
        VV[a].to_csv(OUT / f"coverage_{a}.csv.gz", index=False)
    print(f"defects: {len(defects)}; common cells per member: {len(common)}")
    for member, rnd, asof, nloc, n_up, touched in info:
        print(f"  {member} {rnd}: {nloc} states, larger above mean in {n_up}; blocks changed {touched}")
    rel, lrel = BO.rel, BO.lrel
    # score_week labels the bands "50" and "95" (strings; both.py read them back from csv as numbers)
    cov = lambda V, b: float(V[V.band.astype(str) == str(b)].hit.mean())
    print("\nBY MEMBER (states, rounds 10-10, 10-17, 10-24; truth through 10-31): relWIS, log, cov50, cov95, by round")
    for m in MEMBERS:
        rows = []
        for a in ARMS:
            C, V = CC[a][CC[a].member == m], VV[a][VV[a].member == m]
            r = {"arm": a, "relWIS": rel(C), "log": lrel(C), "cov50": cov(V, 50), "cov95": cov(V, 95)}
            r.update({rnd: rel(C[C["round"] == rnd]) for rnd in ROUNDS})
            rows.append(r)
        print(f"{m}:\n" + pd.DataFrame(rows).set_index("arm").round(4).to_string())
    print(f"\nCONSISTENCY WITH SUBMISSION'S 2026-11-04 TABLE (S10-R3 / S15-R3): Oracle 0.646 / 0.670, Groundhog 0.631 / 0.669")
    for m in MEMBERS:
        print(f"  {m}: {rel(CC['S10-R3'][CC['S10-R3'].member == m]):.4f} / {rel(CC['S15-R3'][CC['S15-R3'].member == m]):.4f}")

    def diff_table(A_, B_):
        M = CC[A_][KEY + ["wis", "base_wis", "log_wis", "base_log_wis"]].merge(
            CC[B_][KEY + ["wis", "log_wis"]], on=KEY, suffixes=("_a", "_b"))
        return M
    rng = np.random.default_rng(SEED)
    states = sorted({f for (_, f, _) in common})
    idx = [rng.integers(0, len(states), len(states)) for _ in range(2000)]
    print(f"\nLOCATION-CLUSTER BOOTSTRAP, 2,000 resamples of the {len(states)} states, default_rng({SEED}) "
          "(difference in relWIS, first arm less second; negative = first better)")
    res = {}
    for n in (10, 15):
        M = diff_table(f"S{n}-RX", f"S{n}-R3")
        per = {}
        for m in MEMBERS:
            X = M[M.member == m].groupby("fips")[["wis_a", "wis_b", "base_wis", "log_wis_a", "log_wis_b", "base_log_wis"]].sum()
            per[m] = X.reindex(states).fillna(0.0)
        d = lambda X: (X.wis_a.sum() - X.wis_b.sum()) / X.base_wis.sum()
        dl = lambda X: (X.log_wis_a.sum() - X.log_wis_b.sum()) / X.base_log_wis.sum()
        est = {m: d(per[m]) for m in MEMBERS}
        estl = {m: dl(per[m]) for m in MEMBERS}
        con = est["Oracle"] - est["Groundhog"]
        bs = {m: [] for m in MEMBERS}; bc = []
        arrs = {m: per[m].to_numpy() for m in MEMBERS}
        for I in idx:
            v = {}
            for m in MEMBERS:
                P = arrs[m][I]
                v[m] = (P[:, 0].sum() - P[:, 1].sum()) / P[:, 2].sum()
                bs[m].append(v[m])
            bc.append(v["Oracle"] - v["Groundhog"])
        ci = lambda x: (float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5)))
        for m in MEMBERS:
            lo, hi = ci(bs[m])
            print(f"  {n}x {m}: S{n}-RX - S{n}-R3 {est[m]:+.4f} [{lo:+.4f}, {hi:+.4f}]; log {estl[m]:+.4f}")
        lo, hi = ci(bc)
        print(f"  {n}x contrast D (Oracle's difference less the Groundhog's): {con:+.4f} [{lo:+.4f}, {hi:+.4f}]")
        res[n] = (est, estl, con, lo, hi)
    est, estl, con, lo, hi = res[10]
    print("\nTHE RULE (AMENDMENT2.txt), 10x:")
    r1 = est["Oracle"] > 0.005
    r2 = con > 0.010 and lo > 0
    r3 = len(defects) == 0
    print(f"  (r1) Oracle S10-RX - S10-R3 > +0.005: {est['Oracle']:+.4f} -> {r1}")
    print(f"  (r2) D > +0.010 with its interval above 0: {con:+.4f} [{lo:+.4f}, {hi:+.4f}] -> {r2}")
    print(f"  (r3) no code-check defect: {len(defects)} -> {r3}")
    if not r3:
        print("  -> the code check failed: no advice from this amendment")
    elif r1 and r2:
        print("  -> ADVISE larger_groundhog: the Oracle stays on the mean")
    else:
        print("  -> NO CONCRETE REASON AGAINST larger FOR BOTH MEMBERS")
    print("\nPREDICTIONS:")
    print(f"  P1 S10-RX - S10-R3 >= 0 for both members: Oracle {est['Oracle']:+.4f}, Groundhog {est['Groundhog']:+.4f}"
          f" -> {'holds' if min(est.values()) >= 0 else 'fails'}")
    print(f"  P2 |D| <= 0.010 at 10x: {con:+.4f} -> {'holds' if abs(con) <= 0.010 else 'fails'}")
    c95 = {m: (cov(VV['S10-RX'][VV['S10-RX'].member == m], 95), cov(VV['S10-R3'][VV['S10-R3'].member == m], 95)) for m in MEMBERS}
    print(f"  P3 cov95 S10-RX >= S10-R3 for both: " + ", ".join(f"{m} {a:.3f} vs {b:.3f}" for m, (a, b) in c95.items())
          + f" -> {'holds' if all(a >= b for a, b in c95.values()) else 'fails'}")
    ups = [(x[4], x[3]) for x in info if x[0] == "Oracle"]
    share = sum(u for u, _ in ups) / sum(t for _, t in ups)
    print(f"  (known before the freeze, not a prediction) larger above the mean in {share:.1%} of the Oracle's state-rounds")


if __name__ == "__main__":
    {"--check": main_check, "--score": main_score}[sys.argv[1]]()
