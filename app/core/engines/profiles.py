"""The seam between a DiseaseProfile and the engine layer. Purely additive.

`app/core/engines/pf.py` hardcodes four things that are disease-specific: the
template path, the defaults block, the fitted-variable block, and the vintage
source (`app.core.data.vintage_path`, which reads FluSight's archive). Its
fitting internals are frozen -- the sealed three-season result came out of them.

This module supplies the same four things AS FUNCTIONS OF A PROFILE, so a future
change to pf.py is a substitution rather than a rewrite, and so the COVID pieces
are testable now without running a filter. Nothing here imports pf.py, and
pf.py's behaviour is unchanged.

The influenza branch is asserted equal to pf.py's own constants in
tests/test_engine_profiles.py by reading the pf.py source. If pf.py changes, the
test fails and this file gets updated -- the seam cannot rot silently.

ONE PRE-EXISTING DISAGREEMENT, RECORDED RATHER THAN SILENTLY PICKED
-------------------------------------------------------------------
pf.py's VARS_1S proposes `Reff__FREE` with `uniform_var`; the AMCMC path
(`sihrs_fit.LOG_SCALE_VARS`) proposes it with `loguniform_var`. Both predate
this module. Names and bounds agree; only the proposal scale differs. The seam
follows the AMCMC set, because that is what `DiseaseProfile.log_scale_vars`
mirrors and what a profile-aware conf writer would emit. The divergence is
asserted explicitly in the tests so that resolving it is a deliberate act.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from flubnf.profiles import COVID, INFLUENZA, DiseaseProfile, get_profile  # noqa: E402

#: Byte-identical to pf.py's DEFAULTS_BLOCK. The starting point of every chain.
_DEFAULTS_1S = ("begin parameters\nReff__FREE 1.20\neps1__FREE 0.15\n"
                "phi1__FREE 22.0\nmult__FREE 0.05\nr__FREE 8.0\n")
#: The same, plus omega seeded at the literature centre (9-month protection,
#: 0.0256/wk). Starting a chain at a bound is the fastest way to manufacture the
#: pinning the gate is meant to detect.
_DEFAULTS_COVID = ("begin parameters\nReff__FREE 1.20\neps1__FREE 0.15\n"
                   "phi1__FREE 22.0\nomega__FREE 0.0256\nmult__FREE 0.05\n"
                   "r__FREE 8.0\n")


def defaults_block(profile: DiseaseProfile) -> str:
    return _DEFAULTS_COVID if profile.key == "covid" else _DEFAULTS_1S


def vars_block(profile: DiseaseProfile) -> str:
    """The `*_var` lines a PyBNF conf needs, in the profile's own order.

    Order matters only for readability; the log-scale choice does not. A
    strictly positive scale parameter spanning decades must be proposed in log
    space or the sampler wastes its budget on extreme values that stiffen the
    ODE (measured: 5-10x wall time on `impr`).
    """
    out = []
    for name, (lo, hi) in profile.fitted_priors.items():
        kw = "loguniform_var" if (name in profile.log_scale_vars and lo > 0) \
            else "uniform_var"
        out.append(f"{kw} = {name} {lo} {hi}")
    return "\n".join(out) + "\n"


def template(profile: DiseaseProfile) -> Path:
    p = Path(profile.template)
    if not p.is_file():
        raise FileNotFoundError(f"{profile.key} template missing: {p}")
    return p


def suffix(profile: DiseaseProfile, location: str) -> str:
    """The BNGL simulate suffix, and hence the .exp file name."""
    return f"{location.replace(' ', '_')}_{profile.key}"


def vintage_path(profile: DiseaseProfile, date: str) -> Path:
    """The truth vintage for one as-of date, from this profile's archive.

    Both branches fail LOUDLY on a miss, naming nearby alternatives (rule 5).
    The COVID branch additionally refuses any date before 2024-11-20, because no
    vintage exists there and using settled truth would be a silent lie about
    what the model could have known.
    """
    if profile.key == "covid":
        from flubnf.covid_vintage import vintage_path as covid_vintage_path
        return covid_vintage_path(date)
    from app.core.data import vintage_path as flu_vintage_path
    return flu_vintage_path(date)


def vintages(profile: DiseaseProfile) -> list:
    if profile.key == "covid":
        from flubnf.covid_vintage import vintages as covid_vintages
        return covid_vintages()
    from app.core.data import vintages as flu_vintages
    return flu_vintages()


def resolve(profile: DiseaseProfile, location: str, *, truth_csv,
            locations_csv, season_start: str, as_of: str):
    """One state's fixed inputs, with this profile's biology."""
    from flubnf.covid_fit import resolve_for_profile
    return resolve_for_profile(profile, location, truth_csv=truth_csv,
                               locations_csv=locations_csv,
                               season_start=season_start, as_of=as_of)


def guards(profile: DiseaseProfile) -> dict:
    """The one-epidemic-per-season operations, already bound to this profile.

    Re-exported here so a report or a season page reaches the guarded versions
    by the same import it uses for everything else profile-shaped. Calling
    `flubnf.phase.detect_phase` directly still works and is still unguarded --
    the guard is a discipline at the call site, not a lock on the function.
    """
    from functools import partial

    from flubnf import unimodal_guard as ug
    return {"detect_phase": partial(ug.guarded_detect_phase, profile),
            "place_centers": partial(ug.guarded_place_centers, profile),
            "season_peak": partial(ug.season_peak, profile),
            "shoulder_decomposition": partial(ug.shoulder_decomposition, profile),
            "all_peaks": ug.all_peaks,          # wave-aware, needs no guard
            "count_waves": ug.count_waves,
            "report": ug.guard_report(profile)}


def engine_spec(profile: DiseaseProfile) -> dict:
    """Everything the engine layer needs from a profile, in one dict.

    Intended as the argument a profile-aware `prepare()` would take, so the
    call site stays a single lookup instead of four scattered constants.
    """
    return {"profile": profile.key,
            "template": str(template(profile)),
            "defaults_block": defaults_block(profile),
            "vars_block": vars_block(profile),
            "target_name": profile.target_name,
            "baseline_model": profile.baseline_model,
            "season_boundary_month": profile.season_boundary_month,
            "bimodal_capable": profile.bimodal_capable,
            "n_fitted": profile.n_fitted,
            "vintage_earliest": profile.vintage_earliest}


__all__ = ["COVID", "INFLUENZA", "get_profile", "defaults_block", "vars_block",
           "template", "suffix", "vintage_path", "vintages", "resolve",
           "guards", "engine_spec"]
