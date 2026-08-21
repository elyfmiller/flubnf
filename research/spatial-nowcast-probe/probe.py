"""Two cheap probes for the spatial-metapopulation and nowcast ideas.

1. SPATIAL. Does neighbour / national growth predict next week's growth
   after the state's own lag is known? Incremental R^2 over AR(1), same
   bar that killed the age member's share-channel and that the paediatric
   growth signal barely cleared.

2. NOWCAST. How much of the last week's revision is predictable from a
   state's own historical completeness, leave-one-season-out? And how
   large is the analogue-scale bias that an uncorrected last point
   induces (the analogue is a scale of the last observed value)?

Vintage-true for (2). Final-data for (1) -- spatial coupling is a
biological claim, not a revision claim; if it is not there on settled
data it is not there.

Run from the repo root with the app venv.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core.data import ARCHIVE, vintages, vintage_path  # noqa: E402
from flubnf.settings import LOCATIONS  # noqa: E402

# HHS regions. Enough "neighbourhood" to test spatial coupling without a
# commuting matrix. If regional leave-one-out growth adds nothing, a
# 52-region BNGL metapopulation will not either.
HHS = {
    1: "CT ME MA NH RI VT",
    2: "NJ NY PR",
    3: "DE DC MD PA VA WV",
    4: "AL FL GA KY MS NC SC TN",
    5: "IL IN MI MN OH WI",
    6: "AR LA NM OK TX",
    7: "IA KS MO NE",
    8: "CO MT ND SD UT WY",
    9: "AZ CA HI NV",
    10: "AK ID OR WA",
}
ABBR_TO_HHS = {a: r for r, names in HHS.items() for a in names.split()}


def loc_map():
    loc = pd.read_csv(LOCATIONS, dtype=str)
    name2fips = dict(zip(loc.location_name, loc.location.str.zfill(2)))
    fips2abbr = dict(zip(loc.location.str.zfill(2), loc.abbreviation))
    fips2pop = dict(zip(loc.location.str.zfill(2),
                        pd.to_numeric(loc.population, errors="coerce")))
    return name2fips, fips2abbr, fips2pop


def season_of(d) -> str:
    ts = pd.Timestamp(d)
    y = ts.year if ts.month >= 8 else ts.year - 1
    return f"{y}-{str(y+1)[2:]}"


def load_final() -> pd.DataFrame:
    """Latest vintage as settled truth. Drop US aggregate."""
    latest = vintages()[-1]
    df = pd.read_csv(vintage_path(latest), dtype={"location": str})
    df["location"] = df["location"].str.zfill(2)
    df["date"] = pd.to_datetime(df["date"])
    df = df[df.location != "US"].copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["value"])


# ------------------------------------------------------------------ spatial
def spatial() -> None:
    _, fips2abbr, fips2pop = loc_map()
    df = load_final()
    df["season"] = df["date"].map(season_of)
    df = df[df.season.isin(("2023-24", "2024-25", "2025-26"))]
    df["abbr"] = df.location.map(fips2abbr)
    df["hhs"] = df.abbr.map(ABBR_TO_HHS)
    df["pop"] = df.location.map(fips2pop)
    df = df.dropna(subset=["hhs", "pop", "value"])

    # weekly log-growth per state
    rows = []
    for loc, g in df.groupby("location"):
        g = g.sort_values("date")
        v = g.value.to_numpy(float)
        if (v <= 0).all() or len(v) < 20:
            continue
        lg = np.log(np.maximum(v, 1.0))
        gr = np.diff(lg)
        dates = g.date.to_numpy()[1:]
        seas = g.season.to_numpy()[1:]
        hhs = g.hhs.iloc[0]
        pop = float(g["pop"].iloc[0])
        for i in range(len(gr) - 1):
            # epidemic-ish: skip summer floor
            if v[i + 1] < 20:
                continue
            rows.append((loc, seas[i], dates[i], hhs, pop,
                         gr[i], gr[i + 1], v[i + 1]))
    R = pd.DataFrame(rows, columns=["loc", "season", "date", "hhs", "pop",
                                    "g_t", "g_tp1", "level"])
    print(f"spatial observations: {len(R)} state-weeks\n")

    # national and regional leave-one-out growth at the SAME week
    nat, reg = {}, {}
    for (d, _), sub in R.groupby(["date", "season"]):
        w = sub["pop"].to_numpy()
        g = sub.g_t.to_numpy()
        tot = (w * g).sum()
        wsum = w.sum()
        for loc, p, gg, h in zip(sub["loc"], sub["pop"], sub.g_t, sub.hhs):
            nat[(d, loc)] = (tot - p * gg) / max(wsum - p, 1)
        for h, hs in sub.groupby("hhs"):
            ww, gg = hs["pop"].to_numpy(), hs.g_t.to_numpy()
            tot_r, wsum_r = (ww * gg).sum(), ww.sum()
            for loc, p, gval in zip(hs["loc"], hs["pop"], hs.g_t):
                if len(hs) < 3:
                    continue
                reg[(d, loc)] = (tot_r - p * gval) / max(wsum_r - p, 1)

    R["g_nat"] = [nat.get((d, loc), np.nan) for d, loc in zip(R.date, R["loc"])]
    R["g_reg"] = [reg.get((d, loc), np.nan) for d, loc in zip(R.date, R["loc"])]
    R = R.dropna(subset=["g_nat"])

    def r2(y, cols):
        M = np.column_stack([np.ones(len(y))] + cols)
        b, *_ = np.linalg.lstsq(M, y, rcond=None)
        return 1 - ((y - M @ b) ** 2).sum() / ((y - y.mean()) ** 2).sum()

    def _partial(a, b, c):
        ra = a - np.polyval(np.polyfit(c, a, 1), c)
        rb = b - np.polyval(np.polyfit(c, b, 1), c)
        if ra.std() < 1e-12 or rb.std() < 1e-12:
            return float("nan")
        return float(np.corrcoef(ra, rb)[0, 1])

    def loso(base, extra):
        """Train on two seasons, test the third. Mean ΔR² and RMSE reduction."""
        use = list(base) + list(extra)
        out = []
        for ho in ("2023-24", "2024-25", "2025-26"):
            tr = R[R.season != ho].dropna(subset=use)
            te = R[R.season == ho].dropna(subset=use)
            if len(tr) < 200 or len(te) < 200:
                continue
            ytr, yte = tr.g_tp1.to_numpy(), te.g_tp1.to_numpy()
            def fit(cols):
                M = np.column_stack([np.ones(len(tr))] + [tr[c].to_numpy() for c in cols])
                b, *_ = np.linalg.lstsq(M, ytr, rcond=None)
                Mt = np.column_stack([np.ones(len(te))] + [te[c].to_numpy() for c in cols])
                pred = Mt @ b
                rmse = np.sqrt(((yte - pred) ** 2).mean())
                r2te = 1 - ((yte - pred) ** 2).sum() / ((yte - ytr.mean()) ** 2).sum()
                return r2te, rmse
            r0, e0 = fit(["g_t"] + list(base))
            r1, e1 = fit(["g_t"] + list(base) + list(extra))
            out.append((ho, r0, r1, r1 - r0, e0, e1, 100 * (e0 - e1) / e0, len(te)))
        return out

    # Seasonal envelope control: week-of-season Fourier, the thing eps1/phi1
    # already give the PF. If national growth is just "it's January", this
    # swallows it. If it is THIS year's realised wave, it survives.
    R["wos"] = ((pd.to_datetime(R.date) - pd.to_datetime(R.season.str[:4] + "-08-01"))
                .dt.days // 7).astype(float)
    two_pi = 2 * np.pi / 52.0
    R["sin1"] = np.sin(two_pi * R.wos)
    R["cos1"] = np.cos(two_pi * R.wos)

    print("IN-SAMPLE incremental R² predicting g_{t+1}:")
    y = R.g_tp1.to_numpy()
    print(f"  AR(1) own g_t                         {r2(y, [R.g_t.to_numpy()]):.4f}")
    print(f"  AR(1) + Fourier seasonal              {r2(y, [R.g_t.to_numpy(), R.sin1.to_numpy(), R.cos1.to_numpy()]):.4f}")
    print(f"  + national leave-one-out g_t          {r2(y, [R.g_t.to_numpy(), R.g_nat.to_numpy()]):.4f}")
    print(f"  Fourier + national                    {r2(y, [R.g_t.to_numpy(), R.sin1.to_numpy(), R.cos1.to_numpy(), R.g_nat.to_numpy()]):.4f}")
    R2 = R.dropna(subset=["g_reg"])
    print(f"  + HHS-region leave-one-out g_t        "
          f"{r2(R2.g_tp1.to_numpy(), [R2.g_t.to_numpy(), R2.g_reg.to_numpy()]):.4f}  n={len(R2)}")
    print(f"  Fourier + region                      "
          f"{r2(R2.g_tp1.to_numpy(), [R2.g_t.to_numpy(), R2.sin1.to_numpy(), R2.cos1.to_numpy(), R2.g_reg.to_numpy()]):.4f}")
    print(f"  raw corr(own g_t, nat g_t)            {np.corrcoef(R.g_t, R.g_nat)[0,1]:+.3f}  (collinearity)")
    print(f"  partial corr(nat g_t, g_{{t+1}} | own g_t)  "
          f"{_partial(R.g_nat.to_numpy(), y, R.g_t.to_numpy()):+.3f}")

    print("\nLEAVE-ONE-SEASON-OUT  (AR+Fourier vs AR+Fourier+national):")
    print(f"{'held-out':>10}{'R2 seas':>9}{'R2 +nat':>10}{'dR2':>8}{'RMSE%':>8}{'n':>7}")
    for row in loso(["sin1", "cos1"], extra=["g_nat"]):
        ho, r0, r1, d, e0, e1, pct, n = row
        print(f"{ho:>10}{r0:9.3f}{r1:10.3f}{d:+8.3f}{pct:+8.1f}{n:7d}")
    # Turn-week slice: forecast window straddles this state's season peak
    peaks = {}
    for loc, g in R.groupby("loc"):
        for seas, gs in g.groupby("season"):
            if gs.level.max() < 50:
                continue
            peaks[(loc, seas)] = gs.loc[gs.level.idxmax(), "date"]
    R["turn"] = [
        (abs((pd.Timestamp(d) - peaks[k]).days) <= 21)
        if (k := (loc, seas)) in peaks else False
        for loc, seas, d in zip(R["loc"], R.season, R.date)
    ]
    print("\nTURN weeks (|t - state peak| <= 3wk) vs the rest, LOSO +national:")
    print(f"{'held-out':>10}{'slice':>10}{'n':>7}{'dR2':>8}{'RMSE%':>8}")
    for ho in ("2023-24", "2024-25", "2025-26"):
        for lab, mask in (("turn", True), ("other", False)):
            tr = R[(R.season != ho) & R.g_nat.notna()]
            te = R[(R.season == ho) & (R.turn == mask) & R.g_nat.notna()]
            if len(tr) < 200 or len(te) < 80:
                print(f"{ho:>10}{lab:>10}{len(te):7d}   (skip)")
                continue
            ytr, yte = tr.g_tp1.to_numpy(), te.g_tp1.to_numpy()
            def fit(cols):
                M = np.column_stack([np.ones(len(tr))] + [tr[c].to_numpy() for c in cols])
                b, *_ = np.linalg.lstsq(M, ytr, rcond=None)
                Mt = np.column_stack([np.ones(len(te))] + [te[c].to_numpy() for c in cols])
                pred = Mt @ b
                rmse = np.sqrt(((yte - pred) ** 2).mean())
                r2te = 1 - ((yte - pred) ** 2).sum() / max(((yte - ytr.mean()) ** 2).sum(), 1e-12)
                return r2te, rmse
            r0, e0 = fit(["g_t", "sin1", "cos1"])
            r1, e1 = fit(["g_t", "sin1", "cos1", "g_nat"])
            print(f"{ho:>10}{lab:>10}{len(te):7d}{r1-r0:+8.3f}{100*(e0-e1)/e0:+8.1f}")


# ------------------------------------------------------------------ nowcast
def nowcast() -> None:
    _, fips2abbr, _ = loc_map()
    vs = vintages()
    # pair consecutive vintages: first appearance of a (loc, week-ending)
    # vs the value in the LATEST vintage (settled)
    latest = pd.read_csv(vintage_path(vs[-1]), dtype={"location": str})
    latest["location"] = latest["location"].str.zfill(2)
    latest["date"] = pd.to_datetime(latest["date"])
    latest = latest[latest.location != "US"]
    settled = {(r.location, pd.Timestamp(r.date)): float(r.value)
               for r in latest.itertuples() if pd.notna(r.value) and r.value > 0}

    first = {}   # (loc, week) -> (asof, value)  first time this week appears
    asof_val = {}  # (asof, loc, week) -> value
    print(f"reading {len(vs)} vintages...", flush=True)
    for v in vs:
        df = pd.read_csv(vintage_path(v), dtype={"location": str},
                         usecols=["location", "date", "value"])
        df["location"] = df["location"].str.zfill(2)
        df["date"] = pd.to_datetime(df["date"])
        asof = pd.Timestamp(v)
        df = df[(df.location != "US") & (df.date <= asof)]
        for r in df.itertuples():
            if pd.isna(r.value) or r.value <= 0:
                continue
            key = (r.location, pd.Timestamp(r.date))
            asof_val[(asof, r.location, pd.Timestamp(r.date))] = float(r.value)
            if key not in first:
                first[key] = (asof, float(r.value))

    recs = []
    for (loc, week), (asof, y0) in first.items():
        yf = settled.get((loc, week))
        if yf is None:
            continue
        lag_days = (asof - week).days          # 0 = published same Saturday?
        recs.append((loc, fips2abbr.get(loc, "?"), week, asof,
                     season_of(week), y0, yf, y0 / yf, lag_days))
    C = pd.DataFrame(recs, columns=["loc", "abbr", "week", "asof", "season",
                                    "first", "final", "ratio", "lag_days"])
    # FluSight as-of is the Saturday week-ending; first issue of week T
    # typically appears in the vintage dated T or T+7. Keep in-season.
    C = C[C.season.isin(("2023-24", "2024-25", "2025-26"))]
    print(f"first-issue records: {len(C)}")
    print(f"  median first/final: {C.ratio.median():.3f}   "
          f"p10 {C.ratio.quantile(0.10):.3f}   "
          f"share < 0.95: {(C.ratio < 0.95).mean():.1%}")

    # lag-1 only (the newest observation at as-of): week == asof
    L1 = C[C["week"] == C["asof"]]
    L2 = C[(C["asof"] - C["week"]).dt.days == 7]
    print(f"\nlag 0 (week==asof): n={len(L1)}  median ratio {L1.ratio.median():.3f}"
          f"  p10 {L1.ratio.quantile(0.10):.3f}" if len(L1) else "\nlag 0: none")
    print(f"lag 7d:             n={len(L2)}  median ratio {L2.ratio.median():.3f}"
          f"  p10 {L2.ratio.quantile(0.10):.3f}")

    # Predictability: LOSO state-level median completeness
    print("\nLOSO completeness nowcast of FIRST issue -> settled")
    print("(apply 1/c_hat to first-issue; score as |log error| vs doing nothing)\n")
    print(f"{'held-out':>10}{'n':>7}{'naive MdAPE':>13}{'nowcast MdAPE':>15}"
          f"{'naive mean |log|':>18}{'nowcast':>10}{'% red':>8}")
    target = L2 if len(L2) > 100 else C
    for ho in ("2023-24", "2024-25", "2025-26"):
        tr = target[target.season != ho]
        te = target[target.season == ho]
        if len(tr) < 50 or len(te) < 50:
            continue
        c_state = tr.groupby("loc").ratio.median()
        c_nat = tr.ratio.median()
        chat = te["loc"].map(lambda x: c_state.get(x, c_nat))
        # nowcast: first / c_hat   (if first is 0.95 of final, c_hat=0.95, nowcast=final)
        pred = te["first"].to_numpy() / np.maximum(chat.to_numpy(), 0.3)
        y = te.final.to_numpy()
        naive = te["first"].to_numpy()
        def mdape(p):
            return np.median(np.abs(p - y) / y)
        def mlog(p):
            return np.mean(np.abs(np.log(np.maximum(p, 1)) - np.log(y)))
        md0, md1 = mdape(naive), mdape(pred)
        ml0, ml1 = mlog(naive), mlog(pred)
        print(f"{ho:>10}{len(te):7d}{md0:13.3f}{md1:15.3f}"
              f"{ml0:18.4f}{ml1:10.4f}{100*(ml0-ml1)/ml0:+8.1f}")

    # Analogue-scale implication: the analogue forecast is last_point * ratio.
    # A multiplicative bias c on the last point is a multiplicative bias c on
    # EVERY horizon. Report the typical |log c| -- that is the median-term
    # bias the nowcast would remove from the analogue.
    if len(L2):
        logc = np.log(np.clip(L2.ratio, 0.3, 1.5))
        print(f"\nAnalogue implication (lag-7d first issue):")
        print(f"  median log-bias of uncorrected last point: {np.median(logc):+.4f}  "
              f"({100*(np.exp(np.median(logc))-1):+.1f}% multiplicative)")
        print(f"  mean |log-bias|: {np.mean(np.abs(logc)):.4f}")
        print("  Because analogue is last_point * historical_ratio, this bias")
        print("  lands on ALL four horizons equally. The PF is less exposed:")
        print("  one bad point in ~26 is one likelihood term, not a scale.")

    # State heterogeneity -- the reason a per-state c is even plausible
    print("\nPer-state median first/final (lag-7d, pooled seasons), most incomplete:")
    if len(L2):
        s = L2.groupby("abbr").ratio.agg(["median", "count"])
        s = s[s["count"] >= 10].sort_values("median")
        print(s.head(8).to_string())
        print("...")
        print(s.tail(4).to_string())


if __name__ == "__main__":
    print("=" * 70)
    print("SPATIAL")
    print("=" * 70)
    spatial()
    print("\n" + "=" * 70)
    print("NOWCAST / COMPLETENESS")
    print("=" * 70)
    nowcast()
