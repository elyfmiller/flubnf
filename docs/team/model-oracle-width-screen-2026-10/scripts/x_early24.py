import sys
sys.path.insert(0, "~/Documents/FluBNF-local/research/oracle-width-screen")
import pandas as pd
import report as R
from report_excl import arm
X = pd.read_pickle("arms/X_C0.pkl")
c = X["cells"]
first8 = {s: sorted(c[c.season == s]["asof"].unique())[:8] for s in c.season.unique()}
c["early24"] = [a in first8[s] for s, a in zip(c.season, c["asof"])]
c["sepnov"] = pd.to_datetime(c["asof"]).dt.month.isin([9, 10, 11])
print("weeks early24", c[c.early24]["asof"].nunique(), "Sep-Nov", c[c.sepnov]["asof"].nunique())
for variant in ("XP", "XS"):
    for rule in ("none", "clip 15x", "shrink 15x", "shrink 10x", "X40", "X30", "X20", "X15", "X40+shrink 15x"):
        x = arm(c, rule, variant)
        e, s = R.pooled(x[x.early24]), R.pooled(x[x.sepnov])
        line = f"{variant} {rule:15s} early24 {e['rel']:.4f}/{e['log']:.4f} c95 {e['c95']:.3f} | Sep-Nov {s['rel']:.4f}"
        if rule.startswith("X"):
            for ref in ("none", "shrink 15x"):
                y = arm(c, ref, variant)
                d = R.boot_diff(x[x.early24], y[y.early24], 2000)
                line += f" | -{ref} {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}]"
        print(line)
