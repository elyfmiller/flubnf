"""The screen's readings from score_arm.py's cells (PREREG.md sections 5, 6).

    report.py <arm.cells.pkl> [--vs <C0.cells.pkl>] [--boot 2000]

(A) every output rule at the run's narrowing exponent (k = 0.7): pooled
relWIS on both scales (ratios of sums), coverage, the gate, by season, by
horizon, September-November as-of weeks against the rest; the week-cluster
bootstrap of each rule minus none and minus clip 15x; the "free" line;
leave-one-season-out over the whole grid. (B) with --vs, the arm against
C0 at each one's leave-one-season-out choice and at the live settings.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

KEY = ["season", "asof", "location", "horizon"]


def load(path: str) -> pd.DataFrame:
    d = pd.read_pickle(path)
    d["month"] = pd.to_datetime(d["asof"]).dt.month
    d["early"] = d["month"].isin([9, 10, 11])
    return d


def rules_frame(d: pd.DataFrame) -> pd.DataFrame:
    """One row per (k, rule, cell): the grid, the growth caps, the filter."""
    g = d[d["kind"].isin(["grid", "growth"])].copy()
    g["rule"] = np.where(g["mode"] == "none", "none",
                         g["mode"] + " " + g["n"].map(lambda x: f"{x:g}") +
                         np.where(g["mode"] == "growth", "x/wk", "x"))
    f = d[d["kind"] == "filter"].copy()
    f["k"], f["rule"], f["k_exact"] = 1.0, "filter alone", True
    return pd.concat([g, f], ignore_index=True)


def pooled(x: pd.DataFrame) -> dict:
    return {"rel": x.wis.sum() / x.base_wis.sum(),
            "log": x.log_wis.sum() / x.base_log_wis.sum(),
            "c50": x.cov50.mean(), "c80": x.cov80.mean(), "c95": x.cov95.mean(),
            "n": len(x)}


def gate(x: pd.DataFrame) -> dict:
    h3 = x[x.horizon == 3]
    t = h3.tail_over_recent.dropna()
    m = h3.tail_over_median.dropna()
    return {"over30": float((t > 30).mean()) if len(t) else np.nan,
            "tail_med": float(t.median()) if len(t) else np.nan,
            "band_med": float(m.median()) if len(m) else np.nan}


def boot_diff(a: pd.DataFrame, b: pd.DataFrame, n: int, seed: int = 20261022) -> tuple:
    """Week-cluster bootstrap of pooled relWIS (natural, log) a minus b on
    their common cells; returns (d_nat, lo, hi, d_log, lo, hi)."""
    j = a.merge(b, on=KEY, suffixes=("_a", "_b"))
    wk = j.groupby(["season", "asof"]).agg(
        wa=("wis_a", "sum"), wb=("wis_b", "sum"), ba=("base_wis_a", "sum"),
        la=("log_wis_a", "sum"), lb=("log_wis_b", "sum"), bl=("base_log_wis_a", "sum"))
    W = wk.to_numpy()
    def stat(M):
        return (M[:, 0].sum() - M[:, 1].sum()) / M[:, 2].sum(), (M[:, 3].sum() - M[:, 4].sum()) / M[:, 5].sum()
    d0 = stat(W)
    rng = np.random.default_rng(seed)
    bs = np.array([stat(W[rng.integers(0, len(W), len(W))]) for _ in range(n)])
    lo, hi = np.percentile(bs, [2.5, 97.5], axis=0)
    return d0[0], lo[0], hi[0], d0[1], lo[1], hi[1]


def loso(r: pd.DataFrame) -> tuple:
    """Leave-one-season-out over (k, rule): the choice on the other two
    seasons (natural relWIS, log the tie-break), scored on the held-out one."""
    cand = r[r.rule != "filter alone"]
    agg = cand.groupby(["k", "rule", "season"]).agg(
        w=("wis", "sum"), b=("base_wis", "sum"), lw=("log_wis", "sum"), lb=("base_log_wis", "sum"))
    out, held = [], []
    for s in sorted(cand.season.unique()):
        tr = agg[agg.index.get_level_values("season") != s].groupby(level=[0, 1]).sum()
        tr["rel"] = tr.w / tr.b
        tr["log"] = tr.lw / tr.lb
        k, rule = tr.sort_values(["rel", "log"]).index[0]
        h = cand[(cand.k == k) & (cand.rule == rule) & (cand.season == s)]
        out.append((s, k, rule, pooled(h)))
        held.append(h)
    return out, pooled(pd.concat(held))


def table_a(r: pd.DataFrame, k: float, nboot: int) -> None:
    x = r[(r.k == k) | (r.rule == "filter alone")]
    order = (["filter alone", "none"] + [f"shrink {n}x" for n in (8, 10, 15, 20, 30)]
             + [f"clip {n}x" for n in (8, 10, 15, 20, 30)] + [f"growth {g:g}x/wk" for g in (1.5, 2, 3)])
    base = x[x.rule == "none"]
    c15 = x[x.rule == "clip 15x"]
    print(f"\n(A) every rule at k = {k} (rows a live run would ship; ratios of sums; cells per rule {len(base)})")
    print(f"{'rule':16s} {'relWIS':>7s} {'log':>6s} {'c50':>5s} {'c80':>5s} {'c95':>5s} | "
          f"{'>30x':>5s} {'h3 97.5/recent':>14s} {'h3 97.5/med':>11s} | "
          + " ".join(f"{s:>7s}" for s in sorted(x.season.unique())) + f" {'Sep-Nov':>7s} {'rest':>6s}")
    rows = {}
    for rule in order:
        y = x[x.rule == rule]
        if y.empty:
            continue
        p, gt = pooled(y), gate(y)
        rows[rule] = (p, gt)
        bys = " ".join(f"{pooled(y[y.season == s])['rel']:7.3f}" for s in sorted(x.season.unique()))
        print(f"{rule:16s} {p['rel']:7.3f} {p['log']:6.3f} {p['c50']:5.2f} {p['c80']:5.2f} {p['c95']:5.2f} | "
              f"{gt['over30']:5.1%} {gt['tail_med']:14.1f} {gt['band_med']:11.2f} | {bys} "
              f"{pooled(y[y.early])['rel']:7.3f} {pooled(y[~y.early])['rel']:6.3f}")
    print("\nby horizon (natural relWIS):")
    for rule in ("none", "shrink 8x", "shrink 10x", "shrink 15x", "clip 15x"):
        y = x[x.rule == rule]
        if not y.empty:
            print(f"  {rule:12s} " + "  ".join(f"h{h} {pooled(y[y.horizon == h])['rel']:.3f}" for h in range(4)))
    print(f"\nweek-cluster bootstrap ({nboot}), pooled relWIS difference [95%], natural | log:")
    for rule in order[2:]:
        y = x[x.rule == rule]
        if y.empty:
            continue
        for ref_name, ref in (("none", base), ("clip 15x", c15)):
            if rule == ref_name:
                continue
            d = boot_diff(y, ref, nboot)
            print(f"  {rule:16s} minus {ref_name:8s} {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}] | "
                  f"{d[3]:+.4f} [{d[4]:+.4f}, {d[5]:+.4f}]")
    free = [n for n in (8, 10, 15, 20, 30)
            if f"shrink {n}x" in rows and rows[f"shrink {n}x"][0]["rel"] - rows["none"][0]["rel"] <= 0.010
            and rows[f"shrink {n}x"][0]["c95"] >= 0.90]
    print(f"\nfree line (shrink within 0.010 of none, 95% coverage >= 0.90): "
          f"{('smallest n = %gx' % min(free)) if free else 'no shrink n qualifies'}")


def steps(reg_path: str, c0_path: str, nboot: int) -> None:
    """Amendment R: from the registered member to the 2026-10-28
    candidates, one change at a time, each against REG on common cells."""
    reg, c0 = load(reg_path), load(c0_path)
    rr, rc = rules_frame(reg), rules_frame(c0)
    sel = [
        ("1 registered (to_date, w 0.5, k 1)", rr[(rr.k == 1.0) & (rr.rule == "none")], "exact"),
        ("2 + weight 0.25", reg[reg.kind == "json_secondary"], "pre-floor"),
        ("3 + stage-rule seed (k 1)", rc[(rc.k == 1.0) & (rc.rule == "none")], "approx."),
        ("4 + narrowing 0.7 (live 10-24)", rc[(rc.k == 0.7) & (rc.rule == "none")], "exact"),
    ] + [(f"5 + {m} {n}x", rc[(rc.k == 0.7) & (rc.rule == f"{m} {n}x")], "exact")
         for m in ("shrink", "clip") for n in (15, 10, 8)]
    ref = sel[0][1]
    seasons = sorted(ref.season.unique())
    print("\nAMENDMENT R: from the registered member to the candidates (each step on "
          "the cells it shares with step 1)")
    print(f"{'step':34s} {'kind':9s} {'relWIS':>7s} {'log':>6s} {'c50':>5s} {'c95':>5s} {'>30x':>6s} "
          f"{'h3 tail':>7s} | " + " ".join(f"{s:>7s}" for s in seasons)
          + " | minus step 1, natural [95%]       log [95%]")
    for name, x, kind in sel:
        x = x.merge(ref[KEY], on=KEY)
        p, g = pooled(x), gate(x)
        bys = " ".join(f"{pooled(x[x.season == s])['rel']:7.3f}" for s in seasons)
        if name.startswith("1 "):
            diff = ""
        else:
            dd = boot_diff(x, ref, nboot)
            diff = (f" {dd[0]:+.3f} [{dd[1]:+.3f}, {dd[2]:+.3f}]  {dd[3]:+.3f} [{dd[4]:+.3f}, {dd[5]:+.3f}]")
        print(f"{name:34s} {kind:9s} {p['rel']:7.3f} {p['log']:6.3f} {p['c50']:5.2f} {p['c95']:5.2f} "
              f"{g['over30']:6.1%} {g['tail_med']:7.1f} | {bys} |{diff}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cells")
    ap.add_argument("--vs", default="")
    ap.add_argument("--steps-from", default="", help="REG cells: print amendment R's table")
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()
    if a.steps_from:
        steps(a.steps_from, a.cells, a.boot)
        return
    d = load(a.cells)
    r = rules_frame(d)
    k_run = float(d[(d.kind == "grid") & (d.k_exact)].k.iloc[0])
    print(f"{a.cells}: {r["asof"].nunique()} weeks, seasons {sorted(r.season.unique())}, run k {k_run}")
    for kind in ("json_krun", "json_k1"):
        c = d[d.kind == kind]
        kk = k_run if kind == "json_krun" else 1.0
        g = r[(r.k == kk) & (r.rule == "none")]
        if len(c):
            print(f"check C: {kind} WIS {c.wis.sum():.1f} against the grid's k={kk} rows "
                  f"{g.wis.sum():.1f} (ratio {g.wis.sum() / c.wis.sum():.4f})")
    table_a(r, k_run, a.boot)
    if r.season.nunique() < 2:
        print("\nleave-one-season-out needs two seasons or more; skipped")
        return
    out, hp = loso(r)
    print("\nleave-one-season-out over k x rule:")
    for s, k, rule, p in out:
        print(f"  held out {s}: chose k {k:g}, {rule}; held-out relWIS {p['rel']:.3f}, log {p['log']:.3f}, c95 {p['c95']:.2f}")
    print(f"  pooled held-out: relWIS {hp['rel']:.3f}, log {hp['log']:.3f}, c95 {hp['c95']:.2f}")
    if a.vs:
        rc = rules_frame(load(a.vs))
        oc, hc = loso(rc)
        print(f"\n(B) against C0: held-out relWIS arm {hp['rel']:.3f} / C0 {hc['rel']:.3f}; "
              f"log {hp['log']:.3f} / {hc['log']:.3f}; c95 {hp['c95']:.2f} / {hc['c95']:.2f}")
        for (s, k, rule, p), (_, kc, rulec, pc) in zip(out, oc):
            print(f"  {s}: arm {p['rel']:.3f} (k {k:g}, {rule}) | C0 {pc['rel']:.3f} (k {kc:g}, {rulec}) "
                  f"| difference {p['rel'] - pc['rel']:+.3f}")
        kc, rulec = oc[-1][1], oc[-1][2]
        for (kk, rr) in ((kc, rulec), (k_run, "shrink 15x"), (k_run, "shrink 10x"), (1.0, "filter alone")):
            ya = r[(r.k == kk) & (r.rule == rr)] if rr != "filter alone" else r[r.rule == rr]
            yc = rc[(rc.k == kk) & (rc.rule == rr)] if rr != "filter alone" else rc[rc.rule == rr]
            if len(ya) and len(yc):
                dd = boot_diff(ya, yc, a.boot)
                print(f"  at k {kk:g}, {rr}: arm minus C0 {dd[0]:+.4f} [{dd[1]:+.4f}, {dd[2]:+.4f}] | "
                      f"log {dd[3]:+.4f} [{dd[4]:+.4f}, {dd[5]:+.4f}]")


if __name__ == "__main__":
    main()
