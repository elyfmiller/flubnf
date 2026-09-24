"""RESEARCH (COVID profile seam, not on the shipped path): DiseaseProfile,
everything that varies between diseases, as data rather than a forked path.

INFLUENZA reproduces the shipped constants exactly; tests/test_profiles.py
asserts each against the module that owns it (season_of, season_start,
retro.season_bounds, ...), so a failure means the profile drifted, not
production.

COVID (first pass, never validated against a COVID retrospective) changes:
  season boundary 8 -> 6   the summer wave peaks at epiweeks 31-36; August
                           would cut an epidemic in half. June is the trough.
  target/truth column      same hubverse structure, sibling NHSN column.
  baseline                 CovidHub-baseline, the same estimator as
                           FluSight's (relWIS comparable; the field is not).
  omega FREED              omega, not eps2, decides whether one harmonic
                           can make two epidemics a year; fixing it decides
                           bimodality by fiat.
  bimodal_capable          72.5% of COVID state-seasons are multi-wave (flu
                           36.8%); one-epidemic code paths must refuse or
                           mark output (flubnf/unimodal_guard.py).
s0 is a sensitivity axis for both diseases. Sources: docs/MODEL-PROVENANCE.md section 5.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from flubnf.analogue import (SEASON_2020_21_SUPPRESSED,
                             SEASON_2021_22_CALENDAR_INVERSION)

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
    #: `phi1` is peak TRANSMISSIBILITY, not peak admissions: never give it a
    #: peak-week prior (the peak leads it by ~11 wk for COVID, 4.7 for flu).
    phi1_is_peak_week: bool
    peak_lead_weeks: Optional[float]
    peak_lead_iqr: Optional[tuple]
    peak_lead_source: str
    #: Median R^2 of one annual harmonic on log(admissions+1) per state, 2023-26.
    annual_r2_median: Optional[float] = None
    #: Fraction of state-seasons carrying >= 2 distinct waves.
    p_multiwave: Optional[float] = None


@dataclass(frozen=True)
class FixedParams:
    """Structural constants the fit does NOT sample, with provenance.

    `omega_per_week is None` means omega is FITTED: the template declares
    `omega__FREE` and has no `{{OMEGA}}` token.
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

    Recorded, not silently dropped; consumers print `reason`.
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

        Such a cell scores the instrument, not the forecast; cells wholly
        on one side are kept (the shift is common to model and truth).
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
    #: Month/day the season window CLOSES in the following year (season_bounds).
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
    #: DonorSeasonExclusion records removing donors from the FORECAST (vs
    #: excluded_windows, which removes cells from SCORING). Empty unless
    #: measured for this disease: an exclusion does not generalize.
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

        Pass this, not a literal, to donor_ratios. A record minted under
        another season boundary is refused (the label means other weeks).
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

        `{{OMEGA}}` is absent when omega is fitted.
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
# Copied from the owning modules on purpose (tests/test_profiles.py asserts
# each equality): sihrs_fit (gamma, rho, gammaH, omega, MIN_PRIORS,
# LOG_SCALE_VARS), sihrs_priors (s0, attack rate), analogue.season_of and
# app/core/runs.py (boundary), app/core/retro.season_bounds (season end).

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
    # Referenced, not copied, from flubnf/analogue.py (registry order).
    donor_season_exclusions=(SEASON_2021_22_CALENDAR_INVERSION,
                             SEASON_2020_21_SUPPRESSED),
)


# ---------------------------------------------------------------------------
# COVID-19
# ---------------------------------------------------------------------------

# gamma: Omicron INTRINSIC generation time 6.84 d (Manica 2022, CrI
# 5.72-8.60), the quantity matching SIHRS and flu's Chan 2024 value. The ~3 d
# figures in circulation are household/serial intervals. Halves gamma
# (2.19 -> 1.02/wk): first pass, belongs on a sensitivity arm. Hart 2022
# (10.1016/S1473-3099(22)00001-9) corroborates on the intrinsic scale.
# See docs/MODEL-PROVENANCE.md section 5.
COVID_GENERATION_TIME_DAYS = 6.84
COVID_GT_SOURCE = "10.1016/j.lanepe.2022.100446"            # Manica et al. 2022

# omega (protected fraction exp(-omega*t)): two reinfection meta-analyses
# agree on ~9 months (Bobrovitz 2023: 0.0268/wk; COVID-19 Forecasting Team
# 2023: 0.0255/wk). The prior box (1.8-18 months) is deliberately wider than
# the 3-12 month gate window so "concentrates inside, off its bounds" is a
# real test; pinning at either end is a kill.
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

# rho: IHR as a BRANCHING fraction (not ascertainment; only rho*mult is
# identified). First pass: a notch below flu's 2% for the Omicron era.
COVID_RHO = 0.005

# Seasonal INFECTION attack rate (denominator of the pinned rho*mult): wide on
# purpose, the weakest link (as Vinh 2021 is for flu); anchored on the
# reinfection meta-analyses above.
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
    omega_source=" / ".join(COVID_OMEGA_SOURCES),
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
    # Flu's five plus omega. eps2/phi2 stay out: with omega free one harmonic
    # already reaches the two-wave year, and width is the named failure mode.
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
    # EXPLICITLY EMPTY until a COVID retrospective measures one: flu's
    # exclusions are claims about flu's calendar, and their labels name other
    # weeks under a June boundary.
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
