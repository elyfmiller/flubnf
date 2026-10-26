"""The historical ceiling as a post-calibration step on the Groundhog's kernel
replays (prereg c9587ab57ab6db4b). Per week, in the pipeline's order: hub rows
in whole admissions, the ceiling (ratios from the week's vintage), then the
n-cap; every arm scored on the same cells.
  hist.py --season <s>   build and score every arm for one season (cached)
  hist.py --report       the tables, the bootstrap, the prediction checks"""
import gzip, json, math, sys
from pathlib import Path
import numpy as np, pandas as pd
from app.core import groundhog as gh, scoring, data as D, submit as SUB
from flubnf import tailcap as TC

ROOT = Path(__file__).parent / "results"
SEAS3 = ["2023-24", "2024-25", "2025-26"]
SEAS = SEAS3 + ["2026-27"]
ARMS = ["N", "C15", "S15", "H", "HS15", "HC15", "Hf"]
KEY = ["season", "asof", "fips", "horizon"]
n2f = gh._name2fips(); f2n = {f: l for l, f in n2f.items()}
rel = lambda d: d.wis.sum() / d.base_wis.sum()
lrel = lambda d: d.log_wis.sum() / d.base_log_wis.sum()

def frame(path, asof):
    t = pd.read_csv(path, dtype={"location": str})
    t = t[t["date"].astype(str).str[:10] <= str(asof)].copy()
    t["location"] = t["location"].str.zfill(2)
    return t

def series(t):
    """{fips: [(date, value)]} every location, finite values, oldest first
    (the pipeline's hist_series and obs, before the US is dropped)."""
    return {f: [(str(r.date)[:10], float(r.value)) for r in g.sort_values("date").itertuples()
                if np.isfinite(r.value)] for f, g in t.groupby("location")}

FINAL = None
def final_frame():
    global FINAL
    if FINAL is None:
        FINAL = pd.read_csv(scoring.HUB / "target-data/target-hospital-admissions.csv", dtype={"location": str})
    return FINAL

def to_q(rows):
    out = {}
    for r in rows:
        if r["target"] != TC.TARGET or r["output_type"] != "quantile": continue
        out.setdefault(f2n[str(r["location"])], {}).setdefault(str(r["horizon"]), {})[float(r["output_type_id"])] = float(r["value"])
    return out

def blocks(rows):
    b = {}
    for r in rows:
        if r["target"] == TC.TARGET and r["output_type"] == "quantile":
            b.setdefault((str(r["location"]), int(r["horizon"])), {})[float(r["output_type_id"])] = float(r["value"])
    return b

def week_arms(qw, asof):
    """{arm: rows} plus the week's record (ratios, limits, recent levels)."""
    ser = series(frame(D.vintage_path(asof), asof))
    hist = {f: v for f, v in ser.items() if f != "US"}
    obs = {f: [x for _, x in v[-15:]] for f, v in ser.items()}
    ratios = TC.history_ratios(hist, asof, level=1.0)
    fin = series(frame(scoring.HUB / "target-data/target-hospital-admissions.csv", asof))
    ratios_f = TC.history_ratios({f: v for f, v in fin.items() if f != "US"}, asof, level=1.0)
    rows = []
    for loc, hq in qw.items():
        f = n2f.get(loc)
        if f: rows += SUB.rows_from_quantiles({h: {float(L): float(v) for L, v in lv.items()} for h, lv in hq.items()}, f, asof)
    fips = {str(r["location"]) for r in rows}
    recent = {f: TC.recent_level(obs.get(f, [])) for f in fips}
    hl = {f: TC.history_limits(ratios, recent[f]) for f in fips}
    hlf = {f: TC.history_limits(ratios_f, recent[f]) for f in fips}
    lim = {f: TC.limit_for(15.0, obs.get(f, [])) for f in fips}
    H, _ = TC.clip_rows_by_horizon(rows, hl)
    A = {"N": rows,
         "C15": TC.cap_rows(rows, lim, mode="clip")[0],
         "S15": TC.cap_rows(rows, lim, mode="shrink")[0],
         "H": H,
         "HS15": TC.cap_rows(H, lim, mode="shrink")[0],
         "HC15": TC.cap_rows(H, lim, mode="clip")[0],
         "Hf": TC.clip_rows_by_horizon(rows, hlf)[0]}
    rec = {"ratios": ratios, "ratios_final": ratios_f, "recent": recent,
           "hist_limits": hl}
    return A, rec

def check_week(rows, H, hl):
    """The code check on the H rows (prereg): returns a list of defects."""
    bad = []
    B0, B1 = blocks(rows), blocks(H)
    if set(B0) != set(B1): bad.append(("block set changed",))
    for k, b0 in B0.items():
        b1 = B1.get(k, {}); lim = (hl.get(k[0]) or {}).get(k[1], float("nan"))
        if not math.isfinite(lim):
            if b1 != b0: bad.append(("changed without a limit", k))
            continue
        # the rule as written: above the median, values over max(limit,
        # median) go to that top in whole admissions (half to even), the
        # block kept monotone; the median and below untouched
        top = max(lim, b0[0.5]); exp, prev = {}, -math.inf
        for L in sorted(b0):
            v = b0[L]
            if L > 0.5 and v > top: v = int(round(top))
            v = max(v, prev); prev = v; exp[L] = v
        if exp != b1: bad.append(("differs from the written rule", k, lim, b0, b1))
        if any(b1[L] != b0[L] for L in b0 if L <= 0.5): bad.append(("median or below moved", k))
    return bad

def run_season(season):
    F = json.load(gzip.open(ROOT / season / "forecasts.json.gz"))["forecasts"]
    truth, _ = scoring.load_truth()
    out = {a: ([], []) for a in ARMS}
    recs, touch, tails, defects = {}, [], [], []
    for asof, qw in F.items():
        A, rec = week_arms(qw, asof)
        recs[asof] = {"ratios": rec["ratios"], "ratios_final": rec["ratios_final"]}
        defects += [(asof,) + d for d in check_week(A["N"], A["H"], rec["hist_limits"])]
        B0 = blocks(A["N"])
        for a in ("H", "HS15", "HC15", "C15", "S15", "Hf"):
            B = blocks(A[a])
            for k, b in B.items():
                touch.append((season, asof, a, k[0], k[1], b != B0[k]))
        for a, rows in A.items():
            B = blocks(rows)
            for (f, h), b in B.items():
                if h == 3 and f != "US":
                    r = rec["recent"].get(f, float("nan"))
                    tails.append((season, asof, a, f, b[0.975] / r if r and math.isfinite(r) and r > 0 else float("nan")))
            c, v = gh.score_week(to_q(rows), asof, n2f, truth)
            if not c.empty: c["asof"] = asof; out[a][0].append(c)
            if not v.empty: v["asof"] = asof; out[a][1].append(v)
    for a, (cs, vs) in out.items():
        pd.concat(cs).assign(season=season).to_csv(ROOT / season / f"cells_{a}.csv.gz", index=False)
        pd.concat(vs).assign(season=season).to_csv(ROOT / season / f"coverage_{a}.csv.gz", index=False)
    pd.DataFrame(touch, columns=["season", "asof", "arm", "fips", "horizon", "changed"]).to_csv(ROOT / season / "touched.csv.gz", index=False)
    pd.DataFrame(tails, columns=["season", "asof", "arm", "fips", "h3_over_recent"]).to_csv(ROOT / season / "h3tails.csv.gz", index=False)
    json.dump({"weeks": recs, "defects": defects}, open(ROOT / season / "ceiling_record.json", "w"), indent=1, default=str)
    print(f"{season}: {len(F)} weeks, {len(defects)} defects", flush=True)

if __name__ == "__main__" and sys.argv[1] == "--season":
    run_season(sys.argv[2])

def month(a):
    m = int(str(a)[5:7])
    return "Sep-Oct" if m in (9, 10) else "Nov" if m == 11 else "Aug" if m == 8 else "Dec+"

def report():
    CC, VV = {}, {}
    for a in ["K0"] + ARMS:
        cs, vs = [], []
        for s in SEAS:
            fn = "cells.csv.gz" if a == "K0" else f"cells_{a}.csv.gz"
            vn = "coverage.csv.gz" if a == "K0" else f"coverage_{a}.csv.gz"
            c = pd.read_csv(ROOT / s / fn, dtype={"fips": str}); c["season"] = s
            v = pd.read_csv(ROOT / s / vn, dtype={"fips": str}); v["season"] = s
            cs.append(c); vs.append(v[v.scored.astype(bool)])
        CC[a], VV[a] = pd.concat(cs, ignore_index=True), pd.concat(vs, ignore_index=True)
    common = None
    for a, C in CC.items():
        k = set(map(tuple, C[C.fips != "US"][KEY].astype(str).values)); common = k if common is None else common & k
    sizes = {a: int((C.fips != "US").sum()) for a, C in CC.items()}
    print(f"state cells per arm {sizes}; common {len(common):,} (" +
          ", ".join(f"{s} {sum(1 for k in common if k[0] == s):,}" for s in SEAS) + ")")
    US = {a: C[C.fips == "US"] for a, C in CC.items()}
    for a in CC:
        C = CC[a]; C = C[C.fips != "US"]; CC[a] = C[[tuple(x) in common for x in C[KEY].astype(str).values]].copy()
        V = VV[a]; V = V[V.fips != "US"]; VV[a] = V[[tuple(x) in common for x in V[KEY].astype(str).values]].copy()
        CC[a]["mo"] = CC[a]["asof"].map(month); VV[a]["mo"] = VV[a]["asof"].map(month)
    print("\nREPRODUCTION GATE (K0, uncapped replay quantiles, states): record 0.6802, 0.6272, 0.6448, pooled 0.6423 (17,116)")
    print("  " + ", ".join(f"{s} {rel(CC['K0'][CC['K0'].season == s]):.4f}" for s in SEAS) +
          f"; pooled three seasons {rel(CC['K0'][CC['K0'].season.isin(SEAS3)]):.4f} on {int(CC['K0'].season.isin(SEAS3).sum()):,}")
    cov = lambda V, b: float(V[V.band == b].hit.mean()) if (V.band == b).any() else float("nan")
    print("\nTHREE SEASONS POOLED (states; relWIS natural, log; coverage 50, 95; by season; US separately), and 2026-27's weeks:")
    rows = []
    for a in ["K0"] + ARMS:
        C, V = CC[a][CC[a].season.isin(SEAS3)], VV[a][VV[a].season.isin(SEAS3)]
        r = {"arm": a, "relWIS": round(rel(C), 4), "log": round(lrel(C), 4), "cov50": round(cov(V, 50), 3), "cov95": round(cov(V, 95), 3)}
        r.update({s: round(rel(C[C.season == s]), 4) for s in SEAS3})
        u = US[a]; r["US"] = round(rel(u[u.season.isin(SEAS3)]), 4)
        C4, V4 = CC[a][CC[a].season == "2026-27"], VV[a][VV[a].season == "2026-27"]
        r["2026-27"] = round(rel(C4), 4); r["26-27cov95"] = round(cov(V4, 95), 3)
        rows.append(r)
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nBY AS-OF MONTH, three seasons (relWIS / cov50 / cov95; cells):")
    for mo in ("Aug", "Sep-Oct", "Nov", "Dec+"):
        n = int(((CC["N"].mo == mo) & CC["N"].season.isin(SEAS3)).sum())
        if not n: continue
        line = []
        for a in ["K0"] + ARMS:
            C = CC[a][(CC[a].mo == mo) & CC[a].season.isin(SEAS3)]; V = VV[a][(VV[a].mo == mo) & VV[a].season.isin(SEAS3)]
            line.append(f"{a} {rel(C):.4f}/{cov(V, 50):.2f}/{cov(V, 95):.3f}")
        print(f"  {mo} ({n:,} cells; seasons {sorted(CC['N'][(CC['N'].mo == mo) & CC['N'].season.isin(SEAS3)].season.unique())}):\n    " + "\n    ".join(line))
    print("  2026-27 Sep-Oct (supplementary): " + "  ".join(
        f"{a} {rel(CC[a][CC[a].season == '2026-27']):.4f}/{cov(VV[a][VV[a].season == '2026-27'], 95):.3f}" for a in ARMS))

    def boot(A, B, mo=None, seasons=SEAS3, R=2000):
        M = CC[A][KEY + ["wis", "base_wis", "mo"]].merge(CC[B][KEY + ["wis"]], on=KEY, suffixes=("_a", "_b"))
        M = M[M.season.isin(seasons)]
        if mo: M = M[M.mo == mo]
        W = M.groupby(["season", "asof"]).agg(a=("wis_a", "sum"), b=("wis_b", "sum"), base=("base_wis", "sum")).reset_index()
        est = (W.a.sum() - W.b.sum()) / W.base.sum()
        rng = np.random.default_rng(20261025)
        G = [W[W.season == s][["a", "b", "base"]].to_numpy() for s in seasons if (W.season == s).any()]
        g = []
        for _ in range(R):
            P = np.vstack([x[rng.integers(0, len(x), len(x))] for x in G])
            g.append((P[:, 0].sum() - P[:, 1].sum()) / P[:, 2].sum())
        return est, float(np.percentile(g, 2.5)), float(np.percentile(g, 97.5))
    PAIRS = [("H", "N"), ("H", "C15"), ("HS15", "S15"), ("HS15", "C15"), ("HC15", "C15"), ("HC15", "H"), ("S15", "C15"), ("Hf", "H")]
    B = {}
    print("\nWEEK-CLUSTER BOOTSTRAP, 2,000 resamples stratified by season, seed 20261025 (negative = first arm better):")
    for mo in (None, "Sep-Oct", "Nov", "Dec+"):
        print(f"  {mo or 'all three seasons'}:")
        for A, Bb in PAIRS:
            B[(A, Bb, mo)] = e = boot(A, Bb, mo)
            print(f"    {A:5s} - {Bb:4s} {e[0]:+.4f} [{e[1]:+.4f}, {e[2]:+.4f}]")

    T = pd.concat([pd.read_csv(ROOT / s / "touched.csv.gz", dtype={"fips": str}) for s in SEAS])
    T["mo"] = T["asof"].map(month); T = T[T.fips != "US"]
    print("\nSHARE OF STATE (location, horizon) BLOCKS CHANGED, by horizon (h0 h1 h2 h3 | all):")
    for sub, D_ in (("three seasons", T[T.season.isin(SEAS3)]), ("Sep-Oct 2023-24", T[(T.season == "2023-24") & (T.mo == "Sep-Oct")]),
                    ("Nov", T[T.season.isin(SEAS3) & (T.mo == "Nov")]), ("Dec+", T[T.season.isin(SEAS3) & (T.mo == "Dec+")]),
                    ("2026-27", T[T.season == "2026-27"])):
        print(f"  {sub}:")
        for a in ("H", "HS15", "HC15", "C15", "S15", "Hf"):
            d = D_[D_.arm == a]
            print(f"    {a:5s} " + " ".join(f"{d[d.horizon == h].changed.mean():.3f}" for h in range(4)) + f" | {d.changed.mean():.3f}")

    print("\nTHE CEILING'S RATIOS (vintage, maximum) BY HORIZON: median over the season's weeks, minimum, and every September-October week:")
    R = []
    for s in SEAS:
        rec = json.load(open(ROOT / s / "ceiling_record.json"))
        for asof, w in rec["weeks"].items():
            for h in range(4):
                R.append((s, asof, h, w["ratios"][str(h)], w["ratios_final"][str(h)]))
        if rec["defects"]: print(f"  DEFECTS {s}: {len(rec['defects'])}, first {rec['defects'][:3]}")
        else: print(f"  code check on the H rows, {s}: no defect")
    R = pd.DataFrame(R, columns=["season", "asof", "h", "vint", "final"]); R["mo"] = R["asof"].map(month)
    for s in SEAS:
        d = R[R.season == s]
        print(f"  {s}: median " + " ".join(f"{d[d.h == h].vint.median():.1f}x" for h in range(4)) +
              "; min " + " ".join(f"{d[d.h == h].vint.min():.1f}x" for h in range(4)))
        for asof, g in d[d.mo == "Sep-Oct"].groupby("asof"):
            print(f"      {asof}: " + " ".join(f"{x:.1f}x" for x in g.sort_values("h").vint))
    R["rd"] = (R.vint - R.final).abs() / R.final
    print("  vintage against final truth, |relative difference| by horizon: median " +
          " ".join(f"{R[R.h == h].rd.median():.3%}" for h in range(4)) + "; max " +
          " ".join(f"{R[R.h == h].rd.max():.1%}" for h in range(4)) + f"; weeks with any difference {int((R.groupby('asof').rd.max() > 1e-12).sum())} of {R["asof"].nunique()}")

    X = pd.concat([pd.read_csv(ROOT / s / "h3tails.csv.gz", dtype={"fips": str}) for s in SEAS]); X = X[X.season.isin(SEAS3)]
    print("\nh3 97.5% QUANTILE OVER THE RECENT LEVEL, states, three seasons: typical (median), 90th percentile, max, share over 30x; Sep-Oct typical:")
    for a in ARMS:
        x = X[X.arm == a].h3_over_recent.dropna(); xo = X[(X.arm == a) & (X["asof"].map(month) == "Sep-Oct")].h3_over_recent.dropna()
        print(f"  {a:5s} {x.median():5.1f}x {x.quantile(.9):5.1f}x {x.max():6.1f}x {(x > 30).mean():.3%} | Sep-Oct {xo.median():.1f}x")

    print("\nPREDICTIONS (prereg c9587ab57ab6db4b):")
    p = lambda *k: B[k]
    r3 = {a: rel(CC[a][CC[a].season.isin(SEAS3)]) for a in ARMS}
    c95 = {a: cov(VV[a][VV[a].season.isin(SEAS3)], 95) for a in ARMS}
    c50 = {a: cov(VV[a][VV[a].season.isin(SEAS3)], 50) for a in ARMS}
    g1 = -0.004 <= p("H", "N", None)[0] <= 0.002 and p("H", "C15", None)[1] <= 0
    g1b = p("H", "C15", None)
    print(f"  G1 H-N {p('H', 'N', None)[0]:+.4f} in [-0.004,+0.002]; H-C15 interval [{g1b[1]:+.4f}, {g1b[2]:+.4f}] includes 0 or below -> {'HOLDS' if g1 and g1b[1] <= 0 else 'FAILS'}")
    d2 = p("HS15", "S15", None)[0]
    print(f"  G2 HS15-S15 {d2:+.4f} in [-0.006,-0.001]; HS15-C15 {p('HS15', 'C15', None)[0]:+.4f} > 0 -> {'HOLDS' if -0.006 <= d2 <= -0.001 and p('HS15', 'C15', None)[0] > 0 else 'FAILS'}")
    d3 = p("HS15", "S15", "Sep-Oct")[0]
    print(f"  G3 Sep-Oct HS15-S15 {d3:+.4f} within 0.005 -> {'HOLDS' if abs(d3) <= 0.005 else 'FAILS'}")
    d4 = p("HC15", "H", None)[0]
    print(f"  G4 HC15-H {d4:+.4f} within 0.003 -> {'HOLDS' if abs(d4) <= 0.003 else 'FAILS'}")
    print(f"  G5 cov95 H {c95['H']:.3f} >= .925, HS15 {c95['HS15']:.3f} >= .910 -> {'HOLDS' if c95['H'] >= .925 and c95['HS15'] >= .910 else 'FAILS'}")
    rd = max(R[R.h == h].rd.median() for h in range(4)); d6 = r3["Hf"] - r3["H"]
    print(f"  G6 max over horizons of the median |rel diff| {rd:.3%} < 5%; Hf-H {d6:+.4f} within 0.002 -> {'HOLDS' if rd < 0.05 and abs(d6) <= 0.002 else 'FAILS'}")
    print("\nDECISION RULE for the pairing HS15:")
    seas = {s: rel(CC['HS15'][CC['HS15'].season == s]) - rel(CC['S15'][CC['S15'].season == s]) for s in SEAS3}
    defects = sum(len(json.load(open(ROOT / s / "ceiling_record.json"))["defects"]) for s in SEAS)
    ok = {"a HS15-S15 <= 0": d2 <= 0, "b no season worse than S15 by >0.003": max(seas.values()) <= 0.003,
          "c Sep-Oct HS15-S15 <= +0.005": d3 <= 0.005, "d cov95 >= .90, cov50 >= .40": c95["HS15"] >= .90 and c50["HS15"] >= .40,
          "e no code defect": defects == 0}
    for k, v in ok.items(): print(f"  {k}: {'yes' if v else 'NO'}")
    print("  seasons HS15-S15: " + ", ".join(f"{s} {d:+.4f}" for s, d in seas.items()))
    print("  -> " + ("SUPPORTED" if all(ok.values()) else "NOT SUPPORTED: " + "; ".join(k for k, v in ok.items() if not v)))
    seasH = {s: rel(CC['H'][CC['H'].season == s]) - rel(CC['N'][CC['N'].season == s]) for s in SEAS3}
    print(f"  for the record, H against N: pooled {p('H', 'N', None)[0]:+.4f}, seasons " + ", ".join(f"{s} {d:+.4f}" for s, d in seasH.items()) +
          f", Sep-Oct {p('H', 'N', 'Sep-Oct')[0]:+.4f}, cov95 {c95['H']:.3f} cov50 {c50['H']:.3f}")

if __name__ == "__main__" and sys.argv[1] == "--report":
    report()
