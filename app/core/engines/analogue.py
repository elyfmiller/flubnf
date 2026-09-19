"""The calendar-analogue engine: instant, pure-python, no workroot needed
beyond a place to write its quantiles.

Wraps flubnf.analogue at its DEFAULT_BANDWIDTH and its shipped donor pool;
neither is overridden or restated here, so the engine cannot disagree with
the library about what production runs. The bandwidth's value and provenance
live beside flubnf.analogue.DEFAULT_BANDWIDTH. Returns QUANTILES per
horizon (the analogue is quantile-native); the ensemble vincentizes them with
the PF's sample-derived quantiles directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from flubnf import analogue as AN                     # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL # noqa: E402
from app.core.data import LOCATIONS, vintage_path     # noqa: E402


def completeness_args(spec, fips: str, anchor_date, newest_date) -> tuple:
    """(completeness, widen_log_sd) for one state, or (None, None).
    This path is DORMANT: no shipped configuration sets these keys, and
    both pre-registered completeness corrections were tested and killed
    (docs/RELEASE-1.0.md, the two reporting-completeness entries).

    Build 2 (2026-08-21 handoff section 4): a frozen per-state first-issue
    completeness table may ride in `spec.extra["analogue_completeness"]`
    ({fips: c}), with the residual widening sd in
    `spec.extra["analogue_widen_log_sd"]`. The correction applies ONLY when
    the state's anchor is the vintage's newest week (lag 0) -- an older
    anchor is already near settled (lag-2 median vintage/final is 1.000 in
    every measured season) and must be neither scaled nor widened.

    Specs without `extra`, or without the keys, return (None, None), which
    leaves flubnf.analogue byte-identical to the pre-Build-2 path.
    """
    extra = getattr(spec, "extra", None) or {}
    # The declared reporting model's both-members arm (research/
    # reporting-model): the real-time pooled lag-0 factor divides the
    # anchor when the anchor is the vintage's newest week; no widening.
    rep = extra.get("reporting") or {}
    if str(rep.get("mode") or "") == "both":
        if anchor_date != newest_date:
            return None, None
        from app.core import completeness as _comp
        fac = _comp.factors_cached(spec.forecast_date, spec.season_start)
        return float(fac["factors"][0]), None
    cmap = extra.get("analogue_completeness") or {}
    c = cmap.get(fips)
    if c is None or anchor_date != newest_date:
        return None, None
    sig = extra.get("analogue_widen_log_sd") or None
    return float(c), (float(sig) if sig else None)


_AUX_BANK_CACHE: dict = {}


def load_aux_bank(path: str) -> dict:
    """Read an auxiliary donor bank: JSON of "location|YYYY-MM-DD" -> value.

    Keys are (location, datetime.date), the shape `flubnf.analogue.donor_ratios`
    reads. The location keys need not match the admissions bank's, because the
    pool is cross-location by construction and a location key is used only to
    find a week's own future value.

    The file is a local data artefact, not repository content (`app/state/`
    and `data/` are gitignored), so a relative path resolves against the repo
    root and a missing file raises rather than yielding an empty pool: an
    empty auxiliary bank would silently halve the splice into the single-pool
    forecast while still being labelled spliced.
    """
    import json
    from datetime import date as _date

    fp = Path(path)
    if not fp.is_absolute():
        fp = REPO / fp
    key = (str(fp), fp.stat().st_mtime_ns if fp.exists() else None)
    hit = _AUX_BANK_CACHE.get(key)
    if hit is not None:
        return hit
    if not fp.exists():
        raise FileNotFoundError(
            f"auxiliary donor bank not found: {fp}. spec.extra['iliplus']"
            f"['bank'] must name a readable JSON file; it is a local data "
            f"artefact and is not carried in this repository.")
    raw = json.load(open(fp))
    bank = {}
    for k, v in raw.items():
        loc, _, ds = k.partition("|")
        if not ds:
            raise ValueError(
                f"auxiliary bank key {k!r} is not 'location|YYYY-MM-DD'")
        y, m, d = (int(x) for x in ds.split("-"))
        val = float(v)
        if val > 0:
            bank[(loc, _date(y, m, d))] = val
    if not bank:
        raise ValueError(f"auxiliary donor bank {fp} holds no positive values")
    _AUX_BANK_CACHE[key] = bank
    return bank


def _built_aux_bank(spec, build) -> dict:
    """Build the auxiliary bank from Delphi rather than read it off disk.

    `build` is `spec.extra["iliplus"]["build"]`, a dict:
      first_season  ISO date opening the earliest donor season to pull
                    (default "2016-08-01", where fluview_clinical begins)
      vintage       True (the default) pulls each stream AS PUBLISHED at the
                    forecast date; False pulls the latest issue, which is
                    measured-equivalent for this donor construction and much
                    cheaper to cache, but is not vintage-true and stops being
                    equivalent if the calendar bandwidth ever widens (see
                    flubnf.iliplus)
      regions       explicit region list, default every state in locations.csv
      cache_dir / nrevss_cache_dir   override the on-disk response caches

    Raw responses are cached per (region, issue) under app/state, so a replay
    of the same weeks never re-hits the network.
    """
    if not isinstance(build, dict):
        raise ValueError(
            f"spec.extra['iliplus']['build'] must be a dict, got "
            f"{type(build).__name__}")
    from flubnf import iliplus
    vintage = bool(build.get("vintage", True))
    aux = iliplus.build_bank(
        build.get("first_season", "2016-08-01"),
        str(spec.forecast_date) if vintage else None,
        regions=build.get("regions"),
        locations_csv=build.get("locations_csv"),
        cache_dir=build.get("cache_dir"),
        nrevss_cache_dir=build.get("nrevss_cache_dir"),
    )
    if not aux:
        raise ValueError(
            f"the ILI+ bank built for {spec.forecast_date} is empty. A "
            f"spliced run with an empty auxiliary pool would silently be the "
            f"single-pool forecast while still being labelled spliced.")
    return aux


def splice_args(spec, bank):
    """`flubnf.analogue.DonorSplice` from `spec.extra['iliplus']`, or None.

    This path is DORMANT: no shipped configuration sets the key, and a spec
    without it leaves the analogue byte-identical to the single-pool path
    (verified over all 85 archived as-of weeks, 405,904 quantile values, zero
    differences).

    Config keys, exactly one of `bank` or `build` required:
      bank            path to a prebuilt auxiliary bank JSON
      build           arguments for flubnf.iliplus.build_bank, which pulls
                      ILINet and the clinical stream from Delphi and caches
                      the raw responses; see _built_aux_bank
      weight          weight on the AUXILIARY pool, default 0.5
      shrink          "auto" (default) fits sd(admissions)/sd(aux) on strictly
                      prior shared seasons; a number uses that value; None
                      applies no rescale
      exclude_seasons seasons dropped from the AUXILIARY pool, default the
                      registry's shipped set; validated by
                      `resolve_donor_exclusions` exactly as the admissions
                      pool's is, so an auxiliary pool cannot quietly drop a
                      season the registry has not accepted
      bandwidth       auxiliary calendar bandwidth, default the admissions one

    An unfittable "auto" shrink RAISES rather than falling back to the
    single-pool path. A replay labelled spliced that was silently unspliced
    for some weeks is the failure mode this is guarding against.
    """
    extra = getattr(spec, "extra", None) or {}
    cfg = extra.get("iliplus")
    # Absent, or explicitly False, means dormant. An empty dict does NOT:
    # the key is there, so the caller meant to splice, and returning None
    # would produce a run labelled spliced that quietly was not.
    if cfg is None or cfg is False:
        return None
    if not isinstance(cfg, dict):
        raise ValueError(
            f"spec.extra['iliplus'] must be a dict, got {type(cfg).__name__}")
    # Presence, not truthiness: build={} is a legitimate "use every default"
    # and an empty dict is falsy, so a truthiness test would read it as absent
    # and then complain that neither key was given.
    has_path, has_build = "bank" in cfg, "build" in cfg
    if has_path == has_build:
        raise ValueError(
            "spec.extra['iliplus'] needs exactly one of 'bank' (a path to a "
            "prebuilt donor bank) or 'build' (arguments for "
            "flubnf.iliplus.build_bank); got "
            + ("both" if has_path else "neither"))
    path, build = cfg.get("bank"), cfg.get("build")
    if has_path:
        aux = load_aux_bank(str(path))
    else:
        aux = _built_aux_bank(spec, build)
    excl = cfg.get("exclude_seasons")
    excl = (tuple(sorted(AN.EXCLUDED_DONOR_SEASONS)) if excl is None
            else tuple(sorted(int(x) for x in excl)))
    AN.resolve_donor_exclusions(excl)          # loud, before anything is fit
    shrink = cfg.get("shrink", "auto")
    if isinstance(shrink, str):
        if shrink != "auto":
            raise ValueError(
                f"spec.extra['iliplus']['shrink'] must be 'auto', a number or "
                f"None, got {shrink!r}")
        # spec.forecast_date is a date STRING on the retro path; season_of
        # needs a date. The shrink is a property of the run's target season,
        # not of any one location, so it uses the untrimmed forecast date:
        # the per-location anchor trims move the window by a week or two and
        # only ever cross the 1 August boundary in the off-season.
        ts = AN.season_of(pd.Timestamp(spec.forecast_date).date())
        shrink = AN.fit_log_ratio_shrink(bank, aux, ts, exclude_seasons=excl)
        if shrink is None:
            raise ValueError(
                f"auxiliary shrink could not be fitted for target season "
                f"{ts}: no shared prior season with enough ratios. Set an "
                f"explicit 'shrink', or do not splice this season.")
    return AN.DonorSplice(
        bank=aux,
        weight=float(cfg.get("weight", 0.5)),
        shrink=(None if shrink is None else float(shrink)),
        exclude_seasons=excl,
        bandwidth=(None if cfg.get("bandwidth") is None
                   else int(cfg["bandwidth"])),
    )


def run(spec) -> dict:
    """location -> {horizon(str): {level(float): value}} quantiles."""
    v = vintage_path(spec.forecast_date)
    t = pd.read_csv(v, dtype={"location": str})
    t["location"] = t["location"].str.zfill(2)
    t["date"] = pd.to_datetime(t["date"])
    t = t[t.date <= pd.Timestamp(spec.forecast_date)]     # vintage honesty
    bank = AN.build_bank(t.itertuples())
    newest = t.date.max()                                  # current report week

    locs = pd.read_csv(LOCATIONS, dtype=str)
    name2fips = dict(zip(locs.location_name, locs.location))

    out = {}
    T = pd.Timestamp(spec.forecast_date)
    # Trims move the ANCHOR back, exactly as they move the PF's fit origin:
    # the ratios then span h + k weeks so every labelled horizon still
    # lands on as-of + 7h. Two trims combine per state: the operator's
    # weeks_to_drop, and the nowcast rule (drop_same_day, OFF by default
    # since the 2026-08-27 v1.1 measurement; see RunSpec.drop_same_day).
    # Before this the analogue ignored both trims, anchoring on the very
    # week the fit dropped and desyncing the members (audit finding).
    # With both off the arithmetic is byte-identical to the historical path.
    k_user = int(getattr(spec, "weeks_to_drop", 0) or 0)
    drop_same = bool(getattr(spec, "drop_same_day", False))
    # Dormant unless spec.extra["iliplus"] is set; None keeps AN.forecast on
    # its historical single-pool arithmetic. Built once per run: it depends
    # only on the spec and the vintage bank, not on the location.
    splice = splice_args(spec, bank)
    for loc in spec.locations:
        fips = name2fips.get(loc)
        if fips is None:
            continue
        g = t[t.location == fips].sort_values("date")
        vals = pd.to_numeric(g.value, errors="coerce").dropna()
        auto = 1 if (drop_same and len(vals)
                     and g.date.loc[vals.index[-1]] == T) else 0
        k = k_user + auto
        if k:
            vals = vals.iloc[:-k] if len(vals) > k else vals.iloc[0:0]
        if not len(vals):
            continue                                       # gap: engine skips, report shows it
        anchor = float(vals.iloc[-1])
        anchor_date = g.date.loc[vals.index[-1]]
        window_ref = (T - pd.Timedelta(days=7 * k)).date()
        c, sig = completeness_args(spec, fips, anchor_date, newest)
        qs = {}
        for h in (1, 2, 3, 4):
            # Donor pool: AN.forecast's default, which is every strictly prior
            # season EXCEPT the registered exclusions, 2021-22 and 2020-21
            # (flubnf.analogue.EXCLUDED_DONOR_SEASONS, adopted 2026-08-24 and
            # 2026-09-19). Deliberately not restated as a literal here
            # -- the engine must not be able to disagree with the library about
            # which pool production uses.
            q = AN.forecast(anchor, window_ref, h + k, bank, QL,
                            completeness=c, widen_log_sd=sig, splice=splice)
            if q:
                qs[str(h)] = {float(L): float(x) for L, x in q.items()}
        if qs:
            out[loc] = qs
    return out
