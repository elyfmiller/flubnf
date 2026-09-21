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


#: Auxiliary donor streams the engine can build. Each entry maps a stream
#: name to the module that owns it; a stream this dict does not name cannot
#: be spliced in, which is the point.
AUX_STREAMS = ("iliplus", "flusurv")


def _built_aux_bank(spec, stream: str, build) -> dict:
    """Build an auxiliary bank from its source rather than read it off disk.

    `build` is that pool's `build` dict. Common keys are the stream module's
    own; the two streams differ because their sources do:

      iliplus   first_season (ISO date, default "2016-08-01"), vintage
                (default True: pull each stream AS PUBLISHED at the forecast
                date; False pulls the latest issue, which is
                measured-equivalent for this donor construction and cheaper
                to cache), regions, cache_dir, nrevss_cache_dir
      flusurv   first_epiweek (default 200335), locations, cache_dir.
                There is NO vintage option: Delphi serves this endpoint with
                no revision history, so one would be a lie in the signature.

    Raw responses are cached under app/state, so a replay of the same weeks
    never re-hits the network.
    """
    if not isinstance(build, dict):
        raise ValueError(
            f"aux pool {stream!r}: 'build' must be a dict, got "
            f"{type(build).__name__}")
    if stream == "iliplus":
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
    elif stream == "flusurv":
        from flubnf import flusurv
        if "vintage" in build:
            raise ValueError(
                "aux pool 'flusurv': there is no vintage option. Delphi "
                "serves this endpoint with no revision history, so a "
                "vintage-true fetch is not available and asking for one "
                "would be silently ignored.")
        aux = flusurv.build_bank(
            int(build.get("first_epiweek", flusurv.FIRST_EPIWEEK)),
            locations=build.get("locations"),
            cache_dir=build.get("cache_dir"),
        )
    else:                                                # pragma: no cover
        raise ValueError(f"unknown aux stream {stream!r}")
    if not aux:
        raise ValueError(
            f"the {stream!r} bank built for {spec.forecast_date} is empty. A "
            f"spliced run with an empty auxiliary pool would silently be the "
            f"single-pool forecast while still being labelled spliced.")
    return aux


def _one_pool(spec, bank, cfg):
    """One `flubnf.analogue.AuxPool` from one entry of spec.extra['aux_pools'].

    Keys: stream (required, from AUX_STREAMS), weight (required), and exactly
    one of bank (a prebuilt path) or build (source arguments). Optional:
    shrink ("auto" by default, fitting sd(admissions)/sd(stream) on strictly
    prior shared seasons; a number uses that value; None applies no rescale),
    exclude_seasons (default the registry's shipped set), bandwidth.

    An unfittable "auto" shrink RAISES rather than falling back to no
    rescale. A replay labelled spliced that was silently unscaled for some
    weeks is the failure mode this is guarding against.
    """
    if not isinstance(cfg, dict):
        raise ValueError(
            f"each entry of spec.extra['aux_pools'] must be a dict, got "
            f"{type(cfg).__name__}")
    stream = cfg.get("stream")
    if stream not in AUX_STREAMS:
        raise ValueError(
            f"aux pool 'stream' must be one of {AUX_STREAMS}, got "
            f"{stream!r}")
    if "weight" not in cfg:
        raise ValueError(f"aux pool {stream!r} requires a 'weight'")
    # Presence, not truthiness: build={} is a legitimate use-every-default
    # and an empty dict is falsy, so a truthiness test would read it as
    # absent and then complain that neither key was given.
    has_path, has_build = "bank" in cfg, "build" in cfg
    if has_path == has_build:
        raise ValueError(
            f"aux pool {stream!r} needs exactly one of 'bank' (a path to a "
            f"prebuilt donor bank) or 'build' (source arguments); got "
            + ("both" if has_path else "neither"))
    aux = (load_aux_bank(str(cfg["bank"])) if has_path
           else _built_aux_bank(spec, stream, cfg["build"]))
    excl = cfg.get("exclude_seasons")
    excl = (tuple(sorted(AN.EXCLUDED_DONOR_SEASONS)) if excl is None
            else tuple(sorted(int(x) for x in excl)))
    AN.resolve_donor_exclusions(excl)          # loud, before anything is fit
    shrink = cfg.get("shrink", "auto")
    if isinstance(shrink, str):
        if shrink != "auto":
            raise ValueError(
                f"aux pool {stream!r}: 'shrink' must be 'auto', a number or "
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
                f"aux pool {stream!r}: shrink could not be fitted for target "
                f"season {ts}: no shared prior season with enough ratios. "
                f"Set an explicit 'shrink', or do not splice this season.")
    return AN.AuxPool(
        bank=aux,
        weight=float(cfg["weight"]),
        shrink=(None if shrink is None else float(shrink)),
        exclude_seasons=excl,
        bandwidth=(None if cfg.get("bandwidth") is None
                   else int(cfg["bandwidth"])),
        label=stream,
    )


def splice_args(spec, bank):
    """`flubnf.analogue.DonorSplice` from `spec.extra['aux_pools']`, or None.

    This path is DORMANT: no shipped configuration sets the key, and a spec
    without it leaves the analogue byte-identical to the single-pool path
    (verified over all 85 archived as-of weeks, 405,904 quantile values,
    zero differences).

    `aux_pools` is a list of pool configs; see `_one_pool`. Absent, or
    explicitly False, means dormant. An empty list does NOT: the key is
    there, so the caller meant to splice, and returning None would produce a
    run labelled spliced that quietly was not.
    """
    extra = getattr(spec, "extra", None) or {}
    cfg = extra.get("aux_pools")
    if cfg is None or cfg is False:
        return None
    if not isinstance(cfg, (list, tuple)):
        raise ValueError(
            f"spec.extra['aux_pools'] must be a list of pool configs, got "
            f"{type(cfg).__name__}")
    if not cfg:
        raise ValueError(
            "spec.extra['aux_pools'] is empty. Remove the key to run the "
            "single-pool analogue; an empty list would label a run spliced "
            "that was not.")
    pools = tuple(_one_pool(spec, bank, c) for c in cfg)
    total = sum(p.weight for p in pools)
    if total > 1.0 + 1e-12:
        raise ValueError(
            f"aux pool weights sum to {total}, leaving the admissions pool a "
            f"negative weight; they must sum to at most 1")
    return AN.DonorSplice(pools=pools)


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
