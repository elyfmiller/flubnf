"""The code check of prereg c9587ab57ab6db4b, part one: the ceiling's ratios
re-implemented in pandas from the written rule and compared with
flubnf.tailcap.history_ratios on every replay week's vintage, at the
maximum and at 0.975."""
import math, sys
from datetime import date, timedelta
import numpy as np, pandas as pd
from app.core import retro, data as D
from flubnf import tailcap as TC

def season_of(d): return d.year if d.month >= 8 else d.year - 1

def indep(t, asof, level):
    a = date.fromisoformat(asof); ew, se = a.isocalendar()[1], season_of(a)
    pool = {h: [] for h in range(4)}
    for f, g in t[t.location != "US"].groupby("location"):
        g = g[np.isfinite(g.value)].sort_values("date")
        d = [date.fromisoformat(str(x)[:10]) for x in g.date]; v = g.value.to_numpy(float)
        base = pd.Series(v).rolling(3, min_periods=1).mean().to_numpy()
        at = dict(zip(d, v))
        for i, w in enumerate(d):
            if season_of(w) >= se: continue
            dw = abs(w.isocalendar()[1] - ew)
            if min(dw, 52 - dw) > 2 or not base[i] >= 10: continue
            for h in range(4):
                y = at.get(w + timedelta(weeks=h + 1))
                if y is not None: pool[h].append(y / base[i])
    return {h: (float("nan") if not r else max(r) if level >= 1 else float(np.quantile(r, level)))
            for h, r in pool.items()}

bad = n = 0
for s in ["2023-24", "2024-25", "2025-26", "2026-27"]:
    for asof in retro.season_vintages(s):
        t = pd.read_csv(D.vintage_path(asof), dtype={"location": str})
        t = t[t.date.astype(str).str[:10] <= asof].copy(); t["location"] = t.location.str.zfill(2)
        hs = {f: [(str(r.date)[:10], float(r.value)) for r in g.sort_values("date").itertuples() if np.isfinite(r.value)]
              for f, g in t.groupby("location") if f != "US"}
        for level in (1.0, 0.975):
            a, b = TC.history_ratios(hs, asof, level=level), indep(t, asof, level)
            n += 1
            for h in range(4):
                x, y = a[h], b[h]
                if not ((math.isnan(x) and math.isnan(y)) or abs(x - y) <= 1e-9 * max(1, abs(y))):
                    bad += 1; print("MISMATCH", s, asof, level, h, x, y)
print(f"ratio check: {n} week-levels, {bad} mismatches")
