"""Multi-season data-processing audit: every known trap, checked empirically."""
import sys, glob, numpy as np, pandas as pd
sys.path.insert(0,'.')
from pathlib import Path
from flubnf.settings import ARCHIVE, HUB
issues, ok = [], []

# 1. vintage inventory: gaps within seasons
vints = sorted(p.name.split('_')[-1].removesuffix('.csv')
               for p in ARCHIVE.glob('target-hospital-admissions_*.csv'))
d = pd.to_datetime(pd.Series(vints))
gaps = d.diff().dt.days
big = [(d[i-1].date(), d[i].date(), int(g)) for i, g in enumerate(gaps) if g and g > 14]
ok.append(f"vintages: {len(vints)} from {vints[0]} to {vints[-1]}")
for a,b,g in big: issues.append(f"vintage gap {a} -> {b} ({g} d) — seed dates must avoid; preflight exists")

# 2. week-ending convention: all Saturdays?
t = pd.read_csv(ARCHIVE/f'target-hospital-admissions_{vints[-1]}.csv')
dates = pd.to_datetime(t['date'] if 'date' in t.columns else t['week_ending_date'])
dows = dates.dt.dayofweek.unique()
(ok if set(dows)=={5} else issues).append(
    f"week-ending day(s): {sorted(dows)} {'(all Saturday)' if set(dows)=={5} else '— MIXED — normalize!'}")

# 3. join integrity: truth locations vs locations.csv
locs = pd.read_csv(HUB/'auxiliary-data/locations.csv', dtype=str)
tl = set(t['location'].astype(str).str.zfill(2))
ll = set(locs['location'].astype(str).str.zfill(2))
extra, missing = tl-ll, ll-tl
if extra: issues.append(f"truth has location codes NOT in locations.csv: {sorted(extra)[:5]}")
else: ok.append("join: every truth location resolves in locations.csv (zero-padded)")
# zero-pad trap
raw = set(t['location'].astype(str))
if any(len(x)==1 for x in raw): issues.append("UNPADDED location codes in truth — zfill required on every join")
else: ok.append("location codes arrive zero-padded")

# 4. value sanity across ALL vintages: negatives, NaN, dtype
bad_neg, bad_nan = [], []
for v in vints:
    tv = pd.read_csv(ARCHIVE/f'target-hospital-admissions_{v}.csv')
    col = 'value'
    x = pd.to_numeric(tv[col], errors='coerce')
    if (x<0).any(): bad_neg.append((v, int((x<0).sum())))
    if x.isna().sum() > 0: bad_nan.append((v, int(x.isna().sum())))
if bad_neg: issues.append(f"NEGATIVE admissions in {len(bad_neg)} vintages e.g. {bad_neg[:3]}")
else: ok.append("no negative values in any of the vintages")
if bad_nan: issues.append(f"NaN values in {len(bad_nan)} vintages e.g. {bad_nan[:3]}")
else: ok.append("no NaNs in any vintage")

# 5. duplicates: (location, date) unique within each vintage?
dup = []
for v in vints[-6:]:
    tv = pd.read_csv(ARCHIVE/f'target-hospital-admissions_{v}.csv')
    dcol = 'date' if 'date' in tv.columns else 'week_ending_date'
    n = tv.duplicated(subset=['location', dcol]).sum()
    if n: dup.append((v, int(n)))
if dup: issues.append(f"duplicate (location, week) rows: {dup}")
else: ok.append("no duplicate (location, week) rows (last 6 vintages)")

# 6. population drift: hub locations.csv vs any vendored copy
vendored = glob.glob('data/**/locations*.csv', recursive=True) + glob.glob('flubnf/**/locations*.csv', recursive=True)
if vendored:
    for vf in vendored[:3]:
        vv = pd.read_csv(vf, dtype=str)
        m = locs.merge(vv, on='location', suffixes=('_hub','_vend'))
        if 'population_hub' in m.columns and 'population_vend' in m.columns:
            diff = m[m.population_hub != m.population_vend]
            if len(diff): issues.append(f"POPULATION DRIFT {vf}: {len(diff)} rows differ (e.g. {diff.iloc[0]['location']})")
            else: ok.append(f"vendored {vf} matches hub populations")
else: ok.append("no vendored locations.csv found — hub file is sole source")

# 7. cross-season continuity: does the LATEST vintage cover all seasons back to 2022?
dcol = 'date' if 'date' in t.columns else 'week_ending_date'
span = pd.to_datetime(t[dcol])
ok.append(f"latest vintage spans {span.min().date()} -> {span.max().date()} "
          f"({(span.max()-span.min()).days//7} weeks) — multi-season fits read ONE vintage, no stitching")
# per-location week gaps inside the latest vintage
gapcount = 0
for loc, g in t.groupby('location'):
    dd = pd.to_datetime(g[dcol]).sort_values().diff().dt.days.dropna()
    gapcount += int((dd > 7).sum())
if gapcount: issues.append(f"within-vintage week gaps across locations: {gapcount} (multi-season fits will interpolate SILENTLY unless handled)")
else: ok.append("no within-vintage week gaps in the latest vintage")

# 8. revision behavior (backfill): quantify on the last 8 vintage pairs
revs = []
for v1, v2 in zip(vints[-9:-1], vints[-8:]):
    a = pd.read_csv(ARCHIVE/f'target-hospital-admissions_{v1}.csv')
    b = pd.read_csv(ARCHIVE/f'target-hospital-admissions_{v2}.csv')
    dc = 'date' if 'date' in a.columns else 'week_ending_date'
    m = a.merge(b, on=['location', dc], suffixes=('_old','_new'))
    ch = m[m.value_old != m.value_new]
    if len(m): revs.append(len(ch)/len(m))
ok.append(f"revision rate between consecutive vintages: median {np.median(revs):.1%} of cells (backfill handling stays mandatory)")

print("DATA AUDIT — multi-season accuracy")
print("="*60)
print(f"\nPASS ({len(ok)}):")
for o in ok: print(f"  + {o}")
print(f"\nFINDINGS ({len(issues)}):")
for i in issues: print(f"  ! {i}")
