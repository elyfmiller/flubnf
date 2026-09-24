"""SHIPPED: the Oracle SIHRS donor bank (bank change B2): past-season NHSN
admissions growth (flubnf.oracle_bank, unchanged) mixed half and half with
FluSurv-NET rate growth from the Groundhog's committed bank
(flubnf.bank.read("flusurv"), digest verified). Spec: b2/PREREG_b2_FROZEN.md
(flubnf.oracle.B2_SHA256), shipped by addendum A2.

FLUSURV-NET HALF (S-B2-1, S-B2-4..6). Donor CELLS are the Groundhog's own
(flubnf.analogue.donor_paths(..., length=6, with_keys=True)); a path also
needs its W-1 cell, all eight weeks W-1 .. W+6 in strictly earlier
non-excluded seasons, G_inst(W) > 0 and finite midpoints. No count floor (a
rate has none); network aggregates and the NY sites are donors, as in the
Groundhog. Admissible with >= flubnf.analogue.MIN_DONORS paths. Stamps use
oracle_bank.estimate_G on each location's RATE series over the bank's
Saturday grid (a per-location constant cancels in log differences), held
at five decimals like the admissions pool.

SHRINK (S-B2-7, S-B2-8). The Groundhog's fit_log_ratio_shrink for the same
target season and vintage, applied as G' = gamma + shrink * (G - gamma).
An unfittable shrink raises.

MIXTURE (S-B2-2, S-B2-3), identity rule R_EITHER: w_aux = W_AUX when both
halves are admissible, 1 or 0 when only one is, identity when neither. See
flubnf.oracle.member_for_cell for the draw. Week label:
"admissions-fbase@<pool digest8>+flusurv@<bank digest8>".
"""
from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from . import analogue as AN
from . import bank as BK
from . import oracle_bank as OB

#: the auxiliary stream (the shipped Groundhog's SHIPPED_AUX)
AUX_STREAM = "flusurv"
#: the shipped bank's stream name: the admissions half plus the auxiliary
STREAM = f"{OB.STREAM}+{AUX_STREAM}"
#: the Groundhog's weight on the auxiliary pool, as a mixture probability
W_AUX = 0.5
#: the identity rule of the mixture (S-B2-3)
IDENTITY_RULE = "R_EITHER"

AGGREGATES = ("network_all", "network_eip", "network_ihsp")
NY_SITES = ("ny_albany", "ny_rochester")

#: the FluSurv-NET path table, the screen's own format (rates in place of
#: the admissions table's counts)
POOL_COLUMNS = ["asof", "target_season", "target_epiweek", "rule",
                "donor_location", "donor_week", "donor_season", "donor_epiweek",
                "cal_dist", "rate_W", "min_rate_Wm1_Wp6", "G_origin",
                "G_mid1", "G_mid2", "G_mid3", "G_mid4",
                "rho_1", "rho_2", "rho_3", "rho_4", "is_aggregate", "is_ny_site"]

IDENTITY_TEXT = "identity:fewer_than_MIN_DONORS_paths"


# ---------------------------------------------------------------------------
# the committed bank and its weekly grid
# ---------------------------------------------------------------------------

def read_bank(banks_dir=None) -> tuple:
    """(bank, manifest) of the committed FluSurv-NET bank, digest verified
    by flubnf.bank.read (which raises on a missing or mismatched bank)."""
    return BK.read(AUX_STREAM, banks_dir)


class Grid:
    """Each location's contiguous weekly series on ONE Saturday grid (the
    whole bank's span), NaN where the bank has no cell, with the bank's G
    estimators (flubnf.oracle_bank.estimate_G, floor 0: no count floor)."""

    def __init__(self, bank):
        dates = sorted({d for _, d in bank})
        if not dates:
            raise ValueError("an empty donor bank has no grid")
        self.d0, self.d1 = dates[0], dates[-1]
        self.n = (self.d1 - self.d0).days // 7 + 1
        self.locs = sorted({loc for loc, _ in bank})
        self.series = {loc: np.full(self.n, np.nan) for loc in self.locs}
        for (loc, d), val in bank.items():
            if d.weekday() != 5:
                raise ValueError(f"bank cell {loc} {d} is not a week-ending Saturday")
            self.series[loc][self.index(d)] = float(val)
        self.est = {loc: OB.estimate_G(self.series[loc], floor=0.0, smooth=True)
                    for loc in self.locs}

    def index(self, d: date) -> int:
        return (d - self.d0).days // 7


_GRIDS: dict = {}


def grid_for(bank, digest: str | None = None) -> Grid:
    """The bank's grid, built once per bank digest in a process."""
    key = digest or id(bank)
    g = _GRIDS.get(key)
    if g is None:
        g = _GRIDS[key] = Grid(bank)
    return g


# ---------------------------------------------------------------------------
# calendar positions (the ring of flubnf.analogue.calendar_distance)
# ---------------------------------------------------------------------------

def ring_position(e: int) -> float:
    """An epiweek's place on the ring: week 53 at 52.5."""
    return 52.5 if e == 53 else float(e)


# ---------------------------------------------------------------------------
# the FluSurv-NET path pool
# ---------------------------------------------------------------------------

def collect_paths(bank, grid: Grid, target_position, target_season: int, *,
                  bandwidth: int = AN.DEFAULT_BANDWIDTH,
                  exclude_seasons=AN.EXCLUDED_DONOR_SEASONS,
                  crossing_rule: bool = True) -> tuple:
    """The FluSurv-NET paths at a target position for a target season, in
    the bank's own iteration order. Returns (paths, counts).

    The donor cells are flubnf.analogue's (donor_paths over the shared
    _donor_cells, length 6, keys kept); then the W-1 cell, the
    season-crossing rule and the guards. counts records how many cells each
    step keeps, so a disagreement with another construction shows by step.
    """
    drop = AN.resolve_donor_exclusions(exclude_seasons)
    n_sel = sum(1 for _ in AN._donor_cells(bank, target_position, target_season,
                                           bandwidth, False, drop))
    _, keys = AN.donor_paths(bank, target_position, target_season, length=6,
                             bandwidth=bandwidth, exclude_seasons=exclude_seasons,
                             with_keys=True)
    n_w8 = n_cross = n_guard = 0
    paths = []
    for loc, d in keys:
        prev = bank.get((loc, d - timedelta(days=7)))
        if prev is None or not np.isfinite(prev) or prev <= 0:
            continue
        n_w8 += 1
        weeks = [d + timedelta(days=7 * k) for k in OB.PATH_WEEKS]
        crosses = any(AN.season_of(x) >= target_season or AN.season_of(x) in drop
                      for x in weeks)
        if crosses:
            n_cross += 1
            if crossing_rule:
                continue
        i = grid.index(d)
        est = grid.est[loc]
        g0 = float(est["G_inst"][i])
        gmid = np.array([est["G_week"][i + k] for k in OB.HORIZONS], dtype=float)
        rho = OB.rho_path(est, i)
        if not (np.isfinite(g0) and g0 > 0 and np.isfinite(gmid).all()
                and np.isfinite(rho).all()):
            n_guard += 1
            continue
        rates = [float(bank[(loc, x)]) for x in weeks]
        paths.append({"donor_location": loc, "donor_week": d,
                      "donor_season": AN.season_of(d), "donor_epiweek": AN.epiweek(d),
                      "cal_dist": AN.calendar_distance(AN.epiweek(d), target_position),
                      "rate_W": float(bank[(loc, d)]), "min_rate": float(min(rates)),
                      "G_origin": g0, "G_mid": gmid, "rho": rho,
                      "crosses_season": bool(crosses),
                      "is_aggregate": loc in AGGREGATES, "is_ny_site": loc in NY_SITES})
    by_season: dict = {}
    for p in paths:
        by_season[p["donor_season"]] = by_season.get(p["donor_season"], 0) + 1
    counts = {"n_selected": n_sel, "n_forward6_present": len(keys),
              "n_window8_present": n_w8, "n_crossing": n_cross,
              "n_guard_removed": n_guard, "n_path": len(paths),
              "n_seasons": len(by_season),
              "by_season": {int(k): int(v) for k, v in sorted(by_season.items())},
              "crossing_rule_applied": bool(crossing_rule),
              "target_position": float(target_position),
              "target_season": int(target_season)}
    return paths, counts


def admissible(counts: dict) -> bool:
    """The Groundhog's own floor on a pool: at least MIN_DONORS paths."""
    return int(counts["n_path"]) >= AN.MIN_DONORS


def path_rows(asof: str, target_epiweek: int, target_season: int, paths: list,
              rule: str) -> list:
    """The rows of the path table as strings, the stamps at five decimals
    (flubnf.oracle_bank._f); ONE IDENTITY row when the half is not
    admissible."""
    if rule != "donor":
        r = {c: "" for c in POOL_COLUMNS}
        r.update(asof=asof, target_season=str(target_season),
                 target_epiweek=str(target_epiweek), rule=rule,
                 donor_location="IDENTITY", rho_1="1.000000", rho_2="1.000000",
                 rho_3="1.000000", rho_4="1.000000")
        return [r]
    rows = []
    for p in paths:
        r = {"asof": asof, "target_season": str(target_season),
             "target_epiweek": str(target_epiweek), "rule": rule,
             "donor_location": p["donor_location"],
             "donor_week": p["donor_week"].isoformat(),
             "donor_season": str(p["donor_season"]),
             "donor_epiweek": str(p["donor_epiweek"]), "cal_dist": str(p["cal_dist"]),
             "rate_W": OB._f(p["rate_W"], 5), "min_rate_Wm1_Wp6": OB._f(p["min_rate"], 5),
             "G_origin": OB._f(p["G_origin"], 5),
             "is_aggregate": str(int(p["is_aggregate"])),
             "is_ny_site": str(int(p["is_ny_site"]))}
        for j, k in enumerate(OB.HORIZONS):
            r[f"G_mid{k}"] = OB._f(float(p["G_mid"][j]), 5)
            r[f"rho_{k}"] = OB._f(float(p["rho"][j]), 6)
        rows.append(r)
    return rows


def pool_from_rows(rows: list) -> dict:
    """The half as the member reads it, from path-table rows (strings), at
    the table's precision. G_mid holds the RAW stamps; see shrunk_pool."""
    if not rows or rows[0]["rule"] != "donor":
        return {"n": 0, "rule": 0,
                "rule_text": rows[0]["rule"] if rows else "identity:empty",
                "G_mid": np.zeros((0, 4)), "season": np.zeros(0, int),
                "is_aggregate": np.zeros(0, int), "is_ny_site": np.zeros(0, int)}
    H = OB.HORIZONS
    return {"n": len(rows), "rule": 1, "rule_text": "donor",
            "loc": np.array([r["donor_location"] for r in rows]),
            "week": np.array([r["donor_week"] for r in rows]),
            "season": np.array([int(r["donor_season"]) for r in rows]),
            "G_origin": np.array([float(r["G_origin"]) for r in rows]),
            "G_mid": np.array([[float(r[f"G_mid{k}"]) for k in H] for r in rows]),
            "rho": np.array([[float(r[f"rho_{k}"]) for k in H] for r in rows]),
            "is_aggregate": np.array([int(r["is_aggregate"]) for r in rows]),
            "is_ny_site": np.array([int(r["is_ny_site"]) for r in rows])}


def shrunk(G, s: float) -> np.ndarray:
    """G' = gamma + s * (G - gamma): the Groundhog's a -> exp(s ln a) on a
    ratio, in path space (G - gamma is a difference of smoothed logs)."""
    return OB.GAMMA + s * (np.asarray(G, dtype=float) - OB.GAMMA)


def shrunk_pool(pool: dict, s: float) -> dict:
    """The half the member draws from: G_mid shrunk (full precision, not
    re-rounded), the table's stamps kept as G_mid_raw."""
    out = dict(pool)
    out["G_mid_raw"] = pool["G_mid"]
    out["G_mid"] = shrunk(pool["G_mid"], s) if pool["n"] else pool["G_mid"]
    out["shrink"] = float(s)
    return out


# ---------------------------------------------------------------------------
# the shrink, the Groundhog's per-run fit
# ---------------------------------------------------------------------------

def fit_shrink(admissions_bank, aux_bank, asof: date, *,
               exclude_seasons=AN.EXCLUDED_DONOR_SEASONS) -> tuple:
    """(shrink, target season, the shared prior seasons it was fitted on):
    flubnf.analogue.fit_log_ratio_shrink on the admissions bank of the
    week's vintage, as the Groundhog engine fits shrink = "auto" for a run
    dated `asof`. Raises when it cannot be fitted."""
    ts = AN.season_of(asof)
    s = AN.fit_log_ratio_shrink(admissions_bank, aux_bank, ts,
                                exclude_seasons=exclude_seasons)
    if s is None:
        raise ValueError(
            f"the FluSurv-NET shrink cannot be fitted for {asof} (target season "
            f"{ts}): no shared prior season with enough ratios. The shipped "
            "Oracle SIHRS does not fall back to an unscaled or an "
            "admissions-only bank.")
    drop = AN.resolve_donor_exclusions(exclude_seasons)
    shared = ({AN.season_of(d) for _, d in admissions_bank}
              & {AN.season_of(d) for _, d in aux_bank})
    prior = sorted(x for x in shared if x < ts and x not in drop)
    return float(s), ts, prior


# ---------------------------------------------------------------------------
# the mixture
# ---------------------------------------------------------------------------

def mixture_state(adm_ok: bool, aux_ok: bool) -> str:
    if adm_ok and aux_ok:
        return "both"
    if aux_ok:
        return "flusurv_only"
    if adm_ok:
        return "admissions_only"
    return "identity"


def resolve_w_aux(adm_ok: bool, aux_ok: bool, w_aux: float = W_AUX):
    """R_EITHER: the FluSurv-NET probability of the week, None = identity."""
    return {"both": float(w_aux), "flusurv_only": 1.0, "admissions_only": 0.0,
            "identity": None}[mixture_state(adm_ok, aux_ok)]


def label(admissions_digest: str, aux_bank_digest: str) -> str:
    """The week's bank label: admissions-fbase@<8>+flusurv@<8>."""
    return f"{OB.STREAM}@{admissions_digest[:8]}+{AUX_STREAM}@{aux_bank_digest[:8]}"


def rule_block(bank_digest: str) -> dict:
    """The FluSurv-NET half's rule, stated in its manifest and the week's
    provenance."""
    return {"name": "FLUSURV_PATHS", "stream": AUX_STREAM, "bank_digest": bank_digest,
            "selection": ("flubnf.analogue.donor_paths(length=6, with_keys=True) over "
                          "the shared _donor_cells, then the W-1 cell"),
            "bandwidth": AN.DEFAULT_BANDWIDTH, "min_donors": AN.MIN_DONORS,
            "excluded_donor_seasons": sorted(AN.EXCLUDED_DONOR_SEASONS),
            "path_weeks": list(OB.PATH_WEEKS), "count_floor": None,
            "season_crossing_rule": ("every raw week a path reads (W-1 to W+6) lies in "
                                     "a strictly earlier, non-excluded season"),
            "guards": "G_inst(W) > 0 and every midpoint stamp finite",
            "aggregates_and_ny_sites": "donors",
            "gamma": OB.GAMMA, "smoother": OB.SMOOTHER_ID,
            "shrink": ("fit_log_ratio_shrink(admissions bank of the week's vintage, "
                       "FluSurv-NET bank, season_of(T)); G' = gamma + shrink * (G - gamma)"),
            "identity_rule": IDENTITY_RULE, "w_aux": W_AUX,
            "draw": ("second uniform stream v on the frozen generator: v < w_aux draws "
                     "floor((v / w_aux) n_aux), otherwise the admissions donor floor(u n_adm)")}


# ---------------------------------------------------------------------------
# written and read, the flubnf.bank contract
# ---------------------------------------------------------------------------

def pool_path(out_dir, asof: str) -> Path:
    return Path(out_dir) / f"flusurv_paths_{asof}.csv"


def manifest_path(out_dir, asof: str) -> Path:
    return Path(out_dir) / f"flusurv_paths_{asof}.manifest.json"


def write_rows(path, rows: list) -> None:
    """The table in the screen's format (csv.DictWriter, default dialect)."""
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=POOL_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def read_rows(path) -> list:
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def write_pool(week: dict, out_dir, *, built_utc: str = "") -> dict:
    """Write the week's FluSurv-NET half and its manifest, atomically."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    asof = week["asof"]
    fp = pool_path(out_dir, asof)
    tmp = fp.with_name(fp.name + ".tmp")
    write_rows(tmp, week["rows"])
    tmp.replace(fp)
    man = {"stream": AUX_STREAM, "layout_version": OB.LAYOUT_VERSION,
           "builder": "flubnf.oracle_mix", "built_utc": built_utc,
           "bank_digest": week["bank_digest"], "asof": asof,
           "target_season": week["target_season"], "target_epiweek": week["target_epiweek"],
           "rule": rule_block(week["bank_digest"]), "pool_rule": week["rule"],
           "admissible": week["admissible"], "counts": week["counts"],
           "shrink": week["shrink"], "shrink_prior_seasons": week["shrink_prior_seasons"],
           "cells": week["n_paths"], "digest": week["digest"]}
    mp = manifest_path(out_dir, asof)
    tmp = mp.with_name(mp.name + ".tmp")
    tmp.write_text(json.dumps(man, indent=1, sort_keys=True, default=str) + "\n")
    tmp.replace(mp)
    return man


def read_pool(out_dir, asof: str) -> tuple:
    """(raw pool, manifest) of a written week, digest verified; raises on a
    mismatch (flubnf.bank's rule)."""
    fp, mp = pool_path(out_dir, asof), manifest_path(out_dir, asof)
    man = json.loads(mp.read_text())
    rows = read_rows(fp)
    got = OB.digest_rows(rows)
    if got != man.get("digest"):
        raise ValueError(f"the FluSurv-NET pool at {fp} does not match its manifest "
                         f"({got} against {man.get('digest')}); it is not used")
    return pool_from_rows(rows), man


# ---------------------------------------------------------------------------
# one week
# ---------------------------------------------------------------------------

def build_week(asof: str, admissions_bank, *, aux=None, shrink: float | None = None,
               out_dir=None, built_utc: str = "") -> dict:
    """The FluSurv-NET half for the week dated `asof`.

    `admissions_bank` is the week's vintage bank (flubnf.oracle_bank
    VintageBank.count_bank), used for the shrink only. `aux` is (bank,
    manifest) of the FluSurv-NET bank, by default the committed one read by
    digest. `shrink`, when given, replaces the fitted value (tests and
    research only). With `out_dir` the table and its manifest are written.
    Returns the raw pool, the pool the member draws from (shrunk), the
    rows, their content digest, the counts and the shrink."""
    T = date.fromisoformat(asof)
    bank, bman = aux if aux is not None else read_bank()
    grid = grid_for(bank, bman.get("digest"))
    e = AN.epiweek(T)
    ts = AN.season_of(T)
    paths, counts = collect_paths(bank, grid, ring_position(e), ts)
    ok = admissible(counts)
    rule = "donor" if ok else IDENTITY_TEXT
    rows = path_rows(asof, e, ts, paths, rule)
    raw = pool_from_rows(rows)
    if shrink is None:
        s, _, prior = fit_shrink(admissions_bank, bank, T)
    else:
        s, prior = float(shrink), None
    week = {"asof": asof, "target_season": ts, "target_epiweek": e,
            "bank_digest": bman["digest"], "bank_label": f"{AUX_STREAM}@{bman['digest'][:8]}",
            "rule": rule, "admissible": ok, "counts": counts, "rows": rows,
            "digest": OB.digest_rows(rows), "n_paths": int(raw["n"]),
            "pool_raw": raw, "pool": shrunk_pool(raw, s), "shrink": s,
            "shrink_prior_seasons": prior,
            "n_aggregate": int(sum(p["is_aggregate"] for p in paths)),
            "n_ny_site": int(sum(p["is_ny_site"] for p in paths))}
    week["manifest"] = (write_pool(week, out_dir, built_utc=built_utc)
                        if out_dir is not None else None)
    return week
