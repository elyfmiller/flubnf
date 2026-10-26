"""The historical-ceiling arm's readings (AMENDMENT3_HIST.md sections 4, 6
and 7) from hist_arm.py's output.

    report_hist.py <H.pkl> [--boot 2000]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import report as R

REFS = ["none", "clip 15x", "shrink 15x", "clip 10x"]
ARMS = ["hist max", "hist 0.975", "hist max+shrink 15x", "hist max+clip 15x",
        "hist max+shrink 10x"]
SECONDARY = ["histF max", "histF max+shrink 15x"]
PAIR, S15, C15 = "hist max+shrink 15x", "shrink 15x", "clip 15x"
HS = (0, 1, 2, 3)


def subsets(c: pd.DataFrame) -> None:
    c["month"] = pd.to_datetime(c["asof"]).dt.month
    first8 = {s: sorted(c[c.season == s]["asof"].unique())[:8] for s in c.season.unique()}
    c["early24"] = [a in first8[s] for s, a in zip(c.season, c["asof"])]
    c["sepnov"] = c.month.isin([9, 10, 11])
    c["oct"] = c.month == 10
    c["mgroup"] = np.where(c.month.isin([8, 9, 10]), "Sep-Oct",
                           np.where(c.month.isin([11, 12, 1]), "Nov-Jan", "Feb-May"))


def verdict(ok: bool, fav: bool = False) -> str:
    return "HOLDS" if ok else ("FAVOURABLE MISS" if fav else "FAILS")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("h")
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()
    X = pd.read_pickle(a.h)
    c, b, r = X["cells"], X["blocks"], X["ratios"]
    subsets(c)
    b["month"] = pd.to_datetime(b["asof"]).dt.month
    first8 = {s: sorted(b[b.season == s]["asof"].unique())[:8] for s in b.season.unique()}
    b["early24"] = [x in first8[s] for s, x in zip(b.season, b["asof"])]
    b["oct"] = b.month == 10
    rule = {k: c[c.rule == k] for k in REFS + ARMS + SECONDARY}
    seasons = sorted(c.season.unique())
    nweeks = c["asof"].nunique()
    print(f"{a.h}: {nweeks} weeks (checks A3-D3 passed on every one, else the run stops), "
          f"{len(rule['none'])} cells per rule; early24 {c[c.early24]['asof'].nunique()} weeks, "
          f"Sep-Nov {c[c.sepnov]['asof'].nunique()}, October {c[c.oct]['asof'].nunique()}")

    print(f"\n{'rule':22s} relWIS   log   c50  c80  c95 |  >30x h3/rec h3/med | "
          + " ".join(f"{s:>7s}" for s in seasons)
          + " | early24 (c95) Sep-Nov    Oct   rest |   h0    h1    h2    h3")
    for k in REFS + ARMS + SECONDARY:
        x = rule[k]
        p, g = R.pooled(x), R.gate(x)
        bys = " ".join(f"{R.pooled(x[x.season == s])['rel']:7.3f}" for s in seasons)
        e = R.pooled(x[x.early24])
        bh = " ".join(f"{R.pooled(x[x.horizon == h])['rel']:.3f}" for h in HS)
        print(f"{k:22s} {p['rel']:.4f} {p['log']:.4f} {p['c50']:.2f} {p['c80']:.2f} {p['c95']:.3f} | "
              f"{100 * g['over30']:4.1f}% {g['tail_med']:5.1f} {g['band_med']:6.2f} | {bys} | "
              f"{e['rel']:.4f} ({e['c95']:.3f}) {R.pooled(x[x.sepnov])['rel']:.4f} "
              f"{R.pooled(x[x.oct])['rel']:.4f} {R.pooled(x[~x.early24])['rel']:.4f} | {bh}")

    print(f"\nweek-cluster bootstrap ({a.boot}), arm minus reference, natural [95%] | log [95%]:")
    D = {}
    for k in ARMS:
        for ref in REFS:
            d = R.boot_diff(rule[k], rule[ref], a.boot)
            e = R.boot_diff(rule[k][rule[k].early24], rule[ref][rule[ref].early24], a.boot)
            D[(k, ref)] = d
            D[(k, ref, "early")] = e
            print(f"  {k:20s} - {ref:10s} {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}] | {d[3]:+.4f} "
                  f"[{d[4]:+.4f}, {d[5]:+.4f}]   early24 {e[0]:+.4f} [{e[1]:+.4f}, {e[2]:+.4f}] | "
                  f"{e[3]:+.4f} [{e[4]:+.4f}, {e[5]:+.4f}]")
    for k, ref in (("histF max", "hist max"), ("histF max+shrink 15x", PAIR)):
        d = R.boot_diff(rule[k], rule[ref], a.boot)
        print(f"  {k:20s} - {ref:20s} {d[0]:+.5f} [{d[1]:+.5f}, {d[2]:+.5f}] | {d[3]:+.5f} "
              f"[{d[4]:+.5f}, {d[5]:+.5f}]  (settled against vintage ratios)")

    print("\nblocks the ceiling touched (any level changed / the 97.5% itself clipped / collapsed "
          "to the median), share by horizon:")
    b["c975_max"] = b.q975_max != b.q975
    b["c975_975"] = b.q975_975 != b.q975
    for lab, m in [("all 84", b.index == b.index), ("early24", b.early24), ("October", b.oct)] + \
            [(s, b.season == s) for s in seasons]:
        bb = b[m]
        row = []
        for tag, t, q, col in (("max", "touched_max", "c975_max", "collapsed_max"),
                               ("0.975", "touched_975", "c975_975", "collapsed_975")):
            row.append(f"{tag}: " + " ".join(
                f"h{h} {100 * bb[bb.horizon == h][t].mean():4.1f}/{100 * bb[bb.horizon == h][q].mean():4.1f}"
                f"/{100 * bb[bb.horizon == h][col].mean():.1f}" for h in HS))
        print(f"  {lab:8s} " + " || ".join(row))
    print(f"  the pairing's rows differ from shrink 15x's in "
          + " ".join(f"h{h} {100 * b[b.horizon == h].pair_differs_s15.mean():.1f}%" for h in HS)
          + " of blocks (October: "
          + " ".join(f"h{h} {100 * b[b.oct & (b.horizon == h)].pair_differs_s15.mean():.1f}%" for h in HS) + ")")

    print("\nthe ceiling's ratios over the recent level (vintage), by horizon:")
    v = r[r.source == "v"].copy()
    v["month"] = pd.to_datetime(v["asof"]).dt.month
    v["early24"] = [x in first8[s] for s, x in zip(v.season, v["asof"])]
    for lvl in (1.0, 0.975):
        vv = v[v.level == lvl]
        t = vv.groupby("horizon").ratio
        e = vv[vv.early24].groupby("horizon").ratio
        print(f"  level {lvl:g}: median over the 84 weeks " + " ".join(f"{t.median()[h]:.2f}" for h in HS)
              + " (10th-90th " + " ".join(f"{t.quantile(.1)[h]:.1f}-{t.quantile(.9)[h]:.1f}" for h in HS)
              + "); early24 median " + " ".join(f"{e.median()[h]:.2f}" for h in HS))
        for asof, g in vv[vv.month == 10].groupby("asof"):
            gg = g.set_index("horizon")
            print(f"    October {asof}: " + " ".join(f"{gg.ratio[h]:.2f}" for h in HS)
                  + f" (pool {int(gg.pool[0])})")
        bym = vv.groupby(["month", "horizon"]).ratio.median().unstack()
        print("    by as-of month (median): " + "; ".join(
            f"{m:02d} " + " ".join(f"{bym.loc[m, h]:.1f}" for h in HS)
            for m in [9, 10, 11, 12, 1, 2, 3, 4, 5] if m in bym.index))
    pools = v[v.level == 1.0].groupby("season").pool
    print("  pool sizes (h0) by season: " + "; ".join(
        f"{s} median {pools.median()[s]:.0f} (min {pools.min()[s]:.0f})" for s in seasons))

    j = r[r.source == "v"].merge(r[r.source == "f"], on=["season", "asof", "level", "horizon"],
                                 suffixes=("_v", "_f"))
    j["rd"] = j.ratio_f / j.ratio_v - 1
    for lvl in (1.0, 0.975):
        jj = j[j.level == lvl]
        w = jj.loc[jj.rd.abs().idxmax()]
        print(f"  settled against vintage, level {lvl:g}: median |relative difference| "
              f"{100 * jj.rd.abs().median():.3f}%, 90th {100 * jj.rd.abs().quantile(.9):.2f}%, "
              f"max {100 * w.rd:+.2f}% ({w['asof']} h{int(w.horizon)}); identical in "
              f"{100 * (jj.rd == 0).mean():.0f}% of week-horizons")

    print("\nthe pairing's natural WIS gain over shrink 15x by as-of month group:")
    jp = rule[PAIR].merge(rule[S15], on=R.KEY, suffixes=("_p", "_s"))
    jp["gain"] = jp.wis_s - jp.wis_p
    tot = jp.gain.sum()
    base = jp.base_wis_p.sum()
    for grp in ("Sep-Oct", "Nov-Jan", "Feb-May"):
        gg = jp[jp.mgroup_p == grp]
        print(f"  {grp}: {gg['asof'].nunique()} weeks, gain {gg.gain.sum():+.1f} "
              f"({100 * gg.gain.sum() / tot if tot else float('nan'):.0f}% of {tot:+.1f}), "
              f"{gg.gain.sum() / base:+.4f} relWIS")

    # predictions and the decision
    P = {k: R.pooled(rule[k]) for k in rule}
    out = []
    d = D[("hist max", "none")]
    out.append(("P1", verdict(d[0] <= 0 and d[2] <= 0),
                f"hist max - none {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}]"))
    gain = (P[S15]["rel"] - P[PAIR]["rel"]) / P[S15]["rel"]
    out.append(("P2a", verdict(0.005 <= gain <= 0.015, gain > 0.015),
                f"pairing below shrink 15x by {100 * gain:.2f}%"))
    d = D[(PAIR, C15)]
    out.append(("P2b", verdict(d[1] <= 0 <= d[2], d[2] < 0),
                f"pairing - clip 15x {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}]"))
    po, so = R.pooled(rule[PAIR][rule[PAIR].oct]), R.pooled(rule[S15][rule[S15].oct])
    out.append(("P3a", verdict(abs(po["rel"] - so["rel"]) <= 0.002),
                f"October pairing {po['rel']:.4f} against shrink 15x {so['rel']:.4f}"))
    vm = v[(v.level == 1.0) & (v.month == 10)].pivot(index="asof", columns="horizon", values="ratio")
    above = (vm[[1, 2, 3]] > 15).all(axis=1)
    out.append(("P3b", "REPORTED", f"{int(above.sum())} of {len(vm)} October as-ofs with the maximum "
                f"above 15 at h1-h3"))
    nj = jp[jp.mgroup_p == "Nov-Jan"].gain.sum()
    share = nj / tot if tot > 0 else float("nan")
    out.append(("P3c", verdict(tot > 0 and share > 0.5),
                f"Nov-Jan share of the gain {100 * share:.0f}% (total {tot:+.1f})"))
    out.append(("P4", verdict(P["hist 0.975"]["c95"] <= P["none"]["c95"] - 0.02
                              and P["hist 0.975"]["log"] > P["none"]["log"]),
                f"0.975 c95 {P['hist 0.975']['c95']:.3f} against none {P['none']['c95']:.3f}; "
                f"log {P['hist 0.975']['log']:.4f} against {P['none']['log']:.4f}"))
    sh = {h: b[b.horizon == h].touched_max.mean() for h in HS}
    so_ = {h: b[b.oct & (b.horizon == h)].touched_max.mean() for h in HS}
    out.append(("Q1", verdict(sh[0] < 0.05 and 0.05 <= sh[3] <= 0.30 and max(so_.values()) < 0.05),
                f"touched h0 {100 * sh[0]:.1f}%, h3 {100 * sh[3]:.1f}%, October max "
                f"{100 * max(so_.values()):.1f}%"))
    jj = j[j.level == 1.0]
    dF = abs(P["histF max"]["rel"] - P["hist max"]["rel"])
    out.append(("Q2", verdict(jj.rd.abs().median() < 0.01 and dF < 0.001),
                f"median |rel diff| {100 * jj.rd.abs().median():.3f}%, |histF - hist| {dF:.5f}"))
    bs3 = {s: b[(b.season == s) & (b.horizon == 3)].touched_max.mean() for s in seasons}
    out.append(("Q3", verdict(max(bs3, key=bs3.get) == "2023-24"),
                "h3 touched by season " + ", ".join(f"{s} {100 * x:.1f}%" for s, x in bs3.items())))
    print("\npredictions (AMENDMENT3 section 6):")
    for name, v_, txt in out:
        print(f"  {name:4s} {v_:16s} {txt}")

    ok = {n: v_ for n, v_, _ in out}
    p_ok = all(ok[n] in ("HOLDS", "FAVOURABLE MISS") for n in ("P1", "P2a", "P2b", "P3a", "P3c"))
    i_ = P[PAIR]["rel"] <= P[S15]["rel"] and P[PAIR]["log"] <= P[S15]["log"]
    ii = {s: R.pooled(rule[PAIR][rule[PAIR].season == s])["rel"]
          - R.pooled(rule[S15][rule[S15].season == s])["rel"] for s in seasons}
    pe, se_ = R.pooled(rule[PAIR][rule[PAIR].early24]), R.pooled(rule[S15][rule[S15].early24])
    iii = (P[PAIR]["c95"] >= P[S15]["c95"] - 0.010, pe["c95"] >= se_["c95"] - 0.010)
    iv = pe["rel"] - se_["rel"] <= 0.005
    print("\nthe decision for 2026-10-28 (AMENDMENT3 section 7):")
    print(f"  (1) checks: passed on all {nweeks} weeks")
    print(f"  (2) P1, P2, P3: {'hold' if p_ok else 'DO NOT ALL HOLD'}")
    print(f"  (3i) pairing {P[PAIR]['rel']:.4f} / {P[PAIR]['log']:.4f} against shrink 15x "
          f"{P[S15]['rel']:.4f} / {P[S15]['log']:.4f}: {'ok' if i_ else 'FAILS'}")
    print(f"  (3ii) by season " + ", ".join(f"{s} {x:+.4f}" for s, x in ii.items())
          + f": {'ok' if max(ii.values()) <= 0.010 else 'FAILS'}")
    print(f"  (3iii) c95 {P[PAIR]['c95']:.3f} against {P[S15]['c95']:.3f}; early24 {pe['c95']:.3f} "
          f"against {se_['c95']:.3f}: {'ok' if all(iii) else 'FAILS'}")
    print(f"  (3iv) early24 {pe['rel']:.4f} against {se_['rel']:.4f} ({pe['rel'] - se_['rel']:+.4f}): "
          f"{'ok' if iv else 'FAILS'}")
    passed = p_ok and i_ and max(ii.values()) <= 0.010 and all(iii) and iv
    print(f"  => {'PASSES' if passed else 'DOES NOT PASS'}")


if __name__ == "__main__":
    main()
