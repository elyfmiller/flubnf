"""The horizon convention, and the one place the two of them meet.

TWO CONVENTIONS, DELIBERATELY
-----------------------------
**Canonical, in memory, everywhere under `app/`**: forecast horizons are
the hub's own labels ``"0" "1" "2" "3"``, and the anchor week is
:data:`ORIGIN`, a key that is not a number at all. Horizon ``"0"`` is the
FIRST FORECAST week, whose ``target_end_date`` equals the submission's
``reference_date``.

**Stored, on disk, unchanged since the seal**: ``"0"`` is the ANCHOR week
and ``"1".."4"`` are the four forecasts. Every ``samples.json.gz`` ever
written carries this, including the sealed record, which is read-only and
can never be migrated.

WHY NOT JUST RENAME
-------------------
Because ``"0"`` already exists and already means something else. The two
zero-horizons are one week apart, so a rename does not drop a key, it
OVERWRITES the anchor with a forecast and shifts every submitted row one
week early. That failure is silent: the file still validates, the row
count is right, and only the dates are wrong. This repository has shipped
one off-by-one of that exact shape already (``app/core/submit.py``,
``hub_reference_date``, the 2026-08-26 run whose file name and rows
disagreed by a week).

So the stored form is frozen and the translation happens HERE, at the
storage boundary, and nowhere else. Two rules keep it that way:

1. Anything read from or written to a week file passes through
   :func:`to_canonical` or :func:`to_stored`. `app.core.retro` is the only
   caller that should need them.
2. No other module under `app/` writes a horizon literal in ``1..4``.
   `app/tests/test_horizon_convention.py` holds the line.

The `flubnf/` library keeps its own PHYSICAL horizons (1 to 4 weeks
ahead), because ``n_observed + h - 1`` indexes a trajectory array and 1 is
genuinely one week on. Producers under `app/core/engines/` translate at
their own edge. That boundary is real and is not an accident of history.
"""
from __future__ import annotations

#: The anchor week: the last observed point, carried alongside the
#: forecasts but never submitted and never scored.
ORIGIN = "origin"

#: Canonical forecast horizons, the hub's labels.
HORIZONS = ("0", "1", "2", "3")

#: On disk: the anchor, and the four forecasts.
STORED_ORIGIN = "0"
STORED_HORIZONS = ("1", "2", "3", "4")

_TO_CANONICAL = {STORED_ORIGIN: ORIGIN,
                 **{s: c for s, c in zip(STORED_HORIZONS, HORIZONS)}}
_TO_STORED = {v: k for k, v in _TO_CANONICAL.items()}


def to_canonical(by_h) -> dict:
    """One location's ``{stored horizon: value}`` in canonical keys.

    A key the stored convention does not define is passed through
    unchanged rather than guessed at: a record carrying something this
    module has not been taught about must reach a reader intact and be
    refused there, not be silently renamed here.
    """
    return {_TO_CANONICAL.get(str(h), str(h)): v for h, v in by_h.items()}


def to_stored(by_h) -> dict:
    """One location's ``{canonical horizon: value}`` in stored keys."""
    return {_TO_STORED.get(str(h), str(h)): v for h, v in by_h.items()}


def _map_locations(by_loc, fn) -> dict:
    return {loc: fn(hz) for loc, hz in by_loc.items()}


#: the sample-shaped and quantile-shaped members a week record may carry:
#: the mechanistic member, the two-strain research member, the filter's
#: own samples (app.core.oracle.FILTER_KEY: a console run's courtesy copy
#: and a `flubnf oracle backfill` research root; a replay's stored week
#: does not carry them; never displayed), and the Groundhog
MEMBERS = ("pf", "pf2s", "pf_filter", "analogue")


def record_to_canonical(rec: dict, members=MEMBERS) -> dict:
    """A whole stored week record, members converted in place of a copy of
    the mapping. Non-member keys (``asof``, ``pf_failures``) are carried
    through untouched."""
    out = dict(rec)
    for m in members:
        if isinstance(rec.get(m), dict):
            out[m] = _map_locations(rec[m], to_canonical)
    return out


def record_to_stored(rec: dict, members=MEMBERS) -> dict:
    """The inverse of :func:`record_to_canonical`."""
    out = dict(rec)
    for m in members:
        if isinstance(rec.get(m), dict):
            out[m] = _map_locations(rec[m], to_stored)
    return out


def quantiles_to_canonical(mq: dict) -> dict:
    """The sidecar's ``{member: {location: {horizon: ...}}}``, stored to
    canonical."""
    return {m: _map_locations(locs, to_canonical) for m, locs in mq.items()}


def quantiles_to_stored(mq: dict) -> dict:
    """The inverse of :func:`quantiles_to_canonical`."""
    return {m: _map_locations(locs, to_stored) for m, locs in mq.items()}


#: Run artefacts (``results.json`` under a workroot) also predate the
#: canonical convention. Unlike a week's samples they carry NO anchor, so
#: the two forms are told apart without ambiguity by the presence of "4":
#:
#:    legacy    {"1","2","3","4"}
#:    canonical {"0","1","2","3"}
#:
#: A workroot written before this change still renders correctly in the
#: console, which is the whole reason this detection exists rather than a
#: migration: those runs are the user's record of what was forecast.
def models_to_canonical(models) -> dict:
    """``{model: {location: {horizon: ...}}}`` from a run artefact, in
    canonical horizons whichever convention it was written in.

    Detection is per location map, not per file, so a partially rewritten
    artefact cannot end up half converted by a whole-file guess.
    """
    if not isinstance(models, dict):
        return models
    out = {}
    for model, by_loc in models.items():
        if not isinstance(by_loc, dict):
            out[model] = by_loc
            continue
        fixed = {}
        for loc, hz in by_loc.items():
            fixed[loc] = (to_canonical(hz)
                          if isinstance(hz, dict) and STORED_HORIZONS[-1] in hz
                          else hz)
        out[model] = fixed
    return out


def models_to_stored(models) -> dict:
    """The inverse of :func:`models_to_canonical`, for writing a run
    artefact in the convention every existing one already uses."""
    if not isinstance(models, dict):
        return models
    return {m: {loc: (to_stored(hz) if isinstance(hz, dict) else hz)
                for loc, hz in by_loc.items()}
            if isinstance(by_loc, dict) else by_loc
            for m, by_loc in models.items()}
