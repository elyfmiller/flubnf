"""The tail cap on both halves, the Groundhog half (prereg.txt beside this
file, sha256 67262c94...). Post hoc on the stored retro forecasts: per week,
the hub rows in whole admissions, then each arm's cap; every arm scored on
the same cells.
  both.py --verify        the stored forecasts' sha256 against the prereg
  both.py --season <s>    build, check and score every arm for one season
  both.py --report        the tables, the bootstrap, the predictions, the rule
Run from the repository root (PYTHONPATH=.), with FLUBNF_HUB the hub clone at
3a83d410 and CAP_ROOT the research folder (default
~/flubnf-model-research/cap-both-halves-2026-11: replay/<season>/ in,
results/<season>/ out)."""
import gzip, hashlib, json, math, os, sys
from datetime import timedelta
from pathlib import Path
import numpy as np, pandas as pd
from app.core import groundhog as gh, scoring, data as D, submit as SUB
from flubnf import tailcap as TC

ROOT = Path(os.environ.get("CAP_ROOT") or Path.home() / "flubnf-model-research" / "cap-both-halves-2026-11")
REPLAY, RES = ROOT / "replay", ROOT / "results"
SEAS = ["2023-24", "2024-25", "2025-26"]
SHA = {"2023-24": "355dca4f1278128d2d7f973019cbb8689f7e3cb448432b52b05b6a058dfedbb5",
       "2024-25": "48902aacbc74fd8cd3f8625a10cc8616ce5df4f1d9e1b2f8fda274eb51a3bd24",
       "2025-26": "7bdd5f20134fba9c194819a8bba35c6b52b88f0028784079a4f9a5ac12517e67"}
NS, LEVELS, MODES = (10, 15), ("R3", "R1", "RX"), ("S", "M", "B", "LN")
ARMS = ["N"] + [f"{m}{n}-{v}" for m in MODES for n in NS for v in LEVELS]
PROD = {10: "S10-R3", 15: "S15-R3"}
LOWER_K = 0.7
KEY = ["season", "asof", "fips", "horizon"]
CSW = [("2023-10-07", "2023-12-02"), ("2024-11-16", "2024-12-14"), ("2025-11-15", "2025-12-06")]
SEED = 20261110
n2f = gh._name2fips(); f2n = {f: l for l, f in n2f.items()}
rel = lambda d: d.wis.sum() / d.base_wis.sum()
lrel = lambda d: d.log_wis.sum() / d.base_log_wis.sum()


def verify():
    bad = []
    for s, h in SHA.items():
        got = hashlib.sha256((REPLAY / s / "forecasts.json.gz").read_bytes()).hexdigest()
        print(f"{s}: {got} {'ok' if got == h else 'MISMATCH'}")
        if got != h: bad.append(s)
    if bad: sys.exit(f"stored forecasts differ from the prereg: {bad}")


# ---- the week's data, as app/ui/pipeline.py builds it ------------------------
def obs_by_fips(asof):
    """fips -> obs: the vintage's rows dated on or before the as-of, the last
    15 by date, finite values, oldest first (pipeline.py, drop_same_day off
    as in the replays)."""
    t = pd.read_csv(D.vintage_path(asof), dtype={"location": str})
    t = t[t["date"].astype(str).str[:10] <= str(asof)].copy()
    t["location"] = t["location"].str.zfill(2)
    return {f: [float(x) for x in g.sort_values("date")["value"].tail(15) if np.isfinite(x)]
            for f, g in t.groupby("location")}


def levels(obs):
    r3 = TC.recent_level(obs)
    r1 = float(obs[-1]) if obs else float("nan")
    rx = max(r3, r1) if math.isfinite(r3) and math.isfinite(r1) else float("nan")
    return {"R3": r3, "R1": r1, "RX": rx}


def blocks(rows):
    b = {}
    for r in rows:
        if r["target"] == TC.TARGET and r["output_type"] == "quantile":
            b.setdefault((str(r["location"]), int(r["horizon"])), {})[float(r["output_type_id"])] = float(r["value"])
    return b


def to_q(B):
    out = {}
    for (f, h), b in B.items():
        out.setdefault(f2n[f], {})[str(h)] = dict(b)
    return out


# ---- the lower-half rules (this screen's code, not the repository's) -------
def power(block, k, lower=True, upper=False):
    """q' = m (q/m)^k on the chosen half (q > 0; 0 stays 0); others as given."""
    out = dict(block); m = out.get(0.5)
    if k is None or k >= 1 or m is None or not (m > 0):
        return out
    for L, v in out.items():
        if ((lower and L < 0.5) or (upper and L > 0.5)) and math.isfinite(v) and v > 0:
            out[L] = m * (v / m) ** k
    return out


def k_lower_balance(loc_blocks, k):
    """B's kL: once the cap acts (k < 1), min over horizons of
    k ln(q97.5/m) / ln(m/q2.5), where q2.5 > 0, m > q2.5, q97.5 > m; 1 when
    k = 1 or no horizon qualifies; at most 1."""
    if k >= 1:
        return 1.0
    ks = []
    for b in loc_blocks.values():
        m, lo, hi = b.get(0.5), b.get(0.025), b.get(0.975)
        if None in (m, lo, hi) or not (lo > 0 and m > lo and hi > m):
            continue
        ks.append(k * math.log(hi / m) / math.log(m / lo))
    return min([1.0] + ks)


def week_arms(qw, asof):
    """{arm: blocks} and the week's record (levels, k, kL)."""
    obs = obs_by_fips(asof)
    rows = []
    for loc, hq in qw.items():
        f = n2f.get(loc)
        if f: rows += SUB.rows_from_quantiles({h: {float(L): float(v) for L, v in lv.items()} for h, lv in hq.items()}, f, asof)
    B0 = blocks(rows)
    fips = sorted({f for f, _ in B0})
    by_loc = {f: {h: b for (g, h), b in B0.items() if g == f} for f in fips}
    lv = {f: levels(obs.get(f, [])) for f in fips}
    A, rec = {"N": B0}, {"levels": lv, "k": {}, "kL": {}}
    for n in NS:
        for V in LEVELS:
            lim = {f: (n * lv[f][V] if math.isfinite(lv[f][V]) and lv[f][V] > 0 else float("nan")) for f in fips}
            S = blocks(TC.cap_rows(rows, lim, mode="shrink")[0])
            k = {f: min([1.0] + [TC.exponent_needed(b, lim[f]) for b in by_loc[f].values()]) for f in fips}
            kL = {f: k_lower_balance(by_loc[f], k[f]) for f in fips}
            M, Bb, LN = {}, {}, {}
            for (f, h), b in B0.items():
                M[(f, h)] = TC.whole_block(power(b, k[f], lower=True, upper=True), b)
                Bb[(f, h)] = TC.whole_block(power(power(b, k[f], lower=False, upper=True), kL[f]), b)
                LN[(f, h)] = TC.whole_block(power(power(b, k[f], lower=False, upper=True), LOWER_K), b)
            A[f"S{n}-{V}"], A[f"M{n}-{V}"], A[f"B{n}-{V}"], A[f"LN{n}-{V}"] = S, M, Bb, LN
            rec["k"][f"{n}-{V}"], rec["kL"][f"{n}-{V}"] = k, kL
            rec.setdefault("lim", {})[f"{n}-{V}"] = lim
    return A, rec


# ---- the code check (prereg (i) to (v)) -------------------------------------
def k_written(loc_blocks, lim):
    """The location exponent from its written rule (the tailcap docstring):
    the worst horizon's exponent bringing its 97.5% quantile to the limit."""
    if not (lim is not None and math.isfinite(lim)):
        return 1.0
    k = 1.0
    for b in loc_blocks.values():
        m, q = b.get(0.5), b.get(0.975)
        if m is None or q is None or not (m > 0) or q <= m or q <= lim or lim <= m:
            continue
        k = min(k, math.log(lim / m) / math.log(q / m))
    return k


def round_monotone(new, old):
    out, top = {}, -math.inf
    for L in sorted(new):
        v = new[L]
        if v != old[L]: v = int(round(v))
        v = max(v, top); top = v; out[L] = v
    return out


def check_week(A, rec):
    bad = []
    B0 = A["N"]
    fips = sorted({f for f, _ in B0})
    by_loc = {f: {h: b for (g, h), b in B0.items() if g == f} for f in fips}
    for n in NS:
        for V in LEVELS:
            tag = f"{n}-{V}"; lim = rec["lim"][tag]; k = rec["k"][tag]; kL = rec["kL"][tag]
            S = A[f"S{tag}"]
            for f in fips:
                kw = k_written(by_loc[f], lim[f])
                if abs(kw - k[f]) > 1e-12: bad.append(("i k", tag, f, kw, k[f]))
                for h, b in by_loc[f].items():
                    m = b[0.5]
                    want = dict(b)
                    if math.isfinite(lim[f]) and kw < 1 and m > 0:
                        for L, v in b.items():
                            if L > 0.5 and v > 0: want[L] = m * (v / m) ** kw
                    if round_monotone(want, b) != S[(f, h)]: bad.append(("i S", tag, f, h))
            for mode in MODES:
                X = A[f"{mode}{tag}"]
                for key, b in B0.items():
                    x = X[key]; levs = sorted(b)
                    if x[0.5] != b[0.5]: bad.append(("ii median", mode, tag, key))
                    if any(x[a] > x[c] for a, c in zip(levs, levs[1:])): bad.append(("ii monotone", mode, tag, key))
                    if any(x[L] != b[L] and float(x[L]) != int(x[L]) for L in levs): bad.append(("ii whole", mode, tag, key))
                    if mode != "S" and any(x[L] != S[key][L] for L in levs if L > 0.5): bad.append(("iii upper", mode, tag, key))
                    f, h = key
                    if mode == "M" and k[f] >= 1 and x != b: bad.append(("v M", tag, key))
                    if mode == "B" and kL[f] >= 1 and any(x[L] != b[L] for L in levs if L < 0.5): bad.append(("v B", tag, key))
                    if mode == "B" and kL[f] < 1:
                        m, lo0, hi0 = b[0.5], b[0.025], b[0.975]
                        if lo0 > 0 and m > lo0 and hi0 > m:
                            lo, hi = x[0.025], x[0.975]
                            if not (m * m <= (hi + 1) * (lo + 1) + 1e-9): bad.append(("iv B lean", tag, key, lo, m, hi))
    return bad


# ---- one season -------------------------------------------------------------
def run_season(season):
    F = json.load(gzip.open(REPLAY / season / "forecasts.json.gz"))["forecasts"]
    truth, _ = scoring.load_truth()
    out = {a: ([], []) for a in ["K0"] + ARMS}
    touch, recs, defects = [], {}, []
    for asof, qw in F.items():
        A, rec = week_arms(qw, asof)
        defects += [(asof,) + d for d in check_week(A, rec)]
        recs[asof] = {"k": rec["k"], "kL": rec["kL"]}
        B0 = A["N"]
        for a in ARMS[1:]:
            for (f, h), b in A[a].items():
                b0 = B0[(f, h)]
                touch.append((season, asof, a, f, h, any(b[L] != b0[L] for L in b0 if L < 0.5),
                              any(b[L] != b0[L] for L in b0 if L > 0.5)))
        T = pd.Timestamp(asof)
        for a in ["K0"] + ARMS:
            q = {loc: {str(h): {float(L): float(v) for L, v in lv.items()} for h, lv in hq.items()} for loc, hq in qw.items()} if a == "K0" else to_q(A[a])
            c, v = gh.score_week(q, asof, n2f, truth)
            if not c.empty:
                c = c.copy(); c["asof"] = asof
                lo, hi, lean = [], [], []
                for r in c.itertuples():
                    y = truth.get((str(r.fips), T + timedelta(days=7 * (int(r.horizon) + 1))))
                    b = q[f2n[str(r.fips)]][str(int(r.horizon))]
                    lo.append(int(y < b[0.025])); hi.append(int(y > b[0.975]))
                    w_up = b[0.975] - b[0.5]
                    lean.append((b[0.5] - b[0.025]) / w_up if w_up > 0 else float("nan"))
                c["below"], c["above"], c["lean"] = lo, hi, lean
                out[a][0].append(c)
            if not v.empty: v = v.copy(); v["asof"] = asof; out[a][1].append(v)
    d = RES / season; d.mkdir(parents=True, exist_ok=True)
    for a, (cs, vs) in out.items():
        pd.concat(cs).assign(season=season).to_csv(d / f"cells_{a}.csv.gz", index=False)
        pd.concat(vs).assign(season=season).to_csv(d / f"coverage_{a}.csv.gz", index=False)
    pd.DataFrame(touch, columns=["season", "asof", "arm", "fips", "horizon", "lower", "upper"]).to_csv(d / "touched.csv.gz", index=False)
    json.dump({"weeks": recs, "defects": defects}, open(d / "record.json", "w"), default=str)
    print(f"{season}: {len(F)} weeks, {len(defects)} defects", flush=True)


# ---- the report -------------------------------------------------------------
def month(a):
    m = int(str(a)[5:7])
    return "Sep-Oct" if m in (9, 10) else "Nov" if m == 11 else "Aug" if m == 8 else "Dec+"


def report():
    CC, VV = {}, {}
    for a in ["K0"] + ARMS:
        cs, vs = [], []
        for s in SEAS:
            c = pd.read_csv(RES / s / f"cells_{a}.csv.gz", dtype={"fips": str}); c["season"] = s
            v = pd.read_csv(RES / s / f"coverage_{a}.csv.gz", dtype={"fips": str}); v["season"] = s
            cs.append(c[c.fips != "US"]); vs.append(v[v.scored.astype(bool) & (v.fips != "US")])
        CC[a], VV[a] = pd.concat(cs, ignore_index=True), pd.concat(vs, ignore_index=True)
    sizes = {a: len(C) for a, C in CC.items()}
    print(f"state cells per arm: {sorted(set(sizes.values()))} (K0 {sizes['K0']:,})")
    # EARLY: the first 8 as-of weeks of each season with a scored state cell
    early = set()
    for s in SEAS:
        wk = sorted(CC["N"][CC["N"].season == s].asof.unique())[:8]
        early |= {(s, w) for w in wk}
    in_csw = lambda a: any(lo <= str(a) <= hi for lo, hi in CSW)
    for a in CC:
        for X in (CC[a], VV[a]):
            X["mo"] = X["asof"].map(month)
            X["early"] = [(s, w) in early for s, w in zip(X.season, X.asof)]
            X["csw"] = X["asof"].map(in_csw)
    print("\nREPRODUCTION GATE (K0, the stored quantiles, states): record 0.6802, 0.6272, 0.6448, pooled 0.6423 (17,116)")
    g = {s: rel(CC["K0"][CC["K0"].season == s]) for s in SEAS}
    print("  " + ", ".join(f"{s} {g[s]:.4f}" for s in SEAS) + f"; pooled {rel(CC['K0']):.4f} on {len(CC['K0']):,}")
    gate = [round(g[s], 4) for s in SEAS] == [0.6802, 0.6272, 0.6448] and round(rel(CC["K0"]), 4) == 0.6423 and len(CC["K0"]) == 17116
    print("  -> " + ("PASSES" if gate else "FAILS: stop, nothing below is read"))
    if not gate:
        return
    cov = lambda V, b: float(V[V.band == b].hit.mean()) if (V.band == b).any() else float("nan")
    subsets = {"pooled": lambda X: X, "EARLY": lambda X: X[X.early], "CSW": lambda X: X[X.csw],
               "Sep-Oct": lambda X: X[X.mo == "Sep-Oct"], "Nov": lambda X: X[X.mo == "Nov"], "Dec+": lambda X: X[X.mo == "Dec+"]}
    print(f"\nweeks: EARLY {len(early)}; corrected-seed windows {CC['N'][CC['N'].csw].groupby(['season', 'asof']).ngroups}; "
          f"cells pooled {len(CC['N']):,}, EARLY {int(CC['N'].early.sum()):,}, CSW {int(CC['N'].csw.sum()):,}")
    T = {}
    for name, sub in subsets.items():
        rows = []
        for a in ARMS:
            C, V = sub(CC[a]), sub(VV[a])
            r = {"arm": a, "relWIS": rel(C), "log": lrel(C), "cov50": cov(V, 50), "cov95": cov(V, 95),
                 "below2.5": C.below.mean(), "above97.5": C.above.mean()}
            if name == "pooled":
                r.update({s: rel(C[C.season == s]) for s in SEAS})
                h0 = C[C.horizon == 0].lean.dropna(); r["h0lean"] = h0.median()
            if name == "EARLY":
                r["h0lean"] = C[C.horizon == 0].lean.dropna().median()
            rows.append(r)
        T[name] = pd.DataFrame(rows).set_index("arm")
        print(f"\n{name.upper()} (states): relWIS, log relWIS, coverage 50 / 95, truth below 2.5% / above 97.5%"
              + (", by season, h0 lean (below over above)" if name == "pooled" else ", h0 lean" if name == "EARLY" else ""))
        print(T[name].round(4).to_string())

    def boot(A, B, sub=None, R=2000):
        M = CC[A][KEY + ["wis", "base_wis", "early", "csw"]].merge(CC[B][KEY + ["wis"]], on=KEY, suffixes=("_a", "_b"))
        if sub == "EARLY": M = M[M.early]
        if sub == "CSW": M = M[M.csw]
        W = M.groupby(["season", "asof"]).agg(a=("wis_a", "sum"), b=("wis_b", "sum"), base=("base_wis", "sum")).reset_index()
        est = (W.a.sum() - W.b.sum()) / W.base.sum()
        rng = np.random.default_rng(SEED)
        G = [W[W.season == s][["a", "b", "base"]].to_numpy() for s in SEAS if (W.season == s).any()]
        bs = []
        for _ in range(R):
            P = np.vstack([x[rng.integers(0, len(x), len(x))] for x in G])
            bs.append((P[:, 0].sum() - P[:, 1].sum()) / P[:, 2].sum())
        return est, float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))
    pairs = [(a, "S10-R3") for a in ARMS if a != "S10-R3"]
    pairs += [(f"{m}{n}-{v}", f"S{n}-{v}") for m in ("M", "B", "LN") for n in NS for v in LEVELS]
    pairs += [(f"S{n}-{v}", f"S{n}-R3") for n in NS for v in ("R1", "RX")]
    pairs = list(dict.fromkeys(pairs))
    Bt = {}
    print(f"\nWEEK-CLUSTER BOOTSTRAP, 2,000 resamples stratified by season, default_rng({SEED}) (negative = first arm better):")
    for sub in (None, "EARLY", "CSW"):
        print(f"  {sub or 'pooled'}:")
        for A_, B_ in pairs:
            Bt[(A_, B_, sub)] = e = boot(A_, B_, sub)
            print(f"    {A_:8s} - {B_:7s} {e[0]:+.4f} [{e[1]:+.4f}, {e[2]:+.4f}]")

    TT = pd.concat([pd.read_csv(RES / s / "touched.csv.gz", dtype={"fips": str}) for s in SEAS])
    TT = TT[TT.fips != "US"]
    print("\nSHARE OF STATE BLOCKS CHANGED, below the median | above it (all weeks):")
    for a in ARMS[1:]:
        d = TT[TT.arm == a]; print(f"  {a:8s} {d.lower.mean():.3f} | {d.upper.mean():.3f}")
    print("\nLOCATION EXPONENTS over location-weeks with a limit: k (median, share < 0.5) and kL (median, share < 1):")
    for s in SEAS:
        rec = json.load(open(RES / s / "record.json"))
        if rec["defects"]: print(f"  DEFECTS {s}: {len(rec['defects'])}, first {rec['defects'][:3]}")
        else: print(f"  code check {s}: no defect")
    K = {}
    for s in SEAS:
        for asof, w in json.load(open(RES / s / "record.json"))["weeks"].items():
            for tag, kk in w["k"].items():
                for f, x in kk.items():
                    K.setdefault(tag, []).append((x, w["kL"][tag][f]))
    for tag, v in K.items():
        a = np.array(v); act = a[a[:, 0] < 1]
        print(f"  {tag:6s} acting {len(act) / len(a):.3f}; k median {np.median(act[:, 0]) if len(act) else 1:.2f}, "
              f"< 0.5 {np.mean(act[:, 0] < 0.5) if len(act) else 0:.3f}; kL median {np.median(act[:, 1]) if len(act) else 1:.2f}, < 1 {np.mean(act[:, 1] < 1) if len(act) else 0:.3f}")

    P, E = T["pooled"], T["EARLY"]
    b = lambda A_, B_, sub=None: Bt[(A_, B_, sub)][0]
    print("\nPREDICTIONS (prereg 67262c94):")
    chk = lambda ok: "HOLDS" if ok else "FAILS"
    g1 = (-0.012 <= b("M10-R3", "S10-R3") <= 0.001, -0.008 <= b("M15-R3", "S15-R3") <= 0.001)
    print(f"  G1 M10-S10 {b('M10-R3', 'S10-R3'):+.4f} in [-0.012,+0.001]; M15-S15 {b('M15-R3', 'S15-R3'):+.4f} in [-0.008,+0.001] -> {chk(all(g1))}")
    g2 = (b("M10-R3", "S10-R3", "EARLY"), b("M15-R3", "S15-R3", "EARLY"))
    print(f"  G2 EARLY M-S at 10 {g2[0]:+.4f}, at 15 {g2[1]:+.4f}, both <= -0.005 -> {chk(max(g2) <= -0.005)}")
    d95 = (P.cov95["S10-R3"] - P.cov95["M10-R3"], P.cov95["S15-R3"] - P.cov95["M15-R3"])
    up = (P["below2.5"]["M10-R3"] > P["below2.5"]["S10-R3"], P["below2.5"]["M15-R3"] > P["below2.5"]["S15-R3"])
    print(f"  G3 cov95 drop under M: 10 {d95[0]:+.3f} (>= .02), 15 {d95[1]:+.3f} (>= .01); below-2.5% rises {up} -> {chk(d95[0] >= .02 and d95[1] >= .01 and all(up))}")
    lowB = {n: TT[TT.arm == f"B{n}-R3"].lower.mean() for n in NS}; lowM = {n: TT[TT.arm == f"M{n}-R3"].lower.mean() for n in NS}
    g4 = all(abs(b(f"B{n}-R3", f"S{n}-R3")) <= abs(b(f"M{n}-R3", f"S{n}-R3")) and lowB[n] < lowM[n] for n in NS)
    print(f"  G4 |B-S| <= |M-S| and B touches fewer lower halves than M, at 10 and 15 -> {chk(g4)}")
    g5 = (b("LN10-R3", "S10-R3"), b("LN15-R3", "S15-R3"))
    print(f"  G5 LN-S at 10 {g5[0]:+.4f}, at 15 {g5[1]:+.4f}, both >= -0.002 -> {chk(min(g5) >= -0.002)}")
    rx_up = {n: TT[TT.arm == f"S{n}-RX"].upper.mean() < TT[TT.arm == f"S{n}-R3"].upper.mean() for n in NS}
    g6 = -0.010 <= b("S10-RX", "S10-R3") <= 0.002 and b("S10-RX", "S10-R3", "EARLY") <= 0.003 and all(rx_up.values())
    print(f"  G6 S10-RX - S10-R3 {b('S10-RX', 'S10-R3'):+.4f} in [-0.010,+0.002]; EARLY {b('S10-RX', 'S10-R3', 'EARLY'):+.4f} <= +0.003; RX touches fewer {rx_up} -> {chk(g6)}")
    print(f"  G7 S10-R3 - S15-R3 {P.relWIS['S10-R3'] - P.relWIS['S15-R3']:+.4f} > 0 -> {chk(P.relWIS['S10-R3'] > P.relWIS['S15-R3'])}")

    defects = sum(len(json.load(open(RES / s / "record.json"))["defects"]) for s in SEAS)
    print("\nDECISION RULE, at each n (the arm against S n-R3):")
    parse = lambda a: (a.split("-")[0].rstrip("0123456789"), int(a.split("-")[0].lstrip("SMBLN")), a.split("-")[1])
    simple = lambda a: (("R3", "RX", "R1").index(parse(a)[2]), MODES.index(parse(a)[0]) if parse(a)[0] != "S" else -1)
    for n in NS:
        base = PROD[n]; passing = []
        for a in [x for x in ARMS if x not in ("N", base) and parse(x)[1] == n]:
            e = boot(a, base) if (a, base, None) not in Bt else Bt[(a, base, None)]
            es = boot(a, base, "EARLY") if (a, base, "EARLY") not in Bt else Bt[(a, base, "EARLY")]
            seas = max(P[s][a] - P[s][base] for s in SEAS)
            tests = {"a": e[0] <= 0 and e[2] <= 0.002, "b": seas <= 0.005, "c": es[0] <= 0.003,
                     "d": P.log[a] - P.log[base] <= 0.002,
                     "e": P.cov95[a] >= .90 and P.cov50[a] >= .40 and E.cov95[a] >= .85, "f": defects == 0}
            print(f"  {a:8s} {e[0]:+.4f} [{e[1]:+.4f}, {e[2]:+.4f}] worst season {seas:+.4f} EARLY {es[0]:+.4f} "
                  f"log {P.log[a] - P.log[base]:+.4f} cov95 {P.cov95[a]:.3f} cov50 {P.cov50[a]:.3f} EARLY95 {E.cov95[a]:.3f} "
                  f"-> {'passes' if all(tests.values()) else 'fails ' + ''.join(k for k, v in tests.items() if not v)}")
            if all(tests.values()): passing.append(a)
        if not passing:
            print(f"  at {n}x: none passes; {base} stays the recommendation")
            continue
        best = min(P.relWIS[a] for a in passing)
        near = sorted([a for a in passing if P.relWIS[a] <= best + 0.001], key=simple)
        print(f"  at {n}x: passing {passing}; lowest pooled {best:.4f}; within 0.001, by the tie order: {near} -> RECOMMENDED {near[0]}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "--verify": verify()
    elif cmd == "--season": verify(); run_season(sys.argv[2])
    elif cmd == "--report": report()
