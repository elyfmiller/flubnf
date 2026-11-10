"""Why the Groundhog lifts flat small states (round 2026-11-07, as-of 2026-10-31).

Usage: python gh_flat.py <flubnf clone> [asof] [reference_date]
Needs FLUBNF_HUB. Engine-free: the shipped Groundhog (flusurv aux at 0.5,
own share 0.5, size-matched kernel), reproduced from the as-of vintage, then
each pool's median ratio taken apart.
"""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(REPO))
ASOF = sys.argv[2] if len(sys.argv) > 2 else "2026-10-31"
REF = sys.argv[3] if len(sys.argv) > 3 else "2026-11-07"

import numpy as np                                    # noqa: E402
import pandas as pd                                   # noqa: E402
from flubnf import analogue as AN                     # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL # noqa: E402
from app.core.runs import RunSpec                     # noqa: E402
from app.core.engines import analogue as E            # noqa: E402

HUB = Path(os.environ["FLUBNF_HUB"])
FOCUS = ["Hawaii", "Alaska", "Montana", "Washington"]

locs_t = pd.read_csv(HUB / "auxiliary-data/locations.csv", dtype=str)
locs_t = locs_t[locs_t.location != "US"]
name2fips = dict(zip(locs_t.location_name, locs_t.location.str.zfill(2)))
all_states = [n for n in locs_t.location_name]

extra = {"aux_pools": E.shipped_aux_pools(), "local_pools": E.shipped_local_pools()}
spec = RunSpec(engine="analogue", forecast_date=ASOF, locations=all_states, extra=extra)
notes = {}
out = E.run(spec, notes=notes)

# the vintage, as _walk reads it
vpath = E._source(spec)[0]
t = pd.read_csv(vpath, dtype={"location": str})
t["location"] = t["location"].str.zfill(2)
t["date"] = pd.to_datetime(t["date"])
t = t[t.date <= pd.Timestamp(ASOF)]
bank = AN.build_bank(t.itertuples())
splice = E.splice_args(spec, bank)
local = E.local_args(spec)
pool = splice.pools[0]
print(f"vintage {Path(vpath).name}; aux {pool.label} weight {pool.weight} "
      f"shrink {pool.shrink:.4f}; local own_share {local.own_share} "
      f"kernel_sd {local.kernel_sd} ess_floor {local.ess_floor}")
print(f"notes: {notes}" if notes else "notes: none")

# the submitted file (medians only: the 10x shrink acts above the median)
sub_fp = HUB / f"model-output/NAU_PyBNF-GroundHogCGR/{REF}-NAU_PyBNF-GroundHogCGR.csv"
sub = None
if sub_fp.exists():
    sub = pd.read_csv(sub_fp, dtype={"location": str, "output_type_id": str})
    sub = sub[(sub.output_type == "quantile") & (sub.target == "wk inc flu hosp")]


def series(fips, n=6):
    g = t[t.location == fips].sort_values("date")
    v = pd.to_numeric(g.value, errors="coerce")
    return list(zip(g.date.dt.date.astype(str).iloc[-n:], v.iloc[-n:]))


def wq(vals, w, L=0.5):
    return AN.weighted_quantile(vals, w, [L])[float(L)]


ew, se = AN.epiweek(date.fromisoformat(ASOF)), AN.season_of(date.fromisoformat(ASOF))

print("\n=== Reproduction and decomposition, h3 = 4 weeks past the anchor")
for name in FOCUS:
    fips = name2fips[name]
    s = series(fips)
    anchor = float(s[-1][1])
    print(f"\n{name} (FIPS {fips}): last weeks " +
          ", ".join(f"{d[5:]} {v:g}" for d, v in s))
    obs3 = (s[-1][1] / s[-4][1]) ** (1 / 3)
    rep = out.get(name, {})
    meds = [rep.get(str(h), {}).get(0.5) for h in range(4)]
    line = "  reproduced medians h0-h3: " + ", ".join(
        f"{m:.1f}" if m is not None else "-" for m in meds)
    if sub is not None:
        ss = sub[(sub.location == fips) & (sub.output_type_id.astype(float) == 0.5)]
        if len(ss):
            line += "; submitted: " + ", ".join(
                f"{v:.1f}" for v in ss.sort_values("horizon").value)
        else:
            line += "; submitted: not in the file"
    print(line)
    print(f"  observed weekly growth, last 3 weeks: {obs3:.3f}")
    for h in (1, 4):
        r, lcs, v0 = AN.keyed_ratios(bank, ew, se, h, AN.DEFAULT_BANDWIDTH, with_anchor=True)
        w = AN.local_weights(lcs, fips, local, anchors=v0, target_anchor=anchor)
        own = lcs == fips
        adm = wq(r, w)
        own_q = wq(r[own], w[own]) if own.any() else float("nan")
        rest_q = wq(r[~own], w[~own])
        a = AN.donor_ratios(pool.bank, ew, se, h, bandwidth=AN.DEFAULT_BANDWIDTH
                            if pool.bandwidth is None else pool.bandwidth,
                            exclude_seasons=pool.exclude_seasons)
        a = a[np.isfinite(a) & (a > 0)]
        a = np.exp(pool.shrink * np.log(a))
        aux = float(np.quantile(a, 0.5))
        fin = (1 - pool.weight) * adm + pool.weight * aux
        g = lambda x: x ** (1 / h)                            # noqa: E731
        up = float(w[r > 1].sum() / w.sum())
        print(f"  h={h} wk: median ratio {fin:.3f} (x anchor = {anchor * fin:.1f}); "
              f"weekly {g(fin):.3f} | admissions {adm:.3f} [own {own_q:.3f} "
              f"(n={int(own.sum())}), rest {rest_q:.3f} (n={int((~own).sum())})] "
              f"| FluSurv-NET {aux:.3f} (n={a.size}) | admissions weight on "
              f"rising donors {up:.0%}")
        if h == 4 and own.any():
            # own donor cells with their ratios, by season
            cells = [((l, d), v) for (l, d), v in AN._donor_cells(
                bank, ew, se, AN.DEFAULT_BANDWIDTH, False,
                AN.resolve_donor_exclusions(AN.EXCLUDED_DONOR_SEASONS)) if l == fips]
            by = {}
            for (l, d), v in cells:
                v1 = bank.get((l, d + timedelta(days=7 * h)))
                if v1 and v1 > 0:
                    by.setdefault(AN.season_of(d), []).append(v1 / v)
            print("    own seasons' 4-week ratios: " + "; ".join(
                f"{s_}-{(s_ + 1) % 100:02d} " + " ".join(f"{x:.2f}" for x in xs)
                for s_, xs in sorted(by.items())))

print("\n=== Every state this round: implied weekly growth to h3 against observed")
rows = []
for name in all_states:
    fips = name2fips[name]
    rep = out.get(name)
    if not rep or "3" not in rep:
        continue
    s = series(fips, 4)
    if len(s) < 4 or not all(np.isfinite(v) and v > 0 for _, v in s):
        continue
    anchor = float(s[-1][1])
    gh = (rep["3"][0.5] / anchor) ** (1 / 4)
    ob = (s[-1][1] / s[0][1]) ** (1 / 3)
    rows.append((name, anchor, ob, gh))
df = pd.DataFrame(rows, columns=["state", "last", "obs_wk", "gh_wk"])
print(f"states {len(df)}; Groundhog weekly growth median {df.gh_wk.median():.3f}, "
      f"10th-90th {df.gh_wk.quantile(.1):.3f}-{df.gh_wk.quantile(.9):.3f}; "
      f"observed median {df.obs_wk.median():.3f}, 10th-90th "
      f"{df.obs_wk.quantile(.1):.3f}-{df.obs_wk.quantile(.9):.3f}")
print(f"Spearman(observed, Groundhog) = {df.obs_wk.rank().corr(df.gh_wk.rank()):.2f}; "
      f"Pearson on log = {np.log(df.obs_wk).corr(np.log(df.gh_wk)):.2f}")
flat = df[df.obs_wk <= 1.05].sort_values("obs_wk")
print(f"\nstates observed flat or falling (<= 1.05/wk): {len(flat)}")
print(flat.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
