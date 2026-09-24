"""PRODUCTION: relWIS conventions and the published convention note (server
retro pages, site_page, report_season).

Relative WIS under two conventions that must never be mixed.

Both are correct, answer different questions, and are NOT comparable; nothing
may put them in one table or let one stand in for the other.

RATIO OF SUMS (`ratio_of_sums`, this project's home convention):
sum(model WIS) / sum(FluSight-baseline WIS) over the same cells.
Cell-weighted (a peak week counts more), needs only our own scored cells,
so it is ALWAYS computable. Every sealed figure uses it.

PAIRWISE SCALED (`pairwise_scaled`, what the CDC dashboard reports; the
scoringutils / Cramer et al. definition): theta_ij = mean WIS of i / mean
WIS of j on the cells both submitted; a model's skill is the geometric mean
of theta_ij over j != i, scaled so FluSight-baseline = 1.0. Mean-weighted
and field-dependent, and it needs every other team's per-cell WIS, so it
may be unavailable: `load_field_cells` reports absence as a normal state and
no caller may substitute the other convention. This is a faithful port of
the tournament that reproduced the published 2025-26 figures (56 of 57
models within rounding); do not "improve" it.

THE CELL FRAME. Every function works on one frame, one row per scored cell
per model, with CELL_COLUMNS (model, reference_date YYYY-MM-DD, location
zero-padded FIPS, horizon hub-coded 0-3, wis), keyed (reference_date,
location, horizon). `seal_cells` converts a scores frame (model, location,
fips, asof, horizon, wis, base_wis, rel) using the frozen join
reference_date = asof + 7 (submit.hub_reference_date).

FIELD CELLS. Per-model CSVs (CELL_COLUMNS) built by scoring every hub model
with flubnf.wis.wis, by score_hub.py, which lives OUTSIDE this repository;
this module only reads them, from $FLUBNF_FIELD_CELLS, else app/state/field_cells,
nowhere else. app/state is gitignored, so absence is the usual state.

RANKS ARE COMPUTED, NOT DISPLAYED (insert_model, Figures.detail). Placement
against the field was withdrawn 2026-08-24 (methods.html,
docs/archive/RELEASE-1.0.md). The condition for lifting it is not merely
porting the builder: the field AND this project's entry must be rescored end
to end on one stated convention and the shipped configuration. The machinery
stays tested so that meeting it is a display decision, not a rewrite.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

#: The columns a cell frame carries, and the key that identifies a cell.
CELL_COLUMNS = ("model", "reference_date", "location", "horizon", "wis")
CELL_KEY = ["reference_date", "location", "horizon"]

#: the denominator under ratio of sums; the 1.0 the pairwise field is scaled to
BASELINE = "FluSight-baseline"

#: these strings appear in URLs, template conditionals and tests
RATIO_OF_SUMS = "ratio_of_sums"
PAIRWISE = "pairwise"
CONVENTIONS = (RATIO_OF_SUMS, PAIRWISE)

#: every sealed number uses it and it is always available; changing this
#: default would silently restate every published figure
DEFAULT_CONVENTION = RATIO_OF_SUMS

#: reader-facing naming: `name` titles a switch, `short` labels every printed
#: figure (no relWIS is printed unlabelled), `blurb` states the definition
CONVENTION_INFO = {
    RATIO_OF_SUMS: {
        "key": RATIO_OF_SUMS,
        "name": "Ratio of sums",
        "short": "ratio of sums",
        "blurb": ("Total model WIS divided by total FluSight-baseline WIS "
                  "over the same cells. Cell-weighted, computed from this "
                  "project's own scores alone."),
        "needs_field": False,
    },
    PAIRWISE: {
        "key": PAIRWISE,
        "name": "Pairwise scaled (CDC dashboard)",
        "short": "pairwise scaled, the CDC dashboard convention",
        "blurb": ("The scoringutils definition the CDC FluSight dashboard "
                  "reports: geometric mean of pairwise mean-WIS ratios on "
                  "shared cells, scaled so FluSight-baseline is 1.0. "
                  "Mean-weighted, and dependent on which teams are in the "
                  "field."),
        "needs_field": True,
    },
}

#: THE one sentence printed beside every published relWIS (Jinja global, and
#: imported by the site and report builders). It names WHICH ratio, since
#: "a ratio against the baseline" describes both, and warns off the dashboard.
PUBLISHED_CONVENTION_NOTE = (
    "Every relWIS here is a ratio of sums: total model WIS over total "
    "FluSight-baseline WIS on the same cells. The CDC FluSight dashboard "
    "reports a different quantity, a pairwise scaled relative WIS, so a "
    "figure here is not comparable with one there.")

#: our member keys in the field's naming, so our rows and the hub's share a frame
SEAL_MODEL_NAMES = {"pf": "FluBNF-PF", "analogue": "FluBNF-analogue",
                    "ensemble": "FluBNF-ensemble"}

#: where the field-cells cache is looked for: $FLUBNF_FIELD_CELLS, else
#: app/state/field_cells, nowhere else. Data, not code; absence is normal.
FIELD_CELLS_ENV = "FLUBNF_FIELD_CELLS"
APP_STATE = Path(__file__).resolve().parents[1] / "state"
FIELD_CELLS_DEFAULT = APP_STATE / "field_cells"

#: appended to every unavailability reason, so absence does not read as a fault
FIELD_CELLS_HOWTO = (
    "The cache is a directory of per-model score files, one row per "
    "scored cell; it is built from a FluSight hub clone by the "
    "out-of-repo score_hub.py and then pointed at with "
    f"${FIELD_CELLS_ENV} or placed in {FIELD_CELLS_DEFAULT}")


def _is_state(location) -> bool:
    """Not the national row: us_national.is_us inverted (lazy import keeps
    this module importable alone)."""
    from app.core.us_national import is_us
    return not is_us(location)


def season_of(reference_date: str) -> str:
    """The influenza season a hub reference date belongs to, YYYY-YY.

    August is the hub's boundary. The pairwise convention is computed per
    season, as the dashboard's is.
    """
    s = str(reference_date)
    try:
        y, m = int(s[:4]), int(s[5:7])
    except (ValueError, IndexError):
        return ""
    return (f"{y}-{str(y + 1)[2:]}" if m >= 8
            else f"{y - 1}-{str(y)[2:]}")


def convention_of(value) -> str:
    """Normalise whatever a URL or a form carried into one of CONVENTIONS.

    Unrecognised values resolve to the default (a mistyped query parameter
    must not break the page, which names the convention it used anyway).
    """
    v = str(value or "").strip().lower()
    # accept the documented name "pairwise scaled" as an alias
    if v in ("pairwise_scaled", "pairwise-scaled", "pairwise scaled"):
        return PAIRWISE
    return v if v in CONVENTIONS else DEFAULT_CONVENTION


def convention_info(convention: str) -> dict:
    """The naming for one convention, normalised first."""
    return CONVENTION_INFO[convention_of(convention)]


def field_cells_dir() -> Path:
    """Where to look for the field cells: the env var, else the default
    (returned even when absent, so messages can name a path)."""
    env = os.environ.get(FIELD_CELLS_ENV)
    if env:
        return Path(env).expanduser()
    return FIELD_CELLS_DEFAULT


# --------------------------------------------------------------------------
# the cell frame
# --------------------------------------------------------------------------

def seal_cells(df, models: dict = None):
    """The seal's per-cell scores as a cell frame, baseline rows included.

    base_wis (the baseline's score for the cell) becomes one BASELINE row
    per cell, so ratio_of_sums is a pure function over the frame. Returns an
    empty, correctly-shaped frame for anything unusable.
    """
    import pandas as pd
    empty = pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                          zip(CELL_COLUMNS, ("object", "object", "object",
                                             "int64", "float64"))})
    if df is None or not len(df):
        return empty
    need = {"model", "asof", "wis"}
    if not need.issubset(set(df.columns)):
        return empty
    if "fips" not in df.columns and "location" not in df.columns:
        return empty
    names = SEAL_MODEL_NAMES if models is None else models
    d = df.copy()
    d["reference_date"] = (pd.to_datetime(d["asof"], errors="coerce")
                           + pd.Timedelta(days=7)).dt.strftime("%Y-%m-%d")
    # FIPS keys a cell; without a fips column (older/synthetic frames) the name
    # is a fine key within one frame (only pairwise needs real FIPS)
    key_col = "fips" if "fips" in d.columns else "location"
    d["location"] = d[key_col].astype(str).str.zfill(2)
    # no horizon column: one cell per (week, location), a constant key serves
    if "horizon" not in d.columns:
        d["horizon"] = 0
    d["horizon"] = pd.to_numeric(d["horizon"], errors="coerce")
    d = d.dropna(subset=["reference_date", "horizon"])
    d["horizon"] = d["horizon"].astype(int)
    ours = d.copy()
    ours["model"] = ours["model"].map(names)
    ours = ours.dropna(subset=["model", "wis"])
    out = [ours[list(CELL_COLUMNS)]]
    if "base_wis" in d.columns:
        # one baseline row per cell (base_wis repeats beside every member)
        b = d.dropna(subset=["base_wis"]).drop_duplicates(subset=CELL_KEY)
        b = b.assign(model=BASELINE, wis=b["base_wis"])
        out.append(b[list(CELL_COLUMNS)])
    return pd.concat(out, ignore_index=True)


# --------------------------------------------------------------------------
# convention A: ratio of sums
# --------------------------------------------------------------------------

def ratio_of_sums(cells, model: str, baseline: str = BASELINE):
    """(value, n_cells) for one model under the ratio-of-sums convention.

    Only cells the model and the baseline share contribute, so the sums are
    always over the same denominator set. (nan, 0) when they share none.
    """
    if cells is None or not len(cells):
        return float("nan"), 0
    a = cells[cells["model"] == model][CELL_KEY + ["wis"]]
    b = cells[cells["model"] == baseline][CELL_KEY + ["wis"]]
    if not len(a) or not len(b):
        return float("nan"), 0
    m = a.merge(b, on=CELL_KEY, suffixes=("", "_b"))
    if not len(m):
        return float("nan"), 0
    denom = float(m["wis_b"].sum())
    if denom <= 0:
        return float("nan"), len(m)
    return float(m["wis"].sum()) / denom, int(len(m))


# --------------------------------------------------------------------------
# convention B: pairwise scaled relative WIS
# --------------------------------------------------------------------------

def pairwise_scaled(cells, field, baseline: str = BASELINE):
    """(scaled, n_cells) for every model in `field`, the CDC definition.

    `scaled[m]` is m's geometric-mean pairwise relative skill divided by the
    baseline's own, which is what puts FluSight-baseline at exactly 1.0.
    `n_cells[m]` is how many cells m submitted inside this frame, the
    coverage figure that makes a field-dependent number readable.

    Pairs with no overlap or non-positive means are skipped, as in the
    reference implementation.
    """
    import numpy as np
    if cells is None or not len(cells):
        return {}, {}
    sub = cells[cells["model"].isin(list(field))]
    if not len(sub):
        return {}, {}
    mat = sub.pivot_table(index=CELL_KEY, columns="model", values="wis",
                          aggfunc="mean")
    models = [m for m in field if m in mat.columns]
    if not models:
        return {}, {}
    V = mat[models].to_numpy(dtype=float)
    ok = ~np.isnan(V)
    theta = {}
    for i, name in enumerate(models):
        logs = []
        for j in range(len(models)):
            if i == j:
                continue
            mask = ok[:, i] & ok[:, j]
            if not mask.any():
                continue
            mi, mj = V[mask, i].mean(), V[mask, j].mean()
            if mi <= 0 or mj <= 0:
                continue
            logs.append(math.log(mi / mj))
        theta[name] = math.exp(sum(logs) / len(logs)) if logs else float("nan")
    b = theta.get(baseline, float("nan"))
    if not (b == b) or b <= 0:          # nan or degenerate: no scaling exists
        return {}, {}
    scaled = {m: theta[m] / b for m in models}
    n_cells = {m: int(ok[:, k].sum()) for k, m in enumerate(models)}
    return scaled, n_cells


def insert_model(cells, model: str, field, baseline: str = BASELINE) -> dict:
    """Our model dropped into the real field, alone, and ranked in it.

    Alone, because inserting several members moves every other team's
    figure. `rank` and `n_models` are computed, never printed (see the
    module docstring). Returns {} when the tournament cannot run.
    """
    order = [m for m in field if m != model] + [model]
    scaled, n_cells = pairwise_scaled(cells, order, baseline=baseline)
    # a model can be in `scaled` yet nan (shared no cell with anyone, e.g. a
    # stale cache in one jurisdiction): return {} rather than raise below
    value = scaled.get(model, float("nan"))
    if value != value:
        return {}
    ranked = sorted((v, m) for m, v in scaled.items() if v == v)
    rank = 1 + [m for _, m in ranked].index(model)
    return {"value": value, "rank": rank, "n_models": len(ranked),
            "n_cells": n_cells.get(model, 0),
            "field": {m: v for m, v in scaled.items() if m != model}}


# --------------------------------------------------------------------------
# the field cells: a cache that may simply not be here
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldCells:
    """The other teams' per-cell WIS, or a plain statement of its absence.

    `available` false is a NORMAL state; `reason` is printed in place of the
    numbers. Nothing may respond to absence with the other convention.
    """
    cells: object = None
    models: tuple = ()
    source: str = ""
    reason: str = ""
    #: identity of these cached files, for callers that memoise a tournament
    stamp: str = ""

    @property
    def available(self) -> bool:
        return self.cells is not None and len(self.cells) > 0


#: one parsed field frame (~677k cells), keyed by dir and the CSVs' identities
_FIELD_CACHE: dict = {}


def load_field_cells(directory=None) -> FieldCells:
    """Load the cached field cells, or say why there are none.

    Never raises for a missing, empty or unreadable cache: each is reported
    through `reason`.
    """
    import pandas as pd
    d = Path(directory) if directory is not None else field_cells_dir()
    if not d.is_dir():
        return FieldCells(source=str(d), reason=(
            "no hub field data cached: the other teams' per-cell scores "
            f"are not on this machine (looked in {d}). {FIELD_CELLS_HOWTO}"))
    files = sorted(p for p in d.glob("*.csv") if p.is_file())
    if not files:
        return FieldCells(source=str(d), reason=(
            "no hub field data cached: the cache directory "
            f"{d} holds no per-model score files. {FIELD_CELLS_HOWTO}"))
    try:
        key = (str(d), tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size)
                             for p in files))
    except OSError as e:
        return FieldCells(source=str(d), reason=(
            f"the cached hub field data at {d} could not be read: {e}"))
    hit = _FIELD_CACHE.get(key)
    if hit is not None:
        return hit
    frames = []
    for p in files:
        try:
            one = pd.read_csv(p, dtype={"location": str})
        except Exception:
            # one bad team file must not cost the field (coverage counts show it)
            continue
        if not len(one) or not set(CELL_COLUMNS).issubset(set(one.columns)):
            continue
        frames.append(one[list(CELL_COLUMNS)])
    if not frames:
        return FieldCells(source=str(d), reason=(
            f"the cached hub field data at {d} holds no usable per-cell "
            "scores"))
    cells = pd.concat(frames, ignore_index=True)
    cells["horizon"] = pd.to_numeric(cells["horizon"],
                                     errors="coerce").fillna(-1).astype(int)
    cells["reference_date"] = cells["reference_date"].astype(str)
    models = tuple(sorted(cells["model"].unique()))
    if BASELINE not in models:
        return FieldCells(source=str(d), reason=(
            f"the cached hub field data at {d} does not include "
            f"{BASELINE}, so no figure can be scaled to it"))
    import hashlib
    stamp = hashlib.sha1(repr(key).encode()).hexdigest()[:16]
    out = FieldCells(cells=cells, models=models, source=str(d), stamp=stamp)
    _FIELD_CACHE.clear()          # one field frame at a time; it is large
    _FIELD_CACHE[key] = out
    return out


# --------------------------------------------------------------------------
# what a page asks for
# --------------------------------------------------------------------------

#: print order, the retired blend last (present only in older scores frames).
#: Same as us_national.MODELS, repeated so this module stands alone.
MODELS = ("pf", "analogue", "ensemble")


@dataclass(frozen=True)
class Figures:
    """One set of relWIS figures and the convention that produced them.

    The convention travels with the numbers. An unavailable set carries no
    numbers, only `reason`: there is nothing to fall back into.
    """
    convention: str = DEFAULT_CONVENTION
    values: dict = None            # member key -> relWIS
    detail: dict = None            # member key -> coverage, rank, field size
    states: tuple = ()             # per-jurisdiction rows, same convention
    reason: str = ""               # why there are no numbers
    source: str = ""               # where the field data came from
    n_field: int = 0               # how many other teams were in the field

    @property
    def available(self) -> bool:
        return bool(self.values)

    @property
    def info(self) -> dict:
        return convention_info(self.convention)

    @property
    def name(self) -> str:
        """What a switch calls this convention."""
        return self.info["name"]

    @property
    def label(self) -> str:
        """The phrase printed beside every number these figures produced."""
        return self.info["short"]

    @property
    def blurb(self) -> str:
        """The one-sentence statement of the definition."""
        return self.info["blurb"]


def _empty(convention: str, reason: str, source: str = "") -> Figures:
    return Figures(convention=convention_of(convention), values={},
                   detail={}, states=(), reason=reason, source=source)


def _ratio_figures(cells, conv: str, models, names) -> Figures:
    """Every ratio-of-sums figure a season page prints, in one pass.

    Same arithmetic as `ratio_of_sums`, from one baseline join and grouped
    sums (a merge per model per state costs 156 merges per page view).
    """
    a = cells[cells["model"] != BASELINE]
    b = cells[cells["model"] == BASELINE][CELL_KEY + ["wis"]]
    if not len(a) or not len(b):
        return _empty(conv, "no cells shared with the FluSight baseline")
    m = a.merge(b, on=CELL_KEY, suffixes=("", "_b"))
    if not len(m):
        return _empty(conv, "no cells shared with the FluSight baseline")
    msums = m.groupby("model")[["wis", "wis_b"]].sum()
    mcount = m.groupby("model").size()
    psums = m.groupby(["location", "model"])[["wis", "wis_b"]].sum()
    pcount = m.groupby(["location", "model"]).size()

    def one(sums, counts, key, member):
        name = SEAL_MODEL_NAMES.get(member, member)
        k = key(name)
        if k not in sums.index:
            return None, 0
        den = float(sums.at[k, "wis_b"])
        n = int(counts.at[k])
        return ((float(sums.at[k, "wis"]) / den) if den > 0 else None), n

    values, detail = {}, {}
    for member in models:
        v, n = one(msums, mcount, lambda name: name, member)
        if v is not None:
            values[member] = v
            detail[member] = {"n_cells": n}
    if not values:
        return _empty(conv, "no cells shared with the FluSight baseline")
    states = []
    for loc in sorted(m["location"].unique()):
        row = {"name": names.get(loc, loc), "detail": {}}
        hit = False
        for member in models:
            v, n = one(psums, pcount, lambda name: (loc, name), member)
            row[member] = v
            row["detail"][member] = {"n_cells": n}
            hit = hit or v is not None
        if hit:
            states.append(row)
    # sort by printed name, not FIPS, so Puerto Rico is alphabetical too
    states.sort(key=lambda r: str(r["name"]))
    return Figures(convention=conv, values=values, detail=detail,
                   states=tuple(states))


def _pairwise_figures(cells, conv: str, models, names,
                      field: FieldCells) -> Figures:
    """Every pairwise figure a season page prints, over one shared frame.

    The field is narrowed once (our seasons, jurisdictions only) and the
    per-state tournaments run on slices (re-filtering costs ~1 s per state).
    """
    import pandas as pd
    hub = [m for m in field.models if not m.startswith("FluBNF-")]
    # states only and only the seasons this run scored, as the dashboard does:
    # field US rows would move every theta and so the baseline scaling
    seasons = {season_of(d) for d in cells["reference_date"].unique()}
    seasons.discard("")
    fc = field.cells
    fc = fc[fc["location"].map(_is_state)]
    if seasons:
        fc = fc[fc["reference_date"].map(season_of).isin(seasons)]
    if not len(fc):
        return _empty(conv, ("the cached hub field data covers no season "
                             "this run scored"), field.source)
    ours = cells[cells["model"] != BASELINE]
    both = pd.concat([fc, ours], ignore_index=True)
    values, detail = {}, {}
    for m in models:
        got = insert_model(both, SEAL_MODEL_NAMES.get(m, m), hub)
        if got:
            # rank and n_models ride along unprinted (placement withdrawn)
            values[m] = got["value"]
            detail[m] = {"n_cells": got["n_cells"], "rank": got["rank"],
                         "n_models": got["n_models"]}
    if not values:
        return _empty(conv, ("no overlap between this run's cells and the "
                             "cached hub field data, so no pairwise "
                             "comparison exists"), field.source)
    states = []
    for loc, g in both.groupby("location", sort=True):
        row = {"name": names.get(loc, loc), "detail": {}}
        hit = False
        for m in models:
            here = insert_model(g, SEAL_MODEL_NAMES.get(m, m), hub)
            row[m] = here.get("value") if here else None
            row["detail"][m] = ({"n_cells": here["n_cells"],
                                 "rank": here["rank"],
                                 "n_models": here["n_models"]}
                                if here else {})
            hit = hit or row[m] is not None
        if hit:
            states.append(row)
    states.sort(key=lambda r: str(r["name"]))       # see _ratio_figures
    # the field the (unprinted) ranks were taken in, minus our member; not the
    # cache's team count, which spans every season it covers
    n_field = max((d["n_models"] for d in detail.values()), default=1) - 1
    return Figures(convention=conv, values=values, detail=detail,
                   states=tuple(states), source=field.source,
                   n_field=n_field)


def season_figures(scores_df, convention: str = DEFAULT_CONVENTION,
                   field: FieldCells = None, models: tuple = MODELS
                   ) -> Figures:
    """Every relWIS figure a season page prints, under ONE convention.

    `scores_df` must already be narrowed to the published scope (pass it
    through us_national.pooled_frame first). Season figures and state rows
    come from the same convention; an uncomputable pairwise result is empty
    and says why, never the other convention.
    """
    conv = convention_of(convention)
    cells = seal_cells(scores_df)
    if not len(cells):
        return _empty(conv, "no scored cells")
    # FIPS -> printed name from the frame itself (name-keyed frames need none)
    names = {}
    cols = set(getattr(scores_df, "columns", ()))
    if {"fips", "location"} <= cols:
        for f, n in zip(scores_df["fips"].astype(str).str.zfill(2),
                        scores_df["location"]):
            names.setdefault(str(f), str(n))
    if conv == RATIO_OF_SUMS:
        return _ratio_figures(cells, conv, models, names)
    f = field if field is not None else load_field_cells()
    if not f.available:
        return _empty(conv, f.reason, f.source)
    return _pairwise_figures(cells, conv, models, names, f)
