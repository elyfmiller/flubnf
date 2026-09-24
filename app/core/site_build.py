"""PUBLIC SITE: what the site says (`flubnf site build`).

The public site generator (`flubnf site build` -> site/).

Reads app/state (season roots, the newest run bundle) and the hub clone and
writes a static, offline-openable page. Nothing is typed by hand. app/state
is gitignored, so the generated page IS the published evidence, reviewed as
a diff and committed: site.json is data-only and pretty-printed so a
rebuild's diff shows which numbers moved.

SCORES. Each shipped model's own relWIS (the PF and the Groundhog; an older
payload's stored "ensemble" is printed as stored). No stored scores.json is
read (a test pins this): every season is rescored from each week's playback
payload under the frozen cell rule and the validated baseline. A tree
replayed by the bare analogue (the seal) prints under the Groundhog's name
with nothing here to say so: publish from a Groundhog replay.

HARVESTED, NOT RESTATED: Methods (methods.html through the console's own
Jinja env, diagrams included); the home.html perf table's relWIS (the drift
alarm, cross_check) and any placement columns (none since the 2026-08-24
withdrawal, docs/archive/RELEASE-1.0.md); the BNGL source verbatim; the DOIs
in flubnf/sihrs_priors.py. A cross-check mismatch is reported loudly in the
payload's `consistency` block, never silently reconciled.
"""
from __future__ import annotations

import html as _html
import json
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core import horizons as hz

APP = Path(__file__).resolve().parents[1]
REPO = APP.parent
APP_STATE = APP / "state"
TEMPLATES = APP / "ui" / "templates"
STATIC = APP / "ui" / "static"
BNGL = REPO / "flubnf" / "templates" / "SIHRS_pop_min.bngl"

#: site/, not docs/: docs/ holds hand-written, unpublished markdown (Pages
#: deploys from an Actions artifact, so the name is free)
OUT_DIR = REPO / "site"

PAYLOAD_NAME = "site.json"
PAGE_NAME = "index.html"
PLOTLY_NAME = "plotly.min.js"

#: payload schema version; bump when a consumer-visible shape changes
PAYLOAD_VERSION = 1

#: canonical hub horizons; app.core.horizons owns the convention
HORIZONS = hz.HORIZONS
#: median, 50% and 80% intervals: the levels both sources store (a live
#: run's results.json keeps only the five display levels)
FAN_LEVELS = (0.1, 0.25, 0.5, 0.75, 0.9)
#: observed weeks shown behind the forecast
OBS_WEEKS = 14
#: a run must cover this many jurisdictions to become the outlook (never a smoke run)
MIN_OUTLOOK_LOCATIONS = 40

#: the two shipped models; "ensemble" only for older payloads with a stored blend
MODEL_ORDER = ("pf", "analogue", "ensemble")
OFFICIAL_ORDER = ("FluSight-baseline", "FluSight-ensemble")

#: search order, also the tiebreak: the lab's own runs (retro/) beat the
#: sealed three-season record when at least as complete
ROOT_ORDER = (("lab run", APP_STATE / "retro"),
              ("sealed record", APP_STATE / "retro_seal"))


class BuildError(RuntimeError):
    """The build cannot produce an honest page (no seasons, no truth)."""


# ---------------------------------------------------------------- discovery

#: the mechanistic column's two names: trees replayed before the Oracle step
#: (every sealed record) store the plain filter under pf
PF_LABEL_ORACLE = "Oracle SIHRS"
PF_LABEL_FILTER = "Particle filter alone"


def tree_carries_oracle(root: Path) -> bool:
    """Whether a season tree's pf is the Oracle SIHRS member: its run
    record says the step was applied, or its weeks carry the step's
    provenance (oracle.json, written beside every week the step touched)."""
    from app.core import retro
    root = Path(root)
    s = (retro.read_meta(root).get("settings") or {})
    if s.get("oracle") == "applied":
        return True
    if str(s.get("oracle") or "").startswith("none"):
        return False
    # a plain-filter run writes oracle.json too, with "applied": false
    try:
        for w in sorted((root / "weeks").iterdir())[:3]:
            f = w / "oracle.json"
            if f.is_file():
                try:
                    return json.loads(f.read_text()).get("applied") is True
                except (OSError, ValueError):
                    return False
        return False
    except OSError:
        return False


def _week_applied(week_dir: Path) -> bool:
    """Whether one stored week's oracle.json says the step was applied
    (presence alone is not enough)."""
    try:
        return json.loads((Path(week_dir) / "oracle.json").read_text()
                          ).get("applied") is True
    except (OSError, ValueError):
        return False


def pf_label(seasons: dict) -> str:
    """The season tables' name for pf: the Oracle SIHRS only when every
    published season stores the member."""
    if seasons and all(tree_carries_oracle(i["root"])
                       for i in seasons.values()):
        return PF_LABEL_ORACLE
    return PF_LABEL_FILTER


def tree_knobs(root) -> dict:
    """The model-knobs record of a season tree's run record ({} for a
    shipped tree or one from before the registry)."""
    from app.core import retro
    try:
        return retro.season_knobs(retro.read_meta(Path(root)))
    except Exception:
        return {}


def discover_seasons(roots=ROOT_ORDER) -> dict:
    """{season: {"root", "origin", "weeks"}} for every season with stored
    weeks, across every known root.

    A season is any YYYY-YY directory with completed weeks. The more
    complete root wins; ROOT_ORDER breaks ties.
    """
    from app.core import playback

    found: dict = {}
    for origin, root in roots:
        if not Path(root).is_dir():
            continue
        for d in sorted(Path(root).iterdir()):
            if not d.is_dir() or not re.fullmatch(r"\d{4}-\d{2}", d.name):
                continue
            if tree_knobs(d):
                continue    # a modified-settings replay never publishes
            try:
                weeks = playback.season_weeks(d)
            except Exception:
                weeks = []
            if not weeks:
                continue
            prev = found.get(d.name)
            if prev is None or len(weeks) > len(prev["weeks"]):
                found[d.name] = {"root": d, "origin": origin, "weeks": weeks}
    return dict(sorted(found.items()))


# ------------------------------------------------------------------ scoring

def _score_payload(payload: dict, truth, n2f, bases_cache: dict) -> dict:
    """{model: [wis_sum, base_sum, cells]} for one stored week.

    THE frozen cell rule for every model; US excluded for ours and theirs
    alike (us_national.POOLED_INCLUDES_US).

    One asymmetry, on purpose: our models are scored on their own cells (as
    the published record was), and the officials only on the cells our first
    model (MODEL_ORDER) scored, so a row compares like with like.
    """
    import pandas as pd
    from app.core.scoring import _baseline_cells
    from flubnf.wis import wis as wis_fn

    from app.core import us_national as usn

    def _pooled(block):
        return {k: v for k, v in (block or {}).items() if not usn.is_us(k)}

    asof = payload["asof"]
    T = pd.Timestamp(asof)
    ours = {m: _pooled(q) for m, q in (payload.get("models") or {}).items()}
    officials = {om: _pooled(q)
                 for om, q in (payload.get("official") or {}).items() if q}
    if not ours and not officials:
        return {}

    locs = set().union(*(set(b) for b in
                         list(ours.values()) + list(officials.values())))
    fips_set = {n2f[l] for l in locs if l in n2f}
    key = (asof, frozenset(fips_set))
    if key not in bases_cache:
        # a baseline that cannot be built fails the build (an empty dict would
        # silently drop the week from the published relWIS)
        try:
            bases_cache[key] = _baseline_cells(asof, fips_set, truth)
        except Exception as e:
            # BuildError: the CLI prints it as one line, not a traceback
            raise BuildError(
                f"baseline for week {asof} could not be built: {e}. "
                "The site build stops rather than publish a season that "
                "silently omits this week from its scores.") from e
    bases = bases_cache[key]

    def _score(qbl: dict, only: set | None):
        ws = bs = 0.0
        n = 0
        seen = set()
        for loc, hq in qbl.items():
            fips = n2f.get(loc)
            if not fips:
                continue
            for h in HORIZONS:
                raw = hq.get(h)
                if not raw:
                    continue
                cell = (fips, int(h))
                if only is not None and cell not in only:
                    continue
                try:
                    q = {float(k): float(v) for k, v in raw.items()}
                except (TypeError, ValueError):
                    continue
                actual = truth.get(
                    (fips, T + timedelta(days=7 * (int(h) + 1))))
                if actual is None or actual <= 0 or q.get(0.5, 0.0) <= 0:
                    continue
                base = bases.get((fips, asof, int(h)))
                if base is None:
                    continue
                try:
                    w = float(wis_fn(q, actual).wis)
                except Exception:
                    continue
                ws += w
                bs += float(base)
                n += 1
                seen.add(cell)
        return ([ws, bs, n] if n else None), seen

    out: dict = {}
    ref_cells: set | None = None
    for model in MODEL_ORDER:
        if model not in ours:
            continue
        acc, seen = _score(ours[model], None)
        if acc:
            out[model] = acc
            if ref_cells is None:
                ref_cells = seen
    for om, qbl in officials.items():
        acc, _seen = _score(qbl, ref_cells)
        if acc:
            out[om] = acc
    return out


def _rel(acc) -> float | None:
    return (acc[0] / acc[1]) if acc and acc[1] else None


def score_season(season: str, info: dict, truth, n2f,
                 bases_cache: dict | None = None) -> dict:
    """One season, week by week, from its stored playback payloads.

    Returns per-model totals and the per-week cumulative relWIS series.
    Payloads come through playback.build_week (cached or rebuilt), so no
    separate warming step is needed.
    """
    from app.core import playback

    bases_cache = {} if bases_cache is None else bases_cache
    totals: dict = {}
    weekly = []
    for asof in info["weeks"]:
        try:
            payload = playback.build_week(info["root"], season, asof)
        except Exception:
            continue
        wk = _score_payload(payload, truth, n2f, bases_cache)
        for model, acc in wk.items():
            t = totals.setdefault(model, [0.0, 0.0, 0])
            t[0] += acc[0]
            t[1] += acc[1]
            t[2] += acc[2]
        weekly.append({
            "asof": asof,
            "week": {m: round(_rel(a), 4) for m, a in wk.items()
                     if _rel(a) is not None},
            "cum": {m: round(_rel(t), 4) for m, t in totals.items()
                    if _rel(t) is not None},
        })
    return {
        "season": season,
        "origin": info["origin"],
        "root": str(Path(info["root"]).relative_to(REPO))
        if str(info["root"]).startswith(str(REPO)) else str(info["root"]),
        "weeks": len(info["weeks"]),
        "first_week": info["weeks"][0] if info["weeks"] else None,
        "last_week": info["weeks"][-1] if info["weeks"] else None,
        "scored_weeks": len(weekly),
        "models": {m: {"rel": round(_rel(a), 4), "cells": a[2]}
                   for m, a in totals.items() if _rel(a) is not None},
        "weekly": weekly,
        "_totals": totals,
    }


# ------------------------------------------------------------------ outlook

def _locations_frame():
    from flubnf.settings import load_locations
    return load_locations()


def _vintage_observed(asof: str) -> dict | None:
    """{location_name: [[date, value], ...]} as the archive held it ON the
    forecast date, or None when no vintage was archived for that date.

    The observed line and the map's "current" anchor are what the forecast
    SAW (NHSN revises the newest week ~4-5% up); a payload carries settled
    truth, which appears only in the settled overlay.
    """
    from app.core import data as data_mod

    try:
        df = data_mod.load_vintage(asof)
    except Exception:
        return None
    loc = _locations_frame()
    f2n = dict(zip(loc.location.str.zfill(2), loc.location_name))
    out: dict = {}
    for r in df.itertuples():
        name = f2n.get(r.location)
        if name:
            out.setdefault(name, []).append([str(r.date)[:10], float(r.value)])
    for series in out.values():
        series.sort()
    return out or None


def _cards_from_quantiles(models: dict, truth_by_loc: dict, asof: str) -> dict:
    """{model: {fips: hover card}} through the app's ONE categorical path.

    Every map surface uses report.categorical_probs_from_quantiles, so a
    category here matches the console's.
    """
    from app.core.report import categorical_probs_from_quantiles
    from app.core.report_v2 import CATS

    loc = _locations_frame()
    n2f = dict(zip(loc.location_name, loc.location.str.zfill(2)))
    n2a = dict(zip(loc.location_name, loc.abbreviation))
    n2p = dict(zip(loc.location_name, loc.population.astype(float)))

    out: dict = {}
    for model, qbl in hz.models_to_canonical(models or {}).items():
        cards = {}
        for name, hq in (qbl or {}).items():
            fips = n2f.get(name, "")
            raw = (hq or {}).get("0")     # one week ahead, canonical
            series = [p for p in (truth_by_loc.get(name) or [])
                      if p[0] <= asof and p[1] is not None]
            if len(fips) != 2 or not raw or not series:
                continue
            try:
                q1 = {float(k): float(v) for k, v in raw.items()}
            except (TypeError, ValueError):
                continue
            last = float(series[-1][1])
            probs = categorical_probs_from_quantiles(
                q1, last, int(n2p.get(name, 0)), 0)
            if not probs:
                continue
            med = float(q1.get(0.5, 0.0))
            hover = (f"<b>{_html.escape(name)}</b><br>current: {last:.0f}"
                     f"<br>1-wk median: {med:.0f}<br>" +
                     "<br>".join(
                         f"{c.replace('_', ' ')}: {probs.get(c, 0):.0%}"
                         for c in CATS))
            cards[fips] = {"probs": probs, "name": name,
                           "abbr": n2a.get(name, ""), "fips": fips,
                           "hover_html": hover,
                           "current": round(last, 1),
                           "median1": round(med, 1)}
        if cards:
            out[model] = cards
    return out


def _newest_run_source() -> tuple:
    """(run_id, bundle, results) for the newest run that can serve as a
    national outlook, or (None, None, None).

    A run qualifies only with per-model outlook cards for at least
    MIN_OUTLOOK_LOCATIONS jurisdictions AND quantile grids in results.json
    (the fans come from there: the bundle's fans are the PF's alone).
    """
    from app.core import report_v2

    roots = APP_STATE / "workroots"
    if not roots.is_dir():
        return None, None, None
    for d in sorted((p for p in roots.iterdir() if p.is_dir()),
                    key=lambda p: p.name, reverse=True):
        b, r = d / report_v2.BUNDLE_NAME, d / "results.json"
        if not b.is_file() or not r.is_file():
            continue
        try:
            bundle = json.loads(b.read_text())
            results = json.loads(r.read_text())
        except Exception:
            continue
        # research runs never reach the public site (older ones: by their spec)
        from app.core.runs import is_research
        if results.get("research") or is_research(results.get("spec", "")):
            continue
        if bundle.get("version") not in report_v2.SUPPORTED_BUNDLE_VERSIONS:
            continue
        by_model = {m: {c["fips"]: c for c in (cards or {}).values()
                        if isinstance(c, dict) and c.get("fips")
                        and c.get("probs")}
                    for m, cards in (bundle.get("cards_by_model") or {}).items()}
        by_model = {m: c for m, c in by_model.items() if c}
        if not by_model:
            continue
        if max(len(c) for c in by_model.values()) < MIN_OUTLOOK_LOCATIONS:
            continue
        if not (results.get("models") or {}).get("pf"):
            continue
        return d.name, bundle, results
    return None, None, None


def build_outlook(seasons: dict, pin: tuple | None = None) -> dict:
    """The home map and its per-model fills, plus the week's fans.

    Source: the newest run bundle covering the country, else the newest
    retrospective week; the source is named on the page. `pin` (season,
    asof) overrides the retrospective week explicitly and is recorded; the
    default never picks a photogenic week.
    """
    from app.core import playback, usmap
    from app.core.report_v2 import MODEL_LABEL

    rid, bundle, results = (None, None, None) if pin \
        else _newest_run_source()
    if bundle is not None:
        cards_by_model = {
            m: {c["fips"]: c for c in (cards or {}).values()
                if isinstance(c, dict) and c.get("fips") and c.get("probs")}
            for m, cards in (bundle.get("cards_by_model") or {}).items()}
        cards_by_model = {m: c for m, c in cards_by_model.items() if c}
        asof = (results.get("forecast_date")
                or bundle.get("reference_date") or "")
        ox = results.get("oracle")
        source = {"kind": "run", "run_id": rid, "asof": asof,
                  "season": None, "origin": "live run",
                  "label": f"this week's run, forecast date {asof}",
                  # what the fan's mechanistic median is: the member when
                  # the run recorded the step's bank label, else the filter
                  "pf_label": (PF_LABEL_ORACLE if ox and ox != "none"
                               else PF_LABEL_FILTER)}
        fans = _fans_from_results(results, bundle)
    else:
        if not seasons:
            raise BuildError(
                "no forecast source: no run bundle covers the country and no "
                "retrospective season has stored weeks under app/state. Run a "
                "season (Retrospective tab) or a weekly forecast first.")
        season = max(seasons)
        info = seasons[season]
        asof = info["weeks"][-1]
        if pin:
            season = pin[0] or season
            if season not in seasons:
                raise BuildError(
                    f"--season {season}: no stored weeks. Available: "
                    + ", ".join(sorted(seasons)))
            info = seasons[season]
            asof = pin[1] or info["weeks"][-1]
            if asof not in info["weeks"]:
                raise BuildError(
                    f"--asof {asof}: {season} has no completed week there. "
                    f"Available: {info['weeks'][0]}..{info['weeks'][-1]}")
        payload = playback.build_week(info["root"], season, asof)
        vintage = _vintage_observed(asof)
        observed = vintage if vintage is not None else (
            payload.get("truth") or {})
        cards_by_model = _cards_from_quantiles(
            payload.get("models") or {}, observed, asof)
        source = {"kind": "retrospective", "run_id": None, "asof": asof,
                  "season": season, "origin": info["origin"],
                  "pinned": bool(pin),
                  "observations": ("vintage archived on the forecast date"
                                   if vintage is not None else
                                   "settled truth (no vintage archived for "
                                   "this date)"),
                  "label": f"{season} retrospective, week of {asof}",
                  "pf_label": (PF_LABEL_ORACLE if _week_applied(
                      Path(info["root"]) / "weeks" / asof)
                      else PF_LABEL_FILTER)}
        fans = _fans_from_payload(payload, observed)

    models = [m for m in MODEL_ORDER if m in cards_by_model]
    models += [m for m in sorted(cards_by_model) if m not in models]
    if not models:
        raise BuildError("the forecast source carries no model with "
                         "categorical forecast cards")
    default = models[0]

    fills = {m: usmap.state_swap_payload(cards_by_model[m]) for m in models}
    hover = {f: {"name": c["name"], "abbr": c.get("abbr", ""),
                 "current": c.get("current"), "median1": c.get("median1"),
                 "probs": {k: round(float(v), 4)
                           for k, v in (c.get("probs") or {}).items()}}
             for f, c in cards_by_model[default].items()}

    # modal-category counts, so an off-season wall of "stable" reads as data
    tally: dict = {}
    for c in cards_by_model[default].values():
        probs = c.get("probs") or {}
        if probs:
            tally[max(probs, key=probs.get)] = 1 + tally.get(
                max(probs, key=probs.get), 0)

    # PR is forecast but has no Albers shape: carry both counts
    drawn = set(fills[default])
    return {
        "source": source,
        "models": models,
        "labels": {m: MODEL_LABEL.get(m, m) for m in models},
        "default_model": default,
        "fills": fills,
        "hover": hover,
        "coverage": len(cards_by_model[default]),
        "mapped": len(drawn & set(hover)),
        "unmapped": sorted(hover[f]["name"] for f in hover
                           if f not in drawn),
        "modal_tally": dict(sorted(tally.items(), key=lambda kv: -kv[1])),
        "_cards": cards_by_model[default],
        "fans": fans,
    }


# --------------------------------------------------------------------- fans

def _q_at(raw: dict, level: float):
    """One stored level, tolerating the float-format drift JSON round-trips
    introduce ("0.5" vs "0.50")."""
    if not raw:
        return None
    key = str(level)
    if key in raw:
        return float(raw[key])
    try:
        best = min(raw, key=lambda k: abs(float(k) - level))
    except (TypeError, ValueError):
        return None
    return float(raw[best]) if abs(float(best) - level) < 1e-9 else None


def _fan_entry(obs, settled, hq_pf, hq_an) -> dict | None:
    """One location's fan: the PF's intervals and median, the Groundhog's
    median as the overlay (`an`)."""
    if not obs or not hq_pf:
        return None
    q = {}
    for h in HORIZONS:
        raw = hq_pf.get(h)
        vals = {str(L): _q_at(raw, L) for L in FAN_LEVELS} if raw else {}
        if all(v is not None for v in vals.values()) and vals:
            q[h] = {k: round(v, 2) for k, v in vals.items()}
    if not q:
        return None
    entry = {"obs": obs[-OBS_WEEKS:], "settled": settled, "q": q}
    med = {h: _q_at((hq_an or {}).get(h), 0.5) for h in HORIZONS}
    med = {h: round(v, 2) for h, v in med.items() if v is not None}
    if med:
        entry["an"] = med
    return entry


def _fans_from_payload(payload: dict, observed: dict | None = None) -> dict:
    """All-location fans from a retrospective week.

    OBSERVED = the vintage as of the forecast date (what it saw); SETTLED =
    the payload's truth for the four target weeks, only those that have
    arrived (none for a live week: no overlay, no legend entry).
    """
    asof = payload["asof"]
    truth = payload.get("truth") or {}
    observed = truth if observed is None else observed
    models = payload.get("models") or {}
    pf, an = models.get("pf") or {}, models.get("analogue") or {}
    targets = [(datetime.fromisoformat(asof)
                + timedelta(days=7 * (h + 1))).date().isoformat()
               for h in (0, 1, 2, 3)]
    out = {}
    for name in sorted(pf):
        obs = [[d, v] for d, v in (observed.get(name) or [])
               if d <= asof and v is not None]
        by_date = {d: v for d, v in (truth.get(name) or []) if v is not None}
        settled = [[d, by_date[d]] for d in targets if d in by_date]
        e = _fan_entry(obs, settled, pf.get(name), an.get(name))
        if e:
            out[name] = e
    return out


def _fans_from_results(results: dict, bundle: dict) -> dict:
    """All-location fans from a live run.

    Quantiles and observations from results.json; the settled overlay from
    the bundle's fans (filled only for a backdated run). results.json keeps
    stored horizons ("1".."4") in every existing workroot, so its models are
    canonicalised before `_fan_entry` reads "0".."3".
    """
    models = hz.models_to_canonical(results.get("models") or {})
    pf, an = models.get("pf") or {}, models.get("analogue") or {}
    observed = results.get("observed") or {}
    settled = {}
    for det in (bundle.get("details") or {}).values():
        if not isinstance(det, dict):
            continue
        fan = det.get("fan") or {}
        pts = fan.get("settled") or []
        if det.get("name") and pts:
            settled[det["name"]] = [[str(d), float(v)] for d, v in pts
                                    if v is not None]
    # framed to the four target weeks (older bundles carried a fifth)
    asof = str(results.get("forecast_date") or "")
    if asof:
        last = (datetime.fromisoformat(asof)
                + timedelta(days=28)).date().isoformat()
        settled = {n: [pt for pt in pts if asof < pt[0] <= last]
                   for n, pts in settled.items()}
    out = {}
    for name in sorted(pf):
        obs = [[str(d), float(v)] for d, v in (observed.get(name) or [])
               if v is not None]
        e = _fan_entry(obs, settled.get(name) or [], pf.get(name),
                       an.get(name))
        if e:
            out[name] = e
    return out


# ------------------------------------------------------- harvest of the app

_PERF_ROW = re.compile(
    r"<tr[^>]*>\s*<td>(?P<season>\d{4}-\d{2})</td>.*?"
    r'<td class="num rel">(?P<rel>[\d.]+)</td>', re.S)

#: the optional standings columns, matched INSIDE one row only
_PERF_FIELD = re.compile(
    r'<td>(?P<field>[^<]*\bof\b[^<]*)</td>\s*'
    r'<td class="num">(?P<pct>[^<]*)</td>', re.S)

_FIELD = re.compile(r"(?P<rank>\d+)\s+of\s+(?P<size>\d+)")


def harvest_placement() -> dict:
    """{season: {rank, field, text, percentile, app_rel}} from the console's
    own performance table.

    `app_rel` (always present) feeds cross_check. The standings columns are
    optional and absent since the 2026-08-24 withdrawal
    (docs/archive/RELEASE-1.0.md); site_page then prints "placement
    withdrawn". Restored columns would be picked up unchanged.
    """
    src = (TEMPLATES / "home.html").read_text(encoding="utf-8")
    block = src.split('<table class="perf">', 1)
    if len(block) < 2:
        return {}
    body = block[1].split("</table>", 1)[0]
    out = {}
    # row by row, so an optional column is never read from the next row
    for row in re.split(r"(?=<tr\b)", body):
        m = _PERF_ROW.match(row.strip())
        if not m:
            continue
        entry = {"app_rel": float(m.group("rel"))}
        g = _PERF_FIELD.search(row)
        if g:
            text = " ".join(g.group("field").split())
            pct = " ".join(g.group("pct").split())
            entry["text"] = text
            f = _FIELD.search(text)
            if f:
                entry["rank"] = int(f.group("rank"))
                entry["field"] = int(f.group("size"))
            if pct:
                entry["percentile_text"] = pct
                p = re.match(r"(\d+)", pct)
                if p:
                    entry["percentile"] = int(p.group(1))
        out[m.group("season")] = entry
    return out


#: the Measured-performance card duplicates the site's own scores: dropped
#: from the harvested Methods
_PERF_CARD = re.compile(
    r'<div class="card"><h2>Measured performance</h2>.*?</div>\s*(?=<div class="card")',
    re.S)


def harvest_methods(versions: dict) -> str:
    """The console's Methods page as standalone markup.

    Rendered through the console's own Jinja env (app.ui.server.templates),
    so the site's SVGs are the app's; only base.html's chrome is left behind.
    """
    from app.ui.server import templates

    src = (TEMPLATES / "methods.html").read_text(encoding="utf-8")
    body = src.split("{% block content %}", 1)
    if len(body) < 2:
        raise BuildError("methods.html has no content block to harvest")
    body = body[1].rsplit("{% endblock %}", 1)[0]
    tpl = templates.env.from_string('{% import "diagrams.html" as dg %}'
                                    + body)
    html = tpl.render(versions=versions)
    html = _PERF_CARD.sub("", html, count=1)
    # the console's in-app links have no meaning on a static site; only
    # same-page anchors survive
    html = re.sub(r'href="/(?!/)[^"#]*(#[^"]*)"', r'href="\1"', html)
    html = re.sub(r'href="/(?!/)[^"]*"', 'href="#methods"', html)
    return html.strip()


def harvest_bibliography() -> list:
    """The fixed parameters' sources, read from flubnf/sihrs_priors.py (the
    DOIs beside their derivations), so a re-sourced parameter updates the site."""
    from flubnf import sihrs_priors as P

    def doi(x):
        return f"https://doi.org/{x}"

    items = [
        {"what": "Generation time",
         "text": (f"Chan et al. 2024, mean intrinsic generation time "
                  f"{P.GENERATION_TIME_DAYS} days (95% CrI "
                  f"{P.GENERATION_TIME_CRI[0]}-{P.GENERATION_TIME_CRI[1]}), "
                  "US household transmission study. Sets the recovery rate."),
         "href": doi(P.GT_SOURCE), "label": f"doi:{P.GT_SOURCE}"},
        {"what": "Reproduction number context",
         "text": ("Boelle et al. 2011 reports community reproduction "
                  "numbers 1.2 to 2.3, median 1.5. Context, not a bound: "
                  "the fitted R_eff prior is uniform 0.6 to 2.5, and the "
                  f"recorded working range {P.R0_RANGE[0]} to "
                  f"{P.R0_RANGE[1]} widens Boelle's low end deliberately."),
         "href": doi(P.R0_SOURCE), "label": f"doi:{P.R0_SOURCE}"},
        {"what": "Attack rate",
         "text": (f"Vinh et al. 2021, age-seroprevalence decomposition; the "
                  f"cumulative infection fraction is carried as the range "
                  f"{P.ATTACK_RATE_RANGE[0]}-{P.ATTACK_RATE_RANGE[1]} and "
                  "used only as the denominator when pinning the "
                  "ascertainment product."),
         "href": doi(P.ATTACK_RATE_SOURCE),
         "label": f"doi:{P.ATTACK_RATE_SOURCE}"},
        {"what": "Under-detection",
         "text": ("Reed et al. 2015, influenza hospitalization "
                  "under-detection multipliers by age. Recorded as context "
                  "for ascertainment, never used to calibrate it against "
                  "the NHSN target."),
         "href": doi(P.UNDERDETECTION_SOURCE),
         "label": f"doi:{P.UNDERDETECTION_SOURCE}"},
    ]
    for key, who in (("estimator_titer_to_s0", "Xiong et al. 2025"),
                     ("cdc_us_longitudinal_panel", "Li et al. 2025")):
        src = P.S0_SOURCES.get(key)
        if src:
            items.append({
                "what": "Initial susceptibility",
                "text": (f"{who}, serological basis for the bounded s0 "
                         f"sensitivity axis "
                         f"({P.S0_RANGE[0]}-{P.S0_RANGE[1]}, default "
                         f"{P.S0_DEFAULT}); no published source gives a "
                         "per-state US value, so s0 is not fitted."),
                "href": doi(src), "label": f"doi:{src}"})
    items += [
        {"what": "Fitting framework",
         "text": ("Mitra et al. 2019, PyBioNetFit and the Biological "
                  "Property Specification Language, iScience 19:1012-1036 "
                  "-- the framework this lab co-developed and the particle "
                  "filter extends."),
         "href": "https://doi.org/10.1016/j.isci.2019.08.045",
         "label": "doi:10.1016/j.isci.2019.08.045"},
        {"what": "Model language",
         "text": ("BioNetGen: the rule-based modeling language and compiler "
                  "the SIHRS compartment model is written in."),
         "href": "https://bionetgen.org", "label": "bionetgen.org"},
        {"what": "Target data and comparators",
         "text": ("CDC FluSight forecast hub: NHSN target data, the "
                  "authoritative locations table, and the baseline and "
                  "ensemble comparators every score on this page is "
                  "measured against."),
         "href": "https://github.com/cdcepi/FluSight-forecast-hub",
         "label": "github.com/cdcepi/FluSight-forecast-hub"},
    ]
    return items


def harvest_bngl() -> dict:
    src = BNGL.read_text(encoding="utf-8")
    return {"path": str(BNGL.relative_to(REPO)),
            "lines": len(src.splitlines()), "source": src}


# -------------------------------------------------------------- consistency

def cross_check(scored: list, placement: dict,
                label: str = PF_LABEL_ORACLE) -> list:
    """Compare every computed season score against the number the console
    publishes for the same season, and record the comparison.

    The drift alarm: a mismatch means the app's text or the data moved, and
    the build says so rather than publish a different figure silently.
    """
    out = []
    for s in scored:
        # home.html's first score column (app_rel) is the PF
        rel = (s["models"].get("pf") or {}).get("rel")
        app = (placement.get(s["season"]) or {}).get("app_rel")
        if rel is None or app is None:
            continue
        out.append({"what": f"{s['season']} {label} relWIS",
                    "computed": rel, "app": app,
                    "ok": abs(rel - app) <= 0.0006})
    return out


# ------------------------------------------------------------------ payload

def build_payload(seasons: dict | None = None,
                  pin: tuple | None = None) -> dict:
    """Everything the page renders as numbers, in one JSON-ready dict."""
    from app.core.scoring import load_truth
    from app.ui.server import RUNNING_SHA, VERSIONS

    t0 = time.time()
    seasons = discover_seasons() if seasons is None else seasons
    truth, n2f = load_truth()
    bases_cache: dict = {}

    scored = [score_season(s, info, truth, n2f, bases_cache)
              for s, info in seasons.items()]
    pooled: dict = {}
    for s in scored:
        for m, acc in s.pop("_totals").items():
            p = pooled.setdefault(m, [0.0, 0.0, 0])
            p[0] += acc[0]
            p[1] += acc[1]
            p[2] += acc[2]

    placement = harvest_placement()
    for s in scored:
        stand = {k: v for k, v in placement.get(s["season"], {}).items()
                 if k != "app_rel"}
        # no standing -> no `placement` key: the page prints "placement
        # withdrawn" and draws no percentile bars
        if stand:
            s["placement"] = stand

    # one outlook computation: build() renders the map from the same _cards
    # the toggle's fills came from
    outlook = build_outlook(seasons, pin)
    fans = outlook.pop("fans")

    loc = _locations_frame()
    f2n = {f: n for n, f in zip(loc.location_name,
                                loc.location.str.zfill(2))
           if f in outlook["hover"]}

    return {
        "payload_version": PAYLOAD_VERSION,
        "generated_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat(),
        "build": {"sha": RUNNING_SHA, "versions": dict(sorted(
            VERSIONS.items()))},
        "outlook": outlook,
        "fans": fans,
        "fips_to_name": dict(sorted(f2n.items())),
        "seasons": scored,
        "pooled": {m: {"rel": round(_rel(a), 4), "cells": a[2]}
                   for m, a in sorted(pooled.items()) if _rel(a) is not None},
        "model_order": list(MODEL_ORDER),
        "official_order": list(OFFICIAL_ORDER),
        "consistency": cross_check(scored, placement, pf_label(seasons)),
        # the season tables' name for the mechanistic column (pf_label)
        "pf_label": pf_label(seasons),
        "elapsed_s": round(time.time() - t0, 2),
    }


# ------------------------------------------------------------------- render

def build(out_dir: Path | None = None, seasons: dict | None = None,
          pin: tuple | None = None) -> dict:
    """Write the whole site. Returns a summary for the CLI to print."""
    from app.core import usmap
    from app.core.site_page import render_page
    from app.ui.server import VERSIONS

    out = Path(out_dir or OUT_DIR)
    t0 = time.time()
    payload = build_payload(seasons, pin)
    cards = payload["outlook"].pop("_cards")

    page = render_page(
        payload,
        map_svg=usmap.svg_map(cards, dom_id="usmap", interactive=True),
        methods_html=harvest_methods(VERSIONS),
        bibliography=harvest_bibliography(),
        bngl=harvest_bngl())

    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False)
    (out / PAYLOAD_NAME).write_text(text + "\n", encoding="utf-8", newline="\n")
    (out / PAGE_NAME).write_text(page, encoding="utf-8", newline="\n")
    # no Jekyll pass over generated output
    (out / ".nojekyll").write_text("", encoding="utf-8", newline="\n")

    plotly_src = STATIC / PLOTLY_NAME
    dst = out / PLOTLY_NAME
    if plotly_src.is_file():
        if not dst.is_file() or dst.stat().st_size != plotly_src.stat().st_size:
            shutil.copyfile(plotly_src, dst)
    else:                                  # fall back to the installed wheel
        from plotly.offline import get_plotlyjs
        dst.write_text(get_plotlyjs(), encoding="utf-8", newline="\n")

    bad = [c for c in payload["consistency"] if not c["ok"]]
    return {
        "out": out,
        "page_bytes": (out / PAGE_NAME).stat().st_size,
        "payload_bytes": (out / PAYLOAD_NAME).stat().st_size,
        "plotly_bytes": dst.stat().st_size,
        "seasons": [s["season"] for s in payload["seasons"]],
        "locations": len(payload["fans"]),
        "outlook": payload["outlook"]["source"],
        "pooled": payload["pooled"].get("pf", {}).get("rel"),
        "mismatches": bad,
        "elapsed_s": round(time.time() - t0, 2),
    }
