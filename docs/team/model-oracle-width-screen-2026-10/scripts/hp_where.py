import sys
sys.path.insert(0, sys.argv[1])
import numpy as np, pandas as pd
import report as R
ra = R.rules_frame(R.load(sys.argv[2])); rc = R.rules_frame(R.load(sys.argv[3]))
k, rule = 0.7, "clip 15x"
a = ra[(ra.k == k) & (ra.rule == rule)]; c = rc[(rc.k == k) & (rc.rule == rule)]
j = a.merge(c, on=R.KEY, suffixes=("_a", "_c"))
j["month"] = pd.to_datetime(j["asof"]).dt.month
for s, g in j.groupby("season"):
    print(s, "total baseline", round(g.base_wis_a.sum()))
    m = g.groupby("month").agg(dw=("wis_a", "sum"), wc=("wis_c", "sum"), b=("base_wis_a", "sum"), c95a=("cov95_a", "mean"), c95c=("cov95_c", "mean"))
    m["d"] = (m.dw - m.wc) / g.base_wis_a.sum()
    m = m.reindex([9,10,11,12,1,2,3,4,5,6]).dropna()
    print("  month contribution to pooled diff:", " ".join(f"{int(i)}:{r.d:+.4f}(c95 {r.c95a:.2f}/{r.c95c:.2f})" for i, r in m.iterrows()))
    L = g.groupby("location").apply(lambda x: (x.wis_a.sum() - x.wis_c.sum()) / g.base_wis_a.sum()).sort_values()
    print("  best 5:", " ".join(f"{i} {v:+.4f}" for i, v in L.head(5).items()))
    print("  worst 5:", " ".join(f"{i} {v:+.4f}" for i, v in L.tail(5).items()))
