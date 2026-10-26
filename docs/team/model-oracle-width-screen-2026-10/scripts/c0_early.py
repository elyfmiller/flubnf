"""C0's early-week reading (logs/report_C0_early.txt): each cap rule minus
none on the first 8 scoreable weeks of each season (24 weeks), at k 0.7.

    c0_early.py   (from the screen directory)
"""
import sys; sys.path.insert(0, ".")
from report import load, rules_frame, pooled, boot_diff
d = load("arms/C0.cells.pkl"); r = rules_frame(d); x = r[r.k == 0.7]
first = set()
for s, g in x.groupby("season"):
    first |= set(sorted(g["asof"].unique())[:8])
e = x[x["asof"].isin(first)]
base = e[e.rule == "none"]
print("early weeks (first 8 scoreable per season, 24 weeks), each rule minus none, natural [95%] | log [95%]")
for rule in ["shrink 8x", "shrink 10x", "shrink 15x", "shrink 20x", "clip 8x", "clip 10x", "clip 15x", "clip 20x"]:
    dd = boot_diff(e[e.rule == rule], base, 2000)
    print(f"  {rule:11s} {dd[0]:+.4f} [{dd[1]:+.4f}, {dd[2]:+.4f}] | {dd[3]:+.4f} [{dd[4]:+.4f}, {dd[5]:+.4f}]")
