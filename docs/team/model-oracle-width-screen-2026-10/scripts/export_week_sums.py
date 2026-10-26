"""Week-level sums of the screen's scored cells, for review without the
per-cell tables: pooled relWIS (natural, log), coverage and report.py's
week-cluster bootstrap are all functions of these sums.

    export_week_sums.py <out_dir>

week_sums_H.csv and week_sums_X.csv (the post hoc arms): one row per
(season, asof, horizon, k, rule[, variant]); week_sums_<arm>.csv.gz for the
replayed arms C0, REG, R20, R22, HP, HS: one row per (season, asof, k,
rule), the four horizons summed (their by-horizon numbers are in the
reports). Each row:
n cells, sums of wis, base_wis, log_wis, base_log_wis, counts covered at
50/80/95, and for h3 the count with the 97.5% over 30x the recent level.
pooled relWIS = sum(wis) / sum(base_wis); log = sum(log_wis) /
sum(base_log_wis); coverage = sum(cov) / sum(n).
"""
import sys
from pathlib import Path

import pandas as pd

import report as R

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)


def sums(d, keys):
    d = d.copy()
    d["over30"] = (d.tail_over_recent > 30) & (d.horizon == 3)
    d["h3"] = d.horizon == 3
    g = d.groupby(keys, dropna=False).agg(
        n=("wis", "size"), wis=("wis", "sum"), base_wis=("base_wis", "sum"),
        log_wis=("log_wis", "sum"), base_log_wis=("base_log_wis", "sum"),
        cov50=("cov50", "sum"), cov80=("cov80", "sum"), cov95=("cov95", "sum"),
        h3_cells=("h3", "sum"), h3_over30=("over30", "sum")).reset_index()
    for c in ("wis", "base_wis", "log_wis", "base_log_wis"):
        g[c] = g[c].round(4)
    return g


for arm in ("C0", "REG", "R20", "R22", "HP", "HS"):
    r = R.rules_frame(R.load(f"arms/{arm}.cells.pkl"))
    g = sums(r, ["season", "asof", "k", "rule"])
    g.to_csv(OUT / f"week_sums_{arm}.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    print(arm, len(g))
for arm, p, keys in (("H", "arms/H_C0.pkl", ["season", "asof", "horizon", "k", "rule"]),
                     ("X", "arms/X_C0.pkl", ["season", "asof", "horizon", "k", "rule", "variant"])):
    g = sums(pd.read_pickle(p)["cells"], keys)
    g.to_csv(OUT / f"week_sums_{arm}.csv", index=False)
    print(arm, len(g))
X = pd.read_pickle("arms/H_C0.pkl")
X["ratios"].to_csv(OUT / "hist_ratios.csv", index=False)
b = X["blocks"]
b["c975_max"] = b.q975_max != b.q975
b["c975_975"] = b.q975_975 != b.q975
bt = b.groupby(["season", "asof", "horizon"]).agg(
    blocks=("fips", "size"), touched_max=("touched_max", "sum"), q975_clipped_max=("c975_max", "sum"),
    collapsed_max=("collapsed_max", "sum"), touched_975=("touched_975", "sum"),
    q975_clipped_975=("c975_975", "sum"), collapsed_975=("collapsed_975", "sum"),
    pair_differs_s15=("pair_differs_s15", "sum")).reset_index()
bt.to_csv(OUT / "hist_blocks_touched.csv", index=False)
print("ratios", len(X["ratios"]), "blocks", len(bt))
