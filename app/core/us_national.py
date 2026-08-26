"""The US national series: one resolution order, one provenance vocabulary,
one named scoring policy.

Three surfaces used to answer "what is the US number here" in three
different ways, and none of them said which answer the reader was looking
at. This module is the single place that answers both halves of the
question at once: the data, and where the data came from.

PROVENANCE, three states and no others:

  fitted          the replay (or the console run) fitted the US series as
                  its own location, exactly as it fits a state. The number
                  is a model output at the national level.
  aggregated      no national fit exists, so the national figure is
                  CONSTRUCTED by summing the fitted state forecasts
                  (retro.national_aggregate). It is a derived quantity, not
                  a model output, and states are treated as independent.
  officials_only  neither exists. The US view carries the CDC comparators
                  alone, which is what the hub archive supplies.

Resolution order is fitted, then aggregated, then officials_only; `resolve`
is the only implementation of it. A fitted number and an aggregated number
are DIFFERENT MODEL OUTPUTS and must never be interchangeable without the
reader noticing, so every result carries the label and the note that say
which one it is, and every surface prints one of them.

SCORING POLICY (see POOLED_INCLUDES_US below): the pooled relWIS headline
covers the fitted jurisdictions only. US never joins it. That is a named
decision here rather than an accident of which locations a given run
happened to cover, so fitting US changes no published headline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: The hub's FIPS code for the national row, and every spelling of the
#: national location name this application has ever written into a run
#: record, a samples file, or a form post.
US_FIPS = "US"
US_SPELLINGS = ("US", "US (NATIONAL)", "UNITED STATES", "USA")

#: The three provenance states. Nothing outside this tuple is a valid
#: answer, and a surface that cannot say which one it has must say that
#: rather than guess.
FITTED = "fitted"
AGGREGATED = "aggregated"
OFFICIALS_ONLY = "officials_only"
PROVENANCES = (FITTED, AGGREGATED, OFFICIALS_ONLY)

#: The members a season scores, in the order every table prints them.
MODELS = ("pf", "analogue", "ensemble")

#: THE long label for each provenance: what a location picker, a chart
#: title, or a legend calls the national series. `label()` is the accessor;
#: the aggregated form names the state count when the caller knows it, so a
#: six-state panel can never read as though it had summed the country.
LABELS = {
    FITTED: "US national (fitted)",
    AGGREGATED: "US national (sum of states)",
    OFFICIALS_ONLY: "US (official models only)",
}

#: THE short label, for a table row or a verdict tile where the column
#: header already supplies the context. "US (aggregated)" is the wording
#: the season page and both report exports have always used for the
#: constructed figure; it is kept exactly so no published artifact is
#: silently reworded.
SHORT_LABELS = {
    FITTED: "US (fitted)",
    AGGREGATED: "US (aggregated)",
    OFFICIALS_ONLY: "US (officials only)",
}

#: THE one-sentence provenance note. Every surface that prints a US number
#: prints the matching note beside it, so a reader comparing two seasons
#: cannot mistake a fitted national forecast for a constructed one.
NOTES = {
    FITTED: (
        "US (fitted) is a national forecast in its own right: the run fitted "
        "the US series as its own location, with the same members, the same "
        "particles, and the same replicates as every state, and scored it "
        "against the US truth row."),
    AGGREGATED: (
        "US (aggregated) is not a fitted national forecast: the run fitted "
        "states only, so each member is aggregated from its state forecasts "
        "with states treated as independent (PF by summing its per-state "
        "sample draws, aligned by draw index; the analogue by drawing from "
        "each state's quantile curve independently and summing), and the two "
        "national member quantile sets are then vincentized 50/50, the "
        "shipped ensemble recipe. Scored against the US truth row with the "
        "same relWIS machinery as every state."),
    OFFICIALS_ONLY: (
        "No national forecast of ours exists for this season: the run fitted "
        "states only and the sum-of-states aggregate could not be "
        "constructed, so the US view carries the CDC comparators alone."),
}

#: The plain word for the fallback, used where a surface needs to flag that
#: it is NOT showing the preferred answer.
FALLBACK_WORD = "fallback"

#: How the aggregated and officials-only states read when a surface has to
#: name them as fallbacks in one clause.
FALLBACK_NOTES = {
    AGGREGATED: ("fallback: no US fit exists for this season, so the figure "
                 "shown is aggregated from state forecasts"),
    OFFICIALS_ONLY: ("fallback: no US fit and no sum-of-states aggregate "
                     "exist for this season, so only the CDC comparators "
                     "are shown"),
}


# ------------------------------------------------------- scoring policy

#: THE named scoring decision (2026-08-26), NOT an emergent property of
#: which locations a run happened to cover.
#:
#: The pooled relWIS headline (0.8131 / 0.6179 / 0.6827, pooled 0.6781 over
#: 15,460 cells) is a 52-JURISDICTION average: 50 states, DC, and Puerto
#: Rico. The US national series is the sum of those same 52 constituents,
#: so adding it to the pooled average is a change of convention rather than
#: a new measurement, and it would move a number printed in a public
#: release, in CITATION.cff, and in a manuscript.
#:
#: Fitting US must therefore change no headline. `pooled_frame` is the one
#: gate; flipping this flag is the only way US would ever join the pooled
#: figure, and doing so would require re-publishing every one of those
#: numbers. app/tests/test_us_national.py fails if a US cell ever reaches
#: the pooled sums.
POOLED_INCLUDES_US = False

#: The sentence every surface prints when it states what the pooled figure
#: covers.
POOLED_SCOPE_NOTE = (
    "Pooled relWIS covers the fitted jurisdictions only (50 states, DC, and "
    "Puerto Rico). The US national cell is reported separately and never "
    "joins the pooled average: the national series is the sum of those same "
    "jurisdictions, so pooling it in would count them twice.")


# ---------------------------------------------------------- identification

def is_us(loc) -> bool:
    """Whether a location name or FIPS code names the national series.

    One spelling test for the whole application. `US`, `US (national)`, and
    the FIPS code `US` are all the national row; nothing else is."""
    return str(loc).strip().upper() in US_SPELLINGS


def state_names(locations) -> list:
    """The jurisdictions in a location list, national row removed."""
    return [l for l in (locations or []) if not is_us(l)]


def with_us(locations, us_name: str = US_FIPS) -> list:
    """A location list with the national row present exactly once, appended
    last. Idempotent: a list that already names US is returned unchanged, in
    its own spelling, so an existing run's list is never rewritten."""
    locs = list(locations or [])
    if any(is_us(l) for l in locs):
        return locs
    return locs + [us_name]


# -------------------------------------------------------- frame splitting

def pooled_frame(df):
    """The scored frame the POOLED headline is computed from.

    Every pooled sum in the application goes through this function, so the
    52-jurisdiction convention is enforced in one place instead of relying
    on US never having been fitted. See POOLED_INCLUDES_US."""
    if df is None or "location" not in getattr(df, "columns", ()):
        return df
    if POOLED_INCLUDES_US:
        return df
    return df[~df["location"].map(is_us)]


def us_frame(df):
    """The scored frame's US rows alone, or None when it carries none."""
    if df is None or "location" not in getattr(df, "columns", ()):
        return None
    sub = df[df["location"].map(is_us)]
    return sub if len(sub) else None


def pooled_locations(names) -> list:
    """A location NAME list under the same policy, for surfaces that hold
    names rather than a frame (per-state tables, map card sets)."""
    if POOLED_INCLUDES_US:
        return list(names or [])
    return state_names(names)


# ------------------------------------------------------------- the answer

def label(provenance: str, n_states: int | None = None) -> str:
    """The long label for a provenance. The aggregated form names its state
    count when the caller knows it, so `US national (sum of 52 states)`
    reads on a full grid and `US national (sum of 6 states)` on a panel."""
    if provenance == AGGREGATED and n_states:
        return f"US national (sum of {int(n_states)} states)"
    return LABELS.get(provenance, LABELS[OFFICIALS_ONLY])


def short_label(provenance: str) -> str:
    return SHORT_LABELS.get(provenance, SHORT_LABELS[OFFICIALS_ONLY])


def note(provenance: str) -> str:
    return NOTES.get(provenance, NOTES[OFFICIALS_ONLY])


@dataclass(frozen=True)
class UsNational:
    """What the US series is for one season, and where it came from.

    `scores` maps member name to relWIS, or to None where that member has
    no scoreable national cell. `cells` maps member name to the cell count
    behind its score. Both are empty under `officials_only`, which is the
    honest answer when we have no national forecast at all."""

    provenance: str
    scores: dict = field(default_factory=dict)
    cells: dict = field(default_factory=dict)
    n_states: int | None = None
    reason: str = ""

    @property
    def is_fitted(self) -> bool:
        return self.provenance == FITTED

    @property
    def is_fallback(self) -> bool:
        """Whether this is the fallback rather than the preferred answer.
        Every surface that shows a fallback says that it is one."""
        return self.provenance != FITTED

    @property
    def label(self) -> str:
        return label(self.provenance, self.n_states)

    @property
    def short_label(self) -> str:
        return short_label(self.provenance)

    @property
    def note(self) -> str:
        return note(self.provenance)

    @property
    def fallback_note(self) -> str:
        return FALLBACK_NOTES.get(self.provenance, "")

    @property
    def has_scores(self) -> bool:
        return any(self.scores.get(m) for m in MODELS)

    def get(self, model, default=None):
        """Dict-style access, so a Jinja template can print `us.pf` beside
        the members it already prints that way."""
        return self.scores.get(model, default)

    def __getitem__(self, model):
        return self.scores.get(model)

    def as_dict(self) -> dict:
        """The JSON-safe form the templates, the player config, and the
        exported artifacts carry. The provenance and its wording travel
        WITH the numbers: nothing downstream may print a US score without
        also holding the label that says which kind of score it is."""
        d = {"provenance": self.provenance, "label": self.label,
             "short_label": self.short_label, "note": self.note,
             "fitted": self.is_fitted, "fallback": self.is_fallback,
             "fallback_note": self.fallback_note,
             "n_states": self.n_states, "cells": dict(self.cells)}
        d.update({m: self.scores.get(m) for m in MODELS})
        if self.reason:
            d["reason"] = self.reason
        return d


#: The shipped, never-self-fitted member weights the season scoring uses.
#: The aggregate must be THE aggregate, not a reweighted cousin.
DEFAULT_WEIGHTS = {"pf": 0.5, "analogue": 0.5}


def from_scores(df) -> UsNational | None:
    """The fitted answer read straight out of a season's scores frame, or
    None when the frame carries no national rows. relWIS is sum(wis) over
    sum(base_wis), the frozen formula, per member."""
    sub = us_frame(df)
    if sub is None:
        return None
    scores, cells = {}, {}
    for m in MODELS:
        g = sub[sub["model"] == m] if "model" in sub.columns else sub[:0]
        bs = float(g["base_wis"].sum()) if len(g) else 0.0
        scores[m] = (float(g["wis"].sum()) / bs) if bs else None
        cells[m] = int(len(g))
    n_states = None
    if df is not None and "location" in getattr(df, "columns", ()):
        n_states = int(pooled_frame(df)["location"].nunique())
    return UsNational(FITTED, scores=scores, cells=cells, n_states=n_states)


def resolve(root, scores_df=None, ensemble_weights=None,
            allow_aggregate: bool = True) -> UsNational:
    """THE resolution order for one season root: a fitted US cell, else the
    sum-of-states aggregate, else officials only.

    This is the only implementation. Every consumer (the season page, the
    playback stats, the season report, the exported files) calls it and
    prints the label it returns; none of them re-derives the order.

    `scores_df` is the season's scores frame when the caller already holds
    it (the season page does), and is loaded here otherwise. `ensemble_
    weights` is passed straight through to the aggregate construction; the
    default is the shipped 50/50 pair the season scoring uses.

    `allow_aggregate=False` skips the constructed fallback for callers that
    must not pay its compute cost (it is minutes on a cold cache). Such a
    caller gets `officials_only` and must say so, never an aggregate it did
    not actually compute."""
    root = Path(root)
    if scores_df is None:
        try:
            from app.core import playback
            scores_df = playback._season_scores(root)
        except Exception:
            scores_df = None

    fitted = from_scores(scores_df)
    if fitted is not None and fitted.has_scores:
        return fitted

    n_states = None
    if scores_df is not None and "location" in getattr(scores_df,
                                                       "columns", ()):
        n_states = int(pooled_frame(scores_df)["location"].nunique()) or None

    if not allow_aggregate:
        return UsNational(OFFICIALS_ONLY, n_states=n_states,
                          reason="the aggregate was not computed here")

    row, reason = aggregate_row(root, ensemble_weights)
    if row:
        scores = {m: (float(row[m]) if row.get(m) else None) for m in MODELS}
        cells = {m: int((row.get("cells") or {}).get(m, 0)) for m in MODELS}
        return UsNational(AGGREGATED, scores=scores, cells=cells,
                          n_states=n_states)
    return UsNational(OFFICIALS_ONLY, n_states=n_states, reason=reason)


def aggregate_row(root, ensemble_weights=None) -> tuple:
    """(row, reason): the constructed sum-of-states aggregate for a season
    root, or (None, why it could not be delivered) in words an artifact can
    print. Silent omission is the failure class this replaced."""
    from app.core import retro as _retro
    weights = ensemble_weights if ensemble_weights is not None \
        else DEFAULT_WEIGHTS
    try:
        row = _retro.national_aggregate(Path(root), ensemble_weights=weights)
    except Exception as e:
        return None, ("its construction failed while this view was built "
                      f"({type(e).__name__}: {str(e)[:120]})")
    if not row or not any(row.get(m) for m in MODELS):
        return None, ("its construction returned no scoreable national "
                      "cells for this season")
    return row, ""
