"""PRODUCTION: canonical vs stored horizon translation at the storage boundary
(retro, engines, playback, server).

The horizon convention, and the one place the two of them meet.

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
Stored ``"0"`` is the anchor, one week before canonical ``"0"``: a rename
overwrites the anchor with a forecast and silently shifts every submitted
row a week early (the file still validates). So the stored form is frozen
and the translation happens HERE, at the storage boundary, and nowhere else:

1. Anything read from or written to a week file passes through
   :func:`to_canonical` or :func:`to_stored`. `app.core.retro` is the only
   caller that should need them.
2. No other module under `app/` writes a horizon literal in ``1..4``.
   `app/tests/test_horizon_convention.py` holds the line.

The `flubnf/` library keeps PHYSICAL horizons (1 to 4 weeks ahead) because
``n_observed + h - 1`` indexes a trajectory array; producers under
`app/core/engines/` translate at their own edge.
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

    An unknown key passes through unchanged, to be refused by the reader
    rather than silently renamed here.
    """
    return {_TO_CANONICAL.get(str(h), str(h)): v for h, v in by_h.items()}


def to_stored(by_h) -> dict:
    """One location's ``{canonical horizon: value}`` in stored keys."""
    return {_TO_STORED.get(str(h), str(h)): v for h, v in by_h.items()}


def _map_locations(by_loc, fn) -> dict:
    return {loc: fn(hz) for loc, hz in by_loc.items()}


#: members a week record may carry: the mechanistic member, the two-strain
#: research member, the plain filter's samples (oracle.FILTER_KEY; console
#: runs and backfill roots only, never displayed), and the Groundhog
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


#: A run artefact (workroot results.json) records the convention its
#: "models" were written in under this key; the writers use STORED.
CONVENTION_KEY = "horizon_convention"
STORED = "stored"
CANONICAL = "canonical"


#: Run artefacts carry no anchor. When the file records its convention
#: (CONVENTION_KEY) that is read; files written before the record are told
#: apart by the presence of "4" (legacy {"1".."4"} vs canonical {"0".."3"}),
#: a guess that misreads a location missing only its last horizon, so it
#: serves old files only. Detected rather than migrated: old workroots are
#: the user's record.
def models_to_canonical(models, convention=None) -> dict:
    """``{model: {location: {horizon: ...}}}`` from a run artefact, in
    canonical horizons. `convention` is the file's CONVENTION_KEY value:
    STORED converts every location, CANONICAL leaves them; None (an older
    file, or an unknown value) detects per location map, not per file, so
    a partly rewritten artefact is never half converted.
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
            if not isinstance(hz, dict):
                fixed[loc] = hz
            elif convention == STORED:
                fixed[loc] = to_canonical(hz)
            elif convention == CANONICAL:
                fixed[loc] = hz
            else:
                fixed[loc] = (to_canonical(hz)
                              if STORED_HORIZONS[-1] in hz else hz)
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
