"""DiseaseProfile: everything that varies between diseases, as data.

WHY THIS MODULE EXISTS
----------------------
The 2026-08-22 COVID feasibility memo classified every component of the
forecasting stack into three buckets: ports unchanged, needs reparameterization,
structurally invalid. The third bucket is small and every item in it is a value
that the flu path currently hardcodes: the 1 August season boundary, the target
string, the truth column, the baseline pointer, the fixed-parameter set, and the
assumption that a season contains exactly one epidemic.

A `DiseaseProfile` carries those values. It is deliberately DATA, not a forked
code path: the memo's own condition for the eventual EpiBNF rename is that the
second disease be expressible as a profile rather than a fork.

THE INFLUENZA PROFILE IS TODAY'S BEHAVIOR, EXACTLY
--------------------------------------------------
`INFLUENZA` reproduces the shipped constants byte for byte. In particular
`INFLUENZA.season_of` is asserted equal to `flubnf.analogue.season_of` over
every day of a twelve-year span in tests/test_profiles.py, and
`INFLUENZA.season_start(y)` is asserted equal to the string
`app/core/runs.py` builds and to `app/core/retro.season_bounds(...)[0]`.
If any of those tests fail, the profile has drifted from production and the
profile is wrong, not the production path.

WHAT THE COVID PROFILE CHANGES, AND WHY EACH CHANGE IS FORCED
--------------------------------------------------------------
season_boundary_month 8 -> 6
    COVID's summer wave peaked at epiweeks 34, 31, 36, 36 in four of six
    seasons. An August boundary cuts one of the two annual epidemics in half,
    which breaks the analogue's "strictly prior season" donor rule, solstice
    seeding, per-season LOSO freezing and every season report. June sits in
    COVID's actual trough.

target_name -> "wk inc covid hosp"; truth column -> totalconfc19newadm
    Same hubverse task structure, same NHSN Socrata dataset mpgq-jmmr, sibling
    column. One alias, one string.

baseline_model -> "CovidHub-baseline"
    The same `epipredict::cdc_baseline_forecaster()` estimator FluSight uses,
    so a relWIS on COVID is directly comparable to a relWIS on flu. The FIELD is
    not comparable: the pooled COVID ensemble beats its baseline by 22% where the
    flu ensemble beats its by 34%.

omega FREED
    The memo's central finding. `omega` -- not `eps2` -- is the parameter that
    decides whether a one-harmonic SIHRS can produce two epidemics a year. With
    influenza's slow waning the bimodal region of parameter space is 1.2%; with
    COVID waning it is 6.7%, and 20.4% at realistic forcing amplitudes. Fixing
    omega therefore freezes the model into or out of bimodality by fiat.

bimodal_capable True
    72.5% of COVID state-seasons carry two or more distinct waves against flu's
    36.8%. Every one-epidemic-per-season code path must refuse or mark its
    output under this flag -- see flubnf/unimodal_guard.py.

NOT ESTABLISHED, CARRIED AS A CAVEAT
------------------------------------
Every COVID value here is a first pass. `s0` is a sensitivity axis and not a
measurement for either disease. The COVID attack-rate range is wide and
`rho*mult` scales inversely with it. Nothing in this module has been validated
against a COVID retrospective, because none exists yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from flubnf.analogue import SEASON_2021_22_CALENDAR_INVERSION

TEMPLATES = Path(__file__).resolve().parent / "templates"


# ---------------------------------------------------------------------------
# Component records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HarmonicAssumptions:
    """What the transmission term asserts about the calendar.

    beta(t) = beta0 * exp( eps1*cos(2*pi*(t-phi1)/period) [ + eps2*... ] )
    """
    n_harmonics: int
    period_weeks: float
    #: `phi1` is the week of peak TRANSMISSIBILITY. It is NOT the week of peak
    #: admissions and must never be given a peak-week prior. Under COVID waning
    #: the epidemic peak LEADS phi1 by a median 11.0 weeks (IQR -14.4 to -7.8);
    #: under influenza waning the lead is 4.7 weeks. A peak-week prior on phi1
    #: would therefore be wrong by roughly a season quarter for COVID.
    phi1_is_peak_week: bool
    peak_lead_weeks: Optional[float]
    peak_lead_iqr: Optional[tuple]
    peak_lead_source: str
    #: Median R-squared of one annual harmonic fitted to log(admissions+1)
    #: per state, 2023-08 to 2026-08. Recorded so nobody re-derives it.
    annual_r2_median: Optional[float] = None
    #: Fraction of state-seasons carrying >= 2 distinct waves.
    p_multiwave: Optional[float] = None


@dataclass(frozen=True)
class FixedParams:
    """Structural constants the fit does NOT sample, with provenance.

    `omega_per_week is None` means omega is FITTED for this profile and the
    template must declare it `omega__FREE`. That is not a convention: the
    materializer substitutes `{{OMEGA}}`, so a template that frees omega has no
    such token and a profile that fixes omega must supply the value.
    """
    generation_time_days: float
    gamma_per_week: float
    gt_source: str
    gt_note: str
    rho: float
    rho_source: str
    gammaH_per_week: float
    gammaH_note: str
    omega_per_week: Optional[float]
    omega_source: str
    s0_default: float
    s0_range: tuple
    attack_rate_range: tuple
    attack_rate_source: str

    @property
    def omega_is_fitted(self) -> bool:
        return self.omega_per_week is None


@dataclass(frozen=True)
class ExcludedWindow:
    """A stretch of truth data that must not be scored, and why.

    Recorded rather than silently dropped: a scoring exclusion that leaves no
    trace is indistinguishable from a bug. `reason` is printed by every
    consumer that honours the exclusion.
    """
    #: Last week whose value is on the OLD measurement scale.
    last_clean_week: str
    #: First week whose value is on the NEW measurement scale.
    first_shifted_week: str
    verdict: str
    reason: str
    evidence: str
    recorded_on: str

    def crosses(self, anchor_week: str, target_end_date: str) -> bool:
        """Does a forecast anchored at `anchor_week` and scored at
        `target_end_date` straddle the discontinuity?

        A cell straddles when its anchor is on the old scale and its target is
        on the new one. Such a cell asks the model to predict a step it could
        not have known about; scoring it measures the instrument, not the
        forecast. Cells entirely on one side are fine and are NOT excluded --
        the level shift is common to model and truth there.
        """
        return (str(anchor_week) <= self.last_clean_week
                and str(target_end_date) >= self.first_shifted_week)


# ---------------------------------------------------------------------------
# The profile
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DiseaseProfile:
    key: str
    display_name: str
    #: Month whose first day opens a new season label. Flu 8, COVID 6.
    season_boundary_month: int
    #: Month/day the season window opens (season_start passed to resolve_state).
    season_end_month: int
    season_end_day: int
    target_name: str
    #: NHSN column, Socrata field name first then the web-export header.
    truth_column_alias: str
    truth_value_columns: tuple
    baseline_model: str
    hub_repo: str
    template: Path
    fitted_priors: dict
    log_scale_vars: tuple
    fixed: FixedParams
    harmonic: HarmonicAssumptions
    bimodal_capable: bool
    #: Earliest as-of date for which a vintage exists, or None for "the whole
    #: archive". Nothing before this can be made vintage-true.
    vintage_earliest: Optional[str] = None
    excluded_windows: tuple = field(default_factory=tuple)
    #: `flubnf.analogue.DonorSeasonExclusion` records: seasons this disease
    #: keeps OUT of the calendar analogue's donor pool. Distinct from
    #: `excluded_windows`, which removes cells from SCORING; these remove
    #: donors from the FORECAST. Empty for every disease that has not measured
    #: one, which is the honest default: a donor exclusion is a claim about a
    #: specific season's calendar, not a policy that generalizes.
    donor_season_exclusions: tuple = field(default_factory=tuple)

    # -- calendar ---------------------------------------------------------
    def season_of(self, d: date) -> int:
        """Season label for a date, named by the starting year."""
        return d.year if d.month >= self.season_boundary_month else d.year - 1

    def season_start(self, season_year: int) -> str:
        """ISO date string opening the season, as `resolve_state` wants it."""
        return f"{int(season_year)}-{self.season_boundary_month:02d}-01"

    def season_bounds(self, season_year: int) -> tuple:
        return (self.season_start(season_year),
                f"{int(season_year) + 1}-{self.season_end_month:02d}-"
                f"{self.season_end_day:02d}")

    def season_label(self, season_year: int) -> str:
        return f"{int(season_year)}-{(int(season_year) + 1) % 100:02d}"

    # -- exclusions -------------------------------------------------------
    def excluded_for(self, anchor_week: str, target_end_date: str):
        """The window this cell straddles, or None. See ExcludedWindow."""
        for w in self.excluded_windows:
            if w.crosses(anchor_week, target_end_date):
                return w
        return None

    @property
    def excluded_donor_seasons(self) -> frozenset:
        """Season labels to keep out of the analogue's donor pool.

        Pass this, not a literal, to `flubnf.analogue.donor_ratios`. Every
        record asserts the boundary month it was minted under, and that
        function refuses a record minted under another, so a profile cannot
        inherit a season label that means a different stretch of calendar
        for it than it did for the disease that measured it.
        """
        for e in self.donor_season_exclusions:
            if e.season_boundary_month != self.season_boundary_month:
                raise ValueError(
                    f"profile {self.key!r} carries donor exclusion "
                    f"{e.label!r}, which was minted under season boundary "
                    f"month {e.season_boundary_month} against this profile's "
                    f"{self.season_boundary_month}. A season label is not "
                    f"portable across calendars.")
        return frozenset(e.season for e in self.donor_season_exclusions)

    # -- fitting ----------------------------------------------------------
    @property
    def n_fitted(self) -> int:
        return len(self.fitted_priors)

    def fixed_tokens(self) -> dict:
        """The `{{TOKEN}}` values this profile supplies to the materializer.

        `{{OMEGA}}` is absent when omega is fitted: the template has no such
        token, and supplying one anyway would silently do nothing.
        """
        t = {"{{GAMMA}}": f"{self.fixed.gamma_per_week:.6f}",
             "{{RHO}}": f"{self.fixed.rho:g}",
             "{{GAMMAH}}": f"{self.fixed.gammaH_per_week:g}"}
        if not self.fixed.omega_is_fitted:
            t["{{OMEGA}}"] = f"{self.fixed.omega_per_week:g}"
        return t


# ---------------------------------------------------------------------------
# INFLUENZA -- today's behavior, byte for byte
# ---------------------------------------------------------------------------
# Every number below is copied from the module that currently owns it:
#   gamma, rho, gammaH, omega    flubnf/sihrs_fit.py
#   s0, attack rate, sources     flubnf/sihrs_priors.py
#   priors                       flubnf/sihrs_fit.py MIN_PRIORS
#   log-scale set                flubnf/sihrs_fit.py LOG_SCALE_VARS
#   season boundary              flubnf/analogue.py season_of, app/core/runs.py
#   season end                   app/core/retro.py season_bounds
# tests/test_profiles.py asserts each of those equalities against the source of
# truth, so this block cannot drift unnoticed.

_FLU_FIXED = FixedParams(
    generation_time_days=3.2,
    gamma_per_week=7.0 / 3.2,
    gt_source="10.1101/2024.08.17.24312064",
    gt_note=("Chan et al. 2024, US 7-site household study. Mean INTRINSIC "
             "generation time 3.2 d (95% CrI 2.9-3.6)."),
    rho=0.02,
    rho_source="UNSOURCED WORKING ASSUMPTION: biological IHR branching fraction; see sihrs_priors.py",
    gammaH_per_week=1.17,
    gammaH_note="~6 d length of stay; does NOT enter the admissions fit target",
    omega_per_week=0.019,
    omega_source=("FIXED at ~1 y immune duration. Weakly identified from "
                  "<3 seasons of a single-wave disease."),
    s0_default=0.85,
    s0_range=(0.70, 0.95),
    attack_rate_range=(0.10, 0.26),
    attack_rate_source="10.1038/s41467-021-26948-8",
)

_FLU_HARMONIC = HarmonicAssumptions(
    n_harmonics=1,
    period_weeks=52.0,
    phi1_is_peak_week=False,
    peak_lead_weeks=4.7,
    peak_lead_iqr=None,
    peak_lead_source="repertoire sweep, covid_model_assessment.md section 5.1",
    annual_r2_median=0.787,
    p_multiwave=0.368,
)

INFLUENZA = DiseaseProfile(
    key="influenza",
    display_name="Influenza",
    season_boundary_month=8,
    season_end_month=6,
    season_end_day=15,
    target_name="wk inc flu hosp",
    truth_column_alias="totalconfflunewadm",
    truth_value_columns=("Total Influenza Admissions", "totalconfflunewadm"),
    baseline_model="FluSight-baseline",
    hub_repo="cdcepi/FluSight-forecast-hub",
    template=TEMPLATES / "SIHRS_pop_min.bngl",
    fitted_priors={
        "Reff__FREE": (0.60, 2.50),
        "eps1__FREE": (0.0, 1.0),
        "phi1__FREE": (0.0, 52.0),
        "mult__FREE": (0.002, 1.0),
        "r__FREE": (0.1, 40.0),
    },
    log_scale_vars=("Reff__FREE", "mult__FREE", "impr__FREE", "r__FREE"),
    fixed=_FLU_FIXED,
    harmonic=_FLU_HARMONIC,
    bimodal_capable=False,
    vintage_earliest=None,
    excluded_windows=(),
    # Adopted 2026-08-24 after passing its pre-registered gates (hash
    # 8f3c7a45a989e905). The record itself lives in flubnf/analogue.py, which
    # owns the donor rule, so this profile references it rather than copying
    # it and cannot drift from what production applies.
    donor_season_exclusions=(SEASON_2021_22_CALENDAR_INVERSION,),
)


# ---------------------------------------------------------------------------
# COVID-19
# ---------------------------------------------------------------------------

# gamma. THE TRAP THE MEMO WARNED ABOUT, AND THE MEMO FELL INTO IT.
# ------------------------------------------------------------------
# The decision memo says "Omicron-lineage generation time is close to
# influenza's, roughly 3 days, not the 5-7 days of ancestral SARS-CoV-2 ...
# Source it." Sourced, that is not what the literature says.
#
# Manica et al. 2022 (Lancet Reg Health Eur, 23,122 infected individuals in
# 8,903 households, Reggio Emilia, January 2022) estimate for Omicron:
#     mean INTRINSIC generation time      6.84 d  (95% CrI 5.72-8.60)
#     mean realized HOUSEHOLD generation  3.59 d  (95% CrI 3.55-3.60)
#     household serial interval           2.38 d  (95% CrI 2.30-2.47)
# and state plainly that the intrinsic generation time "might not have shortened
# as compared to previous estimates on ancestral lineages, Alpha and Delta".
# The "roughly 3 days" figure is the REALIZED household interval or the serial
# interval -- both depressed by susceptible depletion inside a household and, in
# the contact-tracing cohorts that report 2.7-2.8 d, by isolation.
#
# SIHRS's `gamma` is the removal rate of a frequency-dependent SIR in a large
# population. The matching quantity is the INTRINSIC generation time, and the
# influenza value this profile mirrors (Chan 2024) is explicitly intrinsic. A
# like-for-like swap therefore takes 6.84 d, not 3.
# Corroboration on the same (intrinsic) scale: Hart et al. 2022 give Alpha 5.5 d
# (95% CI 4.7-6.5) and Delta 4.7 d (4.1-5.6).
# CONSEQUENCE, stated because it is large: gamma falls from 2.19/wk to 1.02/wk,
# which more than halves the modelled epidemic's intrinsic speed. This is a
# first-pass value and belongs on any sensitivity arm.
COVID_GENERATION_TIME_DAYS = 6.84
COVID_GT_CRI = (5.72, 8.60)
COVID_GT_SOURCE = "10.1016/j.lanepe.2022.100446"            # Manica et al. 2022
COVID_GT_CORROBORATION = ("10.1016/S1473-3099(22)00001-9",)  # Hart et al. 2022

# omega. The parameter this whole exercise exists to free.
# -------------------------------------------------------
# In SIHRS an individual in R is fully protected and leaves at hazard `omega`,
# so the population fraction still protected t weeks after infection is
# exp(-omega*t). Two systematic reviews give that curve directly:
#
#   Bobrovitz et al. 2023, Lancet Infect Dis. Effectiveness of previous
#   infection against REINFECTION waned to 24.7% (95% CI 16.4-35.5) at 12
#   months  =>  omega = -ln(0.247)/52.18 = 0.0268/wk  (37.3 wk, 8.6 months)
#
#   COVID-19 Forecasting Team 2023, Lancet. Protection against omicron BA.1
#   reinfection 36.1% (24.4-51.3) at 40 weeks
#                          =>  omega = -ln(0.361)/40 = 0.0255/wk  (9.0 months)
#
# Two independent meta-analyses land within 5% of each other at roughly a
# nine-month mean protected duration, comfortably inside the memo's 3-12 month
# window and close to the 26-week median of the parameter sets that reproduced
# COVID's two-wave year in the repertoire sweep.
#
# THE PRIOR IS DELIBERATELY WIDER THAN THE GATE WINDOW. Gate A clause (1) asks
# whether the posterior concentrates inside 3-12 months AND off its bounds. If
# the prior box were the gate window that clause would be near-tautological:
# any posterior is inside a box it cannot leave. The box below spans 1.8 to 18
# months, so the gate window is strictly interior with margin on both sides and
# clause (1) is a real test. Pinning at either end is a kill, per the memo.
COVID_OMEGA_LIT = {
    "bobrovitz_2023_12mo": 0.0268,
    "covid19_forecasting_team_2023_40wk": 0.0255,
}
COVID_OMEGA_SOURCES = ("10.1016/S1473-3099(22)00801-5",   # Bobrovitz et al. 2023
                       "10.1016/S0140-6736(22)02465-5")   # Lancet 2023 meta-analysis
#: Gate window, in per-week waning rate. 3 months = 13.04 wk, 12 months = 52.18 wk.
COVID_OMEGA_GATE = (7.0 / (30.44 * 12.0), 7.0 / (30.44 * 3.0))   # (0.01916, 0.07665)
#: Prior box, 1.8 to 18 months.
COVID_OMEGA_PRIOR = (7.0 / (30.44 * 18.0), 7.0 / (30.44 * 1.8))  # (0.01278, 0.12780)

# rho, the true infection-hospitalisation ratio used as a BRANCHING fraction.
# Only rho*mult is identified and only rho enters the reaction rules, so this
# value moves the S/I dynamics by a fraction of a percent either way. Set an
# order of magnitude below flu's 2% for the high-immunity Omicron era, and
# flagged as first-pass. It is NOT an ascertainment figure.
COVID_RHO = 0.005

# Cumulative INFECTION attack rate per season, the denominator of the pinned
# rho*mult product. Wide on purpose: rho*mult scales inversely with it and this
# is the weakest link in the COVID chain exactly as Vinh 2021 is in the flu one.
# Anchored on the reinfection meta-analyses above: with protection against
# reinfection down to ~25-36% within a year, a large fraction of the population
# is reinfectable annually, and the endemic-era serologic and modelling
# literature puts annual infection incidence in the tens of percent.
COVID_ATTACK_RATE_RANGE = (0.20, 0.50)

_COVID_FIXED = FixedParams(
    generation_time_days=COVID_GENERATION_TIME_DAYS,
    gamma_per_week=7.0 / COVID_GENERATION_TIME_DAYS,
    gt_source=COVID_GT_SOURCE,
    gt_note=("Manica et al. 2022, Omicron INTRINSIC generation time 6.84 d "
             "(95% CrI 5.72-8.60), 8,903 households. The 2.4-3.6 d figures in "
             "circulation are the realized household interval and the serial "
             "interval, which are the wrong quantity for a large-population "
             "frequency-dependent SIR. Corroborated on the intrinsic scale by "
             "Hart et al. 2022 (Alpha 5.5 d, Delta 4.7 d)."),
    rho=COVID_RHO,
    rho_source=("first pass: order of magnitude below influenza's 2% for the "
                "high-immunity Omicron era. Branching only; rho*mult is the "
                "identified combination and mult is fitted."),
    gammaH_per_week=1.17,
    gammaH_note=("~6 d length of stay, carried over from the influenza profile. "
                 "Does NOT enter the admissions fit target at all, so it is "
                 "unidentifiable here and its value cannot bias the fit."),
    omega_per_week=None,                 # FITTED. See COVID_OMEGA_* above.
    omega_source="UNSOURCED WORKING ASSUMPTION:  / ".join(COVID_OMEGA_SOURCES),
    s0_default=0.85,
    s0_range=(0.50, 0.95),
    attack_rate_range=COVID_ATTACK_RATE_RANGE,
    attack_rate_source=" / ".join(COVID_OMEGA_SOURCES),
)

_COVID_HARMONIC = HarmonicAssumptions(
    n_harmonics=1,
    period_weeks=52.0,
    phi1_is_peak_week=False,
    peak_lead_weeks=11.0,
    peak_lead_iqr=(-14.4, -7.8),
    peak_lead_source="repertoire sweep, covid_model_assessment.md section 5.1",
    annual_r2_median=0.454,
    p_multiwave=0.725,
)

#: The one measurement discontinuity found in the CovidHub truth record.
#: Quantified in flubnf/reporting_breaks.py; the verdict is INSTRUMENT.
COVID_MARCH_2026_BREAK = ExcludedWindow(
    last_clean_week="2026-03-21",
    first_shifted_week="2026-03-28",
    verdict="INSTRUMENT, not epidemiology",
    reason=("NHSN confirmed weekly admissions fall by 41-45% in the single week "
            "2026-03-21 -> 2026-03-28 for COVID (-42.7%), influenza (-45.2%) and "
            "RSV (-41.0%) simultaneously, while the number of hospitals reporting "
            "the metric is flat (5,249 -> 5,159, -1.7%) and all 52 non-national "
            "jurisdictions keep reporting. Three pathogens measured by one form do "
            "not fall together for biological reasons. Any forecast anchored "
            "before the step and scored after it is measuring the instrument."),
    evidence=("US national, Socrata mpgq-jmmr fields totalconfc19newadm / "
              "totalconfflunewadm / totalconfrsvnewadm and their *hosprep "
              "reporting counts, plus CovidHub target-data/time-series.parquet "
              "at as_of 2026-08-19. The step is 7.6 robust SD on the log-ratio "
              "residual and 1.9x the next largest excursion in the 84-vintage "
              "record; it was present in the FIRST issue (as_of 2026-04-01), so "
              "it is not a revision artefact."),
    recorded_on="2026-08-22",
)

COVID = DiseaseProfile(
    key="covid",
    display_name="COVID-19",
    season_boundary_month=6,
    season_end_month=5,
    season_end_day=31,
    target_name="wk inc covid hosp",
    truth_column_alias="totalconfc19newadm",
    truth_value_columns=("Total COVID-19 Admissions", "totalconfc19newadm"),
    baseline_model="CovidHub-baseline",
    hub_repo="CDCgov/covid19-forecast-hub",
    template=TEMPLATES / "SIHRS_pop_covid.bngl",
    # Five influenza parameters plus omega. ONE added dimension, and the memo
    # names the reason: omega decides bimodality and is currently fixed.
    # eps2/phi2 are deliberately NOT restored -- the repertoire sweep shows the
    # one-harmonic form already reaches COVID's two-wave year in 20.4% of the
    # realistic-amplitude region once omega is free, so the second harmonic buys
    # reachability that is already there at the cost of two dimensions of
    # posterior width, which is this port's named failure mode.
    fitted_priors={
        "Reff__FREE": (0.60, 2.50),
        "eps1__FREE": (0.0, 1.0),
        "phi1__FREE": (0.0, 52.0),
        "omega__FREE": COVID_OMEGA_PRIOR,
        "mult__FREE": (0.002, 1.0),
        "r__FREE": (0.1, 40.0),
    },
    log_scale_vars=("Reff__FREE", "mult__FREE", "impr__FREE", "r__FREE",
                    "omega__FREE"),
    fixed=_COVID_FIXED,
    harmonic=_COVID_HARMONIC,
    bimodal_capable=True,
    vintage_earliest="2024-11-20",
    excluded_windows=(COVID_MARCH_2026_BREAK,),
    # EXPLICITLY EMPTY, and it must stay empty until a COVID retrospective
    # measures one. Influenza excludes 2021-22 because that season's epidemic
    # was calendar-INVERTED against the others (peak epiweek 16 against 48-6),
    # which is a claim about influenza's calendar and carries nothing about
    # COVID's. It is also not even expressible here: the label 2021 under
    # influenza's 1 August boundary is 2021-08-01 to 2022-07-31, and under
    # COVID's 1 June boundary the same label is 2021-06-01 to 2022-05-31.
    # Inheriting it would silence the wrong ten weeks and keep the wrong ten.
    # DiseaseProfile.excluded_donor_seasons and
    # flubnf.analogue.resolve_donor_exclusions both refuse that mistake, but
    # the empty tuple is written out so the decision is visible here too.
    donor_season_exclusions=(),
)


PROFILES: dict = {p.key: p for p in (INFLUENZA, COVID)}
DEFAULT_PROFILE = INFLUENZA


def get_profile(key: str) -> DiseaseProfile:
    """Look up a profile by key, LOUDLY. A typo must not fall back to flu."""
    try:
        return PROFILES[str(key)]
    except KeyError:
        raise KeyError(
            f"unknown disease profile {key!r}; have {sorted(PROFILES)}") from None
