"""SHIPPED (the Groundhog): the calendar-analogue engine; instant,
pure-python, returns QUANTILES per horizon.

Wraps flubnf.analogue at its DEFAULT_BANDWIDTH and default donor pool, never
restated here, so the engine cannot disagree with the library.

  * bare analogue: `spec.extra` without `aux_pools` (RESEARCH now; the
    member every sealed number was scored with, output unchanged).
  * GROUNDHOG: the shipped auxiliary bank spliced in (SHIPPED_AUX,
    shipped_aux_pools()).

run(spec) never reads SHIPPED_AUX itself: the console and retrospective put
the shipped pools into the spec.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from flubnf import analogue as AN                     # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL # noqa: E402
from app.core.data import LOCATIONS, vintage_path     # noqa: E402


def completeness_args(spec, fips: str, anchor_date, newest_date) -> tuple:
    """(completeness, widen_log_sd) for one state, or (None, None).

    RESEARCH, DORMANT: no shipped configuration sets these keys; both
    pre-registered completeness corrections were killed
    (docs/archive/RELEASE-1.0.md). spec.extra["analogue_completeness"]
    ({fips: c}) and ["analogue_widen_log_sd"] apply ONLY when the anchor is
    the vintage's newest week; older anchors are already near settled.
    """
    extra = getattr(spec, "extra", None) or {}
    # reporting mode "both" (see pf.prepare): the lag-0 factor divides a
    # newest-week anchor; no widening.
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

    Keys become (location, datetime.date), as donor_ratios reads them; they
    need not match the admissions bank's locations. A relative path resolves
    against the repo root (committed banks go through flubnf.bank.read). A
    missing or empty file raises: an empty pool would silently be the
    single-pool forecast under a spliced label.
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
            f"auxiliary donor bank not found: {fp}. A pool's 'bank' entry in "
            f"spec.extra['aux_pools'] must name a readable JSON file; use "
            f"'committed': True for the banks carried in data/banks/.")
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


#: Auxiliary streams the engine can splice; any other name is refused.
AUX_STREAMS = ("iliplus", "flusurv")

#: Named pool configurations; the name (plus bank digests) is what retro
#: records in run_meta.json. All read the COMMITTED banks (data/banks/, never
#: a live fetch). "flusurv" is the shipped arm (SHIPPED_AUX; selected in prereg
#: ea72d194af8318a5 C1: equal skill, better calibration, less donor-season
#: sensitivity); "iliplus" the arm it replaced; "both" a hedge. The ILI+
#: snapshot is latest-issue, measured equivalent to vintage-true (prereg
#: 08e03ca7e8ffcfce); FluSurv-NET has no revision history.
AUX_PRESETS: dict = {
    "flusurv": ({"stream": "flusurv", "weight": 0.5, "committed": True},),
    "iliplus": ({"stream": "iliplus", "weight": 0.5, "committed": True},),
    "both": ({"stream": "iliplus", "weight": 0.25, "committed": True},
             {"stream": "flusurv", "weight": 0.25, "committed": True}),
}


#: The shipped auxiliary configuration (prereg fd4a6f0e9893df22: relWIS 0.6664
#: vs bare 0.7711 on 15,340 cells). Changing it is the lead's decision: every
#: published Groundhog number names this preset and its bank digests.
SHIPPED_AUX = "flusurv"


def shipped_aux_pools() -> list:
    """`spec.extra["aux_pools"]` for the shipped Groundhog. Raises on a
    missing bank or digest mismatch, before the first fit."""
    return aux_preset(SHIPPED_AUX)(None, 0, None)["aux_pools"]


def shipped_aux_label() -> str:
    """The shipped configuration's recorded name, e.g. 'flusurv+flusurv@06eff6a7'."""
    return aux_preset(SHIPPED_AUX).__name__.split(":", 1)[1]


def bare_analogue(asof=None, i=None, vintages=None) -> dict:
    """`week_extra` for the analogue WITHOUT auxiliary donors (RESEARCH; the
    sealed-record member). Named so run_meta.json says which was run."""
    return {}


def aux_preset(name: str):
    """A `week_extra` callable for retro.run_season, by preset name; its
    __name__ is what run_meta.json records. An unknown name raises."""
    if name not in AUX_PRESETS:
        raise ValueError(
            f"unknown auxiliary preset {name!r}; known: "
            f"{sorted(AUX_PRESETS)}")
    pools = [dict(p) for p in AUX_PRESETS[name]]

    # Bank digests go into the NAME (run_meta.json outlives the pruned week
    # manifests) so a run says which donors it used. Resolved here, so a
    # bad bank fails before the first fit.
    from flubnf import bank as _bankmod
    stamp = []
    for pool in pools:
        if pool.get("committed"):
            _b, _m = _bankmod.read(pool["stream"])
            stamp.append(f"{pool['stream']}@{_m['digest'][:8]}")
    tag = ("+" + ",".join(stamp)) if stamp else ""

    def _extra(asof, i, vintages):
        return {"aux_pools": [dict(p) for p in pools]}

    _extra.__name__ = f"aux_preset:{name}{tag}"
    _extra.__doc__ = f"spec.extra for the {name!r} auxiliary configuration."
    return _extra



def _built_aux_bank(spec, stream: str, build) -> dict:
    """Build an auxiliary bank from its source (RESEARCH; `build` dict keys):

      iliplus   first_season (default "2016-08-01"), vintage (default True =
                as published at the forecast date; False = latest issue),
                regions, locations_csv, cache_dir, nrevss_cache_dir
      flusurv   first_epiweek, locations, cache_dir. No vintage option:
                Delphi keeps no revision history for it.

    Raw responses are cached under app/state.
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

    Keys: stream (AUX_STREAMS), weight, and exactly one of committed, bank
    (a prebuilt path) or build (source arguments). Optional: shrink ("auto"
    fits sd(admissions)/sd(stream) on strictly prior shared seasons; a
    number; None = no rescale), exclude_seasons (default: the registry's),
    bandwidth. An unfittable "auto" shrink RAISES rather than silently
    running unscaled.
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
    # Presence, not truthiness: build={} means "all defaults".
    has_path, has_build = "bank" in cfg, "build" in cfg
    has_committed = "committed" in cfg
    if sum((has_path, has_build, has_committed)) != 1:
        raise ValueError(
            f"aux pool {stream!r} needs exactly one of 'committed' (the "
            f"donor bank carried in this repository), 'bank' (a path to a "
            f"prebuilt one) or 'build' (source arguments); got "
            + (f"{sum((has_path, has_build, has_committed))} of them"
               if (has_path or has_build or has_committed) else "none"))
    if has_committed:
        # The shipped path: versioned with the code (no network needed);
        # bank.read RAISES on a manifest digest mismatch.
        from flubnf import bank as _bankmod
        aux, _man = _bankmod.read(stream)
    else:
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
        # The shrink belongs to the run's target season, so it uses the
        # untrimmed forecast date (a string on the retro path).
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
    """`flubnf.analogue.DonorSplice` from `spec.extra['aux_pools']` (a list
    of _one_pool configs), or None when the key is absent or False (the bare
    analogue, byte-identical to the historical path). An empty list raises:
    the caller meant to splice.
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
    # Trims (weeks_to_drop + the optional same-day rule) move the ANCHOR
    # back as they move the PF's fit origin; ratios span h + k weeks so each
    # labelled horizon still lands on as-of + 7h.
    k_user = int(getattr(spec, "weeks_to_drop", 0) or 0)
    drop_same = bool(getattr(spec, "drop_same_day", False))
    # built once per run (independent of location); None = single pool
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
        for h in (1, 2, 3, 4):     # PHYSICAL weeks ahead, the library's unit
            # default donor pool = the registered exclusions; never restated
            q = AN.forecast(anchor, window_ref, h + k, bank, QL,
                            completeness=c, widen_log_sd=sig, splice=splice)
            if q:
                # canonical (hub) key: h weeks ahead is hub horizon h-1
                qs[str(h - 1)] = {float(L): float(x) for L, x in q.items()}
        if qs:
            out[loc] = qs
    return out
