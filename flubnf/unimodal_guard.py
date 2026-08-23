"""Guards for the code that assumes exactly one epidemic per season.

THE FAILURE MODE THIS PREVENTS
------------------------------
Phase classification, transition-center placement, peak reporting and the
shoulder decomposition all assume a season is one rise, one peak, one fall.
72.5% of COVID state-seasons carry two or more distinct waves. Run on such a
season these functions do not raise: they return a well-formed answer about a
peak that is one of two, or a "post-peak shoulder" that is really the trough
between waves. Well-formed nonsense is the dangerous kind of breakage, because
nothing downstream can tell it from a result.

THE RULE
--------
Under a profile with `bimodal_capable=True` these operations REFUSE by default.
A caller who genuinely wants the unimodal answer must pass
`acknowledge_bimodal=True`, and then gets a `Guarded` whose
`unimodal_assumption_violated` flag is set and whose `mark` string travels with
the value into any report. There is no way to obtain an unmarked answer under a
bimodal-capable profile, which is the whole point.

The guard is also DATA-AWARE. Even under influenza, a series that actually shows
two waves is marked, because the assumption is about the series and not only
about the disease. That costs nothing when the assumption holds -- `waves` is 1
for an ordinary flu season, the flag stays False, and the value is the value the
unguarded function would have returned.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

import numpy as np

from .profiles import DEFAULT_PROFILE, DiseaseProfile


class BimodalProfileError(RuntimeError):
    """A one-epidemic-per-season operation was attempted under a profile whose
    disease has two. Raised instead of returning, because the return value would
    be indistinguishable from a correct one."""


@dataclass(frozen=True)
class Guarded:
    """A value plus the honest statement of what it assumed.

    `value` is None only when the operation refused; refusal normally raises, so
    a None here means a caller asked for `strict=False`.
    """
    value: Any
    operation: str
    profile_key: str
    waves_detected: int
    unimodal_assumption_violated: bool
    mark: Optional[str]

    def __bool__(self) -> bool:
        return self.value is not None


#: A wave must reach this fraction of the series maximum. Same threshold the
#: repertoire sweep used, so a count here means what a count means there.
MIN_HEIGHT_FRAC = 0.40
#: Two peaks are distinct only if the trough between them falls at least this
#: far below the smaller of the two -- ordinary prominence. Without it a plateau
#: with two bumps counts as two epidemics.
MAX_TROUGH_FRAC = 0.75
MIN_SEPARATION = 6


def _peak_indices(v: np.ndarray, min_separation: int, min_height_frac: float,
                  max_trough_frac: float) -> list:
    top = float(np.nanmax(v)) if v.size else 0.0
    if v.size < 5 or top <= 0:
        return [int(np.argmax(v))] if v.size and top > 0 else []
    peaks = [i for i in range(1, v.size - 1)
             if v[i] >= v[i - 1] and v[i] > v[i + 1]
             and v[i] >= min_height_frac * top]
    if v[0] > v[1] and v[0] >= min_height_frac * top:
        peaks.insert(0, 0)
    if v[-1] > v[-2] and v[-1] >= min_height_frac * top:
        peaks.append(v.size - 1)
    if not peaks:
        return [int(np.argmax(v))]
    kept = [peaks[0]]
    for p in peaks[1:]:
        q = kept[-1]
        trough = float(v[q:p + 1].min())
        distinct = (p - q >= min_separation
                    and trough <= max_trough_frac * min(v[p], v[q]))
        if distinct:
            kept.append(p)
        elif v[p] > v[q]:
            kept[-1] = p
    return kept


def count_waves(y: Sequence, *, min_separation: int = MIN_SEPARATION,
                min_height_frac: float = MIN_HEIGHT_FRAC,
                max_trough_frac: float = MAX_TROUGH_FRAC) -> int:
    """Distinct waves in a series.

    A wave is a local maximum at least `min_separation` weeks from the last one
    kept, reaching `min_height_frac` of the series maximum, and separated from
    it by a trough at or below `max_trough_frac` of the smaller peak.
    """
    v = np.asarray(y, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return 0
    if float(v.max()) <= 0:
        return 0
    if v.size < 5:
        return 1
    return len(_peak_indices(v, min_separation, min_height_frac,
                             max_trough_frac))


def _guard(profile: DiseaseProfile, operation: str, y: Optional[Sequence],
           acknowledge_bimodal: bool, strict: bool):
    waves = count_waves(y) if y is not None else 0
    violated = bool(profile.bimodal_capable or waves >= 2)
    if not violated:
        return waves, False, None
    detail = (f"{operation}: assumes one epidemic per season. "
              f"profile={profile.key} bimodal_capable={profile.bimodal_capable} "
              f"waves_detected={waves}. ")
    if profile.bimodal_capable and not acknowledge_bimodal:
        if strict:
            raise BimodalProfileError(
                detail + "Refusing: under this profile the answer would be "
                "well-formed and wrong. Pass acknowledge_bimodal=True to get a "
                "MARKED unimodal answer, or use a wave-aware summary.")
        return waves, True, detail + "REFUSED"
    return waves, True, (detail + "MARKED: the value below is the unimodal "
                         "answer and is not the whole season.")


# ---------------------------------------------------------------------------
# Guarded wrappers around the shipped one-epidemic functions
# ---------------------------------------------------------------------------

def guarded_detect_phase(profile: DiseaseProfile, observed, *,
                         acknowledge_bimodal: bool = False,
                         strict: bool = True, **kw) -> Guarded:
    """`flubnf.phase.detect_phase`, guarded.

    detect_phase reads slope and curvature over the last four weeks and returns
    RISING / NEAR_PEAK / FALLING / TROUGH. Between COVID's two waves the correct
    label is ambiguous by construction: the same shape is the fall of wave one
    and the rise of wave two, and the classifier picks one.
    """
    from .phase import detect_phase
    waves, violated, mark = _guard(profile, "detect_phase", observed,
                                   acknowledge_bimodal, strict)
    value = None if (violated and profile.bimodal_capable
                     and not acknowledge_bimodal) else detect_phase(observed, **kw)
    return Guarded(value, "detect_phase", profile.key, waves, violated, mark)


def guarded_place_centers(profile: DiseaseProfile, y, n_transitions: int, *,
                          acknowledge_bimodal: bool = False,
                          strict: bool = True, **kw) -> Guarded:
    """`flubnf.centers.place_centers`, guarded.

    place_centers puts the smooth-beta ramps on "the surge", singular. With two
    surges the greedy non-maximum suppression splits the ramps across both and
    neither is well resolved.
    """
    from .centers import place_centers
    waves, violated, mark = _guard(profile, "place_centers", y,
                                   acknowledge_bimodal, strict)
    value = None if (violated and profile.bimodal_capable
                     and not acknowledge_bimodal) else place_centers(
                         y, n_transitions, **kw)
    return Guarded(value, "place_centers", profile.key, waves, violated, mark)


# ---------------------------------------------------------------------------
# Peak reporting and shoulder decomposition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Peak:
    index: int
    date: Optional[str]
    value: float


def season_peak(profile: DiseaseProfile, values, dates=None, *,
                acknowledge_bimodal: bool = False, strict: bool = True) -> Guarded:
    """THE peak of a season -- an object that may not exist.

    Under a unimodal profile this is the argmax and nothing more. Under a
    bimodal-capable one "the peak week" is a category error: in 2025 COVID's
    September wave (11,069 US admissions) was LARGER than the January wave that
    followed it, so the argmax names one of two epidemics and the report reads
    as if the other did not happen. Use `all_peaks` instead.
    """
    v = np.asarray(values, dtype=float)
    waves, violated, mark = _guard(profile, "season_peak", v,
                                   acknowledge_bimodal, strict)
    value = None
    if not (violated and profile.bimodal_capable and not acknowledge_bimodal):
        finite = np.where(np.isfinite(v))[0]
        if finite.size:
            i = int(finite[int(np.argmax(v[finite]))])
            value = Peak(i, (str(dates[i])[:10] if dates is not None else None),
                         float(v[i]))
    return Guarded(value, "season_peak", profile.key, waves, violated, mark)


def all_peaks(values, dates=None, *, min_separation: int = MIN_SEPARATION,
              min_height_frac: float = MIN_HEIGHT_FRAC,
              max_trough_frac: float = MAX_TROUGH_FRAC) -> list:
    """Every distinct wave's peak, oldest first.

    The wave-aware replacement for `season_peak`: it makes no unimodal
    assumption, so it needs no guard. `len(all_peaks(y)) == count_waves(y)` by
    construction -- the same selector produces both -- so a report can state the
    wave count and list the waves without the two disagreeing.
    """
    v = np.asarray(values, dtype=float)
    if v.size == 0 or not np.isfinite(v).any() or float(np.nanmax(v)) <= 0:
        return []
    if v.size < 5:
        i = int(np.nanargmax(v))
        return [Peak(i, (str(dates[i])[:10] if dates is not None else None),
                     float(v[i]))]
    idx = _peak_indices(np.nan_to_num(v, nan=-np.inf), min_separation,
                        min_height_frac, max_trough_frac)
    return [Peak(int(i), (str(dates[i])[:10] if dates is not None else None),
                 float(v[i])) for i in sorted(idx)]


@dataclass(frozen=True)
class ShoulderSplit:
    rise: tuple            # (start_index, end_index) inclusive
    peak_index: int
    shoulder: tuple        # (start_index, end_index) inclusive


def shoulder_decomposition(profile: DiseaseProfile, values, *,
                           acknowledge_bimodal: bool = False,
                           strict: bool = True) -> Guarded:
    """Split a season into rise / peak / post-peak shoulder.

    This is the decomposition behind the "shoulder is the whole loss" finding
    for influenza. It is defined only when there is one peak. Under COVID the
    weeks it would label "shoulder" contain the trough between two epidemics and
    then the rise of the second, so the resulting per-phase relWIS is an average
    over three different regimes wearing one label.
    """
    v = np.asarray(values, dtype=float)
    waves, violated, mark = _guard(profile, "shoulder_decomposition", v,
                                   acknowledge_bimodal, strict)
    value = None
    if not (violated and profile.bimodal_capable and not acknowledge_bimodal):
        finite = np.where(np.isfinite(v))[0]
        if finite.size:
            i = int(finite[int(np.argmax(v[finite]))])
            value = ShoulderSplit(rise=(0, i), peak_index=i,
                                  shoulder=(i, int(v.size - 1)))
    return Guarded(value, "shoulder_decomposition", profile.key, waves,
                   violated, mark)


def guard_report(profile: DiseaseProfile = DEFAULT_PROFILE) -> dict:
    """What this profile refuses, for a methods section or a startup log."""
    ops = ("detect_phase", "place_centers", "season_peak",
           "shoulder_decomposition")
    return {"profile": profile.key,
            "bimodal_capable": profile.bimodal_capable,
            "p_multiwave": profile.harmonic.p_multiwave,
            "guarded_operations": ops,
            "behaviour": ("refuse (BimodalProfileError) unless "
                          "acknowledge_bimodal=True, then MARKED"
                          if profile.bimodal_capable
                          else "pass through, marked only if the series itself "
                               "shows two waves")}
