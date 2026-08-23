"""The public site generator: the lab's real retrospectives as a static page.

`flubnf site build` reads the app's own state -- the retrospective season
roots under app/state, the newest run's report bundle, the FluSight hub
clone -- and writes a self-contained static site to site/. Nothing on the
page is typed by hand: every score is computed here from stored forecasts
against settled truth, and every word of Methods is rendered from the
console's own templates through the console's own Jinja environment, so the
site and the app cannot drift apart.

WHY THIS EXISTS AS A BUILD RATHER THAN A SERVER
-----------------------------------------------
app/state is gitignored. The retrospectives are hundreds of megabytes of
samples on the lab's laptop and will never be in the repository, so the
generated page IS the published evidence: it is reviewed as a diff and
committed. That makes two properties load-bearing, and both are tested:

  * the payload is data-only and pretty-printed, so a rebuild's diff shows
    which numbers moved rather than a reflowed wall of markup; and
  * the page works offline from disk, because a reviewer opens the built
    file before deciding to commit it.

THE ONE SCORE
-------------
relWIS here is the SHIPPED ensemble: the equal-weight 50/50 quantile blend
of the particle filter and the calendar analogue. That distinction is not
cosmetic. A season's stored scores.json is written by retro.score_season,
whose ensemble column blends with the FROZEN LOSO weights (the per-horizon
0.4-0.8 PF share) -- a configuration the lab evaluated and rejected, and
which scores measurably worse (pooled 0.710 against 0.704 for the equal
blend). Reading scores.json here would publish the rejected ensemble under
the shipped ensemble's name. Instead every season is rescored from each
week's playback payload, whose `ensemble` block IS the equal-weight blend
(playback._week_model_quantiles builds it with ens.equal_weights), through
the validated baseline construction and the frozen cell rule: settled truth
above zero, a positive median, and a cell the FluSight baseline also
covers. That path reproduces the lab's published record exactly --
0.848 / 0.651 / 0.691 -- and test_site_build pins those values.

The members (pf, analogue) are weight-free and therefore agree with
scores.json to the third decimal either way; they are recomputed here anyway
so one pass produces every number on the page.

WHAT IS HARVESTED RATHER THAN RESTATED
--------------------------------------
  * Methods prose and diagrams: app/ui/templates/methods.html rendered
    through app.ui.server.templates.env, so the site shows the console's
    text and the console's SVGs, versions included.
  * The FluSight field placements: the perf table in home.html is the lab's
    published standing (rank, field size, percentile). It is read as data,
    not retyped. A season the table does not cover renders without a
    placement rather than with an invented one.
  * The model source: flubnf/templates/SIHRS_pop_min.bngl, verbatim.
  * The parameter bibliography: the DOIs recorded in flubnf/sihrs_priors.py
    beside the derivations that use them.

Because the app states its own performance numbers in prose, the build
CROSS-CHECKS its computed scores against the app's published table and
records every comparison in the payload's `consistency` block. A mismatch
is reported loudly and does not silently reshape either surface: it means
the app's text or the retrospective on disk has moved, and a human decides
which.
"""
from __future__ import annotations

import html as _html
import json
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
REPO = APP.parent
APP_STATE = APP / "state"
TEMPLATES = APP / "ui" / "templates"
STATIC = APP / "ui" / "static"
BNGL = REPO / "flubnf" / "templates" / "SIHRS_pop_min.bngl"

#: default output tree. site/ rather than docs/: docs/ holds hand-written
#: markdown for the lab (WINDOWS.md, SITE.md) that must not be published,
#: and mixing generated output with hand-written docs makes the diff review
#: this loop depends on much harder to read. Pages is deployed from an
#: Actions artifact, so the directory name is free.
OUT_DIR = REPO / "site"

PAYLOAD_NAME = "site.json"
PAGE_NAME = "index.html"
PLOTLY_NAME = "plotly.min.js"

#: payload schema version; bump when a consumer-visible shape changes
PAYLOAD_VERSION = 1

HORIZONS = ("1", "2", "3", "4")
#: the levels the fan draws: median, 50% interval, 80% interval. Chosen as
#: the intersection of what both forecast sources store -- a retrospective
#: week carries all 23 FluSight levels, a live run's results.json carries
#: the five display levels -- so one fan shape serves both and the site
#: never claims an interval one of its sources cannot supply.
FAN_LEVELS = (0.1, 0.25, 0.5, 0.75, 0.9)
#: observed weeks shown behind the forecast
OBS_WEEKS = 14
#: a run bundle must cover at least this many jurisdictions before it
#: outranks a retrospective week as the outlook source; a one-state smoke
#: run must never become the national map
MIN_OUTLOOK_LOCATIONS = 40

MODEL_ORDER = ("ensemble", "pf", "analogue")
OFFICIAL_ORDER = ("FluSight-baseline", "FluSight-ensemble")

#: season-root search order. The lab's own laptop runs land in retro/ and
#: outrank the sealed record for the same season when they are at least as
#: complete; retro_seal/ is the three-season validation archive.
ROOT_ORDER = (("lab run", APP_STATE / "retro"),
              ("sealed record", APP_STATE / "retro_seal"))


class BuildError(RuntimeError):
    """The build cannot produce an honest page (no seasons, no truth)."""


# ---------------------------------------------------------------- discovery

def discover_seasons(roots=ROOT_ORDER) -> dict:
    """{season: {"root", "origin", "weeks"}} for every season with stored
    weeks, across every known root.

    Nothing is hardcoded: a season is whatever directory holds completed
    weeks, so a season the lab replays next winter appears with no code
    change. When two roots hold the same season the more complete one wins,
    and the lab's own run wins a tie -- ROOT_ORDER is the tiebreak, which is
    why it is ordered rather than a set.
    """
    from app.core import playback

    found: dict = {}
    for origin, root in roots:
        if not Path(root).is_dir():
            continue
        for d in sorted(Path(root).iterdir()):
            if not d.is_dir() or not re.fullmatch(r"\d{4}-\d{2}", d.name):
                continue
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

    THE frozen cell rule for every model: settled truth above zero, a
    positive forecast median, and a cell the validated baseline covers. The
    US national row is excluded -- it is the sum of the states and would
    swamp any sum-based aggregate.

    ONE ASYMMETRY, ON PURPOSE. Our own members are scored on their own
    cells, which is how the lab's published record was computed and what
    the cross-check pins. The OFFICIAL comparators are then scored on the
    cells our ensemble scored, and only those. Without that restriction the
    site would print our relWIS beside FluSight-ensemble's in the same row
    while the two rested on different cell sets -- the official covers
    weeks and locations where our median was zero, and is missing from
    weeks it did not submit -- and a reader would compare them anyway. The
    restricted column answers the question the row actually poses: on the
    cells we scored, what did the official model get?
    """
    import pandas as pd
    from app.core.scoring import _baseline_cells
    from flubnf.wis import wis as wis_fn

    asof = payload["asof"]
    T = pd.Timestamp(asof)
    ours = dict(payload.get("models") or {})
    officials = {om: {k: v for k, v in q.items() if k != "US"}
                 for om, q in (payload.get("official") or {}).items() if q}
    if not ours and not officials:
        return {}

    locs = set().union(*(set(b) for b in
                         list(ours.values()) + list(officials.values())))
    fips_set = {n2f[l] for l in locs if l in n2f}
    key = (asof, frozenset(fips_set))
    if key not in bases_cache:
        try:
            bases_cache[key] = _baseline_cells(asof, fips_set, truth)
        except Exception:
            bases_cache[key] = {}
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
                actual = truth.get((fips, T + timedelta(days=7 * int(h))))
                if actual is None or actual <= 0 or q.get(0.5, 0.0) <= 0:
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
                seen.add(cell)
        return ([ws, bs, n] if n else None), seen

    out: dict = {}
    ens_cells: set | None = None
    for model, qbl in ours.items():
        acc, seen = _score(qbl, None)
        if acc:
            out[model] = acc
        if model == "ensemble":
            ens_cells = seen
    for om, qbl in officials.items():
        acc, _seen = _score(qbl, ens_cells)
        if acc:
            out[om] = acc
    return out


def _rel(acc) -> float | None:
    return (acc[0] / acc[1]) if acc and acc[1] else None


def score_season(season: str, info: dict, truth, n2f,
                 bases_cache: dict | None = None) -> dict:
    """One season, week by week, from its stored playback payloads.

    Returns the per-model totals plus the per-week cumulative relWIS series
    the season chart draws. Every payload is fetched through
    playback.build_week, which serves the week's cache when it is fresh and
    rebuilds it when it is not -- so a season the lab just finished on the
    laptop is scored on this pass without a separate cache-warming step.
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

    This matters more than it looks. A replayed week's payload carries
    SETTLED truth, because the playback viewer's job is to show what
    happened. But the page's observed line and the map's "current" anchor
    describe what the forecast SAW, and NHSN revises the freshest week
    upward by a median 4-5% (10th percentile near 0.83). Anchoring the
    change categories on settled truth would quietly move borderline states
    across a cutpoint and contradict the claim this whole project rests on:
    scored only on the data that existed on each forecast date. The settled
    values still appear -- as the settled overlay, which is exactly where
    hindsight belongs.
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

    Every surface that colors a map -- the console's home outlook, the
    weekly report, this site -- reads its probabilities from
    report.categorical_probs_from_quantiles, so a category here is the same
    category the console would show for the same forecast.
    """
    from app.core.report import categorical_probs_from_quantiles
    from app.core.report_v2 import CATS

    loc = _locations_frame()
    n2f = dict(zip(loc.location_name, loc.location.str.zfill(2)))
    n2a = dict(zip(loc.location_name, loc.abbreviation))
    n2p = dict(zip(loc.location_name, loc.population.astype(float)))

    out: dict = {}
    for model, qbl in (models or {}).items():
        cards = {}
        for name, hq in (qbl or {}).items():
            fips = n2f.get(name, "")
            raw = (hq or {}).get("1")
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
                q1, last, int(n2p.get(name, 0)), 1)
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

    A run qualifies only when its report bundle carries per-model outlook
    cards for enough jurisdictions AND its results.json carries the matching
    quantile grids: the bundle's own per-location fans are the particle
    filter's alone (server.py builds `details` from pf_samples), so the
    ensemble fan this site publishes must come from results.json, where all
    three models are stored. A run missing either half is skipped rather
    than half-published.

    The coverage floor matters: a one-state smoke run is not a national map,
    and publishing it as one would be a lie of framing.
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
        if not (results.get("models") or {}).get("ensemble"):
            continue
        return d.name, bundle, results
    return None, None, None


def build_outlook(seasons: dict, pin: tuple | None = None) -> dict:
    """The home map and its per-model fills, plus the week's fans.

    Source order: the newest run bundle that covers the country (the live
    weekly forecast), otherwise the newest retrospective week on disk. The
    chosen source is named in the payload and printed on the page, because
    "this week's forecast" and "the last week we replayed" are different
    claims and the page must make the difference visible.

    `pin` is an explicit (season, asof) override for the retrospective path.
    The default deliberately does NOT pick a photogenic week: an off-season
    map is the honest answer when the newest week is in June, and choosing a
    January peak because it looks better would be cherry-picking. The
    override exists so that choice, when it is made, is made on purpose and
    recorded in the payload rather than baked into the generator.
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
        source = {"kind": "run", "run_id": rid, "asof": asof,
                  "season": None, "origin": "live run",
                  "label": f"this week's run, forecast date {asof}"}
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
                  "label": f"{season} retrospective, week of {asof}"}
        fans = _fans_from_payload(payload, observed)

    models = [m for m in MODEL_ORDER if m in cards_by_model]
    models += [m for m in sorted(cards_by_model) if m not in models]
    if not models:
        raise BuildError("the forecast source carries no model with "
                         "categorical outlook cards")
    default = models[0]

    fills = {m: usmap.state_swap_payload(cards_by_model[m]) for m in models}
    hover = {f: {"name": c["name"], "abbr": c.get("abbr", ""),
                 "current": c.get("current"), "median1": c.get("median1"),
                 "probs": {k: round(float(v), 4)
                           for k, v in (c.get("probs") or {}).items()}}
             for f, c in cards_by_model[default].items()}

    # what the map actually says, counted rather than eyeballed. Off-season
    # weeks are legitimately a wall of "stable", and a reader who cannot
    # tell that from a broken map will assume the second; the count settles
    # it without a threshold or an adjective.
    tally: dict = {}
    for c in cards_by_model[default].values():
        probs = c.get("probs") or {}
        if probs:
            tally[max(probs, key=probs.get)] = 1 + tally.get(
                max(probs, key=probs.get), 0)

    # The forecast covers more jurisdictions than the map can draw: Puerto
    # Rico is a FluSight location with no shape in the Albers topology the
    # console's map is built from. Both counts are carried so the page can
    # state the difference instead of quietly showing 51 shapes under a
    # caption that claims 52. PR keeps its hover card, its fan, and its
    # entry in the location picker; it simply has nowhere to be clicked.
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


def _fan_entry(obs, settled, hq_ens, hq_pf, hq_an) -> dict | None:
    if not obs or not hq_ens:
        return None
    q = {}
    for h in HORIZONS:
        raw = hq_ens.get(h)
        vals = {str(L): _q_at(raw, L) for L in FAN_LEVELS} if raw else {}
        if all(v is not None for v in vals.values()) and vals:
            q[h] = {k: round(v, 2) for k, v in vals.items()}
    if not q:
        return None
    entry = {"obs": obs[-OBS_WEEKS:], "settled": settled, "q": q}
    for name, hq in (("pf", hq_pf), ("an", hq_an)):
        med = {h: _q_at((hq or {}).get(h), 0.5) for h in HORIZONS}
        med = {h: round(v, 2) for h, v in med.items() if v is not None}
        if med:
            entry[name] = med
    return entry


def _fans_from_payload(payload: dict, observed: dict | None = None) -> dict:
    """All-location fans from a retrospective week.

    Two different series, from two different sources, on purpose:

      * the OBSERVED line is the vintage as of the forecast date (passed in
        by build_outlook), because that is what the forecast saw; and
      * the SETTLED overlay is the truth the payload carries for the four
        target weeks AFTER the forecast date, which is hindsight and is
        drawn as such.

    The overlay is conditional by construction: it is emitted only for the
    weeks whose truth has actually arrived, so a live week produces an
    empty list and the page draws no overlay and no legend entry for one --
    absent rather than empty.
    """
    asof = payload["asof"]
    truth = payload.get("truth") or {}
    observed = truth if observed is None else observed
    models = payload.get("models") or {}
    ens, pf, an = (models.get("ensemble") or {}, models.get("pf") or {},
                   models.get("analogue") or {})
    targets = [(datetime.fromisoformat(asof)
                + timedelta(days=7 * h)).date().isoformat()
               for h in (1, 2, 3, 4)]
    out = {}
    for name in sorted(ens):
        obs = [[d, v] for d, v in (observed.get(name) or [])
               if d <= asof and v is not None]
        by_date = {d: v for d, v in (truth.get(name) or []) if v is not None}
        settled = [[d, by_date[d]] for d in targets if d in by_date]
        e = _fan_entry(obs, settled, ens.get(name), pf.get(name),
                       an.get(name))
        if e:
            out[name] = e
    return out


def _fans_from_results(results: dict, bundle: dict) -> dict:
    """All-location fans from a live run.

    Quantiles and observations come from results.json, which stores all
    three models per location on the display level grid. The settled
    overlay, when there is one, comes from the bundle's per-location fan --
    server.py fills it from the newest vintage only for a BACKDATED run, so
    a genuine current-week forecast produces no overlay at all, which is
    exactly right: nothing has settled yet.
    """
    models = results.get("models") or {}
    ens, pf, an = (models.get("ensemble") or {}, models.get("pf") or {},
                   models.get("analogue") or {})
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
    out = {}
    for name in sorted(ens):
        obs = [[str(d), float(v)] for d, v in (observed.get(name) or [])
               if v is not None]
        e = _fan_entry(obs, settled.get(name) or [], ens.get(name),
                       pf.get(name), an.get(name))
        if e:
            out[name] = e
    return out


# ------------------------------------------------------- harvest of the app

_PERF_ROW = re.compile(
    r"<tr[^>]*>\s*<td>(?P<season>\d{4}-\d{2})</td>.*?"
    r'<td class="num rel">(?P<rel>[\d.]+)</td>.*?'
    r"<td>(?P<field>[^<]*)</td>.*?"
    r'<td class="num">(?P<pct>[^<]*)</td>', re.S)

_FIELD = re.compile(r"(?P<rank>\d+)\s+of\s+(?P<size>\d+)")


def harvest_placement() -> dict:
    """{season: {rank, field, text, percentile, app_rel}} from the console's
    own performance table.

    The FluSight standings are a measured lab result -- they take the whole
    hub field scored on identical cells -- and they are published in
    home.html. Reading them here rather than restating them means the lab
    edits one place; a season the table does not cover simply has no
    placement on the site, which is the honest rendering of "not scored
    against the field yet".
    """
    src = (TEMPLATES / "home.html").read_text(encoding="utf-8")
    block = src.split('<table class="perf">', 1)
    if len(block) < 2:
        return {}
    body = block[1].split("</table>", 1)[0]
    out = {}
    for m in _PERF_ROW.finditer(body):
        season = m.group("season")
        text = " ".join(m.group("field").split())
        pct = " ".join(m.group("pct").split())
        entry = {"text": text, "percentile_text": pct,
                 "app_rel": float(m.group("rel"))}
        f = _FIELD.search(text)
        if f:
            entry["rank"] = int(f.group("rank"))
            entry["field"] = int(f.group("size"))
        p = re.match(r"(\d+)", pct)
        if p:
            entry["percentile"] = int(p.group(1))
        out[season] = entry
    return out


#: the app's Measured-performance card duplicates what the site computes on
#: the Retrospectives tab; it is dropped from the harvested Methods content
#: and used instead as the cross-check the consistency block records.
_PERF_CARD = re.compile(
    r'<div class="card"><h2>Measured performance</h2>.*?</div>\s*(?=<div class="card")',
    re.S)


def harvest_methods(versions: dict) -> str:
    """The console's Methods page as standalone markup.

    Rendered through app.ui.server.templates.env -- the console's OWN Jinja
    environment, with the globals its diagram macros need -- so the SVGs on
    this site are the SVGs in the app, produced by the same code from the
    same source, and a change to either lands in both at the next build.
    Only the shell (base.html's nav and chrome) is left behind.
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
    """The fixed parameters' sources, read from the module that defines them.

    flubnf/sihrs_priors.py records each DOI next to the derivation that uses
    it. Harvesting from there means a re-sourced parameter updates the site
    at the next build instead of leaving a stale citation behind.
    """
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
        {"what": "Reproduction number prior",
         "text": (f"Boelle et al. 2011, community reproduction numbers "
                  f"{P.R0_RANGE[0]} to {P.R0_RANGE[1]}. Bounds the R prior."),
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
                  "the SIHRS model is written in."),
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

def cross_check(scored: list, placement: dict) -> list:
    """Compare every computed season score against the number the console
    publishes for the same season, and record the comparison.

    This is the drift alarm. The app states its performance in prose on
    three surfaces; the site computes it from the forecasts on disk. They
    agree today. If they ever stop agreeing, one of them has moved and the
    build says so instead of quietly publishing a different figure under
    the same name.
    """
    out = []
    for s in scored:
        rel = (s["models"].get("ensemble") or {}).get("rel")
        app = (placement.get(s["season"]) or {}).get("app_rel")
        if rel is None or app is None:
            continue
        out.append({"what": f"{s['season']} ensemble relWIS",
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
        if s["season"] in placement:
            s["placement"] = {k: v for k, v in placement[s["season"]].items()
                              if k != "app_rel"}

    # ONE outlook computation. The map SVG the page renders and the fills
    # the toggle swaps in must come from the same cards, or clicking a model
    # button could disagree with the map that was rendered; build() pops
    # _cards off this dict and hands them straight to usmap.svg_map.
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
        "consistency": cross_check(scored, placement),
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
    (out / PAYLOAD_NAME).write_text(text + "\n", encoding="utf-8")
    (out / PAGE_NAME).write_text(page, encoding="utf-8")
    # Pages must not run Jekyll over generated output (it would eat the
    # underscore-prefixed nothing here today, but it also adds a build step
    # that can fail on markup it dislikes)
    (out / ".nojekyll").write_text("", encoding="utf-8")

    plotly_src = STATIC / PLOTLY_NAME
    dst = out / PLOTLY_NAME
    if plotly_src.is_file():
        if not dst.is_file() or dst.stat().st_size != plotly_src.stat().st_size:
            shutil.copyfile(plotly_src, dst)
    else:                                  # fall back to the installed wheel
        from plotly.offline import get_plotlyjs
        dst.write_text(get_plotlyjs(), encoding="utf-8")

    bad = [c for c in payload["consistency"] if not c["ok"]]
    return {
        "out": out,
        "page_bytes": (out / PAGE_NAME).stat().st_size,
        "payload_bytes": (out / PAYLOAD_NAME).stat().st_size,
        "plotly_bytes": dst.stat().st_size,
        "seasons": [s["season"] for s in payload["seasons"]],
        "locations": len(payload["fans"]),
        "outlook": payload["outlook"]["source"],
        "pooled": payload["pooled"].get("ensemble", {}).get("rel"),
        "mismatches": bad,
        "elapsed_s": round(time.time() - t0, 2),
    }
