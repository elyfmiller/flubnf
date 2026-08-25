"""Sourced, citable parameter provenance for the population-parameterized SIHRS.

Every fixed/pinned value carries (a) its numeric value, (b) whether it came from
DATA on disk, from the LITERATURE, or from neither, and (c) an auditable source:
a DOI for literature, a file path plus derivation for data.
`provenance_table()` renders the whole set for a methods section.

NOT EVERYTHING IS SOURCED, and the table says so rather than implying otherwise.
`rho`, `gammaH` and `omega` are working ASSUMPTIONS set as plain constants in
`sihrs_fit.py` (RHO_IHR, GAMMAH_PER_WEEK, OMEGA_PER_WEEK). No DOI and no data
derivation stands behind those three numbers. They appear in the table with
kind="assumption" and an empty source so that a reviewer following a pointer
here finds a stated gap instead of a missing row.

Design rule: population and any parameter that is only product-identified are
FIXED, never fitted. Fitting a product-identified pair yields a ridge-shaped
posterior and per-parameter values that cannot be interpreted (a caveat the
project's own docs already carry for `rho*mult` and `R0*gamma`).

--------------------------------------------------------------------------------
IMPORTANT DEFINITION MISMATCH (do not paper over this)
--------------------------------------------------------------------------------
The FluSight target is NHSN "total influenza admissions" — a near-census of
hospital-reported admissions. Published influenza hospitalization *rates* (e.g.
FluSurv-NET) are laboratory-confirmed influenza-associated hospitalizations in
selected surveillance catchments covering ~9% of the US population. These are
NOT the same quantity, and on 2024/25 the NHSN-derived median (153.0 per 100k)
EXCEEDS the FluSurv-NET rate (127.1 per 100k), giving a nonsensical
"ascertainment" of 1.20.

Consequence: do NOT calibrate `mult` as "reported / true" against a published
surveillance rate. The FluSight target IS the quantity to predict, so `rho*mult`
is calibrated against that state's own observed cumulative reported admissions,
with the literature supplying only the cumulative INFECTION denominator.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Param:
    """One fixed/pinned parameter and where its value comes from."""
    name: str
    value: float
    unit: str
    #: "assumption" means exactly what it says: a value chosen without a
    #: citation or a derivation. Such rows carry an empty `source`.
    kind: Literal["data", "literature", "derived", "assumption"]
    source: str                 # DOI / file path, or "" for an assumption
    note: str
    low: Optional[float] = None
    high: Optional[float] = None


# ---------------------------------------------------------------------------
# LITERATURE. All retrieved via PubMed / Consensus 2026-07-29; DOIs verified in
# the tool responses, not recalled from memory.
# ---------------------------------------------------------------------------

# Generation time -> gamma. Chan et al. 2024 is the best available anchor: US,
# post-COVID, 7-site household study, and it is a CDC analysis feeding CDC's own
# real-time Rt work. Mean intrinsic generation time 3.2 d (95% CrI 2.9-3.6).
GENERATION_TIME_DAYS = 3.2
GENERATION_TIME_CRI = (2.9, 3.6)
GT_SOURCE = "10.1101/2024.08.17.24312064"          # Chan et al. 2024, medRxiv
GT_CORROBORATION = (
    "10.1093/aje/kwu209",                          # Vink 2014: SI H3N2 2.2 d
    "10.1111/j.1750-2659.2011.00234.x",            # Boelle 2011: SI ~3.0 d
)

# R0 prior. Boelle et al. 2011 review: community R0 1.2-2.3, median 1.5 (for
# A/H1N1 2009 pandemic; seasonal epidemics sit at the lower end, so the prior is
# deliberately widened downward rather than centred on 1.5).
R0_RANGE = (1.1, 2.3)
R0_SOURCE = "10.1111/j.1750-2659.2011.00234.x"

# Cumulative seasonal INFECTION fraction (attack rate). Used only as the
# denominator when pinning the rho*mult product. Kept as a range because this is
# the weakest link in the chain.
#
# Serology anchor: Vinh et al. 2021 decomposed age-seroprevalence curves from
# 24,402 general-population sera to annual attack rates of 25.6% (95% CI
# 24.1-27.1) for subtype H3 and 16.0% (14.7-17.3) for H1.
# CAVEAT, load-bearing: that cohort is VIETNAM (2009-2015), not the US. Vietnam
# has markedly weaker influenza seasonality, so these are a methodological
# proxy, not a US point estimate. The range below is therefore kept wide and
# `rho*mult` scales inversely with it, so any headline result must be reported
# with an attack-rate sensitivity arm.
ATTACK_RATE_RANGE = (0.10, 0.26)
ATTACK_RATE_SEROLOGY = {"H3_vietnam": 0.256, "H1_vietnam": 0.160}
ATTACK_RATE_SOURCE = "10.1038/s41467-021-26948-8"      # Vinh et al. 2021
ATTACK_RATE_NOTE = (
    "Cumulative INFECTIONS per season, not symptomatic illnesses. Widest "
    "uncertainty in the chain; rho*mult scales inversely with it."
)

# ---------------------------------------------------------------------------
# s0 — initial susceptible fraction. NO source gives a per-state US value.
# ---------------------------------------------------------------------------
# What the serology literature does supply:
#  * The right ESTIMATOR. Xiong et al. 2025 build population-immunity estimators
#    from individual HAI titers, one of which is the "relative reduction in the
#    reproductive number". That is exactly `s0` in this model, because
#    R_eff = R0 * s0 -- so titer data maps onto s0 without inventing a new
#    quantity. Validated on 36,150 sera across 19 epidemics.
#  * The protection correlate. HAI >= 1:40 is the conventional ~50%-protection
#    threshold (Memoli et al. 2016), but it misses cellular/mucosal immunity, so
#    it UNDERSTATES protection (i.e. overstates s0).
#  * A US-specific level shift. Wang et al. 2023 estimate US population
#    susceptibility rose 45.1% during COVID-19 restrictions -- so any
#    pre-pandemic baseline is stale for 2021+ seasons.
#  * A threshold-sensitivity warning. Wu et al. 2014: infection-seropositivity
#    probability ranges 34%-72% by age at MN 1:40, so attack rates (and hence
#    immunity) inferred from seroconversion are threshold-sensitive; assuming
#    100% seroconversion biases them.
#  * The most current US-representative panel: the CDC multi-season longitudinal
#    study, 723 participants across all 10 HHS regions and 9 age groups, 1,794
#    sera 2021-2024, 12-plex MIADA (Li et al. 2025).
#
# Conclusion: treat s0 as a BOUNDED SENSITIVITY AXIS, not a known constant.
# Fitting it is not an option -- R0*s0 is product-identified.
# CIRCULATING-STRAIN susceptibility, not all-strain seroprevalence. Antigenic
# drift means antibodies to earlier strains do not protect against this season's
# drifted strain, so the fraction effectively susceptible TO THE CIRCULATING
# STRAIN is much higher than "has influenza antibodies". Empirically forced:
# fitting Alabama gave Reff=2.11, which with a literature-plausible R0<=2.3
# (Boelle 2011) requires s0 >= 0.92 -- all-strain seroprevalence (0.35-0.70)
# implied R0 of 3-6 and is the wrong quantity. Xiong et al. 2025's estimators are
# strain-specific for exactly this reason.
S0_RANGE = (0.70, 0.95)
S0_DEFAULT = 0.85
S0_SOURCES = {
    "estimator_titer_to_s0": "10.1101/2025.07.10.25331265",   # Xiong et al. 2025
    "hai_40_protection_correlate": "10.1128/mbio.00417-16",   # Memoli et al. 2016
    "us_susceptibility_shift_covid": "10.1002/jmv.29186",     # Wang et al. 2023
    "seroconversion_threshold_bias": "10.1371/journal.ppat.1004054",  # Wu et al. 2014
    "cdc_us_longitudinal_panel": "10.1038/s41467-025-66431-2",  # Li et al. 2025
    "serocatalytic_tooling": "10.1371/journal.pcbi.1012777",   # Hoze et al. 2025
}
S0_NOTE = (
    "No published source gives a per-state US s0. Xiong et al. 2025 supply the "
    "correct estimator (relative reduction in R, i.e. exactly s0 since "
    "R_eff = R0*s0); Li et al. 2025 supply the most current US-representative "
    "titer panel (723 participants, 10 HHS regions, 2021-2024) from which such "
    "an estimate could be built. Until that is done, run s0 as a sensitivity "
    "axis over S0_RANGE and report the arm."
)

# Under-detection of influenza hospitalizations, by age (Reed et al. 2015):
# 2.1x (<18), 3.1x (18-64), 5.2x (65+) => detection fraction 0.19-0.48.
# RECORDED FOR CONTEXT ONLY -- see the definition-mismatch note in the module
# docstring. Do not use it to calibrate `mult` against the NHSN target.
HOSP_UNDERDETECTION_BY_AGE = {"<18": 2.1, "18-64": 3.1, "65+": 5.2}
UNDERDETECTION_SOURCE = "10.1371/journal.pone.0118369"   # Reed et al. 2015

# Published influenza hospitalization rates per 100k per season, for sanity
# bounds only (NOT for ascertainment calibration).
HOSP_RATE_PER_100K = {
    "paget_2023_global_pooled": 40.5,      # 95% CI 24.3-67.4
    "mmwr_2025_us_2024_25": 127.1,         # high-severity season
}
HOSP_RATE_SOURCES = (
    "Paget et al. 2023, J Glob Health (pooled global, 40.5/100k)",
    "O'Halloran et al. 2025, MMWR (US 2024-25, 127.1/100k)",
)


def gamma_per_week(generation_time_days: float = GENERATION_TIME_DAYS) -> float:
    """Removal rate per week from the mean generation time in days."""
    return 7.0 / float(generation_time_days)


# ---------------------------------------------------------------------------
# DATA. Everything below reads only files on disk, and only weeks at or before
# the as-of date, so there is no leakage.
# ---------------------------------------------------------------------------

def load_populations(locations_csv: str | Path) -> dict:
    """Authoritative populations: the FluSight hub's auxiliary-data/locations.csv.

    Use the hub copy, not a vendored one -- they drift (Alabama was 5,157,699 in
    the hub vs 5,108,468 in an older vendored copy).
    """
    df = pd.read_csv(locations_csv, dtype={"location": str})
    df["location"] = df["location"].str.zfill(2)
    return {r.location_name: int(r.population)
            for r in df.itertuples() if r.abbreviation != "US"}


def cumulative_reported_per_capita(truth_csv: str | Path, location_fips: str,
                                   population: int, season_start: str,
                                   as_of: str) -> float:
    """Cumulative reported admissions per capita for one state, up to `as_of`."""
    t = pd.read_csv(truth_csv, dtype={"location": str})
    t["date"] = pd.to_datetime(t["date"])
    t["location"] = t["location"].str.zfill(2)
    m = ((t.location == str(location_fips).zfill(2))
         & (t.date >= pd.Timestamp(season_start))
         & (t.date <= pd.Timestamp(as_of)))
    return float(t.loc[m, "value"].sum()) / float(population)


def pin_rho_mult(cum_reported_per_capita: float,
                 attack_rate: float = float(np.mean(ATTACK_RATE_RANGE))) -> float:
    """Pin the product `rho*mult` -- the only combination that is identified.

        rho*mult = (cumulative reported admissions per capita) / (attack rate)

    Fixing the product removes the rho-vs-mult ridge entirely and costs nothing
    in forecast skill, because H_weekly depends on the two only through it:
        H_weekly = (rho*mult) * gamma * I
    """
    if attack_rate <= 0:
        raise ValueError("attack_rate must be > 0")
    return float(cum_reported_per_capita) / float(attack_rate)


def initial_infected_fraction(first_week_reported: float, population: int,
                              rho_mult: float,
                              gamma: float = gamma_per_week()) -> float:
    """Per-state `i0` from that state's own first observed week.

    From the INSTANTANEOUS relation H_weekly = rho*mult*gamma*I, with I in
    absolute people:
        i0 = I(0)/N = first_week_reported / (rho*mult * gamma * N)
    Per-state by construction, which is what forecasting 52 differently-sized
    jurisdictions requires.

    CONVENTION NOTE. The shipped particle filter's observation is the weekly
    INTEGRAL of that flux rather than the flux at an instant, so the exact
    inversion would carry a further factor lam/(1 - exp(-lam)) at the first
    week's local growth lam. This value is a SEED only: the filter corrects
    the state at every weekly update, `mult` is fitted afterwards under its
    own prior, and at the start of a season local growth is near zero, where
    the factor tends to 1. Changing the inversion would move every fit, so
    the seed is left on the instantaneous relation deliberately.
    """
    denom = float(rho_mult) * float(gamma) * float(population)
    if denom <= 0:
        raise ValueError("rho_mult, gamma and population must be > 0")
    return float(first_week_reported) / denom


def provenance_table() -> pd.DataFrame:
    """Every fixed value with its source — paste into a methods section."""
    g = gamma_per_week()
    rows = [
        Param("N", np.nan, "people", "data",
              "FluSight hub auxiliary-data/locations.csv",
              "Per-state population; authoritative copy is the hub's, which "
              "drifts from vendored copies."),
        Param("gamma", g, "1/week", "literature", GT_SOURCE,
              f"7 / {GENERATION_TIME_DAYS} d mean intrinsic generation time "
              f"(95% CrI {GENERATION_TIME_CRI[0]}-{GENERATION_TIME_CRI[1]} d), "
              "Chan et al. 2024 US household study. Corroborated by "
              "Vink 2014 (SI 2.2 d, H3N2) and Boelle 2011 (SI ~3.0 d).",
              7.0 / GENERATION_TIME_CRI[1], 7.0 / GENERATION_TIME_CRI[0]),
        Param("R0", np.nan, "dimensionless", "literature", R0_SOURCE,
              "Fitted, with prior from Boelle et al. 2011 community estimates "
              "(1.2-2.3, median 1.5); widened downward for seasonal epidemics.",
              R0_RANGE[0], R0_RANGE[1]),
        Param("rho", 0.02, "dimensionless", "assumption", "",
              "UNSOURCED WORKING ASSUMPTION. Set as RHO_IHR in "
              "flubnf/sihrs_fit.py; no DOI and no data derivation stands "
              "behind the 0.02. Reed et al. 2015 under-detection is NOT a "
              "source for it (see the definition-mismatch note in this "
              "module's docstring). Its practical effect is bounded: "
              "admissions identify only the product rho*mult and mult is "
              "fitted, so this value sets what the fitted mult means rather "
              "than what the fit predicts."),
        Param("gammaH", 1.17, "1/week", "assumption", "",
              "UNSOURCED WORKING ASSUMPTION. Set as GAMMAH_PER_WEEK in "
              "flubnf/sihrs_fit.py, from a ~6 d length of stay taken as "
              "given. It governs the H census only and enters no term of "
              "the admissions fit target, so it cannot bias the fit."),
        Param("omega", 0.019, "1/week", "assumption", "",
              "UNSOURCED WORKING ASSUMPTION. Set as OMEGA_PER_WEEK in "
              "flubnf/sihrs_fit.py, from a ~1 y immune duration taken as "
              "given. Weakly identified from under three seasons, so a fit "
              "cannot correct it either."),
        Param("rho*mult", np.nan, "dimensionless", "derived",
              "data (cumulative reported admissions/capita) / literature (attack rate)",
              "PINNED AS A PRODUCT -- only the product is identified. See "
              "pin_rho_mult(). Attack-rate denominator "
              f"{ATTACK_RATE_RANGE[0]:.0%}-{ATTACK_RATE_RANGE[1]:.0%}."),
        Param("i0", np.nan, "fraction", "data",
              "FluSight hub target-hospital-admissions.csv (first observed week)",
              "Per-state; inverted from that state's own first observed week. "
              "See initial_infected_fraction()."),
        Param("s0", S0_DEFAULT, "fraction", "literature",
              S0_SOURCES["estimator_titer_to_s0"],
              "SENSITIVITY AXIS, not a known constant. Xiong et al. 2025 give "
              "the estimator (relative reduction in R == s0, since "
              "R_eff = R0*s0); Memoli 2016 the HAI>=1:40 ~50%-protection "
              "correlate; Wang 2023 the +45.1% US susceptibility shift during "
              "COVID; Li et al. 2025 the current US panel. No per-state US "
              "value exists -- do NOT fit it (R0*s0 is product-identified).",
              S0_RANGE[0], S0_RANGE[1]),
    ]
    return pd.DataFrame([r.__dict__ for r in rows])
