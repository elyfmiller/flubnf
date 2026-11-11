"""Amendment 1 (AMENDMENT1.txt, sha256 c8db37b6...): the lower half balanced
in admissions (BN), on Part 1's stored Groundhog forecasts, beside Part 1's
arms (both.py, whose results this reads).
  amend1.py --season <s>   build, check and score the BN arms for one season
  amend1.py --report       BN against S and B, the predictions, the rule
Same environment as both.py."""
import gzip, importlib.util, json, math, sys
from datetime import timedelta
from pathlib import Path
import numpy as np, pandas as pd

_spec = importlib.util.spec_from_file_location("both", Path(__file__).with_name("both.py"))
B = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(B)
TC, gh, SUB, scoring = B.TC, B.gh, B.SUB, B.scoring
BN_ARMS = [f"BN{n}-{v}" for n in B.NS for v in ("R3", "RX")]


def k_balance_natural(loc_blocks, k):
    """kN: min over horizons of e_h = ln(m/t) / ln(m/q2.5), t = 2m - q97.5'
    with q97.5' = m (q97.5/m)^k, where m > 0, q2.5 > 0 and q2.5 < t < m;
    1 when k = 1. Also returns the count of horizons left alone for a 2.5%
    quantile of 0 that would otherwise have qualified."""
    if k >= 1:
        return 1.0, 0
    e, zeros = [1.0], 0
    for b in loc_blocks.values():
        m, lo, hi = b.get(0.5), b.get(0.025), b.get(0.975)
        if None in (m, lo, hi) or not (m > 0) or hi <= m:
            continue
        top = m * (hi / m) ** k
        t = 2 * m - top
        if not (t < m):
            continue
        if lo <= 0:
            zeros += int(t > 0)
            continue
        if lo < t:
            e.append(math.log(m / t) / math.log(m / lo))
    return min(e), zeros


def week_bn(qw, asof):
    obs = B.obs_by_fips(asof)
    rows = []
    for loc, hq in qw.items():
        f = B.n2f.get(loc)
        if f: rows += SUB.rows_from_quantiles({h: {float(L): float(v) for L, v in lv.items()} for h, lv in hq.items()}, f, asof)
    B0 = B.blocks(rows)
    fips = sorted({f for f, _ in B0})
    by_loc = {f: {h: b for (g, h), b in B0.items() if g == f} for f in fips}
    lv = {f: B.levels(obs.get(f, [])) for f in fips}
    A, rec, bad = {"N": B0}, {}, []
    for n in B.NS:
        for V in ("R3", "RX"):
            lim = {f: (n * lv[f][V] if math.isfinite(lv[f][V]) and lv[f][V] > 0 else float("nan")) for f in fips}
            S = B.blocks(TC.cap_rows(rows, lim, mode="shrink")[0])
            k = {f: min([1.0] + [TC.exponent_needed(b, lim[f]) for b in by_loc[f].values()]) for f in fips}
            kz = {f: k_balance_natural(by_loc[f], k[f]) for f in fips}
            X = {}
            for (f, h), b in B0.items():
                X[(f, h)] = TC.whole_block(B.power(B.power(b, k[f], lower=False, upper=True), kz[f][0]), b)
            A[f"S{n}-{V}"], A[f"BN{n}-{V}"] = S, X
            rec[f"{n}-{V}"] = {"kN": {f: kz[f][0] for f in fips}, "k": k, "zeros": sum(z for _, z in kz.values())}
            # the code check: Part 1's (i)-(iii), (v) through both.check_week's rules, and (vi), (vii)
            for key, b in B0.items():
                x = X[key]; levs = sorted(b); f, h = key
                if x[0.5] != b[0.5]: bad.append(("ii median", n, V, key))
                if any(x[a] > x[c] for a, c in zip(levs, levs[1:])): bad.append(("ii monotone", n, V, key))
                if any(x[L] != b[L] and float(x[L]) != int(x[L]) for L in levs): bad.append(("ii whole", n, V, key))
                if any(x[L] != S[key][L] for L in levs if L > 0.5): bad.append(("vii upper", n, V, key))
                if kz[f][0] >= 1 and any(x[L] != b[L] for L in levs if L < 0.5): bad.append(("v BN", n, V, key))
                if kz[f][0] < 1:
                    m, lo0, hi0 = b[0.5], b[0.025], b[0.975]
                    if m > 0 and lo0 > 0 and hi0 > m:
                        t = 2 * m - m * (hi0 / m) ** k[f]
                        if lo0 < t < m and not (x[0.025] >= t - 1 - 1e-9): bad.append(("vi BN floor", n, V, key, x[0.025], t))
    return A, rec, bad


def run_season(season):
    F = json.load(gzip.open(B.REPLAY / season / "forecasts.json.gz"))["forecasts"]
    truth, _ = scoring.load_truth()
    out = {a: ([], []) for a in BN_ARMS}
    touch, recs, defects, zeros = [], {}, [], 0
    for asof, qw in F.items():
        A, rec, bad = week_bn(qw, asof)
        defects += [(asof,) + d for d in bad]
        recs[asof] = {t: r["kN"] for t, r in rec.items()}
        zeros += sum(r["zeros"] for r in rec.values())
        B0 = A["N"]
        for a in BN_ARMS:
            for (f, h), b in A[a].items():
                b0 = B0[(f, h)]
                touch.append((season, asof, a, f, h, any(b[L] != b0[L] for L in b0 if L < 0.5), any(b[L] != b0[L] for L in b0 if L > 0.5)))
        T = pd.Timestamp(asof)
        for a in BN_ARMS:
            q = B.to_q(A[a])
            c, v = gh.score_week(q, asof, B.n2f, truth)
            if not c.empty:
                c = c.copy(); c["asof"] = asof
                lo, hi, lean = [], [], []
                for r in c.itertuples():
                    y = truth.get((str(r.fips), T + timedelta(days=7 * (int(r.horizon) + 1))))
                    bb = q[B.f2n[str(r.fips)]][str(int(r.horizon))]
                    lo.append(int(y < bb[0.025])); hi.append(int(y > bb[0.975]))
                    w_up = bb[0.975] - bb[0.5]
                    lean.append((bb[0.5] - bb[0.025]) / w_up if w_up > 0 else float("nan"))
                c["below"], c["above"], c["lean"] = lo, hi, lean
                out[a][0].append(c)
            if not v.empty: v = v.copy(); v["asof"] = asof; out[a][1].append(v)
    d = B.RES / season
    for a, (cs, vs) in out.items():
        pd.concat(cs).assign(season=season).to_csv(d / f"cells_{a}.csv.gz", index=False)
        pd.concat(vs).assign(season=season).to_csv(d / f"coverage_{a}.csv.gz", index=False)
    pd.DataFrame(touch, columns=["season", "asof", "arm", "fips", "horizon", "lower", "upper"]).to_csv(d / "touched_BN.csv.gz", index=False)
    json.dump({"weeks": recs, "defects": defects, "zero_horizons_left_alone": zeros}, open(d / "record_BN.json", "w"), default=str)
    print(f"{season}: {len(F)} weeks, {len(defects)} defects, {zeros} horizon-blocks left alone for a 2.5% quantile of 0", flush=True)


def report():
    arms = ["N"] + [f"{m}{n}-{v}" for m in ("S", "B") for n in B.NS for v in ("R3", "RX")] + BN_ARMS
    CC, VV = {}, {}
    for a in arms:
        cs, vs = [], []
        for s in B.SEAS:
            c = pd.read_csv(B.RES / s / f"cells_{a}.csv.gz", dtype={"fips": str}); c["season"] = s
            v = pd.read_csv(B.RES / s / f"coverage_{a}.csv.gz", dtype={"fips": str}); v["season"] = s
            cs.append(c[c.fips != "US"]); vs.append(v[v.scored.astype(bool) & (v.fips != "US")])
        CC[a], VV[a] = pd.concat(cs, ignore_index=True), pd.concat(vs, ignore_index=True)
    print("state cells per arm:", sorted({len(C) for C in CC.values()}))
    early = set()
    for s in B.SEAS:
        early |= {(s, w) for w in sorted(CC["N"][CC["N"].season == s]["asof"].unique())[:8]}
    for a in CC:
        for X in (CC[a], VV[a]):
            X["mo"] = X["asof"].map(B.month)
            X["early"] = [(s, w) in early for s, w in zip(X.season, X["asof"])]
            X["csw"] = X["asof"].map(lambda x: any(lo <= str(x) <= hi for lo, hi in B.CSW))
    cov = lambda V, b: float(V[V.band == b].hit.mean())
    subsets = {"pooled": lambda X: X, "EARLY": lambda X: X[X.early], "CSW": lambda X: X[X.csw],
               "Sep-Oct": lambda X: X[X.mo == "Sep-Oct"], "Nov": lambda X: X[X.mo == "Nov"], "Dec+": lambda X: X[X.mo == "Dec+"]}
    T = {}
    for name, sub in subsets.items():
        rows = []
        for a in arms:
            C, V = sub(CC[a]), sub(VV[a])
            r = {"arm": a, "relWIS": B.rel(C), "log": B.lrel(C), "cov50": cov(V, 50), "cov95": cov(V, 95),
                 "below2.5": C.below.mean(), "above97.5": C.above.mean(), "h0lean": C[C.horizon == 0].lean.dropna().median()}
            if name == "pooled": r.update({s: B.rel(C[C.season == s]) for s in B.SEAS})
            rows.append(r)
        T[name] = pd.DataFrame(rows).set_index("arm")
        print(f"\n{name.upper()} (states): relWIS, log, coverage 50 / 95, truth below 2.5% / above 97.5%, h0 lean (below over above)"
              + (", by season" if name == "pooled" else ""))
        print(T[name].round(4).to_string())

    def boot(A_, B_, sub=None, R=2000):
        M = CC[A_][B.KEY + ["wis", "base_wis", "early", "csw"]].merge(CC[B_][B.KEY + ["wis"]], on=B.KEY, suffixes=("_a", "_b"))
        if sub == "EARLY": M = M[M.early]
        if sub == "CSW": M = M[M.csw]
        W = M.groupby(["season", "asof"]).agg(a=("wis_a", "sum"), b=("wis_b", "sum"), base=("base_wis", "sum")).reset_index()
        est = (W.a.sum() - W.b.sum()) / W.base.sum()
        rng = np.random.default_rng(B.SEED)
        G = [W[W.season == s][["a", "b", "base"]].to_numpy() for s in B.SEAS if (W.season == s).any()]
        bs = []
        for _ in range(R):
            P = np.vstack([x[rng.integers(0, len(x), len(x))] for x in G])
            bs.append((P[:, 0].sum() - P[:, 1].sum()) / P[:, 2].sum())
        return est, float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))
    pairs = [(f"BN{n}-{v}", f"S{n}-{v}") for n in B.NS for v in ("R3", "RX")] + \
            [(f"BN{n}-{v}", f"S{n}-R3") for n in B.NS for v in ("R3", "RX")] + \
            [(f"BN{n}-{v}", f"B{n}-{v}") for n in B.NS for v in ("R3", "RX")]
    pairs = list(dict.fromkeys(pairs))
    Bt = {}
    print(f"\nWEEK-CLUSTER BOOTSTRAP, 2,000 resamples stratified by season, default_rng({B.SEED}) (negative = first arm better):")
    for sub in (None, "EARLY", "CSW"):
        print(f"  {sub or 'pooled'}:")
        for A_, B_ in pairs:
            Bt[(A_, B_, sub)] = e = boot(A_, B_, sub)
            print(f"    {A_:8s} - {B_:7s} {e[0]:+.4f} [{e[1]:+.4f}, {e[2]:+.4f}]")

    TT = pd.concat([pd.read_csv(B.RES / s / "touched.csv.gz", dtype={"fips": str}) for s in B.SEAS] +
                   [pd.read_csv(B.RES / s / "touched_BN.csv.gz", dtype={"fips": str}) for s in B.SEAS])
    TT = TT[TT.fips != "US"]
    print("\nSHARE OF STATE BLOCKS CHANGED, below the median | above it:")
    for a in arms[1:]:
        d = TT[TT.arm == a]; print(f"  {a:8s} {d.lower.mean():.3f} | {d.upper.mean():.3f}")
    defects, zeros, kN = 0, 0, {}
    for s in B.SEAS:
        r = json.load(open(B.RES / s / "record_BN.json"))
        defects += len(r["defects"]); zeros += r["zero_horizons_left_alone"]
        if r["defects"]: print(f"  DEFECTS {s}: {len(r['defects'])}, first {r['defects'][:3]}")
        for w in r["weeks"].values():
            for tag, kk in w.items():
                kN.setdefault(tag, []).extend(kk.values())
    print(f"\ncode check (BN): {defects} defects; horizon-blocks left alone for a 2.5% quantile of 0: {zeros}")
    for tag, v in kN.items():
        a = np.array(v); act = a[a < 1]
        print(f"  kN {tag}: acting in {len(act) / len(a):.3f} of location-weeks; median when acting {np.median(act) if len(act) else 1:.2f}")

    P, E, SO = T["pooled"], T["EARLY"], T["Sep-Oct"]
    b = lambda A_, B_, sub=None: Bt[(A_, B_, sub)][0]
    chk = lambda ok: "HOLDS" if ok else "FAILS"
    print("\nPREDICTIONS (amendment 1, c8db37b6):")
    h1 = {f"{n}-{v}": TT[TT.arm == f"BN{n}-{v}"].lower.mean() < TT[TT.arm == f"B{n}-{v}"].lower.mean() for n in B.NS for v in ("R3", "RX")}
    print(f"  H1 BN touches fewer lower halves than B {h1} -> {chk(all(h1.values()))}")
    h2 = {f"{n}-{v}": b(f"BN{n}-{v}", f"S{n}-{v}") for n in B.NS for v in ("R3", "RX")}
    print("  H2 BN-S in [-0.004,+0.001]: " + ", ".join(f"{k} {x:+.4f}" for k, x in h2.items()) + f" -> {chk(all(-0.004 <= x <= 0.001 for x in h2.values()))}")
    h3 = {f"{n}-{v}": P.cov95[f"S{n}-{v}"] - P.cov95[f"BN{n}-{v}"] for n in B.NS for v in ("R3", "RX")}
    print("  H3 cov95 drop BN vs S <= .010: " + ", ".join(f"{k} {x:+.3f}" for k, x in h3.items()) + f" -> {chk(all(x <= 0.010 for x in h3.values()))}")
    d_bn, d_b = SO.relWIS["BN10-R3"] - SO.relWIS["S10-R3"], SO.relWIS["B10-R3"] - SO.relWIS["S10-R3"]
    print(f"  H4 Sep-Oct BN10-S10 {d_bn:+.4f} < B10-S10 {d_b:+.4f} -> {chk(d_bn < d_b)}")
    h5 = b("BN10-R3", "S10-R3", "EARLY")
    print(f"  H5 EARLY BN10-R3 - S10-R3 {h5:+.4f} <= 0 -> {chk(h5 <= 0)}")

    print("\nDECISION RULE (amendment 1): BN n-V over S n-V")
    for n in B.NS:
        base = f"S{n}-R3"
        for v in ("R3", "RX"):
            a, ref = f"BN{n}-{v}", f"S{n}-{v}"
            e, es = Bt[(a, base, None)], Bt[(a, base, "EARLY")]
            seas = max(P[s][a] - P[s][base] for s in B.SEAS)
            t1 = {"a": e[0] <= 0 and e[2] <= 0.002, "b": seas <= 0.005, "c": es[0] <= 0.003, "d": P.log[a] - P.log[base] <= 0.002,
                  "e": P.cov95[a] >= .90 and P.cov50[a] >= .40 and E.cov95[a] >= .85, "f": defects == 0}
            e2 = Bt[(a, ref, None)]; seas2 = max(P[s][a] - P[s][ref] for s in B.SEAS)
            t2 = {"2 pooled": e2[0] <= 0 and e2[2] <= 0.002, "2 season": seas2 <= 0.003, "2 cov95": P.cov95[ref] - P.cov95[a] <= 0.010}
            fails = [k for k, x in {**t1, **t2}.items() if not x]
            print(f"  {a:8s} vs {base}: {e[0]:+.4f} [{e[1]:+.4f}, {e[2]:+.4f}], worst season {seas:+.4f}, EARLY {es[0]:+.4f}, "
                  f"log {P.log[a] - P.log[base]:+.4f}, cov95 {P.cov95[a]:.3f}, cov50 {P.cov50[a]:.3f}, EARLY95 {E.cov95[a]:.3f}; "
                  f"vs {ref}: {e2[0]:+.4f} [{e2[1]:+.4f}, {e2[2]:+.4f}], worst season {seas2:+.4f}, cov95 drop {P.cov95[ref] - P.cov95[a]:+.3f} "
                  f"-> {'RECOMMENDED over ' + ref if not fails else 'not: fails ' + ', '.join(fails)}")


if __name__ == "__main__":
    if sys.argv[1] == "--season": B.verify(); run_season(sys.argv[2])
    elif sys.argv[1] == "--report": report()
