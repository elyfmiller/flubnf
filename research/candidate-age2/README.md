# Two-age-class SIHRS — candidate member, draft for testing

Draft of the age-structured mechanism ranked in
`research/2026-08-21-member-search-memo.md`. Nothing here is wired into
`flubnf/` or `app/`; everything is self-contained in this directory so it can be
reviewed while the rest of the tree is being edited. Integration is described
below as a patch to apply, not applied.

| file | what it is |
| --- | --- |
| `SIHRS_pop_age2_min.bngl` | the model, same trim as `SIHRS_pop_min.bngl` |
| `age2_tokens.py` | token derivation; standalone, imports nothing from the repo |

**Status: smoke-tested, not fitted.** BNG2.pl parses it, generates the network
and CVODE integrates it. It has never seen a particle filter or a real state.

## The hypothesis

Paediatric admissions lead adult admissions, and the lead lives *inside* the
target stream, so it cannot be an external concurrent correlate that merely
echoes the latent state. Measured before the model was written, NHSN age strata
2024-25, full grid: paediatric growth at week *t* predicts adult growth at
*t+1* with median partial correlation **+0.315** after conditioning on two lags
of adult growth (71% of 31 jurisdictions above +0.2, sign-consistent). The
paediatric *share level* is null on the same test (+0.09, sign-incoherent).

The information is in the growth, not the level. A two-class mechanism converts
that into an earlier turn without anyone hand-specifying a growth statistic —
which is the argument for a mechanism here rather than a feature.

## Design, and what was measured to fix it

Six fitted parameters against production's five. The new one is `theta`,
assortativity of mixing. Everything else that could have been fitted is a
sourced constant instead.

**`Reff` keeps its production meaning exactly.** `beta0` is divided by the
leading eigenvalue of the next-generation matrix, so the realised growth rate is
invariant to `theta` and to the contact structure. Verified: with each particle
on its own dominant eigenvector, early growth is 0.7738–0.7754 /wk across
`qk ∈ {1,2,3} × theta ∈ {0,0.4,0.8}` — invariant to 4 decimals. `theta`
therefore does not compete with `Reff` for the growth rate, which is the whole
identifiability argument for adding it.

**The lead is carried by contact intensity, not susceptibility.** My first draft
put the asymmetry in differential susceptibility and it does not work: `s0=0.85`
already puts most of the population in `S`, so children's susceptible fraction
can be at most `1/s0 = 1.176×` the mean before the child `R` compartment seeds
negative, and inside that ceiling the lead never exceeds ~0.4 weeks. (My sweep
initially ran `uk = 1.20` and `1.35`, which are past the ceiling and were
silently producing negative seed species — those rows were garbage.) With the
asymmetry in relative contact intensity `qk` instead, the lead is 0.26–1.72
weeks over `qk ∈ [1.5,3] × theta ∈ [0.2,0.8]`. At `qk=1` the two classes are
dynamically identical and the lead is exactly zero.

**The seed split must be a token, not an expression.** `PyBNF-pf`'s
`_init_cloud` does `engine.reset(); x0 = engine.get_state(); tile(x0, (P,1))` —
every particle starts from one species vector evaluated at the `.net` defaults.
Per-particle `theta` reaches the rate laws (re-evaluated from the
`ConstantExpression` graph on each `simulate_segment`) but never reaches the
initial condition. A `theta`-dependent seed would be silently frozen at the
default: self-consistent-looking and wrong. So `{{PEDI0}}` is computed offline,
which is what the engine does anyway. Measured cost, relative error in
week-1-to-3 growth against each particle's own correct seed:

| | theta=0.00 | 0.20 | 0.45 | 0.70 | 0.90 |
| --- | --- | --- | --- | --- | --- |
| qk=1.5 | +0.11% | +0.20% | 0.00% | −4.37% | −17.97% |
| qk=2.0 | +0.30% | +0.49% | 0.00% | −3.87% | −9.97% |
| qk=3.0 | +0.51% | +0.59% | 0.00% | −1.86% | −4.05% |

The error is strongly asymmetric, so the anchor sits *above* the prior mean at
`theta=0.45` and the prior caps at **0.7**, bounding worst-case bias at 4.4%.
That is where the cap comes from; it is not a round number.

`sqrt()` is safe: BNG2.pl parses it, it survives into the `.net` as a
`ConstantExpression`, and CVODE integrates it. The discriminant is written
`(m11-m22)^2 + 4*m12*m21` rather than `trace^2 - 4*det` so it cannot go
negative in floating point and return NaN.

## Validation run against the actual template

Tokens materialized the way `materialize_model` does, defaults block prepended
the way `pf.py` does, `qk=2.0`, `fk=0.205`, `rho` split to a 12% baseline share.

1. All tokens resolve; network generates; ODE integrates; `Ped_share` appears
   as a model column alongside `H_weekly` and `H_Cum`.
2. No negative species at any week; `H_Cum` monotone non-decreasing;
   `Ped_share ∈ [0,1]` throughout.
3. `Reff` invariance across the full prior support: +0.34%, +0.52%, 0.00%,
   −3.93% at `theta` = 0.00, 0.20, 0.45, 0.70 — matching the predicted bound.
4. The mechanism produces what it claims:

| theta | paed peak | adult peak | lead (wk) | share 4wk pre-peak | share at peak | drop |
| --- | --- | --- | --- | --- | --- | --- |
| 0.00 | 13.94 | 14.24 | 0.30 | 0.073 | 0.060 | −0.013 |
| 0.20 | 13.85 | 14.27 | 0.42 | 0.086 | 0.065 | −0.020 |
| 0.45 | 13.69 | 14.38 | 0.70 | 0.120 | 0.080 | −0.040 |
| 0.70 | 13.53 | 14.67 | 1.14 | 0.219 | 0.129 | −0.090 |

The falling paediatric share *before* the admissions peak is the turn signal,
and at n in the hundreds a 4-point drop is comfortably detectable.

## Data

`data.cdc.gov/resource/ua7e-t2fy` carries the strata directly:
`totalconfflunewadmped`, `totalconfflunewadmadult`, `numconfflunewadmunk`.

Coverage, 2024-25, Nov–Mar, all jurisdictions:

- **0 jurisdictions with no age breakdown.**
- 62 with median age-coded weekly denominator ≥ 30; 5 thin (AK, AS, GU, MP, VI).
- `ped + adult + unk == total` in **100%** of rows, so the binomial denominator
  is exact. Use `ped + adult`, excluding unknown-age, as the trials column.
- Pooled paediatric share: median 0.088, p10 0.033, p90 0.190.

This is the candidate's main advantage over the two-strain member: near-universal
availability, so the channel is on everywhere rather than gated to the subset of
states with adequate NREVSS typing volume.

### The blocker

**These strata are not vintage-capable.** Delphi carries the NHSN aggregate with
issue history; it does not carry the age columns, and Socrata exposes one
current view. A vintage-true retrospective cannot query the age split as of a
past Saturday. Two honest routes, both requiring pre-registration:

1. **Backfill emulation.** The age columns arrive in the same NHSN submission as
   the aggregate, whose backfill *is* measurable through Delphi. Apply the
   measured first-issue/final ratio to the age columns. This leans on backfill
   being roughly proportional across age — plausible, because hospitals report
   late as a block rather than selectively by age, and a *share* is far more
   robust to proportional revision than a *level* is. It is an assumption, not a
   fact, and must be labelled as one.
2. **Prospective only.** Start archiving as-of snapshots now and evaluate on
   2025-26 forward. Slower, but genuinely vintage-true, and it also lets route 1
   be tested rather than assumed.

I would not run the full retrospective grid on route 1 without first checking,
on whatever snapshots exist, whether the share is in fact revision-stable.

## Integration (not applied)

Mirrors the existing `variant == "2strain"` path in `app/core/engines/pf.py`.

```python
TEMPLATE_AGE2 = REPO / "research/candidate-age2/SIHRS_pop_age2_min.bngl"
DEFAULTS_AGE2 = ("begin parameters\nReff__FREE 1.20\neps1__FREE 0.15\n"
                 "phi1__FREE 22.0\ntheta__FREE 0.45\nmult__FREE 0.05\nr__FREE 8.0\n")
VARS_AGE2 = """uniform_var = Reff__FREE 0.6 2.5
uniform_var = eps1__FREE 0.0 1.0
uniform_var = phi1__FREE 0.0 52.0
uniform_var = theta__FREE 0.0 0.7
loguniform_var = mult__FREE 0.002 1.0
loguniform_var = r__FREE 0.1 40.0
"""
```

`prepare()` gains an `age2` branch alongside `two_strain`: build `extra_tokens`
with `age2_tokens.age2_tokens(...)`, and write the exp file as

```
# time H_weekly Ped_share_bin Ped_share_n
0 412.0 38 401
1 508.0 -1 -1        <- age split missing that week
```

`Ped_share_bin` = `totalconfflunewadmped`, `Ped_share_n` = ped + adult
(excluding unknown-age). Missing weeks take `-1 -1` and are skipped, exactly as
the NREVSS channel does. No fork change is needed — `classify_obs_cols` already
handles a list of `_bin` channels, and its own tests exercise two of them.

### The one config value that must not be inherited

`pf_binom_neff_cap = 30`, **not** the two-strain's 300.

The two-strain gets away with 300 because NREVSS typed counts are in the tens to
low hundreds, so the cap rarely binds. Here the denominator is total admissions —
thousands in large states — so the cap always binds and *is* the channel weight.
Per-week log-weight spread between two particles, admissions channel at `r=8`
with mu disagreeing by ±20%, versus the binomial channel at share 0.12 vs 0.16:

| weekly admissions | NB channel | cap=30 | cap=60 | cap=120 | cap=300 | uncapped |
| --- | --- | --- | --- | --- | --- | --- |
| 100 | 0.08 | 0.19 | 0.38 | 0.61 | 0.61 | 0.61 |
| 400 | 0.09 | 0.19 | 0.38 | 0.77 | 1.92 | 2.44 |
| 1000 | 0.09 | 0.19 | 0.38 | 0.77 | 1.92 | 6.09 |
| 3000 | 0.09 | 0.19 | 0.38 | 0.77 | 1.92 | 18.28 |

Uncapped, the share channel outweighs admissions by 70–200× in large states and
the filter stops being an admissions model. At 300 it still outweighs it ~20×.
At 30 the two channels are within a factor of ~2, which is the intended regime:
the share channel should inform the turn, not take over the level.

## Pre-registration

Fix before any fit touches data:

- `theta ~ U(0, 0.7)`; seed anchor `theta = 0.45`. Both fixed by the measured
  bias table above.
- `qk` fixed from published US contact matrices, never fitted. This is the
  parameter the whole mechanism rests on and it must not become a free knob.
- `uk = 1.0` in the primary arm, with the hard check `uk ≤ 1/s0`.
- `rhoK`, `rhoA` from `split_rho`, so the aggregate IHR is preserved (keeping
  `rho*mult`'s pinned meaning) and the baseline share matches that state's
  observed value. The binomial channel must argue about dynamics, not level.
- `pf_binom_neff_cap = 30`; sensitivity arms {15, 30, 60} on the selection
  surface only.
- Primary endpoint: relWIS against FluSight-baseline, and specifically whether
  the turn-phase deficit narrows. Ensemble stays equal-weight; no fitted weights.

Open question I could not settle without fitting: whether `theta` is identified
in practice or drifts to its prior mean and leaves the channel doing nothing.
The share dynamics should identify it — the pre-peak drop ranges from 1.3 to 9
points across the prior — but the filter has to actually recover it, and a
single-state pilot should confirm that before the grid runs.
