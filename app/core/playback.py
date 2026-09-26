"""PRODUCTION: season-player payloads and their cache (server /api/retro
playback, report_season, site_build, retro.finalize_season).

Season playback: one JSON payload per stored retrospective week.

GET /api/retro/{season}/playback/{asof} serves what a viewer needs to replay
a submission day: every member's quantile fan, the settled truth, the CDC's
submitted comparators (FluSight-baseline and -ensemble, US cell included)
and running stats.

Conventions (do not re-derive):
  * hub reference_date = asof + 7; horizons are canonical "0".."3"
    (app.core.horizons).
  * scores use THE cell rule (scoring.cell_scored, FluSight's): settled
    truth (0 included), a forecast with finite quantiles (a median of 0
    included), a cell in the validated baseline (scoring._baseline_cells,
    never hand-rolled). Each model is scored on its own cells.
  * stats exclude US, fitted or not (us_national.POOLED_INCLUDES_US, applied
    via pooled_frame / pooled_locations): US is the sum of the 52 and would
    dominate any sum. The national score is reported separately.

THE STATS CONTRACT. payload["stats"][model], for every model the player
shows (the stored members, pf2s, FluSight-baseline and FluSight-ensemble):

  week_rel, cum_rel          relWIS: sum of WIS / sum of baseline WIS over
                             the model's scored cells, this week and
                             cumulatively through it (None: no cells)
  week_log_rel, cum_log_rel  the same on log-scale WIS (flubnf.wis.log_wis)
  week_cov, cum_cov          {"50", "80", "95"}: the fraction of the same
                             cells whose truth lies inside the central
                             interval (inclusive), or None
  week_n, cum_n              scored cell counts
  debug                      optional: where an official's scoring starves

FluSight-baseline's rel and log rel are 1.0 by definition; its coverage is
its own. A scores.json written before the log-scale and coverage columns (a
sealed root) used the earlier cell rule, so the members are scored here
instead (_stats); only what it alone holds (the retired blend) is read from
it, with None for those.

Caching: payloads live in <season_root>/playback_cache/<asof>.json, fresh
while newer than every samples file at or before asof, scores.json and the
truth. Per-week aggregates for models scores.json does not cover live in
stats_cells.json, keyed on the samples mtime, scores.json mtime, truth mtime
and the set of official files present, so late scores or officials propagate.
"""
from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.core import horizons as hz
from app.core import ensemble as ens
from app.core import retro as retro_store
from app.core import us_national as usn
from app.core import scoring
from app.core.scoring import (_baseline_cells, _baseline_log_cells,
                              load_truth)
from flubnf.settings import HUB

OFFICIAL = ("FluSight-baseline", "FluSight-ensemble")
#: bump when cached shapes or scoring logic change (v3: stored members only,
#: no blend; v4: the FluSight cell rule, log-scale relWIS and coverage)
CACHE_V = 4
TARGET = "wk inc flu hosp"
#: canonical hub horizons; app.core.horizons owns the convention
HORIZONS = hz.HORIZONS


class UnknownWeek(FileNotFoundError):
    """Requested asof has no completed samples.json in this season root."""


# ---------------------------------------------------------------- season root

def season_weeks(root: Path) -> list:
    """Completed weeks in a season root, ascending. Form-blind: a week
    stored as samples.json and one stored as samples.json.gz both count."""
    return [p.parent.name for p in retro_store.season_sample_files(root)]


def _samples_path(root: Path, asof: str) -> Path | None:
    """The week's stored samples file, either form, or None."""
    return retro_store.week_samples_path(root, asof)


def _cache_dir(root: Path) -> Path:
    return root / "playback_cache"


def _write_cache(cf: Path, obj) -> None:
    """Every cache write in this file: write beside, then os.replace. Readers
    treat presence as validity, so a torn multi-MB write would be served as
    complete; the .tmp sits beside its target to stay on one filesystem."""
    cf.parent.mkdir(parents=True, exist_ok=True)
    tmp = cf.with_name(cf.name + ".tmp")
    tmp.write_text(json.dumps(obj))
    os.replace(tmp, cf)


# ------------------------------------------------------------- member models

def _member_q(samples_by_h: dict) -> dict:
    """ens.member_quantiles_from_samples, vectorized (one np.quantile call
    per horizon instead of 23); bit-identical, which the tests check."""
    out = {}
    for h in HORIZONS:
        s = np.asarray(samples_by_h.get(h, []), float)
        s = s[np.isfinite(s)]
        if s.size:
            out[h] = dict(zip(ens.QL, map(float, np.quantile(s, ens.QL))))
    return out


def _week_model_quantiles(root: Path, asof: str) -> dict:
    """{model: {location: {"0".."3": {float level: value}}}} for one stored
    week: sample-shaped members (pf, pf2s) through the member-quantile
    formula and the analogue's stored quantiles as-is. No blend (retired).
    Read from the week's quantile sidecar, so draws are not parsed per cold cache."""
    return dict(retro_store.week_member_quantiles(root, asof))


# ----------------------------------------------------------- official models

def _official_files_present(asof: str) -> list:
    """Official models whose submitted hub file exists for this asof (the
    frozen join: reference_date = asof + 7). Existence only, no parsing:
    this doubles as the stats-cache validity key, so it must be cheap."""
    ref = (pd.Timestamp(asof) + timedelta(days=7)).date().isoformat()
    return [om for om in OFFICIAL
            if (HUB / "model-output" / om / f"{ref}-{om}.csv").is_file()]


def season_official_catalog(root: Path) -> list:
    """Official models that submitted in at least one week of the season:
    the player's availability catalog (listed models keep a live toggle in
    weeks they skipped; absent ones are disabled with the Update-data note)."""
    weeks = season_weeks(root)
    return [om for om in OFFICIAL
            if any(om in _official_files_present(w) for w in weeks)]


def _official_quantiles(model: str, asof: str, f2n: dict) -> dict | None:
    """{location_name_or_US: {"0".."3": {float level: value}}} parsed from the
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
        out.setdefault(name, {}).setdefault(str(h), {})[L] = v
    return out


# ------------------------------------------------------------------- scoring

#: the per-week aggregate a model's scored cells sum to (stats_cells.json)
_AGG_KEYS = ("wis", "base", "log", "base_log", "log_n",
             "c50", "c80", "c95", "cov_n", "n")


def _score_block(qbl: dict, asof: str, truth: dict, n2f: dict,
                 bases: dict, lbases: dict | None = None) -> dict:
    """The sums one week's cells give under THE cell rule
    (scoring.cell_scored): {"wis", "base", "n"} for relWIS, {"log",
    "base_log", "log_n"} over the cells with a baseline log score, and
    {"c50", "c80", "c95", "cov_n"} (cells covered, cells with every band)."""
    T = pd.Timestamp(asof)
    lbases = lbases or {}
    agg = dict.fromkeys(_AGG_KEYS, 0.0)
    for loc, hq in qbl.items():
        fips = n2f.get(loc)
        if not fips:
            continue
        for h in HORIZONS:
            q = hq.get(h)
            actual = truth.get(
                (fips, T + timedelta(days=7 * (int(h) + 1))))
            base = bases.get((fips, asof, int(h)))
            if not scoring.cell_scored(q, actual, base):
                continue
            m = scoring.cell_metrics(q, actual)
            if m is None:
                continue
            agg["wis"] += m["wis"]
            agg["base"] += float(base)
            agg["n"] += 1
            lb = lbases.get((fips, asof, int(h)))
            if lb is not None:
                agg["log"] += m["log_wis"]
                agg["base_log"] += float(lb)
                agg["log_n"] += 1
            covs = [m[c] for c in scoring.COVERAGE_COLUMNS]
            if all(c is not None for c in covs):
                for key, c in zip(("c50", "c80", "c95"), covs):
                    agg[key] += c
                agg["cov_n"] += 1
    agg["n"] = int(agg["n"])
    agg["log_n"] = int(agg["log_n"])
    agg["cov_n"] = int(agg["cov_n"])
    return agg


def _week_aggregates(asof: str, truth: dict, n2f: dict, model_q: dict,
                     official_q: dict) -> dict:
    """{model: _score_block sums} for one week, members and officials
    alike, US excluded for all of them (us_national.POOLED_INCLUDES_US)."""
    locs = usn.pooled_locations(
        set().union(*(set(q) for q in model_q.values())) if model_q else [])
    locs = set(locs)
    fips_set = {n2f[l] for l in locs if l in n2f}
    try:
        bases = _baseline_cells(asof, fips_set, truth) if fips_set else {}
    except Exception:
        bases = {}
    lbases = (_baseline_log_cells(asof, fips_set, truth)
              if bases else {})
    agg = {}
    for m, qbl in model_q.items():
        pooled = {k: v for k, v in qbl.items() if k in locs}
        agg[m] = _score_block(pooled, asof, truth, n2f, bases, lbases)
    for om, oq in official_q.items():
        if oq is None:
            continue
        states = {k: v for k, v in oq.items() if k in locs}
        agg[om] = _score_block(states, asof, truth, n2f, bases, lbases)
    return agg


def _sum_aggs(aggs: list) -> dict:
    out = dict.fromkeys(_AGG_KEYS, 0.0)
    for a in aggs:
        for k in _AGG_KEYS:
            out[k] += float(a.get(k, 0) or 0)
    return out


def _agg_stats(a: dict | None) -> dict:
    """{"rel", "log_rel", "cov", "n"} from summed aggregates (the scores
    frame's pooled_metrics, from sums): log_rel needs a baseline log score
    on every cell, cov every band on every cell; else None."""
    if not a or not a.get("n"):
        return {"rel": None, "log_rel": None, "cov": None,
                "n": int((a or {}).get("n", 0) or 0)}
    n = int(a["n"])
    rel = (a["wis"] / a["base"]) if a.get("base") else None
    log_rel = (a["log"] / a["base_log"]
               if a.get("log_n") == n and a.get("base_log") else None)
    cov = ({"50": a["c50"] / n, "80": a["c80"] / n, "95": a["c95"] / n}
           if a.get("cov_n") == n else None)
    return {"rel": rel, "log_rel": log_rel, "cov": cov, "n": n}


#: THE STATS CONTRACT's keys (module docstring), in order; "debug" may join
#: them for an official whose scoring starves
STATS_FIELDS = ("week_rel", "cum_rel", "week_log_rel", "cum_log_rel",
                "week_cov", "cum_cov", "week_n", "cum_n")


def _stat_entry(week: dict, cum: dict) -> dict:
    """One model's stats entry (THE STATS CONTRACT, module docstring) from
    this week's and the cumulative {"rel", "log_rel", "cov", "n"}."""
    return {"week_rel": week["rel"], "cum_rel": cum["rel"],
            "week_log_rel": week["log_rel"], "cum_log_rel": cum["log_rel"],
            "week_cov": week["cov"], "cum_cov": cum["cov"],
            "week_n": week["n"], "cum_n": cum["n"]}


def _season_scores(root: Path):
    """scores.json as a DataFrame, or None when absent/empty/invalid.

    The FULL frame, US included: pooled figures go through
    us_national.pooled_frame, the national one through us_national.resolve."""
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


def _stats_fresh(root: Path, asof: str, payload: dict,
                 truth: dict, n2f: dict) -> dict:
    """Recompute the stats block for a cache-served payload: quantile keys
    come back from JSON as strings; _stats wants floats."""
    def _fl(hq):
        return {h: {float(k): v for k, v in q.items()} for h, q in hq.items()}
    model_q = {m: {loc: _fl(hq) for loc, hq in locs.items()}
               for m, locs in payload.get("models", {}).items()}
    official_q = {om: ({loc: _fl(hq) for loc, hq in locs.items()} or None)
                  for om, locs in payload.get("official", {}).items()}
    for om in OFFICIAL:
        official_q.setdefault(om, None)
    season = root.name
    return _stats(root, season, asof, truth, n2f, model_q, official_q)


def _stats(root: Path, season: str, asof: str, truth: dict, n2f: dict,
           model_q: dict, official_q: dict) -> dict:
    """{model: THE STATS CONTRACT entry} (module docstring). Members
    already covered by the season's scores.json are read from it (one
    formula, computed once); everything else (pf2s, officials, unscored
    roots) is scored on the fly with per-week aggregates cached in
    playback_cache/stats_cells.json.

    A scores.json of an earlier retro.SCORES_V (a sealed root, or a live
    one before finalize_season rescores it) used the earlier cell rule, so
    its members are scored on the fly too and the table is one rule. It is
    read only for what cannot be: the retired blend, or a member no week
    scores here (no baseline in this clone)."""
    raw = _season_scores(root)
    current = retro_store.scores_frame_current(raw)
    # the pooled gate: a fitted US row must never move a pooled figure
    scores = usn.pooled_frame(raw)
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
    # sample mtimes cannot see a late scores.json or newly fetched officials,
    # so both join the per-week validity key
    sf = root / "scores.json"
    scores_mtime = sf.stat().st_mtime if sf.is_file() else None
    dirty = False
    aggs = {}
    for w in upto:
        sp = _samples_path(root, w)
        m = sp.stat().st_mtime if sp else 0
        offs = _official_files_present(w)
        e = cache["weeks"].get(w)
        from app.core.data import truth_mtime as _tm
        if (e and e.get("v") == CACHE_V and e.get("mtime") == m
                and e.get("scores_mtime") == scores_mtime
                and e.get("truth_mtime") == _tm()
                and e.get("officials") == offs):
            aggs[w] = e["agg"]
            continue
        mq = model_q if w == asof else _week_model_quantiles(root, w)
        oq = (official_q if w == asof else
              {om: _official_quantiles(om, w, f2n_all) for om in OFFICIAL})
        aggs[w] = _week_aggregates(w, truth, n2f, mq, oq)
        suspect = any(om in aggs[w] and aggs[w][om].get("base", 0) == 0
                      and oq.get(om) for om in OFFICIAL)
        if not suspect:
            # a zero-base official with a parsed file is a transient failure:
            # recompute next time rather than cache "pending"
            cache["weeks"][w] = {"mtime": m, "scores_mtime": scores_mtime,
                                 "truth_mtime": _tm(),
                                 "officials": offs, "agg": aggs[w], "v": CACHE_V}
            dirty = True
    if dirty:
        _write_cache(cf, cache)

    stats = {}
    wanted = list(model_q) + [om for om in OFFICIAL
                              if any(om in aggs[w] for w in upto)]
    # older scores.json files carry the retired blend's rows: show them as record
    if "ensemble" in scored_models and "ensemble" not in wanted:
        wanted.append("ensemble")
    for m in wanted:
        fly = [aggs[w][m] for w in upto if m in aggs[w]]
        if m in scored_models and (current
                                   or not _sum_aggs(fly)["n"]):
            g = scores[scores.model == m]
            # bracket indexing: .asof is a pandas *method*, never the column
            wk = g[g["asof"] == asof]
            cum = g[g["asof"] <= asof]
            stats[m] = _stat_entry(scoring.pooled_metrics(wk),
                                   scoring.pooled_metrics(cum))
        else:
            wk = aggs.get(asof, {}).get(m)
            cum = _sum_aggs(fly)
            stats[m] = _stat_entry(_agg_stats(wk), _agg_stats(cum))
            if m in OFFICIAL and stats[m]["cum_rel"] is None:
                # say where the official pipeline starves instead of "pending"
                stats[m]["debug"] = _official_debug(root, m, upto, n2f)
    return stats


def _official_debug(root: Path, model: str, upto: list, n2f: dict) -> str:
    """One line naming where the official-scoring pipeline starves."""
    try:
        f2n = {v: k for k, v in n2f.items()}
        f2n["US"] = "US"
        weeks_with_file = [w for w in upto if model in _official_files_present(w)]
        if not weeks_with_file:
            return (f"no {model} submission files for any of the {len(upto)} "
                    "weeks (hub clone missing model-output or outside the "
                    "competition window)")
        w = weeks_with_file[len(weeks_with_file) // 2]
        oq = _official_quantiles(model, w, f2n)
        if not oq:
            return f"file for {w} exists but parsed to zero quantile rows"
        truth, _ = load_truth()
        states = [k for k in oq if k != "US"]
        fips_set = {n2f[l] for l in states if l in n2f}
        try:
            bases = _baseline_cells(w, fips_set, truth)
        except Exception as e:
            return f"baseline construction failed for {w}: {str(e)[:120]}"
        if not bases:
            return f"baseline produced zero cells for {w} ({len(fips_set)} locations)"
        agg = _score_block({k: v for k, v in oq.items() if k != "US"},
                           w, truth, n2f, bases)
        return (f"probe week {w}: files {len(weeks_with_file)}/{len(upto)}, "
                f"parsed locations {len(states)}, baseline cells {len(bases)}, "
                f"scored cells {agg['n']}, wis {agg['wis']:.1f}, "
                f"base {agg['base']:.1f}")
    except Exception as e:
        return f"debug probe failed: {type(e).__name__}: {str(e)[:120]}"


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
    if sp is None:
        known = season_weeks(root)
        raise UnknownWeek(
            f"{season}: no completed week {asof}."
            + (f" Known weeks: {known[0]}..{known[-1]}" if known
               else " No weeks completed yet."))
    cf = _cache_dir(root) / f"{asof}.json"
    from app.core.data import truth_mtime
    newest = max([p.stat().st_mtime
                  for p in retro_store.season_sample_files(root)
                  if p.parent.name <= asof]
                 + ([(root / "scores.json").stat().st_mtime]
                    if (root / "scores.json").is_file() else [])
                 + [truth_mtime()])       # the payload embeds the truth
    if cf.is_file() and cf.stat().st_mtime >= newest:
        try:
            payload = json.loads(cf.read_text())
            if payload.get("_v") != CACHE_V:
                raise ValueError("cache version bump")
            # rebuild once official files appear (Update data changes no sample mtime)
            from datetime import date as _d, timedelta as _td
            ref = (_d.fromisoformat(asof) + _td(days=7)).isoformat()
            missing_now_present = any(
                name not in payload.get("official", {})
                and (HUB / "model-output" / name / f"{ref}-{name}.csv").is_file()
                for name in ("FluSight-baseline", "FluSight-ensemble"))
            # ... and once for payloads cached before US truth always rode along
            us_truth_missing = "US" not in payload.get("truth", {})
            if not missing_now_present and not us_truth_missing:
                # stats are recomputed on every serve; only quantiles/truth are cached
                truth_c, n2f_c = load_truth()
                payload["stats"] = _stats_fresh(root, asof, payload,
                                                truth_c, n2f_c)
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
    # US truth always rides along: the player lists US every week, including
    # weeks outside the officials' window (else empty axes)
    truth_locs = list(locs) + ["US"]
    truth_out = {}
    for name in truth_locs:
        fips = "US" if name == "US" else n2f.get(name)
        if fips:
            truth_out[name] = _truth_series(truth, fips, lo, hi_ext)

    payload = {
        "_v": CACHE_V,
        "asof": asof,
        "locations": locs,
        "truth": truth_out,
        "models": {m: {loc: _strq(hq) for loc, hq in qbl.items()}
                   for m, qbl in model_q.items()},
        "official": {om: {name: _strq(hq) for name, hq in oq.items()}
                     for om, oq in official_q.items() if oq},
        "stats": _stats(root, season, asof, truth, n2f, model_q, official_q),
    }
    _write_cache(cf, payload)
    return payload
