"""The ceiling arm's extra readings (logs/report_H_extra.txt): exact
coverage, coverage by season and horizon, the October mechanism.

    h_extra.py   (from the screen directory; reads arms/H_C0.pkl)
"""
import pandas as pd, numpy as np
import report as R
from report_hist import subsets
X = pd.read_pickle("arms/H_C0.pkl"); c = X["cells"]; subsets(c)
P, S, C, M, MC = "hist max+shrink 15x", "shrink 15x", "clip 15x", "hist max", "hist max+clip 15x"
r = {k: c[c.rule == k] for k in c.rule.unique()}
print("exact c95 all / early24 / Oct:")
for k in ("none", C, S, M, P, MC):
    x = r[k]; print(f"  {k:20s} {x.cov95.mean():.4f} / {x[x.early24].cov95.mean():.4f} / {x[x.oct].cov95.mean():.4f}   c50 {x.cov50.mean():.4f}")
print(f"  pair - s15 c95: all {r[P].cov95.mean()-r[S].cov95.mean():+.4f}, early24 {r[P][r[P].early24].cov95.mean()-r[S][r[S].early24].cov95.mean():+.4f}")
print("c95 by season, pairing / shrink 15x:", "; ".join(f"{s} {r[P][r[P].season==s].cov95.mean():.3f}/{r[S][r[S].season==s].cov95.mean():.3f}" for s in sorted(c.season.unique())))
print("c95 by horizon, pairing / shrink 15x / hist max / none:", "; ".join(f"h{h} {r[P][r[P].horizon==h].cov95.mean():.3f}/{r[S][r[S].horizon==h].cov95.mean():.3f}/{r[M][r[M].horizon==h].cov95.mean():.3f}/{r['none'][r['none'].horizon==h].cov95.mean():.3f}" for h in range(4)))
print("October relWIS by horizon, pairing / shrink 15x / none:")
for h in range(4):
    f = lambda k: R.pooled(r[k][r[k].oct & (r[k].horizon==h)])["rel"]
    print(f"  h{h} {f(P):.4f} / {f(S):.4f} / {f('none'):.4f}")
print("October per week relWIS, pairing / shrink 15x:", "; ".join(f"{a} {R.pooled(r[P][r[P]['asof']==a])['rel']:.3f}/{R.pooled(r[S][r[S]['asof']==a])['rel']:.3f}" for a in sorted(r[P][r[P].oct]["asof"].unique())))
b = X["blocks"]; b["month"] = pd.to_datetime(b["asof"]).dt.month; o = b[b.month == 10]
o = o.assign(w_pair=o.q975_pair/o["median"], w_s15=o.q975_s15/o["median"])
print("October h0-h3 typical 97.5%/median, pairing / shrink 15x:", "; ".join(f"h{h} {o[o.horizon==h].w_pair.median():.2f}/{o[o.horizon==h].w_s15.median():.2f}" for h in range(4)))
for k in (M, MC, P):
    d = R.boot_diff(r[k][r[k].oct], r[S][r[S].oct], 2000); print(f"October {k} - shrink 15x {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}] | {d[3]:+.4f}")
