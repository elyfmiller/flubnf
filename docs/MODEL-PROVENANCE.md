# Model provenance: the SIHRS BNGL templates

This document is the permanent home for the design history, measured results,
sourced values, and warnings that used to live as comment blocks inside the
BNGL templates. The templates themselves (`flubnf/templates/*.bngl`) now carry
only what a reader needs at the point of use, plus one-line pointers here.
Nothing in this document is speculative: every claim below was measured, and
several record experiments that FAILED. Do not redo them without reading why.

Covered templates:

| Template | Role |
|---|---|
| `SIHRS_pop_min.bngl` | Single-strain production model (5 fitted parameters); the PF engine's template |
| `SIHRS_pop_2strain_min.bngl` | Two-strain (A/B) production variant (7 fitted parameters) |
| `SIHRS_pop_natg.bngl` | `min` plus one exogenous national-growth factor, zero new fitted parameters |
| `SIHRS_pop_covid.bngl` | COVID-19 port: `min` with `omega` fitted instead of fixed (6 parameters) |
| `SIHRS_pop_covid_2h.bngl` | COVID Gate A round two, arm A2: `covid` plus the semi-annual harmonic (8 parameters) |
| `SIHRS_pop.bngl` | Multi-season 8-parameter model (keeps `impr`, `eps2`, `phi2`); not trimmed, see section 3 |

Companion sources of record:

* `flubnf/sihrs_priors.py` -- the DOI or data derivation behind every fixed
  influenza value (`gamma`, `rho`, `gammaH`, `omega`, `s0`, `i0`).
* `flubnf/profiles.py` -- the COVID `DiseaseProfile`, its priors, and the
  COVID-specific sources.
* `research/spatial-nowcast-probe/FINDINGS.md` -- the measurements behind the
  national-growth variant.
* `research/covid-phase0/gate_a.py` and `gate_a2.py` -- the frozen COVID gate
  pre-registrations.

---

## 1. Shared architecture

### 1.1 Population parameterization (why there is no magnitude anchor)

The compartments are ABSOLUTE PEOPLE and the state population `N` enters as
known data, instead of an `S(0)=1` normalization plus a fitted or derived
`scaled` anchor.

History: with `S(0)=1` normalization, matching an observed peak `P` required

    mult * scaled_factor = 1/(5.5*f) ~= 30      (f = max_t[rho*gamma*I])

which is INDEPENDENT of `P`, so the anchor carried no per-state information
and sat about 6x above the `mult` prior ceiling. `mult` therefore pinned in
43 of 52 states and forecasts came out roughly 30x low. With `N` in the model
the observation scale is a dimensionless fraction and no anchor is needed.

### 1.2 Frequency-dependent infection

Infection is frequency-dependent: rate constant `beta()/N`, flux
`beta*S*I/N`. That keeps `beta` on exactly the same scale as the normalized
model -- substituting `s=S/N`, `i=I/N` recovers `di/dt = beta*s*i - gamma*i`
identically -- so the R0, `gamma`, `eps`, and `phi` priors transfer unchanged
and no re-derivation is needed.

### 1.3 Seed species

`R(0)` carries the non-susceptible, non-infected remainder, so
`S+I+H+R = N` exactly and pre-existing immunity is representable (`s0 < 1`),
which the `S(0)=1` normalization structurally cannot express.

### 1.4 Fit the flux, never the census

The fit target is REPORTED ADMISSIONS, never the census `H(t)`. `H` is
hospital occupancy; NHSN reports weekly admissions. Fitting the census to an
admissions target conflates a stock with a flow.

What is reported is a weekly COUNT, so the fit target is the INTEGRAL of the
ascertained admission flux `rho*mult*gamma*I` across the reporting week, never
a point sample of that flux. The shipped particle filter runs
`pf_observable_mode = integrated` (the default in `app/core/runs.py`) and
forms `mu = mult * (H_Cum[week end] - H_Cum[week start])`. The two are not
interchangeable: at local weekly log-growth `lam` the ratio of the instant to
the integral is `lam/(1 - exp(-lam))`, which on 2024-25 state admissions is
+46 percent at the median jurisdiction's fastest week and reverses sign in
decline. That derivation, and the batch-AMCMC path which still carries the
bias and must not be published, are recorded in `flubnf/sihrs_fit.py`.

`rho*mult` carries biological IHR times reporting ascertainment. `rho` also
appears in the reaction rules because it is a real branching fraction; `mult`
does NOT and must never: ascertainment must never alter how people move
between compartments, only what we observe of them.

`H_Cum` (the `Hadm()` accumulator) exists because the engine's
`neg_bin_dynamic` likelihood differences any `_Cum` observable into weekly
increments. The accumulator rule `I() -> I() + Hadm()` counts the `I -> H`
flux without consuming `I`.

### 1.5 The `pi` constant (engine workaround)

`pi` is written as a literal (`3.141592653589793`) because BNGL's built-in
`_pi()` breaks the toolchain: bngsim codegen emits `M_PI()` -- a function
call -- which does not compile. Do not "clean this up" back to `_pi()`.

---

## 2. Parameter provenance (single-strain influenza)

Fitted (5): `Reff`, `eps1`, `phi1`, `mult`, `r`. Everything else is fixed
from data or the literature; `flubnf/sihrs_priors.py` records each fixed
value's DOI or derivation next to the code that computes it.

### Reff (fitted)

BASE reproduction number: the harmonic-neutral value at the initial
susceptible fraction `s0`. It is NOT the season-start value and NOT the
realised one, and the name invites both mistakes. Three distinct quantities:

* `Reff` itself, harmonic-neutral, at `S = N*s0`.
* the SEASONALLY FORCED value at that same initial susceptible fraction,
  `Reff*exp(eps1*cos(2*pi*(t-phi1)/52))`, which equals `Reff` only where the
  cosine vanishes (`phi1 = 13` or `39`);
* the REALISED effective reproduction number in week `t`, which carries
  susceptible depletion as well,
  `Reff*exp(eps1*cos(2*pi*(t-phi1)/52)) * S(t)/(N*s0)`.

The last two agree only at `t = 0`, where `S = N*s0`. Recomputed from the
shipped teaching run `app/state/workroots/smoke1s/Pennsylvania_r0/`
(`Reff = 1.20`, `eps1 = 0.15`, `phi1 = 22`), the forced expression reads
1.0507 / 1.2219 / 1.3942 at weeks 0 / 10 / 22 while the realised value from
the `.gdat` is 1.0507 / 1.1731 / 0.8447. At week 22 the forced form is 65
percent high. Quote the realised form whenever the quantity is described as
the reproduction number "at" some week.

Fit `Reff`, NOT R0: admissions identify `Reff` (via the growth rate), and
with `S(0) = N*s0` the classic `R0 = Reff/s0` is only recoverable post hoc.
Fitting R0 with `s0 < 1` silently requires `R0 > 1/s0` just to sustain an
epidemic. `R0` is likewise a BASE value, not a season-start, realised or
peak one.

### eps1, phi1 (fitted)

Annual-harmonic amplitude and phase of the seasonal forcing
`beta() = beta0*exp(eps1*cos(2*pi*(t-phi1)/52))`. The `exp()` form keeps
`beta > 0`. `phi1` is the week of peak TRANSMISSIBILITY, not the week of the
epidemic peak; see section 5.3 for why it must never carry a peak-week prior.

### gamma (fixed)

`7/3.2` per week: 3.2-day mean intrinsic generation time,
Chan 2024, doi:10.1101/2024.08.17.24312064. Note this is the INTRINSIC
generation time, the matching quantity for a large-population
frequency-dependent model (see the COVID `gamma` entry for the
intrinsic-versus-realized trap).

### rho (fixed)

True infection-hospitalization ratio: the biological branching fraction
`I -> H`. Used ONLY in the reaction rules (the flow of people), never in the
observable. Sources and the NHSN-versus-FluSurv-NET ascertainment trap:
`flubnf/sihrs_priors.py`.

### mult (fitted)

Ascertainment: reported / modelled admissions. Fitted log-uniform on
`[0.002, 1.0]`, the shipped prior: `app/core/engines/pf.py` emits
`loguniform_var = mult__FREE 0.002 1.0`, and `flubnf/sihrs_fit.py` and
`flubnf/profiles.py` carry the same bounds. The ceiling is 1.0 because
ascertainment is a reporting fraction: reported admissions cannot exceed 100
percent of the modelled ones. A narrower `0.10` ceiling was tried earlier and
abandoned as defective, because an active upper bound pins `mult` and then
couples it inversely to `Reff`, letting the bound rather than the data set the
observation scale; section 1.1 records that failure mode under the scaled
anchor. Only the product `rho*mult` is identified, but the product CANNOT
be pinned a priori: it depends on the attack rate, which is itself a
consequence of the fitted `Reff`. Pinning it was tried and froze the
magnitude 2.45x wrong while driving `r` to its floor. The resolution: fix
`rho` (biology) and fit `mult` (observation).

### gammaH (fixed)

Discharge rate. It does not enter the admissions fit target at all (it moves
the `H` census only), so it is unidentifiable here and must stay fixed.

### omega (fixed for influenza)

Waning `R -> S`. Weakly identified from fewer than 3 seasons of data, so it
is fixed for influenza. The COVID port frees it; see section 5.

### r (fitted)

Negative-binomial dispersion of the observation model (AMCMC).

### N, s0, i0 (known data, never fitted)

State population, initial susceptible fraction, initial infected fraction.
`s0` is fixed because `R0*s0` is product-identified: freeing both `Reff`
and `s0` adds a ridge, not information.

---

## 3. Decisions and negative results (influenza)

**Every influenza measurement in this section that involves the calendar
analogue was made against the PRE-EXCLUSION donor pool, the one that still
included 2021-22.** On 2026-08-24 that season was excluded from the shipped
pool, which narrowed the analogue materially: its pooled member relWIS moved
from 0.8290 to 0.7723, and the pooled ensemble's central 50, 80 and 95
percent widths fell to 0.93, 0.92 and 0.90 of their previous totals. The
figures below have not been re-derived on the shipped pool. See
`docs/RELEASE-1.0.md` for the change and its evidence.

### 3.1 Why 5 parameters, not 8 (measured)

The entire gap between SIHRS and a well-calibrated reference is SPREAD, not
the central estimate. Swapping SIHRS's median for the analogue's gains 0.003
relWIS; swapping the SPREAD gains 0.070. So the median is fine and the
predictive distribution is too wide. Both figures are pre-exclusion, per the
notice above, and neither has been re-measured against the shipped analogue.
The decision they support was taken on them as they stand.

That width comes from fitting 8 parameters to about 26 weekly points. Each
removed dimension removes a source of posterior spread, which is the actual
defect. Two removals, each for a measured reason, follow.

### 3.2 eps2, phi2 removed (the semi-annual harmonic) -- DO NOT re-add for influenza

An ablation found that the second Fourier harmonic makes `beta(t)` two-humped
but does NOT produce two epidemic peaks: susceptible depletion suppresses the
second hump. The fits were also degenerate: R-hat 2.38 / 26.8. This is a
result about INFLUENZA WANING (1 to 5 year timescale); it was later retired
for COVID specifically, where fast waning changes the answer -- see
section 5.1. Do not cite the influenza ablation as if it transferred.

### 3.3 impr removed from single-season templates -- KEEP it for multi-season

`impr` is the external reseeding hazard (per-susceptible weekly hazard of
infection from OUTSIDE the population). In single-season fits it was PINNED
IN 75% OF FITS, i.e. not identified by the data, and it is dynamically inert
over one 48-week season -- verified: peak 142.6 with `impr = 1e-7` and with
`impr = 0`, and `I` never approaches the denormal range.

KEEP `impr` FOR MULTI-SEASON WORK (`SIHRS_pop.bngl`). Between seasons `I`
decays for about 30 weeks and, in absolute counts, reaches about 1e-150
people -- biologically meaningless and numerically denormal, which made CVODE
fail on 100% of 230-week multi-season fits. Dropping `impr` there
reintroduces that failure.

Why the term exists at all: waning refills the FUEL (`S`) but supplies no
SPARK (`I`), and infection is `S+I -> I+I`, proportional to `I`. Real flu is
REIMPORTED each autumn from other populations; a closed single-population ODE
cannot represent that. The rule is written `S() -> I()` (not `0 -> I()`) so
total population is conserved. It is FITTED in the multi-season template
because no clean literature value exists for a per-state weekly reseeding
rate; it also separates from `i0` multi-season, because `i0` affects only the
FIRST season while importation drives every season's onset.

`tests/test_min_template.py` enforces both halves of this decision.

---

## 4. The national-growth variant (`SIHRS_pop_natg.bngl`)

Production `min` PLUS one exogenous term, zero new fitted parameters:

    beta_s(t)  *=  exp( iota * ( g_nat^{-s}(t) - g_s^obs(t) ) )

`g_nat^{-s}` is the population-weighted LEAVE-ONE-OUT log-growth of
vintage-true weekly admissions across all OTHER FluSight jurisdictions, as of
the same as-of date. `g_s^obs` is the state's own most recent vintage-true
log-growth. Both are built OUTSIDE the BNGL, at materialize time, by
`flubnf/natgrowth.py`, from `app.core.data.vintage_path(asof)` -- never from
the latest file.

### 4.1 Why, measured

Leave-one-out national growth at week `t` predicts a state's own growth at
`t+1` AFTER the state's AR(1) and a Fourier seasonal -- i.e. after exactly
the information `eps1`/`phi1` already give the model. Partial correlation
+0.469. LOSO delta-R^2 +0.081 / +0.032 / +0.118 and turn-week RMSE
reductions +8.9% / +2.4% / +14.7% over 2023-24 / 2024-25 / 2025-26. This is
THIS year's realised wave, not the calendar: nothing else in the production
system sees "the Midwest peaked last week". Detail:
`research/spatial-nowcast-probe/FINDINGS.md` section 1.

### 4.2 On growth, never on level

A level-form importation term `sum_s' w_ss' * A_s'/N_s'` restates prevalence,
which the filter already has (the occupancy-ratio trap). The DIFFERENCE form
is neutral by construction: a state growing at the national rate gets a
multiplier of exactly 1, so the term can only speak when the state and the
country disagree.

### 4.3 Not a metapopulation

The ODEs are not coupled, no species are added, no movement rates exist.
Per-state filters, 10k particles, 5 fitted parameters and per-state
parallelism are all unchanged. A coupled 52-region model was measured and
rejected (`FINDINGS.md` section 1).

### 4.4 iota is frozen a priori -- it is not a fitted parameter

OLS of next-week own log-growth on leave-one-out national growth, given own
lag-1 growth and a first Fourier harmonic on week-of-season
(`probe.py::spatial()`'s design matrix), fitted separately on the two seasons
the handoff names:

    2023-24  n=1393  b[g_nat] = 0.7574
    2024-25  n=1418  b[g_nat] = 0.4504
    mean                        0.6039
    x0.5 shrink toward zero  -> 0.3020   <- iota

Cross-check: pooling those two seasons gives b = 0.5528 -> 0.276, the same
number within the season-to-season spread. 2025-26 is NOT in the average (its
own coefficient is 0.8040, so the exclusion made iota smaller, not larger).
Reproduce: `./.venv/bin/python research/spatial-nowcast-probe/iota_freeze.py`.
The constant lives in `flubnf/natgrowth.py::IOTA_FROZEN`. It must NEVER
appear as a `*__FREE` var line, and it must never be retuned after seeing
scores (handoff Law 1). `app/tests/test_natgrowth.py` enforces this.

Honest note on effective strength: `iota` multiplies `beta`, not the growth
rate. `exp(iota*gap)` shifts weekly log-growth by roughly
`gamma*Reff*iota*gap`, and `gamma` is 2.19/week, so the implemented response
is about 0.66 per unit gap: the x0.5 shrink is approximately cancelled by
that amplification and the term lands near 1.0x the regression coefficient
rather than 0.5x. Recorded so nobody reads 0.3020 as "half strength" when
reporting the arm.

### 4.5 Forecast weeks, the pre-registered rule

`g_nat` is unknown at horizons 1 to 4. THE LAST OBSERVED `(g_nat - g_s)` GAP
IS HELD CONSTANT ACROSS THE 1 TO 4 WEEK HORIZON. No extrapolation, no decay
toward zero, no forecast of the national series. The rule is structural, not
a code path: the final branch of the piecewise `natgap()` expression carries
no upper guard, so every `t` at or beyond the last observed week takes that
value. (A short form of this rule stays in the template header on purpose:
pre-registration is only pre-registration if it is written down, and a test
asserts the template says it.)

### 4.6 Alignment and causality

The filter integrates one segment per observation, `[w-1, w]`. The piecewise
value on `[w-1, w)` is the gap realised up to and including week `w-1`, i.e.
information that existed before that week began. No look-ahead.

### 4.7 Numerical guard

The gap is clipped to +-1.0 log-growth units before `iota` is applied
(`flubnf/natgrowth.py::GAP_CLIP`), so the beta multiplier stays inside
`[0.74, 1.35]`. `beta` enters as `beta0*exp(...)` and the `eps1` bounds are
stiffness-critical; one state reporting 2 admissions after 40 must not hand
`exp()` an argument no solver should see. Clipped weeks are counted and
reported per cell, never silently absorbed. A week with no defined growth
(missing data, or either endpoint under the 5-admission floor) contributes
exactly 0.0, i.e. the production model.

The variant's extra tokens are IOTA, GAPEXPR, and GAPNOTE (all supplied by
`flubnf/natgrowth.py::natg_tokens`); comments in the template write them
without braces so they survive materialization.

---

## 5. The COVID-19 port (`SIHRS_pop_covid.bngl`, `SIHRS_pop_covid_2h.bngl`)

The only structural difference between `SIHRS_pop_covid.bngl` and
`SIHRS_pop_min.bngl` is that `omega` is FITTED instead of fixed. Everything
else -- compartments, reaction rules, the single annual harmonic, the
observable, the frequency-dependent infection term, the population
parameterization -- is identical. The OMEGA token is deliberately absent
from the covid template, which therefore must never contain that placeholder.

### 5.1 Why omega, and why only omega (the repertoire sweep)

A 60,000-draw forward sweep of the plausible parameter region asked how often
the exact one-harmonic structure produces COVID's observed year: two distinct
waves, one in winter and one in summer, each at least half the annual
maximum, in three consecutive years.

    k=1 beta, COVID waning 3-12 mo      6.7% of sets   (20.4% at eps1 <= 0.5)
    k=2 beta, COVID waning 3-12 mo     18.4% of sets   (39.3% at eps1 <= 0.5)
    k=1 beta, influenza waning 1-5 yr   1.2% of sets   ( 4.0% at eps1 <= 0.5)

Read the first and third rows together. The SAME structure is essentially
incapable of a two-wave year under influenza waning and reaches it in a fifth
of the realistic-amplitude region under COVID waning. The parameter that
unlocks bimodality is `omega`, NOT `eps2`: with waning on a roughly 6-month
timescale the susceptible pool refills between forcing peaks and a second
epidemic fires. That is a relaxation oscillation, not a second hump in
`beta(t)`.

This retires, for COVID only, the influenza eps2 ablation of section 3.2.
That result is correct and it is a result about INFLUENZA WANING. It does not
transfer, and it must not be cited as if it did.

Round one kept eps2/phi2 out anyway: 20.4% reachability at realistic
amplitude was judged enough for the fit to find the regime if the data want
it, and the measured defect of this model family is WIDTH (section 3.1). Two
extra dimensions fitted to about 40 weekly points buy reachability that is
already present and pay for it in exactly the currency the port is most
likely to fail in.

### 5.2 COVID parameter sources

`gamma` FIXED at `7/6.84` per week: 6.84-day mean INTRINSIC generation time
for Omicron, Manica 2022, doi:10.1016/j.lanepe.2022.100446 (8,903 households,
95% CrI 5.72-8.60 d). The 2.4-3.6 d figures in circulation are the REALIZED
household generation time and the serial interval, both depressed by
within-household susceptible depletion and, in contact-tracing cohorts, by
isolation. This model is a large-population frequency-dependent SIR, so the
intrinsic quantity is the matching one -- and the influenza value it mirrors
(Chan 2024) is explicitly intrinsic too, so this is like for like.
Corroborated on the same scale by Hart 2022,
doi:10.1016/S1473-3099(22)00001-9 (Alpha 5.5 d, Delta 4.7 d).

`rho` FIXED: first-pass COVID value is an order of magnitude below
influenza's 2%, for the high-immunity Omicron era; only `rho*mult` is
identified and `mult` is fitted, so this moves the S/I dynamics negligibly.
See `flubnf/profiles.py` for the value and source.

`omega` FITTED: prior loguniform over `[0.01278, 0.12780]` per week, i.e. a
mean protected duration of 1.8 to 18 months. Sourced: in SIHRS an individual
in `R` is fully protected and leaves at hazard `omega`, so the fraction still
protected `t` weeks after infection is `exp(-omega*t)`, and two systematic
reviews give that curve directly:

* Bobrovitz 2023, Lancet Infect Dis, doi:10.1016/S1473-3099(22)00801-5 --
  protection against reinfection 24.7% (16.4-35.5) at 12 months
  => `omega = -ln(0.247)/52.18 = 0.0268/wk` (8.6 months).
* Lancet 2023 meta-analysis, doi:10.1016/S0140-6736(22)02465-5 --
  protection against omicron BA.1 reinfection 36.1% (24.4-51.3) at 40 weeks
  => `omega = -ln(0.361)/40 = 0.0255/wk` (9.0 months).

Two independent meta-analyses agree within 5%, and the 26-week median of the
sweep sets that reproduced COVID's two-wave year sits between them.

THE PRIOR IS WIDER THAN THE GATE WINDOW ON PURPOSE. The gate asks whether the
posterior concentrates inside 3-12 months (`omega` 0.01916-0.07665) AND off
its bounds; if the box were the window, "inside" would be a tautology.
Loguniform because `omega` is a strictly positive scale parameter spanning an
order of magnitude.

### 5.3 What must not be done to phi1

`phi1` is the week of peak TRANSMISSIBILITY and carries no peak-week prior
here or anywhere. Under COVID waning the epidemic peak LEADS `phi1` by a
median 11.0 weeks (IQR -14.4 to -7.8) in the same sweep; under influenza
waning the lead is 4.7 weeks. A prior placing `phi1` near the observed peak
week would be wrong by roughly a season quarter. The box stays uniform(0, 52).

### 5.4 Round two, arm A2: the second harmonic restored (`SIHRS_pop_covid_2h.bngl`)

Round one (pre-registration `5ad51005a827740c`) freed `omega` and nothing
else, on the sweep argument above. The fits then landed OUTSIDE the reachable
region: `eps1` collapsed to about 0.03 in all nine fits, `omega` concentrated
at 2.66 to 5.11 months, and the posterior-median models produced 1.00 peaks
per year, zero of nine bimodal, against 2 to 3 observed waves in the same
windows. Reachable was not reached. The sweep also measured that the second
harmonic roughly triples the bimodal region (6.7% -> 18.4% at COVID waning),
and the round-one width result (particle filter 1.105 against a 4.06 bar)
leaves room to pay for two dimensions. Whether the data spend that room on an
identified `eps2`, and whether the fitted model then produces two epidemics a
year, is exactly what round two's gates ask.

Verified numerically with the production simulator before round two was
frozen: with COVID waning, `eps2` in 0.20 to 0.35 produces 2.00 peaks per
year even at `eps1 = 0.03` (the collapsed round-one value) and `omega` inside
the round-one posterior range, e.g. R0 1.2 / eps1 0.03 / eps2 0.20 /
omega 17 wk -> 2.00 peaks/yr. The regime the arm needs is therefore reachable
at the amplitudes the priors allow.

Priors for the two added dimensions (frozen record: `gate_a2.py`):

* `eps2` uniform(0.0, 0.4). The bound is STIFFNESS-CRITICAL, carried from the
  measured flu 8-parameter box (`sihrs_fit.FITTED_PRIORS`):
  `beta_max = Reff*gamma*exp(eps1+eps2)`, and at this arm's prior corner
  (2.5 * 1.0234 * exp(1.4)) that is 10.4/wk, an order of magnitude below the
  roughly 77/wk corner that once made CVODE fail. Uniform because the lower
  bound is exactly 0, where log is undefined.
* `phi2` uniform(0.0, 26.0). The semi-annual harmonic has period 26 weeks, so
  the phase is identified only mod 26; the box spans one full period. No
  peak-week prior, for the same reason `phi1` carries none (section 5.3).

In arm A3 the `gamma` token is materialized with the realized-household value
instead; the token makes that a materialization choice, not an edit.

---

## 6. The two-strain variant (`SIHRS_pop_2strain_min.bngl`)

### 6.1 Motivation, measured (seal 2026-08-19)

The single-strain model's one catastrophic phase is the late-season type
turn. Feb 2024: A declines, B rises, NHSN admissions (the sum) plateau for 5
weeks; a single-strain fit forecasts decline and bleeds relWIS 1.485 for a
month. NREVSS clinical percent-positive SEES the turn as it happens (A
11%->5% while B 2.7%->6.9%, crossing at week 202411) -- but only a two-strain
state can use it.

### 6.2 Structure

Two INDEPENDENT SIHRS circuits over the same population `N` (independent
co-circulation: infection with one type does not protect against the other --
defensible for A versus B, different genera; the cost is expectation-level
double counting, standard for two-strain forecast ODEs). Each circuit spans
the whole population. Shared: population, ascertainment (`mult`), NB
dispersion (`r`), seasonal AMPLITUDE (`eps1`: both types ride the same winter
environment, and splitting it is unidentified from one season of split data).
Strain-specific: reproduction numbers and seasonal PHASE -- the B phase
sitting later in the season is the mechanism that generates spring B waves.

The production `min` trim drops `impr` (single-season fits; the filter
re-conditions weekly) and the semi-annual harmonic (the B circuit carries
two-wave structure mechanistically -- the hypothesis under test). The fully
annotated draft with `impr` retained is `SIHRS_pop_2strain.bngl`.

### 6.3 Observation channels

* NHSN admissions, negative binomial on the WEEKLY INCREMENT of the combined
  accumulator: `mu = mult * (H_Cum[week end] - H_Cum[week start])`, `H_Cum`
  summing `HadmA()` and `HadmB()` (see 6.4). The template's
  `H_weekly() = rho*mult*gamma*(Ia+Ib)` is the INSTANTANEOUS flux and is not
  that mean; it exists so a name-matched output column reaches the `.exp`
  file under `print_functions=>1`. See 1.4 for the size of the gap between
  the two and for which fitting path evaluates which.
* `A_share = Ia/(Ia+Ib)` -> NREVSS typed positives ratio,
  binomial via the engine's `_bin`/`_n` exp columns.

`A_share` assumes equal per-infection test-positivity ascertainment for A and
B; the shared factors cancel in the ratio, which is why `mult` does NOT
appear in it -- the two channels identify different things by design.

`{{A0SHARE}}` (strain-A share of initial infections) is KNOWN DATA from the
season's first as-of NREVSS reading, never fitted: the initial strain mix
comes from surveillance, the model only evolves it.

### 6.4 Engine constraint: exactly one `_Cum` observable

The engine's integrated mode globs the FIRST `_Cum` column, so only the
COMBINED accumulator (`H_Cum`, summing `HadmA()` and `HadmB()`) may carry the
suffix. BNGL observables sum multiple patterns natively. Per-strain
admissions are recoverable as `rho*gamma*Ia` / `rho*gamma*Ib` if ever needed.

### 6.5 Known refinement not taken in the draft

B severity differs from A; a refinement is `rhoB = c*rho` with `c` fixed from
FluSurv-NET typed burden. Kept shared so the fitted parameter count stays
down. `phi1B`'s prior is centered 6 to 10 weeks after `phi1A`, from NREVSS
history.

---

## 7. Change discipline

* Behavior lives in the code lines; provenance lives here. A template edit
  that only touches comments must leave the comment-stripped file and the
  generated `.net` byte-identical (that is how the 2026-08 trim was proved).
* `tests/test_min_template.py` pins `min` against `SIHRS_pop.bngl`;
  `app/tests/test_natgrowth.py` pins `natg` against `min` (identical
  structure blocks, same `__FREE` set, frozen iota, in-template forecast
  rule). Run both before shipping a template change.
