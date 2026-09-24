"""PRODUCTION: US national resolution, labels and the pooled-scope policy
(every scoring surface).

The US national series: one resolution order, one provenance vocabulary,
one named scoring policy. Every surface asks here what the US number is and
where it came from.

PROVENANCE, three states and no others:

  fitted          the run fitted US as its own location: a model output.
  aggregated      CONSTRUCTED by summing the state forecasts
                  (retro.national_aggregate), states independent: derived,
                  not a model output.
  officials_only  neither exists; only the CDC comparators.

`resolve` is the only implementation of the order fitted > aggregated >
officials_only. Fitted and aggregated are DIFFERENT model outputs, so every
result carries the label and note saying which, and surfaces print them.

SCORING POLICY (POOLED_INCLUDES_US): the pooled headline covers the
jurisdictions only; US never joins it, so fitting US changes no headline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: the hub's national FIPS, and every spelling of it ever written by the app
US_FIPS = "US"
US_SPELLINGS = ("US", "US (NATIONAL)", "UNITED STATES", "USA")

#: the only valid provenance states
FITTED = "fitted"
AGGREGATED = "aggregated"
OFFICIALS_ONLY = "officials_only"
PROVENANCES = (FITTED, AGGREGATED, OFFICIALS_ONLY)

#: print order; the retired blend last (older scores frames carry its rows)
MODELS = ("pf", "analogue", "ensemble")

#: THE long label (pickers, titles, legends); `label()` adds the state count
LABELS = {
    FITTED: "US national (fitted)",
    AGGREGATED: "US national (sum of states)",
    OFFICIALS_ONLY: "US (official models only)",
}

#: THE short label (table rows, tiles). "US (aggregated)" is kept verbatim
#: for published artifacts; must equal player.js US_LABELS_JSON
SHORT_LABELS = {
    FITTED: "US (fitted)",
    AGGREGATED: "US (aggregated)",
    OFFICIALS_ONLY: "US (officials only)",
}

#: THE provenance note printed beside every US number
NOTES = {
    FITTED: (
        "US (fitted) is a national forecast in its own right: the run fitted "
        "the US series as its own location, with the same members, the same "
        "particles, and the same replicates as every state, and scored it "
        "against the US truth row."),
    AGGREGATED: (
        "US (aggregated) is not a fitted national forecast: the scores for "
        "this season carry no fitted national cell, so each member is "
        "aggregated from its state forecasts "
        "with states treated as independent (PF by summing its per-state "
        "sample draws, aligned by draw index; the analogue by drawing from "
        "each state's quantile curve independently and summing). Scored "
        "against the US truth row with the same relWIS machinery as every "
        "state."),
    OFFICIALS_ONLY: (
        "No national forecast of ours exists for this season: the run fitted "
        "states only and the sum-of-states aggregate could not be "
        "constructed, so the US view carries the CDC comparators alone."),
}

#: the word flagging a non-preferred answer
FALLBACK_WORD = "fallback"

#: the fallback states in one clause
FALLBACK_NOTES = {
    AGGREGATED: ("fallback: the scores for this season hold no scored US "
                 "fit, so the figure shown is aggregated from state "
                 "forecasts"),
    OFFICIALS_ONLY: ("fallback: no scored US fit and no sum-of-states "
                     "aggregate exist for this season, so only the CDC "
                     "comparators are shown"),
}


# ------------------------------------------------------- scoring policy

#: Named policy (2026-08-26): pooled relWIS is a 52-jurisdiction figure and
#: US (their sum) never joins it; flipping this restates every published
#: number. pooled_frame is the one gate; app/tests/test_us_national.py enforces it.
POOLED_INCLUDES_US = False

#: what every surface prints about the pooled figure's scope
POOLED_SCOPE_NOTE = (
    "Pooled relWIS covers the fitted jurisdictions only (50 states, DC, and "
    "Puerto Rico). The US national cell is reported separately and never "
    "joins the pooled average: the national series is the sum of those same "
    "jurisdictions, so pooling it in would count them twice.")


# ---------------------------------------------------------- identification

def is_us(loc) -> bool:
    """Whether a location name or FIPS code names the national series: the
    one spelling test for the whole application."""
    return str(loc).strip().upper() in US_SPELLINGS


def state_names(locations) -> list:
    """The jurisdictions in a location list, national row removed."""
    return [l for l in (locations or []) if not is_us(l)]


def with_us(locations, us_name: str = US_FIPS) -> list:
    """The list with US appended once; a list already naming US is returned
    unchanged (its own spelling kept)."""
    locs = list(locations or [])
    if any(is_us(l) for l in locs):
        return locs
    return locs + [us_name]


# -------------------------------------------------------- frame splitting

def pooled_frame(df):
    """The scored frame the POOLED headline is computed from: every pooled
    sum goes through here (POOLED_INCLUDES_US)."""
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
    """The long label; the aggregated form names its state count when known
    (so a 6-state panel never reads as the whole country)."""
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
    no scoreable national cell; `cells` to the cell counts. Both are empty
    under `officials_only`."""

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
        """Whether this is a fallback (surfaces must say so)."""
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
        """The JSON-safe form; provenance and wording travel with the numbers."""
        d = {"provenance": self.provenance, "label": self.label,
             "short_label": self.short_label, "note": self.note,
             "fitted": self.is_fitted, "fallback": self.is_fallback,
             "fallback_note": self.fallback_note,
             "n_states": self.n_states, "cells": dict(self.cells)}
        d.update({m: self.scores.get(m) for m in MODELS})
        if self.reason:
            d["reason"] = self.reason
        return d


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


def resolve(root, scores_df=None, allow_aggregate: bool = True) -> UsNational:
    """THE resolution order for one season root: a fitted US cell, else the
    sum-of-states aggregate, else officials only.

    The only implementation; every consumer prints the label it returns.
    `scores_df` is loaded here when not given. `allow_aggregate=False` skips
    the (minutes-long, cold) aggregate and returns `officials_only`."""
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

    row, reason = aggregate_row(root)
    if row:
        scores = {m: (float(row[m]) if row.get(m) else None) for m in MODELS}
        cells = {m: int((row.get("cells") or {}).get(m, 0)) for m in MODELS}
        return UsNational(AGGREGATED, scores=scores, cells=cells,
                          n_states=n_states)
    return UsNational(OFFICIALS_ONLY, n_states=n_states, reason=reason)


def aggregate_row(root) -> tuple:
    """(row, reason): the sum-of-states aggregate, or (None, a printable
    reason). Never a silent omission."""
    from app.core import retro as _retro
    try:
        row = _retro.national_aggregate(Path(root))
    except Exception as e:
        return None, ("its construction failed while this view was built "
                      f"({type(e).__name__}: {str(e)[:120]})")
    if not row or not any(row.get(m) for m in MODELS):
        return None, ("its construction returned no scoreable national "
                      "cells for this season")
    return row, ""
