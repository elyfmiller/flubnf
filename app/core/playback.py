"""Season playback: one JSON payload per stored retrospective week.

GET /api/retro/{season}/playback/{asof} serves what a viewer needs to replay
a submission day: every member's quantile fan, the equal-weight ensemble,
the settled full-season truth, the CDC's own submitted comparators
(FluSight-baseline and FluSight-ensemble, including their US national cell),
and running relWIS stats.

Conventions inherited from the rest of the app (do not re-derive):
  * hub reference_date = our asof + 7 days; hub horizon 0..3 = our "1".."4"
    (the join verified in scripts/ensemble_vs_team.py of the archive repo).
  * relWIS uses THE frozen formula: cells need settled truth > 0 and a
    positive median, and the denominator is scoring._baseline_cells -- the
    validated baseline construction, never a hand-rolled one.
  * stats exclude the US national cell: it is the sum of all states and
    dominates any sum-based aggregate (~50x a state's WIS).

Caching: each built payload lands in <season_root>/playback_cache/<asof>.json
and is served from there while fresh (mtime vs every samples.json at or
before the asof, and vs scores.json). Per-week score aggregates for models
not covered by scores.json live in playback_cache/stats_cells.json so
cumulative stats never rescore old weeks twice.
"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.core import ensemble as ens
from app.core.scoring import _baseline_cells, load_truth
from flubnf.settings import HUB
from flubnf.wis import wis as wis_fn

OFFICIAL = ("FluSight-baseline", "FluSight-ensemble")
TARGET = "wk inc flu hosp"
HORIZONS = ("1", "2", "3", "4")


class UnknownWeek(FileNotFoundError):
    """Requested asof has no completed samples.json in this season root."""


# ---------------------------------------------------------------- season root

def season_weeks(root: Path) -> list:
    """Completed weeks in a season root, ascending."""
    return sorted(p.parent.name
                  for p in (root / "weeks").glob("*/samples.json"))


def _samples_path(root: Path, asof: str) -> Path:
    return root / "weeks" / asof / "samples.json"


def _cache_dir(root: Path) -> Path:
    return root / "playback_cache"


# ------------------------------------------------------------- member models

def _member_q(samples_by_h: dict) -> dict:
    """ens.member_quantiles_from_samples, vectorized: one np.quantile call
    per horizon instead of 23 (each re-sorts 30k samples; a season replay
    makes ~5,000 such cells). Same formula, bit-identical output -- guarded
    by test_vectorized_member_quantiles_match_reference."""
    out = {}
    for h in HORIZONS:
        s = np.asarray(samples_by_h.get(h, []), float)
        s = s[np.isfinite(s)]
        if s.size:
            out[h] = dict(zip(ens.QL, map(float, np.quantile(s, ens.QL))))
    return out


def _week_model_quantiles(root: Path, asof: str) -> dict:
    """{model: {location: {"1".."4": {float level: value}}}} for one stored
    week: sample-shaped members (pf, pf2s) through the member-quantile
    formula, the analogue's stored quantiles as-is, and an equal-weight
    vincentized ensemble of whichever members cover each location."""
    d = json.loads(_samples_path(root, asof).read_text())
    out = {}
    for m in ("pf", "pf2s"):
        if m in d:
            out[m] = {loc: _member_q(s) for loc, s in d[m].items()}
    if "analogue" in d:
        out["analogue"] = {loc: {h: {float(k): float(v)
                                     for k, v in q.items()}
                                 for h, q in qs.items()}
                           for loc, qs in d["analogue"].items()}
    members = {m: q for m, q in out.items()}
    if members:
        blend = {}
        all_locs = set().union(*(set(q) for q in members.values()))
        for loc in all_locs:
            have = {m: q[loc] for m, q in members.items() if loc in q}
            b = ens.vincentize(have, weights=ens.equal_weights(have))
            if b:
                blend[loc] = b
        out["ensemble"] = blend
    return out


# ----------------------------------------------------------- official models

def _official_quantiles(model: str, asof: str, f2n: dict) -> dict | None:
    """{location_name_or_US: {"1".."4": {float level: value}}} parsed from the
    hub's submitted file for this week, or None when the file is absent
    (early weeks, sparse clones). f2n scopes which locations are kept."""
    ref = (pd.Timestamp(asof) + timedelta(days=7)).date().isoformat()
    fp = HUB / "model-output" / model / f"{ref}-{model}.csv"
    if not fp.is_file():
        return None
    d = pd.read_csv(fp, dtype={"location": str, "output_type_id": str})
    if "target" not in d.columns:
        return None
    d = d[(d.target == TARGET) & (d.output_type == "quantile")]
    d["location"] = d["location"].str.zfill(2)
    out: dict = {}
    for r in d.itertuples():
        name = f2n.get(r.location)
        if name is None:
            continue
        try:
            h = int(r.horizon)
            L, v = float(r.output_type_id), float(r.value)
        except (TypeError, ValueError):
            continue
        if not 0 <= h <= 3:
            continue
        out.setdefault(name, {}).setdefault(str(h + 1), {})[L] = v
    return out


# ------------------------------------------------------------------- scoring

def _score_block(qbl: dict, asof: str, truth: dict, n2f: dict,
                 bases: dict) -> tuple:
    """(wis_sum, base_sum, n_cells) under the frozen formula: truth > 0,
    median > 0, cell present in the validated baseline."""
    T = pd.Timestamp(asof)
    ws = bs = 0.0
    n = 0
    for loc, hq in qbl.items():
        fips = n2f.get(loc)
        if not fips:
            continue
        for h in HORIZONS:
            q = hq.get(h)
            if not q:
                continue
            actual = truth.get((fips, T + timedelta(days=7 * int(h))))
            if actual is None or actual <= 0 or q.get(0.5, 0) <= 0:
                continue
            base = bases.get((fips, asof, int(h) - 1))
            if base is None:
                continue
            try:
                w = float(wis_fn(q, actual).wis)
            except Exception:
                continue
            ws += w
            bs += float(base)
            n += 1
    return ws, bs, n


def _week_aggregates(asof: str, truth: dict, n2f: dict, model_q: dict,
                     official_q: dict) -> dict:
    """{model: {"wis", "base", "n"}} for one week, members and officials
    alike, US excluded (it swamps sums)."""
    locs = set().union(*(set(q) for q in model_q.values())) if model_q else set()
    fips_set = {n2f[l] for l in locs if l in n2f}
    try:
        bases = _baseline_cells(asof, fips_set, truth) if fips_set else {}
    except Exception:
        bases = {}
    agg = {}
    for m, qbl in model_q.items():
        ws, bs, n = _score_block(qbl, asof, truth, n2f, bases)
        agg[m] = {"wis": ws, "base": bs, "n": n}
    for om, oq in official_q.items():
        if oq is None:
            continue
        states = {k: v for k, v in oq.items() if k != "US" and k in locs}
        ws, bs, n = _score_block(states, asof, truth, n2f, bases)
        agg[om] = {"wis": ws, "base": bs, "n": n}
    return agg


def _season_scores(root: Path):
    """scores.json as a DataFrame, or None when absent/empty/invalid."""
    sf = root / "scores.json"
    if not sf.is_file():
        return None
    try:
        df = pd.read_json(sf)
    except Exception:
        return None
    if df.empty or "model" not in df.columns:
        return None
    return df


def _stats(root: Path, season: str, asof: str, truth: dict, n2f: dict,
           model_q: dict, official_q: dict) -> dict:
    """{model: {"week_rel", "cum_rel"}}. Members already covered by the
    season's scores.json are read from it (one formula, computed once);
    everything else (pf2s, officials, unscored roots) is scored on the fly
    with per-week aggregates cached in playback_cache/stats_cells.json."""
    scores = _season_scores(root)
    scored_models = set(scores.model.unique()) if scores is not None else set()
    upto = [w for w in season_weeks(root) if w <= asof]
    cf = _cache_dir(root) / "stats_cells.json"
    try:
        cache = json.loads(cf.read_text())
        assert isinstance(cache.get("weeks"), dict)
    except Exception:
        cache = {"weeks": {}}
    f2n_all = {v: k for k, v in n2f.items()}
    f2n_all["US"] = "US"
    dirty = False
    aggs = {}
    for w in upto:
        m = _samples_path(root, w).stat().st_mtime
        e = cache["weeks"].get(w)
        if e and e.get("mtime") == m:
            aggs[w] = e["agg"]
            continue
        mq = model_q if w == asof else _week_model_quantiles(root, w)
        oq = (official_q if w == asof else
              {om: _official_quantiles(om, w, f2n_all) for om in OFFICIAL})
        aggs[w] = _week_aggregates(w, truth, n2f, mq, oq)
        cache["weeks"][w] = {"mtime": m, "agg": aggs[w]}
        dirty = True
    if dirty:
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps(cache))

    def _rel(ws, bs):
        return (ws / bs) if bs else None

    stats = {}
    wanted = list(model_q) + [om for om in OFFICIAL
                              if any(om in aggs[w] for w in upto)]
    for m in wanted:
        if m in scored_models:
            g = scores[scores.model == m]
            # bracket indexing: .asof is a pandas *method*, never the column
            wk = g[g["asof"] == asof]
            cum = g[g["asof"] <= asof]
            stats[m] = {"week_rel": _rel(wk.wis.sum(), wk.base_wis.sum()),
                        "cum_rel": _rel(cum.wis.sum(), cum.base_wis.sum())}
        else:
            wk = aggs.get(asof, {}).get(m)
            cw = sum(aggs[w][m]["wis"] for w in upto if m in aggs[w])
            cb = sum(aggs[w][m]["base"] for w in upto if m in aggs[w])
            stats[m] = {"week_rel": _rel(wk["wis"], wk["base"]) if wk else None,
                        "cum_rel": _rel(cw, cb)}
    return stats


# ------------------------------------------------------------------- payload

def _strq(hq: dict) -> dict:
    return {h: {str(float(L)): float(v) for L, v in q.items()}
            for h, q in hq.items()}


def _truth_series(truth: dict, fips: str, lo: str, hi: str) -> list:
    pts = [(str(d.date()), float(v)) for (f, d), v in truth.items()
           if f == fips and lo <= str(d.date()) <= hi]
    return [[d, v] for d, v in sorted(pts)]


def build_week(root: Path, season: str, asof: str) -> dict:
    """Assemble (or serve from cache) the playback payload for one week."""
    sp = _samples_path(root, asof)
    if not sp.is_file():
        known = season_weeks(root)
        raise UnknownWeek(
            f"{season}: no completed week {asof}."
            + (f" Known weeks: {known[0]}..{known[-1]}" if known
               else " No weeks completed yet."))
    cf = _cache_dir(root) / f"{asof}.json"
    newest = max([_samples_path(root, w).stat().st_mtime
                  for w in season_weeks(root) if w <= asof]
                 + ([(root / "scores.json").stat().st_mtime]
                    if (root / "scores.json").is_file() else []))
    if cf.is_file() and cf.stat().st_mtime >= newest:
        try:
            payload = json.loads(cf.read_text())
            # A payload cached before the official comparator files were
            # fetched must rebuild once they exist: Update data healing the
            # sparse clone changes no samples mtime, so timestamps alone
            # cannot see it (field-found on the first laptop).
            from datetime import date as _d, timedelta as _td
            ref = (_d.fromisoformat(asof) + _td(days=7)).isoformat()
            missing_now_present = any(
                name not in payload.get("official", {})
                and (HUB / "model-output" / name / f"{ref}-{name}.csv").is_file()
                for name in ("FluSight-baseline", "FluSight-ensemble"))
            if not missing_now_present:
                return payload
        except Exception:
            pass                       # corrupt cache: rebuild below

    truth, n2f = load_truth()
    model_q = _week_model_quantiles(root, asof)
    locs = sorted(set().union(*(set(q) for q in model_q.values()))
                  if model_q else set())
    f2n = {n2f[l]: l for l in locs if l in n2f}
    f2n["US"] = "US"
    official_q = {om: _official_quantiles(om, asof, f2n) for om in OFFICIAL}

    from app.core.retro import season_bounds
    lo, hi = season_bounds(season)
    hi_ext = (pd.Timestamp(hi) + timedelta(days=28)).date().isoformat()
    truth_locs = list(locs)
    if any(oq for oq in official_q.values()):
        truth_locs.append("US")
    truth_out = {}
    for name in truth_locs:
        fips = "US" if name == "US" else n2f.get(name)
        if fips:
            truth_out[name] = _truth_series(truth, fips, lo, hi_ext)

    payload = {
        "asof": asof,
        "locations": locs,
        "truth": truth_out,
        "models": {m: {loc: _strq(hq) for loc, hq in qbl.items()}
                   for m, qbl in model_q.items()},
        "official": {om: {name: _strq(hq) for name, hq in oq.items()}
                     for om, oq in official_q.items() if oq},
        "stats": _stats(root, season, asof, truth, n2f, model_q, official_q),
    }
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps(payload))
    return payload
