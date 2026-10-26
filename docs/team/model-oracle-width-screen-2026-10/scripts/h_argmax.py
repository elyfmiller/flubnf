"""Which history cell sets the ceiling's ratio for a few (as-of, horizon)
pairs (logs/report_H_argmax.txt). Run with SCREEN_WT = wt-hist, from it.
"""
import sys; sys.path.insert(0, "~/Documents/FluBNF-local/research/oracle-width-screen")
import pandas as pd, numpy as np
from app.core.data import vintage_path
from hist_arm import series_from_frame
def argmax(series, asof, h):
    a = pd.Timestamp(asof); ew = a.isocalendar()[1]; se = a.year if a.month >= 8 else a.year - 1
    best = (-1, None)
    for f, pairs in series.items():
        s = pd.Series([v for _, v in pairs], index=pd.to_datetime([d for d, _ in pairs])).sort_index()
        base = s.rolling(3, min_periods=1).mean()
        for i, w in enumerate(s.index):
            sw = w.year if w.month >= 8 else w.year - 1
            dw = abs(w.isocalendar()[1] - ew)
            if sw >= se or min(dw, 52 - dw) > 2 or base.iloc[i] < 10: continue
            t = w + pd.Timedelta(weeks=h + 1)
            if t in s.index:
                r = s[t] / base.iloc[i]
                if r > best[0]:
                    nb = s[t - pd.Timedelta(weeks=1)] if (t - pd.Timedelta(weeks=1)) in s.index else np.nan
                    na = s[t + pd.Timedelta(weeks=1)] if (t + pd.Timedelta(weeks=1)) in s.index else np.nan
                    best = (r, f, str(w.date()), base.iloc[i], s[t], nb, na)
    return best
for asof, h in [("2026-05-09", 0), ("2026-05-09", 1), ("2024-04-27", 0), ("2023-10-21", 3), ("2023-10-07", 1), ("2025-12-06", 3), ("2026-01-10", 3)]:
    ser = series_from_frame(pd.read_csv(vintage_path(asof), dtype={"location": str}), asof)
    r, f, w, b, y, nb, na = argmax(ser, asof, h)
    print(f"{asof} h{h}: max {r:.2f} from fips {f} base week {w} (recent {b:.1f}) -> {y:.0f} at W+{h+1} (neighbours {nb:.0f}, {na:.0f})")
