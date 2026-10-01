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

THE ORACLE STEP ON US, three eras read from each stored week's oracle.json
(us_step_week), never from the code version: STEPPED (addendum A3, from
2026-10-01: the step covers the national cell), FILTER (a week stored
before it: US outside the member, its pf the Liu-West filter alone), and
MIXED for a season holding weeks of both (us_step_season).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

#: the hub's national FIPS, and every spelling of it ever written by the app
US_FIPS = "US"
US_SPELLINGS = ("US", "US (NATIONAL)", "UNITED STATES", "USA")

#: the only valid provenance states
FITTED = "fitted"
AGGREGATED = "aggregated"
OFFICIALS_ONLY = "officials_only"
PROVENANCES = (FITTED, AGGREGATED, OFFICIALS_ONLY)

#: print order; the retired blend last (older scores frames carry its rows).
#: The Liu-West filter alone (pf_filter) has US rows for weeks stored since
#: addendum A3 only, when oracle.json's quantiles.null carries US
MODELS = ("pf", "pf_filter", "analogue", "ensemble")

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
        "US (fitted) is a national forecast in its own right, fitted as its "
        "own location with the same settings as every state."),
    AGGREGATED: (
        "US (aggregated) is not a fitted national forecast: each member's "
        "state forecasts are summed (PF sample draws aligned by draw index, "
        "the Groundhog's quantile curves sampled independently), states "
        "treated as independent."),
    OFFICIALS_ONLY: (
        "No national forecast of ours exists for this season, so the US "
        "view carries the CDC comparators alone."),
}

#: the Oracle step on the US cell, by era (the module docstring)
STEPPED = "stepped"
FILTER = "filter"
MIXED = "mixed"

#: what the Oracle SIHRS member's US row is, wherever a table or tile puts
#: it under that name. From addendum A3 (2026-10-01) the Oracle step covers
#: the national cell too (app/core/oracle.py, docs/ORACLE-SIHRS.md 5c); a
#: week stored before it carries the Liu-West filter alone there, and its
#: oracle.json says so (cells.outside_member lists US). PF_US_NOTES words
#: each era; PF_US_NOTE covers both, for a store whose weeks do not say.
PF_US_NOTE = (
    "The US row under Oracle SIHRS: from addendum A3 (2026-10-01) the "
    "Oracle step is applied to the national cell as to the states, DC and "
    "Puerto Rico. A season or week stored before that carries the Liu-West "
    "filter alone there, without the Oracle step; its oracle.json lists US "
    "under outside_member.")
PF_US_NOTES = {
    STEPPED: (
        "The US row under Oracle SIHRS carries the Oracle step, as the "
        "states, DC and Puerto Rico do: the step covers the national cell "
        "since addendum A3 (2026-10-01)."),
    FILTER: (
        "The US row under Oracle SIHRS is the Liu-West filter without the "
        "Oracle step: it was stored before addendum A3 (2026-10-01), when "
        "the step covered the states, DC and Puerto Rico only; its "
        "oracle.json lists US under outside_member."),
    MIXED: (
        "The US row under Oracle SIHRS mixes two eras: weeks stored before "
        "addendum A3 (2026-10-01) carry the Liu-West filter alone there, "
        "weeks stored since carry the Oracle step."),
}
#: the short forms, for a tile beside the US figure; a stepped row needs none
PF_US_SHORT = "the Liu-West filter without the Oracle step"
PF_US_SHORT_MIXED = ("the Liu-West filter alone before addendum A3, the "
                     "Oracle step since")
#: what a page says in place of the Liu-West filter's own US figure, which
#: it shows only for a season whose every week has one
PF_FILTER_US_WITHHELD = (
    "The Liu-West filter's own US forecast exists only for weeks stored "
    "since addendum A3 (2026-10-01), so its US figure is shown only for a "
    "season whose every week has one.")

#: the word flagging a non-preferred answer
FALLBACK_WORD = "fallback"

#: the fallback states in one clause
FALLBACK_NOTES = {
    AGGREGATED: ("fallback: the scores for this season hold no scored US "
                 "fit, so it is aggregated from state forecasts"),
    OFFICIALS_ONLY: ("fallback: no US fit or aggregate this season, so only "
                     "the CDC comparators are shown"),
}


# ------------------------------------------------------- scoring policy

#: Named policy (2026-08-26): pooled relWIS is a 52-jurisdiction figure and
#: US (their sum) never joins it; flipping this restates every published
#: number. pooled_frame is the one gate; app/tests/test_us_national.py enforces it.
POOLED_INCLUDES_US = False

#: what every surface prints about the pooled figure's scope
POOLED_SCOPE_NOTE = (
    "Pooled relWIS covers the fitted states, DC and Puerto Rico; the US "
    "national cell, their sum, is scored apart and never joins the pooled "
    "average.")


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


# ------------------------------------------------- the Oracle step on US

#: a stored week's Oracle step provenance (app/core/oracle.PROVENANCE_NAME)
ORACLE_JSON = "oracle.json"

#: us_step_week's answers keyed by (path, mtime_ns, size): each week's
#: oracle.json (a few MB) is parsed once per process
_STEP_CACHE: dict = {}


def us_step_week(week_dir) -> str | None:
    """What one stored week, or a run's workroot, did with the US cell, from
    its oracle.json: FILTER when US stayed outside the member (named under
    cells.outside_member, or its location entry's state is "outside"),
    STEPPED when the US cell went through the step (any other state, the
    identity and "not eligible" included), None when the step was not
    applied, the file is missing or unreadable, or the week has no US cell.

    Never decided from addendum_a3_sha256: write_not_applied records that
    hash on a week where no step ran."""
    fp = Path(week_dir) / ORACLE_JSON
    try:
        st = fp.stat()
    except OSError:
        return None
    key = (str(fp), st.st_mtime_ns, st.st_size)
    if key in _STEP_CACHE:
        return _STEP_CACHE[key]
    out = None
    try:
        prov = json.loads(fp.read_text(encoding="utf-8"))
        if prov.get("applied") is True:
            outside = (prov.get("cells") or {}).get("outside_member") or ()
            us = [e or {} for loc, e in (prov.get("locations") or {}).items()
                  if is_us(loc) or is_us((e or {}).get("fips"))]
            if (any(is_us(l) for l in outside)
                    or any(e.get("state") == "outside" for e in us)):
                out = FILTER
            elif us:
                out = STEPPED
    except Exception:
        out = None
    _STEP_CACHE[key] = out
    return out


def us_step_weeks(root) -> dict:
    """{asof: STEPPED or FILTER} for each stored week of a season root
    whose oracle.json says (us_step_week); the others are left out."""
    from app.core.retro_store import season_sample_files
    out = {}
    for fp in season_sample_files(Path(root)):
        step = us_step_week(fp.parent)
        if step is not None:
            out[fp.parent.name] = step
    return out


def season_step(steps) -> str | None:
    """One era for a season from its weeks' answers (a us_step_weeks dict
    or any iterable of them): the one value they share, MIXED when they
    differ, None when no week says."""
    seen = set(steps.values() if isinstance(steps, dict) else steps)
    seen.discard(None)
    if not seen:
        return None
    return seen.pop() if len(seen) == 1 else MIXED


def us_step_season(root) -> str | None:
    """STEPPED, FILTER or MIXED over a season root's stored weeks, or None
    when no week says (no oracle.json, the step not applied, a sealed
    record, no US cell)."""
    return season_step(us_step_weeks(root))


def _weeks_text(weeks) -> str:
    """'1 week, 2025-10-04' or '12 weeks, 2025-10-04 to 2025-12-20'."""
    ws = sorted(weeks)
    if len(ws) == 1:
        return f"1 week, {ws[0]}"
    return f"{len(ws)} weeks, {ws[0]} to {ws[-1]}"


def pf_us_note(step, weeks: dict | None = None) -> str:
    """The note for one era (PF_US_NOTES), or PF_US_NOTE when the era is
    not known. A MIXED note names the weeks of each era when `weeks`
    ({FILTER: [asof, ...], STEPPED: [...]}) gives them."""
    text = PF_US_NOTES.get(step, PF_US_NOTE)
    if step == MIXED and weeks and weeks.get(FILTER) and weeks.get(STEPPED):
        text += (f" The filter alone: {_weeks_text(weeks[FILTER])}; the "
                 f"Oracle step: {_weeks_text(weeks[STEPPED])}.")
    return text


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
    no scoreable national cell; `cells` to the cell counts; `log_scores` to
    the log-scale relWIS and `covs` to the coverage fractions ({"50", "80",
    "95"}), each None where the source cannot give it (a scores.json or
    national cache from before these metrics). All are empty under
    `officials_only`.

    `pf_step` is the era of a fitted Oracle SIHRS US row (STEPPED, FILTER,
    MIXED, or None when the stored weeks do not say) and `pf_weeks` its
    weeks by era ({FILTER: [asof, ...], STEPPED: [...]}); `resolve` fills
    both."""

    provenance: str
    scores: dict = field(default_factory=dict)
    cells: dict = field(default_factory=dict)
    n_states: int | None = None
    reason: str = ""
    log_scores: dict = field(default_factory=dict)
    covs: dict = field(default_factory=dict)
    pf_step: str | None = None
    pf_weeks: dict = field(default_factory=dict)

    @property
    def is_fitted(self) -> bool:
        return self.provenance == FITTED

    @property
    def pf_note(self) -> str:
        """What the fitted Oracle SIHRS US row is, for its era; "" unless
        fitted (a sum of states is a sum of stepped state forecasts)."""
        return pf_us_note(self.pf_step, self.pf_weeks) if self.is_fitted else ""

    @property
    def pf_short(self) -> str:
        """The tile's short form; "" when there is nothing to add (a stepped
        row, an era the weeks do not say, a row that is not fitted)."""
        if not self.is_fitted:
            return ""
        return {FILTER: PF_US_SHORT, MIXED: PF_US_SHORT_MIXED}.get(
            self.pf_step, "")

    @property
    def pf_filter_withheld(self) -> str:
        """Why a page withholds the Liu-West filter's own fitted US figure
        (shown only when every stored week has one: STEPPED), or ""."""
        if not self.is_fitted or self.pf_step == STEPPED:
            return ""
        return PF_FILTER_US_WITHHELD

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

    def log_rel(self, model):
        """The member's log-scale relWIS, or None."""
        return self.log_scores.get(model)

    def cov(self, model):
        """The member's coverage fractions {"50", "80", "95"}, or None."""
        return self.covs.get(model)

    def as_dict(self) -> dict:
        """The JSON-safe form; provenance and wording travel with the numbers.
        Member keys carry relWIS; "log_rel" and "cov" map member to its
        log-scale relWIS and coverage fractions (None when unknown).
        For a fitted row, "pf_step" is the era, "pf_note" says what the
        Oracle SIHRS member's US figure is in it, "pf_short" is the tile's
        short form, "pf_note_filter" the note for one week stored before
        addendum A3 (the player's), and "pf_filter_withheld" why the
        Liu-West filter's US figure is not shown (empty when it is)."""
        d = {"provenance": self.provenance, "label": self.label,
             "short_label": self.short_label, "note": self.note,
             "fitted": self.is_fitted, "fallback": self.is_fallback,
             "fallback_note": self.fallback_note,
             "n_states": self.n_states, "cells": dict(self.cells),
             "log_rel": {m: self.log_scores.get(m) for m in MODELS},
             "cov": {m: self.covs.get(m) for m in MODELS},
             "pf_step": self.pf_step if self.is_fitted else None,
             "pf_note": self.pf_note,
             "pf_short": self.pf_short,
             "pf_note_filter": PF_US_NOTES[FILTER] if self.is_fitted else "",
             "pf_filter_withheld": self.pf_filter_withheld}
        d.update({m: self.scores.get(m) for m in MODELS})
        if self.reason:
            d["reason"] = self.reason
        return d


def from_scores(df) -> UsNational | None:
    """The fitted answer read straight out of a season's scores frame, or
    None when the frame carries no national rows. Per member, through
    scoring.pooled_metrics: relWIS is sum(wis) over sum(base_wis), the
    log-scale figure likewise, coverage the fraction of cells covered."""
    from app.core.scoring import pooled_metrics
    sub = us_frame(df)
    if sub is None:
        return None
    scores, cells, logs, covs = {}, {}, {}, {}
    for m in MODELS:
        g = sub[sub["model"] == m] if "model" in sub.columns else sub[:0]
        pm = pooled_metrics(g)
        scores[m] = pm["rel"]
        cells[m] = pm["n"]
        logs[m] = pm["log_rel"]
        covs[m] = pm["cov"]
    n_states = None
    if df is not None and "location" in getattr(df, "columns", ()):
        n_states = int(pooled_frame(df)["location"].nunique())
    return UsNational(FITTED, scores=scores, cells=cells, n_states=n_states,
                      log_scores=logs, covs=covs)


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
        # the Oracle SIHRS US row's era, from the stored weeks' oracle.json
        steps = us_step_weeks(root)
        weeks: dict = {}
        for asof, step in sorted(steps.items()):
            weeks.setdefault(step, []).append(asof)
        return replace(fitted, pf_step=season_step(steps), pf_weeks=weeks)

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
        logs = {m: (row.get("log_rel") or {}).get(m) for m in MODELS}
        covs = {m: (row.get("cov") or {}).get(m) for m in MODELS}
        return UsNational(AGGREGATED, scores=scores, cells=cells,
                          n_states=n_states, log_scores=logs, covs=covs)
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
