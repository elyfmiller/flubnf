"""Data-driven placement of the SIRS smooth-beta transition centers.

The `sirs_logistic` model's transition centers `tc_k` are FIXED at fit time
(only the amplitudes `db_k` are fitted — the identifiability win). The original
design pinned them to tier-constant weeks [8, 18, 28]. The 6-state bake-off
revealed a systematic upswing under-prediction: those constant centers saturate
*before* a state's actual surge inflection, so the smooth beta has no headroom
left to climb through the rise and the median lags (California worst, +37% of
peak; positive rising-phase bias in all 6 pilot states).

`place_centers` fixes the *values* (not the fitting) of the centers: it places
each `tc_k` at an inflection point of the observed series available at the
current forecast week, so the ramps sit on the surge. It is a pure,
deterministic function — same `(y, K, sw)` → same centers, no RNG, no fit
dependence, and it only ever reads `y` (the observations up to "now"), so it
cannot peek at the future.

Early season, before any surge is visible, it falls back to the tier-constant
centers — you cannot time an unseen surge.
"""

from __future__ import annotations

import numpy as np

DEFAULT_FALLBACK: tuple[float, ...] = (8.0, 18.0, 28.0)


def place_centers(
    y: np.ndarray,
    n_transitions: int,
    sw: float = 2.5,
    *,
    min_gap: float = 3.0,
    edge_margin: float = 2.0,
    fallback: tuple[float, ...] = DEFAULT_FALLBACK,
) -> list[float]:
    """Return `n_transitions` transition-center weeks for the observed series.

    Args:
        y:            observed H_weekly up to the current forecast week (no
                      future data).
        n_transitions: number of centers K to return (the transition count).
        sw:           the logistic ramp width; sets the smoothing resolution so
                      placement matches what the beta can represent.
        min_gap:      minimum separation between centers (weeks). Enforced as a
                      strict ordering invariant so centers never cross/collapse
                      → the `db_k` stay separately identifiable.
        edge_margin:  exclude this many weeks at each end (the freshest weeks
                      are revision-prone and an inflection there can't be timed).
        fallback:     tier-constant centers used early-season / on flat series.

    Returns exactly `n_transitions` strictly increasing weeks.
    """
    K = int(n_transitions)
    if K < 1:
        raise ValueError("n_transitions must be >= 1")
    y = np.asarray(y, dtype=float)
    y = y[np.isfinite(y)]
    n = len(y)
    fb = [float(c) for c in fallback]

    def _fb_list(k: int) -> list[float]:
        reps = (k // max(1, len(fb))) + 1
        return (fb * reps)[:k]

    # Guard: too short or flat → tier-constant fallback (early-season behavior).
    if n < 5 or float(np.std(y)) < 1e-9:
        return _clamp_sep(_fb_list(K), K, n, min_gap, edge_margin)

    # 1. Smooth at the beta's own resolution.
    win = max(1, int(round(sw)))
    if win > 1:
        kern = np.ones(win) / win
        ys = np.convolve(y, kern, mode="same")
    else:
        ys = y.copy()

    # 2. Inflection score = |2nd difference| (sign-agnostic, so a late
    #    DOWN-step `db_k<0` is placed at its inflection too). accel[i] maps to
    #    week index i+1.
    accel = np.abs(np.diff(ys, n=2))
    weeks = np.arange(1, n - 1, dtype=float)

    # 3. Edge mask.
    lo, hi = edge_margin, (n - 1) - edge_margin
    valid = (weeks >= lo) & (weeks <= hi)
    cand_weeks = weeks[valid]
    cand_score = accel[valid]

    # 4. Greedy non-maximum suppression with a ±min_gap exclusion window.
    chosen: list[float] = []
    if len(cand_weeks):
        for idx in np.argsort(-cand_score):
            w = float(cand_weeks[idx])
            if all(abs(w - c) >= min_gap for c in chosen):
                chosen.append(w)
            if len(chosen) >= K:
                break

    # 5. Backfill from the tier-constant fallback if too few inflections
    #    (a monotone-so-far series gives fewer than K usable inflections).
    if len(chosen) < K:
        for c in _fb_list(K):
            if all(abs(c - cc) >= min_gap for cc in chosen):
                chosen.append(c)
            if len(chosen) >= K:
                break

    return _clamp_sep(chosen[:K], K, n, min_gap, edge_margin)


def _clamp_sep(
    centers: list[float], K: int, n: int, min_gap: float, edge_margin: float,
) -> list[float]:
    """Sort, clamp into the valid window, enforce min_gap ordering, pad to K."""
    cs = sorted(float(c) for c in centers)
    lo = edge_margin
    # If we have no series (n==0) just space the fallback out.
    hi = max(lo + min_gap * (K - 1), (n - 1) - edge_margin) if n > 0 else lo + min_gap * K
    out: list[float] = []
    for c in cs:
        c = min(max(c, lo), hi)
        if out and c < out[-1] + min_gap:
            c = out[-1] + min_gap  # strict no-crossing; may exceed hi (ok for forecast weeks)
        out.append(c)
    # Pad if backfill+dedup left us short.
    while len(out) < K:
        nxt = (out[-1] + min_gap) if out else lo
        out.append(nxt)
    return out[:K]
