"""Relative WIS: two conventions, kept apart on purpose.

Two different quantities are called "relative WIS" in influenza forecasting
and this project has already been burned by mixing them. A project figure
was read next to the CDC FluSight dashboard and the gap turned out to be a
convention difference, not an error. Both definitions are correct. They
answer different questions, they are computed from different inputs, and
their numbers are NOT comparable with each other. Nothing in this module,
and nothing that consumes it, may put the two in one table or let one stand
in for the other.

RATIO OF SUMS (`ratio_of_sums`) -- this project's home convention

    relWIS = sum(model WIS over cells) / sum(baseline WIS over the same
    cells). Cell-weighted, so a busy peak week counts for more than a quiet
    October one, which is what a "how much total loss did the season cost"
    question wants. It needs only the model's own scored cells and the
    FluSight-baseline score that already sits beside each of them in the
    seal, so it is ALWAYS computable.

PAIRWISE SCALED RELATIVE WIS (`pairwise_scaled`) -- what CDC reports

    The scoringutils / Cramer et al. definition the FluSight dashboard and
    the official hub report use. For every ordered pair of models (i, j),
    theta_ij = mean WIS of i divided by mean WIS of j, computed ONLY on the
    cells BOTH models submitted. A model's relative skill is the geometric
    mean of theta_ij over all j != i. The published figure scales that by
    FluSight-baseline's own relative skill, so the baseline sits at exactly
    1.0.

    Mean-based, so every cell weighs the same. Field-dependent, so adding
    or removing a team moves everyone's number, which is why a figure under
    this convention is meaningless without naming the field it was computed
    against. And it needs EVERY OTHER TEAM's per-cell WIS, which comes from
    the hub's model-output tree, so it is NOT always computable.
    `load_field_cells` reports absence as a normal state; no caller may
    quietly substitute the ratio-of-sums number in its place.

The pairwise implementation here is a faithful port of the reference
tournament that reproduced the CDC dashboard's published 2025-26 figure
(FluSight-ensemble 0.6696 against a published 0.67, 56 of 57 models inside
the report's two-decimal rounding). The definition is not ours to improve:
the entire point is to match CDC exactly.

THE CELL FRAME. Every function below is a pure function over one frame with
these columns, one row per scored cell per model:

    model            str, the model's name in the field's own vocabulary
    reference_date   str, YYYY-MM-DD, the hub's submission Saturday
    location         str, zero-padded FIPS
    horizon          int, hub-coded 0-3
    wis              float

Cells are keyed (reference_date, location, horizon). The seal's scores.json
is a different shape (model, location, fips, asof, horizon, wis, base_wis,
rel) and `seal_cells` performs the one conversion, including the project's
frozen join reference_date = asof + 7 days (see app/core/submit.py
hub_reference_date; the reference reproduction verified this mapping
empirically against the hub's own baseline submissions).

WHERE THE FIELD CELLS LIVE. The pairwise convention needs one cached
artifact: a directory of per-model CSVs, one row per scored cell, with the
CELL_COLUMNS headers. It is built by scoring every hub model's own
submission files against the hub's settled truth with flubnf.wis.wis, the
same function every sealed FluBNF number came from. That builder,
score_hub.py, lives OUTSIDE this repository, so nothing here can rebuild
the cache: this module only reads it. The app looks at $FLUBNF_FIELD_CELLS
first and app/state/field_cells second, and at nothing else. It used to
probe a third path under the running user's home directory, which is where
the reference tournament happened to keep its output; that was dropped
because a public runtime has no business reading a fixed location outside
its own tree, and one environment variable says the same thing explicitly.
app/state is gitignored and CI has neither a hub clone nor an app/state, so
the cache is absent far more often than it is present, and absence is a
state to report rather than a failure to survive.

RANKS ARE COMPUTED HERE AND NOT DISPLAYED. `insert_model` returns a rank
and a field size beside the value, and `_pairwise_figures` carries both
into `Figures.detail`. No page prints them. The reason is a difference in
what the two quantities need to be defensible: the pairwise VALUE is this
project's own score under one stated convention, reproducible end to end
from the sealed per-cell scores that ship with the retrospective, whereas
the RANK additionally asserts that the whole FluSight field was scored on
that same convention, and that half rests on an out-of-repo builder nobody
can rerun from this checkout. Placement against the field was withdrawn on
2026-08-24 (see app/ui/templates/methods.html and docs/RELEASE-1.0.md).

Porting that builder in is NOT on its own the condition for lifting the
withdrawal, and this comment said it was until 2026-08-31. The record in
docs/RELEASE-1.0.md found three faults, and the missing builder is only the
first: the archived field could not be reproduced from this repository's
scoring code either, and one of this project's own published rows carried
the leave-one-season-out fitted ensemble weights it rejects and does not
ship, which no amount of tooling answers. The record's condition is that
the field AND this project's entry are scored again, end to end, on one
stated convention and on the shipped configuration. The machinery is kept
computed and tested so that meeting it is a display decision and not a
rewrite, not because meeting it is close.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

#: The columns a cell frame carries, and the key that identifies a cell.
CELL_COLUMNS = ("model", "reference_date", "location", "horizon", "wis")
CELL_KEY = ["reference_date", "location", "horizon"]

#: The comparator both conventions are stated against. Under ratio of sums
#: it is the denominator; under the pairwise convention it is the model the
#: whole field's relative skill is scaled by, which is what puts it at 1.0.
BASELINE = "FluSight-baseline"

#: The two conventions. These strings are the switch's vocabulary: they
#: appear in URLs, in template conditionals, and in the tests.
RATIO_OF_SUMS = "ratio_of_sums"
PAIRWISE = "pairwise"
CONVENTIONS = (RATIO_OF_SUMS, PAIRWISE)

#: Ratio of sums is the default everywhere because it is the convention
#: every sealed number in this repository was computed under, and because
#: it is always available. Changing this default would silently restate
#: every published figure.
DEFAULT_CONVENTION = RATIO_OF_SUMS

#: How each convention is named to a reader. `name` titles a switch, `short`
#: rides beside a number as the label that says which quantity it is, and
#: `blurb` is the one-sentence statement of the definition. Every surface
#: that prints a relWIS prints one of these beside it: an unlabelled figure
#: is exactly the failure this module exists to prevent.
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

#: THE one sentence every surface prints beside a published relWIS.
#:
#: Both conventions are ratios scaled so FluSight-baseline sits at exactly
#: 1.0, so "a ratio against the FluSight baseline" describes them equally
#: and therefore labels neither: it looks like a label and identifies
#: nothing. The naming has to say WHICH ratio, and it has to warn the one
#: reader who will actually be misled, the one holding a figure here up
#: against the CDC dashboard. Kept as a single string, reached by the
#: templates through a Jinja global and imported by the site and report
#: builders, so the home page, Methods, the published site and the exported
#: report cannot drift into four wordings of the same warning.
PUBLISHED_CONVENTION_NOTE = (
    "Every relWIS here is a ratio of sums: total model WIS over total "
    "FluSight-baseline WIS on the same cells. The CDC FluSight dashboard "
    "reports a different quantity, a pairwise scaled relative WIS, so a "
    "figure here is not comparable with one there.")

#: The seal's member keys mapped into the field's naming, so our rows and
#: the hub's rows can sit in one frame without a name collision.
SEAL_MODEL_NAMES = {"pf": "FluBNF-PF", "analogue": "FluBNF-analogue",
                    "ensemble": "FluBNF-ensemble"}

#: Where the app looks for the cached field cells, in order. The cache is a
#: directory of per-model CSVs (model, reference_date, target_end_date,
#: location, horizon, wis) produced by scoring every hub model's own
#: submissions with this project's WIS function. It is DATA, not code: it
#: is large, it is derived from a hub clone, and app/state is gitignored,
#: so it never ships with the repository and its absence is normal.
#:
#: Two candidates and no more. A machine that keeps the cache anywhere else
#: names it in the environment variable; the runtime does not go looking
#: under anybody's home directory for it.
FIELD_CELLS_ENV = "FLUBNF_FIELD_CELLS"
APP_STATE = Path(__file__).resolve().parents[1] / "state"
FIELD_CELLS_DEFAULT = APP_STATE / "field_cells"

#: What a reader on a machine without the cache needs to be told: what the
#: missing thing is, and what would put it there. Appended to every
#: unavailability reason, because "no hub field data cached" on its own
#: reads as a fault in the app rather than a normal absent input.
FIELD_CELLS_HOWTO = (
    "The cache is a directory of per-model score files, one row per "
    "scored cell; it is built from a FluSight hub clone by the "
    "out-of-repo score_hub.py and then pointed at with "
    f"${FIELD_CELLS_ENV} or placed in {FIELD_CELLS_DEFAULT}")


def _is_state(location) -> bool:
    """A jurisdiction row rather than the national one. One spelling test
    for the whole application lives in us_national; this is its inverse,
    imported lazily so this module stays importable on its own."""
    from app.core.us_national import is_us
    return not is_us(location)


def season_of(reference_date: str) -> str:
    """The influenza season a hub reference date belongs to, YYYY-YY.

    August is the boundary the hub's own season windows use. The pairwise
    convention is computed within a season because the published dashboard
    figure is: a model's field is the teams that submitted that season.
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

    Anything unrecognised resolves to the default rather than raising: a
    mistyped query parameter must not be able to take the retrospective
    down, and the page names the convention it actually used anyway.
    """
    v = str(value or "").strip().lower()
    return v if v in CONVENTIONS else DEFAULT_CONVENTION


def convention_info(convention: str) -> dict:
    """The naming for one convention, normalised first."""
    return CONVENTION_INFO[convention_of(convention)]


def field_cells_dir() -> Path:
    """Where to look for the cached field cells.

    The environment wins outright, then the app's own state directory. The
    default is returned when neither exists, so an unavailability message
    can always name a real path.
    """
    env = os.environ.get(FIELD_CELLS_ENV)
    if env:
        return Path(env).expanduser()
    return FIELD_CELLS_DEFAULT


# --------------------------------------------------------------------------
# the cell frame
# --------------------------------------------------------------------------

def seal_cells(df, models: dict = None):
    """The seal's per-cell scores as a cell frame, baseline rows included.

    The seal carries base_wis beside every model's wis for the same cell,
    which is the FluSight-baseline score for that cell; it is emitted once
    per cell as a BASELINE row so ratio_of_sums can be a pure function over
    the frame rather than a special case reading a second column.

    Returns an empty frame (with the right columns) for anything unusable,
    so callers never have to guard the shape.
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
    # FIPS identifies a cell; the location NAME stands in when a frame
    # carries no fips column (older and synthetic score tables do not). A
    # name is a perfectly good cell id inside one frame, and only the
    # pairwise convention, which joins against hub cells keyed by FIPS,
    # needs the codes themselves.
    key_col = "fips" if "fips" in d.columns else "location"
    d["location"] = d[key_col].astype(str).str.zfill(2)
    # horizon is part of the cell key, so a frame without one has exactly
    # one cell per (week, location) and a constant serves as that key
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
        # one baseline row per cell: the same base_wis is repeated beside
        # every member of the same cell, and counting it three times would
        # not change ratio_of_sums but would corrupt any mean over cells
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

    A faithful port: mean WIS on the cells BOTH models submitted, geometric
    mean over the whole field, then the baseline scaling. Pairs with no
    overlap and non-positive means are skipped, exactly as the reference
    implementation skips them.
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

    Alone is the honest way to read a field-dependent number: inserting all
    three members at once changes every other team's figure as well, so the
    rank would no longer be the rank the model would actually have taken.

    The `rank` and `n_models` in the result are COMPUTED AND NOT PRINTED;
    see the module docstring for why placement stays withdrawn while the
    value is published, and for the condition that would lift it, which is
    a re-scoring and not just a ported script. They are kept because the
    ranking is what makes the insertion meaningful to test, and so that
    reinstating the display stays a one-line change whenever that day comes.

    Returns {} when the tournament cannot be run on this frame.
    """
    order = [m for m in field if m != model] + [model]
    scaled, n_cells = pairwise_scaled(cells, order, baseline=baseline)
    # A model can be IN `scaled` and still have no figure: pairwise_scaled
    # returns nan for a model that shared no cell with anybody (its own
    # geometric mean had no terms). That is a real state here rather than a
    # theoretical one, because the field cells are a cached artifact built
    # out of repo at some past moment: one jurisdiction where the cache's
    # weeks and this run's weeks do not meet, while the rest of the field
    # still overlaps itself, produces exactly it. Both checks are needed.
    # `ranked` drops nan, so testing membership alone and then indexing
    # `ranked` raised ValueError, taking the whole season page down with a
    # 500 rather than leaving one row blank; a figure that does not exist
    # is the documented empty result.
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

    `available` false is a NORMAL state, not an error: the cache is derived
    from a hub clone that CI does not have and that a fresh machine has not
    built. `reason` is the sentence a page prints in place of the numbers.
    Nothing may respond to absence by computing the other convention.
    """
    cells: object = None
    models: tuple = ()
    source: str = ""
    reason: str = ""
    #: An identity for THESE cached files, so a caller that memoises a
    #: tournament can tell a rebuilt cache from the one it computed against.
    stamp: str = ""

    @property
    def available(self) -> bool:
        return self.cells is not None and len(self.cells) > 0


#: One parsed field frame, keyed by the directory and the CSVs' identities,
#: so 677k scored cells are read from disk once rather than per page view.
_FIELD_CACHE: dict = {}


def load_field_cells(directory=None) -> FieldCells:
    """Load the cached field cells, or say why there are none.

    Never raises for a missing, empty, or unreadable cache: every one of
    those is reported through `reason`, because the pairwise convention
    being unavailable is a thing the retrospective must be able to state
    calmly rather than a failure it has to survive.
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
            # one unreadable team file must not cost the whole field; the
            # coverage counts beside every figure show what was actually in
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

#: The members every retrospective surface prints, in the order it prints
#: them. Same tuple as us_national.MODELS; repeated here so this module can
#: be read and tested without that one.
MODELS = ("pf", "analogue", "ensemble")


@dataclass(frozen=True)
class Figures:
    """One set of relWIS figures and the convention that produced them.

    The convention travels WITH the numbers, in the same object, because
    the failure this module exists to prevent is a figure reaching a reader
    without its definition attached. An unavailable set carries no numbers
    at all: there is deliberately nothing to fall back into, only `reason`.
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

    Same arithmetic as `ratio_of_sums`, done once for the season and once
    per jurisdiction off a single baseline join and two grouped sums. The
    per-model-per-state loop that reads naturally costs a merge per cell
    group, which a 52-row table pays 156 times on every page view.
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
    # by the NAME the table prints, not by the FIPS the cells are keyed on.
    # The two orders agree for the states (FIPS was assigned alphabetically)
    # and disagree for the territories, so sorting on the key would drop
    # Puerto Rico past Wyoming; the table's own script documents that the
    # page loads in alphabetical order.
    states.sort(key=lambda r: str(r["name"]))
    return Figures(convention=conv, values=values, detail=detail,
                   states=tuple(states))


def _pairwise_figures(cells, conv: str, models, names,
                      field: FieldCells) -> Figures:
    """Every pairwise figure a season page prints, over one shared frame.

    The field is narrowed ONCE -- to the seasons our own cells span and to
    jurisdictions only -- and the per-state tournaments then run on slices
    of that narrowed frame. Re-filtering 600k+ field rows per state instead
    costs about a second each, which is the whole difference between a page
    and a page nobody waits for.
    """
    import pandas as pd
    hub = [m for m in field.models if not m.startswith("FluBNF-")]
    # STATES ONLY, and only the seasons this run scored. A pairwise figure
    # means nothing without naming its field, and both narrowings are part
    # of that name: the published dashboard convention is states only and
    # one season at a time, and this project's pooled scope is states only
    # as well. Leaving the field's US rows in would move every hub-vs-hub
    # theta and so the baseline scaling our own number is divided by.
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
            # rank and n_models ride along UNPRINTED: the season page shows
            # the value and the cell coverage, never the placement. See the
            # module docstring; the withdrawal is a stated policy, not an
            # oversight, and deleting the fields here would make lifting it
            # a rewrite instead of a template change.
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
    # THE field size is the one the ranks were taken in, so it is read back
    # out of the tournaments rather than counted off the cache. `hub` is
    # every team the cache holds across every season it covers (84 here),
    # while a tournament runs against the teams that actually submitted
    # THIS season, in the jurisdictions this figure covers; counting the
    # cache instead would state a field the number was never computed
    # against. n_models counts the insertion's field including our own
    # member, so the other teams are one fewer. Like the ranks, this is
    # computed and not printed while placement stays withdrawn: it is the
    # field size the withheld ranks belong to, and a field size on its own
    # tells a reader nothing the value does not.
    n_field = max((d["n_models"] for d in detail.values()), default=1) - 1
    return Figures(convention=conv, values=values, detail=detail,
                   states=tuple(states), source=field.source,
                   n_field=n_field)


def season_figures(scores_df, convention: str = DEFAULT_CONVENTION,
                   field: FieldCells = None, models: tuple = MODELS
                   ) -> Figures:
    """Every relWIS figure a season page prints, under ONE convention.

    `scores_df` is the seal's (or a live run's) scores frame, already
    narrowed to the scope the caller means to publish: pass it through
    app/core/us_national.pooled_frame first, exactly as the results page
    does, so both conventions cover the same cells.

    The returned object carries the season figures AND the per-jurisdiction
    rows, both from the same convention, because a page that mixed them
    would be doing the one thing this module exists to prevent. When the
    pairwise convention cannot be computed the result is empty and says
    why; it never quietly becomes the other convention.
    """
    conv = convention_of(convention)
    cells = seal_cells(scores_df)
    if not len(cells):
        return _empty(conv, "no scored cells")
    # FIPS to the jurisdiction name the rest of the retrospective prints;
    # the seal frame carries both, so no locations table is needed here. A
    # frame without a fips column is already keyed by name (see seal_cells)
    # and needs no map at all.
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
